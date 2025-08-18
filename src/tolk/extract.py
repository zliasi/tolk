"""Spec driven extraction.

This module turns a Quantity into a Value. It knows about anchors, fields,
and columns, and nothing whatever about any particular format. Everything it
needs comes from the spec.
"""

from __future__ import annotations

from typing import Any

from . import _engine
from .source import Source
from .spec import ParseRule, Quantity, Spec
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
    offset = src.find_nth(quantity.anchor, quantity.nth)
    if offset < 0:
        return Value.missing(
            quantity.name,
            f"anchor {quantity.anchor.decode(errors='replace')!r} not found",
            src.path,
        )

    where = Provenance(
        path=src.path,
        offset=offset,
        line=src.line_number(offset) if with_lines else None,
    )

    if quantity.parse.is_table:
        return _table_value(src, quantity, where)
    return _scalar_value(src, quantity, where)


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

    value, error = _convert(text, rule)
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
        for column, index in rule.columns.items():
            value, error = _convert(fields[index], rule)
            row[column] = None if error is not None else value
        rows.append(row)

    if not rows:
        return Value.missing(quantity.name, "block held no readable rows", src.path)
    return Value(quantity.name, rows, rule.unit, where)


def _convert(raw: bytes, rule: ParseRule) -> tuple[Any, str | None]:
    """Turn one field into a typed value, or say why it could not be."""
    text = raw.decode("utf-8", errors="replace")
    if rule.type == "str":
        return text, None
    try:
        if rule.type == "int":
            return int(text), None
        return float(text), None
    except ValueError:
        return None, f"{text!r} is not a {rule.type}"
