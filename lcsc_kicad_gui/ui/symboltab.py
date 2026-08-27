"""Symbol tab: the drawing and the property table side by side."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QLabel,
    QMenu,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .svgview import SvgView

HIDDEN_FG = "#8a9099"


class PropertyTable(QTableWidget):
    """The fields KiCad will attach to the placed symbol."""

    def __init__(self, parent=None) -> None:
        super().__init__(0, 2, parent)
        self.setHorizontalHeaderLabels(["Field", "Value"])
        self.verticalHeader().setVisible(False)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setAlternatingRowColors(True)
        self.setWordWrap(True)
        self.setShowGrid(False)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._menu)

        header = self.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setHighlightSections(False)

    def show_properties(self, properties, extra: list[tuple[str, str]] | None = None) -> None:
        rows = [(p.name, p.value, p.hidden) for p in properties]
        rows += [(name, value, False) for name, value in (extra or [])]

        self.setRowCount(len(rows))
        for index, (name, value, hidden) in enumerate(rows):
            name_item = QTableWidgetItem(name)
            value_item = QTableWidgetItem(value)
            if hidden:
                # Mirror KiCad: these exist on the symbol but aren't drawn.
                name_item.setToolTip("Hidden on the schematic sheet")
                value_item.setToolTip("Hidden on the schematic sheet")
                for item in (name_item, value_item):
                    item.setForeground(QColor(HIDDEN_FG))
            value_item.setToolTip(value_item.toolTip() or value)
            self.setItem(index, 0, name_item)
            self.setItem(index, 1, value_item)
        self.resizeRowsToContents()

    def clear_properties(self) -> None:
        self.setRowCount(0)

    def _menu(self, position) -> None:
        item = self.itemAt(position)
        if item is None:
            return
        menu = QMenu(self)
        copy_value = menu.addAction("Copy value")
        copy_row = menu.addAction("Copy field and value")
        chosen = menu.exec(self.viewport().mapToGlobal(position))
        if chosen is None:
            return
        row = item.row()
        name = self.item(row, 0).text() if self.item(row, 0) else ""
        value = self.item(row, 1).text() if self.item(row, 1) else ""
        QGuiApplication.clipboard().setText(
            value if chosen is copy_value else f"{name}\t{value}"
        )


class SymbolTab(QWidget):
    def __init__(self, background: str = "#ffffff", parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.view = SvgView(background)

        side = QWidget()
        side_layout = QVBoxLayout(side)
        side_layout.setContentsMargins(8, 6, 0, 0)
        side_layout.setSpacing(4)
        caption = QLabel("Symbol fields")
        caption.setStyleSheet("font-weight:600;")
        side_layout.addWidget(caption)
        self.table = PropertyTable()
        side_layout.addWidget(self.table, 1)
        note = QLabel("Greyed fields are hidden on the sheet.")
        note.setStyleSheet(f"color:{HIDDEN_FG}; font-size:11px;")
        note.setWordWrap(True)
        side_layout.addWidget(note)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.addWidget(self.view)
        self.splitter.addWidget(side)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([620, 340])
        self.splitter.setChildrenCollapsible(True)
        layout.addWidget(self.splitter)

    # Convenience passthroughs so the window can treat this like the view.
    def load_file(self, path: Path, keep_view: bool = False) -> bool:
        return self.view.load_file(path, keep_view)

    def load_text(self, svg: str, keep_view: bool = False) -> bool:
        return self.view.load_text(svg, keep_view)

    def show_properties(self, properties, extra=None) -> None:
        self.table.show_properties(properties, extra)

    def clear(self) -> None:
        self.view.clear()
        self.table.clear_properties()
