# Wayfinding Document Scanner

A Windows-oriented Python desktop application that scans **searchable PDF files** for
wayfinding and signage requirements. It creates reviewable findings for materials,
finishes, thicknesses, colors, and anti-graffiti systems, then exports them to a CSV file
that opens in Microsoft Excel.

The first prototype is intentionally a candidate-finding tool: every result includes the
source PDF page and nearby source text so a designer can verify it. It does not replace
professional review of the contract documents.

## What the prototype finds

The default vocabulary is based on representative wayfinding specification and drawing
examples, including:

- Materials such as aluminum, aluminum composite, steel, stainless steel, tempered glass,
  Dibond, MDF, EPDM, vinyl, acrylic, and polycarbonate.
- Finishes such as powder coating, paint, primer, topcoat, anodizing, mill finish,
  galvanizing, fluoropolymer, enamel, and bituminous paint.
- Thickness notation such as `3 mm thick`, `5mm steel`, `0.051 mm DFT`, gauge, inches,
  microns, and mils.
- Anti-graffiti film, sacrificial coatings, graffiti-resistant coatings, and related terms.
- Color references including Pantone, CMYK, RAL, traffic colors, and project palette names.

The extraction rules intentionally require thickness context such as `thick`, `DFT`,
`sheet`, `plate`, `panel`, or `coating`. This reduces false positives from dimensions such
as a `50 mm clearance`.

Drawing pages are processed as localized PDF text blocks rather than as one flattened page.
This keeps nearby callouts separate—for example, vinyl graphics from Panel B are not assigned
to Panel D's steel side panels. A dimension is reported as thickness only when it is explicitly
marked as `thick`/`DFT`, or when it directly precedes a recognized material such as
`5mm steel`.

## Windows 11: easiest way to start

You do not need to type Python commands for normal setup or use.

### First-time setup

1. Download this project as a ZIP file and extract it to a normal folder, such as
   `Documents\Wayfinding-Document-Scanner`. Do not run it from inside the ZIP preview.
2. Install [Python 3.12](https://www.python.org/downloads/windows/). In the Python
   installer, select **Add python.exe to PATH**.
3. Open the extracted project folder.
4. Double-click **`setup_windows.bat`**. Windows may display a protection warning because
   this is a new unsigned script. If it does, choose **More info**, verify the filename,
   and select **Run anyway**.
5. Wait until the window says **Setup completed successfully**, then press any key. An
   internet connection is required during this first setup.

### Open the scanner

After setup, double-click **`run_windows.bat`** whenever you want to use the program.

If a black terminal window remains open while the scanner is running, leave it open. It
will close when the application closes unless an error needs to be shown.

### Fixing `No module named document_scanner`

If you previously saw this message:

```text
ModuleNotFoundError: No module named 'document_scanner'
```

replace your old project folder with a fresh download of the complete repository, extract
the ZIP, and run **`setup_windows.bat`** again. Keep `run_windows.bat`, `run_app.py`,
`requirements.txt`, and the entire `src` folder together. Do not copy only the two `.bat`
files to the Desktop. The launcher now resolves `src` from its own location, including
folders whose names contain spaces or which are stored under OneDrive.

If the scanner reports that `config\keywords.json` is missing, your earlier download did
not include the keyword file. The current version has a bundled backup keyword list. Replace
the old folder with the complete updated repository and run `setup_windows.bat` again.

### Command-line alternative

Developers can instead create a virtual environment and install the package manually:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e .
wayfinding-scanner
```

## Using the application

1. Click **Select PDF** for one searchable specification PDF, or **Select Folder** to scan
   every PDF in a folder and its subfolders.
2. Click **Scan Documents**.
3. Review and filter the findings in the results table.
4. Click **Export CSV** and open the output in Excel.
5. Click **Export AI Package** to create a local JSON evidence file for a future AI
   summarization step. This button does not upload or send your documents anywhere.
6. For drawing pages with arrows and callouts, click **Export Visual Pages** and enter the
   important page numbers, such as `17`. The app renders those PDF pages as PNG images.
7. Without an API key, click **Export ChatGPT Package**. Upload the JSON evidence file,
   companion prompt file, visual PNG pages, and visual manifest to ChatGPT. Ask it to
   return/download JSON only, then click **Import ChatGPT JSON**. The desktop program validates
   the result and creates the CSV with the same columns every time.
8. With an API key, click **Create AI Summary** to perform the text-evidence workflow
   automatically.

The CSV is a traceable search/audit report, not the final component schedule. The AI summary
uses one clear **Component** column, omits Drawing Number, Option, and Material Role, combines
all color information into one **Color** cell, and creates a separate row for each source page.
See [`AI_WORKFLOW.md`](AI_WORKFLOW.md) for the simplified schedule fields and rules.

## Consistent ChatGPT Plus workflow without API

Do not ask consumer ChatGPT to create the Excel workbook. Conversational workbook generation
can vary between runs. Instead:

1. Scan the PDF.
2. Click **Export ChatGPT Package**.
3. If the PDF contains drawing callouts, click **Export Visual Pages**. Enter only the relevant
   pages (for example `17`) to avoid uploading unnecessary pages.
4. Upload the generated `.json`, `-prompt.txt`, selected PNGs, and
   `visual-pages-manifest.json` to ChatGPT.
5. Tell ChatGPT to follow the prompt, inspect the PNG arrows/leader lines, and provide a
   downloadable JSON file only.
6. Click **Import ChatGPT JSON** and select that downloaded file.
7. The application rejects changed columns, unknown evidence IDs, and cross-page evidence.
8. The application—not ChatGPT—creates the final CSV with the fixed column order.

This makes the spreadsheet format deterministic even though the AI wording and interpretation
may still require human review.

## OpenAI AI summary setup

The recommended default model is `gpt-5.5` with low reasoning effort. It is selected for
structured extraction quality; the model field remains editable so your company's API
administrator can require another permitted model.

Important: ChatGPT subscriptions and OpenAI API usage are separate. Your company must have
an OpenAI API organization/project with API billing enabled. Ask the project owner to invite
you and give you permission to create your own project-scoped key. Do not share one personal
key across employees and never put a key in this repository.

Create a key at <https://platform.openai.com/api-keys>. For safer repeated use, set it as the
Windows user environment variable `OPENAI_API_KEY`; otherwise the app will request it in a
password field for each run and keep it only in memory.

When you click **Create AI Summary**, the app:

1. Shows the model name.
2. Asks for confirmation before sending data.
3. Sends extracted evidence passages, not the complete PDF.
4. Requests strict structured output.
5. Rejects evidence citations that do not exist in the scan.
6. Saves an Excel-compatible summary CSV and a structured JSON copy.

Review every generated result against its evidence IDs before using it for design,
procurement, or fabrication.

The output columns are:

| Column | Purpose |
| --- | --- |
| Document | Source PDF filename |
| Page | One-based PDF page number |
| Category | Materials, finishes, thickness, anti-graffiti, or colors |
| Component | Detected panel or sign component, when available |
| Material | Related material term found in the surrounding context |
| Finish | Related finish term found in the surrounding context |
| Thickness | Possible material, film, or coating thickness |
| Anti-graffiti | Related protection term |
| Matched term | Term that caused the finding |
| Source text | Original sentence or clause for verification |
| Review status | Starts as `Unreviewed` |

## Customizing vocabulary

The application includes a built-in keyword list, so it can scan even if the optional
`config` folder is missing. To customize the source-tree version, edit
[`config/keywords.json`](config/keywords.json) in a text editor. Terms are grouped by
category and matching is case-insensitive. The application accepts spaces or hyphens
between words, so a configured term such as `anti graffiti` can also match hyphenated text.

Keep the JSON punctuation intact. For example:

```json
{
  "materials": ["aluminum", "stainless steel"],
  "finishes": ["powder coated", "anodized"]
}
```

## Current limitations

- Only PDFs with searchable text are supported. Image-only scans are reported as likely
  OCR candidates but are not OCR-processed yet.
- The text scanner cannot understand arrows or leader lines. **Export Visual Pages** renders
  selected pages for a vision-capable ChatGPT conversation, which can use the drawing layout
  to improve component assignment.
- Visual AI can still misread crossed, faint, or crowded leader lines. Component-to-material
  associations must be checked against the exported page image.
- AI interpretation, PDF highlighting, editable review status, and Excel `.xlsx` formatting
  are planned later rather than included in this baseline.

## Development

Install development dependencies and run the checks:

```powershell
python -m pip install -r requirements-dev.txt
pytest
ruff check .
```
