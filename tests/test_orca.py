import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from tolk import registry  # noqa: E402
from tolk._sniff import sniff  # noqa: E402
from tolk.extract import extract  # noqa: E402
from tolk.source import Source  # noqa: E402

DATA = os.path.join(os.path.dirname(__file__), "data")
OPT = os.path.join(DATA, "orca-opt.out")
TDDFT = os.path.join(DATA, "orca-tddft.out")


class OrcaSpecTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        registry.refresh()
        cls.spec = registry.get("orca")

    def test_spec_is_reachable_by_name(self) -> None:
        self.assertIn("orca", registry.formats())
        self.assertEqual(
            self.spec.names(),
            ["dipole", "energy", "excitations", "geometry", "version"],
        )

    def test_banner_is_detected_over_the_extension(self) -> None:
        self.assertEqual(sniff(OPT), "orca")
        self.assertEqual(sniff(TDDFT), "orca")

    def test_version(self) -> None:
        with Source(OPT) as src:
            self.assertEqual(extract(src, self.spec, "version").value, "6.1.0")

    def test_last_energy_wins(self) -> None:
        with Source(OPT) as src:
            value = extract(src, self.spec, "energy")
        self.assertTrue(value.ok)
        self.assertAlmostEqual(value.value, -270.965189516826, places=12)
        self.assertEqual(value.unit, "hartree")

    def test_dipole(self) -> None:
        with Source(OPT) as src:
            value = extract(src, self.spec, "dipole")
        self.assertAlmostEqual(value.value, 0.021864299, places=9)
        self.assertEqual(value.unit, "debye")

    def test_geometry_mixes_a_label_with_numbers(self) -> None:
        with Source(OPT) as src:
            value = extract(src, self.spec, "geometry")
        self.assertTrue(value.ok)
        self.assertEqual(len(value.value), 15)
        self.assertEqual(
            value.value[0],
            {"symbol": "C", "x": 0.035760, "y": -1.136467, "z": 0.299262},
        )
        self.assertEqual(value.value[-1]["symbol"], "H")
        self.assertEqual(value.unit, "angstrom")

    def test_excitations(self) -> None:
        with Source(TDDFT) as src:
            value = extract(src, self.spec, "excitations")
        self.assertTrue(value.ok)
        self.assertEqual(len(value.value), 10)
        # The transition label is three whitespace fields, so the numbers
        # start at index 3. Getting that wrong shifts every column.
        self.assertEqual(
            value.value[0],
            {
                "energy_ev": 5.070825,
                "wavenumber_cm": 40899.0,
                "wavelength_nm": 244.5,
                "fosc": 0.000000003,
            },
        )
        self.assertAlmostEqual(value.value[-1]["energy_ev"], 8.237910, places=6)

    def test_quantity_absent_from_this_run_gives_a_reason(self) -> None:
        with Source(OPT) as src:
            value = extract(src, self.spec, "excitations")
        self.assertFalse(value.ok)
        self.assertIn("not found", str(value.reason))

    def test_provenance_points_back_at_the_file(self) -> None:
        with Source(OPT) as src:
            value = extract(src, self.spec, "energy", with_lines=True)
            self.assertIsNotNone(value.where)
            line = value.where.line  # type: ignore[union-attr]
            offset = value.where.offset  # type: ignore[union-attr]
            self.assertEqual(src.line_number(offset), line)
            self.assertIn(b"FINAL SINGLE POINT ENERGY", src.line(offset))


if __name__ == "__main__":
    unittest.main()
