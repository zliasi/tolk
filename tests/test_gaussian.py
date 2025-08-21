import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import tolk  # noqa: E402
from tolk import registry  # noqa: E402
from tolk.extract import extract  # noqa: E402
from tolk.source import Source  # noqa: E402

DATA = os.path.join(os.path.dirname(__file__), "data")
FREQ = os.path.join(DATA, "gaussian-freq.out")
TD = os.path.join(DATA, "gaussian-td.out")


class GaussianSpecTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        registry.refresh()
        cls.spec = registry.get("gaussian")

    def test_banner_is_detected_despite_the_out_extension(self) -> None:
        # Both ORCA and Gaussian write .out, so only the banner separates
        # them. Neither spec claims the extension.
        self.assertEqual(tolk.sniff(FREQ), "gaussian")
        self.assertEqual(tolk.sniff(os.path.join(DATA, "orca-opt.out")), "orca")

    def test_version_strips_the_trailing_comma(self) -> None:
        with Source(FREQ) as src:
            self.assertEqual(extract(src, self.spec, "version").value, "A.03")

    def test_scf_energy_is_counted_from_the_left(self) -> None:
        with Source(FREQ) as src:
            value = extract(src, self.spec, "energy")
        self.assertAlmostEqual(value.value, -270.962124365, places=9)
        self.assertEqual(value.unit, "hartree")

    def test_thermochemistry(self) -> None:
        with Source(FREQ) as src:
            self.assertAlmostEqual(
                extract(src, self.spec, "zpe_correction").value, 0.130141, places=6
            )
            self.assertAlmostEqual(
                extract(src, self.spec, "energy_zpe").value, -270.831983, places=6
            )
            self.assertAlmostEqual(
                extract(src, self.spec, "enthalpy").value, -270.826103, places=6
            )
            self.assertAlmostEqual(
                extract(src, self.spec, "free_energy").value, -270.860121, places=6
            )

    def test_geometry_stops_at_the_rule_line(self) -> None:
        with Source(FREQ) as src:
            value = extract(src, self.spec, "geometry")
        self.assertTrue(value.ok)
        self.assertEqual(len(value.value), 15)
        self.assertEqual(
            value.value[0],
            {
                "center": 1,
                "atomic_number": 6,
                "x": -0.000170,
                "y": -1.117900,
                "z": 0.257502,
            },
        )

    def test_excited_states_come_from_repeated_lines(self) -> None:
        with Source(TD) as src:
            value = extract(src, self.spec, "excitations")
        self.assertTrue(value.ok)
        self.assertEqual(len(value.value), 10)
        self.assertEqual(
            value.value[1],
            {
                "state": 2,
                "symmetry": "Singlet-A",
                "energy_ev": 5.7580,
                "wavelength_nm": 215.32,
                "fosc": 0.0131,
            },
        )
        self.assertEqual([row["state"] for row in value.value], list(range(1, 11)))

    def test_agrees_with_orca_on_the_same_molecule(self) -> None:
        # Same geometry through two programs. The first excitation should
        # land within a few hundredths of an eV, which is a cheap check that
        # neither spec is reading the wrong column.
        gaussian = tolk.get(TD, "excitations").value[0]["energy_ev"]
        orca = tolk.get(os.path.join(DATA, "orca-tddft.out"), "excitations").value[0]
        self.assertAlmostEqual(gaussian, orca["energy_ev"], places=2)


if __name__ == "__main__":
    unittest.main()
