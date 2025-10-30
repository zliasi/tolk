"""Bindings for the compiled engine.

This module exists to keep the cffi details out of _engine.py. It exposes
the same functions over the same offsets, so installing it is a rebinding
rather than a branch at every call site.

A haystack reaches C as a borrowed buffer. bytes and mmap both support the
buffer protocol, so nothing is copied on the way in and only integers come
back.
"""

from __future__ import annotations

import mmap
from collections.abc import Iterator
from typing import Any

from ._tolk import ffi, lib  # type: ignore[import-not-found]

Haystack = bytes | mmap.mmap

NOT_FOUND = -1


def _buffer(haystack: Haystack) -> tuple[Any, int]:
    view = ffi.from_buffer(haystack)
    return view, len(view)


def find(
    haystack: Haystack, needle: bytes, start: int = 0, end: int | None = None
) -> int:
    buf, size = _buffer(haystack)
    return int(
        lib.tolk_find(
            buf, size, needle, len(needle), start, size if end is None else end
        )
    )


def rfind(
    haystack: Haystack, needle: bytes, start: int = 0, end: int | None = None
) -> int:
    buf, size = _buffer(haystack)
    return int(
        lib.tolk_rfind(
            buf, size, needle, len(needle), start, size if end is None else end
        )
    )


def count(
    haystack: Haystack, needle: bytes, start: int = 0, end: int | None = None
) -> int:
    _check_needle(needle)
    buf, size = _buffer(haystack)
    return int(
        lib.tolk_count(
            buf, size, needle, len(needle), start, size if end is None else end
        )
    )


def find_nth(
    haystack: Haystack,
    needle: bytes,
    n: int,
    start: int = 0,
    end: int | None = None,
) -> int:
    _check_needle(needle)
    buf, size = _buffer(haystack)
    return int(
        lib.tolk_find_nth(
            buf, size, needle, len(needle), n, start, size if end is None else end
        )
    )


# How many offsets to collect per crossing into C. Big enough that most
# files need one call, small enough that the buffer is nothing.
_BATCH = 4096


def find_all(
    haystack: Haystack, needle: bytes, start: int = 0, end: int | None = None
) -> list[int]:
    """Every occurrence, collected in batches.

    Counting first and then filling an exact array reads the file twice,
    which made this slower than the pure-Python loop it was meant to replace.
    Filling a fixed buffer and resuming where it ran out keeps it to one
    pass.
    """
    _check_needle(needle)
    buf, size = _buffer(haystack)
    stop = size if end is None else end
    out = ffi.new("int64_t[]", _BATCH)
    step = len(needle)
    offsets: list[int] = []
    pos = start
    while True:
        written = int(
            lib.tolk_find_all(buf, size, needle, step, pos, stop, out, _BATCH)
        )
        if written == 0:
            return offsets
        offsets.extend(int(out[i]) for i in range(written))
        if written < _BATCH:
            return offsets
        pos = offsets[-1] + step


def iter_find(
    haystack: Haystack, needle: bytes, start: int = 0, end: int | None = None
) -> Iterator[int]:
    _check_needle(needle)
    return iter(find_all(haystack, needle, start, end))


def iter_rfind(
    haystack: Haystack, needle: bytes, start: int = 0, end: int | None = None
) -> Iterator[int]:
    """Every occurrence, right to left.

    This walks backwards rather than reversing a forward scan. The two are
    not the same for a needle that overlaps itself, since greedy
    non-overlapping matching depends on which end you start from, and the
    backward walk is also what makes find_nth(-1) cost the distance from the
    end rather than the length of the file.
    """
    _check_needle(needle)
    step = len(needle)
    stop = end
    while True:
        hit = rfind(haystack, needle, start, stop)
        if hit < 0:
            return
        yield hit
        if hit <= start:
            return
        stop = hit + step - 1


def line_start(haystack: Haystack, offset: int) -> int:
    buf, size = _buffer(haystack)
    return int(lib.tolk_line_start(buf, size, offset))


def line_end(haystack: Haystack, offset: int) -> int:
    buf, size = _buffer(haystack)
    return int(lib.tolk_line_end(buf, size, offset))


def line_span(haystack: Haystack, offset: int) -> tuple[int, int]:
    buf, size = _buffer(haystack)
    return (
        int(lib.tolk_line_start(buf, size, offset)),
        int(lib.tolk_line_end(buf, size, offset)),
    )


def advance_lines(haystack: Haystack, offset: int, n: int) -> int:
    buf, size = _buffer(haystack)
    return int(lib.tolk_advance_lines(buf, size, offset, n))


def line_number(haystack: Haystack, offset: int) -> int:
    buf, size = _buffer(haystack)
    return int(lib.tolk_line_number(buf, size, offset))


def _check_needle(needle: bytes) -> None:
    if not needle:
        raise ValueError("needle must not be empty")


# Functions the C backend replaces. iter_line_spans and block_span stay in
# Python because they are loops over these primitives, not hot paths of their
# own.
REPLACES = (
    "find",
    "rfind",
    "count",
    "find_nth",
    "iter_find",
    "iter_rfind",
    "line_start",
    "line_end",
    "line_span",
    "advance_lines",
    "line_number",
)


def install(namespace: dict[str, Any]) -> str:
    """Rebind the pure-Python primitives onto the compiled ones."""
    here = globals()
    for name in REPLACES:
        namespace[name] = here[name]
    namespace["find_all"] = find_all
    namespace["scan_columns"] = scan_columns
    namespace["write_rows"] = write_rows
    return "c"


# Rows collected per crossing into C when a block's length is unknown.
_ROWS = 4096


def scan_columns(
    haystack: Haystack, start: int, end: int, cols: list[int]
) -> list[list[float | None]]:
    """Parse numeric columns out of a block in one call.

    This is the fast path for tables. Doing it field by field means a Python
    float() call per cell, which dominates everything else when a block runs
    to thousands of rows. Here the whole block is split and converted in C
    and only the finished numbers cross back.

    Unparseable fields come back as None, so the caller keeps its own rule
    about which rows count as data.
    """
    buf, size = _buffer(haystack)
    ncols = len(cols)
    if ncols == 0:
        return []
    col_array = ffi.new("int64_t[]", cols)
    out = ffi.new("double[]", _ROWS * ncols)

    rows: list[list[float | None]] = []
    pos = start
    while True:
        written = int(
            lib.tolk_scan_columns(buf, size, pos, end, col_array, ncols, out, _ROWS)
        )
        if written == 0:
            return rows
        flat = ffi.unpack(out, written * ncols)
        for r in range(written):
            row = flat[r * ncols : (r + 1) * ncols]
            rows.append([None if v != v else v for v in row])
        if written < _ROWS:
            return rows
        # Resume after the last line consumed. Walking forward from the end
        # of the buffer we filled is the only way to know where that was.
        pos = _resume(haystack, pos, written)


def _resume(haystack: Haystack, pos: int, rows: int) -> int:
    """Start of the line after the rows already collected."""
    buf, size = _buffer(haystack)
    at = pos
    taken = 0
    while taken < rows:
        line_to = int(lib.tolk_line_end(buf, size, at))
        nxt = int(lib.tolk_find(buf, size, b"\n", 1, line_to, size))
        if nxt < 0:
            return size
        if line_to > at:
            taken += 1
        at = nxt + 1
    return at


# Starting arena size. Rows are short, so this covers a few thousand of them
# before the buffer has to grow.
_ARENA = 1 << 16


def write_rows(
    rows: list[list[object]], delimiter: str = ",", precision: int = 17
) -> bytes:
    """Format a table of scalars straight into bytes.

    Building the same output in Python means a str() per cell and a join over
    the lot. Here the numbers are converted in C into one arena and the whole
    thing comes back as a single bytes object.
    """
    sep = delimiter.encode()
    newline = b"\n"
    cap = _ARENA
    while True:
        out = ffi.new("char[]", cap)
        at = 0
        overflow = False
        for row in rows:
            for index, cell in enumerate(row):
                if index:
                    at = int(lib.tolk_write_bytes(out, cap, at, sep, len(sep)))
                    if at < 0:
                        overflow = True
                        break
                at = _write_cell(out, cap, at, cell)
                if at < 0:
                    overflow = True
                    break
            if overflow:
                break
            at = int(lib.tolk_write_bytes(out, cap, at, newline, 1))
            if at < 0:
                overflow = True
                break
        if not overflow:
            return bytes(ffi.buffer(out, at))
        cap *= 2


def _write_cell(out: Any, cap: int, at: int, cell: object) -> int:
    if cell is None:
        return at
    if isinstance(cell, bool):
        text = b"true" if cell else b"false"
        return int(lib.tolk_write_bytes(out, cap, at, text, len(text)))
    if isinstance(cell, int):
        return int(lib.tolk_write_int(out, cap, at, cell))
    if isinstance(cell, float):
        return int(lib.tolk_write_double(out, cap, at, cell, 0))
    text = str(cell).encode()
    return int(lib.tolk_write_bytes(out, cap, at, text, len(text)))
