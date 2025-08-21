"""The convenience layer.

Everything here is a thin wrapper over Source, the registry, and extraction.
It exists so the common case is one call, while the pieces underneath stay
usable on their own for anything the wrapper does not cover.
"""

from __future__ import annotations

import os

from . import _explain, _sniff, registry
from .extract import extract, extract_many
from .source import Source
from .spec import Spec, SpecError
from .value import Value


def sniff(path: str | os.PathLike[str]) -> str | None:
    """Name the format of a file, or None when nothing matches.

    Loading the registry is what teaches the sniffer about spec signatures,
    so it has to happen first. The raw sniffer in _sniff only knows the
    format agnostic builtins.
    """
    registry.load_all()
    return _sniff.sniff(path)


def formats() -> list[str]:
    """Every format a spec is available for."""
    return registry.formats()


def spec(fmt: str) -> Spec:
    """The spec for a format name."""
    return registry.get(fmt)


def get(
    path: str | os.PathLike[str],
    quantities: str | list[str],
    *,
    format: str | None = None,
    with_lines: bool = False,
) -> Value | dict[str, Value]:
    """Read one or more quantities out of a file.

    A single quantity name returns one Value, a list returns a dict keyed by
    name. The format is sniffed unless given.
    """
    with Source(path) as src:
        resolved = _resolve(src, format)
        if isinstance(quantities, str):
            return extract(src, resolved, quantities, with_lines=with_lines)
        return extract_many(src, resolved, quantities, with_lines=with_lines)


def explain(
    path: str | os.PathLike[str], quantity: str, *, format: str | None = None
) -> str:
    """Trace how a spec reads one quantity, rendered for a terminal."""
    with Source(path) as src:
        return _explain.explain_text(src, _resolve(src, format), quantity)


def _resolve(src: Source, format: str | None) -> Spec:
    if format is not None:
        return registry.get(format)
    registry.load_all()
    detected = _sniff.sniff_source(src)
    if detected is None:
        raise SpecError(
            f"{src.path}: could not detect a format, pass format= explicitly. "
            f"known: {', '.join(formats()) or 'none'}"
        )
    return registry.get(detected)
