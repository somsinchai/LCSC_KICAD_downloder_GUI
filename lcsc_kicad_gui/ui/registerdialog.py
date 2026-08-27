"""Show the two library-table rows, and optionally append them for the user."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QGuiApplication
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from ..core import libtable
from ..core.kicad_env import KicadInstall


class RegisterDialog(QDialog):
    def __init__(self, result, installs: list[KicadInstall], preferred: KicadInstall | None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add to KiCad libraries")
        self.setMinimumWidth(660)
        self._result = result
        self._installs = [i for i in installs if i.config_dir is not None]

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        intro = QLabel(
            f"<b>{result.nickname}</b> was saved to<br>"
            f"<span style='color:#8a9099'>{result.folder}</span><br><br>"
            "KiCad needs one symbol-library row and one footprint-library row. "
            "Copy them in yourself, or let this add them for you."
        )
        intro.setWordWrap(True)
        intro.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(intro)

        rows = QPlainTextEdit(f"{result.sym_row}\n{result.fp_row}")
        rows.setReadOnly(True)
        rows.setFont(QFont("Consolas", 9))
        rows.setFixedHeight(96)
        rows.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        layout.addWidget(rows)
        self._rows_text = rows.toPlainText()

        picker = QHBoxLayout()
        picker.addWidget(QLabel("Register into:"))
        self._combo = QComboBox()
        for install in self._installs:
            self._combo.addItem(f"{install.label}  ({install.config_dir})", install)
        if preferred is not None:
            index = self._combo.findText(preferred.label, Qt.MatchFlag.MatchStartsWith)
            if index >= 0:
                self._combo.setCurrentIndex(index)
        picker.addWidget(self._combo, 1)
        layout.addLayout(picker)

        if not self._installs:
            self._combo.setEnabled(False)
            self._combo.addItem("No KiCad configuration folder found")

        self._note = QLabel(
            "One folder per part means two rows per part, so these tables grow as "
            "you download. A timestamped backup is written before any change."
        )
        self._note.setWordWrap(True)
        self._note.setStyleSheet("color:#8a9099; font-size:11px;")
        layout.addWidget(self._note)

        buttons = QDialogButtonBox()
        copy_button = QPushButton("Copy rows")
        copy_button.clicked.connect(self._copy)
        buttons.addButton(copy_button, QDialogButtonBox.ButtonRole.ActionRole)

        self._register_button = QPushButton("Register in KiCad")
        self._register_button.setEnabled(bool(self._installs))
        self._register_button.clicked.connect(self._register)
        buttons.addButton(self._register_button, QDialogButtonBox.ButtonRole.ApplyRole)

        close = buttons.addButton(QDialogButtonBox.StandardButton.Close)
        close.setDefault(True)  # never make the config-writing button the default
        close.clicked.connect(self.accept)
        layout.addWidget(buttons)

    def _copy(self) -> None:
        QGuiApplication.clipboard().setText(self._rows_text)
        self._note.setText("Rows copied to the clipboard.")

    def _register(self) -> None:
        install: KicadInstall = self._combo.currentData()
        if install is None or install.config_dir is None:
            return

        if libtable.kicad_is_running():
            choice = QMessageBox.warning(
                self,
                "KiCad is running",
                "KiCad rewrites its library tables when it closes, which would "
                "discard these rows.\n\nClose KiCad first, then register.",
                QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Ignore,
                QMessageBox.StandardButton.Cancel,
            )
            if choice != QMessageBox.StandardButton.Ignore:
                return

        descr = f"LCSC {self._result.nickname}"
        try:
            sym = libtable.add_row(
                Path(install.config_dir) / "sym-lib-table",
                self._result.nickname,
                self._result.sym_path,
                descr,
            )
            fp = libtable.add_row(
                Path(install.config_dir) / "fp-lib-table",
                self._result.nickname,
                self._result.pretty_dir,
                descr,
            )
        except Exception as err:
            QMessageBox.critical(self, "Could not register", str(err))
            return

        def describe(res) -> str:
            if res.unchanged:
                return "already present"
            return "updated" if res.replaced else "added"

        QMessageBox.information(
            self,
            "Registered",
            f"Symbol library: {describe(sym)}\n"
            f"Footprint library: {describe(fp)}\n\n"
            f"Restart KiCad to pick up the change.",
        )
        self._register_button.setEnabled(False)
