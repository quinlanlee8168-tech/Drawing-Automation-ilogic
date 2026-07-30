import sys
from pathlib import Path

import run_app


def test_launcher_adds_absolute_source_directory(monkeypatch) -> None:
    source_directory = Path(run_app.__file__).resolve().parent / "src"
    monkeypatch.setattr(
        sys, "path", [entry for entry in sys.path if entry != str(source_directory)]
    )

    result = run_app.add_source_directory()

    assert result == source_directory
    assert sys.path[0] == str(source_directory)
    assert (result / "document_scanner" / "app.py").is_file()
