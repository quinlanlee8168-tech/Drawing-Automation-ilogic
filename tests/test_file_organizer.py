from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
from xml.sax.saxutils import escape
import zipfile

from file_organizer import (
    archive_group_key,
    archive_identity_key,
    execute_archive_moves,
    execute_moves,
    remove_empty_folders,
    scan_files_for_archive,
    scan_unmatched_files,
    select_move_items_by_type,
    summarize_file_types,
)


def make_workbook(path: Path, values: list[str]) -> None:
    rows = "".join(
        f'<row r="{row}"><c r="A{row}" t="inlineStr"><is><t>{escape(value)}</t></is></c></row>'
        for row, value in enumerate(values, start=1)
    )
    worksheet = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"<sheetData>{rows}</sheetData></worksheet>"
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="xml" ContentType="application/xml"/>'
        "</Types>"
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("xl/worksheets/sheet1.xml", worksheet)



def make_shared_string_path_workbook(
    path: Path, model_paths: list[str], drawing_paths: list[str]
) -> None:
    """Create an XLSX shaped like the user's BOM export."""

    headers = [
        "Order",
        "RAW PART NUMBER",
        "PART_NUMBER_FILTER",
        "ModelPath",
        "DrawingPath",
        "ReportedPdf",
        "Quantity",
        "Finish",
        "Material",
        "Status",
    ]
    strings = headers + model_paths + drawing_paths + ["MissingDrawing"]
    shared_items = "".join(f"<si><t>{escape(value)}</t></si>" for value in strings)
    shared_strings = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        f'count="{len(strings)}" uniqueCount="{len(strings)}">{shared_items}</sst>'
    )

    header_cells = "".join(
        f'<c r="{column}1" t="s"><v>{index}</v></c>'
        for index, column in enumerate("ABCDEFGHIJ")
    )
    data_rows = []
    for offset, model_path in enumerate(model_paths, start=0):
        row = offset + 2
        model_index = len(headers) + offset
        cells = [
            f'<c r="A{row}"><v>{offset + 1}</v></c>',
            f'<c r="B{row}" t="inlineStr"><is><t>FSI-{offset + 1:03}</t></is></c>',
            f'<c r="D{row}" t="s"><v>{model_index}</v></c>',
        ]
        if offset < len(drawing_paths):
            drawing_index = len(headers) + len(model_paths) + offset
            cells.append(f'<c r="E{row}" t="s"><v>{drawing_index}</v></c>')
        status_index = len(strings) - 1
        cells.append(f'<c r="J{row}" t="s"><v>{status_index}</v></c>')
        data_rows.append(f'<row r="{row}">{"".join(cells)}</row>')

    worksheet = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData><row r="1">{header_cells}</row>{"".join(data_rows)}</sheetData>'
        '</worksheet>'
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '</Types>'
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("xl/sharedStrings.xml", shared_strings)
        archive.writestr("xl/worksheets/sheet1.xml", worksheet)


def test_scan_keeps_referenced_and_skips_old_versions(tmp_path: Path) -> None:
    source = tmp_path / "drawings"
    destination = tmp_path / "unmatched"
    source.mkdir()
    (source / "keep.idw").write_text("current")
    (source / "move.idw").write_text("unlisted")
    old = source / "Old Versions"
    old.mkdir()
    (old / "legacy.idw").write_text("legacy")
    workbook = tmp_path / "paths.xlsx"
    make_workbook(workbook, [str(source / "keep.idw")])

    result = scan_unmatched_files(source, workbook, destination)

    assert [item.source.name for item in result.unmatched_files] == ["move.idw"]
    assert result.unmatched_files[0].destination == destination / "move.idw"
    assert result.skipped_old_version_files == (old / "legacy.idw",)


def test_move_preserves_subfolders_and_does_not_overwrite(tmp_path: Path) -> None:
    source = tmp_path / "drawings"
    subfolder = source / "project"
    subfolder.mkdir(parents=True)
    source_file = subfolder / "part.dwg"
    source_file.write_text("new")
    destination = tmp_path / "unmatched"
    existing = destination / "project" / "part.dwg"
    existing.parent.mkdir(parents=True)
    existing.write_text("existing")
    workbook = tmp_path / "paths.xlsx"
    make_workbook(workbook, [])

    result = scan_unmatched_files(source, workbook, destination)
    completed = execute_moves(result.unmatched_files)

    assert existing.read_text() == "existing"
    assert completed[0].destination.name == "part (1).dwg"
    assert completed[0].destination.read_text() == "new"
    assert not source_file.exists()


def test_destination_inside_source_is_not_scanned(tmp_path: Path) -> None:
    source = tmp_path / "drawings"
    destination = source / "Unmatched"
    destination.mkdir(parents=True)
    (source / "move.dwg").write_text("move")
    (destination / "already-moved.dwg").write_text("ignore")
    workbook = tmp_path / "paths.xlsx"
    make_workbook(workbook, [])

    result = scan_unmatched_files(source, workbook, destination)

    assert [item.source.name for item in result.unmatched_files] == ["move.dwg"]


def test_workbook_inside_source_is_never_moved(tmp_path: Path) -> None:
    source = tmp_path / "drawings"
    source.mkdir()
    workbook = source / "paths.xlsx"
    make_workbook(workbook, [])

    result = scan_unmatched_files(source, workbook, tmp_path / "unmatched")

    assert result.unmatched_files == ()


def test_scan_collects_every_unmatched_file_type(tmp_path: Path) -> None:
    source = tmp_path / "drawings"
    source.mkdir()
    for file_name in (
        "part.ipt",
        "assembly.IAM",
        "drawing.idw",
        "layout.dwg",
        "print.PDF",
        "solid.SLDPRT",
        "notes.txt",
        "extensionless",
    ):
        (source / file_name).write_text("unlisted")
    old = source / "Old Version"
    old.mkdir()
    (old / "legacy.IAM").write_text("legacy")
    (old / "ignore.txt").write_text("legacy notes")
    workbook = tmp_path / "paths.xlsx"
    make_workbook(workbook, [])

    result = scan_unmatched_files(source, workbook, tmp_path / "unmatched")

    assert {item.source.name for item in result.unmatched_files} == {
        "part.ipt",
        "assembly.IAM",
        "drawing.idw",
        "layout.dwg",
        "print.PDF",
        "solid.SLDPRT",
        "notes.txt",
        "extensionless",
    }
    assert set(result.skipped_old_version_files) == {
        old / "legacy.IAM",
        old / "ignore.txt",
    }


def test_summarizes_all_discovered_file_types_case_insensitively(tmp_path: Path) -> None:
    source = tmp_path / "drawings"
    source.mkdir()
    for file_name in ("one.PDF", "two.pdf", "part.SLDPRT", "notes.txt", "README"):
        (source / file_name).write_text(file_name)
    workbook = tmp_path / "paths.xlsx"
    make_workbook(workbook, [])

    result = scan_unmatched_files(source, workbook, tmp_path / "unmatched")

    assert summarize_file_types(result.unmatched_files) == (
        (".pdf", 2),
        (".sldprt", 1),
        (".txt", 1),
        ("", 1),
    )


def test_selects_and_moves_all_files_for_multiple_selected_types(tmp_path: Path) -> None:
    source = tmp_path / "drawings"
    source.mkdir()
    for file_name in ("one.pdf", "two.PDF", "part.sldprt", "keep.ipt"):
        (source / file_name).write_text(file_name)
    workbook = tmp_path / "paths.xlsx"
    make_workbook(workbook, [])

    result = scan_unmatched_files(source, workbook, tmp_path / "unmatched")
    selected = select_move_items_by_type(result.unmatched_files, {".PDF", ".sldprt"})
    completed = execute_moves(selected)

    assert {item.source.name for item in completed} == {"one.pdf", "two.PDF", "part.sldprt"}
    assert (source / "keep.ipt").is_file()
    assert not (source / "one.pdf").exists()
    assert not (source / "two.PDF").exists()
    assert not (source / "part.sldprt").exists()


def test_removes_nested_empty_source_folders_after_selected_moves(tmp_path: Path) -> None:
    source = tmp_path / "drawings"
    nested = source / "project" / "parts"
    nested.mkdir(parents=True)
    moved_file = nested / "unused.sldprt"
    moved_file.write_text("unused")
    workbook = tmp_path / "paths.xlsx"
    make_workbook(workbook, [])

    result = scan_unmatched_files(source, workbook, tmp_path / "unmatched")
    execute_moves(result.unmatched_files)
    removed = remove_empty_folders(source)

    assert removed == (nested, source / "project")
    assert source.is_dir()
    assert not nested.exists()
    assert not (source / "project").exists()


def test_empty_folder_cleanup_preserves_protected_and_excluded_folders(tmp_path: Path) -> None:
    source = tmp_path / "drawings"
    empty = source / "remove-me"
    old_versions = source / "Old Versions" / "nested-empty"
    destination = source / "UNUSED PARTS"
    empty.mkdir(parents=True)
    old_versions.mkdir(parents=True)
    destination.mkdir(parents=True)
    nonempty = source / "keep-me"
    nonempty.mkdir()
    (nonempty / "listed.ipt").write_text("keep")

    removed = remove_empty_folders(source, excluded_folders=(destination,))

    assert removed == (empty,)
    assert source.is_dir()
    assert old_versions.is_dir()
    assert destination.is_dir()
    assert nonempty.is_dir()


def test_bom_export_reads_model_and_drawing_paths_from_mapped_drive(tmp_path: Path) -> None:
    source = tmp_path / "PARTS AND ASSEMBLIES"
    source.mkdir()
    model = source / "FSI-105-01-004_MOD3.iam"
    drawing = source / "FSI-105-01-004_MOD3.idw"
    unlisted = source / "REMOVE-ME.ipt"
    model.write_text("assembly")
    drawing.write_text("drawing")
    unlisted.write_text("unlisted")
    workbook = tmp_path / "bom.xlsx"
    make_shared_string_path_workbook(
        workbook,
        [
            r"Z:\Design\KING COUNTY METRO\KCM TECH PYLON PACKNGO - ALEX EDIT 90"
            r"\PARTS AND ASSEMBLIES\FSI-105-01-004_MOD3.iam"
        ],
        [
            r"Z:\Design\KING COUNTY METRO\KCM TECH PYLON PACKNGO - ALEX EDIT 90"
            r"\PARTS AND ASSEMBLIES\FSI-105-01-004_MOD3.idw"
        ],
    )

    result = scan_unmatched_files(source, workbook, tmp_path / "unmatched")

    assert [item.source for item in result.unmatched_files] == [unlisted]


def make_multi_sheet_workbook(path: Path, sheets: list[list[dict[str, str]]]) -> None:
    """Create an inline-string XLSX with arbitrary rows, columns, and worksheets."""

    content_types = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '</Types>'
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", content_types)
        for sheet_number, rows in enumerate(sheets, start=1):
            xml_rows = []
            for row_number, values in enumerate(rows, start=1):
                cells = "".join(
                    f'<c r="{column}{row_number}" t="inlineStr"><is><t>{escape(value)}</t></is></c>'
                    for column, value in values.items()
                )
                xml_rows.append(f'<row r="{row_number}">{cells}</row>')
            worksheet = (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                f'<sheetData>{"".join(xml_rows)}</sheetData></worksheet>'
            )
            archive.writestr(f"xl/worksheets/sheet{sheet_number}.xml", worksheet)


def test_finds_flexible_path_headers_on_any_sheet_and_ignores_other_columns(
    tmp_path: Path,
) -> None:
    source = tmp_path / "models"
    source.mkdir()
    model = source / "assembly.iam"
    drawing = source / "assembly.idw"
    unrelated_path = source / "old-backup.ipt"
    model.write_text("assembly")
    drawing.write_text("drawing")
    unrelated_path.write_text("not in a model/drawing path column")
    workbook = tmp_path / "flexible-layout.xlsx"
    make_multi_sheet_workbook(
        workbook,
        [
            [
                {"A": "Report title"},
                {"A": "Generated today"},
                {"B": "MODEL PATH", "F": "Notes"},
                {"B": str(model), "F": "keep this model"},
            ],
            [
                {"A": "Metadata"},
                {"C": "drawing_path", "H": "Backup Path"},
                {"C": str(drawing), "H": str(unrelated_path)},
            ],
        ],
    )

    result = scan_unmatched_files(source, workbook, tmp_path / "unmatched")

    assert [item.source for item in result.unmatched_files] == [unrelated_path]


def test_accepts_workbook_with_only_one_path_column(tmp_path: Path) -> None:
    source = tmp_path / "drawings"
    source.mkdir()
    referenced = source / "listed.pdf"
    unlisted = source / "unlisted.pdf"
    referenced.write_text("listed")
    unlisted.write_text("unlisted")
    workbook = tmp_path / "drawing-path-only.xlsx"
    make_multi_sheet_workbook(
        workbook,
        [[{"D": "Drawing Path"}, {"D": str(referenced)}]],
    )

    result = scan_unmatched_files(source, workbook, tmp_path / "unmatched")

    assert [item.source for item in result.unmatched_files] == [unlisted]


def set_modified_time(path: Path, modified_at: datetime) -> None:
    timestamp = modified_at.timestamp()
    path.touch()
    os.utime(path, (timestamp, timestamp))


def test_archive_compares_same_fsi_code_independently_by_file_type(tmp_path: Path) -> None:
    now = datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc)
    source = tmp_path / "project"
    source.mkdir()
    rev_d_pdf = source / "FSI-020-00-01 Fabrication Drawings REV D.pdf"
    rev_e_pdf = source / "FSI-020-00-01 Fabrication Drawings REV E.pdf"
    latest_dwg = source / "FSI-020-00-01 Current Drawing.dwg"
    set_modified_time(rev_d_pdf, now - timedelta(days=120))
    set_modified_time(rev_e_pdf, now - timedelta(days=60))
    set_modified_time(latest_dwg, now - timedelta(days=5))

    result = scan_files_for_archive(source, tmp_path / "archive")

    assert [item.source for item in result.archive_files] == [rev_d_pdf]
    assert result.archive_files[0].group_key == "FSI-020-00-01 | .pdf"
    assert result.archive_files[0].latest_modified_at == now - timedelta(days=60)
    assert result.latest_files == (rev_e_pdf,)
    assert result.ungrouped_files == (latest_dwg,)
    assert result.duplicate_group_count == 1


def test_archive_treats_attached_letter_as_permanent_fsi_suffix(tmp_path: Path) -> None:
    now = datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc)
    source = tmp_path / "project"
    source.mkdir()
    old_d = source / "FSI-020-00-001D Previous Export.pdf"
    newest_d = source / "FSI-020-00-001D Current Export.pdf"
    separate_e = source / "FSI-020-00-001E Current Export.pdf"
    set_modified_time(old_d, now - timedelta(days=30))
    set_modified_time(newest_d, now - timedelta(days=1))
    set_modified_time(separate_e, now)

    result = scan_files_for_archive(source, tmp_path / "archive")

    assert archive_identity_key(old_d) == "FSI-020-00-001D"
    assert archive_identity_key(separate_e) == "FSI-020-00-001E"
    assert archive_group_key(old_d) == "FSI-020-00-001D | .pdf"
    assert [item.source for item in result.archive_files] == [old_d]
    assert result.latest_files == (newest_d,)
    assert result.ungrouped_files == (separate_e,)
    assert result.duplicate_group_count == 1


def test_archive_groups_each_fsi_file_type_separately(tmp_path: Path) -> None:
    now = datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc)
    source = tmp_path / "project"
    source.mkdir()
    old_pdf = source / "FSI-105-01-004 old.pdf"
    newest_pdf = source / "FSI-105-01-004 latest.pdf"
    old_dwg = source / "FSI-105-01-004 old.dwg"
    newest_dwg = source / "FSI-105-01-004 latest.dwg"
    for path, days in ((old_pdf, 20), (newest_pdf, 2), (old_dwg, 30), (newest_dwg, 1)):
        set_modified_time(path, now - timedelta(days=days))

    result = scan_files_for_archive(source, tmp_path / "archive")

    assert {item.source for item in result.archive_files} == {old_pdf, old_dwg}
    assert {item.group_key for item in result.archive_files} == {
        "FSI-105-01-004 | .pdf",
        "FSI-105-01-004 | .dwg",
    }
    assert set(result.latest_files) == {newest_pdf, newest_dwg}
    assert result.duplicate_group_count == 2


def test_archive_fallback_is_also_independent_by_file_type(tmp_path: Path) -> None:
    now = datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc)
    source = tmp_path / "project"
    source.mkdir()
    old_pdf = source / "Top Cabinet Dra REV A.pdf"
    newest_pdf = source / "Top Cabinet Dra Final.pdf"
    separate_sldprt = source / "Top Cabinet Dra Final.sldprt"
    set_modified_time(old_pdf, now - timedelta(days=30))
    set_modified_time(newest_pdf, now - timedelta(days=1))
    set_modified_time(separate_sldprt, now)

    result = scan_files_for_archive(source, tmp_path / "archive")

    assert archive_identity_key(old_pdf) == "top cabinet dra"
    assert archive_group_key(old_pdf) == "top cabinet dra | .pdf"
    assert archive_group_key(separate_sldprt) == "top cabinet dra | .sldprt"
    assert [item.source for item in result.archive_files] == [old_pdf]
    assert result.latest_files == (newest_pdf,)
    assert result.ungrouped_files == (separate_sldprt,)


def test_archive_keeps_all_files_tied_for_newest_time(tmp_path: Path) -> None:
    now = datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc)
    source = tmp_path / "project"
    source.mkdir()
    first = source / "FSI-100-20-300 Drawing.pdf"
    second = source / "FSI-100-20-300 Model.pdf"
    set_modified_time(first, now - timedelta(days=5))
    set_modified_time(second, now - timedelta(days=5))

    result = scan_files_for_archive(source, tmp_path / "archive")

    assert result.archive_files == ()
    assert result.latest_files == (first, second)
    assert result.duplicate_group_count == 1


def test_archive_scan_skips_archive_and_old_version_folders(tmp_path: Path) -> None:
    now = datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc)
    source = tmp_path / "project"
    archive = source / "Archive"
    old_versions = source / "Old Versions"
    archive.mkdir(parents=True)
    old_versions.mkdir()
    old_source = source / "FSI-200-10-100 old.step"
    newest_source = source / "FSI-200-10-100 newest.step"
    already_archived = archive / "FSI-200-10-100 archived.step"
    protected = old_versions / "FSI-200-10-100 legacy.ipt"
    set_modified_time(old_source, now - timedelta(days=100))
    set_modified_time(newest_source, now - timedelta(days=1))
    set_modified_time(already_archived, now)
    set_modified_time(protected, now - timedelta(days=365))

    result = scan_files_for_archive(source, archive)

    assert [item.source for item in result.archive_files] == [old_source]
    assert result.latest_files == (newest_source,)
    assert result.skipped_old_version_files == (protected,)


def test_archive_moves_older_versions_and_preserves_subfolders(tmp_path: Path) -> None:
    now = datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc)
    source = tmp_path / "project"
    nested = source / "drawings" / "issued"
    nested.mkdir(parents=True)
    old_file = nested / "FSI-300-20-100 old.pdf"
    newest_file = source / "FSI-300-20-100 newest.pdf"
    set_modified_time(old_file, now - timedelta(days=100))
    set_modified_time(newest_file, now - timedelta(days=1))
    archive = tmp_path / "archive"

    result = scan_files_for_archive(source, archive)
    completed = execute_archive_moves(result.archive_files)
    removed = remove_empty_folders(source, excluded_folders=(archive,))

    assert completed[0].destination == archive / "drawings" / "issued" / old_file.name
    assert completed[0].destination.is_file()
    assert newest_file.is_file()
    assert not old_file.exists()
    assert removed == (nested, source / "drawings")
    assert source.is_dir()
