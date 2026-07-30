import json
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Any

from document_scanner.ai_exporter import AI_TASK, build_ai_package
from document_scanner.models import Finding

DEFAULT_MODEL = "gpt-5.5"
RESPONSES_URL = "https://api.openai.com/v1/responses"
NULLABLE_STRING = {"anyOf": [{"type": "string"}, {"type": "null"}]}

SUMMARY_JSON_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["rows"],
    "properties": {
        "rows": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "sign_type",
                    "component",
                    "material",
                    "grade_alloy_temper",
                    "material_thickness",
                    "finish_system",
                    "color",
                    "coating_film_thickness",
                    "surface_application",
                    "anti_graffiti_requirement",
                    "manufacturer",
                    "product",
                    "standards",
                    "document",
                    "page",
                    "evidence_ids",
                    "conflicts",
                    "missing_fields",
                    "confidence",
                ],
                "properties": {
                    "sign_type": NULLABLE_STRING,
                    "component": {"type": "string"},
                    "material": NULLABLE_STRING,
                    "grade_alloy_temper": NULLABLE_STRING,
                    "material_thickness": NULLABLE_STRING,
                    "finish_system": NULLABLE_STRING,
                    "color": NULLABLE_STRING,
                    "coating_film_thickness": NULLABLE_STRING,
                    "surface_application": NULLABLE_STRING,
                    "anti_graffiti_requirement": NULLABLE_STRING,
                    "manufacturer": NULLABLE_STRING,
                    "product": NULLABLE_STRING,
                    "standards": {"type": "array", "items": {"type": "string"}},
                    "document": {"type": "string"},
                    "page": {"type": "integer", "minimum": 1},
                    "evidence_ids": {"type": "array", "items": {"type": "string"}},
                    "conflicts": {"type": "array", "items": {"type": "string"}},
                    "missing_fields": {"type": "array", "items": {"type": "string"}},
                    "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                },
            },
        }
    },
}


@dataclass(slots=True)
class SummaryRow:
    component: str
    document: str
    page: int
    sign_type: str | None = None
    material: str | None = None
    grade_alloy_temper: str | None = None
    material_thickness: str | None = None
    finish_system: str | None = None
    color: str | None = None
    coating_film_thickness: str | None = None
    surface_application: str | None = None
    anti_graffiti_requirement: str | None = None
    manufacturer: str | None = None
    product: str | None = None
    standards: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    missing_fields: list[str] = field(default_factory=list)
    confidence: str = "low"


@dataclass(slots=True)
class SummaryResult:
    rows: list[SummaryRow]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SummaryResult":
        if set(data) != {"rows"} or not isinstance(data["rows"], list):
            raise ValueError("The summary must contain exactly one top-level `rows` list.")

        required = set(SUMMARY_JSON_SCHEMA["properties"]["rows"]["items"]["required"])
        parsed_rows: list[SummaryRow] = []
        for index, item in enumerate(data["rows"], start=1):
            if not isinstance(item, dict):
                raise ValueError(f"Summary row {index} must be a JSON object.")
            missing = sorted(required - set(item))
            extra = sorted(set(item) - required)
            if missing:
                raise ValueError(f"Summary row {index} is missing: {', '.join(missing)}")
            if extra:
                raise ValueError(f"Summary row {index} has unexpected fields: {', '.join(extra)}")
            parsed_rows.append(SummaryRow(**item))
        return cls(parsed_rows)

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


Transport = Callable[[urllib.request.Request, float], dict[str, Any]]


def _default_transport(request: urllib.request.Request, timeout: float) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        details = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI API request failed ({error.code}): {details}") from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"Could not connect to the OpenAI API: {error.reason}") from error


def _output_text(response: dict[str, Any]) -> str:
    for output in response.get("output", []):
        if output.get("type") != "message":
            continue
        for content in output.get("content", []):
            if content.get("type") == "output_text" and content.get("text"):
                return str(content["text"])
    raise ValueError("OpenAI did not return structured summary text.")


def validate_summary(summary: SummaryResult, findings: list[Finding]) -> None:
    available_ids = {f"E{index:05d}" for index in range(1, len(findings) + 1)}
    pages_by_id = {
        f"E{index:05d}": (finding.document, finding.page)
        for index, finding in enumerate(findings, start=1)
    }
    cited = {evidence_id for row in summary.rows for evidence_id in row.evidence_ids}
    unknown = sorted(cited - available_ids)
    if unknown:
        raise ValueError(f"AI summary cited unknown evidence IDs: {', '.join(unknown)}")

    for row in summary.rows:
        wrong_page = [
            evidence_id
            for evidence_id in row.evidence_ids
            if pages_by_id.get(evidence_id) != (row.document, row.page)
        ]
        if wrong_page:
            raise ValueError(
                f"AI summary combined evidence from another page in {row.component}: "
                f"{', '.join(wrong_page)}"
            )


def summarize_findings(
    findings: list[Finding],
    api_key: str,
    model: str = DEFAULT_MODEL,
    transport: Transport = _default_transport,
) -> SummaryResult:
    if not api_key.strip():
        raise ValueError("An OpenAI API key is required.")
    if not findings:
        raise ValueError("There are no findings to summarize.")

    package = build_ai_package(findings)
    payload = {
        "model": model.strip() or DEFAULT_MODEL,
        "reasoning": {"effort": "low"},
        "input": [
            {
                "role": "system",
                "content": (
                    f"{AI_TASK}\n"
                    "Create a simple schedule. Use one row per component, material, distinct "
                    "finish, and source page. Never combine page numbers in one row. Do not "
                    "include Drawing Number, Option, or Material Role fields. Combine the color "
                    "name and every stated Pantone/RAL/HEX/CMYK/manufacturer code into one Color "
                    "cell. Candidate values may be wrong; source_text is the authority. Use null "
                    "for unstated values."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(package["evidence_groups"], ensure_ascii=False),
            },
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "wayfinding_simple_summary",
                "strict": True,
                "schema": SUMMARY_JSON_SCHEMA,
            }
        },
    }
    request = urllib.request.Request(
        RESPONSES_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key.strip()}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    response = transport(request, 180.0)
    summary = SummaryResult.from_dict(json.loads(_output_text(response)))
    validate_summary(summary, findings)
    return summary
