import json
from pathlib import Path

import pytest

pymupdf = pytest.importorskip("pymupdf")

from document_scanner.models import Finding  # noqa: E402
from document_scanner.visual_exporter import (  # noqa: E402
    export_visual_pages,
    parse_page_selection,
)


def finding(page: int = 1) -> Finding:
    return Finding(
        document="drawing.pdf",
        page=page,
        category="Materials",
        component="Panel D",
        material="steel",
        finish="",
        thickness="5 mm",
        anti_graffiti="",
        matched_term="steel",
        source_text="Panel D - 5mm steel side panels.",
    )


def create_pdf(path: Path) -> None:
    document = pymupdf.open()
    for page_number in (1, 2):
        page = document.new_page(width=400, height=300)
        page.insert_text((40, 50), f"Panel D page {page_number}")
        page.draw_line((100, 100), (250, 180))
    document.save(path)
    document.close()


def test_parse_page_selection() -> None:
    assert parse_page_selection("") is None
    assert parse_page_selection("17, 19,17") == {17, 19}
    with pytest.raises(ValueError, match="positive PDF page numbers"):
        parse_page_selection("17, page 19")


def test_export_visual_pages_renders_requested_finding_page(tmp_path: Path) -> None:
    pdf_path = tmp_path / "drawing.pdf"
    create_pdf(pdf_path)
    output_directory = tmp_path / "visual"

    result = export_visual_pages(
        pdf_path,
        [finding(1), finding(2)],
        output_directory,
        page_numbers={2},
    )

    assert [path.name for path in result.image_paths] == ["drawing-page-0002.png"]
    assert result.image_paths[0].read_bytes().startswith(b"\x89PNG")
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["pages"][0]["document"] == "drawing.pdf"
    assert manifest["pages"][0]["page"] == 2


def test_export_visual_pages_rejects_pages_without_findings(tmp_path: Path) -> None:
    pdf_path = tmp_path / "drawing.pdf"
    create_pdf(pdf_path)

    with pytest.raises(ValueError, match="No findings exist"):
        export_visual_pages(pdf_path, [finding()], tmp_path / "visual", page_numbers={17})
