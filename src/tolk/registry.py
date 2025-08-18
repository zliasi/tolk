"""Where specs come from.

Specs are looked up by format name across a search path. Shipped specs are
the base layer, user specs override them by name, so fixing a spec for your
own site never means editing the installed package.
"""

from __future__ import annotations

import os
import pathlib

from . import _sniff
from .spec import Spec, SpecError, load

# Colon separated extra directories, highest priority last.
SPEC_PATH_ENV = "TOLK_SPECS"

_BUILTIN_DIR = pathlib.Path(__file__).parent / "specs"

_CACHE: dict[str, Spec] | None = None


def spec_dirs() -> list[pathlib.Path]:
    """Directories searched for specs, lowest priority first."""
    dirs = [d for d in sorted(_BUILTIN_DIR.glob("*")) if d.is_dir()]
    dirs.append(pathlib.Path.home() / ".config" / "tolk" / "specs")
    for entry in os.environ.get(SPEC_PATH_ENV, "").split(os.pathsep):
        if entry:
            dirs.append(pathlib.Path(entry).expanduser())
    return dirs


def load_all(*, refresh: bool = False) -> dict[str, Spec]:
    """Every reachable spec, keyed by format name.

    A later directory wins, so a user spec silently replaces the shipped one
    of the same name. That is the point, and the replaced file is still
    visible through Spec.source when something looks wrong.
    """
    global _CACHE
    if _CACHE is not None and not refresh:
        return _CACHE

    found: dict[str, Spec] = {}
    for directory in spec_dirs():
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.toml")):
            spec = load(path)
            found[spec.format] = spec

    _CACHE = found
    _publish_signatures(found)
    return found


def get(fmt: str) -> Spec:
    """The spec for a format name."""
    specs = load_all()
    try:
        return specs[fmt]
    except KeyError:
        known = ", ".join(sorted(specs)) or "none"
        raise SpecError(f"no spec for format {fmt!r}, known: {known}") from None


def formats() -> list[str]:
    """Every format name a spec is available for."""
    return sorted(load_all())


def refresh() -> None:
    """Drop the cache, for tests and for editing specs in a live session."""
    global _CACHE
    _CACHE = None


def _publish_signatures(specs: dict[str, Spec]) -> None:
    """Give the sniffer what the specs know about recognising their format."""
    for spec in specs.values():
        if not spec.contains and not spec.extensions:
            continue
        _sniff.register(
            _sniff.Signature(
                format=spec.format,
                contains=spec.contains,
                extensions=spec.extensions,
                priority=spec.priority,
            )
        )
