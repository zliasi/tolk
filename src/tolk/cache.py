"""Remembering where anchors were.

Re-running the same extraction over an unchanged file repeats work whose
answer cannot have changed. The cache stores the byte offset an anchor was
found at, keyed by the file's identity and the spec that asked, so a repeat
query skips the scan and goes straight to the line.

Correctness comes first. A stale entry would be silently wrong, so the key
includes size and mtime, and every hit is verified by checking that the
anchor really is at the remembered offset before it is trusted.
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import tempfile
from dataclasses import dataclass, field

from .source import Source

CACHE_ENV = "TOLK_CACHE"

# Beyond this the cache is more bookkeeping than saving, so the oldest
# entries go.
MAX_ENTRIES = 20_000


def default_path() -> pathlib.Path:
    override = os.environ.get(CACHE_ENV)
    if override:
        return pathlib.Path(override).expanduser()
    root = os.environ.get("XDG_CACHE_HOME") or os.path.join(
        pathlib.Path.home(), ".cache"
    )
    return pathlib.Path(root) / "tolk" / "offsets.json"


def file_key(path: str) -> str:
    """Identity of a file for caching, cheap enough to compute every time."""
    stat = os.stat(path)
    return f"{os.path.abspath(path)}:{stat.st_size}:{stat.st_mtime_ns}"


def anchor_key(anchor: bytes, occurrence: object) -> str:
    digest = hashlib.blake2b(anchor, digest_size=8).hexdigest()
    return f"{digest}:{occurrence}"


@dataclass
class OffsetCache:
    """Anchor offsets remembered across runs."""

    path: pathlib.Path = field(default_factory=default_path)
    entries: dict[str, dict[str, int]] = field(default_factory=dict)
    hits: int = 0
    misses: int = 0
    loaded: bool = False

    def load(self) -> None:
        if self.loaded:
            return
        self.loaded = True
        try:
            with open(self.path, encoding="utf-8") as handle:
                raw = json.load(handle)
        except (OSError, ValueError):
            # A missing or corrupt cache is not an error. It is a cache.
            return
        if isinstance(raw, dict):
            self.entries = {
                key: value for key, value in raw.items() if isinstance(value, dict)
            }

    def lookup(self, src: Source, anchor: bytes, occurrence: object) -> int | None:
        """A remembered offset, verified against the file, or None."""
        self.load()
        try:
            fkey = file_key(src.path)
        except OSError:
            return None
        slot = self.entries.get(fkey)
        if slot is None:
            self.misses += 1
            return None
        offset = slot.get(anchor_key(anchor, occurrence))
        if offset is None:
            self.misses += 1
            return None
        # Verify rather than trust. Size and mtime can collide, and a wrong
        # offset would be a silently wrong number rather than a slow one.
        if src.read(offset, offset + len(anchor)) != anchor:
            self.misses += 1
            slot.pop(anchor_key(anchor, occurrence), None)
            return None
        self.hits += 1
        return offset

    def store(
        self, src: Source, anchor: bytes, occurrence: object, offset: int
    ) -> None:
        if offset < 0:
            return
        self.load()
        try:
            fkey = file_key(src.path)
        except OSError:
            return
        self.entries.setdefault(fkey, {})[anchor_key(anchor, occurrence)] = offset

    def save(self) -> None:
        """Write the cache out, atomically, best effort."""
        if not self.loaded or not self.entries:
            return
        trimmed = dict(list(self.entries.items())[-MAX_ENTRIES:])
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            handle = tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=self.path.parent,
                delete=False,
            )
            with handle:
                json.dump(trimmed, handle)
            os.replace(handle.name, self.path)
        except OSError:
            return

    def clear(self) -> None:
        self.entries = {}
        self.hits = 0
        self.misses = 0
        try:
            os.remove(self.path)
        except OSError:
            pass


_ACTIVE: OffsetCache | None = None


def active() -> OffsetCache | None:
    """The cache in use, or None when caching is off."""
    return _ACTIVE


def enable(path: str | os.PathLike[str] | None = None) -> OffsetCache:
    """Turn caching on for this process."""
    global _ACTIVE
    _ACTIVE = OffsetCache(pathlib.Path(path) if path else default_path())
    return _ACTIVE


def disable() -> None:
    """Turn caching off, writing out whatever was learned."""
    global _ACTIVE
    if _ACTIVE is not None:
        _ACTIVE.save()
    _ACTIVE = None
