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
