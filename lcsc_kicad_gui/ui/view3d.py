"""3D preview, built lazily so a broken GPU stack can never block startup."""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QVector3D
from PySide6.QtWidgets import QLabel, QStackedLayout, QWidget

from .. import config

log = logging.getLogger(__name__)
QML_FILE = Path(__file__).resolve().parent / "Model3dView.qml"

PROBE_KEY = "preview/3d_probe"
_STATUS_ERROR = 3  # RuntimeLoader.Error
ENABLE_KEY = "preview/enable_3d"


class View3D(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._stack = QStackedLayout(self)
        self._stack.setContentsMargins(0, 0, 0, 0)

        self._message = QLabel("Fetch a part to see its 3D model.")
        self._message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._message.setWordWrap(True)
        self._message.setStyleSheet("color:#8a9099; padding:24px;")
        self._stack.addWidget(self._message)

        self._quick: QWidget | None = None
        self._pending: Path | None = None

    def show_model(self, obj_path: Path | None, bounds=None) -> None:
        if obj_path is None:
            self._fail("No 3D model is available for this part.")
            return
        self._pending = obj_path
        if not self._ensure_view():
            return
        root = self._quick.rootObject()
        if bounds is not None:
            low, high = bounds
            root.setProperty("modelMin", QVector3D(*low))
            root.setProperty("modelMax", QVector3D(*high))
            root.setProperty("hasExplicitBounds", True)
        else:
            root.setProperty("hasExplicitBounds", False)
        root.setProperty("modelSource", QUrl.fromLocalFile(str(obj_path)))
        self._stack.setCurrentWidget(self._quick)
        # RuntimeLoader can resolve synchronously, in which case the signal has
        # already fired by the time we get here — read the state directly too.
        if root.property("loaderStatus") == _STATUS_ERROR:
            self._on_load_failed(str(root.property("loaderError") or "unknown error"))

    def clear(self) -> None:
        self._pending = None
        self._message.setText("Fetch a part to see its 3D model.")
        self._stack.setCurrentWidget(self._message)

    def _fail(self, text: str) -> None:
        self._message.setText(text)
        self._stack.setCurrentWidget(self._message)

    def _ensure_view(self) -> bool:
        if self._quick is not None:
            return True
        if not config.get_bool(ENABLE_KEY, True):
            self._fail("3D preview is turned off in Settings.\nThe model still downloads.")
            return False
        # A GPU-driver crash kills the process before any except/finally runs,
        # so a flag that survives to the next launch is the only way to notice.
        if config.get_bool(PROBE_KEY, False):
            config.set_value(ENABLE_KEY, False)
            config.set_value(PROBE_KEY, False)
            self._fail(
                "3D preview was turned off after it crashed last time.\n"
                "Re-enable it in Settings to try again."
            )
            return False

        config.set_value(PROBE_KEY, True)
        try:
            from PySide6.QtQuickWidgets import QQuickWidget

            quick = QQuickWidget(self)
            quick.setResizeMode(QQuickWidget.ResizeMode.SizeRootObjectToView)
            quick.setSource(QUrl.fromLocalFile(str(QML_FILE)))
            if quick.status() != QQuickWidget.Status.Ready:
                raise RuntimeError("; ".join(e.toString() for e in quick.errors()) or "QML not ready")
            root = quick.rootObject()
            root.loadFailed.connect(self._on_load_failed)
            self._stack.addWidget(quick)
            self._quick = quick
            return True
        except Exception as err:
            log.warning("QtQuick3D unavailable: %s", err)
            self._fail(
                f"3D preview unavailable ({err}).\nThe STEP and WRL files still download."
            )
            return False
        finally:
            config.set_value(PROBE_KEY, False)

    def _on_load_failed(self, message: str) -> None:
        log.warning("3D model load failed: %s", message)
        self._fail(f"This 3D model could not be displayed.\n{message}")
