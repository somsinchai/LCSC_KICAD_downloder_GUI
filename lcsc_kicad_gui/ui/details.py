"""The part header: what you're looking at, and where the preview came from."""

from __future__ import annotations

import html

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFormLayout, QFrame, QLabel, QVBoxLayout, QWidget

BADGE_KICAD = "background:#1f6f43; color:#e8f5ee;"
BADGE_EASYEDA = "background:#7a5a12; color:#fdf3dc;"
BADGE_NEUTRAL = "background:#2f3339; color:#aab1ba;"


def _value_label(text: str = "—") -> QLabel:
    label = QLabel(text)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    label.setWordWrap(True)
    return label


class DetailsHeader(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 10, 12, 10)
        outer.setSpacing(6)

        self._title = QLabel("No part loaded")
        self._title.setStyleSheet("font-size:15px; font-weight:600;")
        self._title.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        outer.addWidget(self._title)

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(3)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)

        self._mpn = _value_label()
        self._manufacturer = _value_label()
        self._package = _value_label()
        self._counts = _value_label()
        self._datasheet = QLabel("—")
        self._datasheet.setOpenExternalLinks(True)
        self._datasheet.setTextFormat(Qt.TextFormat.RichText)

        form.addRow("MPN", self._mpn)
        form.addRow("Manufacturer", self._manufacturer)
        form.addRow("Package", self._package)
        form.addRow("Contents", self._counts)
        form.addRow("Datasheet", self._datasheet)
        outer.addLayout(form)

        self._badge = QLabel("")
        self._badge.setVisible(False)
        self._badge.setStyleSheet(
            BADGE_NEUTRAL + "padding:2px 8px; border-radius:8px; font-size:11px;"
        )
        outer.addWidget(self._badge, alignment=Qt.AlignmentFlag.AlignLeft)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color:#3a3f47;")
        outer.addWidget(line)

    def clear(self) -> None:
        self._title.setText("No part loaded")
        for label in (self._mpn, self._manufacturer, self._package, self._counts):
            label.setText("—")
        self._datasheet.setText("—")
        self._badge.setVisible(False)

    def show_bundle(self, bundle) -> None:
        info = bundle.info
        self._title.setText(f"{bundle.lcsc_id}   {info.name}")
        self._mpn.setText(info.mpn or "—")
        self._manufacturer.setText(info.manufacturer or "—")
        self._package.setText(bundle.footprint_name or info.package or "—")

        parts = [f"{bundle.pin_count} pins", f"{bundle.pad_count} pads"]
        if bundle.unit_count > 1:
            parts.append(f"{bundle.unit_count} units")
        parts.append("3D model" if bundle.has_3d else "no 3D model")
        self._counts.setText("   ·   ".join(parts))

        if info.datasheet:
            safe = html.escape(info.datasheet, quote=True)
            self._datasheet.setText(f'<a href="{safe}">Open datasheet</a>')
        else:
            self._datasheet.setText("—")

    def set_render_source(self, kicad: bool, version: str = "") -> None:
        self._badge.setVisible(True)
        if kicad:
            self._badge.setText(f"KiCad {version} render".strip())
            style = BADGE_KICAD
        else:
            self._badge.setText("EasyEDA render")
            style = BADGE_EASYEDA
        self._badge.setStyleSheet(
            style + "padding:2px 8px; border-radius:8px; font-size:11px;"
        )
