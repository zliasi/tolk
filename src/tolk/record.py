"""The intermediate record model.

Everything tolk reads becomes a Table, and everything tolk writes is written
from one. That keeps conversion at one reader plus one writer per format
rather than a converter per pair.

The model is open on purpose. Columns it was not told about are carried
through untouched rather than dropped, because a format that loses what it
did not understand cannot round trip.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from . import _engine
from .value import Value


@dataclass
class Table:
    """Rows of named fields, with units and passthrough metadata."""

    rows: list[dict[str, Any]] = field(default_factory=list)
    units: dict[str, str] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def columns(self) -> list[str]:
        """Column names in first seen order, across every row."""
        seen: dict[str, None] = {}
        for row in self.rows:
            for key in row:
                seen.setdefault(key, None)
        return list(seen)

    def __len__(self) -> int:
        return len(self.rows)

    def __bool__(self) -> bool:
        return bool(self.rows)

    @classmethod
    def from_values(cls, values: dict[str, Value], *, path: str | None = None) -> Table:
        """Build a table from one file's extracted quantities.

        Scalars become one row. A single list valued quantity expands to one
        row per element, with the scalars repeated alongside it, which is the
        shape that makes a spectrum or a geometry usable as a table.
        """
        scalars: dict[str, Any] = {}
        units: dict[str, str] = {}
        listed: dict[str, list[dict[str, Any]]] = {}
        misses: dict[str, str] = {}

        for name, value in values.items():
            if not value.ok:
                misses[name] = str(value.reason)
                continue
            if value.unit:
                units[name] = value.unit
            if isinstance(value.value, list):
                listed[name] = _as_rows(name, value.value)
            else:
                scalars[name] = value.value

        if path is not None:
            scalars = {"path": path, **scalars}

        meta: dict[str, Any] = {}
        if misses:
            meta["missing"] = misses

        if not listed:
            return cls(rows=[scalars] if scalars else [], units=units, meta=meta)

        # More than one list cannot be zipped without inventing a
        # relationship between them, so they stay separate tables.
        if len(listed) > 1:
            meta["tables"] = {
                name: cls(rows=rows, units=units) for name, rows in listed.items()
            }
            return cls(rows=[scalars] if scalars else [], units=units, meta=meta)

        ((name, rows),) = listed.items()
        for column, unit in list(units.items()):
            if column == name:
                units.pop(column)
        return cls(rows=[{**scalars, **row} for row in rows], units=units, meta=meta)

    def to_json(self, *, indent: int | None = 2) -> str:
        """JSON with units and metadata alongside the rows."""
        payload: dict[str, Any] = {"rows": self.rows}
        if self.units:
            payload["units"] = self.units
        extra = {k: v for k, v in self.meta.items() if k != "tables"}
        if extra:
            payload["meta"] = extra
        if "tables" in self.meta:
            payload["tables"] = {
                name: table.rows for name, table in self.meta["tables"].items()
            }
        return json.dumps(payload, indent=indent, default=str)

    def to_csv(self, *, delimiter: str = ",") -> str:
        """Delimited text, one header line then one line per row."""
        columns = self.columns
        if not columns:
            return ""
        header = delimiter.join(_quote(c, delimiter) for c in columns)

        body = self._fast_body(columns, delimiter)
        if body is not None:
            return header + "\n" + body

        out = [header]
        for row in self.rows:
            out.append(
                delimiter.join(_quote(_cell(row.get(c)), delimiter) for c in columns)
            )
        return "\n".join(out) + "\n"

    def _fast_body(self, columns: list[str], delimiter: str) -> str | None:
        """Format the body in C, or None when that would be wrong.

        The C writer emits fields as they are, so it can only be used when
        nothing needs quoting. Any text cell falls back to Python rather than
        risk a delimiter inside a value silently splitting a row.
        """
        cells = []
        for row in self.rows:
            values = [row.get(name) for name in columns]
            if any(
                value is not None and not isinstance(value, (int, float))
                for value in values
            ):
                return None
            cells.append(values)
        raw = _engine.write_rows(cells, delimiter)
        if raw is None:
            return None
        return raw.decode("ascii")

    def to_tsv(self) -> str:
        return self.to_csv(delimiter="\t")


def _as_rows(name: str, values: list[Any]) -> list[dict[str, Any]]:
    """Normalise a list valued quantity into rows."""
    rows = []
    for item in values:
        rows.append(dict(item) if isinstance(item, dict) else {name: item})
    return rows


def _cell(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _quote(text: str, delimiter: str) -> str:
    if delimiter in text or '"' in text or "\n" in text:
        return '"' + text.replace('"', '""') + '"'
    return text
