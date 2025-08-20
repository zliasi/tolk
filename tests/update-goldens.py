#!/usr/bin/env python3
"""Regenerate the explain goldens.

The goldens are the specification for what a spec is supposed to match. Run
this after changing a spec or the explain output, then read the diff line by
line before committing it.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from tolk import registry
from tolk._explain import explain_text
from tolk.source import Source

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
EXPECTED = os.path.join(HERE, "expected")

# One case per shipped quantity that the fixtures can exercise.
CASES = [
    ("orca-opt", "orca", "orca-opt.out", ["version", "energy", "dipole", "geometry"]),
    ("orca-tddft", "orca", "orca-tddft.out", ["version", "energy", "excitations"]),
]


def render(fmt: str, fixture: str, names: list[str]) -> str:
    spec = registry.get(fmt)
    path = os.path.join(DATA, fixture)
    blocks = []
    with Source(path) as src:
        for name in names:
            text = explain_text(src, spec, name)
            # Keep the golden stable across checkouts and machines.
            blocks.append(text.replace(spec.source, f"<specs>/{fmt}.toml"))
    return "\n\n".join(blocks) + "\n"


def main() -> None:
    os.makedirs(EXPECTED, exist_ok=True)
    for case, fmt, fixture, names in CASES:
        target = os.path.join(EXPECTED, f"{case}.txt")
        with open(target, "w", encoding="utf-8") as handle:
            handle.write(render(fmt, fixture, names))
        print(f"wrote {os.path.relpath(target, HERE)}")


if __name__ == "__main__":
    main()
