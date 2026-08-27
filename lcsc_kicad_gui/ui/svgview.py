"""A pan/zoom SVG canvas.

QSvgWidget is not enough here: it aspect-fits to the widget with no zoom and
no pan, which is useless when you are checking pin numbers on a 32-pin part.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtSvgWidgets import QGraphicsSvgItem
from PySide6.QtWidgets import QGraphicsItem, QGraphicsScene, QGraphicsView

ZOOM_STEP = 1.15
MIN_SCALE = 0.02
MAX_SCALE = 400.0


class SvgView(QGraphicsView):
    def __init__(self, background: str = "#ffffff", parent=None) -> None:
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self._item: QGraphicsSvgItem | None = None
        self._renderer: QSvgRenderer | None = None
        self._user_moved = False

        self.setBackgroundBrush(QColor(background))
        self.setRenderHints(
            QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform
        )
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    # -- loading ---------------------------------------------------------

    def load_text(self, svg: str, keep_view: bool = False) -> bool:
        if not svg:
            return False
        return self._install(QSvgRenderer(QByteArray(svg.encode("utf-8"))), keep_view)

    def load_file(self, path: Path, keep_view: bool = False) -> bool:
        if not path or not Path(path).is_file():
            return False
        return self._install(QSvgRenderer(str(path)), keep_view)

    def clear(self) -> None:
        self.scene().clear()
        self._item = None
        self._renderer = None
        self._user_moved = False

    def _install(self, renderer: QSvgRenderer, keep_view: bool) -> bool:
        if not renderer.isValid():
            return False
        transform = self.transform()
        center = self.mapToScene(self.viewport().rect().center())

        self.scene().clear()
        item = QGraphicsSvgItem()
        # setSharedRenderer does not take ownership — hold a reference or the
        # renderer is collected and the item draws nothing.
        item.setSharedRenderer(renderer)
        # The default ItemCoordinateCache renders once at natural size and
        # scales the bitmap, so zooming turns it to mush.
        item.setCacheMode(QGraphicsItem.CacheMode.NoCache)
        self.scene().addItem(item)
        self._item, self._renderer = item, renderer

        bounds = item.boundingRect()
        margin = max(bounds.width(), bounds.height()) * 0.04 + 4
        self.scene().setSceneRect(bounds.adjusted(-margin, -margin, margin, margin))

        if keep_view and self._user_moved:
            self.setTransform(transform)
            self.centerOn(center)
        else:
            self.fit()
        return True

    # -- interaction -----------------------------------------------------

    def fit(self) -> None:
        if self._item is not None:
            self.fitInView(self.scene().sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
        self._user_moved = False

    def wheelEvent(self, event) -> None:  # noqa: D102
        if self._item is None:
            return
        factor = ZOOM_STEP if event.angleDelta().y() > 0 else 1 / ZOOM_STEP
        scale = self.transform().m11() * factor
        if MIN_SCALE <= scale <= MAX_SCALE:
            self.scale(factor, factor)
            self._user_moved = True

    def mouseMoveEvent(self, event) -> None:  # noqa: D102
        super().mouseMoveEvent(event)
        if event.buttons():
            self._user_moved = True

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: D102
        self.fit()

    def resizeEvent(self, event) -> None:  # noqa: D102
        super().resizeEvent(event)
        if not self._user_moved:
            self.fit()
