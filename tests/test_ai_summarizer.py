import json
from pathlib import Path

import pytest

from document_scanner.ai_summarizer import summarize_findings
from document_scanner.models import Finding
from document_scanner.summary_exporter import export_summary_csv, export_summary_json


def finding(page: int = 17) -> Finding:
    return Finding(
        document="Addendum.pdf",
        page=page,
        category="Materials",
        component="Panel D",
        material="steel",
        finish="Powder Coated",
        thickness="5mm",
        anti_graffiti="",
        matched_term="steel",
        source_text="Finish Option 2 Powder Coated 5mm steel side panels.",
    )


def api_response(evidence_id: str = "E00001", page: int = 17) -> dict[str, object]:
    summary = {
        "rows": [
            {
                "sign_type": "S1-A",
                "component": "Panel D - Side panels",
                "material": "Steel",
                "grade_alloy_temper": None,
                "material_thickness": "5 mm",
                "finish_system": "Powder coated",
                "color": "Yellow / Pantone 123 C / HEX #FFC72C",
                "coating_film_thickness": None,
                "surface_application": "Face and edges",
                "anti_graffiti_requirement": None,
                "manufacturer": None,
                "product": None,
                "standards": [],
                "document": "Addendum.pdf",
                "page": page,
                "evidence_ids": [evidence_id],
                "conflicts": [],
                "missing_fields": ["Steel grade"],
                "confidence": "high",
            }
        ]
    }
    return {
        "output": [
            {
                "type": "message",
                "content": [{"type": "output_text", "text": json.dumps(summary)}],
            }
        ]
    }


def test_summarize_findings_uses_simple_single_page_schema() -> None:
    captured = {}

    def transport(request, timeout):
        captured["payload"] = json.loads(request.data)
        return api_response()

    result = summarize_findings([finding()], "secret-key", transport=transport)

    assert result.rows[0].component == "Panel D - Side panels"
    assert result.rows[0].page == 17
    properties = captured["payload"]["text"]["format"]["schema"]["properties"]["rows"]["items"][
        "properties"
    ]
    assert "component" in properties
    assert "component_id" not in properties
    assert "material_role" not in properties
    assert "drawing_number" not in properties
    assert "option" not in properties
    assert "color" in properties
    assert "color_name" not in properties
    assert "color_code" not in properties
    assert properties["page"]["type"] == "integer"


def test_summarize_findings_rejects_unknown_evidence_id() -> None:
    with pytest.raises(ValueError, match="unknown evidence IDs"):
        summarize_findings(
            [finding()],
            "secret-key",
            transport=lambda request, timeout: api_response("E99999"),
        )


def test_summarize_findings_rejects_cross_page_grouping() -> None:
    with pytest.raises(ValueError, match="another page"):
        summarize_findings(
            [finding(17), finding(19)],
            "secret-key",
            transport=lambda request, timeout: api_response("E00002", page=17),
        )


def test_summary_exports_clear_flat_csv_and_json(tmp_path: Path) -> None:
    result = summarize_findings(
        [finding()],
        "secret-key",
        transport=lambda request, timeout: api_response(),
    )
    csv_path = tmp_path / "summary.csv"
    json_path = tmp_path / "summary.json"

    export_summary_csv(result, csv_path)
    export_summary_json(result, json_path)

    csv_text = csv_path.read_text(encoding="utf-8-sig")
    assert "Sign Type,Component,Material" in csv_text
    assert "Component ID" not in csv_text
    assert "Material Role" not in csv_text
    assert "Drawing Number" not in csv_text
    assert "Option" not in csv_text
    assert "Color Name" not in csv_text
    assert "Color Code" not in csv_text
    assert "Color" in csv_text
    assert "S1-A,Panel D - Side panels,Steel" in csv_text
    assert json.loads(json_path.read_text(encoding="utf-8"))["rows"][0]["page"] == 17
