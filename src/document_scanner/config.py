import json
from pathlib import Path


class KeywordConfigError(ValueError):
    """Raised when the keyword configuration exists but cannot be used."""


def project_config_path() -> Path:
    """Return the optional user-editable configuration in a source checkout."""
    return Path(__file__).resolve().parents[2] / "config" / "keywords.json"


def bundled_config_path() -> Path:
    """Return the defaults shipped inside the application package."""
    return Path(__file__).resolve().with_name("keywords.json")


def default_config_path() -> Path:
    """Prefer user-editable project keywords, then use bundled defaults."""
    external_path = project_config_path()
    return external_path if external_path.is_file() else bundled_config_path()


def load_keyword_groups(path: Path | None = None) -> dict[str, list[str]]:
    config_path = path or default_config_path()
    try:
        with config_path.open(encoding="utf-8") as file:
            data = json.load(file)
    except FileNotFoundError as error:
        raise KeywordConfigError(
            "The keyword list is missing. Re-download and extract the complete application folder, "
            "then run setup_windows.bat again."
        ) from error
    except json.JSONDecodeError as error:
        raise KeywordConfigError(
            f"The keyword list is not valid JSON: {config_path} (line {error.lineno})."
        ) from error

    if not isinstance(data, dict):
        raise KeywordConfigError("Keyword configuration must contain a JSON object.")

    groups: dict[str, list[str]] = {}
    for category, terms in data.items():
        if not isinstance(category, str) or not isinstance(terms, list):
            raise KeywordConfigError("Each keyword category must map to a list of terms.")
        groups[category] = [str(term).strip() for term in terms if str(term).strip()]

    if not groups:
        raise KeywordConfigError("The keyword configuration does not contain any categories.")
    return groups
