import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from tolk.record import Table  # noqa: E402
from tolk.value import Value  # noqa: E402


class TableTest(unittest.TestCase):
    def test_scalars_become_one_row(self) -> None:
        table = Table.from_values(
            {
                "energy": Value("energy", -1.5, "hartree"),
                "cycles": Value("cycles", 7),
            },
            path="job.out",
        )
        self.assertEqual(len(table), 1)
        self.assertEqual(table.columns, ["path", "energy", "cycles"])
        self.assertEqual(table.units, {"energy": "hartree"})

    def test_a_list_quantity_expands_and_repeats_the_scalars(self) -> None:
        table = Table.from_values(
            {
                "energy": Value("energy", -1.5, "hartree"),
                "states": Value("states", [{"ev": 1.0}, {"ev": 2.0}, {"ev": 3.0}]),
            },
            path="job.out",
        )
        self.assertEqual(len(table), 3)
        self.assertEqual(table.columns, ["path", "energy", "ev"])
        self.assertEqual([row["energy"] for row in table.rows], [-1.5] * 3)

    def test_a_list_of_bare_values_is_named_after_the_quantity(self) -> None:
        table = Table.from_values({"ev": Value("ev", [1.0, 2.0])})
        self.assertEqual(table.rows, [{"ev": 1.0}, {"ev": 2.0}])

    def test_two_list_quantities_stay_separate(self) -> None:
        # Zipping them would invent a relationship that is not in the file.
        table = Table.from_values(
            {
                "a": Value("a", [{"x": 1}, {"x": 2}]),
                "b": Value("b", [{"y": 1}]),
            }
        )
        self.assertEqual(sorted(table.meta["tables"]), ["a", "b"])
        self.assertEqual(len(table.meta["tables"]["b"]), 1)

    def test_misses_are_recorded_not_dropped(self) -> None:
        table = Table.from_values(
            {
                "energy": Value("energy", -1.5),
                "gone": Value.missing("gone", "anchor not found"),
            }
        )
        self.assertEqual(list(table.meta["missing"]), ["gone"])
        self.assertNotIn("gone", table.columns)

    def test_ragged_rows_still_line_up_under_one_header(self) -> None:
        table = Table(rows=[{"a": 1}, {"b": 2}])
        self.assertEqual(table.columns, ["a", "b"])
        self.assertEqual(table.to_csv(), "a,b\n1,\n,2\n")

    def test_csv_quotes_what_needs_it(self) -> None:
        table = Table(rows=[{"note": 'has, comma and "quotes"'}])
        self.assertEqual(table.to_csv(), 'note\n"has, comma and ""quotes"""\n')

    def test_tsv_uses_tabs(self) -> None:
        table = Table(rows=[{"a": 1, "b": 2}])
        self.assertEqual(table.to_tsv(), "a\tb\n1\t2\n")

    def test_json_carries_units_and_meta(self) -> None:
        table = Table.from_values(
            {
                "energy": Value("energy", -1.5, "hartree"),
                "gone": Value.missing("gone", "anchor not found"),
            }
        )
        payload = json.loads(table.to_json())
        self.assertEqual(payload["units"], {"energy": "hartree"})
        self.assertIn("gone", payload["meta"]["missing"])

    def test_empty_table_renders_as_nothing(self) -> None:
        self.assertEqual(Table().to_csv(), "")
        self.assertFalse(Table())


if __name__ == "__main__":
    unittest.main()
