"""Application paths and persisted settings."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import QSettings

APP_NAME = "LCSC KiCad Downloader"

FROZEN = getattr(sys, "frozen", False)

# Where settings.ini lives. In a PyInstaller build the package sits inside
# _internal/, which is the wrong place to write to (and unwritable under
# Program Files), so use the folder holding the .exe instead.
APP_DIR = (
    Path(sys.executable).resolve().parent
    if FROZEN
    else Path(__file__).resolve().parent.parent
)

# Where bundled read-only resources (the QML scene) are unpacked.
RESOURCE_DIR = (
    Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    if FROZEN
    else Path(__file__).resolve().parent.parent
)

_local = os.environ.get("LOCALAPPDATA")
DATA_DIR = Path(_local) / "LCSC_KICAD_downloader" if _local else APP_DIR / ".data"
CACHE_DIR = DATA_DIR / "cache"
QML_DIR = RESOURCE_DIR / "lcsc_kicad_gui" / "ui"

DEFAULT_ROOT = Path.home() / "Documents" / "KiCad" / "LCSC"

# Set from the --no-3d command line flag. Deliberately not persisted:
# there is no settings UI to undo it with.
RUNTIME_NO_3D = False


def settings() -> QSettings:
    """INI beside the app: readable, diffable, and deletable by the user."""
    return QSettings(str(APP_DIR / "settings.ini"), QSettings.Format.IniFormat)


def get_bool(key: str, default: bool) -> bool:
    # QSettings hands back the string "false" from an INI file, which is
    # truthy — the type argument is not optional here.
    return bool(settings().value(key, default, type=bool))


def get_str(key: str, default: str = "") -> str:
    return str(settings().value(key, default))


def set_value(key: str, value: object) -> None:
    store = settings()
    store.setValue(key, value)
    store.sync()


def output_root() -> Path:
    return Path(get_str("output/root", str(DEFAULT_ROOT)))


def ensure_dirs() -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
