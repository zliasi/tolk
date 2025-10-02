#include "tolk.h"

#include <stdlib.h>
#include <string.h>

/* Clamp a caller supplied range onto the buffer. Out of range offsets are
 * pinned rather than rejected, so callers can pass a window without checking
 * it against the file size first. */
static void clamp(tolk_off len, tolk_off *start, tolk_off *end) {
    if (*start < 0) {
        *start = 0;
    }
    if (*end < 0 || *end > len) {
        *end = len;
    }
    if (*start > *end) {
        *start = *end;
    }
}

/* Forward literal search.
 *
 * memchr on the first byte, then memcmp to confirm. The prefilter is what
 * makes this fast: memchr is vectorised in every libc worth using, so most
 * of the buffer is rejected at memory bandwidth and memcmp only runs at
 * candidate positions.
 */
static tolk_off find_in(const char *buf, const char *needle, tolk_off nlen,
                        tolk_off start, tolk_off end) {
    tolk_off last;
    const char *hit;
    tolk_off pos = start;

    if (nlen <= 0) {
        return TOLK_NOT_FOUND;
    }
    last = end - nlen;
    while (pos <= last) {
        hit = (const char *)memchr(buf + pos, needle[0], (size_t)(last - pos + 1));
        if (hit == NULL) {
            return TOLK_NOT_FOUND;
        }
        pos = (tolk_off)(hit - buf);
        if (memcmp(buf + pos, needle, (size_t)nlen) == 0) {
            return pos;
        }
        pos++;
    }
    return TOLK_NOT_FOUND;
}

/* Backward literal search.
 *
 * There is no portable memrchr, so this walks candidates from the right
 * checking the first byte before paying for memcmp. Anchors are usually
 * found within a few lines of where the search starts, so the scan is short
 * in practice even though the worst case is linear.
 */
static tolk_off rfind_in(const char *buf, const char *needle, tolk_off nlen,
                         tolk_off start, tolk_off end) {
    tolk_off pos;

    if (nlen <= 0) {
        return TOLK_NOT_FOUND;
    }
    for (pos = end - nlen; pos >= start; pos--) {
        if (buf[pos] == needle[0] &&
            memcmp(buf + pos, needle, (size_t)nlen) == 0) {
            return pos;
        }
    }
    return TOLK_NOT_FOUND;
}

tolk_off tolk_find(const char *buf, tolk_off len, const char *needle,
                   tolk_off nlen, tolk_off start, tolk_off end) {
    clamp(len, &start, &end);
    return find_in(buf, needle, nlen, start, end);
}

tolk_off tolk_rfind(const char *buf, tolk_off len, const char *needle,
                    tolk_off nlen, tolk_off start, tolk_off end) {
    clamp(len, &start, &end);
    return rfind_in(buf, needle, nlen, start, end);
}

tolk_off tolk_count(const char *buf, tolk_off len, const char *needle,
                    tolk_off nlen, tolk_off start, tolk_off end) {
    tolk_off found = 0;
    tolk_off pos;

    clamp(len, &start, &end);
    if (nlen <= 0) {
        return 0;
    }
    pos = start;
    for (;;) {
        tolk_off hit = find_in(buf, needle, nlen, pos, end);
        if (hit == TOLK_NOT_FOUND) {
            return found;
        }
        found++;
        pos = hit + nlen;
    }
}

tolk_off tolk_find_all(const char *buf, tolk_off len, const char *needle,
                       tolk_off nlen, tolk_off start, tolk_off end,
                       tolk_off *out, tolk_off max) {
    tolk_off written = 0;
    tolk_off pos;

    clamp(len, &start, &end);
    if (nlen <= 0) {
        return 0;
    }
    pos = start;
    while (written < max) {
        tolk_off hit = find_in(buf, needle, nlen, pos, end);
        if (hit == TOLK_NOT_FOUND) {
            break;
        }
        out[written++] = hit;
        pos = hit + nlen;
    }
    return written;
}

tolk_off tolk_find_nth(const char *buf, tolk_off len, const char *needle,
                       tolk_off nlen, tolk_off n, tolk_off start,
                       tolk_off end) {
    tolk_off seen = 0;
    tolk_off pos;

    clamp(len, &start, &end);
    if (nlen <= 0) {
        return TOLK_NOT_FOUND;
    }

    if (n >= 0) {
        pos = start;
        for (;;) {
            tolk_off hit = find_in(buf, needle, nlen, pos, end);
            if (hit == TOLK_NOT_FOUND) {
                return TOLK_NOT_FOUND;
            }
            if (seen == n) {
                return hit;
            }
            seen++;
            pos = hit + nlen;
        }
    }

    /* Negative n counts from the right, so -1 is the last occurrence. That
     * is the common case for output files, where a quantity is printed once
     * per cycle and only the final one matters. */
    pos = end;
    for (;;) {
        tolk_off hit = rfind_in(buf, needle, nlen, start, pos);
        if (hit == TOLK_NOT_FOUND) {
            return TOLK_NOT_FOUND;
        }
        if (seen == -n - 1) {
            return hit;
        }
        seen++;
        if (hit <= start) {
            return TOLK_NOT_FOUND;
        }
        pos = hit + nlen - 1;
    }
}

tolk_off tolk_line_start(const char *buf, tolk_off len, tolk_off offset) {
    tolk_off nl;

    if (offset <= 0) {
        return 0;
    }
    if (offset > len) {
        offset = len;
    }
    nl = rfind_in(buf, "\n", 1, 0, offset);
    return nl == TOLK_NOT_FOUND ? 0 : nl + 1;
}

tolk_off tolk_line_end(const char *buf, tolk_off len, tolk_off offset) {
    tolk_off nl;

    if (offset < 0) {
        offset = 0;
    }
    if (offset > len) {
        return len;
    }
    nl = find_in(buf, "\n", 1, offset, len);
    if (nl == TOLK_NOT_FOUND) {
        nl = len;
    }
    if (nl > offset && buf[nl - 1] == '\r') {
        return nl - 1;
    }
    return nl;
}

tolk_off tolk_advance_lines(const char *buf, tolk_off len, tolk_off offset,
                            tolk_off n) {
    tolk_off pos = tolk_line_start(buf, len, offset);
    tolk_off i;

    if (n > 0) {
        for (i = 0; i < n; i++) {
            tolk_off nl = find_in(buf, "\n", 1, pos, len);
            if (nl == TOLK_NOT_FOUND) {
                return len;
            }
            pos = nl + 1;
        }
    } else {
        for (i = 0; i < -n; i++) {
            if (pos == 0) {
                return 0;
            }
            pos = tolk_line_start(buf, len, pos - 1);
        }
    }
    return pos;
}

tolk_off tolk_line_number(const char *buf, tolk_off len, tolk_off offset) {
    tolk_off start = tolk_line_start(buf, len, offset);
    return tolk_count(buf, len, "\n", 1, 0, start) + 1;
}

/* Longest field this fast path will parse. Numbers in output files are far
 * shorter than this, and anything longer is not a number worth having. */
#define TOLK_FIELD_MAX 64

/* Fields on one line, as offsets into the buffer. Output tables are narrow,
 * so a fixed ceiling avoids allocating per line. */
#define TOLK_FIELDS_MAX 64

static int is_space(char c) {
    return c == ' ' || c == '\t' || c == '\r' || c == '\v' || c == '\f';
}

/* Split [from, to) on whitespace, recording where each field starts and
 * ends. Returns the field count, capped at TOLK_FIELDS_MAX. */
static tolk_off split_fields(const char *buf, tolk_off from, tolk_off to,
                             tolk_off *starts, tolk_off *ends) {
    tolk_off n = 0;
    tolk_off pos = from;

    while (pos < to && n < TOLK_FIELDS_MAX) {
        while (pos < to && is_space(buf[pos])) {
            pos++;
        }
        if (pos >= to) {
            break;
        }
        starts[n] = pos;
        while (pos < to && !is_space(buf[pos])) {
            pos++;
        }
        ends[n] = pos;
        n++;
    }
    return n;
}

static double parse_double(const char *buf, tolk_off from, tolk_off to) {
    char scratch[TOLK_FIELD_MAX + 1];
    tolk_off n = to - from;
    char *stop = NULL;
    double value;

    if (n <= 0 || n > TOLK_FIELD_MAX) {
        return (double)(0.0 / 0.0);
    }
    memcpy(scratch, buf + from, (size_t)n);
    scratch[n] = '\0';
    value = strtod(scratch, &stop);
    /* Anything left over means the field was not a number, not a number
     * with junk after it. */
    if (stop != scratch + n) {
        return (double)(0.0 / 0.0);
    }
    return value;
}

tolk_off tolk_scan_columns(const char *buf, tolk_off len, tolk_off start,
                           tolk_off end, const tolk_off *cols, tolk_off ncols,
                           double *out, tolk_off max_rows) {
    tolk_off starts[TOLK_FIELDS_MAX];
    tolk_off ends[TOLK_FIELDS_MAX];
    tolk_off rows = 0;
    tolk_off pos;

    clamp(len, &start, &end);
    if (ncols <= 0) {
        return 0;
    }

    pos = tolk_line_start(buf, len, start);
    while (pos <= end && rows < max_rows) {
        tolk_off stop = tolk_line_end(buf, len, pos);
        tolk_off nfields;
        tolk_off nl;

        if (stop > end) {
            stop = end;
        }
        nfields = split_fields(buf, pos, stop, starts, ends);
        if (nfields > 0) {
            tolk_off i;
            for (i = 0; i < ncols; i++) {
                tolk_off index = cols[i];
                if (index < 0) {
                    index += nfields;
                }
                if (index < 0 || index >= nfields) {
                    out[rows * ncols + i] = (double)(0.0 / 0.0);
                } else {
                    out[rows * ncols + i] =
                        parse_double(buf, starts[index], ends[index]);
                }
            }
            rows++;
        }

        nl = find_in(buf, "\n", 1, stop, len);
        if (nl == TOLK_NOT_FOUND) {
            break;
        }
        pos = nl + 1;
        if (pos >= len || pos > end) {
            break;
        }
    }
    return rows;
}
