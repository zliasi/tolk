import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from tolk import backends, convert, registry, template  # noqa: E402
from tolk.record import Table  # noqa: E402

DATA = os.path.join(os.path.dirname(__file__), "data")
OPT = os.path.join(DATA, "orca-opt.out")
TD = os.path.join(DATA, "gaussian-td.out")
XYZ = os.path.join(DATA, "nbd.xyz")

BACKEND = """
name = "fake"
detect = "python3"
priority = 99
pairs = [["orca", "fake"], ["*", "alsofake"]]
command = "python3 -c pass {input} {output} {ifmt} {ofmt}"
"""


class ConvertTest(unittest.TestCase):
    def setUp(self) -> None:
        registry.refresh()
        backends.refresh()
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)

    def out(self, name: str) -> str:
        return os.path.join(self.dir.name, name)

    def test_geometry_to_xyz_round_trips_through_tolk(self) -> None:
        target = self.out("geom.xyz")
        convert.convert(OPT, target, quantities=["geometry"])
        table = convert.read(target, format="xyz", quantities=["natoms", "geometry"])
        self.assertEqual(len(table), 15)
        self.assertEqual(table.rows[0]["symbol"], "C")
        self.assertAlmostEqual(table.rows[0]["x"], 0.035760, places=6)

    def test_declared_atom_count_matches_the_rows(self) -> None:
        target = self.out("geom.xyz")
        convert.convert(OPT, target, quantities=["geometry"])
        with open(target, encoding="utf-8") as handle:
            first = handle.readline().strip()
        self.assertEqual(int(first), 15)

    def test_table_to_csv_and_json(self) -> None:
        convert.convert(TD, self.out("x.csv"), quantities=["energy", "excitations"])
        with open(self.out("x.csv"), encoding="utf-8") as handle:
            self.assertEqual(len(handle.read().strip().splitlines()), 11)
        convert.convert(TD, self.out("x.json"), quantities=["excitations"])
        with open(self.out("x.json"), encoding="utf-8") as handle:
            self.assertEqual(len(json.load(handle)["rows"]), 10)

    def test_xyz_refuses_a_table_without_coordinates(self) -> None:
        # Guessing which numeric columns are coordinates is exactly the
        # inference that makes a converter untrustworthy.
        with self.assertRaises(convert.ConvertError) as caught:
            convert.write_xyz(Table(rows=[{"a": 1.0, "b": 2.0}]))
        self.assertIn("symbol", str(caught.exception))

    def test_unknown_target_format_names_what_is_possible(self) -> None:
        with self.assertRaises(convert.ConvertError) as caught:
            convert.plan(OPT, self.out("x.zzz"))
        self.assertIn("tolk writes", str(caught.exception))

    def test_a_missing_backend_says_which_one_would_have_worked(self) -> None:
        with self.assertRaises(convert.ConvertError) as caught:
            convert.plan(OPT, self.out("x.pdb"))
        self.assertIn("obabel", str(caught.exception))

    def test_plan_does_not_write_anything(self) -> None:
        target = self.out("nothing.xyz")
        convert.plan(OPT, target)
        self.assertFalse(os.path.exists(target))

    def test_read_without_a_quantity_list_takes_everything(self) -> None:
        table = convert.read(OPT)
        self.assertIn("excitations", table.meta["missing"])
        self.assertTrue(table.rows)


class BackendTest(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        with open(os.path.join(self.dir.name, "fake.toml"), "w") as handle:
            handle.write(BACKEND)
        self.previous = os.environ.get(backends.BACKEND_PATH_ENV)
        os.environ[backends.BACKEND_PATH_ENV] = self.dir.name
        backends.refresh()

        def restore() -> None:
            if self.previous is None:
                os.environ.pop(backends.BACKEND_PATH_ENV, None)
            else:
                os.environ[backends.BACKEND_PATH_ENV] = self.previous
            backends.refresh()

        self.addCleanup(restore)

    def test_a_user_backend_is_picked_up(self) -> None:
        self.assertIn("fake", backends.names())

    def test_pair_matching_with_wildcards(self) -> None:
        fake = backends.load_all()["fake"]
        self.assertTrue(fake.handles("orca", "fake"))
        self.assertTrue(fake.handles("anything", "alsofake"))
        self.assertFalse(fake.handles("orca", "nope"))

    def test_higher_priority_wins(self) -> None:
        chosen = backends.find("orca", "alsofake", installed_only=False)
        self.assertIsNotNone(chosen)
        self.assertEqual(chosen.name, "fake")

    def test_the_command_is_a_list_never_a_shell_string(self) -> None:
        fake = backends.load_all()["fake"]
        argv = fake.render("in file.xyz", "out.pdb", "xyz", "pdb")
        self.assertIsInstance(argv, list)
        self.assertIn("in", argv)

    def test_a_backend_without_a_command_is_rejected(self) -> None:
        bad = os.path.join(self.dir.name, "bad.toml")
        with open(bad, "w") as handle:
            handle.write('name = "bad"\n')
        with self.assertRaises(backends.BackendError):
            backends.load(bad)


class TemplateTest(unittest.TestCase):
    def test_shipped_templates_load(self) -> None:
        self.assertIn("orca-opt", template.names())

    def test_placeholders_are_reported_in_order(self) -> None:
        self.assertEqual(
            template.get("orca-opt").placeholders,
            ["method", "basis", "nprocs", "maxcore", "charge", "mult", "geometry"],
        )

    def test_render(self) -> None:
        text = template.get("orca-opt").render(
            {
                "method": "PBE0",
                "basis": "def2-SVP",
                "nprocs": 4,
                "maxcore": 2000,
                "charge": 0,
                "mult": 1,
                "geometry": "mol.xyz",
            }
        )
        self.assertIn("! PBE0 def2-SVP Opt", text)
        self.assertIn("* xyzfile 0 1 mol.xyz", text)

    def test_a_missing_value_is_an_error_not_a_blank(self) -> None:
        # A job that runs with an empty basis set wastes more time than one
        # that never starts.
        with self.assertRaises(template.TemplateError) as caught:
            template.get("orca-opt").render({"method": "PBE0"})
        self.assertIn("no value for", str(caught.exception))

    def test_unknown_template_lists_what_exists(self) -> None:
        with self.assertRaises(template.TemplateError) as caught:
            template.get("nosuchtemplate")
        self.assertIn("orca-opt", str(caught.exception))

    def test_settings_parsing(self) -> None:
        self.assertEqual(
            template.parse_settings(["a=1", "b=x=y"]), {"a": "1", "b": "x=y"}
        )
        with self.assertRaises(template.TemplateError):
            template.parse_settings(["nope"])


if __name__ == "__main__":
    unittest.main()
