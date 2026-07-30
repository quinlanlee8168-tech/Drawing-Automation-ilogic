# PDF Package FSI Replacer

This script scans the **bottom-right area** of each page in a package PDF for a drawing number in this format:

`FSI-XXX-XX-XXX` or `FSI-XXX-XX-XXXA` (examples: `FSI-015-02-108`, `FSI-105-03-104A`)

It then replaces that package page with a matching PDF from your replacements folder, based on filenames such as:

`FSI-015-02-108 - STPD SHLTR 4 PNL END REAR WNDSCRN FRAME ASSEMBLY - REV D.pdf`

Suffix letters are treated as part of the drawing number, so `FSI-105-03-104A` matches only a replacement for `FSI-105-03-104A`, not `FSI-105-03-104`.

## Install

```bash
pip install pymupdf pypdf
```

## Usage (no TXT list required)

```bash
python replace_pdf_pages_by_fsi.py \
  --package ./input/package.pdf \
  --replacements ./input/replacements \
  --output ./output/package_YYYY-MM-DD.pdf
```

## Batch mode (multiple package PDFs at once)

```bash
python replace_pdf_pages_by_fsi.py \
  --package-dir ./input/package_folder \
  --replacements ./input/replacements \
  --output ./output/replaced_packages
```

- In batch mode, all `*.pdf` files in `--package-dir` are processed.
- `--output` must be a folder in batch mode.
- Each output file is named `<original> - YYYY-MM-DD.pdf` and summary is `<original> - YYYY-MM-DD - Summary.tsv`.

## Optional: Use a TXT list to limit which FSI codes can be replaced

```bash
python replace_pdf_pages_by_fsi.py \
  --package ./input/package.pdf \
  --list ./input/drawing_list.txt \
  --replacements ./input/replacements \
  --output ./output/package_YYYY-MM-DD.pdf \
  --summary ./output/package_replaced.summary.tsv
```

### Inputs

- `--package`: The PDF package to process.
- `--replacements`: Folder containing replacement PDFs.
- `--output`: Output PDF filename.
- `--list` (optional): Text file with drawing filenames. If provided, only those FSI codes are eligible.
- `--summary` (optional): Output summary TSV (.tsv) path.

### Optional scan tuning

The program first scans a small green title-block box for the Drawing No. and Rev cells. The green box uses normalized page coordinates, where `0` means the left/top of the page and `1` means the right/bottom of the page.

Default green-box coordinates:

```text
--title-left 0.845 --title-top 0.925 --title-right 0.975 --title-bottom 0.965
```

That means: start 84.5% across the page, start 92.5% down the page, stop at 97.5% across the page, and stop 96.5% down the page. For the sample Future Systems title block, this focuses on the bottom-right Drawing No. / Rev row instead of the full title block.

To adjust the green box:

- move it left: lower `--title-left` (example `0.82`)
- move it right/smaller: raise `--title-left` (example `0.87`)
- move it up: lower `--title-top` (example `0.90`)
- move it down/smaller: raise `--title-top` (example `0.94`)
- include more bottom area: raise `--title-bottom` up to `1.0`
- stop higher above the footer: lower `--title-bottom` (example `0.97`)

Monday reminder / next refinement: adjust the wider red fallback box if it still captures too much extra title-block detail. The wider red fallback box is currently controlled separately:

- `--right-frac` (default `0.35`): right-side fraction of page scanned by the wider fallback box.
- `--bottom-frac` (default `0.25`): bottom-side fraction of page scanned by the wider fallback box.

If the small green box does not find the drawing number, the script falls back to the wider lower-right red box.

### Scan preview images

To see exactly what area the program is scanning, add `--scan-preview-dir` to your command:

```bash
python replace_pdf_pages_by_fsi.py \
  --package ./input/package.pdf \
  --replacements ./input/replacements \
  --output ./output/package_YYYY-MM-DD.pdf \
  --scan-preview-dir ./output/scan_previews \
  --scan-preview-pages 3
```

The preview folder will contain PNG images with boxes drawn on top of the package pages:

- **Green box**: the small title-block scan used first for Drawing No. / Rev.
- **Red box**: the wider fallback lower-right scan controlled by `--right-frac` and `--bottom-frac`.
- `--scan-preview-pages 3` previews the first 3 pages. Use `--scan-preview-pages 0` to preview every page.

Use these preview images to confirm whether the green box fully covers only the Drawing No. and Rev cells. The preview key text file also prints the green-box coordinates being used.

Example with a slightly smaller green box:

```bash
python replace_pdf_pages_by_fsi.py \
  --package ./input/package.pdf \
  --replacements ./input/replacements \
  --output ./output/package_YYYY-MM-DD.pdf \
  --scan-preview-dir ./output/scan_previews \
  --scan-preview-pages 3 \
  --title-left 0.86 \
  --title-top 0.93 \
  --title-right 1.0 \
  --title-bottom 0.98
```

### Duplicate FSI replacement files

If multiple replacement PDFs contain the same FSI code, the script automatically picks the **newer revision**:

- prefers higher `REV` (e.g., `REV F` over `REV E`, or `REV 3` over `REV 2`)
- if revision token is equal, it picks the file with the newer modified timestamp

### Summary TSV output

The script writes a summary TSV (.tsv) file showing each package page and whether it was replaced.

- Default path: `<output_stem> - YYYY-MM-DD - Summary.tsv`
- You can override with `--summary <path.tsv>`

Columns:

- `Page`
- `FSI Code`
- `Package REV`
- `Replaced` (YES/NO)
- `Replacement File`
- `Replacement REV`
- `Status`


### Higher-REV-only replacement

The script now replaces a package page only when the matching replacement PDF has a **higher REV** than the REV detected on that package page. The replacement REV is read from the replacement PDF filename, such as `... REV F.pdf`; the package REV is read from the bottom-right text on the package page.

Examples:

- package page `FSI-015-02-066 REV E` + replacement file `... REV F.pdf` -> replaced
- package page `FSI-015-02-066 REV F` + replacement file `... REV F.pdf` -> not replaced
- package page `FSI-015-02-066 REV G` + replacement file `... REV F.pdf` -> not replaced

The package page part number/FSI code (including an optional suffix letter like `A` or `B`) and REV are detected from a refined bottom-right title-block area, so the scan avoids unrelated parts-list rows, notes, dimensions, and revision-history details where possible. The replacement part number/FSI code and REV are detected from the replacement PDF filename. For title blocks with a `Drawing No.` cell and a separate right-side `Rev` cell, the script reads the right-most `Rev` value as the current drawing REV. If that title-block REV cannot be read but the bottom-right area contains a revision table with multiple rows, the script falls back to the highest detected REV from that table. If the program cannot detect a package page REV, it does not replace that page because it cannot confirm the replacement REV is higher. If a matching replacement PDF is missing, the summary records `Does not exist`. If a page is updated, the summary records `Replaced to REV <revision>`.

### Inventor/iLogic REV filename export rule

For Inventor exports where the REV comes from the referenced part/subassembly model iProperties (`Project -> Revision Number`) instead of the drawing iProperties, see `ilogic_add_rev_to_pdf_filename.vb`.

The rule is based on the batch export iLogic workflow and:

- exports all open drawing documents to `Desktop\Inventor_PDF_Output`,
- closes each drawing after export,
- evaluates the models referenced by the actual drawing views and descriptor list, then chooses the best model with usable iProperties/revision data before reading `Part Number`, `Description`, and `Revision Number` from that model; the rule reads API `Design Tracking Properties` first, then the Design Tracking internal GUID, scans property sets, and finally tries iLogic `iProperties.Value(..., "Project", ...)`,
- names referenced-model PDFs as `<Part Number> - <Description> - REV <Revision> - YYYY-MM-DD.pdf`,
- defaults a blank or missing `Revision Number` to `REV A`, and
- records candidate model scoring plus the selected referenced model name, part number, and REV read in the export report so you can verify which model supplied the REV, and
- records `No revision number found; defaulted to REV A` in the export report when REV A is used as a fallback.

### Multi-page replacements

If a matched replacement PDF has multiple pages, the script applies them in-order **within each contiguous block** of that FSI code, then resets for the next block.

Example for a 3-page replacement PDF:

- package pages `3, 4, 5` with same FSI -> replacement pages `1, 2, 3`
- package pages `67, 68, 69` with same FSI -> replacement pages `1, 2, 3` (resets)
- package pages `100, 101, 102` with same FSI -> replacement pages `1, 2, 3` (resets)

If a contiguous block is longer than the replacement page count, the replacement pages repeat in-order within that block.

### Click-to-run GUI (no command line)

A GUI launcher is included as `pdf_replacer_gui.py`.

Run it with:

```bash
py pdf_replacer_gui.py
```

It will prompt you to:

1. Choose single-file mode or batch mode
2. Select replacements folder
3. In single mode: select one package PDF, output PDF, summary TSV (.tsv)
4. In batch mode: select package folder and output folder

### Build a Windows `.exe`

Install PyInstaller:

```bash
py -m pip install pyinstaller
```

Build executable:

```bash
py -m PyInstaller --onefile --windowed --name PDF_Replacer_Gui pdf_replacer_gui.py
```

After build, the executable will be at:

- `dist\PDF_Replacer_Gui.exe`

Copy these files together in the same folder for users:

- `PDF_Replacer_Gui.exe`
- `replace_pdf_pages_by_fsi.py`

(Launcher calls `replace_pdf_pages_by_fsi.py` in the same directory.)
