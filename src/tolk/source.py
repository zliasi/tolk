"""Lazy byte access to a file.

Source is layer 0 of the API. It opens a file, exposes it as bytes, and
copies nothing until asked. Everything above it works in byte offsets, so
this module never needs to know what a file contains.
"""

from __future__ import annotations

import mmap
import os
from collections.abc import Iterator
from types import TracebackType

from . import _engine

# Under this size a mapping costs more than the copy it saves. Setting up a
# mapping is a syscall plus page table work, while a small read lands in
# cache and is done with.
SMALL_FILE_LIMIT = 64 * 1024


def _read_exactly(fd: int, size: int) -> bytes:
    """Read size bytes, tolerating short reads."""
    chunks = []
    remaining = size
    while remaining > 0:
        chunk = os.read(fd, remaining)
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


class Source:
    """A file opened for lazy byte access.

    Large files are memory mapped, so regions nobody looks at never reach
    memory. Small files are read once. Either way the contents are exposed
    as a memoryview and slicing does not copy.

    Slices borrow the underlying buffer, so they must not outlive the
    Source. Use read() instead when the bytes need to escape.
    """

    __slots__ = ("path", "size", "_fd", "_map", "_data", "_view", "_closed")

    def __init__(
        self, path: str | os.PathLike[str], *, small_file_limit: int = SMALL_FILE_LIMIT
    ) -> None:
        self.path = os.fspath(path)
        self._map: mmap.mmap | None = None
        self._closed = False
        self._fd = os.open(self.path, os.O_RDONLY)
        try:
            self.size = os.fstat(self._fd).st_size
            if self.size == 0:
                # An empty file cannot be mapped, and there is nothing to read.
                self._data = b""
            elif self.size <= small_file_limit:
                self._data = _read_exactly(self._fd, self.size)
            else:
                self._map = mmap.mmap(self._fd, 0, access=mmap.ACCESS_READ)
                self._data = self._map
            self._view = memoryview(self._data)
        except BaseException:
            os.close(self._fd)
            raise

    @classmethod
    def from_bytes(cls, data: bytes, name: str = "<bytes>") -> Source:
        """Wrap an in-memory buffer, for tests and piped input."""
        obj = cls.__new__(cls)
        obj.path = name
        obj.size = len(data)
        obj._fd = -1
        obj._map = None
        obj._data = data
        obj._view = memoryview(data)
        obj._closed = False
        return obj

    @property
    def view(self) -> memoryview:
        """The whole file as a borrowed buffer."""
        self._check_open()
        return self._view

    def slice(self, start: int = 0, end: int | None = None) -> memoryview:
        """Borrow bytes in [start, end) without copying."""
        self._check_open()
        return self._view[start : self.size if end is None else end]

    def read(self, start: int = 0, end: int | None = None) -> bytes:
        """Copy bytes in [start, end), safe to keep after close()."""
        return bytes(self.slice(start, end))

    def find(self, needle: bytes, start: int = 0, end: int | None = None) -> int:
        """Offset of the first occurrence of needle, or -1."""
        self._check_open()
        return _engine.find(self._data, needle, start, end)

    def rfind(self, needle: bytes, start: int = 0, end: int | None = None) -> int:
        """Offset of the last occurrence of needle, or -1."""
        self._check_open()
        return _engine.rfind(self._data, needle, start, end)

    def findall(
        self,
        needle: bytes,
        start: int = 0,
        end: int | None = None,
        *,
        reverse: bool = False,
    ) -> list[int]:
        """Offsets of every non-overlapping occurrence."""
        self._check_open()
        walk = _engine.iter_rfind if reverse else _engine.iter_find
        return list(walk(self._data, needle, start, end))

    def find_nth(
        self, needle: bytes, n: int, start: int = 0, end: int | None = None
    ) -> int:
        """Offset of the nth occurrence, negative n counting from the end."""
        self._check_open()
        return _engine.find_nth(self._data, needle, n, start, end)

    def count(self, needle: bytes, start: int = 0, end: int | None = None) -> int:
        """How many non-overlapping occurrences of needle there are."""
        self._check_open()
        return _engine.count(self._data, needle, start, end)

    def line_span(self, offset: int) -> tuple[int, int]:
        """Content span of the line containing offset."""
        self._check_open()
        return _engine.line_span(self._data, offset)

    def line(self, offset: int) -> bytes:
        """The line containing offset, without its terminator."""
        return self.read(*self.line_span(offset))

    def lines(
        self, start: int = 0, end: int | None = None
    ) -> Iterator[tuple[int, int]]:
        """Content spans of the lines overlapping [start, end)."""
        self._check_open()
        return _engine.iter_line_spans(self._data, start, end)

    def advance_lines(self, offset: int, n: int) -> int:
        """Start of the line n lines from the one holding offset."""
        self._check_open()
        return _engine.advance_lines(self._data, offset, n)

    def line_number(self, offset: int) -> int:
        """One based line number of offset, for provenance and messages."""
        self._check_open()
        return _engine.line_number(self._data, offset)

    def close(self) -> None:
        if self._closed:
            return
        try:
            self._view.release()
        except BufferError as exc:
            # Leave the source open so the caller can drop the slices and
            # retry, rather than stranding a half closed object.
            raise BufferError(
                f"{self.path} still has borrowed slices, "
                "copy them with read() before closing"
            ) from exc
        self._closed = True
        if self._map is not None:
            self._map.close()
        if self._fd >= 0:
            os.close(self._fd)

    def _check_open(self) -> None:
        if self._closed:
            raise ValueError(f"{self.path} is closed")

    def __len__(self) -> int:
        return self.size

    def __enter__(self) -> Source:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def __repr__(self) -> str:
        kind = "mapped" if self._map is not None else "buffered"
        return f"<Source {self.path!r} {self.size} bytes {kind}>"


def open(
    path: str | os.PathLike[str], *, small_file_limit: int = SMALL_FILE_LIMIT
) -> Source:
    """Open a file for lazy byte access."""
    return Source(path, small_file_limit=small_file_limit)
