"""Fast parser and IO framework.

The public surface is deliberately layered. Layer 0 is raw byte location and
slicing through Source, usable with no spec at all. Layer 1 is spec-driven
extraction. Layer 2 is batch work across many files. Each layer is useful on
its own.
"""

from ._version import __version__

__all__ = ["__version__"]
