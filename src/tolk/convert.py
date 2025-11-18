"""Converting between formats.

Everything goes through the record model. A reader turns a file into a Table
and a writer turns a Table into bytes, so adding a format costs one reader or
one writer rather than a converter against every other format.

What tolk cannot do itself it hands to a declared backend. It never guesses
and it never silently drops what it did not understand.
"""

from __future__ import annotations

import os
import pathlib
from dataclasses import dataclass
from typing import Callable

from . import backends, registry
from .extract import extract
from .record import Table
from .source import Source
from .spec import SpecError

# Extension to format name, for output where there is nothing to sniff.
OUTPUT_FORMATS = {
    ".csv": "csv",
    ".tsv": "tsv",
    ".json": "json",
    ".xyz": "xyz",
}


class ConvertError(RuntimeError):
    """A conversion could not be done."""


@dataclass(frozen=True)
class Plan:
    """How a conversion would be carried out."""

    source: str
    target: str
    ifmt: str
    ofmt: str
    how: str
    detail: str = ""

    def __str__(self) -> str:
        line = f"{self.ifmt} -> {self.ofmt} via {self.how}"
        return f"{line}\n{self.detail}" if self.detail else line


def output_format(target: str | os.PathLike[str]) -> str:
    suffix = pathlib.Path(target).suffix.lower()
    fmt = OUTPUT_FORMATS.get(suffix)
    return fmt if fmt is not None else suffix.lstrip(".")


def plan(
    source: str | os.PathLike[str],
    target: str | os.PathLike[str],
    *,
    format: str | None = None,
) -> Plan:
    """Work out how a conversion would run, without running it."""
    src_path, dst_path = str(source), str(target)
    ofmt = output_format(dst_path)
    try:
        with Source(src_path) as handle:
            ifmt = format or _detect(handle)
    except SpecError as exc:
        raise ConvertError(str(exc)) from None

    if ofmt in WRITERS:
        return Plan(src_path, dst_path, ifmt, ofmt, "tolk", "native writer")

    backend = backends.find(ifmt, ofmt, installed_only=False)
    if backend is None:
        known = ", ".join(sorted(WRITERS))
        raise ConvertError(
            f"nothing converts {ifmt} to {ofmt}. tolk writes {known}, and no "
            f"declared backend claims the pair"
        )
    if not backend.available():
        raise ConvertError(
            f"{backend.name} would handle {ifmt} to {ofmt} but is not installed"
        )
    return Plan(
        src_path,
        dst_path,
        ifmt,
        ofmt,
        backend.name,
        " ".join(backend.render(src_path, dst_path, ifmt, ofmt)),
    )


def convert(
    source: str | os.PathLike[str],
    target: str | os.PathLike[str],
    *,
    format: str | None = None,
    quantities: list[str] | None = None,
) -> Plan:
    """Convert a file, natively where possible and otherwise by backend."""
    chosen = plan(source, target, format=format)
    if chosen.how != "tolk":
        backend = backends.load_all()[chosen.how]
        backend.run(chosen.source, chosen.target, chosen.ifmt, chosen.ofmt)
        return chosen

    table = read(chosen.source, format=chosen.ifmt, quantities=quantities)
    text = WRITERS[chosen.ofmt](table)
    with open(chosen.target, "w", encoding="utf-8") as handle:
        handle.write(text)
    return chosen


def read(
    source: str | os.PathLike[str],
    *,
    format: str | None = None,
    quantities: list[str] | None = None,
) -> Table:
    """Read a file into the record model.

    Without a quantity list every quantity the spec defines is read, and the
    ones that are not present come back as recorded misses rather than being
    dropped.
    """
    path = str(source)
    with Source(path) as handle:
        spec = registry.get(format) if format else registry.get(_detect(handle))
        wanted = quantities if quantities is not None else spec.names()
        values = {}
        for name in wanted:
            try:
                values[name] = extract(handle, spec, name)
            except SpecError as exc:
                raise ConvertError(str(exc)) from None
    return Table.from_values(values, path=path)


def write_xyz(table: Table) -> str:
    """Write a geometry table as xyz.

    The columns have to be there. Guessing which of several numeric columns
    are coordinates is exactly the kind of inference that makes a converter
    untrustworthy, so a table without symbol, x, y and z is an error.
    """
    rows = [row for row in table.rows if row.get("symbol") is not None]
    missing = [
        key for key in ("symbol", "x", "y", "z") if not rows or key not in rows[0]
    ]
    if missing:
        raise ConvertError(
            f"xyz needs symbol, x, y and z columns, missing {', '.join(missing)}"
        )
    comment = str(table.meta.get("comment") or "written by tolk")
    lines = [str(len(rows)), comment]
    for row in rows:
        lines.append(
            f"{row['symbol']:<3s} {float(row['x']):15.8f} "
            f"{float(row['y']):15.8f} {float(row['z']):15.8f}"
        )
    return "\n".join(lines) + "\n"


WRITERS: dict[str, Callable[[Table], str]] = {
    "csv": lambda table: table.to_csv(),
    "tsv": lambda table: table.to_tsv(),
    "json": lambda table: table.to_json(),
    "xyz": write_xyz,
}


def _detect(handle: Source) -> str:
    from . import _sniff

    registry.load_all()
    detected = _sniff.sniff_source(handle)
    if detected is None:
        raise SpecError(
            f"{handle.path}: could not detect a format, pass format= explicitly"
        )
    return detected


def writers() -> list[str]:
    return sorted(WRITERS)
