"""Copy a staged part into the user's library root."""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from pathlib import Path

from easyeda2kicad.kicad.export_kicad_footprint import ExporterFootprintKicad

from .fetcher import PartBundle

log = logging.getLogger(__name__)


@dataclass
class CommitResult:
    folder: Path
    nickname: str
    sym_path: Path
    pretty_dir: Path
    shapes_dir: Path | None

    @property
    def sym_row(self) -> str:
        from .libtable import format_row

        return format_row(self.nickname, self.sym_path, f"LCSC {self.nickname}")

    @property
    def fp_row(self) -> str:
        from .libtable import format_row

        return format_row(self.nickname, self.pretty_dir, f"LCSC {self.nickname}")


def next_free(path: Path) -> Path:
    """`foo` -> `foo_2`, `foo_3`, … for the first name not taken."""
    counter = 2
    while True:
        candidate = path.with_name(f"{path.name}_{counter}")
        if not candidate.exists():
            return candidate
        counter += 1


def commit(bundle: PartBundle, root: Path, on_exists: str = "ask") -> CommitResult:
    """Copy the staged folder into *root*.

    *on_exists* is ``overwrite`` or ``rename``; ``ask`` must have been resolved
    by the caller before getting here.
    """
    # Absolute: the URI ends up in KiCad's library table, where a relative
    # path would resolve against whatever KiCad's cwd happens to be.
    root = Path(root).expanduser().resolve()
    dest = root / bundle.folder_name
    lib = bundle.staging.lib_name

    if dest.exists():
        if on_exists == "rename":
            dest = next_free(dest)
        elif on_exists == "overwrite":
            # Remove only the three things we own — the user may keep notes or
            # a datasheet alongside them.
            (dest / f"{lib}.kicad_sym").unlink(missing_ok=True)
            shutil.rmtree(dest / f"{lib}.pretty", ignore_errors=True)
            shutil.rmtree(dest / f"{lib}.3dshapes", ignore_errors=True)
        else:
            raise FileExistsError(str(dest))

    dest.mkdir(parents=True, exist_ok=True)
    shutil.copy2(bundle.staging.sym_path, dest / f"{lib}.kicad_sym")

    shapes_dest: Path | None = None
    if bundle.has_3d and bundle.staging.shapes_dir.is_dir():
        shapes_dest = dest / f"{lib}.3dshapes"
        shutil.copytree(bundle.staging.shapes_dir, shapes_dest, dirs_exist_ok=True)

    pretty_dest = dest / f"{lib}.pretty"
    if bundle._ee_footprint is not None:
        # Re-export rather than copy: the 3D model path is baked into the file
        # at export time, and only now do we know where it finally lives.
        pretty_dest.mkdir(parents=True, exist_ok=True)
        exporter = ExporterFootprintKicad(footprint=bundle._ee_footprint)
        if not bundle.has_3d:
            exporter.output.model_3d = None
        exporter.export(
            footprint_full_path=str(pretty_dest / f"{bundle.footprint_name}.kicad_mod"),
            model_3d_path=(dest / f"{lib}.3dshapes").as_posix(),
        )
    elif bundle.staging.pretty_dir.is_dir():
        shutil.copytree(bundle.staging.pretty_dir, pretty_dest, dirs_exist_ok=True)

    return CommitResult(
        folder=dest,
        nickname=lib,
        sym_path=dest / f"{lib}.kicad_sym",
        pretty_dir=pretty_dest,
        shapes_dir=shapes_dest,
    )


def verify(result: CommitResult, bundle: PartBundle) -> list[str]:
    """Post-commit sanity checks. Returns a list of problems (empty is good)."""
    problems: list[str] = []

    if not result.sym_path.is_file():
        problems.append("The symbol library was not written.")
        return problems

    text = result.sym_path.read_text(encoding="utf-8", errors="replace")
    # The Footprint property must read "<nickname>:<footprint stem>" and that
    # file must exist, or KiCad shows "footprint not found" on every use.
    marker = '"Footprint"'
    index = text.find(marker)
    if index != -1:
        tail = text[index + len(marker) : index + len(marker) + 400]
        start = tail.find('"')
        end = tail.find('"', start + 1)
        if start != -1 and end != -1:
            value = tail[start + 1 : end]
            if value:
                if value.count(":") != 1:
                    problems.append(f"Footprint field looks wrong: {value!r}")
                else:
                    _, _, stem = value.partition(":")
                    if not (result.pretty_dir / f"{stem}.kicad_mod").is_file():
                        problems.append(f"Footprint field points at a missing file: {value}")

    for mod in result.pretty_dir.glob("*.kicad_mod") if result.pretty_dir.is_dir() else []:
        body = mod.read_text(encoding="utf-8", errors="replace")
        for line in body.splitlines():
            stripped = line.strip()
            if not stripped.startswith('(model "'):
                continue
            target = stripped.split('"')[1]
            if "${" in target:  # a KiCad path variable we can't resolve here
                continue
            if not Path(target).is_file():
                problems.append(f"3D model reference is missing: {target}")
    return problems
