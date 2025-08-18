"""Format specs.

A spec says where a quantity lives and how to read it. It is data, never
code, so teaching tolk a new format means writing TOML rather than patching
the engine. Nothing in this module knows what any particular format contains.
"""

from __future__ import annotations

import dataclasses
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
    table: bool = False

    @property
    def is_table(self) -> bool:
        return self.table or bool(self.columns)


@dataclass(frozen=True)
class Quantity:
    """One named thing a spec knows how to find."""

    name: str
    anchor: bytes
    occurrence: str | int = "last"
    block: BlockRule | None = None
    parse: ParseRule = dataclasses.field(default_factory=ParseRule)
    description: str = ""

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
