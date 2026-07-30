from pathlib import Path

from document_scanner.extractor import extract_findings
from document_scanner.models import DocumentPage

KEYWORDS = {
    "anti_graffiti": ["anti-graffiti", "protective film", "sacrificial coating"],
    "materials": [
        "aluminum composite",
        "aluminum",
        "stainless steel",
        "steel",
        "tempered glass",
        "dibond",
    ],
    "finishes": ["powder coated", "painted", "primer", "topcoat", "mill finished"],
    "colors": ["traffic yellow", "signal black"],
}


def page(text: str, *blocks: str) -> DocumentPage:
    return DocumentPage(Path("example.pdf"), 6, text, blocks)


def test_extracts_material_and_thickness_from_specification_example() -> None:
    findings = extract_findings(
        page("Aluminum composite: 3 mm thick Dibond, by Alusuisse Composites Inc."),
        KEYWORDS,
    )

    categories = {finding.category for finding in findings}
    assert "Materials" in categories
    assert "Thickness" in categories
    assert all(finding.page == 6 for finding in findings)
    assert any(finding.material.casefold() == "aluminum composite" for finding in findings)
    assert any(finding.thickness == "3 mm" for finding in findings)


def test_extracts_finish_dry_film_thickness() -> None:
    findings = extract_findings(
        page("Paint Finish: Primer: 0.051 mm DFT. Topcoat: Two coats, 0.127 mm DFT."),
        KEYWORDS,
    )

    thicknesses = {finding.thickness for finding in findings}
    assert "0.051 mm" in thicknesses
    assert "0.127 mm" in thicknesses
    assert {
        finding.matched_term.casefold() for finding in findings if finding.category == "Finishes"
    } >= {
        "primer",
        "topcoat",
    }


def test_extracts_drawing_style_material_and_finish() -> None:
    findings = extract_findings(
        page(
            "Panel D - 5mm steel side panels. "
            "Finish Option 2 Powder Coated surface, face and edges."
        ),
        KEYWORDS,
    )

    assert any(finding.component.casefold().startswith("panel d") for finding in findings)
    assert any(finding.material.casefold() == "steel" for finding in findings)
    assert any(finding.finish.casefold() == "powder coated" for finding in findings)
    assert any(finding.thickness.casefold() == "5mm" for finding in findings)


def test_ignores_dimension_without_thickness_context() -> None:
    findings = extract_findings(
        page("Allow a minimum clearance of 50 mm for opening face frame."), KEYWORDS
    )

    assert not any(finding.category == "Thickness" for finding in findings)


def test_extracts_anti_graffiti_requirement() -> None:
    findings = extract_findings(
        page("Apply replaceable anti-graffiti protective film to the tempered glass face."),
        KEYWORDS,
    )

    assert any(finding.category == "Anti Graffiti" for finding in findings)
    assert any(finding.anti_graffiti.casefold() == "anti-graffiti" for finding in findings)
    assert any(finding.material.casefold() == "tempered glass" for finding in findings)


def test_drawing_blocks_do_not_mix_unrelated_callouts() -> None:
    page_17 = page(
        "",
        "Panel A - Upper cap\nWelded steel with clean welded edges along sides and top\n"
        "Finish Option 1\nPainted base surface (Yellow).\n"
        "Finish Option 2\nPowder Coated base surface (Yellow).",
        "Panel B - Middle\nTempered glass graphics digitally imaged to vinyl film "
        "applied to 2nd surface.",
        "Panel D - 5mm steel side panels\nFinish Option 1\nPainted surface, face and edges\n"
        "Finish Option 2\nPowder Coated surface, face and edges",
        "620\n150\n340\n1500\n2828\n778\n2134",
    )

    findings = extract_findings(page_17, KEYWORDS)

    panel_a = [finding for finding in findings if finding.component == "Panel A - Upper cap"]
    panel_b = [finding for finding in findings if finding.component == "Panel B - Middle"]
    panel_d = [finding for finding in findings if finding.component == "Panel D"]

    assert panel_a
    assert all(finding.material.casefold() == "steel" for finding in panel_a)
    assert all(finding.thickness == "" for finding in panel_a)
    assert panel_b
    assert all(finding.material.casefold() == "tempered glass" for finding in panel_b)
    assert panel_d
    assert all(finding.material.casefold() == "steel" for finding in panel_d)
    assert all(finding.thickness == "5mm" for finding in panel_d)
    assert not any(finding.matched_term in {"620", "1500", "2134"} for finding in findings)


def test_large_drawing_dimension_is_not_material_thickness() -> None:
    findings = extract_findings(
        page("Post Details\nMaximum of 5 panels.\n2134 mm overall height."),
        KEYWORDS,
    )

    assert not any(finding.category == "Thickness" for finding in findings)
