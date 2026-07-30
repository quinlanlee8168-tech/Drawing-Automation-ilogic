import csv
import json
from pathlib import Path

from document_scanner.ai_summarizer import SummaryResult, SummaryRow

SUMMARY_HEADERS = [
    "Sign Type",
    "Component",
    "Material",
    "Grade / Alloy / Temper",
    "Material Thickness",
    "Finish System",
    "Color",
    "Coating / Film Thickness",
    "Surface / Application",
    "Anti-Graffiti Requirement",
    "Manufacturer",
    "Product",
    "Standards",
    "Document",
    "Page",
    "Evidence IDs",
    "Conflicts",
    "Missing Information",
    "Confidence",
]


def _join(values: list[str]) -> str:
    return "; ".join(dict.fromkeys(value for value in values if value))


def summary_row(row: SummaryRow) -> list[str | int]:
    return [
        row.sign_type or "Not specified",
        row.component,
        row.material or "Not specified",
        row.grade_alloy_temper or "Not specified",
        row.material_thickness or "Not specified",
        row.finish_system or "Not specified",
        row.color or "Not specified",
        row.coating_film_thickness or "Not specified",
        row.surface_application or "Not specified",
        row.anti_graffiti_requirement or "Not specified",
        row.manufacturer or "Not specified",
        row.product or "Not specified",
        _join(row.standards) or "Not specified",
        row.document,
        row.page,
        _join(row.evidence_ids),
        _join(row.conflicts),
        _join(row.missing_fields),
        row.confidence,
    ]


def export_summary_csv(summary: SummaryResult, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.writer(file)
        writer.writerow(SUMMARY_HEADERS)
        writer.writerows(summary_row(row) for row in summary.rows)


def export_summary_json(summary: SummaryResult, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(summary.as_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
