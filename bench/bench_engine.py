#!/usr/bin/env python3
"""Compare the backends on the operations that actually run.

Usage:
    python bench/bench_engine.py [--size MB] [--repeat N]

The interesting number is not raw search speed, it is how much of the file a
given operation has to touch. A tail read and a last-occurrence lookup should
be flat in file size, and a full scan should be linear. If that stops being
true, something has started reading what nobody asked for.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from tolk import _engine  # noqa: E402

try:
    from tolk import _cengine
except ImportError:
    _cengine = None  # type: ignore[assignment]

ANCHOR = b"FINAL SINGLE POINT ENERGY"


def reference() -> object:
    spec = importlib.util.spec_from_file_location(
        "_engine_ref", os.path.join(os.path.dirname(_engine.__file__), "_engine.py")
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_haystack(megabytes: int) -> bytes:
    """A file shaped like an output log: many lines, the anchor now and then."""
    line = b"  SCF iteration    12    -270.9651895168    0.000001234\n"
    block = line * 200 + ANCHOR + b"      -270.965189516826\n"
    copies = max(1, (megabytes * 1024 * 1024) // len(block))
    return block * copies


def timed(label: str, fn, repeat: int) -> tuple[str, float, object]:
    best = float("inf")
    result = None
    for _ in range(repeat):
        start = time.perf_counter()
        result = fn()
        best = min(best, time.perf_counter() - start)
    return label, best, result


def run(module: object, data: bytes, repeat: int) -> list[tuple[str, float, object]]:
    return [
        timed("find first", lambda: module.find(data, ANCHOR), repeat),
        timed("find last", lambda: module.rfind(data, ANCHOR), repeat),
        timed("nth -1", lambda: module.find_nth(data, ANCHOR, -1), repeat),
        timed("count", lambda: module.count(data, ANCHOR), repeat),
        timed("find all", lambda: list(module.iter_find(data, ANCHOR)), repeat),
        timed("line number at end", lambda: module.line_number(data, len(data) - 1), repeat),
        timed(
            "line span at end",
            lambda: module.line_span(data, len(data) - 100),
            repeat,
        ),
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--size", type=int, default=64, help="haystack size in MB")
    parser.add_argument("--repeat", type=int, default=3)
    args = parser.parse_args()

    data = make_haystack(args.size)
    print(f"backend in use: {_engine.BACKEND}")
    print(f"haystack: {len(data) / 1024 / 1024:.1f} MB, {data.count(ANCHOR)} anchors")
    print()

    py = run(reference(), data, args.repeat)
    if _cengine is None:
        print("c engine not built, showing python only")
        print(f"{'operation':22s} {'python':>10s}")
        for label, seconds, _ in py:
            print(f"{label:22s} {seconds * 1000:9.2f}ms")
        return 0

    c = run(_cengine, data, args.repeat)
    print(f"{'operation':22s} {'python':>10s} {'c':>10s} {'speedup':>9s}")
    for (label, py_s, py_r), (_, c_s, c_r) in zip(py, c):
        if py_r != c_r:
            print(f"{label:22s} MISMATCH {py_r!r} != {c_r!r}")
            continue
        print(
            f"{label:22s} {py_s * 1000:9.2f}ms {c_s * 1000:9.2f}ms "
            f"{py_s / c_s:8.1f}x"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
