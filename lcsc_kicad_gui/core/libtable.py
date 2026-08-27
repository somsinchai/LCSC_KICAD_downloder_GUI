"""Append library rows to KiCad's sym-lib-table / fp-lib-table.

Deliberately *parses for information and splices for modification*: a full
parse/serialise round trip would rewrite every row in the file, normalising
whitespace and quoting on lines we have no business touching — including
KiCad 10's nested `(lib (name "KiCad") (type "Table") …)` reference and any
hand-edited entries. We only ever read nicknames and insert one row.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .kicad_env import CREATE_NO_WINDOW

KEEP_BACKUPS = 5


@dataclass
class TableInfo:
    head: str  # "sym_lib_table" or "fp_lib_table"
    entries: dict[str, tuple[int, int]]  # nickname -> (span start, span end)
    insert_pos: int  # offset of the closing paren of the top-level form


@dataclass
class AddResult:
    added: bool = False
    replaced: bool = False
    unchanged: bool = False
    backup: Path | None = None


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def format_row(nickname: str, uri: Path | str, descr: str = "") -> str:
    """One `(lib …)` row, fully quoted — accepted by KiCad 8, 9 and 10 alike."""
    path = Path(uri).as_posix() if isinstance(uri, Path) else str(uri)
    return (
        f'(lib (name "{_escape(nickname)}")(type "KiCad")(uri "{_escape(path)}")'
        f'(options "")(descr "{_escape(descr)}"))'
    )


def _iter_tokens(text: str):
    """Yield ``(kind, start, end)`` for parens, quoted strings and atoms."""
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch.isspace():
            i += 1
        elif ch == "(":
            yield "(", i, i + 1
            i += 1
        elif ch == ")":
            yield ")", i, i + 1
            i += 1
        elif ch == '"':
            j = i + 1
            while j < n:
                if text[j] == "\\":
                    j += 2
                    continue
                if text[j] == '"':
                    break
                j += 1
            yield "string", i, min(j + 1, n)
            i = min(j + 1, n)
        else:
            j = i
            while j < n and not text[j].isspace() and text[j] not in '()"':
                j += 1
            yield "atom", i, j
            i = j


def _unquote(text: str) -> str:
    if len(text) >= 2 and text[0] == '"':
        return text[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    return text


def scan(text: str) -> TableInfo:
    """Locate the top-level form, its `(lib …)` children and the insert point."""
    tokens = list(_iter_tokens(text))
    head = ""
    depth = 0
    entries: dict[str, tuple[int, int]] = {}
    insert_pos = len(text)

    lib_start: int | None = None
    lib_name: str | None = None
    expect_head = False
    # Inside a depth-2 (name …) clause, the next string/atom is the nickname.
    grab_name = False

    for index, (kind, start, end) in enumerate(tokens):
        piece = text[start:end]
        if kind == "(":
            depth += 1
            if depth == 1:
                expect_head = True
            elif depth == 2 and lib_start is None:
                nxt = tokens[index + 1] if index + 1 < len(tokens) else None
                if nxt and text[nxt[1] : nxt[2]] == "lib":
                    lib_start = start
                    lib_name = None
            elif depth == 3 and lib_start is not None:
                nxt = tokens[index + 1] if index + 1 < len(tokens) else None
                grab_name = bool(nxt and text[nxt[1] : nxt[2]] == "name")
            continue
        if kind == ")":
            if depth == 2 and lib_start is not None:
                if lib_name:
                    entries[lib_name] = (lib_start, end)
                lib_start, lib_name = None, None
            if depth == 1:
                insert_pos = start
            depth -= 1
            grab_name = False
            continue
        if expect_head:
            head = piece
            expect_head = False
            continue
        if grab_name and lib_name is None and piece != "name":
            lib_name = _unquote(piece)
            grab_name = False

    return TableInfo(head=head, entries=entries, insert_pos=insert_pos)


def _new_table(kind: str) -> str:
    return f"({kind}\n  (version 7)\n)\n"


def _backup(path: Path, raw: str) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = path.with_name(f"{path.name}.bak-{stamp}")
    backup.write_text(raw, encoding="utf-8", newline="")
    old = sorted(path.parent.glob(f"{path.name}.bak-*"))
    for stale in old[:-KEEP_BACKUPS]:
        stale.unlink(missing_ok=True)
    return backup


def add_row(path: Path, nickname: str, uri: Path | str, descr: str = "") -> AddResult:
    """Insert or update one library row. Idempotent, backed up, atomic."""
    path = Path(path)
    kind = "fp_lib_table" if path.name.startswith("fp") else "sym_lib_table"
    raw = path.read_text(encoding="utf-8") if path.exists() else _new_table(kind)

    info = scan(raw)
    if info.head not in ("sym_lib_table", "fp_lib_table"):
        raise ValueError(f"{path} is not a KiCad library table")

    row = format_row(nickname, uri, descr)
    result = AddResult()

    if nickname in info.entries:
        start, end = info.entries[nickname]
        if raw[start:end] == row:
            return AddResult(unchanged=True)
        updated = raw[:start] + row + raw[end:]
        result.replaced = True
    else:
        updated = raw[: info.insert_pos] + "  " + row + "\n" + raw[info.insert_pos :]
        result.added = True

    result.backup = _backup(path, raw)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(updated, encoding="utf-8", newline="")
    os.replace(tmp, path)  # atomic on the same volume
    return result


def kicad_is_running() -> bool:
    """KiCad rewrites the global tables when it exits, discarding our edits."""
    if os.name != "nt":
        return False
    try:
        out = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq kicad.exe", "/NH"],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=CREATE_NO_WINDOW,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return "kicad.exe" in (out.stdout or "").lower()


def restore_backup(backup: Path) -> None:
    target = backup.with_name(backup.name.split(".bak-")[0])
    shutil.copy2(backup, target)
