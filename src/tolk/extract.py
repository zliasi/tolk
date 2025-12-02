"""Spec driven extraction.

This module turns a Quantity into a Value. It knows about anchors, fields,
and columns, and nothing whatever about any particular format. Everything it
needs comes from the spec.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from . import _engine, cache
from .source import Source
from .spec import BlockRule, Quantity, Spec
from .value import Provenance, Value


def extract(src: Source, spec: Spec, name: str, *, with_lines: bool = False) -> Value:
    """Read one quantity out of a source."""
    quantity = spec.quantity(name)
    hook = _PARSERS.get((spec.format, name))
    if hook is not None:
        return _run_hook(src, quantity, hook)
    return extract_quantity(src, quantity, with_lines=with_lines)


def _run_hook(
    src: Source, quantity: Quantity, hook: Callable[[Source, Quantity], Any]
) -> Value:
    """Run a registered parser, keeping the same failure contract."""
    try:
        produced = hook(src, quantity)
    except Exception as exc:  # noqa: BLE001 - a hook must not break a sweep
        return Value.missing(quantity.name, f"parser raised {exc}", src.path)
    if produced is None:
        return Value.missing(quantity.name, "parser found nothing", src.path)
    return Value(
        quantity.name,
        produced,
        quantity.parse.unit,
        Provenance(path=src.path, offset=0),
    )


def extract_many(
    src: Source, spec: Spec, names: list[str], *, with_lines: bool = False
) -> dict[str, Value]:
    """Read several quantities out of one source."""
    return {name: extract(src, spec, name, with_lines=with_lines) for name in names}


# Python parsers registered for quantities a spec cannot express.
#
# The escape hatch has to live inside the spec system rather than outside it.
# Without it the first quantity that needs real logic makes a user abandon
# specs entirely and go back to writing a script.
_PARSERS: dict[tuple[str, str], Callable[[Source, Quantity], Any]] = {}


def parser(
    format: str, quantity: str
) -> Callable[[Callable[[Source, Quantity], Any]], Callable[[Source, Quantity], Any]]:
    """Register a Python parser for one quantity of one format.

    The function receives the open Source and the Quantity and returns a
    value, or None to mean the quantity is not there.
    """

    def register(
        fn: Callable[[Source, Quantity], Any],
    ) -> Callable[[Source, Quantity], Any]:
        _PARSERS[(format, quantity)] = fn
        return fn

    return register


def parsers() -> dict[tuple[str, str], Callable[[Source, Quantity], Any]]:
    return dict(_PARSERS)


def clear_parsers() -> None:
    _PARSERS.clear()


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
    store = cache.active()
    if store is None:
        return src.find_nth(quantity.anchor, quantity.nth)

    remembered = store.lookup(src, quantity.anchor, quantity.occurrence)
    if remembered is not None:
        return remembered
    offset = src.find_nth(quantity.anchor, quantity.nth)
    store.store(src, quantity.anchor, quantity.occurrence, offset)
    return offset


def _not_found(quantity: Quantity) -> str:
    anchor = quantity.anchor
    assert anchor is not None  # only reachable when there is one to miss
    return f"anchor {anchor.decode(errors='replace')!r} not found"


def _repeated_value(src: Source, quantity: Quantity, *, with_lines: bool) -> Value:
    """Read every occurrence of a repeating quantity.

    Two shapes end up here. A quantity printed one line per item, and a
    quantity printed as a whole block per cycle. The second is what makes an
    optimisation trajectory readable, since every step writes the same table
    again.
    """
    assert quantity.anchor is not None  # rejected at load time
    offsets = src.findall(quantity.anchor)
    if not offsets:
        return Value.missing(quantity.name, _not_found(quantity), src.path)

    if quantity.block is not None and quantity.parse.is_table:
        return _repeated_blocks(src, quantity, offsets, with_lines=with_lines)

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


def _fast_rows(
    src: Source, quantity: Quantity, span: tuple[int, int]
) -> list[dict[str, Any]] | None:
    """Bulk parse a block in C, or None when this block does not qualify.

    Only all numeric columns with no stripping go this way. A string column
    cannot travel as a double, and stripping is a per field decision the bulk
    parser does not make.
    """
    rule = quantity.parse
    if rule.strip or rule.type == "str":
        return None
    if any(rule.column_type(name) == "str" for name in rule.columns):
        return None

    names = list(rule.columns)
    parsed = src.scan_columns(span[0], span[1], [rule.columns[name] for name in names])
    if parsed is None:
        return None

    want_int = {name: rule.column_type(name) == "int" for name in names}
    rows: list[dict[str, Any]] = []
    for values in parsed:
        row: dict[str, Any] = {}
        readable = 0
        for name, value in zip(names, values):
            if value is None:
                row[name] = None
                continue
            row[name] = int(value) if want_int[name] else value
            readable += 1
        if readable:
            rows.append(row)
    return rows


def _repeated_blocks(
    src: Source, quantity: Quantity, offsets: list[int], *, with_lines: bool
) -> Value:
    """Collect the same block from every occurrence of its anchor.

    Each block gets a step number so the occurrences stay distinguishable
    once they are flattened into one table.
    """
    where = Provenance(
        path=src.path,
        offset=offsets[0],
        line=src.line_number(offsets[0]) if with_lines else None,
    )
    rows: list[dict[str, Any]] = []
    for step, offset in enumerate(offsets):
        block = _block_rows(src, quantity, offset)
        for row in block:
            rows.append({"step": step, **row})
    if not rows:
        return Value.missing(quantity.name, "no occurrence held rows", src.path)
    return Value(quantity.name, rows, quantity.parse.unit, where)


def _block_rows(src: Source, quantity: Quantity, offset: int) -> list[dict[str, Any]]:
    """Rows of one block, by whichever path applies."""
    block = quantity.block
    assert block is not None
    span = src.block_span(
        offset,
        skip=block.skip,
        until=_until(block),
        max_lines=block.max_lines,
    )
    fast = _fast_rows(src, quantity, span)
    if fast is not None:
        return fast
    rows = []
    for line_from, line_to in src.lines(*span):
        row = _row(src.read(line_from, line_to).split(), quantity)
        if row is not None:
            rows.append(row)
    return rows


def _until(block: BlockRule) -> _engine.Until:
    if block.stops_on_blank:
        return _engine.BLANK
    literal = block.until_bytes
    return literal if literal is not None else None


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

    # A block with a scalar rule means the value sits a few lines below the
    # anchor rather than on it.
    offset = where.offset
    if quantity.block is not None:
        offset = src.advance_lines(offset, quantity.block.skip)

    if rule.whole_line:
        # Comments and titles are text with spaces in them, so splitting into
        # fields would throw away everything after the first word.
        text = src.line(offset).strip()
    else:
        if rule.field is None:
            return Value.missing(quantity.name, "no parse.field for a scalar", src.path)
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

    span = src.block_span(
        where.offset,
        skip=block.skip,
        until=_until(block),
        max_lines=block.max_lines,
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
