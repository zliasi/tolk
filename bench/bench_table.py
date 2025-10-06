#!/usr/bin/env python3
"""Measure the table path, which is where the per field work lives.

A block of a few thousand rows costs one float() call per cell in Python.
That is the cost the bulk column parser exists to remove, so this benchmark
is the one that justifies the C engine.
"""

from __future__ import annotations

import os
import sys
import time

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src")
)

from tolk import _engine  # noqa: E402
from tolk.source import Source  # noqa: E402

HEADER = b"  TABLE OF RESULTS\n  ----\n"
ROW = b"  0-1A  ->  {n}-1A    5.070825   40899.0   244.5   0.000000003\n"


def make(rows: int) -> bytes:
    body = b"".join(ROW.replace(b"{n}", str(i).encode()) for i in range(rows))
    return HEADER + body + b"\n"


def python_rows(src: Source, start: int, end: int, cols: list[int]) -> int:
    count = 0
    for line_from, line_to in src.lines(start, end):
        fields = src.read(line_from, line_to).split()
        if len(fields) <= max(cols):
            continue
        try:
            [float(fields[c]) for c in cols]
        except ValueError:
            continue
        count += 1
    return count


def main() -> int:
    cols = [3, 4, 5, 6]
    print(f"backend in use: {_engine.BACKEND}")
    print(f"{'rows':>8s} {'python':>10s} {'c':>10s} {'speedup':>9s}")
    for rows in (100, 1_000, 10_000, 100_000):
        data = make(rows)
        src = Source.from_bytes(data)
        start, end = src.block_span(0, skip=2, until=_engine.BLANK)

        t0 = time.perf_counter()
        n_py = python_rows(src, start, end, cols)
        py = time.perf_counter() - t0

        t0 = time.perf_counter()
        parsed = src.scan_columns(start, end, cols)
        c = time.perf_counter() - t0

        if parsed is None:
            print(f"{rows:8d} {py * 1000:9.2f}ms   (c engine not built)")
            continue
        assert len(parsed) == n_py, (len(parsed), n_py)
        print(f"{rows:8d} {py * 1000:9.2f}ms {c * 1000:9.2f}ms {py / c:8.1f}x")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
