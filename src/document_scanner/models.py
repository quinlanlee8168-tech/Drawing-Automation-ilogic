from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class DocumentPage:
    document_path: Path
    page_number: int
    text: str
    text_blocks: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Finding:
    document: str
    page: int
    category: str
    component: str
    material: str
    finish: str
    thickness: str
    anti_graffiti: str
    matched_term: str
    source_text: str
    review_status: str = "Unreviewed"

    def as_row(self) -> dict[str, str | int]:
        return asdict(self)
