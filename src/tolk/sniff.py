"""Format detection from the first kilobytes of a file.

Detection is content first and extension second. A file named .out says
nothing useful, while the banner a program prints on startup is decisive and
sits within the first page. Signatures are data, so a spec can carry its own
without this module changing.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from .source import Source

# Enough to clear any startup banner without paging in more than one or two
# pages of a large file.
SNIFF_BYTES = 4096


@dataclass(frozen=True)
class Signature:
    """One rule for recognising a format.

    A signature matches when every literal in contains is present in the
    sniffed head. Signatures with no literals match on extension alone, which
    is the weakest evidence and so gets the lowest priority.
    """

    format: str
    contains: tuple[bytes, ...] = ()
    extensions: tuple[str, ...] = ()
    priority: int = 0

    def matches_content(self, head: bytes) -> bool:
        return bool(self.contains) and all(lit in head for lit in self.contains)

    def matches_extension(self, suffix: str) -> bool:
        return suffix.lower() in self.extensions


_REGISTRY: list[Signature] = []


def register(signature: Signature) -> None:
    """Add a signature, highest priority first."""
    _REGISTRY.append(signature)
    _REGISTRY.sort(key=lambda s: -s.priority)


def signatures() -> list[Signature]:
    """Every registered signature, in match order."""
    return list(_REGISTRY)


def sniff(path: str | os.PathLike[str]) -> str | None:
    """Name the format of a file, or None when nothing matches."""
    with Source(path) as src:
        return sniff_source(src)


def sniff_source(src: Source) -> str | None:
    """Name the format of an open source."""
    head = src.head(SNIFF_BYTES)
    suffix = os.path.splitext(src.path)[1]
    for sig in _REGISTRY:
        if sig.matches_content(head):
            return sig.format
    for sig in _REGISTRY:
        if sig.matches_extension(suffix):
            return sig.format
    return None


# Built in signatures. These are the format agnostic ones, so they live here
# rather than in a spec pack. Program specific signatures arrive with the
# specs that need them.
for _sig in (
    Signature("xyz", extensions=(".xyz",), priority=10),
    Signature("csv", extensions=(".csv",), priority=10),
    Signature("tsv", extensions=(".tsv", ".tab"), priority=10),
    # Weakest evidence, so anything with real content wins over it.
    Signature("text", extensions=(".txt", ".log"), priority=-10),
):
    register(_sig)
