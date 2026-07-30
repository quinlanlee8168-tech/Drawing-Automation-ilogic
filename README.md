# Drawing File Organizer

A desktop program with two workflows: compare a folder against model/drawing paths in Excel, or group related filenames and archive older versions using the filesystem **Date modified** value.

## Safety behavior

- Nothing moves until you preview the list and confirm it.
- The program discovers every unmatched file type and lets you select one or more types to move.
- Folders named `Old Version`, `Old Versions`, `old_version(s)`, or `old-version(s)` are never moved or scanned as candidates.
- Existing destination files are never overwritten; the program adds `(1)`, `(2)`, and so on.
- Subfolder structure is preserved in the destination.
- After a successful move, empty source subfolders are removed automatically.
- The selected source root, destination folder, and Old Version folders are never removed.
- If the destination is inside the selected source folder, it is excluded from scanning.
- Every worksheet is checked for model and drawing path columns; unrelated columns are ignored.

## Install

Install Python 3.10 or newer, then run:

```bash
python -m pip install -r requirements.txt
```

## Run

```bash
python app.py
```

1. Choose the folder containing the current model/drawing files.
2. Choose the `.xlsx` or `.xlsm` workbook containing file paths.
3. Choose or create the folder that should receive unmatched files.
4. Select **Scan all unmatched files**. The program scans every file type, including extensions it has not seen before.
5. In **File types found**, select the type or types to move:
   - Click `.pdf` to move every unmatched PDF.
   - Click `.sldprt` to move every unmatched SOLIDWORKS part.
   - Hold **Ctrl** and click `.pdf` and `.sldprt` to select both types.
   - Hold **Shift** to select a range of types.
   - Use **Select all types** to move every unmatched type.
   - Use **Clear type selection** to start again.
6. Review the matching files in the preview table and select **Move selected types** to confirm.

The list of file types is generated dynamically from the scan; it is not limited to a predefined set. Each option includes the number of unmatched files found, such as `.pdf — 12 files` or `.sldprt — 48 files`. Selecting one or more types updates the preview to show every file that will be moved. Files of unselected types remain in the source folder.

After the selected files move successfully, the program checks the source tree from the deepest folders upward and deletes folders that are empty. It does not delete the selected source folder itself, the destination folder if it is inside the source, symbolic-link folders, or any recognized Old Version folder tree. Folders that still contain referenced or unselected files remain unchanged.

## Archive older file versions

Open the **Archive older versions** tab to compare related files without using Excel:

1. Choose **Folder to compare**.
2. Choose **Archive older versions to**.
3. Select **Compare file versions**.
4. Review each older file alongside its comparison key, its Date modified, and the newest Date modified in that group.
5. Select **Archive older versions** and confirm.

The scan includes every regular file type. For each filename, it searches case-insensitively for an FSI identifier such as `FSI-020-00-01`, `FSI-105-01-004`, or `FSI-020-00-001D`. A single letter attached directly to the final number is always treated as a permanent part-number suffix, never as a revision marker. Therefore, `FSI-020-00-001D` and `FSI-020-00-001E` are different permanent identities and are never compared with each other. Files are treated as versions of the same item only when they have both the same complete FSI identifier and the same file extension. PDF versions are compared only with PDFs, DWGs only with DWGs, SLDPRTs only with SLDPRTs, and so on.

If a filename does not contain an FSI identifier, the lowercase first 15 characters of the filename (without its extension) become the fallback identity. The extension is still included in the comparison key, so fallback PDF and SLDPRT files remain independent.

Within every same-identity, same-extension group containing two or more files, the program reads the filesystem modification timestamp (`Date modified` in Windows File Explorer). Files strictly older than the newest timestamp are previewed for archive. The newest file remains in the source. If two or more files are tied for the newest timestamp, all tied files remain for safety. A file with no matching version of its own type is left untouched.

Dates and revision text elsewhere in filenames do not determine which file is newest. Archive subfolder structure is preserved, existing archive files are never overwritten, and empty source folders are removed afterward. The archive destination is excluded if it is inside the source tree; recognized Old Version folders and symbolic-link files are skipped.

## Compatible Excel layouts

The program searches every worksheet for a model path column, a drawing path column, or both. The columns can be in any position and the header can be on any row. Header matching is case-insensitive and ignores spaces, underscores, hyphens, and other punctuation, so all of these examples work:

- `ModelPath`, `Model Path`, or `MODEL_PATH`
- `DrawingPath`, `Drawing Path`, or `drawing_path`

Only values below recognized model/drawing path headers are used when those headers are present. Other columns such as order, quantity, finish, material, status, notes, and backup paths are ignored. A workbook with only `ModelPath` or only `DrawingPath` is also valid. For compatibility with simple path-list workbooks, sheets without these headers still recognize cells that look like file paths.

Both normal Excel shared-string cells and inline text cells are supported. Paths may be absolute Windows paths, mapped-drive paths such as `Z:\Design\...\PARTS AND ASSEMBLIES\part.ipt`, or relative paths. If the mapped drive is different or unavailable, select the corresponding source folder (for example, `PARTS AND ASSEMBLIES`) and the program rebases the path below that folder. Relative paths are checked against both the selected source folder and the workbook's folder.

Supported workbook extensions are `.xlsx` and `.xlsm`. The older binary `.xls` format is not supported; open it in Excel and use **Save As** to create an `.xlsx` file first.

## Workflows

- **Excel unmatched-file cleanup**: uses an `.xlsx`/`.xlsm` workbook and moves unreferenced files by dynamically discovered extension.
- **Archive older versions**: does not require Excel; groups files by FSI code or a 15-character fallback and archives versions older than the newest filesystem Date modified value.

## Test

```bash
python -m pytest
```
