"""Per-part folder naming, staging area, and the commit (copy) step."""

from __future__ import annotations

import re
import shutil
import tempfile
from pathlib import Path

_ILLEGAL = re.compile(r'[<>:"/\|?*\x00-\x1f]')
_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}
MAX_NAME_LEN = 60


def sanitize_name(name: str, max_len: int = MAX_NAME_LEN) -> str:
    """Make *name* safe as a Windows folder-name component.

    EasyEDA metadata is full of CJK (e.g. manufacturer "ESPRESSIF(乐鑫)") and
    characters Windows rejects, so strip to ASCII and drop the illegal set.
    """
    cleaned = _ILLEGAL.sub("_", name)
    cleaned = cleaned.encode("ascii", "ignore").decode("ascii")
    cleaned = re.sub(r"\s+", "_", cleaned).strip("._ ")
    cleaned = re.sub(r"_{2,}", "_", cleaned)
    if len(cleaned) > max_len:
        cleaned = cleaned[:max_len].rstrip("._ ")
    if cleaned.upper() in _RESERVED:
        cleaned += "_"
    return cleaned or "part"


def folder_name_for(lcsc_id: str, symbol_name: str) -> str:
    """`C54951858_ESP32-C5-WROOM-1U-N8R8-V1.2`"""
    suffix = sanitize_name(symbol_name)
    return f"{lcsc_id}_{suffix}" if suffix else lcsc_id


class StagingArea:
    """A temp folder laid out exactly like the final per-part folder.

    Conversion writes here; :meth:`commit` copies it to the real destination.
    Nothing is reconverted at commit time, so what you previewed is exactly
    what lands in the library.
    """

    def __init__(self, lcsc_id: str) -> None:
        self.lcsc_id = lcsc_id
        self._tmp = Path(tempfile.mkdtemp(prefix=f"lcsc_{lcsc_id}_"))
        self.part_dir = self._tmp / lcsc_id
        self.part_dir.mkdir(parents=True, exist_ok=True)

    # The library basename inside the folder is the bare LCSC id: short,
    # unique, and it doubles as the KiCad library nickname.
    @property
    def lib_name(self) -> str:
        return self.lcsc_id

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
