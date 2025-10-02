"""cffi builder for the C engine.

The engine is optional. When it is not built, _engine.py keeps its pure
Python implementations and everything above the backend boundary behaves
identically, only slower.
"""

import os

from cffi import FFI

HERE = os.path.dirname(os.path.abspath(__file__))
CSRC = os.path.join(os.path.dirname(os.path.dirname(HERE)), "csrc")

DECLARATIONS = """
typedef int64_t tolk_off;

tolk_off tolk_find(const char *buf, tolk_off len, const char *needle,
                   tolk_off nlen, tolk_off start, tolk_off end);
tolk_off tolk_rfind(const char *buf, tolk_off len, const char *needle,
                    tolk_off nlen, tolk_off start, tolk_off end);
tolk_off tolk_count(const char *buf, tolk_off len, const char *needle,
                    tolk_off nlen, tolk_off start, tolk_off end);
tolk_off tolk_find_all(const char *buf, tolk_off len, const char *needle,
                       tolk_off nlen, tolk_off start, tolk_off end,
                       tolk_off *out, tolk_off max);
tolk_off tolk_find_nth(const char *buf, tolk_off len, const char *needle,
                       tolk_off nlen, tolk_off n, tolk_off start,
                       tolk_off end);
tolk_off tolk_line_start(const char *buf, tolk_off len, tolk_off offset);
tolk_off tolk_line_end(const char *buf, tolk_off len, tolk_off offset);
tolk_off tolk_advance_lines(const char *buf, tolk_off len, tolk_off offset,
                            tolk_off n);
tolk_off tolk_line_number(const char *buf, tolk_off len, tolk_off offset);
tolk_off tolk_scan_columns(const char *buf, tolk_off len, tolk_off start,
                           tolk_off end, const tolk_off *cols, tolk_off ncols,
                           double *out, tolk_off max_rows);
"""

ffibuilder = FFI()
ffibuilder.cdef(DECLARATIONS)
ffibuilder.set_source(
    "tolk._tolk",
    '#include "tolk.h"',
    sources=[os.path.join(CSRC, "tolk.c")],
    include_dirs=[CSRC],
    extra_compile_args=["-O2", "-std=c99"],
)


if __name__ == "__main__":
    ffibuilder.compile(verbose=True)
