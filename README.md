# Drawing Automation (Inventor + PDF)

## Recommended workflow (Inventor iLogic + optional merge)

Use `ilogic_export_bom_pdfs.vb` to export drawings in Structured BOM order.

### What the iLogic rule does

- starts from the active top-level assembly (`.iam`)
- reads the **Structured BOM** recursively
- includes:
  - top-level parent assembly drawing
  - child subassembly drawings
  - child part drawings
- exports one PDF per BOM occurrence to `PDF_OUTPUT` with a BOM-order numeric prefix (e.g., `0001_...pdf`)
- repeated subassemblies/parts are preserved as repeated entries in export order
- writes one Excel manifest file `PDF_BOM_ORDER.xlsx` to capture exact export order (single worksheet: `PDF_BOM_ORDER`)
- includes `RAW PART NUMBER` (from model iProperties) and `PART_NUMBER FILTER` (extracts and normalizes the first `FSI-...` code so spacing like `FSI - 022 - 004 - 116` becomes `FSI-022-004-116`) in that manifest
- includes `Quantity` from BOM row item quantity in the manifest, multiplied through parent assembly quantities (children inherit parent multipliers)
- includes model `Revision Number` from **iProperties > Project** in both `PDF_BOM_ORDER` and `PART_COUNTS` (blank if not present)
- includes `Finish` and `Material` from model **iProperties > Custom** (blank if not present)
- highlights every `RAW PART NUMBER` cell that does **not** match `FSI-XXX-XX-XXX` (spaces around hyphens allowed)
- adds a second worksheet `PART_COUNTS` in the same workbook that tallies repeated `RAW PART NUMBER` values by summed BOM quantity and includes `REVISION` + `FINISH` + `MATERIAL` columns
- writes `missing_drawings.txt` for models without a matching drawing file
- temporarily disables iLogic event-driven rules while opening drawings for export to avoid external-rule popups from referenced documents
- searches for drawings recursively under the selected drawing search folder(s)
- when duplicate exact-name drawings are found, selects the newest modified file
- skips `OldVersions` folders during drawing search/indexing so outdated drawings are not selected

### Drawing match rule

For each model file, it searches the selected drawing folder(s) recursively and looks for drawings with the exact same base filename.

File names must match model base name exactly (case-insensitive):

- `<ModelName>.idw`
- `<ModelName>.dwg`

Example: `FSI-020-02-004.iam` → `FSI-020-02-004.idw` (or `.dwg`).

If multiple selected folders contain the same exact drawing base name, the rule chooses the candidate with the newest file modified date. The model's own folder is not preferred unless it is also the newest matching file in the selected search folders.

### How to run

1. Open the top-level assembly in Inventor.
2. Open **iLogic** and create a new rule.
3. Paste the contents of `ilogic_export_bom_pdfs.vb`.
4. Run the rule and enter drawing folder path(s) when prompted (semicolon-separated), or leave blank to use the assembly folder.
5. Check `<assembly folder>\PDF_OUTPUT`.

> Note: Inventor exports one drawing per PDF. If you need a single combined PDF, run `combine_from_manifest.py` after export.

## Combine into one BOM-ordered PDF

Use `combine_from_manifest.py` to merge exported PDFs into one file **using the exact order from `PDF_BOM_ORDER.xlsx`**.


> Important: `combine_from_manifest.py` is a **Python** script. Do **not** paste it into an iLogic rule window.

If you want to trigger the merge from Inventor, use `ilogic_run_manifest_merge.vb`, which calls Python for you.

### Configure and run

1. Install dependencies (one-time):

```bash
pip install pypdf openpyxl
```

   (or use `pip install PyPDF2 openpyxl`)

2. Run from terminal:

```bash
python combine_from_manifest.py
```

   Or on Windows, double-click `run_combine_from_manifest.bat` (it tries `python` first, then `py -3`).

3. A folder picker opens so the user can select the `PDF_OUTPUT` folder directly.
   - You can still run by command line with a path argument: `python combine_from_manifest.py "C:\path\to\PDF_OUTPUT"`
   - Or with environment variable: `PDF_OUTPUT_FOLDER`
4. Review the prompted list of PDFs (in manifest order) and confirm to continue.

Or in Inventor iLogic:

- create/run rule from `ilogic_run_manifest_merge.vb` (it auto-searches common locations and supports `scriptPathOverride`)
- for non-interactive runs, set `PDF_OUTPUT_FOLDER` environment variable to avoid terminal prompt
- it will auto-attempt `python -m pip install --upgrade --target "<script folder>\_vendor" pypdf` if the merge fails due to missing PDF library
- if auto-install fails, run that same command manually in the Python environment used by Inventor

Output:

- `Combined_BOM.pdf` in the same `PDF_OUTPUT` folder.

Manifest notes:
- `PDF_BOM_ORDER.xlsx` includes `Status` values (`Exported`, `MissingDrawing`, `ExportFailed`).
- Missing drawings are still recorded in the manifest (with blank `DrawingPath` / `ExportedPdf`) so you can open it in Excel and track gaps quickly.
- `combine_from_manifest.py` skips rows without `ExportedPdf`, so the merge continues without crashing.

## Legacy prototype (Excel-driven)

`combine_bom_pdfs_recursive.py` is a separate prototype for environments where BOM relationships are managed in Excel instead of Inventor.
