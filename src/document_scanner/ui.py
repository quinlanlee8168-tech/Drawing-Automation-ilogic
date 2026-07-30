import os
from pathlib import Path

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from document_scanner.ai_exporter import export_ai_json
from document_scanner.ai_summarizer import DEFAULT_MODEL, SummaryResult, summarize_findings
from document_scanner.config import load_keyword_groups
from document_scanner.exporter import HEADERS, export_csv
from document_scanner.manual_chatgpt import export_manual_prompt, load_chatgpt_summary
from document_scanner.models import Finding
from document_scanner.scanner import scan_path
from document_scanner.summary_exporter import export_summary_csv, export_summary_json
from document_scanner.visual_exporter import export_visual_pages, parse_page_selection


class ScanWorker(QThread):
    progress = Signal(int, int, str)
    completed = Signal(object, object)
    failed = Signal(str)

    def __init__(self, selected_path: Path) -> None:
        super().__init__()
        self.selected_path = selected_path

    def run(self) -> None:
        try:
            findings, warnings = scan_path(
                self.selected_path,
                load_keyword_groups(),
                lambda current, total, message: self.progress.emit(current, total, message),
            )
            self.completed.emit(findings, warnings)
        except Exception as error:
            self.failed.emit(str(error))


class SummaryWorker(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        findings: list[Finding],
        api_key: str,
        model: str,
    ) -> None:
        super().__init__()
        self.findings = findings
        self.api_key = api_key
        self.model = model

    def run(self) -> None:
        try:
            self.completed.emit(summarize_findings(self.findings, self.api_key, self.model))
        except Exception as error:
            self.failed.emit(str(error))
        finally:
            self.api_key = ""


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Wayfinding Document Scanner")
        self.resize(1400, 760)
        self.selected_path: Path | None = None
        self.findings: list[Finding] = []
        self.worker: ScanWorker | None = None
        self.summary_worker: SummaryWorker | None = None

        root = QWidget()
        layout = QVBoxLayout(root)

        controls = QHBoxLayout()
        self.path_label = QLabel("No PDF or folder selected")
        select_pdf = QPushButton("Select PDF")
        select_folder = QPushButton("Select Folder")
        self.scan_button = QPushButton("Scan Documents")
        self.export_button = QPushButton("Export CSV")
        self.ai_export_button = QPushButton("Export ChatGPT Package")
        self.visual_export_button = QPushButton("Export Visual Pages")
        self.import_summary_button = QPushButton("Import ChatGPT JSON")
        self.summarize_button = QPushButton("Create AI Summary")
        self.export_button.setEnabled(False)
        self.ai_export_button.setEnabled(False)
        self.visual_export_button.setEnabled(False)
        self.import_summary_button.setEnabled(False)
        self.summarize_button.setEnabled(False)

        select_pdf.clicked.connect(self.select_pdf)
        select_folder.clicked.connect(self.select_folder)
        self.scan_button.clicked.connect(self.start_scan)
        self.export_button.clicked.connect(self.export_results)
        self.ai_export_button.clicked.connect(self.export_ai_package)
        self.visual_export_button.clicked.connect(self.export_visual_page_images)
        self.import_summary_button.clicked.connect(self.import_chatgpt_summary)
        self.summarize_button.clicked.connect(self.create_ai_summary)
        self.scan_button.setEnabled(False)

        controls.addWidget(select_pdf)
        controls.addWidget(select_folder)
        controls.addWidget(self.path_label, 1)
        controls.addWidget(self.scan_button)
        controls.addWidget(self.export_button)
        controls.addWidget(self.ai_export_button)
        controls.addWidget(self.visual_export_button)
        controls.addWidget(self.import_summary_button)
        controls.addWidget(self.summarize_button)
        layout.addLayout(controls)

        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Category filter:"))
        self.category_filter = QComboBox()
        self.category_filter.addItem("All categories")
        self.category_filter.currentTextChanged.connect(self.populate_table)
        filter_row.addWidget(self.category_filter)
        filter_row.addStretch()
        self.result_count = QLabel("0 findings")
        filter_row.addWidget(self.result_count)
        layout.addLayout(filter_row)

        self.table = QTableWidget(0, len(HEADERS))
        self.table.setHorizontalHeaderLabels(HEADERS)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(9, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table, 1)

        self.status_label = QLabel("Ready")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        layout.addWidget(self.status_label)
        layout.addWidget(self.progress_bar)

        self.setCentralWidget(root)

    def select_pdf(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(self, "Select searchable PDF", "", "PDF (*.pdf)")
        if filename:
            self.set_selected_path(Path(filename))

    def select_folder(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Select folder containing PDFs")
        if directory:
            self.set_selected_path(Path(directory))

    def set_selected_path(self, path: Path) -> None:
        self.selected_path = path
        self.path_label.setText(str(path))
        self.scan_button.setEnabled(True)
        self.status_label.setText("Ready to scan")

    def start_scan(self) -> None:
        if self.selected_path is None:
            return
        self.scan_button.setEnabled(False)
        self.export_button.setEnabled(False)
        self.ai_export_button.setEnabled(False)
        self.visual_export_button.setEnabled(False)
        self.import_summary_button.setEnabled(False)
        self.summarize_button.setEnabled(False)
        self.progress_bar.setRange(0, 0)
        self.status_label.setText("Starting scan…")
        self.worker = ScanWorker(self.selected_path)
        self.worker.progress.connect(self.update_progress)
        self.worker.completed.connect(self.scan_completed)
        self.worker.failed.connect(self.scan_failed)
        self.worker.start()

    def update_progress(self, current: int, total: int, message: str) -> None:
        self.progress_bar.setRange(0, max(total, 1))
        self.progress_bar.setValue(current)
        self.status_label.setText(message)

    def scan_completed(self, findings: list[Finding], warnings: list[str]) -> None:
        self.findings = findings
        categories = sorted({finding.category for finding in findings})
        self.category_filter.blockSignals(True)
        self.category_filter.clear()
        self.category_filter.addItem("All categories")
        self.category_filter.addItems(categories)
        self.category_filter.blockSignals(False)
        self.populate_table()
        self.scan_button.setEnabled(True)
        self.export_button.setEnabled(bool(findings))
        self.ai_export_button.setEnabled(bool(findings))
        self.visual_export_button.setEnabled(bool(findings))
        self.import_summary_button.setEnabled(bool(findings))
        self.summarize_button.setEnabled(bool(findings))
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(1)
        self.status_label.setText(f"Scan complete: {len(findings)} findings")
        if warnings:
            QMessageBox.warning(self, "Scan warnings", "\n".join(warnings))

    def scan_failed(self, message: str) -> None:
        self.scan_button.setEnabled(True)
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self.status_label.setText("Scan failed")
        QMessageBox.critical(self, "Scan failed", message)

    def populate_table(self) -> None:
        selected_category = self.category_filter.currentText()
        visible = [
            finding
            for finding in self.findings
            if selected_category == "All categories" or finding.category == selected_category
        ]
        self.table.setRowCount(len(visible))
        for row, finding in enumerate(visible):
            values = [
                finding.document,
                str(finding.page),
                finding.category,
                finding.component,
                finding.material,
                finding.finish,
                finding.thickness,
                finding.anti_graffiti,
                finding.matched_term,
                finding.source_text,
                finding.review_status,
            ]
            for column, value in enumerate(values):
                self.table.setItem(row, column, QTableWidgetItem(value))
        self.result_count.setText(f"{len(visible)} findings")

    def export_results(self) -> None:
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Export findings",
            "wayfinding-findings.csv",
            "CSV (*.csv)",
        )
        if not filename:
            return
        output_path = Path(filename)
        if output_path.suffix.casefold() != ".csv":
            output_path = output_path.with_suffix(".csv")
        export_csv(self.findings, output_path)
        QMessageBox.information(self, "Export complete", f"Saved results to:\n{output_path}")

    def export_ai_package(self) -> None:
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Export AI evidence package",
            "wayfinding-ai-package.json",
            "JSON (*.json)",
        )
        if not filename:
            return
        output_path = Path(filename)
        if output_path.suffix.casefold() != ".json":
            output_path = output_path.with_suffix(".json")
        export_ai_json(self.findings, output_path)
        prompt_path = output_path.with_name(f"{output_path.stem}-prompt.txt")
        export_manual_prompt(prompt_path)
        QMessageBox.information(
            self,
            "ChatGPT package exported",
            f"Upload both files to ChatGPT:\n{output_path}\n{prompt_path}\n\n"
            "Ask ChatGPT to follow the prompt and return a JSON file. Then use "
            "Import ChatGPT JSON. These files are created locally.",
        )

    def export_visual_page_images(self) -> None:
        if self.selected_path is None:
            return

        pages_text, accepted = QInputDialog.getText(
            self,
            "Choose drawing pages",
            "Enter PDF page numbers separated by commas (example: 17, 19).\n"
            "Leave blank to export every page that has a finding:",
        )
        if not accepted:
            return
        try:
            page_numbers = parse_page_selection(pages_text)
        except ValueError as error:
            QMessageBox.warning(self, "Invalid page numbers", str(error))
            return

        directory = QFileDialog.getExistingDirectory(
            self,
            "Select folder for visual page PNGs",
        )
        if not directory:
            return

        try:
            result = export_visual_pages(
                self.selected_path,
                self.findings,
                Path(directory),
                page_numbers,
            )
        except Exception as error:
            QMessageBox.critical(self, "Visual export failed", str(error))
            return

        warning_text = ""
        if result.warnings:
            warning_text = "\n\nWarnings:\n" + "\n".join(result.warnings)
        QMessageBox.information(
            self,
            "Visual pages exported",
            f"Exported {len(result.image_paths)} PNG page image(s).\n"
            f"Manifest:\n{result.manifest_path}\n\n"
            "Upload the PNGs with the ChatGPT evidence package and prompt. "
            "ChatGPT can then inspect arrows, leader lines, labels, and the drawing layout "
            f"before assigning evidence to components.{warning_text}",
        )

    def import_chatgpt_summary(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Select JSON returned by ChatGPT",
            "",
            "JSON (*.json);;Text (*.txt);;All files (*)",
        )
        if not filename:
            return
        try:
            summary = load_chatgpt_summary(Path(filename), self.findings)
        except Exception as error:
            QMessageBox.critical(self, "Invalid ChatGPT summary", str(error))
            return

        output_name, _ = QFileDialog.getSaveFileName(
            self,
            "Save consistent summary",
            "wayfinding-chatgpt-summary.csv",
            "CSV (*.csv)",
        )
        if not output_name:
            return
        csv_path = Path(output_name)
        if csv_path.suffix.casefold() != ".csv":
            csv_path = csv_path.with_suffix(".csv")
        json_path = csv_path.with_suffix(".json")
        export_summary_csv(summary, csv_path)
        export_summary_json(summary, json_path)
        QMessageBox.information(
            self,
            "ChatGPT summary imported",
            f"Saved the consistent spreadsheet:\n{csv_path}\n\n"
            f"Saved the validated JSON:\n{json_path}",
        )

    def create_ai_summary(self) -> None:
        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            api_key, accepted = QInputDialog.getText(
                self,
                "OpenAI API key",
                "Enter your own OpenAI API key. It is used for this request only and is not saved:",
                QLineEdit.EchoMode.Password,
            )
            if not accepted or not api_key.strip():
                return

        model, accepted = QInputDialog.getText(
            self,
            "OpenAI model",
            "Model:",
            text=DEFAULT_MODEL,
        )
        if not accepted:
            return

        confirmed = QMessageBox.question(
            self,
            "Send evidence to OpenAI?",
            "The extracted source passages—not the full PDF—will be sent to the OpenAI API.\n\n"
            "API usage is billed separately from ChatGPT subscriptions. Continue?",
        )
        if confirmed != QMessageBox.StandardButton.Yes:
            return

        self.summarize_button.setEnabled(False)
        self.status_label.setText(f"Creating AI summary with {model or DEFAULT_MODEL}…")
        self.progress_bar.setRange(0, 0)
        self.summary_worker = SummaryWorker(self.findings, api_key, model or DEFAULT_MODEL)
        api_key = ""
        self.summary_worker.completed.connect(self.ai_summary_completed)
        self.summary_worker.failed.connect(self.ai_summary_failed)
        self.summary_worker.start()

    def ai_summary_completed(self, summary: SummaryResult) -> None:
        self.summarize_button.setEnabled(True)
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(1)
        self.status_label.setText(f"AI summary complete: {len(summary.rows)} rows")
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Save AI component summary",
            "wayfinding-ai-summary.csv",
            "CSV (*.csv)",
        )
        if not filename:
            return
        csv_path = Path(filename)
        if csv_path.suffix.casefold() != ".csv":
            csv_path = csv_path.with_suffix(".csv")
        json_path = csv_path.with_suffix(".json")
        export_summary_csv(summary, csv_path)
        export_summary_json(summary, json_path)
        QMessageBox.information(
            self,
            "AI summary saved",
            f"Saved Excel-compatible summary:\n{csv_path}\n\n"
            f"Saved structured summary:\n{json_path}",
        )

    def ai_summary_failed(self, message: str) -> None:
        self.summarize_button.setEnabled(True)
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self.status_label.setText("AI summary failed")
        QMessageBox.critical(self, "AI summary failed", message)


def run() -> int:
    application = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.show()
    return application.exec()
