import re
from collections.abc import Iterable

from document_scanner.models import DocumentPage, Finding

MEASUREMENT_VALUE = (
    r"(?:\d+(?:\.\d+)?\s*(?:mm|cm|µm|μm|microns?|mils?|gauge|ga\.?)\b"
    r"|\d+(?:\.\d+)?\s*(?:inches|inch|in\.?)\b"
    r"|\d+\s*/\s*\d+\s*(?:\"|inches|inch|in\.?))"
)
EXPLICIT_THICKNESS_PATTERN = re.compile(
    rf"(?:"
    rf"(?P<before>{MEASUREMENT_VALUE})\s*(?:thick(?:ness)?|dft|dry\s+film)\b"
    rf"|(?:thick(?:ness)?|dft|dry\s+film)\s*(?:of|:|is|shall\s+be)?\s*"
    rf"(?P<after>{MEASUREMENT_VALUE})"
    rf")",
    re.IGNORECASE,
)
MATERIAL_THICKNESS_PATTERN = re.compile(
    rf"(?P<value>{MEASUREMENT_VALUE})\s+"
    r"(?:aluminum|aluminium|steel|glass|polycarbonate|acrylic|dibond|mdf)\b",
    re.IGNORECASE,
)

COMPONENT_PATTERNS = [
    re.compile(
        r"\b(?:panel|frame|post|cap|face|signbox|glazing|glass|gasket|fastener|"
        r"sheet|plate|graphic|backer panel|kiosk)s?\s+[A-Z0-9-]*\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bPanel\s+[A-Z](?:\s*-\s*[A-Za-z ]+)?", re.IGNORECASE),
]


def normalize_text(text: str) -> str:
    return " ".join(text.replace("\u00ad", "").split())


def split_contexts(text: str) -> list[str]:
    normalized = normalize_text(text)
    if not normalized:
        return []
    pieces = re.split(r"(?<=[.!?;:])\s+(?=[A-Z0-9])", normalized)
    return [piece.strip() for piece in pieces if piece.strip()]


def _term_pattern(term: str) -> re.Pattern[str]:
    escaped = re.escape(term).replace(r"\ ", r"[\s-]+")
    return re.compile(rf"(?<!\w){escaped}(?!\w)", re.IGNORECASE)


def _find_terms(text: str, terms: Iterable[str]) -> list[str]:
    found: list[str] = []
    for term in terms:
        match = _term_pattern(term).search(text)
        if match:
            found.append(match.group())
    return found


def _first_term(text: str, terms: Iterable[str]) -> str:
    matches = _find_terms(text, terms)
    return matches[0] if matches else ""


def _component(text: str) -> str:
    first_line = next((normalize_text(line) for line in text.splitlines() if line.strip()), "")
    panel_match = re.match(
        r"Panel\s+[A-Z0-9]+(?:\s*-\s*[^:.;]+)?",
        first_line,
        re.IGNORECASE,
    )
    if panel_match:
        component = re.split(
            r"\b(?:welded|tempered|finish|digitally|powder|painted|extends)\b|\d",
            panel_match.group(),
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0]
        return component.strip(" -")
    for pattern in COMPONENT_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group().strip()
    return ""


def _measurements(text: str) -> list[str]:
    measurements: list[str] = []
    for match in EXPLICIT_THICKNESS_PATTERN.finditer(text):
        value = match.group("before") or match.group("after")
        measurements.append(normalize_text(value))
    for match in MATERIAL_THICKNESS_PATTERN.finditer(text):
        measurements.append(normalize_text(match.group("value")))
    return list(dict.fromkeys(measurements))


def _contexts(page: DocumentPage) -> list[tuple[str, str]]:
    """Return normalized contexts paired with their local, unflattened PDF block."""
    blocks = page.text_blocks or (page.text,)
    contexts: list[tuple[str, str]] = []
    for block in blocks:
        normalized_block = normalize_text(block)
        if not normalized_block:
            continue
        pieces = split_contexts(block)
        if not pieces:
            pieces = [normalized_block]
        contexts.extend((piece, block) for piece in pieces)
    return contexts


def extract_findings(
    page: DocumentPage,
    keyword_groups: dict[str, list[str]],
) -> list[Finding]:
    findings: list[Finding] = []
    seen: set[tuple[str, str, str]] = set()
    contexts = _contexts(page)

    for context, source_block in contexts:
        expanded = normalize_text(source_block)
        category_matches = {
            category: _find_terms(context, terms) for category, terms in keyword_groups.items()
        }
        measurements = _measurements(context)

        matched_categories = [category for category, matches in category_matches.items() if matches]
        if measurements:
            matched_categories.append("thickness")

        for category in matched_categories:
            matched_term = (
                measurements[0] if category == "thickness" else category_matches[category][0]
            )
            key = (category, matched_term.casefold(), context.casefold())
            if key in seen:
                continue
            seen.add(key)

            material = _first_term(expanded, keyword_groups.get("materials", []))
            finish = _first_term(expanded, keyword_groups.get("finishes", []))
            anti_graffiti = _first_term(expanded, keyword_groups.get("anti_graffiti", []))
            local_measurements = _measurements(context)
            block_measurements = _measurements(expanded)
            if not local_measurements and len(block_measurements) == 1:
                local_measurements = block_measurements
            thickness = "; ".join(local_measurements)

            findings.append(
                Finding(
                    document=page.document_path.name,
                    page=page.page_number,
                    category=category.replace("_", " ").title(),
                    component=_component(source_block),
                    material=material,
                    finish=finish,
                    thickness=thickness,
                    anti_graffiti=anti_graffiti,
                    matched_term=matched_term,
                    source_text=context,
                )
            )

    return findings
