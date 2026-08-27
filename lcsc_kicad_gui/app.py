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

    from . import config

    # Runtime-only: persisting this would silently disable 3D forever, with no
    # UI anywhere to turn it back on.
    config.RUNTIME_NO_3D = "--no-3d" in argv

    # Direct3D 11 is the most dependable RHI backend on Windows; pick it
    # before QApplication exists, which is the only point it can be set.
    if os.name == "nt" and not os.environ.get("QSG_RHI_BACKEND"):
        try:
            from PySide6.QtQuick import QQuickWindow, QSGRendererInterface

            QQuickWindow.setGraphicsApi(QSGRendererInterface.GraphicsApi.Direct3D11)
        except Exception:  # falls back to Qt's own default
            pass

    from PySide6.QtWidgets import QApplication

    from .mainwindow import MainWindow

    config.ensure_dirs()
    app = QApplication(argv)
    app.setApplicationName(config.APP_NAME)
    app.setOrganizationName("lcsc_kicad_gui")

    window = MainWindow()
    window.show()

    if "--selftest" in argv:
        from .selftest import run_selftest

        return run_selftest(app, window)

    return app.exec()
