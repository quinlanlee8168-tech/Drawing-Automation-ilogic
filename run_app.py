"""Source-tree launcher for the Wayfinding Document Scanner."""

import sys
from pathlib import Path


def add_source_directory() -> Path:
    """Make the local ``src`` package importable from any working directory."""
    source_directory = Path(__file__).resolve().parent / "src"
    source_text = str(source_directory)
    if source_text not in sys.path:
        sys.path.insert(0, source_text)
    return source_directory


def main() -> None:
    source_directory = add_source_directory()
    package_directory = source_directory / "document_scanner"
    if not package_directory.is_dir():
        raise SystemExit(
            "The application files are incomplete. Expected to find: "
            f"{package_directory}\n"
            "Download and extract the entire repository, not only the .bat files."
        )

    from document_scanner.app import main as application_main

    application_main()


if __name__ == "__main__":
    main()
