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
