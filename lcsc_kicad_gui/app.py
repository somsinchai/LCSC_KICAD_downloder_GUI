"""Application bootstrap."""

from __future__ import annotations

import logging
import os
import sys


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv)
    debug = "--debug" in argv
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.INFO,
        format="[%(levelname)s] %(name)s: %(message)s",
    )

    if "--no-3d" in argv:
        from . import config

        config.set_value("preview/enable_3d", False)

    # Direct3D 11 is the most dependable RHI backend on Windows; pick it
    # before QApplication exists, which is the only point it can be set.
    if os.name == "nt" and not os.environ.get("QSG_RHI_BACKEND"):
        try:
            from PySide6.QtQuick import QQuickWindow, QSGRendererInterface

            QQuickWindow.setGraphicsApi(QSGRendererInterface.GraphicsApi.Direct3D11)
        except Exception:  # falls back to Qt's own default
            pass

    from PySide6.QtWidgets import QApplication

    from . import config
    from .mainwindow import MainWindow

    config.ensure_dirs()
    app = QApplication(argv)
    app.setApplicationName(config.APP_NAME)
    app.setOrganizationName("lcsc_kicad_gui")

    window = MainWindow()
    window.show()
    return app.exec()
