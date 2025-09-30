"""Both backends must answer identically.

The C engine is only safe to swap in if it is indistinguishable from the
reference implementation, so these tests run the same inputs through both and
compare. When the extension is not built the C half is skipped, which is also
how the fallback gets exercised on machines with no compiler.
"""

import importlib
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from tolk import _engine  # noqa: E402

try:
    from tolk import _cengine
except ImportError:  # pragma: no cover - depends on the build
    _cengine = None  # type: ignore[assignment]

DATA = os.path.join(os.path.dirname(__file__), "data")

CASES = [
    b"",
    b"\n",
    b"a",
    b"alpha\nbeta\ngamma",
    b"alpha\nbeta\ngamma\n",
    b"one\r\ntwo\r\n",
    b"a\n\nb\n",
    b"aa MARK bb MARK cc MARK dd",
    b"MARK",
    b"MARKMARKMARK",
    b"x" * 1000 + b"MARK" + b"y" * 1000,
]

NEEDLES = [b"MARK", b"a", b"\n", b"zz", b"alpha", b"MARKMARK"]


def _reference() -> object:
    """A pristine copy of the pure-Python engine.

    Importing _engine normally may already have the C functions bound over
    it, so the reference is loaded from source under a different name.
    """
    spec = importlib.util.spec_from_file_location(
        "_engine_reference",
        os.path.join(os.path.dirname(_engine.__file__), "_engine.py"),
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("_engine_reference", module)
    spec.loader.exec_module(module)
    return module


@unittest.skipIf(_cengine is None, "c engine not built")
class ParityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.py = _reference()

    def test_find_and_rfind(self) -> None:
        for data in CASES:
            for needle in NEEDLES:
                with self.subTest(data=data[:20], needle=needle):
                    self.assertEqual(
                        _cengine.find(data, needle), self.py.find(data, needle)
                    )
                    self.assertEqual(
                        _cengine.rfind(data, needle), self.py.rfind(data, needle)
                    )

    def test_bounded_search(self) -> None:
        data = b"aa MARK bb MARK cc MARK dd"
        for start in range(0, len(data), 3):
            for end in range(start, len(data) + 1, 4):
                with self.subTest(start=start, end=end):
                    self.assertEqual(
                        _cengine.find(data, b"MARK", start, end),
                        self.py.find(data, b"MARK", start, end),
                    )
                    self.assertEqual(
                        _cengine.rfind(data, b"MARK", start, end),
                        self.py.rfind(data, b"MARK", start, end),
                    )

    def test_count_and_iteration(self) -> None:
        for data in CASES:
            for needle in NEEDLES:
                with self.subTest(data=data[:20], needle=needle):
                    self.assertEqual(
                        _cengine.count(data, needle), self.py.count(data, needle)
                    )
                    self.assertEqual(
                        list(_cengine.iter_find(data, needle)),
                        list(self.py.iter_find(data, needle)),
                    )
                    self.assertEqual(
                        list(_cengine.iter_rfind(data, needle)),
                        list(self.py.iter_rfind(data, needle)),
                    )

    def test_find_nth_including_negative(self) -> None:
        data = b"aa MARK bb MARK cc MARK dd"
        for n in range(-5, 5):
            with self.subTest(n=n):
                self.assertEqual(
                    _cengine.find_nth(data, b"MARK", n),
                    self.py.find_nth(data, b"MARK", n),
                )

    def test_line_operations(self) -> None:
        for data in CASES:
            for offset in range(0, len(data) + 2):
                with self.subTest(data=data[:20], offset=offset):
                    self.assertEqual(
                        _cengine.line_span(data, offset),
                        self.py.line_span(data, offset),
                    )
                    self.assertEqual(
                        _cengine.line_number(data, offset),
                        self.py.line_number(data, offset),
                    )
                    for step in (-3, -1, 0, 1, 3):
                        self.assertEqual(
                            _cengine.advance_lines(data, offset, step),
                            self.py.advance_lines(data, offset, step),
                        )

    def test_empty_needle_is_refused_by_both(self) -> None:
        with self.assertRaises(ValueError):
            _cengine.count(b"abc", b"")
        with self.assertRaises(ValueError):
            self.py.count(b"abc", b"")

    def test_real_files_agree(self) -> None:
        for name in sorted(os.listdir(DATA)):
            path = os.path.join(DATA, name)
            with open(path, "rb") as handle:
                data = handle.read()
            for needle in (b"ENERGY", b"\n", b"CARTESIAN", b"Excited State"):
                with self.subTest(name=name, needle=needle):
                    self.assertEqual(
                        list(_cengine.iter_find(data, needle)),
                        list(self.py.iter_find(data, needle)),
                    )
                    self.assertEqual(
                        _cengine.find_nth(data, needle, -1),
                        self.py.find_nth(data, needle, -1),
                    )


class BackendTest(unittest.TestCase):
    def test_backend_is_named(self) -> None:
        self.assertIn(_engine.BACKEND, ("python", "c"))

    def test_the_pure_python_path_still_works(self) -> None:
        # Whatever is installed, the reference implementation has to stay
        # correct, since it is what runs on an uncompiled checkout.
        py = _reference()
        self.assertEqual(py.find(b"aa MARK", b"MARK"), 3)
        self.assertEqual(py.BACKEND, "python")


if __name__ == "__main__":
    unittest.main()
