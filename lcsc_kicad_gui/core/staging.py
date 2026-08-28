"""Per-part folder naming, staging area, and the commit (copy) step."""

from __future__ import annotations

import re
import shutil
import tempfile
from pathlib import Path

# The folder name, the library file stem and the KiCad library nickname are all
# the same string, so this has to satisfy the strictest of the three. KiCad's
# own 223 shipped nicknames use nothing outside [A-Za-z0-9_]; hyphen and dot are
# accepted too and part numbers are full of them, so allow those and no more.
_DISALLOWED = re.compile(r"[^A-Za-z0-9_.-]")
_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}
MAX_NAME_LEN = 60


def sanitize_name(name: str, max_len: int = MAX_NAME_LEN) -> str:
    """Make *name* usable as a folder name, a file stem and a KiCad nickname.

    EasyEDA metadata is full of CJK (e.g. manufacturer "ESPRESSIF(乐鑫)") and
    punctuation that is fine in a filename but not in a library nickname, so
    reduce to ASCII and then to the conservative nickname character set.
    """
    cleaned = name.encode("ascii", "ignore").decode("ascii")
    cleaned = _DISALLOWED.sub("_", cleaned)
    cleaned = re.sub(r"\s+", "_", cleaned).strip("._ ")
    cleaned = re.sub(r"_{2,}", "_", cleaned)
    if len(cleaned) > max_len:
        cleaned = cleaned[:max_len].rstrip("._ ")
    if cleaned.upper() in _RESERVED:
        cleaned += "_"
    return cleaned or "part"


def folder_name_for(lcsc_id: str, symbol_name: str) -> str:
    """The part's own name, e.g. `ESP32-C5-WROOM-1U-N8R8-V1.2`.

    This one string is the folder name, the stem of every file inside it and
    the KiCad library nickname, so a part reads the same everywhere. The LCSC
    id is not lost -- it stays as the symbol's "LCSC Part" field. Falls back to
    the id when a part has no usable name.
    """
    name = sanitize_name(symbol_name)
    return name if name and name != "part" else lcsc_id


class StagingArea:
    """A temp folder laid out exactly like the final per-part folder.

    Conversion writes here; :meth:`commit` copies it to the real destination.
    Nothing is reconverted at commit time, so what you previewed is exactly
    what lands in the library.
    """

    def __init__(self, lcsc_id: str, lib_name: str | None = None) -> None:
        self.lcsc_id = lcsc_id
        # Names the library files and doubles as the KiCad nickname. Defaults
        # to the LCSC id only when the caller has no better name to offer.
        self.lib_name = lib_name or lcsc_id
        self._tmp = Path(tempfile.mkdtemp(prefix=f"lcsc_{lcsc_id}_"))
        self.part_dir = self._tmp / lcsc_id
        self.part_dir.mkdir(parents=True, exist_ok=True)

    @property
    def sym_path(self) -> Path:
        return self.part_dir / f"{self.lib_name}.kicad_sym"

    @property
    def pretty_dir(self) -> Path:
        return self.part_dir / f"{self.lib_name}.pretty"

    @property
    def shapes_dir(self) -> Path:
        return self.part_dir / f"{self.lib_name}.3dshapes"

    @property
    def preview_dir(self) -> Path:
        d = self._tmp / "preview"
        d.mkdir(exist_ok=True)
        return d

    def commit(self, destination: Path, overwrite: bool) -> Path:
        """Copy the staged part folder to *destination*. Returns the final path."""
        destination = Path(destination)
        if destination.exists():
            if not overwrite:
                raise FileExistsError(str(destination))
            shutil.rmtree(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(self.part_dir, destination)
        return destination

    def cleanup(self) -> None:
        shutil.rmtree(self._tmp, ignore_errors=True)
