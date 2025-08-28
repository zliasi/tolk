import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import tolk  # noqa: E402
from tolk import registry  # noqa: E402
from tolk.spec import SpecError  # noqa: E402

OVERRIDE = """
format = "orca"

[signature]
contains = ["* O   R   C   A *"]
priority = 50

[quantity.energy]
anchor = "FINAL SINGLE POINT ENERGY"
occurrence = "first"
description = "site override, first energy instead of last"
parse = { field = -1, type = "float", unit = "hartree" }
"""

OPT = os.path.join(os.path.dirname(__file__), "data", "orca-opt.out")


class RegistryTest(unittest.TestCase):
    def setUp(self) -> None:
        registry.refresh()
        self.addCleanup(registry.refresh)

    def test_shipped_specs_are_found(self) -> None:
        self.assertEqual(registry.formats(), ["gaussian", "orca", "xyz"])

    def test_unknown_format_lists_what_exists(self) -> None:
        with self.assertRaises(SpecError) as caught:
            registry.get("nosuchformat")
        self.assertIn("gaussian, orca, xyz", str(caught.exception))

    def test_spec_records_where_it_came_from(self) -> None:
        self.assertTrue(registry.get("orca").source.endswith("orca.toml"))

    def test_describe_lists_quantities(self) -> None:
        text = tolk.describe("orca")
        self.assertIn("energy", text)
        self.assertIn("[hartree]", text)


class OverrideTest(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        path = os.path.join(self.dir.name, "orca.toml")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(OVERRIDE)
        self.previous = os.environ.get(registry.SPEC_PATH_ENV)
        os.environ[registry.SPEC_PATH_ENV] = self.dir.name
        registry.refresh()

        def restore() -> None:
            if self.previous is None:
                os.environ.pop(registry.SPEC_PATH_ENV, None)
            else:
                os.environ[registry.SPEC_PATH_ENV] = self.previous
            registry.refresh()

        self.addCleanup(restore)

    def test_a_user_spec_replaces_the_shipped_one(self) -> None:
        spec = registry.get("orca")
        self.assertTrue(spec.source.startswith(self.dir.name))
        # The override reads the first energy rather than the last, which is
        # a visible behaviour change, not just a different file on disk.
        self.assertEqual(spec.quantity("energy").occurrence, "first")

    def test_the_override_is_what_actually_runs(self) -> None:
        # The fixture holds one energy line, so first and last agree on the
        # number. What proves the override is live is the spec it names.
        value = tolk.get(OPT, "energy")
        self.assertAlmostEqual(value.value, -270.965189516826, places=12)
        self.assertIn("site override", tolk.describe("orca"))
        self.assertIn("occurrence first", tolk.explain(OPT, "energy"))

    def test_quantities_absent_from_the_override_are_gone(self) -> None:
        # Overriding replaces a spec rather than merging into it, so a
        # partial override loses whatever it left out. Spec.source is how
        # that gets diagnosed.
        with self.assertRaises(SpecError):
            registry.get("orca").quantity("geometry")


if __name__ == "__main__":
    unittest.main()
