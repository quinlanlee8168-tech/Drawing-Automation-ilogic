# AI workflow and simple summary fields

The scanner finds traceable evidence, the AI organizes it, and a human verifies the result
against the cited page. The findings CSV is an audit/search report, not the final schedule.

## Consistent workflow with ChatGPT Plus

ChatGPT should not create the Excel file directly. Its workbook layout can vary between
conversations. Use this round trip instead:

1. Export the ChatGPT package from the scanner.
2. For drawing sheets, use **Export Visual Pages** and enter the relevant PDF page numbers.
3. Upload the evidence JSON, companion prompt text, exported PNGs, and visual manifest.
4. Ask ChatGPT to inspect arrows/leader lines and return JSON only.
5. Download the JSON response.
6. Import that JSON into the scanner.
7. Let the scanner validate it and create the final CSV.

The scanner controls the spreadsheet columns, while ChatGPT only supplies values for the
fixed schema.

## Drawing callouts and page images

Normal PDF text extraction records words but loses the meaning of the blue arrows and leader
lines connecting those words to the kiosk. The visual export preserves the complete page
layout. ChatGPT can inspect each PNG to associate a note such as `Panel D - 5mm steel side
panels` with the side panel targeted by its leader line.

Use the visual page only to establish spatial relationships and to read visible labels. Use
the evidence package's `source_text` as the authority for specification wording. If a line is
crossed, faint, or unclear, the AI must leave the evidence unassigned or report a conflict
instead of guessing.

## Final schedule columns

| Field | Meaning |
| --- | --- |
| Sign Type | Sign family, such as S1-A, when stated |
| Component | One readable description, such as `Panel D - Side panels` |
| Material | What the component is made from, such as steel, glass, or vinyl |
| Grade / Alloy / Temper | More specific material designation, when stated |
| Material Thickness | Thickness of the material—not overall geometry |
| Finish System | Painted, powder coated, anodized, digitally imaged, etc. |
| Color | One cell containing the name and all stated codes |
| Coating / Film Thickness | Thickness of an applied coating or film |
| Surface / Application | Face, edges, second surface, exterior, etc. |
| Anti-Graffiti Requirement | Film/coating requirement or `Not specified` |
| Manufacturer / Product | Proprietary product information, when stated |
| Standards | ASTM, ANSI, UL, and similar references |
| Document | Exactly one source document per row |
| Page | Exactly one source page per row |
| Evidence IDs | Evidence from that same document and page |
| Conflicts / Missing Information | Items requiring human review |
| Confidence | High, medium, or low |

## Removed terminology

The final report intentionally omits:

- Drawing Number
- Option
- Component ID
- Component Name
- Component Type
- Material Role
- Separate Color Name and Color Code columns

Component ID/Name/Type are combined into **Component**. Material Role was removed because it
made the schedule harder to read. Finish alternatives may still appear as separate rows with
different Finish System values, but there is no Option column.

## Color rule

Put all color information in one cell. For example:

```text
Fountain Blue / Pantone 2193 / HEX 318CCC / RAL 5015 Sky Blue / CMYK C76 M35 Y0 K0
```

Do not split that information across several columns.

## Page rule

Never combine page numbers in one row. If the same component appears on pages 17 and 19,
create separate rows so each conclusion can be checked against one page.

## AI rules

- Never invent an unstated value.
- Use `Not specified` for missing information.
- Keep alternative finishes separate by creating separate rows when necessary.
- Produce one row per component, material, distinct finish, document, and page.
- Never place multiple page numbers in one row.
- Treat dimensions as geometry unless the text explicitly identifies thickness.
- Distinguish material thickness from coating or film thickness.
- Combine color names and codes into one Color cell.
- Use source text as the authority when candidate fields appear incorrect.
- Cite evidence IDs from the same document and page as the row.
- Report conflicts instead of silently choosing one value.
