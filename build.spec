# PyInstaller build for LCSC KiCad Downloader.
#
# One-FOLDER build on purpose, not one-file. Qt is LGPL-3.0, which requires that
# users be able to replace the Qt libraries with their own build. Keeping the Qt
# DLLs as ordinary files beside the .exe satisfies that directly; a one-file
# build buries them in a self-extracting archive. It also starts far faster,
# since Qt Quick 3D is a few hundred megabytes to unpack on every launch.
#
#   Build:  .venv\Scripts\python.exe -m PyInstaller build.spec --noconfirm

from pathlib import Path

import PySide6

_QT = Path(PySide6.__file__).parent

# RuntimeLoader loads .obj through Qt's assimp-backed asset importer, which is a
# runtime-resolved Qt plugin. Nothing references it statically, so PyInstaller's
# analysis never sees it and the 3D tab fails with "Unsupported" in a frozen
# build. Ship both assimp plugins explicitly.
binaries = [
    (str(_QT / "plugins" / "assetimporters" / "assimp.dll"), "PySide6/plugins/assetimporters"),
    (str(_QT / "plugins" / "sceneparsers" / "assimpsceneimport.dll"), "PySide6/plugins/sceneparsers"),
]

datas = [
    ("lcsc_kicad_gui/ui/Model3dView.qml", "lcsc_kicad_gui/ui"),
    # Shipped with the binary so the licence travels with it (AGPL §6 / LGPL §4).
    ("LICENSE", "."),
    ("THIRD-PARTY-LICENSES.md", "."),
]

# The 3D tab needs QtQuick3D's QML modules at runtime: AssetUtils provides
# RuntimeLoader (assimp-backed .obj loading) and Helpers provides GridGeometry.
# PyInstaller's PySide6 hook does not reliably pull the Quick3D QML tree.
hiddenimports = [
    "PySide6.QtQuick",
    "PySide6.QtQuick3D",
    "PySide6.QtQuickWidgets",
    "PySide6.QtQml",
    "PySide6.QtOpenGL",
    "PySide6.QtSvg",
    "PySide6.QtSvgWidgets",
    "PySide6.QtNetwork",
]

excludes = [
    # Qt modules this app never touches; each is tens of megabytes.
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
    "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets", "PySide6.Qt3DCore",
    "PySide6.Qt3DRender", "PySide6.Qt3DInput", "PySide6.Qt3DLogic",
    "PySide6.Qt3DAnimation", "PySide6.Qt3DExtras", "PySide6.QtCharts",
    "PySide6.QtDataVisualization", "PySide6.QtBluetooth", "PySide6.QtNfc",
    "PySide6.QtPositioning", "PySide6.QtSerialPort", "PySide6.QtSql",
    "PySide6.QtTest", "PySide6.QtDesigner", "PySide6.QtHelp", "PySide6.QtUiTools",
    "PySide6.QtWebSockets", "PySide6.QtWebChannel", "PySide6.QtPdf",
    "PySide6.QtPdfWidgets", "PySide6.QtSpatialAudio", "PySide6.QtTextToSpeech",
    # Scientific stack pulled in by nothing we use.
    "tkinter", "numpy", "matplotlib", "scipy", "PIL", "pandas",
    "PyQt5", "PyQt6",
]

a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)

# PySide6's hook collects the whole Qt library set regardless of the excludes
# above, which drags in Qt6WebEngineCore.dll - 194 MB, about half the build, for
# a browser engine this app never loads. Drop those by filename after analysis.
_UNWANTED = (
    "Qt6WebEngineCore.dll",
    "QtWebEngineProcess.exe",
    "Qt6Pdf.dll",
    "Qt6PdfQuick.dll",
    "Qt6PdfWidgets.dll",
)


def _keep(entry):
    name = entry[0].replace("\\", "/").split("/")[-1]
    if name in _UNWANTED:
        return False
    # WebEngine's locale data and resource packs travel separately.
    lowered = entry[0].lower().replace("\\", "/")
    return "qtwebengine" not in lowered and "/translations/qtwebengine" not in lowered


a.binaries = [b for b in a.binaries if _keep(b)]
a.datas = [d for d in a.datas if _keep(d)]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="LCSC-KiCad-Downloader",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,          # UPX corrupts some Qt DLLs and trips antivirus heuristics
    console=False,      # GUI app: no console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="LCSC-KiCad-Downloader",
)
