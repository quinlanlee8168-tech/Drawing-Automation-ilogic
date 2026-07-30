import json
from pathlib import Path

import pytest

from document_scanner.config import (
    KeywordConfigError,
    bundled_config_path,
    default_config_path,
    load_keyword_groups,
)


def test_load_keyword_groups(tmp_path: Path) -> None:
    path = tmp_path / "keywords.json"
    path.write_text(json.dumps({"materials": [" aluminum ", ""]}), encoding="utf-8")

    assert load_keyword_groups(path) == {"materials": ["aluminum"]}


def test_rejects_non_object_config(tmp_path: Path) -> None:
    path = tmp_path / "keywords.json"
    path.write_text("[]", encoding="utf-8")

    with pytest.raises(KeywordConfigError, match="JSON object"):
        load_keyword_groups(path)


def test_missing_explicit_config_has_helpful_message(tmp_path: Path) -> None:
    with pytest.raises(KeywordConfigError, match="keyword list is missing"):
        load_keyword_groups(tmp_path / "missing.json")


def test_bundled_defaults_are_available() -> None:
    path = bundled_config_path()

    assert path.is_file()
    assert load_keyword_groups(path)["materials"]


def test_default_config_is_always_available(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "document_scanner.config.project_config_path", lambda: tmp_path / "missing.json"
    )

    assert default_config_path() == bundled_config_path()
    assert load_keyword_groups()["anti_graffiti"]
