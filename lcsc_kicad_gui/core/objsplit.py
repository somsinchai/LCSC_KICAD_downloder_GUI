"""Turn EasyEDA's OBJ blob into an assimp-loadable .obj + .mtl pair.

EasyEDA serves geometry and materials in a single file, with `newmtl ... endmtl`
blocks inlined and no `mtllib` directive. Assimp (which backs QtQuick3D's
RuntimeLoader) will not read materials in that form, so split them apart.
"""

from __future__ import annotations

import re
from pathlib import Path

from easyeda2kicad.kicad.export_kicad_3d_model import get_materials

_MATERIAL_BLOCK = re.compile(r"newmtl .*?endmtl\n?", re.DOTALL)


def _mtl_text(raw_obj: str) -> str:
    """Rebuild the material blocks as a standards-compliant .mtl file."""
    lines: list[str] = ["# extracted from EasyEDA inline materials"]
    for name, material in get_materials(raw_obj).items():
        lines.append(f"newmtl {name}")
        for key, prop in (("Ka", "ambient_color"), ("Kd", "diffuse_color"), ("Ks", "specular_color")):
            value = material.get(prop)
            if isinstance(value, list) and value:
                lines.append(f"{key} {' '.join(value)}")
        transparency = material.get("transparency")
        if isinstance(transparency, str):
            try:
                # OBJ `d` is opacity; EasyEDA stores transparency. Invert.
                lines.append(f"d {max(0.0, min(1.0, 1.0 - float(transparency))):.4f}")
            except ValueError:
                pass
        lines.append("")
    return "\n".join(lines)


def obj_bounds(raw_obj: str) -> tuple[tuple[float, float, float], tuple[float, float, float]] | None:
    """Axis-aligned bounds of the OBJ vertices, as (min xyz, max xyz).

    Computed here rather than read back from QML: Qt's RuntimeLoader.bounds is
    not reliably readable from Python, and we already have the vertex data.
    """
    lo = [float("inf")] * 3
    hi = [float("-inf")] * 3
    found = False
    for line in raw_obj.splitlines():
        parts = line.split()
        if len(parts) < 4 or parts[0] != "v":
            continue
        try:
            values = [float(parts[1]), float(parts[2]), float(parts[3])]
        except ValueError:
            continue
        found = True
        for axis in range(3):
            lo[axis] = min(lo[axis], values[axis])
            hi[axis] = max(hi[axis], values[axis])
    if not found:
        return None
    return (lo[0], lo[1], lo[2]), (hi[0], hi[1], hi[2])


def split_obj(raw_obj: str, out_dir: Path, stem: str = "model") -> tuple[Path, Path] | None:
    """Write ``<stem>.obj`` and ``<stem>.mtl`` into *out_dir*.

    Returns the two paths, or ``None`` if the blob holds no usable geometry.
    """
    if not raw_obj or "v " not in raw_obj:
        return None

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    obj_path = out_dir / f"{stem}.obj"
    mtl_path = out_dir / f"{stem}.mtl"

    geometry = _MATERIAL_BLOCK.sub("", raw_obj)
    geometry = re.sub(r"\n{3,}", "\n\n", geometry).strip()

    obj_path.write_text(f"mtllib {mtl_path.name}\n{geometry}\n", encoding="utf-8")
    mtl_path.write_text(_mtl_text(raw_obj), encoding="utf-8")
    return obj_path, mtl_path
