#!/usr/bin/env python3
"""
Replace pages in a PDF package by matching bottom-right FSI codes.
Supports one-to-one sequential replacement when replacement PDFs have multiple pages.

Example drawing number formats: FSI-015-02-108, FSI-105-03-104A
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import fitz  # PyMuPDF
from pypdf import PdfReader, PdfWriter

FSI_CODE_PATTERN = re.compile(r"\b(?:FSI-)?(?P<number>\d{3}-\d{2}-\d{3}[A-Z]?)\b", re.IGNORECASE)
REV_PATTERN = re.compile(r"\bREV(?:ISION)?\s*[:.-]?\s*([A-Z0-9]+)\b", re.IGNORECASE)
DATE_LIKE_PATTERN = re.compile(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b")
UNKNOWN_REV_KEY = (0, "")
DEFAULT_TITLE_BLOCK_RECT = (0.845, 0.925, 0.975, 0.965)
NormalizedRect = Tuple[float, float, float, float]


def normalize_fsi_code(match: re.Match[str]) -> str:
    return f"FSI-{match.group('number').upper()}"


def extract_fsi_from_filename(name: str) -> Optional[str]:
    match = FSI_CODE_PATTERN.search(name)
    return normalize_fsi_code(match) if match else None


def load_allowed_codes(list_file: Path) -> set[str]:
    allowed_codes: set[str] = set()
    with list_file.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            code = extract_fsi_from_filename(line)
            if code:
                allowed_codes.add(code)
    return allowed_codes


def normalize_rev_token(token: str) -> Tuple[int, str]:
    """Return revision sort key where higher is newer.

    Supports REV A..Z and REV 0..999. Unknown format sorts lowest.
    """
    token = token.upper()
    if token.isdigit():
        return (2, token.zfill(6))
    if len(token) == 1 and "A" <= token <= "Z":
        return (1, token)
    return (0, token)


def extract_rev_token(name: str) -> Tuple[int, str]:
    rev_match = REV_PATTERN.search(name)
    if not rev_match:
        return UNKNOWN_REV_KEY
    return normalize_rev_token(rev_match.group(1))


def extract_rev_label(name: str) -> str:
    rev_match = REV_PATTERN.search(name)
    return rev_match.group(1).upper() if rev_match else ""


def build_replacement_map(replacements_dir: Path, allowed_codes: Optional[set[str]] = None) -> Dict[str, Path]:
    replacements: Dict[str, Path] = {}

    for pdf_path in replacements_dir.glob("*.pdf"):
        code = extract_fsi_from_filename(pdf_path.stem)
        if not code:
            continue
        if allowed_codes is not None and code not in allowed_codes:
            continue

        if code in replacements:
            current = replacements[code]
            current_rev = extract_rev_token(current.stem)
            candidate_rev = extract_rev_token(pdf_path.stem)

            if candidate_rev > current_rev:
                print(f"Duplicate code {code}: choosing newer revision {pdf_path.name} over {current.name}")
                replacements[code] = pdf_path
            elif candidate_rev == current_rev:
                current_mtime = current.stat().st_mtime
                candidate_mtime = pdf_path.stat().st_mtime
                if candidate_mtime > current_mtime:
                    print(f"Duplicate code {code}: same revision token; choosing latest modified {pdf_path.name}")
                    replacements[code] = pdf_path
                else:
                    print(f"Duplicate code {code}: keeping {current.name}, skipping {pdf_path.name}")
            else:
                print(f"Duplicate code {code}: keeping newer revision {current.name}, skipping {pdf_path.name}")
            continue

        replacements[code] = pdf_path

    return replacements


def get_bottom_right_rect(page: fitz.Page, right_frac: float, bottom_frac: float) -> fitz.Rect:
    rect = page.rect
    return fitz.Rect(
        rect.x0 + rect.width * (1.0 - right_frac),
        rect.y0 + rect.height * (1.0 - bottom_frac),
        rect.x1,
        rect.y1,
    )


def validate_normalized_rect(rect: NormalizedRect) -> NormalizedRect:
    left, top, right, bottom = rect
    if not (0.0 <= left < right <= 1.0 and 0.0 <= top < bottom <= 1.0):
        raise ValueError(
            "Title-block scan coordinates must be normalized values where "
            "0 <= left < right <= 1 and 0 <= top < bottom <= 1."
        )
    return rect


def get_refined_title_block_rect(page: fitz.Page, title_block_rect: NormalizedRect) -> fitz.Rect:
    """Return the tight bottom-right title-block area for drawing number + REV.

    This avoids scanning the wider lower-right page area where parts lists, notes,
    dimensions, and revision-history rows can appear.
    """
    left, top, right, bottom = validate_normalized_rect(title_block_rect)
    page_rect = page.rect
    return fitz.Rect(
        page_rect.x0 + page_rect.width * left,
        page_rect.y0 + page_rect.height * top,
        page_rect.x0 + page_rect.width * right,
        page_rect.y0 + page_rect.height * bottom,
    )


def get_words_in_rect(page: fitz.Page, search_rect: fitz.Rect) -> List[Tuple[float, float, float, float, str]]:
    words_in_rect: List[Tuple[float, float, float, float, str]] = []
    for x0, y0, x1, y1, text, *_ in page.get_text("words"):
        word_rect = fitz.Rect(x0, y0, x1, y1)
        if search_rect.intersects(word_rect):
            words_in_rect.append((x0, y0, x1, y1, text))
    return words_in_rect


def find_page_fsi_code_in_rect(page: fitz.Page, search_rect: fitz.Rect) -> Optional[str]:
    candidates: List[Tuple[float, float, str]] = []

    for x0, y0, x1, y1, text in get_words_in_rect(page, search_rect):
        match = FSI_CODE_PATTERN.search(text)
        if match:
            candidates.append((x1, y1, normalize_fsi_code(match)))

    if not candidates:
        clip_text = page.get_text("text", clip=search_rect)
        match = FSI_CODE_PATTERN.search(clip_text)
        return normalize_fsi_code(match) if match else None

    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return candidates[0][2]


def find_page_fsi_code(page: fitz.Page, right_frac: float, bottom_frac: float, title_block_rect: NormalizedRect) -> Optional[str]:
    # First scan only the tight title-block drawing-number area. This prevents
    # matching FSI numbers from the parts list or notes.
    title_block_code = find_page_fsi_code_in_rect(page, get_refined_title_block_rect(page, title_block_rect))
    if title_block_code:
        return title_block_code

    # Fallback to the user-tunable lower-right scan area for older/different
    # title-block layouts.
    return find_page_fsi_code_in_rect(page, get_bottom_right_rect(page, right_frac, bottom_frac))


def is_supported_rev_label(label: str) -> bool:
    label = label.upper()
    return label.isdigit() or (len(label) == 1 and "A" <= label <= "Z")


def choose_highest_rev(labels: List[str]) -> Tuple[Tuple[int, str], str]:
    valid_labels = [label.upper() for label in labels if is_supported_rev_label(label)]
    if not valid_labels:
        return UNKNOWN_REV_KEY, ""

    return max((normalize_rev_token(label), label) for label in valid_labels)


def line_has_date_like_token(line_words: List[str]) -> bool:
    return any(DATE_LIKE_PATTERN.search(word) for word in line_words)


def group_words_by_line(words: List[Tuple[float, float, float, float, str]], y_tolerance: float = 4.0) -> List[List[str]]:
    lines: List[Tuple[float, List[Tuple[float, str]]]] = []

    for x0, y0, _x1, _y1, text in sorted(words, key=lambda item: (item[1], item[0])):
        if not text.strip():
            continue

        if not lines or abs(y0 - lines[-1][0]) > y_tolerance:
            lines.append((y0, [(x0, text)]))
        else:
            lines[-1][1].append((x0, text))

    return [[text for _x, text in sorted(line_words, key=lambda item: item[0])] for _line_y, line_words in lines]


def find_title_block_rev_from_words(words: List[Tuple[float, float, float, float, str]]) -> Tuple[Tuple[int, str], str]:
    """Find a REV value from a title-block cell where header `Rev` is above the value.

    Many Future Systems title blocks place `Rev` as a column header and the actual
    revision letter directly below it (for example, a header cell `Rev` with `D`
    underneath). This helper reads that layout before falling back to revision
    table parsing.
    """
    rev_headers: List[Tuple[float, float, float, float]] = []

    for x0, y0, x1, y1, text in words:
        cleaned = re.sub(r"[^A-Za-z]", "", text).upper()
        if cleaned in {"REV", "REVISION"}:
            rev_headers.append((x0, y0, x1, y1))

    if not rev_headers:
        return UNKNOWN_REV_KEY, ""

    # If there are multiple `Rev` headers, prefer the right-most one. Revision
    # tables also have a `Rev` header, but the drawing title block REV cell is
    # normally the right-most REV header in the bottom-right scan area.
    rightmost_header_center_x = max((x0 + x1) / 2.0 for x0, _y0, x1, _y1 in rev_headers)

    candidates: List[Tuple[float, Tuple[int, str], str]] = []
    for header_x0, _header_y0, header_x1, header_y1 in rev_headers:
        header_center_x = (header_x0 + header_x1) / 2.0
        if header_center_x < rightmost_header_center_x - 50.0:
            continue

        header_width = max(header_x1 - header_x0, 1.0)
        max_x_distance = max(header_width * 3.0, 35.0)

        for x0, y0, x1, _y1, text in words:
            if y0 <= header_y1:
                continue

            candidate_label = re.sub(r"[^A-Za-z0-9]", "", text).upper()
            if not is_supported_rev_label(candidate_label):
                continue

            candidate_center_x = (x0 + x1) / 2.0
            x_distance = abs(candidate_center_x - header_center_x)
            if x_distance > max_x_distance:
                continue

            y_distance = y0 - header_y1
            # Prefer the closest value under the Rev header, then the right column.
            distance_score = y_distance + x_distance
            candidates.append((distance_score, normalize_rev_token(candidate_label), candidate_label))

    if not candidates:
        return UNKNOWN_REV_KEY, ""

    _distance, rev_key, rev_label = min(candidates, key=lambda item: item[0])
    return rev_key, rev_label


def find_page_rev(page: fitz.Page, right_frac: float, bottom_frac: float, title_block_rect: NormalizedRect) -> Tuple[Tuple[int, str], str]:
    """Find the current package page REV in the bottom-right title block.

    The replacement REV comes from the replacement PDF filename, but the package
    REV must come from the package page itself. The primary target is the title
    block `Rev` cell beside/under the drawing number. Revision-table rows are
    used only as a fallback.
    """
    refined_rect = get_refined_title_block_rect(page, title_block_rect)
    refined_words = get_words_in_rect(page, refined_rect)

    # First read the actual title-block Rev value (for example, header `Rev` with
    # value `D` below it). This is the current drawing/page REV to compare.
    title_block_rev = find_title_block_rev_from_words(refined_words)
    if title_block_rev != (UNKNOWN_REV_KEY, ""):
        return title_block_rev

    search_rect = get_bottom_right_rect(page, right_frac, bottom_frac)
    clip_text = page.get_text("text", clip=search_rect)
    words_in_rect = get_words_in_rect(page, search_rect)

    rev_labels = [match.group(1).upper() for match in REV_PATTERN.finditer(clip_text)]

    # Fallback: revision tables commonly have rows like: E  C  09/26/24  ...
    # Read the first token from each date-bearing row and choose the highest REV.
    for line_words in group_words_by_line(words_in_rect):
        if not line_words:
            continue
        first_token = re.sub(r"[^A-Za-z0-9]", "", line_words[0]).upper()
        if is_supported_rev_label(first_token) and line_has_date_like_token(line_words):
            rev_labels.append(first_token)

    return choose_highest_rev(rev_labels)


def should_replace_for_higher_rev(
    package_rev: Tuple[int, str],
    replacement_rev: Tuple[int, str],
    package_rev_label: str,
    replacement_rev_label: str,
) -> Tuple[bool, str]:
    if replacement_rev == UNKNOWN_REV_KEY:
        return False, "Not replaced: replacement filename has no REV token"
    if package_rev == UNKNOWN_REV_KEY:
        return False, f"Not replaced: package page REV not detected; replacement REV {replacement_rev_label} cannot be confirmed higher"
    if replacement_rev <= package_rev:
        return False, f"Not replaced: replacement REV {replacement_rev_label} is not higher than package REV {package_rev_label}"
    return True, ""


def safe_preview_name(path: Path) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", path.stem).strip("_") or "package"


def write_scan_preview_images(
    package_pdf: Path,
    preview_dir: Path,
    right_frac: float,
    bottom_frac: float,
    max_pages: int,
    title_block_rect: NormalizedRect,
) -> None:
    """Write annotated PNGs showing the exact scan boxes used by the script.

    Green box = refined title-block scan used first for drawing number/REV.
    Red box = wider fallback lower-right scan controlled by --right-frac/--bottom-frac.
    """
    preview_dir.mkdir(parents=True, exist_ok=True)

    with fitz.open(package_pdf) as doc:
        page_count = len(doc) if max_pages <= 0 else min(max_pages, len(doc))
        for index in range(page_count):
            page = doc[index]
            refined_rect = get_refined_title_block_rect(page, title_block_rect)
            fallback_rect = get_bottom_right_rect(page, right_frac, bottom_frac)
            detected_code = find_page_fsi_code(page, right_frac, bottom_frac, title_block_rect) or "NOT FOUND"
            _rev_key, detected_rev = find_page_rev(page, right_frac, bottom_frac, title_block_rect)
            detected_rev = detected_rev or "NOT FOUND"

            # Draw preview boxes after detection so markup does not affect text scanning.
            page.draw_rect(fallback_rect, color=(1, 0, 0), width=1.5)
            page.draw_rect(refined_rect, color=(0, 0.7, 0), width=2.5)

            label_point = fitz.Point(refined_rect.x0, max(page.rect.y0 + 14, refined_rect.y0 - 28))
            page.insert_text(
                label_point,
                f"GREEN title scan {title_block_rect} | RED fallback | Drawing: {detected_code} | REV: {detected_rev}",
                fontsize=8,
                color=(0, 0.35, 0),
            )

            pixmap = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
            preview_path = preview_dir / f"{safe_preview_name(package_pdf)} - page {index + 1:03d} scan preview.png"
            pixmap.save(preview_path)

    key_path = preview_dir / f"{safe_preview_name(package_pdf)} - scan preview key.txt"
    key_path.write_text(
        f"GREEN box = title-block scan used first for Drawing No. / Rev. Normalized coordinates: {title_block_rect}.\n"
        "Coordinates are page percentages: left, top, right, bottom. Example: left=0.845 starts 84.5% across the page.\n"
        "RED box = wider fallback lower-right scan controlled by --right-frac and --bottom-frac.\n"
        "If the green box misses the Drawing No. or Rev cell, adjust --title-left/--title-top/--title-right/--title-bottom.\n",
        encoding="utf-8",
    )
    print(f"Scan preview images written: {preview_dir}")


def replace_package_pages(
    package_pdf: Path,
    output_pdf: Path,
    replacements: Dict[str, Path],
    right_frac: float,
    bottom_frac: float,
    title_block_rect: NormalizedRect,
) -> Tuple[int, int, List[str]]:
    package_doc = fitz.open(package_pdf)
    package_reader = PdfReader(str(package_pdf))
    writer = PdfWriter()

    replaced_count = 0
    missing_count = 0
    summary_rows: List[str] = []

    replacement_pages_by_code: Dict[str, List] = {}
    replacement_totals: Dict[str, int] = {}
    replacement_revs_by_code: Dict[str, Tuple[int, str]] = {}
    replacement_rev_labels_by_code: Dict[str, str] = {}

    for code, replacement_pdf in replacements.items():
        replacement_reader = PdfReader(str(replacement_pdf))
        pages = list(replacement_reader.pages)
        if len(pages) == 0:
            raise ValueError(f"Replacement PDF has no pages: {replacement_pdf}")
        replacement_pages_by_code[code] = pages
        replacement_totals[code] = len(pages)
        replacement_revs_by_code[code] = extract_rev_token(replacement_pdf.stem)
        replacement_rev_labels_by_code[code] = extract_rev_label(replacement_pdf.stem)

    active_code: Optional[str] = None
    active_position = 0

    for index in range(len(package_reader.pages)):
        page = package_doc[index]
        page_code = find_page_fsi_code(page, right_frac, bottom_frac, title_block_rect)
        if not page_code or page_code not in replacements:
            writer.add_page(package_reader.pages[index])
            if page_code:
                missing_count += 1
                summary_rows.append(f"{index + 1}\t{page_code}\t\tNO\t\t\tDoes not exist: no replacement PDF found for FSI code")
            else:
                summary_rows.append(f"{index + 1}\t\t\tNO\t\t\tNo FSI code detected")
            active_code = None
            active_position = 0
            continue

        # Reset sequence when a new contiguous block starts.
        if page_code != active_code:
            active_code = page_code
            active_position = 0

        package_rev, package_rev_label = find_page_rev(page, right_frac, bottom_frac, title_block_rect)
        replacement_rev = replacement_revs_by_code[page_code]
        replacement_rev_label = replacement_rev_labels_by_code[page_code]
        should_replace, skip_status = should_replace_for_higher_rev(
            package_rev=package_rev,
            replacement_rev=replacement_rev,
            package_rev_label=package_rev_label,
            replacement_rev_label=replacement_rev_label,
        )
        if not should_replace:
            writer.add_page(package_reader.pages[index])
            summary_rows.append(
                f"{index + 1}\t{page_code}\t{package_rev_label}\tNO\t"
                f"{replacements[page_code].name}\t{replacement_rev_label}\t{skip_status}"
            )
            active_code = None
            active_position = 0
            continue

        replacement_pages = replacement_pages_by_code[page_code]
        replacement_total = replacement_totals[page_code]

        replacement_page = replacement_pages[active_position % replacement_total]
        writer.add_page(replacement_page)
        replaced_count += 1

        used_page_num = (active_position % replacement_total) + 1
        summary_rows.append(
            f"{index + 1}\t{page_code}\t{package_rev_label}\tYES\t{replacements[page_code].name}\t"
            f"{replacement_rev_label}\tReplaced to REV {replacement_rev_label} using page {used_page_num} of {replacement_total} "
            f"because replacement REV {replacement_rev_label} is higher than package REV {package_rev_label}"
        )

        active_position += 1

    with output_pdf.open("wb") as handle:
        writer.write(handle)

    package_doc.close()
    return replaced_count, missing_count, summary_rows


def default_summary_path(output_pdf: Path) -> Path:
    today = date.today().isoformat()
    stem = output_pdf.stem
    if stem.endswith(f" - {today}"):
        return output_pdf.with_name(f"{stem} - Summary.tsv")
    return output_pdf.with_name(f"{stem} - {today} - Summary.tsv")


def process_single_package(
    package_pdf: Path,
    replacements: Dict[str, Path],
    output_pdf: Path,
    summary_path: Optional[Path],
    right_frac: float,
    bottom_frac: float,
    scan_preview_dir: Optional[Path],
    scan_preview_pages: int,
    title_block_rect: NormalizedRect,
) -> Tuple[int, int, Path]:
    if scan_preview_dir is not None:
        write_scan_preview_images(
            package_pdf=package_pdf,
            preview_dir=scan_preview_dir,
            right_frac=right_frac,
            bottom_frac=bottom_frac,
            max_pages=scan_preview_pages,
            title_block_rect=title_block_rect,
        )

    replaced, missing, summary_rows = replace_package_pages(
        package_pdf=package_pdf,
        output_pdf=output_pdf,
        replacements=replacements,
        right_frac=right_frac,
        bottom_frac=bottom_frac,
        title_block_rect=title_block_rect,
    )

    final_summary_path = summary_path if summary_path else default_summary_path(output_pdf)
    with final_summary_path.open("w", encoding="utf-8") as summary_file:
        summary_file.write("Page\tFSI Code\tPackage REV\tReplaced\tReplacement File\tReplacement REV\tStatus\n")
        for row in summary_rows:
            summary_file.write(f"{row}\n")

    print(f"Done: {package_pdf.name} -> {output_pdf.name} | Replaced pages: {replaced}")
    if missing:
        print(f"Detected FSI code on page(s) but replacement missing for {missing} page(s).")
    print(f"Summary written: {final_summary_path}")
    return replaced, missing, final_summary_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Replace pages in a PDF package using FSI code matching.")
    parser.add_argument("--package", required=False, type=Path, default=None, help="Input package PDF to scan and replace.")
    parser.add_argument("--package-dir", required=False, type=Path, default=None, help="Optional folder of package PDFs to process in batch.")
    parser.add_argument("--list", required=False, type=Path, default=None, help="Optional text file with drawing filenames to limit allowed FSI codes.")
    parser.add_argument("--replacements", required=True, type=Path, help="Folder containing replacement PDF files.")
    parser.add_argument("--output", required=True, type=Path, help="Output PDF path.")
    parser.add_argument("--right-frac", type=float, default=0.35, help="Right-side fraction of page to scan (default: 0.35).")
    parser.add_argument("--bottom-frac", type=float, default=0.25, help="Bottom-side fraction of page to scan (default: 0.25).")
    parser.add_argument("--summary", type=Path, default=None, help="Optional output summary TSV file path.")
    parser.add_argument("--scan-preview-dir", type=Path, default=None, help="Optional folder for annotated PNG previews showing scan boxes.")
    parser.add_argument("--scan-preview-pages", type=int, default=3, help="Number of preview pages to write (default: 3; use 0 for all pages).")
    parser.add_argument("--title-left", type=float, default=DEFAULT_TITLE_BLOCK_RECT[0], help=f"Green title scan left edge as page percentage 0-1 (default: {DEFAULT_TITLE_BLOCK_RECT[0]}).")
    parser.add_argument("--title-top", type=float, default=DEFAULT_TITLE_BLOCK_RECT[1], help=f"Green title scan top edge as page percentage 0-1 (default: {DEFAULT_TITLE_BLOCK_RECT[1]}).")
    parser.add_argument("--title-right", type=float, default=DEFAULT_TITLE_BLOCK_RECT[2], help=f"Green title scan right edge as page percentage 0-1 (default: {DEFAULT_TITLE_BLOCK_RECT[2]}).")
    parser.add_argument("--title-bottom", type=float, default=DEFAULT_TITLE_BLOCK_RECT[3], help=f"Green title scan bottom edge as page percentage 0-1 (default: {DEFAULT_TITLE_BLOCK_RECT[3]}).")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        title_block_rect = validate_normalized_rect((args.title_left, args.title_top, args.title_right, args.title_bottom))
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if args.list and not args.list.exists():
        print(f"List file not found: {args.list}", file=sys.stderr)
        return 1
    if not args.replacements.exists() or not args.replacements.is_dir():
        print(f"Replacements folder not found: {args.replacements}", file=sys.stderr)
        return 1

    if args.package is None and args.package_dir is None:
        print("Provide --package for single mode or --package-dir for batch mode.", file=sys.stderr)
        return 1
    if args.package is not None and args.package_dir is not None:
        print("Use either --package or --package-dir, not both.", file=sys.stderr)
        return 1

    allowed_codes: Optional[set[str]] = None
    if args.list:
        allowed_codes = load_allowed_codes(args.list)
        if not allowed_codes:
            print("No valid FSI codes found in list file.", file=sys.stderr)
            return 1

    replacement_map = build_replacement_map(args.replacements, allowed_codes)
    if not replacement_map:
        if args.list:
            print("No replacement PDFs found for FSI codes in the list.", file=sys.stderr)
        else:
            print("No replacement PDFs with valid FSI code were found in replacements folder.", file=sys.stderr)
        return 1

    if args.package_dir is not None:
        if not args.package_dir.exists() or not args.package_dir.is_dir():
            print(f"Package folder not found: {args.package_dir}", file=sys.stderr)
            return 1

        package_files = sorted(args.package_dir.glob("*.pdf"))
        if not package_files:
            print(f"No PDF files found in package folder: {args.package_dir}", file=sys.stderr)
            return 1

        output_dir = args.output
        output_dir.mkdir(parents=True, exist_ok=True)
        if not output_dir.is_dir():
            print("In batch mode, --output must be a directory.", file=sys.stderr)
            return 1

        total_replaced = 0
        total_missing = 0
        for package_pdf in package_files:
            today = date.today().isoformat()
            output_pdf = output_dir / f"{package_pdf.stem} - {today}.pdf"
            replaced, missing, _ = process_single_package(
                package_pdf=package_pdf,
                replacements=replacement_map,
                output_pdf=output_pdf,
                summary_path=output_pdf.with_name(f"{output_pdf.stem} - Summary.tsv"),
                right_frac=args.right_frac,
                bottom_frac=args.bottom_frac,
                scan_preview_dir=(args.scan_preview_dir / safe_preview_name(package_pdf)) if args.scan_preview_dir else None,
                scan_preview_pages=args.scan_preview_pages,
                title_block_rect=title_block_rect,
            )
            total_replaced += replaced
            total_missing += missing

        print(f"Batch complete. Packages processed: {len(package_files)} | Total replaced pages: {total_replaced}")
        if total_missing:
            print(f"Batch note: replacement missing for {total_missing} page(s) across packages.")
        return 0

    if not args.package or not args.package.exists():
        print(f"Package PDF not found: {args.package}", file=sys.stderr)
        return 1

    process_single_package(
        package_pdf=args.package,
        replacements=replacement_map,
        output_pdf=args.output,
        summary_path=args.summary,
        right_frac=args.right_frac,
        bottom_frac=args.bottom_frac,
        scan_preview_dir=args.scan_preview_dir,
        scan_preview_pages=args.scan_preview_pages,
        title_block_rect=title_block_rect,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
