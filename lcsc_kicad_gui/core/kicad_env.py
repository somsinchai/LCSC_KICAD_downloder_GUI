"""Discovery of installed KiCad versions and their kicad-cli."""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

# Symbol library file-format versions, from easyeda2kicad.kicad.parameters_kicad_symbol.
# Mapping the major KiCad release to the .kicad_sym schema it writes.
SYM_VERSION_BY_MAJOR = {
    6: 20211014,
    7: 20220914,
    8: 20231120,
    9: 20241209,
    10: 20251024,
}

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0

_SEARCH_ROOTS = [
    Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "KiCad",
    Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "KiCad",
    Path("/usr/bin"),
    Path("/usr/local/bin"),
    Path("/Applications"),
]


@dataclass(frozen=True)
class KicadInstall:
    version: str  # "10.0.5"
    major: int  # 10
    cli: Path  # .../bin/kicad-cli.exe
    config_dir: Path | None  # %APPDATA%/kicad/10.0

    @property
    def sym_format_version(self) -> int:
        """The .kicad_sym schema version this KiCad expects."""
        known = sorted(SYM_VERSION_BY_MAJOR)
        major = min(max(self.major, known[0]), known[-1])
        return SYM_VERSION_BY_MAJOR[major]

    @property
    def label(self) -> str:
        return f"KiCad {self.version}"

    def __str__(self) -> str:  # shown in the combo box
        return self.label


def _run_version(cli: Path) -> str | None:
    try:
        out = subprocess.run(
            [str(cli), "--version"],
            capture_output=True,
            text=True,
            timeout=20,
            creationflags=CREATE_NO_WINDOW,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    match = re.search(r"\d+\.\d+(?:\.\d+)?", out.stdout or "")
    return match.group(0) if match else None


def _config_dir_for(version: str) -> Path | None:
    """%APPDATA%/kicad/<major>.<minor> if it exists."""
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return None
    parts = version.split(".")
    if len(parts) < 2:
        return None
    candidate = Path(appdata) / "kicad" / f"{parts[0]}.{parts[1]}"
    return candidate if candidate.is_dir() else None


def _candidate_clis() -> list[Path]:
    exe = "kicad-cli.exe" if os.name == "nt" else "kicad-cli"
    found: list[Path] = []
    for root in _SEARCH_ROOTS:
        if not root.is_dir():
            continue
        direct = root / exe
        if direct.is_file():
            found.append(direct)
        # Windows: C:\Program Files\KiCad\<ver>\bin\kicad-cli.exe
        for child in sorted(root.iterdir()):
            if not child.is_dir():
                continue
            for rel in (Path("bin") / exe, Path("Contents/MacOS") / exe):
                nested = child / rel
                if nested.is_file():
                    found.append(nested)
    return found


def detect_installs() -> list[KicadInstall]:
    """All usable KiCad installs, newest first."""
    installs: list[KicadInstall] = []
    seen: set[Path] = set()
    for cli in _candidate_clis():
        resolved = cli.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        version = _run_version(cli)
        if not version:
            continue
        major = int(version.split(".")[0])
        installs.append(
            KicadInstall(
                version=version,
                major=major,
                cli=cli,
                config_dir=_config_dir_for(version),
            )
        )
    installs.sort(key=lambda i: [int(p) for p in i.version.split(".")], reverse=True)
    return installs
