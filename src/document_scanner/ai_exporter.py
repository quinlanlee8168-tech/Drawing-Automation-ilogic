import json
import re
from collections import defaultdict
from pathlib import Path

from document_scanner.models import Finding

AI_TASK = """
Create a component-based material and finish schedule from the supplied evidence groups.
Do not guess missing values. Keep mutually exclusive finish options separate. Associate a
thickness only with the material or coating explicitly supported by evidence. Treat drawing
dimensions as geometry unless the evidence explicitly identifies material or coating
thickness. Cite evidence_ids for every populated value and report conflicts and missing fields.
""".strip()

SUMMARY_SCHEMA = {
    "sign_type": "Sign family/type when stated",
    "component": "One clear component description",
    "material": "One base or applied material for this row",
    "grade_alloy_temper": "Grade, alloy, temper, or material type",
    "material_thickness": "Material thickness only",
    "finish_system": "Paint, powder coat, anodize, film, digital print, etc.",
    "color": "One combined cell with color name and all stated color codes",
    "coating_film_thickness": "Coating DFT or film thickness only",
    "surface_application": "Face, edges, second surface, exterior, etc.",
    "anti_graffiti_requirement": "Requirement or null when unstated",
    "manufacturer": "Manufacturer when stated",
    "product": "Product/model when stated",
    "standards": ["ASTM, ANSI, UL, or other standards"],
    "document": "Exactly one source document",
    "page": "Exactly one source page number; never a list",
    "evidence_ids": ["Evidence IDs from that same document and page"],
    "conflicts": ["Contradictory or unresolved requirements"],
    "missing_fields": ["Important values not stated"],
    "confidence": "high, medium, or low",
}


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _option(text: str) -> str:
    match = re.search(r"\b(?:finish\s+)?option\s+([A-Z0-9]+)\b", text, re.IGNORECASE)
    return f"Option {match.group(1)}" if match else ""


def build_ai_package(findings: list[Finding]) -> dict[str, object]:
    """Build an auditable retrieval package for a later AI summarization step."""
    grouped: dict[tuple[str, int, str], list[tuple[int, Finding]]] = defaultdict(list)
    for index, finding in enumerate(findings, start=1):
        component = finding.component.strip() or "Unassigned"
        grouped[(finding.document, finding.page, component)].append((index, finding))

    evidence_groups: list[dict[str, object]] = []
    for (document, page, component), entries in sorted(grouped.items()):
        evidence = []
        for index, finding in entries:
            evidence.append(
                {
                    "evidence_id": f"E{index:05d}",
                    "category": finding.category,
                    "matched_term": finding.matched_term,
                    "source_text": finding.source_text,
                    "review_status": finding.review_status,
                }
            )

        group_findings = [finding for _, finding in entries]
        evidence_groups.append(
            {
                "document": document,
                "page": page,
                "component_hint": component,
                "option_hints": _unique(
                    [_option(finding.source_text) for finding in group_findings]
                ),
                "candidate_values": {
                    "materials": _unique([finding.material for finding in group_findings]),
                    "finishes": _unique([finding.finish for finding in group_findings]),
                    "thicknesses": _unique([finding.thickness for finding in group_findings]),
                    "anti_graffiti": _unique([finding.anti_graffiti for finding in group_findings]),
                },
                "evidence": evidence,
            }
        )

    return {
        "format_version": "1.0",
        "purpose": "AI-ready evidence package; candidate values are not final requirements.",
        "instructions": AI_TASK,
        "required_summary_schema": SUMMARY_SCHEMA,
        "evidence_groups": evidence_groups,
    }


def export_ai_json(findings: list[Finding], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as file:
        json.dump(build_ai_package(findings), file, indent=2, ensure_ascii=False)
        file.write("\n")
