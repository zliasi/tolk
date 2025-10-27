"""Work across many files.

One file at a time was never the interesting case. A sweep over a directory
of calculations is, and there the cost is dominated by opening files and
faulting pages in, which is where threads actually help.

The engine holds no mutable global state, so running it from several threads
is safe. Python's own bytecode still serialises, so the gain is on the IO
side rather than the parsing side, and it is real but bounded.
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable, TypeVar

from . import _check, _sniff, registry
from .extract import extract
from .record import Table
from .source import Source
from .spec import Spec, SpecError
from .value import Value

T = TypeVar("T")

# More threads than this stops helping, since the work left is Python
# bytecode holding the GIL rather than page faults releasing it.
DEFAULT_WORKERS = 8


def _workers(requested: int | None) -> int:
    if requested is not None:
        return max(1, requested)
    return min(DEFAULT_WORKERS, (os.cpu_count() or 2) + 2)


def map_files(
    paths: list[str],
    work: Callable[[str], T],
    *,
    workers: int | None = None,
) -> list[T]:
    """Run work over every path, preserving order.

    A file that raises does not take the sweep down with it. The exception
    travels back as the result for that path, so the caller decides.
    """

    def guarded(path: str) -> Any:
        try:
            return work(path)
        except Exception as exc:  # noqa: BLE001 - deliberately broad
            return exc

    count = _workers(workers)
    if count == 1 or len(paths) < 2:
        return [guarded(path) for path in paths]
    with ThreadPoolExecutor(max_workers=count) as pool:
        return list(pool.map(guarded, paths))


@dataclass
class Sweep:
    """What a sweep over many files produced."""

    table: Table = field(default_factory=Table)
    errors: dict[str, str] = field(default_factory=dict)
    formats: dict[str, str] = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.table)

    def __bool__(self) -> bool:
        return bool(self.table)


def get_many(
    paths: list[str],
    quantities: str | list[str],
    *,
    format: str | None = None,
    with_lines: bool = False,
    workers: int | None = None,
) -> Sweep:
    """Extract the same quantities from many files into one table."""
    names = [quantities] if isinstance(quantities, str) else list(quantities)

    def one(path: str) -> tuple[dict[str, Value], str | None]:
        with Source(path) as src:
            spec = _resolve(src, format)
            values = {}
            for name in names:
                try:
                    values[name] = extract(src, spec, name, with_lines=with_lines)
                except SpecError as exc:
                    values[name] = Value.missing(name, str(exc), path)
            return values, spec.format

    sweep = Sweep()
    rows: list[dict[str, Any]] = []
    for path, outcome in zip(paths, map_files(paths, one, workers=workers)):
        if isinstance(outcome, Exception):
            sweep.errors[path] = str(outcome)
            continue
        values, fmt = outcome
        if fmt is not None:
            sweep.formats[path] = fmt
        table = Table.from_values(values, path=path)
        rows.extend(table.rows)
        sweep.table.units.update(table.units)
        for name, reason in table.meta.get("missing", {}).items():
            sweep.errors[f"{path}:{name}"] = reason
    sweep.table.rows = rows
    return sweep


def check_many(
    paths: list[str], *, format: str | None = None, workers: int | None = None
) -> list[_check.Status]:
    """Check many files at once, preserving order."""

    def one(path: str) -> _check.Status:
        return _check.check(path, format=format)

    results = []
    for path, outcome in zip(paths, map_files(paths, one, workers=workers)):
        if isinstance(outcome, Exception):
            results.append(_check.Status(path, _check.UNKNOWN, str(outcome)))
        else:
            results.append(outcome)
    return results


def _resolve(src: Source, format: str | None) -> Spec:
    if format is not None:
        return registry.get(format)
    registry.load_all()
    detected = _sniff.sniff_source(src)
    if detected is None:
        raise SpecError(
            f"{src.path}: could not detect a format, pass format= explicitly"
        )
    return registry.get(detected)
