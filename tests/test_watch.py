import os
import sys
import tempfile
import threading
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import tolk  # noqa: E402
from tolk import _check, registry  # noqa: E402
from tolk.extract import clear_parsers, parser  # noqa: E402
from tolk.source import Source  # noqa: E402
from tolk.spec import Quantity  # noqa: E402

DATA = os.path.join(os.path.dirname(__file__), "data")
OPT = os.path.join(DATA, "orca-opt.out")
TERMINATOR = "****ORCA TERMINATED NORMALLY****"


class FollowTest(unittest.TestCase):
    def setUp(self) -> None:
        registry.refresh()
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        with open(OPT, encoding="utf-8", errors="replace") as handle:
            self.full = handle.read()
        self.cut = self.full.index(TERMINATOR)
        self.path = os.path.join(self.dir.name, "live.out")

    def start_partial(self) -> None:
        with open(self.path, "w", encoding="utf-8") as handle:
            handle.write(self.full[: self.cut])

    def test_follow_stops_when_the_run_terminates(self) -> None:
        self.start_partial()

        def finish() -> None:
            time.sleep(0.2)
            with open(self.path, "a", encoding="utf-8") as handle:
                handle.write(self.full[self.cut :])

        thread = threading.Thread(target=finish)
        thread.start()
        self.addCleanup(thread.join)

        updates = list(tolk.follow(self.path, "energy", poll=0.05))
        self.assertGreaterEqual(len(updates), 2)
        self.assertEqual(updates[0].state, _check.RUNNING)
        self.assertTrue(updates[-1].finished)
        self.assertEqual(updates[-1].state, _check.OK)
        self.assertAlmostEqual(updates[-1].value.value, -270.965189516826, places=12)

    def test_an_already_finished_file_yields_once(self) -> None:
        updates = list(tolk.follow(OPT, "energy", poll=0.05))
        self.assertEqual(len(updates), 1)
        self.assertTrue(updates[0].finished)

    def test_size_is_reported_and_grows(self) -> None:
        self.start_partial()

        def finish() -> None:
            time.sleep(0.2)
            with open(self.path, "a", encoding="utf-8") as handle:
                handle.write(self.full[self.cut :])

        thread = threading.Thread(target=finish)
        thread.start()
        self.addCleanup(thread.join)

        sizes = [update.size for update in tolk.follow(self.path, "energy", poll=0.05)]
        self.assertEqual(sizes, sorted(sizes))
        self.assertLess(sizes[0], sizes[-1])


class ParserHookTest(unittest.TestCase):
    def setUp(self) -> None:
        registry.refresh()
        self.addCleanup(clear_parsers)

    def test_a_hook_takes_over_a_quantity(self) -> None:
        @parser("orca", "energy")
        def doubled(src: Source, quantity: Quantity) -> float:
            offset = src.rfind(quantity.anchor or b"")
            return float(src.line(offset).split()[-1]) * 2

        value = tolk.get(OPT, "energy")
        self.assertAlmostEqual(value.value, -541.930379033652, places=9)
        # The unit still comes from the spec, the hook only supplies a value.
        self.assertEqual(value.unit, "hartree")

    def test_clearing_restores_the_spec(self) -> None:
        @parser("orca", "energy")
        def broken(src: Source, quantity: Quantity) -> float:
            return 0.0

        clear_parsers()
        self.assertAlmostEqual(
            tolk.get(OPT, "energy").value, -270.965189516826, places=12
        )

    def test_a_hook_that_raises_is_a_miss_not_a_crash(self) -> None:
        # A hook is user code inside a sweep, so it must not be able to take
        # the sweep down.
        @parser("orca", "energy")
        def boom(src: Source, quantity: Quantity) -> float:
            raise RuntimeError("nope")

        value = tolk.get(OPT, "energy")
        self.assertFalse(value.ok)
        self.assertIn("parser raised", str(value.reason))

    def test_a_hook_returning_none_is_a_miss(self) -> None:
        @parser("orca", "energy")
        def nothing(src: Source, quantity: Quantity) -> None:
            return None

        self.assertFalse(tolk.get(OPT, "energy").ok)


if __name__ == "__main__":
    unittest.main()
