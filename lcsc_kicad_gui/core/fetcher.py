"""LCSC id -> fully converted, previewable part bundle.

Everything here runs on a worker thread: the easyeda2kicad importers do their
network calls and parsing inside ``__init__``, so *constructing* them is the
blocking work.
"""

from __future__ import annotations

import json
import logging
import re
import socket
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from easyeda2kicad.easyeda.easyeda_api import EasyedaApi
from easyeda2kicad.easyeda.easyeda_importer import (
    Easyeda3dModelImporter,
    EasyedaFootprintImporter,
    EasyedaSymbolImporter,
)
from easyeda2kicad.easyeda.easyeda_svg_renderer import (
    render_footprint_svg,
    render_symbol_svg,
)
from easyeda2kicad.kicad.export_kicad_3d_model import Exporter3dModelKicad
from easyeda2kicad.kicad.export_kicad_footprint import ExporterFootprintKicad
from easyeda2kicad.kicad.export_kicad_symbol import ExporterSymbolKicad

from . import render
from .kicad_env import KicadInstall
from .objsplit import obj_bounds, split_obj
from .staging import StagingArea, folder_name_for, sanitize_name
from .symbolprops import SymbolProperty, read_symbol_properties

log = logging.getLogger(__name__)

LCSC_ID_RE = re.compile(r"^C\d+$")

# The .kicad_mod's 3D path is baked in at export time. Stage with a token and
# re-export at commit, so changing the output root can never strand the model.
MODEL_PATH_PLACEHOLDER = "__LCSC_3DSHAPES__"


class FetchError(Exception):
    """Raised with a message meant for the user."""


def install_utf8_cache_patch() -> None:
    """Force UTF-8 when easyeda2kicad reads/writes its response cache.

    Upstream opens those files without an explicit encoding, so on cp1252
    Windows any part with non-ASCII metadata (manufacturer "ESPRESSIF(乐鑫)",
    for one) raises UnicodeEncodeError. The library catches and logs it, so
    caching silently never works. Patch it shut.
    """
    if getattr(EasyedaApi, "_utf8_cache_patched", False):
        return

    def _read_from_cache(self, cache_path, binary: bool = False):
        if not self.use_cache or not Path(cache_path).exists():
            return None
        try:
            return Path(cache_path).read_bytes() if binary else Path(cache_path).read_text("utf-8")
        except Exception as err:
            log.debug("cache read skipped for %s: %s", cache_path, err)
            return None

    def _write_to_cache(self, cache_path, data, binary: bool = False) -> None:
        if not self.use_cache:
            return
        try:
            path = Path(cache_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            if binary:
                path.write_bytes(data)
                return
            if path.suffix == ".json":
                try:
                    parsed = json.loads(data) if isinstance(data, str) else data
                    path.write_text(json.dumps(parsed, indent=2, ensure_ascii=False), "utf-8")
                    return
                except (json.JSONDecodeError, TypeError):
                    pass
            path.write_text(data, encoding="utf-8")
        except Exception as err:  # caching is best-effort, never fatal
            log.debug("cache write skipped for %s: %s", cache_path, err)

    EasyedaApi._read_from_cache = _read_from_cache  # type: ignore[method-assign]
    EasyedaApi._write_to_cache = _write_to_cache  # type: ignore[method-assign]
    EasyedaApi._utf8_cache_patched = True  # type: ignore[attr-defined]


@dataclass
class PartInfo:
    lcsc_id: str = ""
    name: str = ""
    prefix: str = ""
    package: str = ""
    manufacturer: str = ""
    mpn: str = ""
    datasheet: str = ""
    description: str = ""


@dataclass
class PartBundle:
    """A staged, previewable part. Commit copies it to its final home."""

    lcsc_id: str
    info: PartInfo
    staging: StagingArea
    folder_name: str
    symbol_name: str = ""
    footprint_name: str = ""
    model_name: str = ""
    pin_count: int = 0
    pad_count: int = 0
    unit_count: int = 1
    # Tier 1 preview: EasyEDA's own geometry. Instant, always available.
    ee_symbol_svg: str = ""
    ee_footprint_svg: str = ""
    # Tier 2 preview: rendered by kicad-cli from the files we generated.
    ki_symbol_svgs: list[Path] = field(default_factory=list)
    ki_footprint_svg: Path | None = None
    obj_path: Path | None = None
    obj_bounds: tuple[tuple[float, float, float], tuple[float, float, float]] | None = None
    has_3d: bool = False
    # Symbol library schema version chosen for the target KiCad.
    sym_format_version: int | None = None
    # (name, value) exactly as written into the .kicad_sym
    properties: list[SymbolProperty] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    # Retained so commit can re-export both with their final names: the
    # footprint needs the final 3D path, the symbol needs the final nickname.
    _ee_footprint: Any = None
    _ee_symbol: Any = None

    @property
    def has_kicad_symbol_render(self) -> bool:
        return bool(self.ki_symbol_svgs)

    @property
    def has_kicad_footprint_render(self) -> bool:
        return self.ki_footprint_svg is not None

    def warn(self, message: str) -> None:
        if message not in self.warnings:
            self.warnings.append(message)


class _WarningCollector(logging.Handler):
    """Capture easyeda2kicad's log records — it reports failures only that way."""

    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        if record.name.startswith("lcsc_kicad_gui"):
            return
        try:
            self.messages.append(record.getMessage())
        except Exception:
            pass


def _online() -> bool:
    try:
        socket.create_connection(("easyeda.com", 443), timeout=6).close()
        return True
    except OSError:
        return False


def normalize_lcsc_id(text: str) -> str:
    cleaned = text.strip().upper().removeprefix("LCSC").strip()
    if cleaned.isdigit():
        cleaned = "C" + cleaned
    return cleaned


def fetch_part(
    lcsc_id: str,
    install: KicadInstall | None = None,
    cache_dir: Path | None = None,
    include_hidden_pins: bool = True,
    progress: Callable[[str], None] = lambda _msg: None,
) -> PartBundle:
    """Fetch, convert into a staging folder, and render previews."""
    install_utf8_cache_patch()

    lcsc_id = normalize_lcsc_id(lcsc_id)
    if not LCSC_ID_RE.match(lcsc_id):
        raise FetchError(f"'{lcsc_id}' is not an LCSC part number (expected e.g. C54951858).")

    collector = _WarningCollector()
    logging.getLogger().addHandler(collector)
    try:
        bundle = _fetch(lcsc_id, install, cache_dir, include_hidden_pins, progress)
    finally:
        logging.getLogger().removeHandler(collector)

    for message in collector.messages:
        bundle.warn(message)
    return bundle


def _fetch(
    lcsc_id: str,
    install: KicadInstall | None,
    cache_dir: Path | None,
    include_hidden_pins: bool,
    progress: Callable[[str], None],
) -> PartBundle:
    api = EasyedaApi(use_cache=bool(cache_dir))
    if cache_dir:
        # Upstream defaults this to Path.cwd(), which is a landmine in a GUI.
        api.cache_dir = Path(cache_dir)

    progress(f"Fetching {lcsc_id} from EasyEDA…")
    cad = api.get_cad_data_of_component(lcsc_id=lcsc_id)
    if not cad:
        # The library swallows every exception and returns {}, so work out why.
        if not _online():
            raise FetchError("Can't reach easyeda.com. Check your network and try again.")
        raise FetchError(f"EasyEDA has no CAD data for {lcsc_id}. Check the part number.")

    progress("Converting symbol…")
    ee_symbol = EasyedaSymbolImporter(easyeda_cp_cad_data=cad).get_symbol()
    info = PartInfo(
        lcsc_id=lcsc_id,
        name=ee_symbol.info.name,
        prefix=ee_symbol.info.prefix,
        package=ee_symbol.info.package,
        manufacturer=ee_symbol.info.manufacturer,
        mpn=ee_symbol.info.mpn,
        datasheet=ee_symbol.info.datasheet,
        description=ee_symbol.info.description or cad.get("description", ""),
    )

    folder_name = folder_name_for(lcsc_id, info.mpn or info.name)
    # One name for the folder, the library files and the KiCad nickname.
    staging = StagingArea(lcsc_id, lib_name=folder_name)
    bundle = PartBundle(
        lcsc_id=lcsc_id,
        info=info,
        staging=staging,
        folder_name=folder_name,
        sym_format_version=install.sym_format_version if install else None,
        symbol_name=ee_symbol.info.name,
        pin_count=len(ee_symbol.pins),
        unit_count=1 + len(ee_symbol.sub_symbols or []),
    )

    progress("Reading footprint…")
    ee_footprint = None
    try:
        ee_footprint = EasyedaFootprintImporter(easyeda_cp_cad_data=cad).get_footprint()
    except Exception as err:
        log.warning("footprint import failed: %s", err)
        bundle.warn(f"No footprint could be built: {err}")

    if ee_footprint is not None:
        # The .kicad_mod filename must be filesystem-safe, and the symbol's
        # Footprint field must keep matching it — they come from the same
        # EasyEDA package name, so sanitising one means syncing the other.
        safe = sanitize_name(ee_footprint.info.name, max_len=120)
        if safe != ee_footprint.info.name:
            bundle.warn(f"Footprint name adjusted: {ee_footprint.info.name} -> {safe}")
            ee_footprint.info.name = safe
            ee_symbol.info.package = safe
        bundle.footprint_name = ee_footprint.info.name
        bundle.pad_count = len(ee_footprint.pads)

    # 3D first: the footprint must only reference a model we actually wrote.
    progress("Downloading 3D model…")
    model_3d = None
    try:
        model_3d = Easyeda3dModelImporter(
            easyeda_cp_cad_data=cad, download_raw_3d_model=True, api=api
        ).output
    except Exception as err:  # a network hiccup shouldn't lose the whole part
        log.warning("3D model import failed: %s", err)

    model_exporter = Exporter3dModelKicad(model_3d=model_3d) if model_3d else None
    if model_exporter and model_exporter.output:
        if model_exporter.export(output_dir=str(staging.shapes_dir), overwrite=True):
            bundle.has_3d = True
            bundle.model_name = model_exporter.output.name
    if not bundle.has_3d:
        bundle.warn("No 3D model is available for this part.")

    if model_3d and model_3d.raw_obj:
        split = split_obj(model_3d.raw_obj, staging.preview_dir, stem="model")
        if split:
            bundle.obj_path = split[0]
            bundle.obj_bounds = obj_bounds(model_3d.raw_obj)

    progress("Converting footprint…")
    if ee_footprint is not None:
        staging.pretty_dir.mkdir(parents=True, exist_ok=True)
        exporter = ExporterFootprintKicad(footprint=ee_footprint)
        if not bundle.has_3d:
            # Otherwise the .kicad_mod points at a .wrl that was never written:
            # the model reference comes from EasyEDA metadata, not from the
            # download actually succeeding.
            exporter.output.model_3d = None
        exporter.export(
            footprint_full_path=str(staging.pretty_dir / f"{ee_footprint.info.name}.kicad_mod"),
            model_3d_path=MODEL_PATH_PLACEHOLDER,
        )
        bundle._ee_footprint = ee_footprint

    progress("Writing symbol library…")
    # A fresh exporter per export: tune_footprint_ref_path() mutates
    # info.package in place, so reusing one double-prefixes the Footprint field.
    symbol_exporter = ExporterSymbolKicad(
        symbol=ee_symbol,
        lib_path=None,
        version=bundle.sym_format_version,
    )
    if not symbol_exporter.save_to_lib(
        lib_path=str(staging.sym_path),
        footprint_lib_name=staging.lib_name,
        overwrite=True,
    ):
        raise FetchError(f"Could not write the symbol library for {lcsc_id}.")

    bundle._ee_symbol = ee_symbol
    bundle.properties = read_symbol_properties(staging.sym_path)

    progress("Rendering previews…")
    try:
        bundle.ee_symbol_svg = render_symbol_svg(cad)
        bundle.ee_footprint_svg = render_footprint_svg(cad)
    except Exception as err:
        log.warning("EasyEDA preview render failed: %s", err)

    if install:
        bundle.ki_symbol_svgs = render.render_symbol(
            install,
            staging.sym_path,
            ee_symbol.info.name,
            staging.preview_dir / "sym",
            include_hidden_pins,
        )
        if bundle.ki_symbol_svgs:
            bundle.unit_count = max(bundle.unit_count, len(bundle.ki_symbol_svgs))
        if ee_footprint is not None:
            bundle.ki_footprint_svg = render.render_footprint(
                install,
                staging.pretty_dir,
                ee_footprint.info.name,
                staging.preview_dir / "fp",
            )
    else:
        bundle.warn("KiCad was not found, so previews show EasyEDA's drawing, not KiCad's.")

    return bundle
