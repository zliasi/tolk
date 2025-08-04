"""Backend primitives.

This module is the backend boundary. Every function takes a haystack plus
byte offsets and returns byte offsets, never parsed values. The C engine
implements exactly these signatures, so swapping backends changes nothing
above this line.

A haystack is anything with bytes-like find and rfind taking start and end,
which covers both bytes and mmap. memoryview does not qualify, which is why
Source keeps the underlying object around alongside its view.
"""

from __future__ import annotations

import mmap
from collections.abc import Iterator

Haystack = bytes | mmap.mmap

# Which implementation is in use. The C engine overrides this when it loads.
BACKEND = "python"


def find(
    haystack: Haystack, needle: bytes, start: int = 0, end: int | None = None
) -> int:
    """First occurrence of needle in [start, end), or -1."""
    if end is None:
        return haystack.find(needle, start)
    return haystack.find(needle, start, end)


def rfind(
    haystack: Haystack, needle: bytes, start: int = 0, end: int | None = None
) -> int:
    """Last occurrence of needle in [start, end), or -1."""
    if end is None:
        return haystack.rfind(needle, start)
    return haystack.rfind(needle, start, end)


def iter_find(
    haystack: Haystack, needle: bytes, start: int = 0, end: int | None = None
) -> Iterator[int]:
    """Every occurrence in [start, end), left to right.

    Matches do not overlap, which is what anchors want and what bytes.count
    reports.
    """
    _check_needle(needle)
    step = len(needle)
    pos = start
    while True:
        hit = find(haystack, needle, pos, end)
        if hit < 0:
            return
        yield hit
        pos = hit + step


def iter_rfind(
    haystack: Haystack, needle: bytes, start: int = 0, end: int | None = None
) -> Iterator[int]:
    """Every occurrence in [start, end), right to left."""
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


def count(
    haystack: Haystack, needle: bytes, start: int = 0, end: int | None = None
) -> int:
    """How many non-overlapping occurrences lie in [start, end)."""
    _check_needle(needle)
    return sum(1 for _ in iter_find(haystack, needle, start, end))


def find_nth(
    haystack: Haystack,
    needle: bytes,
    n: int,
    start: int = 0,
    end: int | None = None,
) -> int:
    """Offset of the nth occurrence, or -1.

    n is zero based from the left. Negative n counts from the right, so -1
    is the last occurrence, which is the common case for output files where
    a quantity is printed once per cycle.
    """
    _check_needle(needle)
    if n >= 0:
        walker = iter_find(haystack, needle, start, end)
        wanted = n
    else:
        walker = iter_rfind(haystack, needle, start, end)
        wanted = -n - 1
    for i, hit in enumerate(walker):
        if i == wanted:
            return hit
    return -1


def _check_needle(needle: bytes) -> None:
    if not needle:
        raise ValueError("needle must not be empty")


NEWLINE = b"\n"


def line_start(haystack: Haystack, offset: int) -> int:
    """Offset where the line containing offset begins.

    An offset sitting on a newline belongs to the line that newline ends,
    not the one it starts.
    """
    nl = rfind(haystack, NEWLINE, 0, offset)
    return 0 if nl < 0 else nl + 1


def line_end(haystack: Haystack, offset: int) -> int:
    """Offset just past the content of the line containing offset.

    The newline itself is excluded, and so is a carriage return before it,
    so the span is the line's text rather than its bytes on disk.
    """
    nl = find(haystack, NEWLINE, offset)
    if nl < 0:
        nl = len(haystack)
    if nl > offset and haystack[nl - 1 : nl] == b"\r":
        return nl - 1
    return nl


def line_span(haystack: Haystack, offset: int) -> tuple[int, int]:
    """Content span of the line containing offset."""
    return line_start(haystack, offset), line_end(haystack, offset)


def iter_line_spans(
    haystack: Haystack, start: int = 0, end: int | None = None
) -> Iterator[tuple[int, int]]:
    """Content spans of the lines overlapping [start, end).

    Lines are found as they are needed, so nothing outside the requested
    region is ever touched. The first line is entered at its true start even
    if start lands mid line.
    """
    size = len(haystack)
    if size == 0:
        return
    limit = size if end is None else min(end, size)
    pos = line_start(haystack, start)
    while pos <= limit:
        stop = line_end(haystack, pos)
        yield pos, stop
        nl = find(haystack, NEWLINE, stop)
        if nl < 0:
            return
        pos = nl + 1
        # A trailing newline ends the last line, it does not open an empty
        # one. Blank lines in the middle of the file still come through.
        if pos >= size or pos > limit:
            return


def advance_lines(haystack: Haystack, offset: int, n: int) -> int:
    """Start offset of the line n lines away from the one holding offset.

    Walks off the end to the file size, and off the front to zero, rather
    than failing, so callers can clamp instead of guarding every step.
    """
    pos = line_start(haystack, offset)
    if n > 0:
        for _ in range(n):
            nl = find(haystack, NEWLINE, pos)
            if nl < 0:
                return len(haystack)
            pos = nl + 1
    else:
        for _ in range(-n):
            if pos == 0:
                return 0
            pos = line_start(haystack, pos - 1)
    return pos


def line_number(haystack: Haystack, offset: int) -> int:
    """One based line number of offset.

    This is the one operation that has to read everything before the offset,
    so it stays opt in and is only used for provenance and error messages.
    """
    return count(haystack, NEWLINE, 0, line_start(haystack, offset)) + 1
