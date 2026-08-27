# SPDX-FileCopyrightText: 2026 somsinchai
# SPDX-License-Identifier: AGPL-3.0-only
"""Entry point for the packaged build, and for `python main.py` from source.

PyInstaller runs its entry script as a top-level module named `__main__`, so
the package's own `__main__.py` cannot be used - its relative imports have no
parent package to resolve against.
"""

import sys

from lcsc_kicad_gui.app import main

if __name__ == "__main__":
    sys.exit(main(sys.argv))
