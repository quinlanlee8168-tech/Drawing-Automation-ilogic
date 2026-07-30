#!/usr/bin/env python3
"""Simple click-to-run GUI for replace_pdf_pages_by_fsi.py workflow."""

from __future__ import annotations

import subprocess
import sys
from datetime import date
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox


def pick_folder(title: str) -> str:
    return filedialog.askdirectory(title=title)


def save_file(title: str, defaultextension: str, filetypes: list[tuple[str, str]]) -> str:
    return filedialog.asksaveasfilename(title=title, defaultextension=defaultextension, filetypes=filetypes)


def ask_yes_no(title: str, message: str) -> bool:
    return messagebox.askyesno(title, message)


def main() -> int:
    root = tk.Tk()
    root.withdraw()

    batch_mode = ask_yes_no("PDF Package Replacer", "Do you want to process multiple package PDFs at once?")

    replacements = pick_folder("Select replacement PDFs folder")
    if not replacements:
        return 1

    cmd = [sys.executable, str(Path(__file__).with_name("replace_pdf_pages_by_fsi.py")), "--replacements", replacements]

    if batch_mode:
        messagebox.showinfo("PDF Package Replacer", "Select package folder containing all package PDFs, then select output folder.")
        package_dir = pick_folder("Select folder containing package PDFs")
        if not package_dir:
            return 1

        output_dir = pick_folder("Select output folder for replaced package PDFs")
        if not output_dir:
            return 1

        cmd.extend(["--package-dir", package_dir, "--output", output_dir])
    else:
        messagebox.showinfo("PDF Package Replacer", "Select one package PDF, then output PDF and summary paths.")
        package_file = filedialog.askopenfilename(title="Select PDF package to update", filetypes=[("PDF files", "*.pdf")])
        if not package_file:
            return 1

        today = date.today().isoformat()
        default_output = str(Path(package_file).with_name(f"{Path(package_file).stem} - {today}.pdf"))
        output_pdf = save_file("Save updated package PDF as", ".pdf", [("PDF files", "*.pdf")])
        if not output_pdf:
            output_pdf = default_output

        default_summary = str(Path(output_pdf).with_name(f"{Path(output_pdf).stem} - Summary.tsv"))
        output_summary = save_file("Save summary TSV as (optional)", ".tsv", [("TSV files", "*.tsv"), ("All files", "*.*")])
        if not output_summary:
            output_summary = default_summary

        cmd.extend(["--package", package_file, "--output", output_pdf, "--summary", output_summary])

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except Exception as exc:
        messagebox.showerror("Error", f"Failed to run replacement:\n{exc}")
        return 1

    if result.returncode != 0:
        messagebox.showerror("Replacement failed", f"Command failed with code {result.returncode}\n\n{result.stderr or result.stdout}")
        return result.returncode

    if batch_mode:
        messagebox.showinfo("Batch replacement complete", result.stdout.strip() or "Batch completed.")
    else:
        messagebox.showinfo("Replacement complete", f"Updated package written to:\n{output_pdf}\n\nSummary TSV written to:\n{output_summary}\n\n{result.stdout.strip()}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
