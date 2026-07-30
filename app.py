"""Desktop interface for Excel cleanup and modified-date archiving."""

from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from file_organizer import (
    ArchiveItem,
    ArchiveResult,
    MoveItem,
    ScanResult,
    execute_archive_moves,
    execute_moves,
    file_type_for_path,
    remove_empty_folders,
    scan_files_for_archive,
    scan_unmatched_files,
    select_move_items_by_type,
    summarize_file_types,
)


class FileOrganizerApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Drawing File Organizer")
        self.geometry("1040x760")
        self.minsize(840, 600)

        self.source_var = tk.StringVar()
        self.workbook_var = tk.StringVar()
        self.destination_var = tk.StringVar()
        self.status_var = tk.StringVar(
            value="Choose the source folder, Excel file, and destination, then scan all files."
        )
        self.scan_result: ScanResult | None = None
        self.file_types: tuple[str, ...] = ()
        self.busy = False

        self.archive_source_var = tk.StringVar()
        self.archive_destination_var = tk.StringVar()
        self.archive_status_var = tk.StringVar(
            value="Choose a source and archive folder, then compare file versions."
        )
        self.archive_result: ArchiveResult | None = None
        self.archive_busy = False
        self._build_ui()

    def _build_ui(self) -> None:
        notebook = ttk.Notebook(self)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        cleanup_tab = ttk.Frame(notebook, padding=12)
        archive_tab = ttk.Frame(notebook, padding=12)
        notebook.add(cleanup_tab, text="Excel unmatched-file cleanup")
        notebook.add(archive_tab, text="Archive older versions")
        self._build_cleanup_tab(cleanup_tab)
        self._build_archive_tab(archive_tab)

    def _build_cleanup_tab(self, frame: ttk.Frame) -> None:
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(7, weight=1)
        self._path_row(
            frame, 0, "Folders containing files to clean up", self.source_var,
            self._choose_source,
        )
        self._path_row(
            frame, 1, "Excel containing drawing/parts path", self.workbook_var,
            self._choose_workbook,
        )
        self._path_row(
            frame, 2, "Select a destination folder for unmatched files",
            self.destination_var, self._choose_destination,
        )

        note = (
            "The scan discovers every unmatched file type. Select one or more types "
            "to move all matching files. Old Version folders are skipped."
        )
        ttk.Label(frame, text=note, wraplength=960).grid(
            row=3, column=0, columnspan=3, sticky="w", pady=(8, 10)
        )

        self.preview_button = ttk.Button(
            frame, text="1. Scan all unmatched files", command=self._preview
        )
        self.preview_button.grid(row=4, column=0, columnspan=3, sticky="w", pady=(0, 8))

        type_frame = ttk.LabelFrame(frame, text="File types found — select one or more", padding=8)
        type_frame.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(0, 8))
        type_frame.columnconfigure(0, weight=1)
        self.type_list = tk.Listbox(
            type_frame, height=5, selectmode=tk.EXTENDED, exportselection=False, state=tk.DISABLED
        )
        self.type_list.grid(row=0, column=0, rowspan=3, sticky="ew")
        self.type_list.bind("<<ListboxSelect>>", self._type_selection_changed)
        scrollbar = ttk.Scrollbar(type_frame, orient=tk.VERTICAL, command=self.type_list.yview)
        scrollbar.grid(row=0, column=1, rowspan=3, sticky="ns")
        self.type_list.configure(yscrollcommand=scrollbar.set)
        self.select_all_types_button = ttk.Button(
            type_frame, text="Select all types", command=self._select_all_types, state=tk.DISABLED
        )
        self.select_all_types_button.grid(row=0, column=2, padx=(10, 0), sticky="ew")
        self.clear_types_button = ttk.Button(
            type_frame, text="Clear type selection", command=self._clear_type_selection,
            state=tk.DISABLED,
        )
        self.clear_types_button.grid(row=1, column=2, padx=(10, 0), pady=4, sticky="ew")
        self.move_button = ttk.Button(
            type_frame, text="2. Move selected types", command=self._move, state=tk.DISABLED
        )
        self.move_button.grid(row=2, column=2, padx=(10, 0), sticky="ew")

        self.tree = self._result_tree(frame, row=7, columns=("type", "source", "destination"))
        self.tree.heading("type", text="Type")
        self.tree.heading("source", text="Unmatched file")
        self.tree.heading("destination", text="New location")
        self.tree.column("type", width=90, minwidth=70, stretch=False)
        self.tree.column("source", width=445)
        self.tree.column("destination", width=445)
        ttk.Label(frame, textvariable=self.status_var, wraplength=960).grid(
            row=9, column=0, columnspan=3, sticky="w", pady=(10, 0)
        )

    def _build_archive_tab(self, frame: ttk.Frame) -> None:
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(5, weight=1)
        self._path_row(
            frame, 0, "Folder containing files to archive", self.archive_source_var,
            self._choose_archive_source,
        )
        self._path_row(
            frame, 1, "Choose a destination folder for archive files", self.archive_destination_var,
            self._choose_archive_destination,
        )

        note = (
            "Groups related files by part number and file type, then compares their system "
            "Date modified values. If no recognized part number is present, the first 15 "
            "filename characters are used. File types are compared independently."
        )
        ttk.Label(frame, text=note, wraplength=960).grid(
            row=2, column=0, columnspan=3, sticky="w", pady=(8, 10)
        )

        buttons = ttk.Frame(frame)
        buttons.grid(row=3, column=0, columnspan=3, sticky="w", pady=(0, 8))
        self.archive_preview_button = ttk.Button(
            buttons, text="1. Compare file versions", command=self._preview_archive
        )
        self.archive_preview_button.pack(side=tk.LEFT)
        self.archive_move_button = ttk.Button(
            buttons, text="2. Archive older versions", command=self._archive_files,
            state=tk.DISABLED,
        )
        self.archive_move_button.pack(side=tk.LEFT, padx=(8, 0))

        summary_frame = ttk.LabelFrame(frame, text="Version comparison preview", padding=8)
        summary_frame.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(0, 8))
        self.archive_summary_var = tk.StringVar(value="No version comparison has been run.")
        ttk.Label(summary_frame, textvariable=self.archive_summary_var, wraplength=930).pack(
            anchor="w"
        )

        self.archive_tree = self._result_tree(
            frame,
            row=5,
            columns=("group", "modified", "latest", "type", "source", "destination"),
        )
        self.archive_tree.heading("group", text="Comparison key")
        self.archive_tree.heading("modified", text="Older Date modified")
        self.archive_tree.heading("latest", text="Newest Date modified")
        self.archive_tree.heading("type", text="Type")
        self.archive_tree.heading("source", text="Older file")
        self.archive_tree.heading("destination", text="Archive location")
        self.archive_tree.column("group", width=155, minwidth=130, stretch=False)
        self.archive_tree.column("modified", width=155, minwidth=140, stretch=False)
        self.archive_tree.column("latest", width=155, minwidth=140, stretch=False)
        self.archive_tree.column("type", width=75, minwidth=60, stretch=False)
        self.archive_tree.column("source", width=300)
        self.archive_tree.column("destination", width=300)
        ttk.Label(frame, textvariable=self.archive_status_var, wraplength=960).grid(
            row=7, column=0, columnspan=3, sticky="w", pady=(10, 0)
        )

    def _result_tree(self, frame: ttk.Frame, row: int, columns: tuple[str, ...]) -> ttk.Treeview:
        tree = ttk.Treeview(frame, columns=columns, show="headings", selectmode="none")
        vertical = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=tree.yview)
        horizontal = ttk.Scrollbar(frame, orient=tk.HORIZONTAL, command=tree.xview)
        tree.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        tree.grid(row=row, column=0, columnspan=2, sticky="nsew")
        vertical.grid(row=row, column=2, sticky="ns")
        horizontal.grid(row=row + 1, column=0, columnspan=2, sticky="ew")
        return tree

    def _path_row(self, parent, row, label, variable, command) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 10), pady=4)
        ttk.Entry(parent, textvariable=variable).grid(row=row, column=1, sticky="ew", pady=4)
        ttk.Button(parent, text="Browse…", command=command).grid(
            row=row, column=2, padx=(10, 0), pady=4
        )

    def _choose_source(self) -> None:
        selected = filedialog.askdirectory(title="Folders containing files to clean up")
        if selected:
            self.source_var.set(selected)

    def _choose_workbook(self) -> None:
        selected = filedialog.askopenfilename(
            title="Select excel workbook containing part/drawing path",
            filetypes=[("Excel workbooks", "*.xlsx *.xlsm"), ("All files", "*.*")],
        )
        if selected:
            self.workbook_var.set(selected)

    def _choose_destination(self) -> None:
        selected = filedialog.askdirectory(title="Choose destination folder for unmatched files")
        if selected:
            self.destination_var.set(selected)

    def _choose_archive_source(self) -> None:
        selected = filedialog.askdirectory(title="Choose folder containing files to archive")
        if selected:
            self.archive_source_var.set(selected)

    def _choose_archive_destination(self) -> None:
        selected = filedialog.askdirectory(title="Choose archive destination folder")
        if selected:
            self.archive_destination_var.set(selected)

    @staticmethod
    def _type_label(file_type: str) -> str:
        return file_type or "(no extension)"

    @staticmethod
    def _clear_tree(tree: ttk.Treeview) -> None:
        for row_id in tree.get_children():
            tree.delete(row_id)

    # Excel cleanup workflow
    def _clear_results(self) -> None:
        self.scan_result = None
        self.file_types = ()
        self.type_list.configure(state=tk.NORMAL)
        self.type_list.delete(0, tk.END)
        self.type_list.configure(state=tk.DISABLED)
        self._clear_tree(self.tree)

    def _selected_types(self) -> tuple[str, ...]:
        return tuple(self.file_types[index] for index in self.type_list.curselection())

    def _selected_items(self) -> tuple[MoveItem, ...]:
        if not self.scan_result:
            return ()
        return select_move_items_by_type(self.scan_result.unmatched_files, self._selected_types())

    def _show_items(self, items: tuple[MoveItem, ...]) -> None:
        self._clear_tree(self.tree)
        for item in items:
            self.tree.insert("", tk.END, values=(
                self._type_label(file_type_for_path(item.source)),
                str(item.source), str(item.destination),
            ))

    def _type_selection_changed(self, _event=None) -> None:
        if self.busy or not self.scan_result:
            return
        selected_types = self._selected_types()
        selected_items = self._selected_items()
        if selected_types:
            self._show_items(selected_items)
            names = ", ".join(self._type_label(value) for value in selected_types)
            self.status_var.set(
                f"Selected {len(selected_items)} file(s) in {len(selected_types)} type(s): {names}."
            )
        else:
            self._show_items(self.scan_result.unmatched_files)
            self.status_var.set(
                f"Found {len(self.scan_result.unmatched_files)} unmatched file(s). "
                "Select one or more file types to move."
            )
        self._set_busy(False)

    def _select_all_types(self) -> None:
        self.type_list.selection_set(0, tk.END)
        self._type_selection_changed()

    def _clear_type_selection(self) -> None:
        self.type_list.selection_clear(0, tk.END)
        self._type_selection_changed()

    def _set_busy(self, busy: bool) -> None:
        self.busy = busy
        has_types = bool(self.file_types)
        has_selection = bool(self._selected_types())
        self.preview_button.configure(state=tk.DISABLED if busy else tk.NORMAL)
        self.type_list.configure(state=tk.DISABLED if busy or not has_types else tk.NORMAL)
        self.select_all_types_button.configure(
            state=tk.NORMAL if has_types and not busy else tk.DISABLED
        )
        self.clear_types_button.configure(
            state=tk.NORMAL if has_selection and not busy else tk.DISABLED
        )
        self.move_button.configure(state=tk.NORMAL if has_selection and not busy else tk.DISABLED)

    def _preview(self) -> None:
        self._clear_results()
        self._set_busy(True)
        self.status_var.set("Reading workbook and scanning every file type…")

        def work() -> None:
            try:
                result = scan_unmatched_files(
                    Path(self.source_var.get()), Path(self.workbook_var.get()),
                    Path(self.destination_var.get()),
                )
            except Exception as exc:
                self.after(0, lambda: self._show_error("Scan failed", exc))
                return
            self.after(0, lambda: self._show_preview(result))

        threading.Thread(target=work, daemon=True).start()

    def _show_preview(self, result: ScanResult) -> None:
        self.scan_result = result
        summaries = summarize_file_types(result.unmatched_files)
        self.file_types = tuple(file_type for file_type, _count in summaries)
        self.type_list.configure(state=tk.NORMAL)
        for file_type, count in summaries:
            noun = "file" if count == 1 else "files"
            self.type_list.insert(tk.END, f"{self._type_label(file_type)} — {count} {noun}")
        self._show_items(result.unmatched_files)
        self.status_var.set(
            f"Found {len(result.unmatched_files)} unmatched file(s) across {len(summaries)} "
            f"file type(s). Skipped {len(result.skipped_old_version_files)} file(s) in "
            "old-version folders. Select one or more file types to move."
        )
        self._set_busy(False)

    def _move(self) -> None:
        selected_types = self._selected_types()
        items = self._selected_items()
        if not selected_types or not items:
            messagebox.showinfo("Nothing selected", "Select one or more file types first.")
            return
        names = ", ".join(self._type_label(value) for value in selected_types)
        if not messagebox.askyesno(
            "Confirm move",
            f"Move {len(items)} file(s) of these types?\n\n{names}\n\n"
            "Existing destination files will not be overwritten.",
        ):
            return
        source = Path(self.source_var.get())
        destination = Path(self.destination_var.get())
        self._set_busy(True)
        self.status_var.set(f"Moving {len(items)} file(s) from the selected type(s)…")

        def work() -> None:
            try:
                completed = execute_moves(items)
                removed = remove_empty_folders(source, excluded_folders=(destination,))
            except Exception as exc:
                self.after(0, lambda: self._show_error("Move failed", exc))
                return
            self.after(0, lambda: self._show_complete(len(completed), len(removed)))

        threading.Thread(target=work, daemon=True).start()

    def _show_complete(self, count: int, removed_count: int) -> None:
        self._clear_results()
        self.status_var.set(
            f"Finished moving {count} file(s) and removed {removed_count} empty folder(s)."
        )
        self._set_busy(False)
        messagebox.showinfo(
            "Move complete",
            f"Moved {count} file(s).\nRemoved {removed_count} empty source folder(s).",
        )

    def _show_error(self, title: str, error: Exception) -> None:
        self._clear_results()
        self._set_busy(False)
        self.status_var.set(str(error))
        messagebox.showerror(title, str(error))

    # Older-version archive workflow
    def _clear_archive_results(self) -> None:
        self.archive_result = None
        self._clear_tree(self.archive_tree)
        self.archive_summary_var.set("No version comparison has been run.")

    def _set_archive_busy(self, busy: bool) -> None:
        self.archive_busy = busy
        self.archive_preview_button.configure(state=tk.DISABLED if busy else tk.NORMAL)
        has_files = bool(self.archive_result and self.archive_result.archive_files)
        self.archive_move_button.configure(
            state=tk.NORMAL if has_files and not busy else tk.DISABLED
        )

    def _preview_archive(self) -> None:
        self._clear_archive_results()
        if not self.archive_source_var.get().strip():
            self._show_archive_error(
                "Missing source folder", ValueError("Choose a folder containing files to archive.")
            )
            return
        if not self.archive_destination_var.get().strip():
            self._show_archive_error(
                "Missing archive folder", ValueError("Choose an archive destination folder.")
            )
            return
        self._set_archive_busy(True)
        self.archive_status_var.set(
            "Grouping filenames and comparing filesystem Date modified values…"
        )

        def work() -> None:
            try:
                result = scan_files_for_archive(
                    Path(self.archive_source_var.get()),
                    Path(self.archive_destination_var.get()),
                )
            except Exception as exc:
                self.after(0, lambda: self._show_archive_error("Version scan failed", exc))
                return
            self.after(0, lambda: self._show_archive_preview(result))

        threading.Thread(target=work, daemon=True).start()

    def _show_archive_preview(self, result: ArchiveResult) -> None:
        self.archive_result = result
        for item in result.archive_files:
            self.archive_tree.insert("", tk.END, values=(
                item.group_key,
                item.modified_at.astimezone().strftime("%Y-%m-%d %I:%M %p"),
                item.latest_modified_at.astimezone().strftime("%Y-%m-%d %I:%M %p"),
                self._type_label(file_type_for_path(item.source)),
                str(item.source),
                str(item.destination),
            ))
        self.archive_summary_var.set(
            f"Compared {result.duplicate_group_count} group(s) containing multiple files. "
            f"Keeping {len(result.latest_files)} newest or tied-newest file(s); "
            f"{len(result.archive_files)} strictly older file(s) are ready to archive. "
            f"Left {len(result.ungrouped_files)} file(s) with no matching version untouched."
        )
        self.archive_status_var.set(
            f"Previewed {len(result.archive_files)} older version(s). Skipped "
            f"{len(result.skipped_old_version_files)} file(s) in Old Version folders."
        )
        self._set_archive_busy(False)

    def _archive_files(self) -> None:
        if not self.archive_result or not self.archive_result.archive_files:
            messagebox.showinfo(
                "Nothing to archive", "Compare file versions first; no older versions are selected."
            )
            return
        items = self.archive_result.archive_files
        if not messagebox.askyesno(
            "Confirm archive",
            f"Archive all {len(items)} older version(s)?\n\n"
            "Files were grouped by FSI code (or the first 15 filename characters) and "
            "file type. The newest Date modified file of each type will remain.\n\n"
            "Existing archive files will not be overwritten.",
        ):
            return
        source = Path(self.archive_source_var.get())
        destination = Path(self.archive_destination_var.get())
        self._set_archive_busy(True)
        self.archive_status_var.set(f"Archiving {len(items)} older version(s)…")

        def work() -> None:
            try:
                completed = execute_archive_moves(items)
                removed = remove_empty_folders(source, excluded_folders=(destination,))
            except Exception as exc:
                self.after(0, lambda: self._show_archive_error("Archive failed", exc))
                return
            self.after(0, lambda: self._show_archive_complete(len(completed), len(removed)))

        threading.Thread(target=work, daemon=True).start()

    def _show_archive_complete(self, count: int, removed_count: int) -> None:
        self._clear_archive_results()
        self.archive_status_var.set(
            f"Archived {count} older version(s) and removed {removed_count} empty folder(s)."
        )
        self._set_archive_busy(False)
        messagebox.showinfo(
            "Archive complete",
            f"Archived {count} older version(s).\n"
            f"Removed {removed_count} empty source folder(s).",
        )

    def _show_archive_error(self, title: str, error: Exception) -> None:
        self._clear_archive_results()
        self._set_archive_busy(False)
        self.archive_status_var.set(str(error))
        messagebox.showerror(title, str(error))


if __name__ == "__main__":
    FileOrganizerApp().mainloop()
