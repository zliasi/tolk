import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from tolk.source import SMALL_FILE_LIMIT, Source  # noqa: E402


class SourceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)

    def write(self, name: str, data: bytes) -> str:
        path = os.path.join(self.dir.name, name)
        with open(path, "wb") as handle:
            handle.write(data)
        return path

    def test_small_file_is_buffered(self) -> None:
        with Source(self.write("small", b"hello")) as src:
            self.assertEqual(src.size, 5)
            self.assertEqual(src.read(), b"hello")
            self.assertIn("buffered", repr(src))

    def test_large_file_is_mapped(self) -> None:
        data = b"x" * (SMALL_FILE_LIMIT + 1)
        with Source(self.write("large", data)) as src:
            self.assertEqual(src.size, len(data))
            self.assertIn("mapped", repr(src))
            self.assertEqual(src.read(0, 4), b"xxxx")

    def test_empty_file_is_not_mapped(self) -> None:
        with Source(self.write("empty", b"")) as src:
            self.assertEqual(src.size, 0)
            self.assertEqual(src.read(), b"")
            self.assertEqual(list(src.lines()), [])

    def test_slice_does_not_copy(self) -> None:
        src = Source.from_bytes(b"abcdef")
        view = src.slice(1, 3)
        self.assertIsInstance(view, memoryview)
        self.assertEqual(bytes(view), b"bc")

    def test_read_survives_close(self) -> None:
        src = Source(self.write("copy", b"abcdef"))
        data = src.read(0, 3)
        src.close()
        self.assertEqual(data, b"abc")

    def test_close_reports_live_slices(self) -> None:
        src = Source(self.write("borrow", b"x" * (SMALL_FILE_LIMIT + 1)))
        view = src.slice(0, 4)
        with self.assertRaises(BufferError):
            src.close()
        # The source stays usable so the caller can drop the slice and retry.
        del view
        src.close()

    def test_use_after_close_is_refused(self) -> None:
        src = Source(self.write("closed", b"abc"))
        src.close()
        with self.assertRaises(ValueError):
            src.read()

    def test_close_is_idempotent(self) -> None:
        src = Source(self.write("twice", b"abc"))
        src.close()
        src.close()

    def test_from_bytes_needs_no_file(self) -> None:
        src = Source.from_bytes(b"in memory", name="<test>")
        self.assertEqual(src.path, "<test>")
        self.assertEqual(src.read(), b"in memory")


class TailHeadTest(unittest.TestCase):
    def setUp(self) -> None:
        self.src = Source.from_bytes(b"alpha\nbeta\ngamma\ndelta\n")

    def test_tail_starts_on_a_line_boundary(self) -> None:
        self.assertEqual(self.src.tail(12), b"delta\n")

    def test_tail_can_keep_the_partial_line(self) -> None:
        self.assertEqual(self.src.tail(12, whole_lines=False), b"gamma\ndelta\n")

    def test_tail_larger_than_file_returns_everything(self) -> None:
        self.assertEqual(self.src.tail(9999), self.src.read())

    def test_head_trims_to_whole_lines(self) -> None:
        self.assertEqual(self.src.head(8), b"alpha\nbe")
        self.assertEqual(self.src.head(8, whole_lines=True), b"alpha\n")

    def test_head_larger_than_file_returns_everything(self) -> None:
        self.assertEqual(self.src.head(9999, whole_lines=True), self.src.read())


if __name__ == "__main__":
    unittest.main()
