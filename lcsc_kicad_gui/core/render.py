"""Authoritative previews: render generated KiCad files to SVG via kicad-cli."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from .kicad_env import CREATE_NO_WINDOW, KicadInstall

log = logging.getLogger(__name__)
TIMEOUT = 60


def _run(cli: Path, args: list[str]) -> tuple[bool, str]:
    try:
        proc = subprocess.run(
            [str(cli), *args],
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
            creationflags=CREATE_NO_WINDOW,
        )
    except subprocess.TimeoutExpired:
        return False, "kicad-cli timed out"
    except OSError as err:
        return False, f"kicad-cli could not be started: {err}"
    if proc.returncode != 0:
        return False, (proc.stderr or proc.stdout or "kicad-cli failed").strip()
    return True, ""


def render_symbol(
    install: KicadInstall,
    sym_lib: Path,
    symbol_name: str,
    out_dir: Path,
    include_hidden_pins: bool = True,
) -> list[Path]:
    """Render one symbol. A multi-unit part yields one SVG per unit, in order."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    args = ["sym", "export", "svg", "-o", str(out_dir), "-s", symbol_name]
    if include_hidden_pins:
        args.append("--include-hidden-pins")
    args.append(str(sym_lib))

    ok, err = _run(install.cli, args)
    if not ok:
        log.warning("symbol render failed: %s", err)
        return []
    # Filenames are chosen by kicad-cli ("<name>_unit1.svg"), so glob rather
    # than predict; sanitisation of odd characters is not documented.
    return sorted(out_dir.glob("*.svg"))


def render_footprint(
    install: KicadInstall,
    pretty_dir: Path,
    footprint_name: str,
    out_dir: Path,
) -> Path | None:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    # Pass the .pretty directory, not the .kicad_mod: KiCad 8/9 accept only a
    # directory here, KiCad 10 accepts either.
    ok, err = _run(
        install.cli,
        ["fp", "export", "svg", "-o", str(out_dir), "--fp", footprint_name, str(pretty_dir)],
    )
    if not ok:
        log.warning("footprint render failed: %s", err)
        return None
    svgs = sorted(out_dir.glob("*.svg"))
    return svgs[0] if svgs else None
