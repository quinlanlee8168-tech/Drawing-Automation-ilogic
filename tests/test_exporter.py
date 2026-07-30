from pathlib import Path

from document_scanner.exporter import export_csv
from document_scanner.models import Finding


def test_export_csv_writes_excel_compatible_file(tmp_path: Path) -> None:
    output = tmp_path / "findings.csv"
    finding = Finding(
        document="spec.pdf",
        page=4,
        category="Materials",
        component="Panel C",
        material="Aluminum",
        finish="Powder coated",
        thickness="3 mm",
        anti_graffiti="",
        matched_term="Aluminum",
        source_text="Panel C is 3 mm aluminum.",
    )

    export_csv([finding], output)
    contents = output.read_text(encoding="utf-8-sig")

    assert "Document,Page,Category" in contents
    assert "spec.pdf,4,Materials,Panel C,Aluminum" in contents
