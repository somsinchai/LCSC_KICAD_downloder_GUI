# Third-party components in this build

LCSC KiCad Downloader is Copyright © 2026 somsinchai and is licensed under the
**GNU Affero General Public License, version 3 only (AGPL-3.0-only)**. The full
text is in `LICENSE`.

## Complete Corresponding Source

The complete source code for this program, including the build scripts used to
produce this binary, is published at:

**<https://github.com/somsinchai/LCSC_KICAD_downloder_GUI>**

Each binary release is built from the matching tag in that repository, and the
source for that tag is downloadable from the same release page. This satisfies
AGPL-3.0 section 6(d).

---

## Bundled components

### Qt 6 / PySide6 — LGPL-3.0-only

Copyright © The Qt Company Ltd. and other contributors.

This application uses the Qt toolkit through PySide6, under the terms of the
**GNU Lesser General Public License version 3**. Qt is dynamically linked and
its libraries ship as separate files in this folder — you may replace them with
your own build of Qt of the same major version, which is why this program is
distributed as a folder rather than a single self-extracting executable.

- Qt source code: <https://download.qt.io/official_releases/qt/>
- PySide6 source: <https://code.qt.io/cgit/pyside/pyside-setup.git/>
- LGPL-3.0 text: <https://www.gnu.org/licenses/lgpl-3.0.txt>
- Qt licensing: <https://www.qt.io/qt-licensing>

Qt Quick 3D additionally bundles **Assimp** (Open Asset Import Library),
3-clause BSD licence — <https://github.com/assimp/assimp/blob/master/LICENSE>

### easyeda2kicad — AGPL-3.0-only

Copyright © uPesy and contributors.
<https://github.com/uPesy/easyeda2kicad.py>

Does all of the EasyEDA → KiCad conversion. It is used **unmodified**, exactly
as published on PyPI. Because this program imports it in-process, the two form
a single combined work, which is why this program is also AGPL-3.0-only.

### Python — PSF License 2.0

Copyright © Python Software Foundation.
<https://docs.python.org/3/license.html>

---

## Not bundled

**KiCad** (<https://www.kicad.org/>, GPL-3.0-or-later) is *not* included. If you
have it installed, this program runs `kicad-cli.exe` as a separate process to
render the previews. Calling a separate program at arm's length does not make
the two a combined work.
