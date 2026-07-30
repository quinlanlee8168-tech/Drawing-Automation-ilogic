import json
from pathlib import Path

from document_scanner.ai_exporter import build_ai_package, export_ai_json
from document_scanner.models import Finding


def finding(**overrides: object) -> Finding:
    values = {
        "document": "Addendum.pdf",
        "page": 17,
        "category": "Materials",
        "component": "Panel D",
        "material": "steel",
        "finish": "Powder Coated",
        "thickness": "5mm",
        "anti_graffiti": "",
        "matched_term": "steel",
        "source_text": "Finish Option 2 Powder Coated 5mm steel side panels.",
    }
    values.update(overrides)
    return Finding(**values)


def test_ai_package_groups_component_evidence_and_preserves_options() -> None:
    package = build_ai_package(
        [
            finding(),
            finding(
                category="Finishes",
                matched_term="Powder Coated",
                source_text="Finish Option 2 Powder Coated surface, face and edges.",
            ),
        ]
    )

    groups = package["evidence_groups"]
    assert len(groups) == 1
    group = groups[0]
    assert group["component_hint"] == "Panel D"
    assert group["option_hints"] == ["Option 2"]
    assert group["candidate_values"]["materials"] == ["steel"]
    assert group["candidate_values"]["thicknesses"] == ["5mm"]
    assert [item["evidence_id"] for item in group["evidence"]] == ["E00001", "E00002"]


def test_ai_package_keeps_components_separate() -> None:
    package = build_ai_package(
        [
            finding(),
            finding(component="Panel B - Middle", material="Tempered glass", thickness=""),
        ]
    )

    assert len(package["evidence_groups"]) == 2


def test_export_ai_json_writes_schema_and_evidence(tmp_path: Path) -> None:
    output = tmp_path / "ai-package.json"
    export_ai_json([finding()], output)

    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["format_version"] == "1.0"
    assert "required_summary_schema" in data
    assert data["evidence_groups"][0]["document"] == "Addendum.pdf"
