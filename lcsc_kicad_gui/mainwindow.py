"""Main window: enter a part, look at it, download it."""

from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path

from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtGui import QAction, QDesktopServices, QKeySequence
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from . import config
from .core import fetcher
from .core.kicad_env import KicadInstall, detect_installs
from .ui.details import DetailsHeader
from .ui.registerdialog import RegisterDialog
from .ui.svgview import SvgView
from .ui.symboltab import SymbolTab
from .ui.view3d import View3D
from .workers import CommitJob, FetchJob

log = logging.getLogger(__name__)

SYMBOL_BG = "#ffffff"
FOOTPRINT_BG = "#001023"  # matches pcbnew, so white silkscreen stays readable

HINT_2D = "Scroll to zoom · drag to pan · double-click to fit"
HINT_3D = "Left-drag to pan · right-drag to rotate · scroll to zoom · double-click to fit"


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(config.APP_NAME)
        self.resize(1180, 780)

        self._pool = QThreadPool.globalInstance()
        self._pool.setMaxThreadCount(3)
        self._installs: list[KicadInstall] = detect_installs()
        self._bundles: dict[str, object] = {}
        self._current = None
        self._busy: set[str] = set()

        self._build_ui()
        self._restore()
        self._report_environment()

    # -- construction ----------------------------------------------------

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(10, 10, 10, 6)
        root.setSpacing(8)

        root.addLayout(self._build_search_row())

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_side_panel())
        splitter.addWidget(self._build_preview_panel())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([260, 900])
        self._splitter = splitter
        root.addWidget(splitter, 1)

        root.addLayout(self._build_action_row())

        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("Ready")

        quit_action = QAction("Quit", self)
        quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        quit_action.triggered.connect(self.close)
        self.addAction(quit_action)

    def _build_search_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)

        self._entry = QLineEdit()
        self._entry.setPlaceholderText("LCSC part number, e.g. C54951858  (paste several to queue them)")
        self._entry.returnPressed.connect(self._on_fetch)
        row.addWidget(self._entry, 1)

        self._fetch_button = QPushButton("Fetch")
        self._fetch_button.setDefault(True)
        self._fetch_button.clicked.connect(self._on_fetch)
        row.addWidget(self._fetch_button)

        row.addSpacing(12)
        row.addWidget(QLabel("KiCad:"))
        self._kicad_combo = QComboBox()
        for install in self._installs:
            self._kicad_combo.addItem(install.label, install)
        if not self._installs:
            self._kicad_combo.addItem("not found", None)
            self._kicad_combo.setEnabled(False)
        self._kicad_combo.currentIndexChanged.connect(self._on_kicad_changed)
        row.addWidget(self._kicad_combo)
        return row

    def _build_side_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        layout.addWidget(QLabel("Fetched parts"))
        self._list = QListWidget()
        self._list.currentItemChanged.connect(self._on_selection)
        layout.addWidget(self._list, 1)

        self._hidden_pins = QCheckBox("Show hidden pins in preview")
        self._hidden_pins.setChecked(True)
        layout.addWidget(self._hidden_pins)
        return panel

    def _build_preview_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self._details = DetailsHeader()
        layout.addWidget(self._details)

        unit_row = QHBoxLayout()
        unit_row.addStretch(1)
        self._unit_label = QLabel("Unit")
        self._unit_combo = QComboBox()
        self._unit_combo.currentIndexChanged.connect(self._on_unit_changed)
        for widget in (self._unit_label, self._unit_combo):
            widget.setVisible(False)
            unit_row.addWidget(widget)
        layout.addLayout(unit_row)

        self._symbol_tab = SymbolTab(SYMBOL_BG)
        self._symbol_view = self._symbol_tab.view
        self._footprint_view = SvgView(FOOTPRINT_BG)
        self._view3d = View3D()

        self._tabs = QTabWidget()
        self._tabs.addTab(self._symbol_tab, "Symbol")
        self._tabs.addTab(self._footprint_view, "Footprint")
        self._tabs.addTab(self._view3d, "3D")
        layout.addWidget(self._tabs, 1)

        self._hint = QLabel(HINT_2D)
        self._hint.setStyleSheet("color:#8a9099; font-size:11px;")
        layout.addWidget(self._hint)
        self._tabs.currentChanged.connect(self._on_tab_changed)
        return panel

    def _build_action_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)

        row.addWidget(QLabel("Save to:"))
        self._root_edit = QLineEdit(str(config.output_root()))
        self._root_edit.editingFinished.connect(
            lambda: config.set_value("output/root", self._root_edit.text())
        )
        row.addWidget(self._root_edit, 1)

        browse = QPushButton("Browse…")
        browse.clicked.connect(self._on_browse)
        row.addWidget(browse)

        self._download_button = QPushButton("Download")
        self._download_button.setEnabled(False)
        self._download_button.clicked.connect(self._on_download)
        row.addWidget(self._download_button)
        return row

    # -- state -----------------------------------------------------------

    def _restore(self) -> None:
        store = config.settings()
        geometry = store.value("ui/geometry")
        if geometry:
            self.restoreGeometry(geometry)
        splitter = store.value("ui/splitter")
        if splitter:
            self._splitter.restoreState(splitter)
        symbol_split = store.value("ui/symbol_splitter")
        if symbol_split:
            self._symbol_tab.splitter.restoreState(symbol_split)
        self._hidden_pins.setChecked(config.get_bool("preview/include_hidden_pins", True))

        preferred = config.get_str("kicad/version")
        if preferred:
            index = self._kicad_combo.findText(preferred, Qt.MatchFlag.MatchStartsWith)
            if index >= 0:
                self._kicad_combo.setCurrentIndex(index)

    def closeEvent(self, event) -> None:  # noqa: D102
        store = config.settings()
        store.setValue("ui/geometry", self.saveGeometry())
        store.setValue("ui/splitter", self._splitter.saveState())
        store.setValue("ui/symbol_splitter", self._symbol_tab.splitter.saveState())
        store.setValue("preview/include_hidden_pins", self._hidden_pins.isChecked())
        store.setValue("output/root", self._root_edit.text())
        store.sync()
        for bundle in self._bundles.values():
            try:
                bundle.staging.cleanup()
            except Exception:
                pass
        super().closeEvent(event)

    def _report_environment(self) -> None:
        if not self._installs:
            self.statusBar().showMessage(
                "KiCad not found — previews will use EasyEDA's drawing. Downloads still work."
            )

    @property
    def _install(self) -> KicadInstall | None:
        return self._kicad_combo.currentData()

    def _on_kicad_changed(self) -> None:
        install = self._install
        if install is not None:
            config.set_value("kicad/version", install.label)

    # -- fetching --------------------------------------------------------

    def _on_fetch(self) -> None:
        raw = self._entry.text().strip()
        if not raw:
            return
        # Accept a pasted list: commas, whitespace or newlines all separate.
        tokens = [t for t in raw.replace(",", " ").split() if t]
        queued = 0
        for token in tokens:
            part_id = fetcher.normalize_lcsc_id(token)
            if not fetcher.LCSC_ID_RE.match(part_id):
                self.statusBar().showMessage(f"'{token}' is not an LCSC part number.")
                continue
            if part_id in self._busy:
                continue
            self._start_fetch(part_id)
            queued += 1
        if queued:
            self._entry.clear()

    def _start_fetch(self, lcsc_id: str) -> None:
        config.ensure_dirs()
        self._busy.add(lcsc_id)
        self._set_list_status(lcsc_id, "fetching…")

        job = FetchJob(
            lcsc_id,
            install=self._install,
            cache_dir=config.CACHE_DIR,
            include_hidden_pins=self._hidden_pins.isChecked(),
        )
        job.signals.progress.connect(self._on_progress)
        job.signals.finished.connect(self._on_fetched)
        job.signals.failed.connect(self._on_failed)
        self._pool.start(job)

    def _on_progress(self, lcsc_id: str, message: str) -> None:
        self.statusBar().showMessage(f"{lcsc_id}: {message}")

    def _on_fetched(self, lcsc_id: str, bundle) -> None:
        self._busy.discard(lcsc_id)
        previous = self._bundles.get(lcsc_id)
        if previous is not None:
            try:
                previous.staging.cleanup()
            except Exception:
                pass
        self._bundles[lcsc_id] = bundle
        self._set_list_status(lcsc_id, bundle.info.mpn or bundle.info.name, data=lcsc_id)
        self.statusBar().showMessage(f"{lcsc_id}: ready")

        item = self._find_item(lcsc_id)
        if item is not None and (self._list.currentItem() is None or self._current is None):
            self._list.setCurrentItem(item)
        elif self._current and self._current.lcsc_id == lcsc_id:
            self._show(bundle)

        if bundle.warnings:
            log.info("%s: %s", lcsc_id, "; ".join(bundle.warnings))

    def _on_failed(self, lcsc_id: str, message: str, trace: str) -> None:
        self._busy.discard(lcsc_id)
        self._set_list_status(lcsc_id, f"failed — {message}")
        self.statusBar().showMessage(f"{lcsc_id}: {message}")
        if trace:
            log.error("%s failed:\n%s", lcsc_id, trace)

    # -- list ------------------------------------------------------------

    def _find_item(self, lcsc_id: str) -> QListWidgetItem | None:
        for index in range(self._list.count()):
            item = self._list.item(index)
            if item.data(Qt.ItemDataRole.UserRole + 1) == lcsc_id:
                return item
        return None

    def _set_list_status(self, lcsc_id: str, text: str, data: str | None = None) -> None:
        item = self._find_item(lcsc_id)
        if item is None:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole + 1, lcsc_id)
            self._list.addItem(item)
        item.setText(f"{lcsc_id}\n{text}")
        if data:
            item.setData(Qt.ItemDataRole.UserRole, data)

    def _on_selection(self, current: QListWidgetItem | None, _previous=None) -> None:
        if current is None:
            return
        lcsc_id = current.data(Qt.ItemDataRole.UserRole + 1)
        bundle = self._bundles.get(lcsc_id)
        if bundle is not None:
            self._show(bundle)

    # -- preview ---------------------------------------------------------

    def _show(self, bundle) -> None:
        self._current = bundle
        self._details.show_bundle(bundle)
        self._download_button.setEnabled(True)

        units = bundle.ki_symbol_svgs
        multi = len(units) > 1
        self._unit_label.setVisible(multi)
        self._unit_combo.setVisible(multi)
        self._unit_combo.blockSignals(True)
        self._unit_combo.clear()
        if multi:
            for index in range(len(units)):
                self._unit_combo.addItem(f"{index + 1} of {len(units)}")
        self._unit_combo.blockSignals(False)

        # Tier 2 where we have it, tier 1 otherwise — never an empty pane.
        extra = []
        if bundle.footprint_name:
            extra.append(("Footprint file", f"{bundle.footprint_name}.kicad_mod"))
        extra.append(("3D model", bundle.model_name if bundle.has_3d else "none"))
        extra.append(("Library folder", bundle.folder_name))
        self._symbol_tab.show_properties(bundle.properties, extra)

        symbol_from_kicad = bool(units) and self._symbol_view.load_file(units[0])
        if not symbol_from_kicad:
            self._symbol_view.load_text(bundle.ee_symbol_svg)

        footprint_from_kicad = bundle.ki_footprint_svg is not None and self._footprint_view.load_file(
            bundle.ki_footprint_svg
        )
        if not footprint_from_kicad:
            self._footprint_view.load_text(bundle.ee_footprint_svg)

        install = self._install
        self._details.set_render_source(
            kicad=symbol_from_kicad or footprint_from_kicad,
            version=install.version if install else "",
        )
        self._view3d.show_model(bundle.obj_path, bundle.obj_bounds)

    def _on_tab_changed(self, index: int) -> None:
        self._hint.setText(HINT_3D if self._tabs.widget(index) is self._view3d else HINT_2D)

    def _on_unit_changed(self, index: int) -> None:
        if self._current is None or index < 0:
            return
        units = self._current.ki_symbol_svgs
        if 0 <= index < len(units):
            self._symbol_view.load_file(units[index])

    # -- download --------------------------------------------------------

    def _on_browse(self) -> None:
        chosen = QFileDialog.getExistingDirectory(
            self, "Choose a library folder", self._root_edit.text()
        )
        if chosen:
            self._root_edit.setText(chosen)
            config.set_value("output/root", chosen)

    def _on_download(self) -> None:
        bundle = self._current
        if bundle is None:
            return
        root = Path(self._root_edit.text()).expanduser()
        destination = root / bundle.folder_name

        on_exists = "overwrite"
        if destination.exists():
            box = QMessageBox(self)
            box.setWindowTitle("Folder already exists")
            box.setText(f"{destination} already exists.")
            box.setInformativeText("Replace the files in it, or save alongside it?")
            replace = box.addButton("Replace", QMessageBox.ButtonRole.DestructiveRole)
            rename = box.addButton("Save as a copy", QMessageBox.ButtonRole.AcceptRole)
            box.addButton(QMessageBox.StandardButton.Cancel)
            box.exec()
            clicked = box.clickedButton()
            if clicked is replace:
                on_exists = "overwrite"
            elif clicked is rename:
                on_exists = "rename"
            else:
                return

        self._download_button.setEnabled(False)
        self.statusBar().showMessage(f"{bundle.lcsc_id}: saving…")

        job = CommitJob(bundle, root, on_exists)
        job.signals.finished.connect(self._on_committed)
        job.signals.failed.connect(self._on_commit_failed)
        self._pool.start(job)

    def _on_committed(self, lcsc_id: str, result, problems) -> None:
        self._download_button.setEnabled(True)
        config.set_value("output/root", self._root_edit.text())

        if problems:
            QMessageBox.warning(
                self,
                "Saved, but check this",
                f"{result.folder}\n\n" + "\n".join(f"• {p}" for p in problems),
            )
        self.statusBar().showMessage(f"{lcsc_id}: saved to {result.folder}")

        bundle = self._bundles.get(lcsc_id)
        dialog = RegisterDialog(result, self._installs, self._install, self)
        dialog.exec()

    def _on_commit_failed(self, lcsc_id: str, message: str, trace: str) -> None:
        self._download_button.setEnabled(True)
        QMessageBox.critical(self, "Could not save", f"{lcsc_id}\n\n{message}")
        if trace:
            log.error("%s commit failed:\n%s", lcsc_id, trace)
