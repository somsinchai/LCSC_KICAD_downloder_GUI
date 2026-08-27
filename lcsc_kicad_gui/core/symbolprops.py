"""Read the property fields back out of a generated .kicad_sym.

Reading the file rather than the in-memory model means the table shows exactly
what KiCad will show — including anything the exporter renamed or dropped.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SymbolProperty:
    name: str
    value: str
    hidden: bool = False


def _unescape(text: str) -> str:
    return text.replace('\\"', '"').replace("\\\\", "\\")


def _read_string(text: str, start: int) -> tuple[str, int]:
    """Read the quoted string starting at *start*; returns (value, next index)."""
    end = start + 1
    while end < len(text):
        if text[end] == "\\":
            end += 2
            continue
        if text[end] == '"':
            break
        end += 1
    return _unescape(text[start + 1 : end]), end + 1


def _block_end(text: str, open_paren: int) -> int:
    """Index just past the paren that closes the one at *open_paren*."""
    depth = 0
    i = open_paren
    while i < len(text):
        ch = text[i]
        if ch == '"':
            _, i = _read_string(text, i)
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return len(text)


def read_symbol_properties(sym_path: Path) -> list[SymbolProperty]:
    """Return the symbol's properties in the order the file declares them."""
    path = Path(sym_path)
    if not path.is_file():
        return []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    properties: list[SymbolProperty] = []
    seen: set[str] = set()
    marker = "(property"
    index = 0

    while True:
        index = text.find(marker, index)
        if index == -1:
            break
        # The exporter puts the name on its own line, so don't assume it
        # follows the keyword directly — just take the next two strings.
        block_end = _block_end(text, index)
        block = text[index:block_end]
        cursor = len(marker)

        pair: list[str] = []
        while len(pair) < 2:
            quote = block.find('"', cursor)
            if quote == -1:
                break
            value, cursor = _read_string(block, quote)
            pair.append(value)

        index = block_end
        if len(pair) == 2 and pair[0] and pair[0] not in seen:
            seen.add(pair[0])
            properties.append(
                SymbolProperty(pair[0], pair[1], hidden="(hide yes)" in block)
            )
    return properties
