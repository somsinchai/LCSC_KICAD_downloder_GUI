"""End-to-end self check: `--selftest`.

Fetches a known part and reports whether each part of the pipeline worked.
Writes the result to a file rather than stdout, because the released build is
a windowed executable with no console attached — so this also works for a user
who is asked to check their install before filing a bug.
"""

from __future__ import annotations

import platform
import sys
import time
from pathlib import Path

from PySide6.QtCore import QTimer

from . import config
from .core.kicad_env import detect_installs

TEST_PART = "C54951858"
FETCH_TIMEOUT = 180
RENDER_3D_WAIT = 4000


def _report_path() -> Path:
    return config.APP_DIR / "selftest-report.txt"


def run_selftest(app, window) -> int:
    lines: list[str] = []
    failures: list[str] = []

    def record(label: str, ok: bool, detail: str = "") -> None:
        mark = "PASS" if ok else "FAIL"
        lines.append(f"[{mark}] {label}{(' - ' + detail) if detail else ''}")
        if not ok:
            failures.append(label)

    lines.append(f"{config.APP_NAME} self test")
    lines.append(f"version      : {__import__('lcsc_kicad_gui').__version__}")
    lines.append(f"frozen       : {config.FROZEN}")
    lines.append(f"python       : {sys.version.split()[0]}")
    lines.append(f"platform     : {platform.platform()}")
    lines.append(f"app dir      : {config.APP_DIR}")
    lines.append(f"resource dir : {config.RESOURCE_DIR}")

    try:
        from PySide6 import __version__ as pyside_version

        lines.append(f"PySide6      : {pyside_version}")
    except Exception:
        lines.append("PySide6      : unknown")

    installs = detect_installs()
    lines.append(
        "kicad        : "
        + (", ".join(i.label for i in installs) if installs else "not found")
    )
    lines.append("")

    record("QML scene file is present", config.QML_DIR.joinpath("Model3dView.qml").is_file(),
           str(config.QML_DIR / "Model3dView.qml"))

    window._entry.setText(TEST_PART)
    window._on_fetch()
    deadline = time.time() + FETCH_TIMEOUT

    def finish() -> None:
        text = "\n".join(lines)
        text += "\n\n" + ("FAILED: " + ", ".join(failures) if failures else "All checks passed.")
        text += "\n"
        try:
            _report_path().write_text(text, encoding="utf-8")
        except OSError:
            pass
        # Also to stdout when there is one (running from source, or --debug).
        if sys.stdout is not None:
            try:
                print(text)
            except Exception:
                pass
        app.exit(1 if failures else 0)

    def check_3d() -> None:
        view = window._view3d
        quick = getattr(view, "_quick", None)
        if quick is None:
            record("3D view initialised", False, view._message.text().replace("\n", " "))
        else:
            root = quick.rootObject()
            status = root.property("loaderStatus") if root is not None else None
            # RuntimeLoader.Success == 1
            record("3D model loaded", status == 1,
                   f"loaderStatus={status} {root.property('loaderError') if root else ''}")
            record("3D grid sized to the part",
                   bool(root and 0 < root.property("gridStep") < 100),
                   f"step={root.property('gridStep') if root else '?'} mm")
        finish()

    def poll() -> None:
        bundle = window._current
        if bundle is None:
            if time.time() > deadline:
                record(f"fetch {TEST_PART}", False, "timed out")
                finish()
            return
        timer.stop()

        record(f"fetch {TEST_PART}", True, bundle.info.name)
        record("symbol converted", bundle.pin_count > 0, f"{bundle.pin_count} pins")
        record("footprint converted", bundle.pad_count > 0, f"{bundle.pad_count} pads")
        record("symbol fields read back", len(bundle.properties) > 0,
               f"{len(bundle.properties)} fields")
        record("3D model downloaded", bundle.has_3d, bundle.model_name or "none")
        record("symbol preview drawn", window._symbol_view._item is not None)
        record("footprint preview drawn", window._footprint_view._item is not None)
        if installs:
            record("kicad-cli rendered the symbol", bool(bundle.ki_symbol_svgs))
            record("kicad-cli rendered the footprint", bundle.ki_footprint_svg is not None)
        else:
            lines.append("[SKIP] kicad-cli rendering - KiCad not installed")

        if config.RUNTIME_NO_3D:
            lines.append("[SKIP] 3D view - started with --no-3d")
            finish()
            return
        window._tabs.setCurrentIndex(2)
        app.processEvents()
        QTimer.singleShot(RENDER_3D_WAIT, check_3d)

    timer = QTimer()
    timer.timeout.connect(poll)
    timer.start(300)
    return app.exec()
