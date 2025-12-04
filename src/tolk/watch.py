"""Following a file that is still being written.

A running calculation is the one case where reading the same file twice is
not waste. Watching means re-reading only what has been appended, which the
byte layer already makes cheap: remember the size, and start the next scan
there.
"""

from __future__ import annotations

import os
import time
from collections.abc import Iterator
from dataclasses import dataclass

from . import _check, _sniff, registry
from .extract import extract
from .source import Source
from .spec import Spec, SpecError
from .value import Value

POLL = 2.0


@dataclass(frozen=True)
class Update:
    """One observation of a file that is being written."""

    path: str
    value: Value
    size: int
    state: str

    @property
    def finished(self) -> bool:
        return self.state in (_check.OK, _check.ERROR)


def follow(
    path: str | os.PathLike[str],
    quantity: str,
    *,
    format: str | None = None,
    poll: float = POLL,
    limit: int | None = None,
) -> Iterator[Update]:
    """Yield the quantity again each time the file grows.

    Stops when the run terminates, so a caller can simply iterate to
    completion. Nothing is yielded while the file is unchanged, which is what
    makes polling cheap.
    """
    target = os.fspath(path)
    seen = -1
    produced = 0

    while True:
        try:
            size = os.path.getsize(target)
        except OSError:
            time.sleep(poll)
            continue

        if size != seen:
            seen = size
            with Source(target) as src:
                spec = registry.get(format) if format else _detect(src)
                value = extract(src, spec, quantity)
            status = _check.check(target, format=spec.format)
            yield Update(target, value, size, status.state)
            produced += 1
            if status.state in (_check.OK, _check.ERROR):
                return
            if limit is not None and produced >= limit:
                return

        time.sleep(poll)


def _detect(src: Source) -> Spec:
    registry.load_all()
    detected = _sniff.sniff_source(src)
    if detected is None:
        raise SpecError(f"{src.path}: could not detect a format, pass format=")
    return registry.get(detected)
