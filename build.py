# SPDX-FileCopyrightText: 2026 somsinchai
# SPDX-License-Identifier: AGPL-3.0-only
"""Build the Windows release: PyInstaller, then a zip ready to upload.

    .venv\\Scripts\\python.exe build.py            build and zip
    .venv\\Scripts\\python.exe build.py --no-zip   build only

Produces `dist/LCSC-KiCad-Downloader/` and
`dist/LCSC-KiCad-Downloader-<version>-windows-x64.zip`.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist" / "LCSC-KiCad-Downloader"

# Copied to the top level of the release, beside the .exe, so they are visible
# without digging into _internal/. AGPL section 6 and LGPL section 4 both want
# the licence to travel with the binary.
ALONGSIDE_EXE = ["LICENSE", "THIRD-PARTY-LICENSES.md", "README.md"]


def version() -> str:
    text = (ROOT / "lcsc_kicad_gui" / "__init__.py").read_text(encoding="utf-8")
    match = re.search(r'__version__\s*=\s*"([^"]+)"', text)
    return match.group(1) if match else "0.0.0"


def build() -> None:
    for stale in (ROOT / "build", ROOT / "dist"):
        shutil.rmtree(stale, ignore_errors=True)

    print("Running PyInstaller ...")
    result = subprocess.run(
        [sys.executable, "-m", "PyInstaller", "build.spec", "--noconfirm", "--log-level", "WARN"],
        cwd=ROOT,
    )
    if result.returncode != 0:
        sys.exit(f"PyInstaller failed with exit code {result.returncode}")

    exe = DIST / "LCSC-KiCad-Downloader.exe"
    if not exe.is_file():
        sys.exit(f"Expected {exe} but it was not produced")

    for name in ALONGSIDE_EXE:
        source = ROOT / name
        if source.is_file():
            shutil.copy2(source, DIST / name)

    size = sum(f.stat().st_size for f in DIST.rglob("*") if f.is_file())
    print(f"\nBuilt {DIST}  ({size / 1024 / 1024:.0f} MB)")


def make_zip() -> Path:
    archive = ROOT / "dist" / f"LCSC-KiCad-Downloader-{version()}-windows-x64.zip"
    print(f"Zipping to {archive.name} ...")
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in sorted(DIST.rglob("*")):
            if path.is_file():
                zf.write(path, Path("LCSC-KiCad-Downloader") / path.relative_to(DIST))
    print(f"  {archive.stat().st_size / 1024 / 1024:.0f} MB")
    return archive


def main() -> int:
    build()
    if "--no-zip" not in sys.argv:
        make_zip()
    print(
        "\nBefore publishing, check the build actually works:\n"
        f"  {DIST / 'LCSC-KiCad-Downloader.exe'} --selftest\n"
        "then read selftest-report.txt beside the exe."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
