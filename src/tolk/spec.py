"""Format specs.

A spec says where a quantity lives and how to read it. It is data, never
code, so teaching tolk a new format means writing TOML rather than patching
the engine. Nothing in this module knows what any particular format contains.
"""

from __future__ import annotations

import dataclasses
import os
import pathlib
import tomllib
from dataclasses import dataclass

# What a block stops on when until is not a literal.
BLANK_UNTIL = "blank"

SCALAR_TYPES = ("float", "int", "str")


class SpecError(ValueError):
    """A spec is malformed. Raised at load time, never at extraction time."""


@dataclass(frozen=True)
class BlockRule:
    """How to walk from an anchor to the lines that hold the data.

    skip steps over the header and any rule lines under it. until ends the
    run, either at the first blank line or at a literal that begins a line
    once leading whitespace is dropped. max_lines bounds it either way.
    """

    skip: int = 0
    until: str | None = None
    max_lines: int | None = None

    @property
    def until_bytes(self) -> bytes | None:
        if self.until is None or self.until == BLANK_UNTIL:
            return None
        return self.until.encode()

    @property
    def stops_on_blank(self) -> bool:
        return self.until == BLANK_UNTIL


@dataclass(frozen=True)
class ParseRule:
    """How to turn the located text into a value.

    A scalar takes one whitespace separated field from a single line, where
    negative indices count from the right because trailing values are the
    stable end of a line. A table takes named columns from every line of a
    block.
    """

    type: str = "float"
    unit: str | None = None
    field: int | None = None
    columns: dict[str, int] = dataclasses.field(default_factory=dict)
    types: dict[str, str] = dataclasses.field(default_factory=dict)
    strip: str = ""
    whole_line: bool = False
    table: bool = False

    @property
    def is_table(self) -> bool:
        return self.table or bool(self.columns)

    def column_type(self, column: str) -> str:
        """Type for one column, falling back to the rule wide default.

        Real tables mix a label with its numbers, so a per column override is
        the difference between a spec and a special case in code.
        """
        return self.types.get(column, self.type)


@dataclass(frozen=True)
class Quantity:
    """One named thing a spec knows how to find."""

    name: str
    # No anchor means the quantity sits at a known place from the start of
    # the file, which is how formats with a fixed shape and no banner work.
    anchor: bytes | None = None
    occurrence: str | int = "last"
    block: BlockRule | None = None
    parse: ParseRule = dataclasses.field(default_factory=ParseRule)
    description: str = ""

    @property
    def repeats(self) -> bool:
        """Whether every occurrence is wanted rather than one of them.

        Some programs print a quantity once per item instead of as a table,
        one line per excited state or per optimisation cycle. Those are still
        one quantity, so they come back as a list.
        """
        return self.occurrence == "all"

    @property
    def nth(self) -> int:
        """The occurrence as an index that find_nth understands."""
        if self.occurrence == "first":
            return 0
        if self.occurrence == "last":
            return -1
        if isinstance(self.occurrence, int):
            return self.occurrence
        raise SpecError(f"{self.name}: bad occurrence {self.occurrence!r}")


@dataclass(frozen=True)
class Terminators:
    """Literals that say how a run ended, looked for in the tail only."""

    ok: tuple[bytes, ...] = ()
    error: tuple[bytes, ...] = ()


@dataclass(frozen=True)
class Spec:
    """Everything tolk knows about one format."""

    format: str
    quantities: dict[str, Quantity] = dataclasses.field(default_factory=dict)
    terminators: Terminators = dataclasses.field(default_factory=Terminators)
    contains: tuple[bytes, ...] = ()
    extensions: tuple[str, ...] = ()
    priority: int = 0
    source: str = "<builtin>"

    def quantity(self, name: str) -> Quantity:
        try:
            return self.quantities[name]
        except KeyError:
            known = ", ".join(sorted(self.quantities)) or "none"
            raise SpecError(
                f"{self.format} has no quantity {name!r}, knows: {known}"
            ) from None

    def names(self) -> list[str]:
        return sorted(self.quantities)


def loads(text: str, source: str = "<string>") -> Spec:
    """Parse a spec from TOML text.

    Validation is strict and happens here, so a typo in a spec fails at load
    time with a message naming the file and the key, rather than silently
    extracting nothing an hour into a batch run.
    """
    try:
        raw = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise SpecError(f"{source}: {exc}") from None

    _reject_unknown(raw, _SPEC_KEYS, source, "top level")
    fmt = raw.get("format")
    if not isinstance(fmt, str) or not fmt:
        raise SpecError(f"{source}: needs a non-empty format name")

    signature = _table(raw, "signature", source)
    _reject_unknown(signature, _SIGNATURE_KEYS, source, "signature")
    terminator = _table(raw, "terminator", source)
    _reject_unknown(terminator, _TERMINATOR_KEYS, source, "terminator")

    quantities = {}
    for name, body in _table(raw, "quantity", source).items():
        where = f"quantity.{name}"
        if not isinstance(body, dict):
            raise SpecError(f"{source}: {where} must be a table")
        quantities[name] = _quantity(name, body, source, where)

    return Spec(
        format=fmt,
        quantities=quantities,
        terminators=Terminators(
            ok=_literals(terminator, "ok", source, "terminator"),
            error=_literals(terminator, "error", source, "terminator"),
        ),
        contains=_literals(signature, "contains", source, "signature"),
        extensions=tuple(_strings(signature, "extensions", source, "signature")),
        priority=_int(signature, "priority", source, "signature", 0),
        source=source,
    )


def load(path: str | os.PathLike[str]) -> Spec:
    """Parse a spec from a TOML file."""
    text = pathlib.Path(path).read_text(encoding="utf-8")
    return loads(text, str(path))


_SPEC_KEYS = frozenset({"format", "signature", "terminator", "quantity"})
_SIGNATURE_KEYS = frozenset({"contains", "extensions", "priority"})
_TERMINATOR_KEYS = frozenset({"ok", "error"})
_QUANTITY_KEYS = frozenset({"anchor", "occurrence", "block", "parse", "description"})
_BLOCK_KEYS = frozenset({"skip", "until", "max_lines"})
_PARSE_KEYS = frozenset(
    {
        "type",
        "unit",
        "field",
        "columns",
        "types",
        "strip",
        "whole_line",
        "table",
    }
)


def _quantity(name: str, body: dict[str, object], source: str, where: str) -> Quantity:
    _reject_unknown(body, _QUANTITY_KEYS, source, where)
    anchor = body.get("anchor")
    if anchor is not None and (not isinstance(anchor, str) or not anchor):
        raise SpecError(f"{source}: {where}.anchor must be a non-empty string")

    occurrence = body.get("occurrence", "last")
    if occurrence not in ("first", "last", "all") and not isinstance(occurrence, int):
        raise SpecError(
            f"{source}: {where}.occurrence must be first, last, all, or an integer"
        )
    if anchor is None and occurrence == "all":
        raise SpecError(
            f"{source}: {where} has no anchor, so there is nothing to repeat over"
        )

    block = None
    if "block" in body:
        raw_block = body["block"]
        if not isinstance(raw_block, dict):
            raise SpecError(f"{source}: {where}.block must be a table")
        _reject_unknown(raw_block, _BLOCK_KEYS, source, f"{where}.block")
        block = BlockRule(
            skip=_int(raw_block, "skip", source, f"{where}.block", 0),
            until=_optional_str(raw_block, "until", source, f"{where}.block"),
            max_lines=_optional_int(raw_block, "max_lines", source, f"{where}.block"),
        )

    parse = ParseRule()
    if "parse" in body:
        raw_parse = body["parse"]
        if not isinstance(raw_parse, dict):
            raise SpecError(f"{source}: {where}.parse must be a table")
        _reject_unknown(raw_parse, _PARSE_KEYS, source, f"{where}.parse")
        kind = raw_parse.get("type", "float")
        if kind not in SCALAR_TYPES:
            raise SpecError(
                f"{source}: {where}.parse.type must be one of "
                f"{', '.join(SCALAR_TYPES)}"
            )
        columns = raw_parse.get("columns", {})
        if not isinstance(columns, dict) or not all(
            isinstance(v, int) for v in columns.values()
        ):
            raise SpecError(
                f"{source}: {where}.parse.columns must map names to field indices"
            )
        types = raw_parse.get("types", {})
        if not isinstance(types, dict) or not all(
            v in SCALAR_TYPES for v in types.values()
        ):
            raise SpecError(
                f"{source}: {where}.parse.types must map column names to "
                f"one of {', '.join(SCALAR_TYPES)}"
            )
        unknown_typed = sorted(set(types) - set(columns))
        if unknown_typed:
            raise SpecError(
                f"{source}: {where}.parse.types names columns that do not "
                f"exist: {', '.join(unknown_typed)}"
            )

        parse = ParseRule(
            type=kind,
            unit=_optional_str(raw_parse, "unit", source, f"{where}.parse"),
            field=_optional_int(raw_parse, "field", source, f"{where}.parse"),
            columns={str(k): int(v) for k, v in columns.items()},
            types={str(k): str(v) for k, v in types.items()},
            strip=_optional_str(raw_parse, "strip", source, f"{where}.parse") or "",
            whole_line=bool(raw_parse.get("whole_line", False)),
            table=bool(raw_parse.get("table", False)),
        )

    if parse.is_table and block is None and occurrence != "all":
        raise SpecError(f"{source}: {where} reads a table but defines no block")
    if not parse.is_table and parse.field is None and not parse.whole_line:
        raise SpecError(
            f"{source}: {where} needs parse.field, parse.columns, or "
            "parse.whole_line"
        )

    return Quantity(
        name=name,
        anchor=None if anchor is None else anchor.encode(),
        occurrence=occurrence,
        block=block,
        parse=parse,
        description=_optional_str(body, "description", source, where) or "",
    )


def _table(raw: dict[str, object], key: str, source: str) -> dict[str, object]:
    value = raw.get(key, {})
    if not isinstance(value, dict):
        raise SpecError(f"{source}: {key} must be a table")
    return value


def _reject_unknown(
    body: dict[str, object], allowed: frozenset[str], source: str, where: str
) -> None:
    unknown = sorted(set(body) - allowed)
    if unknown:
        raise SpecError(
            f"{source}: {where} has unknown key(s) {', '.join(unknown)}, "
            f"allowed: {', '.join(sorted(allowed))}"
        )


def _strings(body: dict[str, object], key: str, source: str, where: str) -> list[str]:
    value = body.get(key, [])
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise SpecError(f"{source}: {where}.{key} must be a string or list of strings")
    return [str(v) for v in value]


def _literals(
    body: dict[str, object], key: str, source: str, where: str
) -> tuple[bytes, ...]:
    return tuple(v.encode() for v in _strings(body, key, source, where))


def _int(
    body: dict[str, object], key: str, source: str, where: str, default: int
) -> int:
    value = body.get(key, default)
    if not isinstance(value, int) or isinstance(value, bool):
        raise SpecError(f"{source}: {where}.{key} must be an integer")
    return value


def _optional_int(
    body: dict[str, object], key: str, source: str, where: str
) -> int | None:
    if key not in body:
        return None
    return _int(body, key, source, where, 0)


def _optional_str(
    body: dict[str, object], key: str, source: str, where: str
) -> str | None:
    if key not in body:
        return None
    value = body[key]
    if not isinstance(value, str):
        raise SpecError(f"{source}: {where}.{key} must be a string")
    return value
