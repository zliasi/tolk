"""Fast parser and IO framework.

The public surface is deliberately layered. Layer 0 is raw byte location and
slicing through Source, usable with no spec at all. Layer 1 is spec-driven
extraction. Layer 2 is batch work across many files. Each layer is useful on
its own.
"""

from ._engine import BLANK
from ._sniff import Signature
from ._version import __version__
from .api import describe, explain, formats, get, sniff, spec
from .source import Source, open
from .spec import SpecError
from .value import Provenance, Value

__all__ = [
    "BLANK",
    "Provenance",
    "Signature",
    "Source",
    "SpecError",
    "Value",
    "__version__",
    "describe",
    "explain",
    "formats",
    "get",
    "open",
    "sniff",
    "spec",
]
