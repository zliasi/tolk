import glob
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import tolk  # noqa: E402
from tolk import cache, registry  # noqa: E402

DATA = os.path.join(os.path.dirname(__file__), "data")
OUTS = sorted(glob.glob(os.path.join(DATA, "*.out")))
OPT = os.path.join(DATA, "orca-opt.out")


class SweepTest(unittest.TestCase):
    def setUp(self) -> None:
        registry.refresh()

    def test_one_table_across_formats(self) -> None:
        sweep = tolk.get_many(OUTS, ["energy"])
        self.assertEqual(len(sweep), len(OUTS))
        self.assertEqual(sweep.table.units["energy"], "hartree")
        self.assertEqual(sorted(set(sweep.formats.values())), ["gaussian", "orca"])

    def test_order_is_preserved(self) -> None:
        sweep = tolk.get_many(OUTS, ["energy"])
        self.assertEqual([row["path"] for row in sweep.table.rows], OUTS)

    def test_single_worker_matches_many(self) -> None:
        one = tolk.get_many(OUTS, ["energy"], workers=1)
        many = tolk.get_many(OUTS, ["energy"], workers=4)
        self.assertEqual(one.table.rows, many.table.rows)

    def test_a_missing_quantity_is_recorded_not_raised(self) -> None:
        sweep = tolk.get_many(OUTS, ["energy", "dipole"])
        self.assertTrue(sweep.errors)
        self.assertEqual(len(sweep), len(OUTS))

    def test_an_unreadable_file_does_not_stop_the_sweep(self) -> None:
        paths = OUTS + [os.path.join(DATA, "does-not-exist.out")]
        sweep = tolk.get_many(paths, ["energy"])
        self.assertEqual(len(sweep), len(OUTS))
        self.assertEqual(len(sweep.errors), 1)

    def test_check_many_keeps_order_and_survives_bad_paths(self) -> None:
        paths = OUTS + [os.path.join(DATA, "nope.out")]
        results = tolk.check_many(paths)
        self.assertEqual([status.path for status in results], paths)
        self.assertEqual(results[-1].state, "unknown")

    def test_map_files_returns_exceptions_rather_than_raising(self) -> None:
        def boom(path: str) -> str:
            if path.endswith("orca-opt.out"):
                raise RuntimeError("nope")
            return path

        results = tolk.map_files(OUTS, boom)
        self.assertEqual(len(results), len(OUTS))
        self.assertEqual(sum(isinstance(r, Exception) for r in results), 1)


class ColumnsTest(unittest.TestCase):
    def test_column_view(self) -> None:
        sweep = tolk.get_many(OUTS, ["energy"])
        columns = sweep.table.to_columns()
        self.assertEqual(sorted(columns), ["energy", "path"])
        self.assertEqual(len(columns["energy"]), len(OUTS))

    def test_arrow_is_optional(self) -> None:
        table = tolk.get_many(OUTS, ["energy"]).table
        try:
            import pyarrow  # noqa: F401
        except ImportError:
            with self.assertRaises(ImportError):
                table.to_arrow()
        else:  # pragma: no cover - only when pyarrow is installed
            self.assertEqual(table.to_arrow().num_rows, len(OUTS))


class CacheTest(unittest.TestCase):
    def setUp(self) -> None:
        registry.refresh()
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.path = os.path.join(self.dir.name, "offsets.json")
        self.addCleanup(cache.disable)

    def test_second_read_is_a_hit(self) -> None:
        store = cache.enable(self.path)
        tolk.get(OPT, "energy")
        self.assertEqual(store.hits, 0)
        tolk.get(OPT, "energy")
        self.assertEqual(store.hits, 1)

    def test_the_cache_survives_the_process(self) -> None:
        store = cache.enable(self.path)
        tolk.get(OPT, "energy")
        cache.disable()
        reopened = cache.enable(self.path)
        value = tolk.get(OPT, "energy")
        self.assertEqual(reopened.hits, 1)
        self.assertAlmostEqual(value.value, -270.965189516826, places=12)
        del store

    def test_a_changed_file_is_not_trusted(self) -> None:
        # Size and mtime can collide, so a hit is only used after the anchor
        # is confirmed to still be at the remembered offset.
        target = os.path.join(self.dir.name, "job.out")
        with open(OPT, "rb") as handle:
            original = handle.read()
        with open(target, "wb") as handle:
            handle.write(original)
        store = cache.enable(self.path)
        tolk.get(target, "energy")

        shifted = b"# padding\n" * 20 + original
        with open(target, "wb") as handle:
            handle.write(shifted)
        os.utime(target, (0, 0))
        value = tolk.get(target, "energy")
        self.assertAlmostEqual(value.value, -270.965189516826, places=12)
        del store

    def test_results_match_with_and_without_the_cache(self) -> None:
        plain = tolk.get(OPT, ["energy", "geometry"])
        cache.enable(self.path)
        cached = tolk.get(OPT, ["energy", "geometry"])
        again = tolk.get(OPT, ["energy", "geometry"])
        self.assertEqual(plain["energy"].value, cached["energy"].value)
        self.assertEqual(plain["geometry"].value, again["geometry"].value)

    def test_caching_is_off_by_default(self) -> None:
        cache.disable()
        self.assertIsNone(cache.active())


if __name__ == "__main__":
    unittest.main()
