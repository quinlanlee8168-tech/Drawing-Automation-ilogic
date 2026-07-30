import json
from pathlib import Path

from document_scanner.ai_summarizer import SUMMARY_JSON_SCHEMA, SummaryResult, validate_summary
from document_scanner.models import Finding

MANUAL_PROMPT = """
Analyze the attached wayfinding AI evidence package.

Return the final answer as JSON only. Do not create Excel, CSV, Markdown tables, commentary,
or code fences. Follow the `required_summary_schema` in the evidence package exactly.

Rules:
- Use one row per component, material, distinct finish, document, and page.
- Never combine multiple page numbers in one row.
- If page PNG images are attached, inspect the visual drawing layout before assigning evidence.
- Follow arrows and leader lines from each note to the component they identify. Use nearby labels
  such as Panel A, Panel B, Panel C, and Panel D to resolve otherwise unassigned evidence.
- Use page images only to establish visual relationships and readable drawing information.
  Do not invent a relationship when a leader line is unclear or obscured.
- Treat drawing dimensions as geometry unless a callout explicitly describes material,
  coating, or film thickness.
- Do not include Drawing Number, Option, Material Role, Component ID, Component Name, or
  Component Type fields.
- Use one `component` field with a readable description.
- Combine the color name and every stated Pantone, RAL, HEX, CMYK, or manufacturer code in
  the single `color` field.
- Use null for unstated values.
- Treat source_text as authoritative; candidate values may be wrong.
- Cite only evidence IDs from the same document and page as the row.
- Do not guess. Report ambiguity in conflicts or missing_fields.
- Confidence must be high, medium, or low.

The response must be a JSON object with one top-level key named `rows`.
""".strip()


def export_manual_prompt(output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    schema_text = json.dumps(SUMMARY_JSON_SCHEMA, indent=2, ensure_ascii=False)
    output_path.write_text(
        f"{MANUAL_PROMPT}\n\nRequired JSON Schema:\n{schema_text}\n",
        encoding="utf-8",
    )


def _strip_code_fence(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```") and stripped.endswith("```"):
        lines = stripped.splitlines()
        return "\n".join(lines[1:-1]).strip()
    return stripped


def load_chatgpt_summary(path: Path, findings: list[Finding]) -> SummaryResult:
    try:
        data = json.loads(_strip_code_fence(path.read_text(encoding="utf-8")))
    except json.JSONDecodeError as error:
        raise ValueError(
            f"The ChatGPT result is not valid JSON (line {error.lineno}). "
            "Ask ChatGPT to return JSON only, then download it again."
        ) from error

    summary = SummaryResult.from_dict(data)
    validate_summary(summary, findings)
    return summary
