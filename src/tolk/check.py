"""Run status from the tail of a file.

A program says how it ended on its last few lines, so the whole question is
answerable from a few kilobytes. That is what makes checking a directory of
several hundred calculations take seconds rather than minutes.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass

from . import _sniff, registry
from .source import Source
from .spec import Spec

# How much of the end to read. Large enough for a timing table and a
# terminator, small enough to be one or two pages.
TAIL_BYTES = 8192

# A file with no terminator that was written to recently is most likely still
# being written to. Beyond this it is more likely to have died.
RUNNING_WINDOW = 300.0

OK = "ok"
ERROR = "error"
RUNNING = "running"
UNKNOWN = "unknown"


@dataclass(frozen=True)
class Status:
    """How one file ended."""

    path: str
    state: str
    detail: str | None = None
    format: str | None = None

    @property
    def ok(self) -> bool:
        return self.state == OK

    def __bool__(self) -> bool:
        return self.ok

    def __str__(self) -> str:
        if self.detail:
            return f"{self.state:8s} {self.path}  {self.detail}"
        return f"{self.state:8s} {self.path}"


def check(
    path: str | os.PathLike[str],
    *,
    format: str | None = None,
    tail_bytes: int = TAIL_BYTES,
    running_window: float = RUNNING_WINDOW,
    now: float | None = None,
) -> Status:
    """Say whether a run finished, failed, or is still going."""
    with Source(path) as src:
        spec = _spec_for(src, format)
        if spec is None:
            return Status(src.path, UNKNOWN, "no spec for this format")

        if not spec.terminators.ok and not spec.terminators.error:
            return Status(
                src.path, UNKNOWN, "spec declares no terminators", spec.format
            )

        tail = src.tail(tail_bytes)

        # Error markers are checked first. A file can hold both when a run
        # dies after printing something that looks like success.
        for marker in spec.terminators.error:
            if marker in tail:
                return Status(
                    src.path, ERROR, marker.decode(errors="replace"), spec.format
                )
        for marker in spec.terminators.ok:
            if marker in tail:
                return Status(src.path, OK, None, spec.format)

        return Status(
            src.path, _unterminated(src.path, running_window, now), None, spec.format
        )


def check_many(
    paths: list[str] | list[os.PathLike[str]], **kwargs: object
) -> list[Status]:
    """Check several files, in the order given."""
    return [check(path, **kwargs) for path in paths]  # type: ignore[arg-type]


def _spec_for(src: Source, format: str | None) -> Spec | None:
    if format is not None:
        return registry.get(format)
    registry.load_all()
    detected = _sniff.sniff_source(src)
    if detected is None:
        return None
    try:
        return registry.get(detected)
    except Exception:
        return None


def _unterminated(path: str, window: float, now: float | None) -> str:
    """No terminator found, so decide between still running and dead."""
    try:
        age = (time.time() if now is None else now) - os.path.getmtime(path)
    except OSError:
        return UNKNOWN
    return RUNNING if age <= window else UNKNOWN
