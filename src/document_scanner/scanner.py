from collections.abc import Callable
from pathlib import Path

from document_scanner.extractor import extract_findings
from document_scanner.models import Finding
from document_scanner.pdf_reader import discover_pdfs, extract_pdf_pages

ProgressCallback = Callable[[int, int, str], None]


def scan_path(
    path: Path,
    keyword_groups: dict[str, list[str]],
    progress: ProgressCallback | None = None,
) -> tuple[list[Finding], list[str]]:
    pdf_paths = discover_pdfs(path)
    findings: list[Finding] = []
    warnings: list[str] = []

    for document_index, pdf_path in enumerate(pdf_paths, start=1):
        if progress:
            progress(document_index - 1, len(pdf_paths), f"Opening {pdf_path.name}")
        try:
            pages = extract_pdf_pages(pdf_path)
        except Exception as error:
            warnings.append(f"Could not read {pdf_path.name}: {error}")
            continue

        if pages and not any(page.text.strip() for page in pages):
            warnings.append(f"{pdf_path.name} has no searchable text and may require OCR.")

        for page in pages:
            findings.extend(extract_findings(page, keyword_groups))

        if progress:
            progress(document_index, len(pdf_paths), f"Scanned {pdf_path.name}")

    return findings, warnings
