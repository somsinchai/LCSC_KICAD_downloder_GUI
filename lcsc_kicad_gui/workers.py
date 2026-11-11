"""Background jobs. Workers emit plain data; only the GUI thread builds widgets."""

from __future__ import annotations

import traceback
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Signal

from .core import commit as commit_mod
from .core import fetcher
from .core import project as project_mod
from .core.kicad_env import KicadInstall


class FetchSignals(QObject):
    progress = Signal(str, str)  # lcsc_id, message
    finished = Signal(str, object)  # lcsc_id, PartBundle
    failed = Signal(str, str, str)  # lcsc_id, message, traceback


class CommitSignals(QObject):
    finished = Signal(str, object, object)  # lcsc_id, CommitResult, problems
    failed = Signal(str, str, str)


class ImportSignals(QObject):
    progress = Signal(str, str)  # lcsc_id, message
    # [(lcsc_id, ImportResult | None, error message, traceback), ...]
    finished = Signal(object)
    failed = Signal(str, str, str)  # only if the batch itself blows up


class FetchJob(QRunnable):
    def __init__(
        self,
        lcsc_id: str,
        install: KicadInstall | None,
        cache_dir: Path | None,
        include_hidden_pins: bool = True,
    ) -> None:
        super().__init__()
        self.lcsc_id = lcsc_id
        self.signals = FetchSignals()
        self._install = install
        self._cache_dir = cache_dir
        self._hidden_pins = include_hidden_pins
        self.setAutoDelete(True)

    def run(self) -> None:  # noqa: D102
        try:
            bundle = fetcher.fetch_part(
                self.lcsc_id,
                install=self._install,
                cache_dir=self._cache_dir,
                include_hidden_pins=self._hidden_pins,
                progress=lambda msg: self.signals.progress.emit(self.lcsc_id, msg),
            )
        except fetcher.FetchError as err:
            self.signals.failed.emit(self.lcsc_id, str(err), "")
        except Exception as err:  # never let a worker take the app down
            self.signals.failed.emit(self.lcsc_id, str(err), traceback.format_exc())
        else:
            self.signals.finished.emit(self.lcsc_id, bundle)


class CommitJob(QRunnable):
    def __init__(self, bundle, root: Path, on_exists: str) -> None:
        super().__init__()
        self.bundle = bundle
        self.signals = CommitSignals()
        self._root = root
        self._on_exists = on_exists
        self.setAutoDelete(True)

    def run(self) -> None:  # noqa: D102
        lcsc_id = self.bundle.lcsc_id
        try:
            result = commit_mod.commit(self.bundle, self._root, self._on_exists)
            problems = commit_mod.verify(result, self.bundle)
        except Exception as err:
            self.signals.failed.emit(lcsc_id, str(err), traceback.format_exc())
        else:
            self.signals.finished.emit(lcsc_id, result, problems)


class ImportJob(QRunnable):
    """Copy parts into a KiCad project and register their libraries.

    Runs the parts one after another: every import rewrites the same project
    sym-lib-table and fp-lib-table, so doing them in parallel would race.
    *plan* is ``[(bundle, on_exists), ...]``. One part failing doesn't stop
    the rest; each outcome is reported in ``finished``.
    """

    def __init__(self, plan, project) -> None:
        super().__init__()
        self.plan = list(plan)
        self.signals = ImportSignals()
        self._project = project
        self.setAutoDelete(True)

    def run(self) -> None:  # noqa: D102
        outcomes = []
        try:
            for bundle, on_exists in self.plan:
                lcsc_id = bundle.lcsc_id
                self.signals.progress.emit(lcsc_id, f"importing into {self._project.name}…")
                try:
                    result = project_mod.import_part(bundle, self._project, on_exists)
                except Exception as err:
                    outcomes.append((lcsc_id, None, str(err), traceback.format_exc()))
                else:
                    outcomes.append((lcsc_id, result, "", ""))
        except Exception as err:  # never let a worker take the app down
            self.signals.failed.emit("", str(err), traceback.format_exc())
        else:
            self.signals.finished.emit(outcomes)
