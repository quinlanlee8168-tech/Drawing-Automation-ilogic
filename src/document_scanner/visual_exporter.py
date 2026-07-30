import json
import re
from dataclasses import dataclass
from pathlib import Path

import pymupdf

from document_scanner.models import Finding
from document_scanner.pdf_reader import discover_pdfs

INVALID_FILENAME_CHARACTERS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


@dataclass(frozen=True, slots=True)
class VisualExportResult:
    image_paths: tuple[Path, ...]
    manifest_path: Path
    warnings: tuple[str, ...] = ()


def parse_page_selection(value: str) -> set[int] | None:
    """Parse a comma-separated page list. A blank value means all finding pages."""
    if not value.strip():
        return None

    pages: set[int] = set()
    for item in value.split(","):
        candidate = item.strip()
        if not candidate:
            continue
        if not candidate.isdigit() or int(candidate) < 1:
            raise ValueError(
                "Enter positive PDF page numbers separated by commas, for example: 17, 19, 34."
            )
        pages.add(int(candidate))
    if not pages:
        raise ValueError("Enter at least one PDF page number, or leave the field blank.")
    return pages


def _safe_stem(value: str) -> str:
    safe = INVALID_FILENAME_CHARACTERS.sub("_", value).strip(" .")
    return safe or "document"


def export_visual_pages(
    selected_path: Path,
    findings: list[Finding],
    output_directory: Path,
    page_numbers: set[int] | None = None,
    dpi: int = 150,
) -> VisualExportResult:
    """Render finding pages as PNGs so a vision-capable AI can inspect drawing callouts."""
    if dpi < 72:
        raise ValueError("Visual page export requires a resolution of at least 72 DPI.")

    requested: dict[str, set[int]] = {}
    for finding in findings:
        if page_numbers is None or finding.page in page_numbers:
            requested.setdefault(finding.document, set()).add(finding.page)
    if not requested:
        raise ValueError("No findings exist on the selected page numbers.")

    pdfs_by_name: dict[str, list[Path]] = {}
    for pdf_path in discover_pdfs(selected_path):
        pdfs_by_name.setdefault(pdf_path.name, []).append(pdf_path)

    output_directory.mkdir(parents=True, exist_ok=True)
    image_paths: list[Path] = []
    manifest_pages: list[dict[str, object]] = []
    warnings: list[str] = []
    scale = dpi / 72
    matrix = pymupdf.Matrix(scale, scale)

    for document_name, pages in sorted(requested.items(), key=lambda item: item[0].casefold()):
        matches = pdfs_by_name.get(document_name, [])
        if not matches:
            warnings.append(f"Could not locate source PDF: {document_name}")
            continue
        if len(matches) > 1:
            warnings.append(
                f"Skipped {document_name}: more than one PDF with that filename was found."
            )
            continue

        pdf_path = matches[0]
        with pymupdf.open(pdf_path) as document:
            for page_number in sorted(pages):
                if page_number > document.page_count:
                    warnings.append(
                        f"Skipped {document_name} page {page_number}: "
                        f"the PDF has only {document.page_count} pages."
                    )
                    continue
                output_path = output_directory / (
                    f"{_safe_stem(pdf_path.stem)}-page-{page_number:04d}.png"
                )
                pixmap = document[page_number - 1].get_pixmap(matrix=matrix, alpha=False)
                pixmap.save(output_path)
                image_paths.append(output_path)
                manifest_pages.append(
                    {
                        "image": output_path.name,
                        "document": document_name,
                        "page": page_number,
                        "purpose": (
                            "Inspect labels, arrows, leader lines, dimensions, and their "
                            "visual relationship to drawing components."
                        ),
                    }
                )

    if not image_paths:
        details = "\n".join(warnings) or "No matching PDF pages were available."
        raise ValueError(f"No visual pages were exported.\n{details}")

    manifest_path = output_directory / "visual-pages-manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "instructions": (
                    "Use each PNG together with the evidence package. The PNG establishes "
                    "visual callout-to-component relationships; the evidence source_text "
                    "remains authoritative for specification wording."
                ),
                "pages": manifest_pages,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return VisualExportResult(tuple(image_paths), manifest_path, tuple(warnings))
