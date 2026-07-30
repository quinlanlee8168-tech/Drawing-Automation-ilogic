import json
from pathlib import Path

import pytest

from document_scanner.manual_chatgpt import export_manual_prompt, load_chatgpt_summary
from document_scanner.models import Finding
from document_scanner.summary_exporter import export_summary_csv


def finding() -> Finding:
    return Finding(
        document="Addendum.pdf",
        page=17,
        category="Materials",
        component="Panel D",
        material="steel",
        finish="Powder Coated",
        thickness="5mm",
        anti_graffiti="",
        matched_term="steel",
        source_text="Panel D - 5mm steel side panels.",
    )


def valid_summary() -> dict[str, object]:
    return {
        "rows": [
            {
                "sign_type": "S1-A",
                "component": "Panel D - Side panels",
                "material": "Steel",
                "grade_alloy_temper": None,
                "material_thickness": "5 mm",
                "finish_system": "Powder coated",
                "color": "Yellow / Pantone 123 C",
                "coating_film_thickness": None,
                "surface_application": "Face and edges",
                "anti_graffiti_requirement": None,
                "manufacturer": None,
                "product": None,
                "standards": [],
                "document": "Addendum.pdf",
                "page": 17,
                "evidence_ids": ["E00001"],
                "conflicts": [],
                "missing_fields": ["Steel grade"],
                "confidence": "high",
            }
        ]
    }


def test_manual_prompt_requires_json_only_and_fixed_schema(tmp_path: Path) -> None:
    output = tmp_path / "prompt.txt"
    export_manual_prompt(output)
    text = output.read_text(encoding="utf-8")

    assert "Return the final answer as JSON only" in text
    assert '"component"' in text
    assert '"color"' in text
    assert '"drawing_number"' not in text
    assert "Follow arrows and leader lines" in text


def test_load_chatgpt_summary_and_generate_consistent_csv(tmp_path: Path) -> None:
    input_path = tmp_path / "chatgpt.json"
    input_path.write_text(json.dumps(valid_summary()), encoding="utf-8")

    summary = load_chatgpt_summary(input_path, [finding()])
    output_path = tmp_path / "summary.csv"
    export_summary_csv(summary, output_path)

    text = output_path.read_text(encoding="utf-8-sig")
    assert text.startswith("Sign Type,Component,Material")
    assert "S1-A,Panel D - Side panels,Steel" in text


def test_load_chatgpt_summary_accepts_json_code_fence(tmp_path: Path) -> None:
    input_path = tmp_path / "chatgpt.txt"
    input_path.write_text(
        f"```json\n{json.dumps(valid_summary())}\n```",
        encoding="utf-8",
    )

    assert load_chatgpt_summary(input_path, [finding()]).rows[0].page == 17


def test_load_chatgpt_summary_rejects_changed_columns(tmp_path: Path) -> None:
    data = valid_summary()
    data["rows"][0]["option"] = "Option 2"
    input_path = tmp_path / "chatgpt.json"
    input_path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ValueError, match="unexpected fields: option"):
        load_chatgpt_summary(input_path, [finding()])
