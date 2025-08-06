import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from tolk import _sniff as sniff_module  # noqa: E402
from tolk._sniff import Signature, register, signatures, sniff  # noqa: E402
from tolk.source import Source  # noqa: E402

XYZ = b"3\ncomment\nO 0.0 0.0 0.0\nH 0.0 0.0 1.0\nH 1.0 0.0 0.0\n"


class SniffTest(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)

    def write(self, name: str, data: bytes) -> str:
        path = os.path.join(self.dir.name, name)
        with open(path, "wb") as handle:
            handle.write(data)
        return path

    def test_known_extensions(self) -> None:
        self.assertEqual(sniff(self.write("mol.xyz", XYZ)), "xyz")
        self.assertEqual(sniff(self.write("t.csv", b"a,b\n1,2\n")), "csv")
        self.assertEqual(sniff(self.write("t.tsv", b"a\tb\n")), "tsv")
        self.assertEqual(sniff(self.write("t.log", b"hello\n")), "text")

    def test_unknown_extension_is_none(self) -> None:
        self.assertIsNone(sniff(self.write("t.weird", b"x\n")))

    def test_empty_file_is_none(self) -> None:
        self.assertIsNone(sniff(self.write("empty.weird", b"")))

    def test_signatures_are_ordered_by_priority(self) -> None:
        priorities = [sig.priority for sig in signatures()]
        self.assertEqual(priorities, sorted(priorities, reverse=True))


class ContentSignatureTest(unittest.TestCase):
    def setUp(self) -> None:
        # Registration is global, so put the registry back afterwards.
        saved = list(sniff_module._REGISTRY)
        self.addCleanup(lambda: sniff_module._REGISTRY.__setitem__(slice(None), saved))

    def test_content_beats_extension(self) -> None:
        register(Signature("banner", contains=(b"PROGRAM BANNER",), priority=50))
        src = Source.from_bytes(b"   * PROGRAM BANNER *\nrest\n", name="job.log")
        self.assertEqual(sniff_module.sniff_source(src), "banner")

    def test_all_literals_must_be_present(self) -> None:
        register(Signature("both", contains=(b"ALPHA", b"BETA"), priority=50))
        half = Source.from_bytes(b"ALPHA only\n", name="job.weird")
        self.assertIsNone(sniff_module.sniff_source(half))
        full = Source.from_bytes(b"ALPHA and BETA\n", name="job.weird")
        self.assertEqual(sniff_module.sniff_source(full), "both")

    def test_literals_beyond_the_sniff_window_are_missed(self) -> None:
        register(Signature("late", contains=(b"LATE MARKER",), priority=50))
        data = b"x" * sniff_module.SNIFF_BYTES + b"LATE MARKER\n"
        src = Source.from_bytes(data, name="job.weird")
        self.assertIsNone(sniff_module.sniff_source(src))


if __name__ == "__main__":
    unittest.main()
