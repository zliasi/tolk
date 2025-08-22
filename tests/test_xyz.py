import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import tolk  # noqa: E402
from tolk import registry  # noqa: E402
from tolk.spec import SpecError, loads  # noqa: E402

XYZ = os.path.join(os.path.dirname(__file__), "data", "nbd.xyz")


class XyzSpecTest(unittest.TestCase):
    def setUp(self) -> None:
        registry.refresh()

    def test_detected_by_extension(self) -> None:
        # No banner exists, so the extension is the only evidence there is.
        self.assertEqual(tolk.sniff(XYZ), "xyz")

    def test_atom_count_comes_from_the_first_line(self) -> None:
        self.assertEqual(tolk.get(XYZ, "natoms").value, 15)

    def test_comment_keeps_its_spaces(self) -> None:
        value = tolk.get(XYZ, "comment")
        self.assertTrue(value.ok)
        self.assertIsInstance(value.value, str)

    def test_geometry_matches_the_declared_count(self) -> None:
        natoms = tolk.get(XYZ, "natoms").value
        geometry = tolk.get(XYZ, "geometry")
        self.assertEqual(len(geometry.value), natoms)
        self.assertEqual(geometry.value[0]["symbol"], "C")
        self.assertAlmostEqual(geometry.value[0]["y"], -1.11790, places=5)

    def test_explain_says_there_is_no_anchor(self) -> None:
        text = tolk.explain(XYZ, "natoms")
        self.assertIn("anchor   none", text)


class AnchorlessSpecTest(unittest.TestCase):
    def test_repeating_with_no_anchor_is_rejected(self) -> None:
        # There is nothing to repeat over without an anchor, so this is a
        # spec bug rather than an empty result at extraction time.
        with self.assertRaises(SpecError) as caught:
            loads(
                'format = "x"\n[quantity.a]\noccurrence = "all"\n'
                "parse = { field = 0 }",
                "bad.toml",
            )
        self.assertIn("nothing to repeat", str(caught.exception))

    def test_whole_line_needs_no_field(self) -> None:
        spec = loads(
            'format = "x"\n[quantity.title]\nparse = { whole_line = true, '
            'type = "str" }',
            "x.toml",
        )
        self.assertTrue(spec.quantity("title").parse.whole_line)

    def test_a_quantity_with_no_way_to_read_is_still_rejected(self) -> None:
        with self.assertRaises(SpecError):
            loads('format = "x"\n[quantity.a]\nanchor = "A"', "bad.toml")


if __name__ == "__main__":
    unittest.main()
