"""Modern Qt (PySide6) GUI for File Organizer v2.0.

Why Qt fixes the v1 complaints:
- HiDPI: Qt6 scales natively (no hardcoded pixels, layout-based geometry,
  vector QPainter chart instead of a fixed-size matplotlib figure).
- Resizable: every panel lives in layouts + QSplitters with sane minimums —
  no ``resizable(False, False)`` / ``800x800`` lock-in.
- Responsive: organizing runs in a QThread, progress + Cancel, no frozen UI.
- Safe: all moves go through :mod:`file_organizer.core` (rename-on-conflict,
  sanitized folder names, preview before acting).
"""

from __future__ import annotations

import os
import sys
import traceback

try:
    from PySide6.QtCore import Qt, QThread, QObject, Signal, QSize, QMimeData
    from PySide6.QtGui import QAction, QColor, QPainter, QPen, QPalette, QDragEnterEvent, QDropEvent
    from PySide6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
        QGroupBox, QPushButton, QLabel, QListWidget, QListWidgetItem, QTableWidget,
        QTableWidgetItem, QHeaderView, QProgressBar, QTextEdit, QSplitter, QComboBox,
        QCheckBox, QDialog, QDialogButtonBox, QMessageBox, QFileDialog, QTabWidget,
        QStatusBar, QMenuBar, QAbstractItemView, QSizePolicy,
    )
except ImportError as exc:
    # Re-raise immediately: app.run_gui() catches ImportError and falls back
    # to the legacy Tk interface (or prints install instructions). Swallowing
    # it here would die later with a confusing NameError on QWidget.
    raise ImportError(
        "PySide6 is required for the Qt interface: "
        "'sudo apt install python3-pyside6' or 'pip install PySide6'"
    ) from exc


from . import __version__
from .config import AppSettings, load_settings, save_settings
from .core import (
    OTHER_CATEGORY,
    clear_undo_log,
    delete_empty_dirs,
    find_empty_dirs,
    load_undo_log,
    normalize_extensions,
    plan_moves,
    sanitize_folder_name,
    save_undo_log,
    scan_directory,
    organize_files as core_organize,
    undo_moves as core_undo,
)


def _human_size(num: int) -> str:
    if num is None or num < 0:
        return "—"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if num < 1024:
            return f"{num:.0f} {unit}" if unit == "B" else f"{num:.1f} {unit}"
        num /= 1024
    return f"{num:.1f} PB"


_PIE_COLORS = [
    "#4C8DDA", "#E06C5B", "#63B267", "#C9902E", "#9B72CF",
    "#4DB6AC", "#E3919B", "#7E9BB5", "#A5B841", "#8D6E63",
]


class PieChart(QWidget):
    """Lightweight DPI-independent pie chart (QPainter, no matplotlib)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._counts: dict[str, int] = {}
        self.setMinimumSize(QSize(220, 220))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_counts(self, counts: dict[str, int]) -> None:
        self._counts = {k: v for k, v in counts.items() if v > 0}
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.contentsRect()
        items = list(self._counts.items())
        if not items:
            painter.setPen(QPen(self.palette().color(QPalette.ColorRole.PlaceholderText)))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "Select a directory\nto view statistics")
            return
        total = sum(v for _, v in items)
        side = min(rect.width(), rect.height()) - 16
        diameter = max(side, 40)
        from PySide6.QtCore import QRectF
        box = QRectF(rect.center().x() - diameter / 2, rect.center().y() - diameter / 2,
                     diameter, diameter)
        angle = 90 * 16
        for i, (label, value) in enumerate(items):
            span = int(360 * 16 * value / total)
            color = QColor(_PIE_COLORS[i % len(_PIE_COLORS)])
            painter.setBrush(color)
            painter.setPen(QPen(self.palette().color(QPalette.ColorRole.Base), 1))
            painter.drawPie(box, angle, -span)
            angle -= span
        # Legend below-center is handled by the summary label; keep chart clean.


class OrganizeWorker(QObject):
    progress = Signal(int, int, str)
    finished = Signal(dict)
    failed = Signal(str)

    def __init__(self, directory, categories, selected, include_other,
                 recursive, conflict, delete_empty):
        super().__init__()
        self._params = (directory, categories, selected, include_other,
                        recursive, conflict, delete_empty)
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        (directory, categories, selected, include_other,
         recursive, conflict, delete_empty) = self._params
        try:
            result = core_organize(
                directory, categories, selected,
                include_other=include_other, recursive=recursive,
                conflict=conflict,
                progress_cb=lambda i, n, name: self.progress.emit(i, n, name),
                cancel_check=lambda: self._cancel,
            )
            if delete_empty and not self._cancel:
                result["cleanup"] = delete_empty_dirs(directory)
            self.finished.emit(result)
        except Exception:  # never crash the thread silently
            self.failed.emit(traceback.format_exc())


class CategoryEditorDialog(QDialog):
    """Edit folder names + extensions with the same validation as core."""

    def __init__(self, categories: dict[str, list[str]], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit File Categories")
        self.resize(620, 420)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Folder names must be plain names (no /, .., or absolute paths).\n"
                                "Extensions are comma-separated, with or without a leading dot."))

        self.table = QTableWidget(0, 2, self)
        self.table.setHorizontalHeaderLabels(["Folder Name", "Extensions"])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        layout.addWidget(self.table)

        for name, exts in categories.items():
            self._add_row(name, ", ".join(exts))

        row_btns = QHBoxLayout()
        add_btn = QPushButton("Add Category")
        del_btn = QPushButton("Remove Selected")
        add_btn.clicked.connect(lambda: self._add_row("", ""))
        del_btn.clicked.connect(self._remove_selected)
        row_btns.addWidget(add_btn)
        row_btns.addWidget(del_btn)
        row_btns.addStretch(1)
        layout.addLayout(row_btns)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save |
                                   QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._result: dict[str, list[str]] | None = None

    def _add_row(self, name: str, exts: str) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(name))
        self.table.setItem(row, 1, QTableWidgetItem(exts))

    def _remove_selected(self) -> None:
        for index in sorted(self.table.selectionModel().selectedRows(), reverse=True):
            self.table.removeRow(index.row())

    def _on_save(self) -> None:
        new: dict[str, list[str]] = {}
        for row in range(self.table.rowCount()):
            name_item = self.table.item(row, 0)
            ext_item = self.table.item(row, 1)
            name = name_item.text().strip() if name_item else ""
            exts_raw = ext_item.text() if ext_item else ""
            if not name and not exts_raw.strip():
                continue  # ignore fully blank rows
            try:
                clean = sanitize_folder_name(name)
            except ValueError as exc:
                QMessageBox.warning(self, "Invalid Folder Name", f"Row {row + 1}: {exc}")
                return
            if not exts_raw.strip():
                QMessageBox.warning(self, "Incomplete Entry",
                                    f"Row {row + 1} ({clean}): provide at least one extension.")
                return
            try:
                exts = normalize_extensions(exts_raw.split(","))
            except ValueError as exc:
                QMessageBox.warning(self, "Invalid Extensions", f"Row {row + 1}: {exc}")
                return
            if clean in new:
                QMessageBox.warning(self, "Duplicate Folder",
                                    f"The folder name '{clean}' appears twice.")
                return
            new[clean] = exts
        if not new:
            QMessageBox.warning(self, "Empty", "Define at least one category.")
            return
        self._result = new
        self.accept()

    def result_categories(self) -> dict[str, list[str]] | None:
        return self._result


class MainWindow(QMainWindow):
    def __init__(self, settings: AppSettings):
        super().__init__()
        self.settings = settings
        self.directory = ""
        self.last_move_log: list[dict] = []
        persisted = load_undo_log()
        if persisted and persisted.get("moved"):
            self.last_move_log = persisted["moved"]
        self._worker: OrganizeWorker | None = None
        self._thread: QThread | None = None

        self.setWindowTitle(f"File Organizer {__version__}")
        self.setMinimumSize(QSize(960, 680))
        self.resize(1180, 800)
        self.setAcceptDrops(True)
        self._build_ui()
        self._refresh_category_list({})
        self._update_buttons()

    # -- construction ------------------------------------------------------

    def _build_ui(self) -> None:
        menubar = self.menuBar()
        file_menu = menubar.addMenu("&File")
        act_quit = QAction("Quit", self)
        act_quit.setShortcut("Ctrl+Q")
        act_quit.triggered.connect(self.close)
        file_menu.addAction(act_quit)

        opts_menu = menubar.addMenu("&Options")
        act_edit = QAction("Edit File Categories…", self)
        act_edit.triggered.connect(self.edit_categories)
        opts_menu.addAction(act_edit)

        help_menu = menubar.addMenu("&Help")
        act_about = QAction("About", self)
        act_about.triggered.connect(self.show_about)
        help_menu.addAction(act_about)

        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        splitter.addWidget(self._build_left_panel())
        splitter.addWidget(self._build_right_panel())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([360, 820])
        self.setCentralWidget(splitter)

        status = QStatusBar(self)
        self.setStatusBar(status)
        self.status_label = QLabel("Ready.")
        status.addWidget(self.status_label, 1)

    def _build_left_panel(self) -> QWidget:
        panel = QWidget(self)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 8, 8, 8)

        # Directory group
        dir_group = QGroupBox("Directory", panel)
        dir_layout = QVBoxLayout(dir_group)
        self.dir_combo = QComboBox(dir_group)
        self.dir_combo.setEditable(True)
        self.dir_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.dir_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        for recent in self.settings.recent_dirs:
            self.dir_combo.addItem(recent)
        self.dir_combo.lineEdit().returnPressed.connect(self._directory_chosen_from_combo)
        dir_layout.addWidget(self.dir_combo)
        browse_row = QHBoxLayout()
        browse_btn = QPushButton("Browse…", dir_group)
        browse_btn.clicked.connect(self.browse_directory)
        browse_row.addWidget(browse_btn)
        browse_row.addStretch(1)
        dir_layout.addLayout(browse_row)
        hint = QLabel("Tip: you can also drag & drop a folder onto this window.", dir_group)
        hint.setWordWrap(True)
        hint.setStyleSheet("color: palette(placeholder-text);")
        dir_layout.addWidget(hint)
        layout.addWidget(dir_group)

        # Categories group
        cat_group = QGroupBox("Categories", panel)
        cat_layout = QVBoxLayout(cat_group)
        self.cat_list = QListWidget(cat_group)
        self.cat_list.itemChanged.connect(lambda _item: self._on_selection_changed())
        cat_layout.addWidget(self.cat_list, 1)
        layout.addWidget(cat_group, 1)

        # Options group
        opt_group = QGroupBox("Options", panel)
        opt_layout = QVBoxLayout(opt_group)
        self.include_other_chk = QCheckBox("File uncategorized items into “Other”", opt_group)
        self.include_other_chk.setChecked(self.settings.include_other)
        self.include_other_chk.toggled.connect(lambda v: (setattr(self.settings, "include_other", v),
                                                          self._on_selection_changed()))
        self.recursive_chk = QCheckBox("Include subdirectories", opt_group)
        self.recursive_chk.setChecked(self.settings.recursive)
        self.recursive_chk.toggled.connect(lambda v: setattr(self.settings, "recursive", v))
        self.delete_empty_chk = QCheckBox("Delete empty folders afterwards", opt_group)
        self.delete_empty_chk.setChecked(self.settings.delete_empty)
        self.delete_empty_chk.toggled.connect(lambda v: setattr(self.settings, "delete_empty", v))
        form = QFormLayout()
        self.conflict_combo = QComboBox(opt_group)
        self.conflict_combo.addItems(["rename", "skip", "overwrite"])
        self.conflict_combo.setToolTip("rename: never overwrite (appends “ (1)”); "
                                       "skip: leave clashing files; overwrite: replace (risky)")
        self.conflict_combo.setCurrentText(self.settings.conflict)
        self.conflict_combo.currentTextChanged.connect(lambda v: setattr(self.settings, "conflict", v))
        form.addRow("If destination exists:", self.conflict_combo)
        opt_layout.addWidget(self.include_other_chk)
        opt_layout.addWidget(self.recursive_chk)
        opt_layout.addWidget(self.delete_empty_chk)
        opt_layout.addLayout(form)
        layout.addWidget(opt_group)

        # Actions
        self.organize_btn = QPushButton("Organize", panel)
        self.organize_btn.setDefault(True)
        self.organize_btn.clicked.connect(self.start_organize)
        self.preview_btn = QPushButton("Preview…", panel)
        self.preview_btn.clicked.connect(self.refresh_preview)
        self.undo_btn = QPushButton("Undo Last Action", panel)
        self.undo_btn.clicked.connect(self.undo_last)
        self.cancel_btn = QPushButton("Cancel", panel)
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self.cancel_organize)
        btn_row = QHBoxLayout()
        btn_row.addWidget(self.organize_btn)
        btn_row.addWidget(self.preview_btn)
        layout.addLayout(btn_row)
        btn_row2 = QHBoxLayout()
        btn_row2.addWidget(self.undo_btn)
        btn_row2.addWidget(self.cancel_btn)
        layout.addLayout(btn_row2)

        self.progress = QProgressBar(panel)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        layout.addWidget(self.progress)
        return panel

    def _build_right_panel(self) -> QWidget:
        panel = QWidget(self)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 8, 8, 8)

        splitter = QSplitter(Qt.Orientation.Vertical, panel)
        # Chart + summary
        top = QWidget(splitter)
        top_layout = QHBoxLayout(top)
        self.chart = PieChart(top)
        top_layout.addWidget(self.chart, 1)
        self.summary_label = QLabel("No directory selected.", top)
        self.summary_label.setWordWrap(True)
        self.summary_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        top_layout.addWidget(self.summary_label, 1)
        splitter.addWidget(top)

        # Tabs: preview + log
        self.tabs = QTabWidget(splitter)
        self.preview_table = QTableWidget(0, 4, self.tabs)
        self.preview_table.setHorizontalHeaderLabels(["File", "Category", "Size", "Destination"])
        self.preview_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch)
        self.preview_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.preview_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabs.addTab(self.preview_table, "Preview")
        self.log_view = QTextEdit(self.tabs)
        self.log_view.setReadOnly(True)
        self.log_view.setPlaceholderText("Activity log…")
        self.tabs.addTab(self.log_view, "Log")
        splitter.addWidget(self.tabs)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([260, 540])
        layout.addWidget(splitter, 1)
        return panel

    # -- directory handling --------------------------------------------------

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        mime: QMimeData = event.mimeData()
        if mime.hasUrls() and len(mime.urls()) == 1 and mime.urls()[0].isLocalFile():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        path = event.urls()[0].toLocalFile()
        if os.path.isdir(path):
            self.set_directory(path)

    def browse_directory(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "Select Directory to Organize",
                                                  self.directory or os.path.expanduser("~"))
        if chosen:
            self.set_directory(chosen)

    def _directory_chosen_from_combo(self) -> None:
        path = self.dir_combo.currentText().strip()
        if os.path.isdir(path):
            self.set_directory(path)
        else:
            QMessageBox.warning(self, "Not a Directory", f"Cannot open:\n{path}")

    def set_directory(self, path: str) -> None:
        self.directory = os.path.abspath(path)
        if self.dir_combo.findText(self.directory) == -1:
            self.dir_combo.insertItem(0, self.directory)
        self.dir_combo.setCurrentText(self.directory)
        self.settings.push_recent(self.directory)
        save_settings(self.settings)
        self.rescan()
        self.log(f"Selected directory: {self.directory}")

    def rescan(self) -> None:
        if not self.directory:
            return
        result = scan_directory(self.directory, self.settings.categories)
        counts = result["counts"]
        self.chart.set_counts(counts)
        lines = [f"<b>{result['total']}</b> file(s) in <b>{self.directory}</b>"]
        for cat in sorted(counts):
            lines.append(f"• {cat}: {counts[cat]}")
        for err in result["errors"]:
            lines.append(f"<i>Error: {err}</i>")
        self.summary_label.setText("<br>".join(lines))
        self._refresh_category_list(counts)
        self.refresh_preview(silent=True)
        self._update_buttons()
        status = f"Found {result['total']} file(s)."
        if result["errors"]:
            status += f" ({len(result['errors'])} errors — see Log)"
            for err in result["errors"]:
                self.log(f"ERROR: {err}")
        self.status_label.setText(status)

    # -- categories ------------------------------------------------------------

    def _refresh_category_list(self, counts: dict[str, int]) -> None:
        self.cat_list.blockSignals(True)
        self.cat_list.clear()
        selected = self._selected_categories(block=False)
        for category in self.settings.categories:
            count = counts.get(category, 0)
            item = QListWidgetItem(f"{category}  ({count})")
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            # Preserve previous check state; default checked.
            item.setCheckState(Qt.CheckState.Checked if selected.get(category, True)
                               else Qt.CheckState.Unchecked)
            item.setData(Qt.ItemDataRole.UserRole, category)
            self.cat_list.addItem(item)
        if self.settings.include_other:
            count = counts.get(OTHER_CATEGORY, 0)
            item = QListWidgetItem(f"{OTHER_CATEGORY}  ({count})")
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if selected.get(OTHER_CATEGORY, True)
                               else Qt.CheckState.Unchecked)
            item.setData(Qt.ItemDataRole.UserRole, OTHER_CATEGORY)
            self.cat_list.addItem(item)
        self.cat_list.blockSignals(False)

    def _selected_categories(self, block: bool = True) -> dict[str, bool]:
        state: dict[str, bool] = {}
        for i in range(self.cat_list.count()):
            item = self.cat_list.item(i)
            state[item.data(Qt.ItemDataRole.UserRole)] = (
                item.checkState() == Qt.CheckState.Checked)
        return state

    def _checked_category_names(self) -> list[str]:
        return [name for name, on in self._selected_categories().items() if on]

    def _on_selection_changed(self) -> None:
        self.refresh_preview(silent=True)
        self._update_buttons()

    def edit_categories(self) -> None:
        dialog = CategoryEditorDialog(self.settings.categories, self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.result_categories():
            self.settings.categories = dialog.result_categories()
            save_settings(self.settings)
            self.log("File categories updated.")
            self.rescan()

    # -- preview ---------------------------------------------------------------

    def refresh_preview(self, silent: bool = False) -> None:
        if not self.directory:
            if not silent:
                QMessageBox.information(self, "No Directory", "Select a directory first.")
            return
        plan = plan_moves(self.directory, self.settings.categories,
                          selected=self._checked_category_names(),
                          include_other=self.include_other_chk.isChecked(),
                          recursive=self.recursive_chk.isChecked())
        scan = scan_directory(self.directory, self.settings.categories)
        size_by_name = {f["name"]: f["size"] for f in scan["files"]}
        self.preview_table.setRowCount(len(plan))
        for row, item in enumerate(plan):
            # plan entries from recursive mode may live in subdirs; basename lookup is best-effort
            size = size_by_name.get(item["filename"], -1)
            self.preview_table.setItem(row, 0, QTableWidgetItem(item["filename"]))
            self.preview_table.setItem(row, 1, QTableWidgetItem(item["category"]))
            self.preview_table.setItem(row, 2, QTableWidgetItem(_human_size(size)))
            self.preview_table.setItem(row, 3, QTableWidgetItem(item["dest_path"]))
        self.tabs.setCurrentWidget(self.preview_table)
        if not silent:
            self.status_label.setText(f"Preview: {len(plan)} file(s) would be moved.")
            self.log(f"Preview: {len(plan)} file(s) would be moved.")

    # -- organize (threaded) -----------------------------------------------------

    def _update_buttons(self) -> None:
        has_dir = bool(self.directory)
        any_checked = any(self._selected_categories().values()) if self.cat_list.count() else False
        running = self._thread is not None
        self.organize_btn.setEnabled(has_dir and any_checked and not running)
        self.preview_btn.setEnabled(has_dir and not running)
        self.undo_btn.setEnabled(bool(self.last_move_log) and not running)
        self.cancel_btn.setEnabled(running)

    def start_organize(self) -> None:
        if not self.directory:
            QMessageBox.warning(self, "No Directory", "Select a directory first.")
            return
        plan = plan_moves(self.directory, self.settings.categories,
                          selected=self._checked_category_names(),
                          include_other=self.include_other_chk.isChecked(),
                          recursive=self.recursive_chk.isChecked())
        if not plan:
            QMessageBox.information(self, "Nothing To Do",
                                    "No files match the current selection.")
            return
        if self.settings.conflict == "overwrite":
            answer = QMessageBox.warning(
                self, "Overwrite Mode",
                f"“Overwrite” will REPLACE {len(plan)} file(s) at the destination.\n"
                "This cannot be perfectly undone. Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                return
        else:
            answer = QMessageBox.question(
                self, "Organize Files",
                f"Move {len(plan)} file(s) into category folders?\n"
                f"Conflict policy: {self.settings.conflict}.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes)
            if answer != QMessageBox.StandardButton.Yes:
                return

        self._thread = QThread(self)
        self._worker = OrganizeWorker(
            self.directory, dict(self.settings.categories),
            self._checked_category_names(),
            self.include_other_chk.isChecked(), self.recursive_chk.isChecked(),
            self.conflict_combo.currentText(), self.delete_empty_chk.isChecked())
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self._worker.finished.connect(self._thread.quit)
        self._thread.finished.connect(self._teardown_thread)
        self.progress.setValue(0)
        self._update_buttons()
        self.log(f"Starting to organize {len(plan)} file(s)…")
        self._thread.start()

    def _on_progress(self, done: int, total: int, name: str) -> None:
        self.progress.setMaximum(total)
        self.progress.setValue(done)
        self.status_label.setText(f"[{done}/{total}] {name}")

    def _on_finished(self, result: dict) -> None:
        self.last_move_log = result.get("moved", [])
        if self.last_move_log:
            save_undo_log(self.last_move_log, self.directory)
        else:
            clear_undo_log()
        self.log(f"Moved {len(self.last_move_log)} file(s).")
        for item in result.get("skipped", []):
            self.log(f"Skipped (exists): {item['filename']}")
        for err in result.get("errors", []):
            self.log(f"ERROR: {err}")
        cleanup = result.get("cleanup")
        if cleanup:
            self.log(f"Deleted {len(cleanup['deleted'])} empty folder(s).")
            for err in cleanup.get("errors", []):
                self.log(f"ERROR: {err}")
        if result.get("cancelled"):
            self.log("Cancelled by user.")
            QMessageBox.information(self, "Cancelled", "Organization was cancelled.")
        else:
            QMessageBox.information(self, "Done",
                                    f"Organized {len(self.last_move_log)} file(s).")
        self.progress.setValue(self.progress.maximum())
        self.rescan()

    def _on_failed(self, tb: str) -> None:
        self.log(f"FAILED:\n{tb}")
        QMessageBox.critical(self, "Error", "Organization failed — see Log for details.")

    def _teardown_thread(self) -> None:
        if self._worker:
            self._worker.deleteLater()
            self._worker = None
        if self._thread:
            self._thread.deleteLater()
            self._thread = None
        self.cancel_btn.setEnabled(False)
        self._update_buttons()

    def cancel_organize(self) -> None:
        if self._worker:
            self._worker.cancel()
            self.log("Cancelling… (finishes the current file)")

    # -- undo --------------------------------------------------------------------

    def undo_last(self) -> None:
        if not self.last_move_log:
            QMessageBox.information(self, "Nothing to Undo", "No recent organization to undo.")
            return
        answer = QMessageBox.question(
            self, "Undo", f"Move {len(self.last_move_log)} file(s) back?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        result = core_undo(self.last_move_log)
        self.log(f"Undid {result['undone']} file move(s).")
        for err in result["errors"]:
            self.log(f"ERROR: {err}")
        self.last_move_log = []
        clear_undo_log()
        QMessageBox.information(self, "Undo Complete",
                                f"Moved back {result['undone']} file(s).")
        self.rescan()

    # -- misc ----------------------------------------------------------------------

    def log(self, message: str) -> None:
        self.log_view.append(message)

    def show_about(self) -> None:
        QMessageBox.about(
            self, "About File Organizer",
            f"<b>File Organizer {__version__}</b><br><br>"
            "Organize files by category on Linux.<br><br>"
            "Moves are <i>rename-on-conflict</i> by default so existing files "
            "are never silently overwritten.<br><br>"
            "MIT License — Elshad Guliyev<br>"
            "<a href='https://github.com/ell-shad/file-organizer'>GitHub</a>")

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._thread is not None:
            QMessageBox.warning(self, "Busy", "Wait for the current task or Cancel it first.")
            event.ignore()
            return
        save_settings(self.settings)
        super().closeEvent(event)


def run(argv: list[str] | None = None) -> int:
    """Entry point used by ``file_organizer.app``."""
    app = QApplication.instance() or QApplication(argv or sys.argv)
    app.setApplicationName("File Organizer")
    app.setOrganizationName("ell-shad")
    settings = load_settings()
    window = MainWindow(settings)
    window.show()
    return app.exec()
