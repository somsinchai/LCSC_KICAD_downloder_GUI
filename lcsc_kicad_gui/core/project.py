# SPDX-FileCopyrightText: 2026 somsinchai
# SPDX-License-Identifier: AGPL-3.0-only
"""Import a part into a KiCad project rather than a library shelf.

The part is copied under ``<project>/libs/<Part>/`` and registered in the
project's own ``sym-lib-table`` and ``fp-lib-table``, so it is available in
that project and nowhere else. Every path written is ``${KIPRJMOD}``-relative,
which is what lets the project be moved, zipped or handed to someone else with
the 3D models still resolving.

Nothing here touches the schematic. KiCad has no supported API for placing a
symbol on a sheet — the IPC API in KiCad 9 and 10 covers the board only — and
hand-editing a ``.kicad_sch`` risks a file the user may have open.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from . import libtable
from .commit import CommitResult, commit, verify
from .fetcher import PartBundle

log = logging.getLogger(__name__)

# Subfolder inside the project. Keeping parts out of the project root matters:
# tools that dump one folder per part at the top level make a project unreadable
# after a dozen components.
LIBS_SUBDIR = "libs"

# KiCad expands this to the directory holding the .kicad_pro. It is always
# defined while a project is loaded and cannot be redefined by the user.
PRJ_VAR = "${KIPRJMOD}"


@dataclass(frozen=True)
class KicadProject:
    pro_path: Path
    directory: Path
    name: str

    @property
    def sym_table(self) -> Path:
        return self.directory / "sym-lib-table"

    @property
    def fp_table(self) -> Path:
        return self.directory / "fp-lib-table"

    @property
    def libs_dir(self) -> Path:
        return self.directory / LIBS_SUBDIR

    @property
    def uri_base(self) -> str:
        return f"{PRJ_VAR}/{LIBS_SUBDIR}"


@dataclass
class ImportResult:
    project: KicadProject
    commit: CommitResult
    sym_row: libtable.AddResult
    fp_row: libtable.AddResult
    problems: list[str] = field(default_factory=list)

    @property
    def nickname(self) -> str:
        return self.commit.nickname

    def summary(self) -> str:
        def describe(result: libtable.AddResult) -> str:
            if result.unchanged:
                return "already registered"
            return "updated" if result.replaced else "added"

        return (
            f"Symbol library: {describe(self.sym_row)}\n"
            f"Footprint library: {describe(self.fp_row)}"
        )


def find_project(folder: Path | str | None) -> KicadProject | None:
    """The KiCad project in *folder*, or ``None`` if there isn't exactly one."""
    if not folder:
        return None
    directory = Path(folder).expanduser()
    if not directory.is_dir():
        return None

    projects = sorted(directory.glob("*.kicad_pro"))
    if not projects:
        return None
    if len(projects) > 1:
        # Prefer one named after the folder; otherwise the first is as good a
        # guess as any and the UI shows which was chosen.
        preferred = directory / f"{directory.name}.kicad_pro"
        chosen = preferred if preferred in projects else projects[0]
        log.info("%s holds %d projects; using %s", directory, len(projects), chosen.name)
    else:
        chosen = projects[0]

    return KicadProject(
        pro_path=chosen,
        directory=directory.resolve(),
        name=chosen.stem,
    )


def check_writable(project: KicadProject) -> None:
    """Fail before touching anything if the project folder can't be written.

    os.access() reports the Windows read-only attribute rather than the ACL and
    says nothing useful about a OneDrive placeholder, so actually try it.
    """
    probe = project.directory / f".lcsc-write-test-{os.getpid()}"
    try:
        probe.touch()
        probe.unlink()
    except OSError as err:
        raise OSError(f"Cannot write to {project.directory}: {err}") from err


def import_part(
    bundle: PartBundle, project: KicadProject, on_exists: str = "overwrite"
) -> ImportResult:
    """Copy *bundle* into *project* and register both libraries."""
    check_writable(project)
    result = commit(
        bundle,
        root=project.libs_dir,
        on_exists=on_exists,
        uri_base=project.uri_base,
    )

    descr = f"LCSC {bundle.lcsc_id}"
    sym_row = libtable.add_row(
        project.sym_table, result.nickname, result.sym_uri, descr
    )
    fp_row = libtable.add_row(project.fp_table, result.nickname, result.fp_uri, descr)

    return ImportResult(
        project=project,
        commit=result,
        sym_row=sym_row,
        fp_row=fp_row,
        problems=verify(result, bundle, project_dir=project.directory),
    )
