import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))

import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "update_goldens",
    os.path.join(os.path.dirname(__file__), "update-goldens.py"),
)
assert _spec is not None and _spec.loader is not None
update_goldens = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(update_goldens)

EXPECTED = os.path.join(os.path.dirname(__file__), "expected")


class GoldenTest(unittest.TestCase):
    def test_explain_output_matches_the_goldens(self) -> None:
        for case, fmt, fixture, names in update_goldens.CASES:
            with self.subTest(case=case):
                path = os.path.join(EXPECTED, f"{case}.txt")
                with open(path, encoding="utf-8") as handle:
                    expected = handle.read()
                actual = update_goldens.render(fmt, fixture, names)
                self.assertEqual(
                    actual,
                    expected,
                    f"{case} drifted, review and run make goldens",
                )


if __name__ == "__main__":
    unittest.main()
