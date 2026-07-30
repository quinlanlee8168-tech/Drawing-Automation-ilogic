import os
from collections import defaultdict

import fitz  # PyMuPDF
import pandas as pd
from PyPDF2 import PdfMerger

# -----------------------
# 1. CONFIGURE PATHS
# -----------------------
excel_file = r"C:\Users\Lee\OneDrive - Futuresystems\KANSAS CITY\KANSAS CITY SIGNAGE S1\INVENTOR DRAWINGS\PDF_OUTPUT\BOM.xlsx"
pdf_folder = r"C:\Users\Lee\OneDrive - Futuresystems\KANSAS CITY\KANSAS CITY SIGNAGE S1\INVENTOR DRAWINGS\PDF_OUTPUT"
output_file = r"C:\Users\Lee\OneDrive - Futuresystems\KANSAS CITY\KANSAS CITY SIGNAGE S1\INVENTOR DRAWINGS\PDF_OUTPUT\Combined_BOM_Recursive.pdf"

# Top-level assembly to expand recursively (master BOM item)
master_code = "FSI-020-00-001"

# Set True if you want to include only leaves (children with no children)
# Set False to include every node in traversal order.
merge_leaf_parts_only = False

# -----------------------
# 2. READ BOM AS PARENT -> CHILD RELATIONSHIPS
# -----------------------
# Expected columns in BOM:
# - PARENT DRAWING NUMBER
# - DRAWING NUMBER
# Where each row means: parent contains child.

df = pd.read_excel(
    excel_file,
    usecols=["PARENT DRAWING NUMBER", "DRAWING NUMBER"],
)

# Normalize values: remove whitespace and keep as string
for col in ["PARENT DRAWING NUMBER", "DRAWING NUMBER"]:
    df[col] = (
        df[col]
        .fillna("")
        .astype(str)
        .str.replace(r"\s+", "", regex=True)
    )

# Build graph preserving BOM row order
children_by_parent = defaultdict(list)
for _, row in df.iterrows():
    parent = row["PARENT DRAWING NUMBER"]
    child = row["DRAWING NUMBER"]
    if child:
        children_by_parent[parent].append(child)


def expand_bom_depth_first(root_code: str):
    """
    Return parts in depth-first BOM order, including root and descendants.
    Duplicate parts are de-duplicated while preserving first appearance order.
    """
    ordered = []
    seen = set()
    stack = [root_code]

    while stack:
        node = stack.pop()
        if node in seen:
            continue
        seen.add(node)
        ordered.append(node)

        # Reverse when pushing so traversal follows Excel row order.
        children = children_by_parent.get(node, [])
        for child in reversed(children):
            stack.append(child)

    return ordered


all_parts = expand_bom_depth_first(master_code)

if merge_leaf_parts_only:
    leaf_parts = [p for p in all_parts if len(children_by_parent.get(p, [])) == 0]
    ordered_parts = leaf_parts
else:
    ordered_parts = all_parts

print(f"Master: {master_code}")
print(f"Expanded to {len(all_parts)} unique BOM items.")
print(f"Merging {len(ordered_parts)} items (leaf_only={merge_leaf_parts_only}).")

# -----------------------
# 3. SCAN PDFs FOR DRAWING NUMBERS (BOTTOM-RIGHT CORNER)
# -----------------------
pdf_mapping = {}  # Maps part_code -> pdf_path

pdf_files = [f for f in os.listdir(pdf_folder) if f.lower().endswith(".pdf")]
print(f"Found {len(pdf_files)} PDF files in folder.")

for pdf_file in pdf_files:
    pdf_path = os.path.join(pdf_folder, pdf_file)
    doc = fitz.open(pdf_path)

    try:
        found_codes = set()
        for page in doc:
            rect_width = 400
            rect_height = 150
            rect = fitz.Rect(
                page.rect.width - rect_width,
                page.rect.height - rect_height,
                page.rect.width,
                page.rect.height,
            )
            text = page.get_textbox(rect).strip()

            # Only test against parts we actually plan to merge.
            for code in ordered_parts:
                if code in text:
                    found_codes.add(code)

        for code in found_codes:
            # First hit wins; helps avoid accidental remaps.
            pdf_mapping.setdefault(code, pdf_path)
    finally:
        doc.close()

print(f"Matched {len(pdf_mapping)} PDFs to BOM items.")

# -----------------------
# 4. MERGE PDFs IN RECURSIVE BOM ORDER
# -----------------------
merger = PdfMerger()
missing = []

for code in ordered_parts:
    pdf = pdf_mapping.get(code)
    if pdf:
        merger.append(pdf)
    else:
        missing.append(code)

merger.write(output_file)
merger.close()

print(f"Merged PDF created: {output_file}")
if missing:
    print("Missing PDFs for:")
    for code in missing:
        print(f"  - {code}")
