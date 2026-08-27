# LCSC → KiCad Downloader

Type an LCSC part number, look at the symbol, footprint and 3D model, then save
a folder KiCad can import. A GUI alternative to running the
[`easyeda2kicad`](https://github.com/uPesy/easyeda2kicad.py) CLI blind.

![tabs: Symbol / Footprint / 3D](#)

## Why the preview is trustworthy

The part is converted to real KiCad files *before* anything is shown, into a
temporary staging folder. The Symbol and Footprint tabs are then rendered by
`kicad-cli` from those exact files — so you are looking at KiCad's own drawing
of what you are about to import, not at EasyEDA's drawing of the source data.
Pressing **Download** copies the staged folder; nothing is re-converted.

If KiCad isn't installed, previews fall back to EasyEDA's rendering and the
badge under the part details says so.

## Setup

Needs Python 3.10 and, for the KiCad-accurate previews, KiCad 8, 9 or 10.

```
setup.bat
```

Creates `.venv` and installs PySide6 + easyeda2kicad. Then:

```
run.bat
```

## Using it

1. Type or paste a part number — `C54951858`. Paste several (separated by
   spaces, commas or newlines) to queue them.
2. Check the three tabs.
   - **Symbol** — the drawing on the left, the fields KiCad will attach to the
     placed symbol on the right. Greyed rows are hidden on the schematic sheet.
     Right-click a row to copy it. Drag the divider to resize.
   - **Footprint** — scroll to zoom, drag to pan, double-click to fit.
   - **3D** — left-drag to pan, right-drag to rotate, scroll to zoom,
     double-click to re-frame.
3. Pick the KiCad version in the top-right — it sets the `.kicad_sym` format
   version, so choose the KiCad you actually use. **A KiCad 10 library cannot
   be opened by KiCad 9 or 8.**
4. **Download**. Each part becomes its own folder:

```
C54951858_ESP32-C5-WROOM-1U-N8R8-V1.2/
├── C54951858.kicad_sym
├── C54951858.pretty/
│   └── COMM-SMD_32P-L21.2-W18.0_ESP32-C5-WROOM-1U.kicad_mod
└── C54951858.3dshapes/
    ├── COMM-SMD_32P-….step
    └── COMM-SMD_32P-….wrl
```

5. A dialog then shows the two library-table rows KiCad needs. Copy them in
   yourself, or press **Register in KiCad** to have them appended (a
   timestamped backup is written first). Close KiCad before registering — it
   rewrites those tables when it exits.

## Notes

- One folder per part means two library-table rows per part. The tables grow as
  you download; registration is always optional.
- 3D preview uses Qt Quick 3D. If your GPU stack can't start it, the tab shows
  a message and everything else keeps working — the STEP and WRL files still
  download. `run.bat --no-3d` disables it outright.
- Settings live in `settings.ini` next to the app. Delete it to reset.
- `easyeda2kicad` is AGPL-3.0, and this imports it as a library. That matters
  if you publish or host this; for personal use there is nothing to do.

## Command line

```
run.bat --debug     verbose logging
run.bat --no-3d     disable the 3D tab
```
