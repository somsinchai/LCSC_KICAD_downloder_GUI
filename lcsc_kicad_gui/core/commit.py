"""Copy a staged part into the user's library root."""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from pathlib import Path

from easyeda2kicad.kicad.export_kicad_footprint import ExporterFootprintKicad
from easyeda2kicad.kicad.export_kicad_symbol import ExporterSymbolKicad

from .fetcher import PartBundle
from .symbolprops import read_symbol_properties

log = logging.getLogger(__name__)


@dataclass
class CommitResult:
    folder: Path
    nickname: str
    sym_path: Path
    pretty_dir: Path
    shapes_dir: Path | None
    lcsc_id: str = ""
    # The URIs to register. Absolute for a library shelf; ${KIPRJMOD}-relative
    # when the part was imported into a project, so the project stays portable.
    sym_uri: str = ""
    fp_uri: str = ""

    @property
    def descr(self) -> str:
        return f"LCSC {self.lcsc_id}" if self.lcsc_id else self.nickname

    @property
    def sym_row(self) -> str:
        from .libtable import format_row

        return format_row(self.nickname, self.sym_uri or self.sym_path, self.descr)

    @property
    def fp_row(self) -> str:
        from .libtable import format_row

        return format_row(self.nickname, self.fp_uri or self.pretty_dir, self.descr)


def occupant(folder: Path, lib: str) -> str | None:
    """The LCSC id of the part already installed as *lib* in *folder*.

    ``None`` when nothing is there. ``""`` when a library is there but carries
    no LCSC Part field - hand-made, or from another tool - which is exactly the
    case not to overwrite without asking.
    """
    path = Path(folder) / f"{lib}.kicad_sym"
    if not path.is_file():
        return None
    for prop in read_symbol_properties(path):
        if prop.name == "LCSC Part":
            return prop.value
    return ""


def next_free(path: Path) -> Path:
    """`foo` -> `foo_2`, `foo_3`, … for the first name not taken."""
    counter = 2
    while True:
        candidate = path.with_name(f"{path.name}_{counter}")
        if not candidate.exists():
            return candidate
        counter += 1


def commit(
    bundle: PartBundle,
    root: Path,
    on_exists: str = "ask",
    model_3d_path: str | None = None,
    uri_base: str | None = None,
) -> CommitResult:
    """Copy the staged folder into *root*.

    *on_exists* is ``overwrite`` or ``rename``; ``ask`` must have been resolved
    by the caller before getting here.

    *model_3d_path* overrides what gets baked into the ``.kicad_mod``; pass
    ``${KIPRJMOD}/...`` to keep a project portable. *uri_base* is the matching
    prefix for the library-table rows. Both default to absolute paths.
    """
    # Absolute: the URI ends up in KiCad's library table, where a relative
    # path would resolve against whatever KiCad's cwd happens to be.
    root = Path(root).expanduser().resolve()
    dest = root / bundle.folder_name

    if dest.exists():
        if on_exists == "rename":
            # lib, the nickname and both URIs are all derived from dest.name
            # below, so a renamed copy automatically gets its own identity
            # rather than overwriting the original's library-table row.
            dest = next_free(dest)
        elif on_exists == "overwrite":
            pass  # handled below, once the final library name is known
        else:
            raise FileExistsError(str(dest))

    # Folder name, library file stem and KiCad nickname are one and the same,
    # so a renamed copy renames its library too.
    lib = dest.name
    if dest.exists() and on_exists == "overwrite":
        # Remove only the three things we own — the user may keep notes or a
        # datasheet alongside them.
        (dest / f"{lib}.kicad_sym").unlink(missing_ok=True)
        shutil.rmtree(dest / f"{lib}.pretty", ignore_errors=True)
        shutil.rmtree(dest / f"{lib}.3dshapes", ignore_errors=True)
        if bundle.lcsc_id != lib:
            # Older versions named these after the LCSC id; clear them out so a
            # re-download leaves one library here, not two.
            (dest / f"{bundle.lcsc_id}.kicad_sym").unlink(missing_ok=True)
            shutil.rmtree(dest / f"{bundle.lcsc_id}.pretty", ignore_errors=True)
            shutil.rmtree(dest / f"{bundle.lcsc_id}.3dshapes", ignore_errors=True)

    dest.mkdir(parents=True, exist_ok=True)

    if bundle._ee_symbol is not None:
        # Re-export rather than copy: the nickname is baked into the symbol's
        # Footprint field, and only now is the final library name known. A
        # fresh exporter each time - it prefixes info.package in place, so a
        # reused one yields "Lib:Lib:footprint".
        ExporterSymbolKicad(
            symbol=bundle._ee_symbol, lib_path=None, version=bundle.sym_format_version
        ).save_to_lib(
            lib_path=str(dest / f"{lib}.kicad_sym"),
            footprint_lib_name=lib,
            overwrite=True,
        )
    else:
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
            model_3d_path=(
                model_3d_path
                or (f"{uri_base}/{lib}/{lib}.3dshapes" if uri_base else None)
                or (dest / f"{lib}.3dshapes").as_posix()
            ),
        )
    elif bundle.staging.pretty_dir.is_dir():
        shutil.copytree(bundle.staging.pretty_dir, pretty_dest, dirs_exist_ok=True)

    return CommitResult(
        folder=dest,
        nickname=lib,
        sym_path=dest / f"{lib}.kicad_sym",
        pretty_dir=pretty_dest,
        shapes_dir=shapes_dest,
        lcsc_id=bundle.lcsc_id,
        sym_uri=f"{uri_base}/{lib}/{lib}.kicad_sym" if uri_base else "",
        fp_uri=f"{uri_base}/{lib}/{lib}.pretty" if uri_base else "",
    )


def verify(
    result: CommitResult, bundle: PartBundle, project_dir: Path | None = None
) -> list[str]:
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
            resolved = target
            if "${KIPRJMOD}" in target:
                if project_dir is None:
                    continue  # nothing to resolve it against
                resolved = target.replace("${KIPRJMOD}", Path(project_dir).as_posix())
            elif "${" in target:
                continue  # some other KiCad path variable we can't expand
            if not Path(resolved).is_file():
                problems.append(f"3D model reference is missing: {target}")
    return problems
