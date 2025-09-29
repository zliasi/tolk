#include "tolk.h"

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
