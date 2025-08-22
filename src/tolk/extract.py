"""Spec driven extraction.

This module turns a Quantity into a Value. It knows about anchors, fields,
and columns, and nothing whatever about any particular format. Everything it
needs comes from the spec.
"""

from __future__ import annotations

from typing import Any

from . import _engine
from .source import Source
from .spec import Quantity, Spec
from .value import Provenance, Value


def extract(src: Source, spec: Spec, name: str, *, with_lines: bool = False) -> Value:
    """Read one quantity out of a source."""
    quantity = spec.quantity(name)
    return extract_quantity(src, quantity, with_lines=with_lines)


def extract_many(
    src: Source, spec: Spec, names: list[str], *, with_lines: bool = False
) -> dict[str, Value]:
    """Read several quantities out of one source."""
    return {name: extract(src, spec, name, with_lines=with_lines) for name in names}


def extract_quantity(
    src: Source, quantity: Quantity, *, with_lines: bool = False
) -> Value:
    """Read one quantity, already resolved from its spec."""
    if quantity.repeats:
        return _repeated_value(src, quantity, with_lines=with_lines)

    offset = _anchor_offset(src, quantity)
    if offset < 0:
        return Value.missing(quantity.name, _not_found(quantity), src.path)

    where = Provenance(
        path=src.path,
        offset=offset,
        line=src.line_number(offset) if with_lines else None,
    )

    if quantity.parse.is_table:
        return _table_value(src, quantity, where)
    return _scalar_value(src, quantity, where)


def _anchor_offset(src: Source, quantity: Quantity) -> int:
    """Byte the quantity is read from, or -1 when the anchor is absent."""
    if quantity.anchor is None:
        return 0
    return src.find_nth(quantity.anchor, quantity.nth)


def _not_found(quantity: Quantity) -> str:
    anchor = quantity.anchor
    assert anchor is not None  # only reachable when there is one to miss
    return f"anchor {anchor.decode(errors='replace')!r} not found"


def _repeated_value(src: Source, quantity: Quantity, *, with_lines: bool) -> Value:
    """Read every occurrence of an anchor that prints one line each."""
    assert quantity.anchor is not None  # rejected at load time
    offsets = src.findall(quantity.anchor)
    if not offsets:
        return Value.missing(quantity.name, _not_found(quantity), src.path)

    rule = quantity.parse
    where = Provenance(
        path=src.path,
        offset=offsets[0],
        line=src.line_number(offsets[0]) if with_lines else None,
    )

    rows: list[Any] = []
    for offset in offsets:
        fields = src.line(offset).split()
        if rule.is_table:
            row = _row(fields, quantity)
            if row is not None:
                rows.append(row)
        elif rule.field is not None:
            try:
                raw = fields[rule.field]
            except IndexError:
                continue
            value, error = _convert(raw, rule.type, rule.strip)
            if error is None:
                rows.append(value)

    if not rows:
        return Value.missing(
            quantity.name, "no occurrence held a readable value", src.path
        )
    return Value(quantity.name, rows, rule.unit, where)


def _row(fields: list[bytes], quantity: Quantity) -> dict[str, Any] | None:
    """One record from a split line, or None when the line is furniture."""
    rule = quantity.parse
    if len(fields) <= max(rule.columns.values(), default=-1):
        return None
    row: dict[str, Any] = {}
    readable = 0
    for column, index in rule.columns.items():
        value, error = _convert(fields[index], rule.column_type(column), rule.strip)
        row[column] = None if error is not None else value
        readable += error is None
    return row if readable else None


def _scalar_value(src: Source, quantity: Quantity, where: Provenance) -> Value:
    rule = quantity.parse
    if rule.field is None:
        return Value.missing(quantity.name, "no parse.field for a scalar", src.path)

    # A block with a scalar rule means the value sits a few lines below the
    # anchor rather than on it.
    offset = where.offset
    if quantity.block is not None:
        offset = src.advance_lines(offset, quantity.block.skip)

    fields = src.line(offset).split()
    try:
        text = fields[rule.field]
    except IndexError:
        return Value.missing(
            quantity.name,
            f"line has {len(fields)} fields, wanted index {rule.field}",
            src.path,
        )

    value, error = _convert(text, rule.type, rule.strip)
    if error is not None:
        return Value.missing(quantity.name, error, src.path)
    return Value(quantity.name, value, rule.unit, where)


def _table_value(src: Source, quantity: Quantity, where: Provenance) -> Value:
    rule = quantity.parse
    block = quantity.block
    if block is None:
        return Value.missing(quantity.name, "table quantity has no block", src.path)

    until: _engine.Until = None
    if block.stops_on_blank:
        until = _engine.BLANK
    elif block.until_bytes is not None:
        until = block.until_bytes

    span = src.block_span(
        where.offset, skip=block.skip, until=until, max_lines=block.max_lines
    )

    rows: list[dict[str, Any]] = []
    wanted = max(rule.columns.values(), default=-1)
    for line_from, line_to in src.lines(*span):
        fields = src.read(line_from, line_to).split()
        if not fields or len(fields) <= wanted:
            # Ragged lines are skipped rather than fatal, because separators
            # and continuation lines turn up inside real blocks.
            continue
        row: dict[str, Any] = {}
        readable = 0
        for column, index in rule.columns.items():
            value, error = _convert(fields[index], rule.column_type(column), rule.strip)
            row[column] = None if error is not None else value
            readable += error is None
        # A line where nothing converts is furniture, a rule or a separator
        # that happens to have enough fields. A line where only some columns
        # fail is data with a hole in it, and is kept.
        if readable:
            rows.append(row)

    if not rows:
        return Value.missing(quantity.name, "block held no readable rows", src.path)
    return Value(quantity.name, rows, rule.unit, where)


def _convert(raw: bytes, kind: str, strip: str = "") -> tuple[Any, str | None]:
    """Turn one field into a typed value, or say why it could not be.

    strip removes the punctuation programs glue onto values, the comma after
    a revision string or the "f=" in front of an oscillator strength, so a
    spec can read them without a regex.
    """
    text = raw.decode("utf-8", errors="replace")
    if strip:
        text = text.strip(strip)
    if kind == "str":
        return text, None
    try:
        if kind == "int":
            return int(text), None
        return float(text), None
    except ValueError:
        return None, f"{text!r} is not a {kind}"
