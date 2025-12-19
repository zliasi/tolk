"""External conversion backends, declared as data.

tolk converts what it can itself and hands the rest to whatever is installed.
Which tools those are is not a decision the code should hold, so a backend is
a TOML file naming how to detect the tool, which format pairs it handles, and
the command to run.

Only Open Babel ships. Anything else belongs in ~/.config/tolk/backends/, or
in a pull request if it is widely useful.
"""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import tomllib
from dataclasses import dataclass

BACKEND_PATH_ENV = "TOLK_BACKENDS"

_BUILTIN_DIR = pathlib.Path(__file__).parent / "backends"

_CACHE: dict[str, Backend] | None = None


class BackendError(RuntimeError):
    """A backend was asked to do something it could not."""


@dataclass(frozen=True)
class Backend:
    """One external tool tolk knows how to drive."""

    name: str
    command: str
    detect: str = ""
    pairs: tuple[tuple[str, str], ...] = ()
    priority: int = 0
    source: str = "<builtin>"
    description: str = ""

    def available(self) -> bool:
        """Whether the tool is actually installed."""
        if not self.detect:
            return True
        return shutil.which(self.detect.split()[0]) is not None

    def handles(self, ifmt: str, ofmt: str) -> bool:
        """Whether this backend claims a conversion.

        A pair entry of "*" matches anything, so a tool can say it reads
        everything and writes one thing, or the reverse.
        """
        for want_in, want_out in self.pairs:
            if want_in in ("*", ifmt) and want_out in ("*", ofmt):
                return True
        return False

    def render(self, source: str, target: str, ifmt: str, ofmt: str) -> list[str]:
        """The command line, as a list, never a shell string."""
        filled = self.command.format(input=source, output=target, ifmt=ifmt, ofmt=ofmt)
        return filled.split()

    def run(self, source: str, target: str, ifmt: str, ofmt: str) -> str:
        """Convert, or say why it could not."""
        if not self.available():
            raise BackendError(f"{self.name} is not installed")
        argv = self.render(source, target, ifmt, ofmt)
        try:
            done = subprocess.run(argv, capture_output=True, text=True, check=False)
        except OSError as exc:
            raise BackendError(f"{self.name}: {exc}") from None
        if done.returncode != 0:
            detail = (done.stderr or done.stdout or "").strip().splitlines()
            tail = detail[-1] if detail else f"exit {done.returncode}"
            raise BackendError(f"{self.name}: {tail}")
        return " ".join(argv)


def backend_dirs() -> list[pathlib.Path]:
    """Directories searched for backends, lowest priority first."""
    dirs = [_BUILTIN_DIR, pathlib.Path.home() / ".config" / "tolk" / "backends"]
    for entry in os.environ.get(BACKEND_PATH_ENV, "").split(os.pathsep):
        if entry:
            dirs.append(pathlib.Path(entry).expanduser())
    return dirs


def load_all(*, refresh: bool = False) -> dict[str, Backend]:
    """Every reachable backend, keyed by name."""
    global _CACHE
    if _CACHE is not None and not refresh:
        return _CACHE

    found: dict[str, Backend] = {}
    for directory in backend_dirs():
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.toml")):
            backend = load(path)
            found[backend.name] = backend
    _CACHE = found
    return found


def load(path: str | os.PathLike[str]) -> Backend:
    """Parse one backend file."""
    text = pathlib.Path(path).read_text(encoding="utf-8")
    try:
        raw = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise BackendError(f"{path}: {exc}") from None

    name = raw.get("name") or pathlib.Path(path).stem
    command = raw.get("command")
    if not isinstance(command, str) or "{input}" not in command:
        raise BackendError(f"{path}: command must be a string containing {{input}}")

    pairs = []
    for entry in raw.get("pairs", []):
        if not isinstance(entry, list) or len(entry) != 2:
            raise BackendError(f"{path}: each pair must be [from, to]")
        pairs.append((str(entry[0]), str(entry[1])))

    return Backend(
        name=str(name),
        command=command,
        detect=str(raw.get("detect", "")),
        pairs=tuple(pairs),
        priority=int(raw.get("priority", 0)),
        source=str(path),
        description=str(raw.get("description", "")),
    )


def refresh() -> None:
    global _CACHE
    _CACHE = None


def find(ifmt: str, ofmt: str, *, installed_only: bool = True) -> Backend | None:
    """The best backend for a conversion, or None."""
    candidates = [
        backend
        for backend in load_all().values()
        if backend.handles(ifmt, ofmt)
        and (backend.available() if installed_only else True)
    ]
    if not candidates:
        return None
    return sorted(candidates, key=lambda b: (-b.priority, b.name))[0]


def names() -> list[str]:
    return sorted(load_all())
