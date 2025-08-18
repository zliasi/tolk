"""Extracted values and where they came from.

Every value knows its origin. The engine already has the byte offset, so
carrying it costs nothing and means a number in a table can always be traced
back to the line that produced it.

Nothing here raises. A quantity that could not be read comes back as a value
of None with a reason attached, because a batch over five hundred files where
twelve are broken must not stop at the first one.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Provenance:
    """Where a value was found."""

    path: str
    offset: int
    # Line numbering has to count newlines from the start of the file, so it
    # is filled in only when asked for.
    line: int | None = None

    def __str__(self) -> str:
        if self.line is None:
            return f"{self.path}@{self.offset}"
        return f"{self.path}:{self.line}"


@dataclass(frozen=True)
class Value:
    """One extracted quantity, or the reason there is not one."""

    name: str
    value: Any = None
    unit: str | None = None
    where: Provenance | None = None
    reason: str | None = None

    @property
    def ok(self) -> bool:
        return self.reason is None

    def __bool__(self) -> bool:
        return self.ok

    @classmethod
    def missing(cls, name: str, reason: str, path: str | None = None) -> Value:
        """A quantity that could not be read, and why."""
        return cls(name=name, reason=reason if path is None else f"{path}: {reason}")

    def __str__(self) -> str:
        if not self.ok:
            return f"{self.name}: {self.reason}"
        if self.unit:
            return f"{self.name}: {self.value} {self.unit}"
        return f"{self.name}: {self.value}"
