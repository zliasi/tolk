"""Show what a spec actually did.

A declarative system is only usable if you can see why it matched what it
matched. explain reports the anchor, the byte it landed on, the text of the
line, the block it walked, and the value that came out, so a wrong result
points at the spec rather than at the engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import _engine
from .extract import extract_quantity
from .source import Source
from .spec import Quantity, Spec
from .value import Value

# Enough of a block to see whether the skip and stop rules are right.
PREVIEW_LINES = 6


@dataclass(frozen=True)
class Explanation:
    """Everything known about one extraction attempt."""

    quantity: str
    format: str
    spec_source: str
    anchor: bytes | None
    occurrence: str | int
    offset: int | None = None
    line: int | None = None
    anchor_text: str = ""
    block_preview: list[str] = field(default_factory=list)
    block_total: int = 0
    rule: str = ""
    value: Value | None = None

    @property
    def found(self) -> bool:
        return self.offset is not None


def explain(src: Source, spec: Spec, name: str) -> Explanation:
    """Trace how a spec reads one quantity out of a source."""
    quantity = spec.quantity(name)
    value = extract_quantity(src, quantity, with_lines=True)

    if quantity.repeats:
        return _explain_repeated(src, spec, quantity, value)

    offset = (
        0 if quantity.anchor is None else src.find_nth(quantity.anchor, quantity.nth)
    )

    if offset < 0:
        return Explanation(
            quantity=name,
            format=spec.format,
            spec_source=spec.source,
            anchor=quantity.anchor,
            occurrence=quantity.occurrence,
            rule=_describe_rule(quantity),
            value=value,
        )

    preview, total = _preview(src, quantity, offset)
    return Explanation(
        quantity=name,
        format=spec.format,
        spec_source=spec.source,
        anchor=quantity.anchor,
        occurrence=quantity.occurrence,
        offset=offset,
        line=src.line_number(offset),
        anchor_text=src.line(offset).decode("utf-8", errors="replace"),
        block_preview=preview,
        block_total=total,
        rule=_describe_rule(quantity),
        value=value,
    )


def _explain_repeated(
    src: Source, spec: Spec, quantity: Quantity, value: Value
) -> Explanation:
    """Trace a quantity that is printed once per item rather than once."""
    assert quantity.anchor is not None  # rejected at load time
    offsets = src.findall(quantity.anchor)
    if not offsets:
        return Explanation(
            quantity=quantity.name,
            format=spec.format,
            spec_source=spec.source,
            anchor=quantity.anchor,
            occurrence=quantity.occurrence,
            rule=_describe_rule(quantity),
            value=value,
        )
    return Explanation(
        quantity=quantity.name,
        format=spec.format,
        spec_source=spec.source,
        anchor=quantity.anchor,
        occurrence=quantity.occurrence,
        offset=offsets[0],
        line=src.line_number(offsets[0]),
        anchor_text=src.line(offsets[0]).decode("utf-8", errors="replace"),
        block_preview=[
            src.line(off).decode("utf-8", errors="replace")
            for off in offsets[:PREVIEW_LINES]
        ],
        block_total=len(offsets),
        rule=_describe_rule(quantity),
        value=value,
    )


def _preview(src: Source, quantity: Quantity, offset: int) -> tuple[list[str], int]:
    block = quantity.block
    if block is None:
        return [], 0

    until: _engine.Until = None
    if block.stops_on_blank:
        until = _engine.BLANK
    elif block.until_bytes is not None:
        until = block.until_bytes

    span = src.block_span(
        offset, skip=block.skip, until=until, max_lines=block.max_lines
    )
    spans = list(src.lines(*span))
    shown = [
        src.read(a, b).decode("utf-8", errors="replace")
        for a, b in spans[:PREVIEW_LINES]
    ]
    return shown, len(spans)


def _describe_rule(quantity: Quantity) -> str:
    rule = quantity.parse
    if rule.is_table:
        columns = ", ".join(
            f"{name}={index}" for name, index in sorted(rule.columns.items())
        )
        return f"columns {columns}"
    if rule.whole_line:
        return f"whole line as {rule.type}"
    return f"field {rule.field} as {rule.type}"


def format_explanation(exp: Explanation) -> str:
    """Render an explanation as plain lines for a terminal."""
    out: list[str] = []
    out.append(f"quantity {exp.quantity} ({exp.format}, {exp.spec_source})")
    if exp.anchor is None:
        out.append("anchor   none, read from the start of the file")
    else:
        anchor = exp.anchor.decode("utf-8", errors="replace")
        out.append(f"anchor   {anchor!r} occurrence {exp.occurrence}")

    if not exp.found:
        out.append("found    no")
        if exp.value is not None and exp.value.reason:
            out.append(f"reason   {exp.value.reason}")
        return "\n".join(out)

    out.append(f"found    byte {exp.offset}, line {exp.line}")
    out.append(f"line     {exp.anchor_text.strip()}")

    if exp.block_total:
        label = "matches" if exp.occurrence == "all" else "block"
        out.append(f"{label:8s} {exp.block_total} lines")
        for text in exp.block_preview:
            out.append(f"         {text.strip()}")
        if exp.block_total > len(exp.block_preview):
            out.append(f"         ... {exp.block_total - len(exp.block_preview)} more")

    out.append(f"rule     {exp.rule}")
    value = exp.value
    if value is None or not value.ok:
        reason = value.reason if value is not None else "no value"
        out.append(f"value    none, {reason}")
    elif isinstance(value.value, list):
        columns = ", ".join(sorted(value.value[0])) if value.value else ""
        out.append(f"value    {len(value.value)} rows of {columns}")
    else:
        unit = f" {value.unit}" if value.unit else ""
        out.append(f"value    {value.value}{unit}")
    return "\n".join(out)


def explain_text(src: Source, spec: Spec, name: str) -> str:
    """Trace an extraction and render it in one call."""
    return format_explanation(explain(src, spec, name))
