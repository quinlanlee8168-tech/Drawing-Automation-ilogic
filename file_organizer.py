"""Core logic for moving files that are not referenced by an Excel workbook."""

from __future__ import annotations

import os
import re
import shutil
import zipfile
from datetime import datetime, timezone
from xml.etree import ElementTree
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import Iterable, Iterator


DEFAULT_OLD_VERSION_NAMES = frozenset(
    {
        "old version",
        "old versions",
        "old_version",
        "old_versions",
        "old-version",
        "old-versions",
    }
)


@dataclass(frozen=True)
class MoveItem:
    """A proposed or completed file move."""

    source: Path
    destination: Path


@dataclass(frozen=True)
class ScanResult:
    """Results produced when a source folder is compared with a workbook."""

    referenced_files: frozenset[Path]
    unmatched_files: tuple[MoveItem, ...]
    skipped_old_version_files: tuple[Path, ...]


@dataclass(frozen=True)
class ArchiveItem:
    """An older file proposed for archival within a filename-identity group."""

    source: Path
    destination: Path
    modified_at: datetime
    group_key: str
    latest_modified_at: datetime


@dataclass(frozen=True)
class ArchiveResult:
    """Older duplicate versions, newest files retained, and protected files skipped."""

    archive_files: tuple[ArchiveItem, ...]
    latest_files: tuple[Path, ...]
    ungrouped_files: tuple[Path, ...]
    duplicate_group_count: int
    skipped_old_version_files: tuple[Path, ...]


def _normalized(path: Path) -> Path:
    """Return an absolute, case-normalized path without requiring it to exist."""

    return Path(os.path.normcase(os.path.abspath(os.path.normpath(path))))


def _is_old_version_part(part: str, old_version_names: frozenset[str]) -> bool:
    return part.strip().casefold() in old_version_names


def is_in_old_version_folder(
    relative_path: Path, old_version_names: frozenset[str] = DEFAULT_OLD_VERSION_NAMES
) -> bool:
    """Return whether any parent directory is a recognized old-version folder."""

    return any(_is_old_version_part(part, old_version_names) for part in relative_path.parts[:-1])


def _candidate_paths(value: object, source_folder: Path, workbook_path: Path) -> Iterator[Path]:
    """Yield reasonable local interpretations of a workbook cell value."""

    if not isinstance(value, str):
        return

    raw = value.strip().strip('"').strip("'")
    if not raw:
        return

    # Excel cells often contain Windows paths even if validation is run elsewhere.
    windows_path = PureWindowsPath(raw)
    local_text = raw.replace("\\", os.sep).replace("/", os.sep)
    local_path = Path(local_text)

    if windows_path.is_absolute():
        yield Path(str(windows_path))

        # A workbook may use a mapped drive (for example Z:) that is unavailable
        # or mapped differently on the computer running this program. If the
        # selected source folder occurs in the workbook path, rebase everything
        # below that folder onto the selected local source folder.
        source_name = source_folder.name.casefold()
        matching_indexes = [
            index
            for index, part in enumerate(windows_path.parts)
            if part.casefold() == source_name
        ]
        if matching_indexes:
            yield source_folder.joinpath(*windows_path.parts[matching_indexes[-1] + 1 :])
    elif local_path.is_absolute():
        yield local_path
    else:
        yield source_folder / local_path
        yield workbook_path.parent / local_path


def _cell_text(cell: ElementTree.Element, shared_strings: list[str], worksheet_name: str) -> str | None:
    """Return the displayed text stored in an Excel worksheet cell."""

    cell_type = cell.get("t")
    if cell_type == "inlineStr":
        inline = cell.find("{*}is")
        if inline is None:
            return None
        value = "".join(node.text or "" for node in inline.iter() if node.tag.endswith("}t"))
        return value or None

    value_node = cell.find("{*}v")
    if value_node is None or value_node.text is None:
        return None
    value = value_node.text
    if cell_type == "s":
        try:
            value = shared_strings[int(value)]
        except (ValueError, IndexError) as exc:
            raise ValueError(
                f"Workbook has an invalid shared-string reference in {worksheet_name}."
            ) from exc
    return value or None


def _column_name(cell_reference: str) -> str:
    """Extract an Excel column name such as ``AB`` from a cell reference."""

    match = re.match(r"[A-Za-z]+", cell_reference)
    return match.group(0).upper() if match else ""


def _normalized_header(value: str) -> str:
    """Normalize headings so Model Path, model_path, and ModelPath all match."""

    return "".join(character for character in value.casefold() if character.isalnum())


def _looks_like_path(value: str) -> bool:
    """Return whether an unlabelled cell appears to contain a file path."""

    cleaned = value.strip().strip('"').strip("'")
    if not cleaned:
        return False
    suffix = PureWindowsPath(cleaned).suffix
    return bool(suffix and ("\\" in cleaned or "/" in cleaned or suffix.casefold() in {
        ".ipt", ".iam", ".idw", ".dwg", ".pdf"
    }))


def _excel_path_values(workbook_path: Path) -> Iterator[str]:
    """Yield values from ModelPath/DrawingPath columns in every worksheet.

    Header matching ignores capitalization, spaces, underscores, and punctuation.
    For backwards compatibility, a worksheet without either heading falls back
    to cells that look like file paths.
    """

    try:
        archive = zipfile.ZipFile(workbook_path)
    except (OSError, zipfile.BadZipFile) as exc:
        raise ValueError(f"Not a valid .xlsx or .xlsm workbook: {workbook_path}") from exc

    with archive:
        names = set(archive.namelist())
        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in names:
            root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
            for item in root.findall("{*}si"):
                shared_strings.append(
                    "".join(node.text or "" for node in item.iter() if node.tag.endswith("}t"))
                )

        worksheet_names = sorted(
            name
            for name in names
            if name.startswith("xl/worksheets/sheet") and name.endswith(".xml")
        )
        for worksheet_name in worksheet_names:
            root = ElementTree.fromstring(archive.read(worksheet_name))
            rows: list[dict[str, str]] = []
            for row in root.findall(".//{*}row"):
                values: dict[str, str] = {}
                for cell in row.findall("{*}c"):
                    value = _cell_text(cell, shared_strings, worksheet_name)
                    column = _column_name(cell.get("r", ""))
                    if value is not None and column:
                        values[column] = value
                rows.append(values)

            path_columns: set[str] = set()
            found_path_header = False
            fallback_values: list[str] = []
            for values in rows:
                header_columns = {
                    column
                    for column, value in values.items()
                    if _normalized_header(value) in {"modelpath", "drawingpath"}
                }
                if header_columns:
                    found_path_header = True
                    path_columns.update(header_columns)
                    continue

                if path_columns:
                    for column in path_columns:
                        value = values.get(column)
                        if value:
                            yield value
                elif not found_path_header:
                    fallback_values.extend(
                        value for value in values.values() if _looks_like_path(value)
                    )

            if not found_path_header:
                yield from fallback_values


def read_referenced_files(workbook_path: Path, source_folder: Path) -> frozenset[Path]:
    """Read model/drawing path columns and return their possible normalized paths."""

    workbook_path = workbook_path.expanduser().resolve()
    source_folder = source_folder.expanduser().resolve()
    referenced: set[Path] = set()
    for value in _excel_path_values(workbook_path):
        referenced.update(
            _normalized(candidate)
            for candidate in _candidate_paths(value, source_folder, workbook_path)
        )
    return frozenset(referenced)


def _unique_destination(destination: Path) -> Path:
    """Avoid overwriting an existing destination file."""

    if not destination.exists():
        return destination
    counter = 1
    while True:
        candidate = destination.with_name(f"{destination.stem} ({counter}){destination.suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


def scan_unmatched_files(
    source_folder: Path,
    workbook_path: Path,
    destination_folder: Path,
    old_version_names: frozenset[str] = DEFAULT_OLD_VERSION_NAMES,
) -> ScanResult:
    """Build a safe move plan for every file not referenced by the workbook."""

    source_folder = source_folder.expanduser().resolve()
    workbook_path = workbook_path.expanduser().resolve()
    destination_folder = destination_folder.expanduser().resolve()

    if not source_folder.is_dir():
        raise ValueError(f"Source folder does not exist: {source_folder}")
    if not workbook_path.is_file():
        raise ValueError(f"Excel workbook does not exist: {workbook_path}")
    if source_folder == destination_folder:
        raise ValueError("The destination folder must be different from the source folder.")
    if source_folder in destination_folder.parents:
        destination_is_inside_source = True
    else:
        destination_is_inside_source = False

    referenced = read_referenced_files(workbook_path, source_folder)
    moves: list[MoveItem] = []
    skipped: list[Path] = []

    for root, directory_names, file_names in os.walk(source_folder):
        root_path = Path(root)

        # Never scan the destination when it is inside the selected source tree.
        directory_names[:] = [
            name
            for name in directory_names
            if not (
                destination_is_inside_source
                and _normalized(root_path / name) == _normalized(destination_folder)
            )
        ]

        for file_name in file_names:
            source = root_path / file_name
            relative = source.relative_to(source_folder)
            if _normalized(source) == _normalized(workbook_path):
                continue
            if is_in_old_version_folder(relative, old_version_names):
                skipped.append(source)
                continue
            if _normalized(source) in referenced:
                continue
            destination = _unique_destination(destination_folder / relative)
            moves.append(MoveItem(source=source, destination=destination))

    return ScanResult(
        referenced_files=referenced,
        unmatched_files=tuple(moves),
        skipped_old_version_files=tuple(skipped),
    )


# A letter attached to the final numeric segment is part of the permanent FSI code.
# It must never be interpreted as a revision marker or discarded during grouping.
FSI_CODE_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])FSI-\d{3}-\d{2}-\d{2,3}[A-Za-z]?(?![A-Za-z0-9])",
    re.IGNORECASE,
)
FALLBACK_GROUP_LENGTH = 15


def archive_identity_key(path: Path) -> str:
    """Identify a file by its complete permanent FSI code or a 15-character fallback."""

    match = FSI_CODE_PATTERN.search(path.stem)
    if match:
        return match.group(0).upper()
    return path.stem[:FALLBACK_GROUP_LENGTH].casefold()


def archive_group_key(path: Path) -> str:
    """Combine filename identity and file type so extensions compare independently."""

    file_type = path.suffix.casefold() or "(no extension)"
    return f"{archive_identity_key(path)} | {file_type}"


def scan_files_for_archive(
    source_folder: Path,
    archive_folder: Path,
    old_version_names: frozenset[str] = DEFAULT_OLD_VERSION_NAMES,
) -> ArchiveResult:
    """Find older versions by grouping names and comparing filesystem modified time.

    Every regular file type is considered independently. Files are grouped by an
    FSI code when present, otherwise by the first 15 characters of the filename
    stem, and then separated by extension. Within a same-identity, same-extension
    group, only files strictly older than the newest modification time are proposed
    for archive. Newest-time ties stay.
    """

    source_folder = source_folder.expanduser().resolve()
    archive_folder = archive_folder.expanduser().resolve()
    if not source_folder.is_dir():
        raise ValueError(f"Source folder does not exist: {source_folder}")
    if source_folder == archive_folder:
        raise ValueError("The archive folder must be different from the source folder.")

    archive_is_inside_source = source_folder in archive_folder.parents
    groups: dict[str, list[tuple[Path, datetime]]] = {}
    skipped: list[Path] = []
    for root, directory_names, file_names in os.walk(source_folder):
        root_path = Path(root)
        directory_names[:] = [
            name
            for name in directory_names
            if not (
                archive_is_inside_source
                and _normalized(root_path / name) == _normalized(archive_folder)
            )
        ]

        for file_name in file_names:
            source = root_path / file_name
            relative = source.relative_to(source_folder)
            if is_in_old_version_folder(relative, old_version_names):
                skipped.append(source)
                continue
            if source.is_symlink() or not source.is_file():
                continue
            try:
                modified_at = datetime.fromtimestamp(source.stat().st_mtime, tz=timezone.utc)
            except OSError:
                continue
            groups.setdefault(archive_group_key(source), []).append((source, modified_at))

    archive_items: list[ArchiveItem] = []
    latest_files: list[Path] = []
    ungrouped_files: list[Path] = []
    duplicate_group_count = 0
    for group_key, files in groups.items():
        if len(files) < 2:
            ungrouped_files.extend(source for source, _modified_at in files)
            continue
        duplicate_group_count += 1
        latest_modified_at = max(modified_at for _source, modified_at in files)
        for source, modified_at in files:
            if modified_at == latest_modified_at:
                latest_files.append(source)
                continue
            relative = source.relative_to(source_folder)
            archive_items.append(
                ArchiveItem(
                    source=source,
                    destination=_unique_destination(archive_folder / relative),
                    modified_at=modified_at,
                    group_key=group_key,
                    latest_modified_at=latest_modified_at,
                )
            )

    archive_items.sort(
        key=lambda item: (item.group_key.casefold(), item.modified_at, str(item.source).casefold())
    )
    latest_files.sort(key=lambda path: str(path).casefold())
    ungrouped_files.sort(key=lambda path: str(path).casefold())
    return ArchiveResult(
        archive_files=tuple(archive_items),
        latest_files=tuple(latest_files),
        ungrouped_files=tuple(ungrouped_files),
        duplicate_group_count=duplicate_group_count,
        skipped_old_version_files=tuple(skipped),
    )


def execute_archive_moves(items: Iterable[ArchiveItem]) -> tuple[MoveItem, ...]:
    """Move archive candidates using the same overwrite-safe move behavior."""

    return execute_moves(MoveItem(item.source, item.destination) for item in items)


def file_type_for_path(path: Path) -> str:
    """Return a case-insensitive extension key, or an empty string when absent."""

    return path.suffix.casefold()


def summarize_file_types(items: Iterable[MoveItem]) -> tuple[tuple[str, int], ...]:
    """Return every discovered extension and its unmatched-file count."""

    counts: dict[str, int] = {}
    for item in items:
        file_type = file_type_for_path(item.source)
        counts[file_type] = counts.get(file_type, 0) + 1
    return tuple(sorted(counts.items(), key=lambda entry: (entry[0] == "", entry[0])))


def select_move_items_by_type(
    items: Iterable[MoveItem], selected_types: Iterable[str]
) -> tuple[MoveItem, ...]:
    """Return all move items whose extensions are among the selected types."""

    normalized_types = frozenset(file_type.casefold() for file_type in selected_types)
    return tuple(
        item for item in items if file_type_for_path(item.source) in normalized_types
    )


def remove_empty_folders(
    source_folder: Path,
    excluded_folders: Iterable[Path] = (),
    old_version_names: frozenset[str] = DEFAULT_OLD_VERSION_NAMES,
) -> tuple[Path, ...]:
    """Remove empty source subfolders after moves, deepest folders first.

    The selected source root, excluded folders (such as a destination inside the
    source), symbolic links, and recognized old-version folder trees are never
    removed.
    """

    source_folder = source_folder.expanduser().resolve()
    if not source_folder.is_dir():
        raise ValueError(f"Source folder does not exist: {source_folder}")

    excluded = tuple(_normalized(folder.expanduser().resolve()) for folder in excluded_folders)
    removed: list[Path] = []
    for root, _directory_names, _file_names in os.walk(source_folder, topdown=False):
        folder = Path(root)
        if folder == source_folder or folder.is_symlink():
            continue

        normalized_folder = _normalized(folder)
        if any(
            normalized_folder == excluded_folder or excluded_folder in normalized_folder.parents
            for excluded_folder in excluded
        ):
            continue

        relative = folder.relative_to(source_folder)
        if any(_is_old_version_part(part, old_version_names) for part in relative.parts):
            continue

        try:
            folder.rmdir()
        except OSError:
            # The folder is not empty, became non-empty, or cannot be removed.
            continue
        removed.append(folder)

    return tuple(removed)


def execute_moves(items: Iterable[MoveItem]) -> tuple[MoveItem, ...]:
    """Execute a move plan, preserving relative folders and never overwriting files."""

    completed: list[MoveItem] = []
    for item in items:
        if not item.source.is_file():
            raise FileNotFoundError(f"Source file no longer exists: {item.source}")
        destination = _unique_destination(item.destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(item.source), str(destination))
        completed.append(MoveItem(item.source, destination))
    return tuple(completed)
