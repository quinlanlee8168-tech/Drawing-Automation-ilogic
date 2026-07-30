import csv
from pathlib import Path

from document_scanner.models import Finding

HEADERS = [
    "Document",
    "Page",
    "Category",
    "Component",
    "Material",
    "Finish",
    "Thickness",
    "Anti-graffiti",
    "Matched term",
    "Source text",
    "Review status",
]


def export_csv(findings: list[Finding], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.writer(file)
        writer.writerow(HEADERS)
        for finding in findings:
            writer.writerow(
                [
                    finding.document,
                    finding.page,
                    finding.category,
                    finding.component,
                    finding.material,
                    finding.finish,
                    finding.thickness,
                    finding.anti_graffiti,
                    finding.matched_term,
                    finding.source_text,
                    finding.review_status,
                ]
            )
