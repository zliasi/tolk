import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from tolk.extract import extract  # noqa: E402
from tolk.source import Source  # noqa: E402
from tolk.spec import SpecError, loads  # noqa: E402

SPEC = """
format = "demo"

[signature]
contains = ["DEMO PROGRAM"]
extensions = [".demo"]
priority = 40

[terminator]
ok = ["FINISHED CLEANLY"]
error = ["ABORTED"]

[quantity.energy]
anchor = "TOTAL ENERGY"
occurrence = "last"
parse = { field = -1, type = "float", unit = "hartree" }

[quantity.cycles]
anchor = "CYCLE COUNT"
parse = { field = -1, type = "int" }

[quantity.table]
anchor = "RESULT TABLE"
block = { skip = 2, until = "blank" }
parse = { columns = { first = 1, second = 2 } }
"""

REPORT = b"""DEMO PROGRAM v1
TOTAL ENERGY  -1.5
CYCLE COUNT  7
TOTAL ENERGY  -2.5

RESULT TABLE
----
  a 1.0 2.0
  b 3.0 4.0
  ---- separator ----
  c 5.0 6.0

FINISHED CLEANLY
"""


class LoaderTest(unittest.TestCase):
    def test_round_trip(self) -> None:
        spec = loads(SPEC, "demo.toml")
        self.assertEqual(spec.format, "demo")
        self.assertEqual(spec.names(), ["cycles", "energy", "table"])
        self.assertEqual(spec.contains, (b"DEMO PROGRAM",))
        self.assertEqual(spec.extensions, (".demo",))
        self.assertEqual(spec.priority, 40)
        self.assertEqual(spec.terminators.ok, (b"FINISHED CLEANLY",))
        self.assertEqual(spec.terminators.error, (b"ABORTED",))
        self.assertEqual(spec.source, "demo.toml")

    def test_occurrence_maps_to_an_index(self) -> None:
        spec = loads(SPEC, "demo.toml")
        self.assertEqual(spec.quantity("energy").nth, -1)
        # Anything without an explicit occurrence takes the last one, since a
        # converged value is normally the one printed last.
        self.assertEqual(spec.quantity("cycles").nth, -1)

    def test_unknown_quantity_lists_what_exists(self) -> None:
        spec = loads(SPEC, "demo.toml")
        with self.assertRaises(SpecError) as caught:
            spec.quantity("nope")
        self.assertIn("cycles, energy, table", str(caught.exception))

    def test_unknown_keys_are_rejected(self) -> None:
        bad = (
            'format = "x"\n[quantity.a]\nanchor = "A"\nparse = { field = 0 }\ntypo = 1'
        )
        with self.assertRaises(SpecError) as caught:
            loads(bad, "bad.toml")
        self.assertIn("typo", str(caught.exception))

    def test_missing_format_is_rejected(self) -> None:
        with self.assertRaises(SpecError):
            loads('[quantity.a]\nanchor = "A"\nparse = { field = 0 }', "bad.toml")

    def test_empty_anchor_is_rejected(self) -> None:
        with self.assertRaises(SpecError):
            loads('format = "x"\n[quantity.a]\nanchor = ""', "bad.toml")

    def test_unknown_scalar_type_is_rejected(self) -> None:
        bad = 'format = "x"\n[quantity.a]\nanchor = "A"\nparse = { type = "bogus" }'
        with self.assertRaises(SpecError):
            loads(bad, "bad.toml")

    def test_quantity_without_a_way_to_read_is_rejected(self) -> None:
        with self.assertRaises(SpecError):
            loads('format = "x"\n[quantity.a]\nanchor = "A"', "bad.toml")

    def test_table_without_a_block_is_rejected(self) -> None:
        bad = (
            'format = "x"\n[quantity.a]\nanchor = "A"\n'
            "parse = { columns = { one = 1 } }"
        )
        with self.assertRaises(SpecError):
            loads(bad, "bad.toml")

    def test_bad_toml_names_the_source(self) -> None:
        with self.assertRaises(SpecError) as caught:
            loads("format = ", "broken.toml")
        self.assertIn("broken.toml", str(caught.exception))


class ExtractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.spec = loads(SPEC, "demo.toml")
        self.src = Source.from_bytes(REPORT, name="report.demo")

    def test_last_occurrence_wins(self) -> None:
        value = extract(self.src, self.spec, "energy")
        self.assertTrue(value.ok)
        self.assertEqual(value.value, -2.5)
        self.assertEqual(value.unit, "hartree")

    def test_integer_field(self) -> None:
        self.assertEqual(extract(self.src, self.spec, "cycles").value, 7)

    def test_provenance_is_optional(self) -> None:
        bare = extract(self.src, self.spec, "energy")
        self.assertIsNotNone(bare.where)
        self.assertIsNone(bare.where.line)  # type: ignore[union-attr]
        numbered = extract(self.src, self.spec, "energy", with_lines=True)
        self.assertEqual(numbered.where.line, 4)  # type: ignore[union-attr]

    def test_table_columns(self) -> None:
        value = extract(self.src, self.spec, "table")
        self.assertTrue(value.ok)
        self.assertEqual(
            value.value,
            [
                {"first": 1.0, "second": 2.0},
                {"first": 3.0, "second": 4.0},
                {"first": 5.0, "second": 6.0},
            ],
        )

    def test_missing_anchor_gives_a_reason(self) -> None:
        spec = loads(
            'format = "x"\n[quantity.gone]\nanchor = "NOT HERE"\n'
            "parse = { field = 0 }",
            "x.toml",
        )
        value = extract(self.src, spec, "gone")
        self.assertFalse(value.ok)
        self.assertIn("not found", str(value.reason))
        self.assertIn("report.demo", str(value.reason))

    def test_unparseable_field_gives_a_reason(self) -> None:
        spec = loads(
            'format = "x"\n[quantity.bad]\nanchor = "DEMO PROGRAM"\n'
            'parse = { field = 0, type = "float" }',
            "x.toml",
        )
        value = extract(self.src, spec, "bad")
        self.assertFalse(value.ok)
        self.assertIn("not a float", str(value.reason))


if __name__ == "__main__":
    unittest.main()
