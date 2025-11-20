"""Input file templates.

Deliberately dumb. A template is text with {placeholders}, and rendering
substitutes them. tolk does not know what a valid input file for any program
looks like and should not pretend to, because that knowledge goes stale and
belongs to whoever runs the program.

What it does do is refuse quietly broken output. A placeholder with no value
is an error, not an empty string, since a job that runs with a blank basis
set wastes more time than one that never starts.
"""

from __future__ import annotations

import os
import pathlib
import re
import string
from dataclasses import dataclass

TEMPLATE_PATH_ENV = "TOLK_TEMPLATES"

_BUILTIN_DIR = pathlib.Path(__file__).parent / "templates"

_PLACEHOLDER = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


class TemplateError(ValueError):
    """A template could not be rendered."""


@dataclass(frozen=True)
class Template:
    """A text template and where it came from."""

    name: str
    text: str
    source: str = "<string>"

    @property
    def placeholders(self) -> list[str]:
        """Every name the template expects, in first seen order."""
        seen: dict[str, None] = {}
        for match in _PLACEHOLDER.finditer(self.text):
            seen.setdefault(match.group(1), None)
        return list(seen)

    def render(self, values: dict[str, object]) -> str:
        """Fill the template, or say exactly what is missing."""
        missing = [name for name in self.placeholders if name not in values]
        if missing:
            raise TemplateError(
                f"{self.name}: no value for {', '.join(missing)}. "
                f"needs {', '.join(self.placeholders)}"
            )
        try:
            return string.Template(_PLACEHOLDER.sub(r"${\1}", self.text)).substitute(
                {k: str(v) for k, v in values.items()}
            )
        except (KeyError, ValueError) as exc:
            raise TemplateError(f"{self.name}: {exc}") from None


def template_dirs() -> list[pathlib.Path]:
    dirs = [_BUILTIN_DIR, pathlib.Path.home() / ".config" / "tolk" / "templates"]
    for entry in os.environ.get(TEMPLATE_PATH_ENV, "").split(os.pathsep):
        if entry:
            dirs.append(pathlib.Path(entry).expanduser())
    return dirs


def load_all() -> dict[str, Template]:
    """Every reachable template, keyed by name, later directories winning."""
    found: dict[str, Template] = {}
    for directory in template_dirs():
        if not directory.is_dir():
            continue
        for path in sorted(directory.iterdir()):
            if path.is_file():
                found[path.stem] = Template(
                    path.stem, path.read_text(encoding="utf-8"), str(path)
                )
    return found


def get(name: str) -> Template:
    templates = load_all()
    try:
        return templates[name]
    except KeyError:
        known = ", ".join(sorted(templates)) or "none"
        raise TemplateError(f"no template {name!r}, known: {known}") from None


def names() -> list[str]:
    return sorted(load_all())


def parse_settings(pairs: list[str]) -> dict[str, object]:
    """Turn key=value arguments into a mapping."""
    values: dict[str, object] = {}
    for pair in pairs:
        key, sep, value = pair.partition("=")
        if not sep or not key:
            raise TemplateError(f"{pair!r} is not key=value")
        values[key.strip()] = value
    return values
