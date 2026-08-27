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
