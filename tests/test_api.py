import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import tolk  # noqa: E402
from tolk import registry  # noqa: E402
from tolk.value import Value  # noqa: E402

DATA = os.path.join(os.path.dirname(__file__), "data")
OPT = os.path.join(DATA, "orca-opt.out")
TDDFT = os.path.join(DATA, "orca-tddft.out")


class ApiTest(unittest.TestCase):
    def setUp(self) -> None:
        registry.refresh()

    def test_formats_and_spec(self) -> None:
        self.assertIn("orca", tolk.formats())
        self.assertEqual(tolk.spec("orca").format, "orca")

    def test_single_quantity_returns_one_value(self) -> None:
        value = tolk.get(OPT, "energy")
        self.assertIsInstance(value, Value)
        self.assertAlmostEqual(value.value, -270.965189516826, places=12)

    def test_list_of_quantities_returns_a_dict(self) -> None:
        values = tolk.get(TDDFT, ["version", "excitations"])
        self.assertIsInstance(values, dict)
        self.assertEqual(sorted(values), ["excitations", "version"])
        self.assertEqual(values["version"].value, "6.1.0")

    def test_format_can_be_forced(self) -> None:
        value = tolk.get(OPT, "energy", format="orca")
        self.assertTrue(value.ok)

    def test_undetectable_format_is_refused(self) -> None:
        here = os.path.join(os.path.dirname(__file__), "..", "LICENSE")
        with self.assertRaises(tolk.SpecError) as caught:
            tolk.get(here, "energy")
        self.assertIn("could not detect", str(caught.exception))

    def test_unknown_format_is_refused(self) -> None:
        with self.assertRaises(tolk.SpecError):
            tolk.get(OPT, "energy", format="nosuchformat")

    def test_missing_quantity_does_not_raise(self) -> None:
        # A quantity this run never printed is a miss with a reason, not an
        # exception, so a sweep over many files survives the odd broken one.
        value = tolk.get(OPT, "excitations")
        self.assertFalse(value.ok)
        self.assertIn("not found", str(value.reason))

    def test_explain_names_the_spec_and_the_byte(self) -> None:
        text = tolk.explain(OPT, "energy")
        self.assertIn("quantity energy (orca,", text)
        self.assertIn("FINAL SINGLE POINT ENERGY", text)
        self.assertIn("value    -270.965189516826 hartree", text)

    def test_explain_reports_a_miss(self) -> None:
        text = tolk.explain(OPT, "excitations")
        self.assertIn("found    no", text)


if __name__ == "__main__":
    unittest.main()
