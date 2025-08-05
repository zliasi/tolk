import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from tolk import _engine  # noqa: E402
from tolk._engine import BLANK  # noqa: E402

HAYSTACK = b"aa MARK bb MARK cc MARK dd"

TABLE = b"""HEADER
----
  a 1
  b 2
  c 3

after
"""


class SearchTest(unittest.TestCase):
    def test_find_and_rfind(self) -> None:
        self.assertEqual(_engine.find(HAYSTACK, b"MARK"), 3)
        self.assertEqual(_engine.rfind(HAYSTACK, b"MARK"), 19)
        self.assertEqual(_engine.find(HAYSTACK, b"missing"), -1)

    def test_bounded_search(self) -> None:
        self.assertEqual(_engine.find(HAYSTACK, b"MARK", 0, 6), -1)
        self.assertEqual(_engine.rfind(HAYSTACK, b"MARK", 0, 10), 3)

    def test_iteration_is_non_overlapping(self) -> None:
        self.assertEqual(list(_engine.iter_find(HAYSTACK, b"MARK")), [3, 11, 19])
        self.assertEqual(list(_engine.iter_find(b"aaaa", b"aa")), [0, 2])

    def test_reverse_iteration_mirrors_forward(self) -> None:
        forward = list(_engine.iter_find(HAYSTACK, b"MARK"))
        reverse = list(_engine.iter_rfind(HAYSTACK, b"MARK"))
        self.assertEqual(reverse, list(reversed(forward)))

    def test_count(self) -> None:
        self.assertEqual(_engine.count(HAYSTACK, b"MARK"), 3)
        self.assertEqual(_engine.count(HAYSTACK, b"MARK", 4), 2)

    def test_nth_from_the_left(self) -> None:
        self.assertEqual(_engine.find_nth(HAYSTACK, b"MARK", 0), 3)
        self.assertEqual(_engine.find_nth(HAYSTACK, b"MARK", 2), 19)
        self.assertEqual(_engine.find_nth(HAYSTACK, b"MARK", 9), -1)

    def test_nth_from_the_right(self) -> None:
        self.assertEqual(_engine.find_nth(HAYSTACK, b"MARK", -1), 19)
        self.assertEqual(_engine.find_nth(HAYSTACK, b"MARK", -3), 3)
        self.assertEqual(_engine.find_nth(HAYSTACK, b"MARK", -9), -1)

    def test_empty_needle_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            _engine.count(HAYSTACK, b"")


class LineTest(unittest.TestCase):
    def spans(self, data: bytes) -> list[bytes]:
        return [bytes(data[a:b]) for a, b in _engine.iter_line_spans(data)]

    def test_lines_without_trailing_newline(self) -> None:
        self.assertEqual(self.spans(b"alpha\nbeta"), [b"alpha", b"beta"])

    def test_trailing_newline_adds_no_empty_line(self) -> None:
        self.assertEqual(self.spans(b"alpha\nbeta\n"), [b"alpha", b"beta"])

    def test_blank_lines_inside_the_file_survive(self) -> None:
        self.assertEqual(self.spans(b"a\n\nb\n"), [b"a", b"", b"b"])

    def test_carriage_returns_are_not_content(self) -> None:
        self.assertEqual(self.spans(b"one\r\ntwo\r\n"), [b"one", b"two"])

    def test_empty_file_has_no_lines(self) -> None:
        self.assertEqual(self.spans(b""), [])

    def test_line_start_and_end(self) -> None:
        data = b"alpha\nbeta\ngamma"
        self.assertEqual(_engine.line_span(data, 7), (6, 10))
        # An offset sitting on the newline belongs to the line it closes.
        self.assertEqual(_engine.line_span(data, 5), (0, 5))

    def test_region_iteration_enters_the_line_it_lands_in(self) -> None:
        data = b"alpha\nbeta\ngamma"
        spans = list(_engine.iter_line_spans(data, 7, 12))
        self.assertEqual(spans, [(6, 10), (11, 16)])

    def test_advance_clamps_at_both_ends(self) -> None:
        data = b"alpha\nbeta\ngamma"
        self.assertEqual(_engine.advance_lines(data, 0, 2), 11)
        self.assertEqual(_engine.advance_lines(data, 12, -1), 6)
        self.assertEqual(_engine.advance_lines(data, 0, 99), len(data))
        self.assertEqual(_engine.advance_lines(data, 12, -99), 0)

    def test_line_number_is_one_based(self) -> None:
        data = b"alpha\nbeta\ngamma"
        self.assertEqual(_engine.line_number(data, 0), 1)
        self.assertEqual(_engine.line_number(data, 7), 2)
        self.assertEqual(_engine.line_number(data, 12), 3)


class BlockTest(unittest.TestCase):
    def lines(self, **kwargs: object) -> list[bytes]:
        offset = _engine.find(TABLE, b"HEADER")
        start, end = _engine.block_span(TABLE, offset, **kwargs)  # type: ignore[arg-type]
        return [
            bytes(TABLE[a:b]) for a, b in _engine.iter_line_spans(TABLE, start, end)
        ]

    def test_stop_on_blank(self) -> None:
        self.assertEqual(
            self.lines(skip=2, until=BLANK), [b"  a 1", b"  b 2", b"  c 3"]
        )

    def test_stop_on_literal_ignores_indentation(self) -> None:
        self.assertEqual(self.lines(skip=2, until=b"c"), [b"  a 1", b"  b 2"])

    def test_max_lines_bounds_the_block(self) -> None:
        self.assertEqual(self.lines(skip=2, max_lines=2), [b"  a 1", b"  b 2"])

    def test_skipping_past_the_end_is_empty(self) -> None:
        offset = _engine.find(TABLE, b"HEADER")
        span = _engine.block_span(TABLE, offset, skip=99, until=BLANK)
        self.assertEqual(span, (len(TABLE), len(TABLE)))


if __name__ == "__main__":
    unittest.main()
