from pathlib import Path

import pymupdf

from document_scanner.models import DocumentPage


def discover_pdfs(path: Path) -> list[Path]:
    if path.is_file():
        return [path] if path.suffix.casefold() == ".pdf" else []
    if path.is_dir():
        return sorted(
            (candidate for candidate in path.rglob("*.pdf") if candidate.is_file()),
            key=lambda candidate: str(candidate).casefold(),
        )
    return []


def extract_pdf_pages(pdf_path: Path) -> list[DocumentPage]:
    pages: list[DocumentPage] = []
    with pymupdf.open(pdf_path) as document:
        for page_index, page in enumerate(document):
            blocks = tuple(
                block[4].strip()
                for block in page.get_text("blocks", sort=True)
                if len(block) > 4 and block[4].strip()
            )
            pages.append(
                DocumentPage(
                    document_path=pdf_path,
                    page_number=page_index + 1,
                    text="\n".join(blocks),
                    text_blocks=blocks,
                )
            )
    return pages
