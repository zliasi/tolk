/* Byte location primitives.
 *
 * Every function takes a buffer and byte offsets and returns byte offsets.
 * Nothing here knows what a file contains, and nothing here allocates. The
 * pure-Python backend in _engine.py implements the same contract, so the two
 * are interchangeable.
 *
 * Offsets are signed so -1 can mean "not found" without a separate out
 * parameter. Ranges are half open, [start, end).
 */

#ifndef TOLK_H
#define TOLK_H

#include <stddef.h>
#include <stdint.h>

typedef int64_t tolk_off;

#define TOLK_NOT_FOUND ((tolk_off)-1)

/* First occurrence of needle in [start, end), or TOLK_NOT_FOUND. */
tolk_off tolk_find(const char *buf, tolk_off len, const char *needle,
                   tolk_off nlen, tolk_off start, tolk_off end);

/* Last occurrence of needle in [start, end), or TOLK_NOT_FOUND. */
tolk_off tolk_rfind(const char *buf, tolk_off len, const char *needle,
                    tolk_off nlen, tolk_off start, tolk_off end);

/* Non-overlapping occurrences of needle in [start, end). */
tolk_off tolk_count(const char *buf, tolk_off len, const char *needle,
                    tolk_off nlen, tolk_off start, tolk_off end);

/* Fill out with up to max non-overlapping occurrences, return how many were
 * written. Callers size the array from tolk_count when they need all of
 * them. */
tolk_off tolk_find_all(const char *buf, tolk_off len, const char *needle,
                       tolk_off nlen, tolk_off start, tolk_off end,
                       tolk_off *out, tolk_off max);

/* Offset of the nth occurrence, negative n counting from the right. */
tolk_off tolk_find_nth(const char *buf, tolk_off len, const char *needle,
                       tolk_off nlen, tolk_off n, tolk_off start,
                       tolk_off end);

/* Start of the line holding offset. An offset on a newline belongs to the
 * line that newline ends. */
tolk_off tolk_line_start(const char *buf, tolk_off len, tolk_off offset);

/* End of the content of the line holding offset. The newline is excluded,
 * and so is a carriage return before it. */
tolk_off tolk_line_end(const char *buf, tolk_off len, tolk_off offset);

/* Start of the line n lines from the one holding offset. Walks off the end
 * to len and off the front to 0 rather than failing. */
tolk_off tolk_advance_lines(const char *buf, tolk_off len, tolk_off offset,
                            tolk_off n);

/* One based line number of offset. Reads everything before it, by
 * definition. */
tolk_off tolk_line_number(const char *buf, tolk_off len, tolk_off offset);

/* Parse numeric columns out of a block of whitespace separated lines.
 *
 * Walks [start, end) line by line, splits each line on whitespace, and
 * writes the requested field indices as doubles into out, row major. A
 * negative index counts from the right of the line.
 *
 * A field that does not parse, or a line too short to hold one, becomes NaN
 * so the caller can apply its own rule about what counts as data. Lines with
 * no fields at all are skipped entirely.
 *
 * Returns the number of rows written, at most max_rows.
 */
tolk_off tolk_scan_columns(const char *buf, tolk_off len, tolk_off start,
                           tolk_off end, const tolk_off *cols, tolk_off ncols,
                           double *out, tolk_off max_rows);

#endif /* TOLK_H */
