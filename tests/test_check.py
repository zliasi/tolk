import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import tolk  # noqa: E402
from tolk import _check as check_module  # noqa: E402
from tolk import registry  # noqa: E402

DATA = os.path.join(os.path.dirname(__file__), "data")
OPT = os.path.join(DATA, "orca-opt.out")
FREQ = os.path.join(DATA, "gaussian-freq.out")


class CheckTest(unittest.TestCase):
    def setUp(self) -> None:
        registry.refresh()
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)

    def variant(self, source: str, name: str, replace: tuple[str, str]) -> str:
        with open(source, encoding="utf-8", errors="replace") as handle:
            text = handle.read()
        path = os.path.join(self.dir.name, name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text.replace(*replace))
        return path

    def test_finished_runs(self) -> None:
        self.assertTrue(tolk.check(OPT))
        self.assertEqual(tolk.check(OPT).state, check_module.OK)
        self.assertEqual(tolk.check(OPT).format, "orca")
        self.assertEqual(tolk.check(FREQ).state, check_module.OK)

    def test_error_termination(self) -> None:
        path = self.variant(
            FREQ,
            "failed.out",
            ("Normal termination of Gaussian", "Error termination request"),
        )
        status = tolk.check(path)
        self.assertEqual(status.state, check_module.ERROR)
        self.assertFalse(status)
        self.assertIn("Error termination", str(status.detail))

    def test_error_wins_over_a_success_marker(self) -> None:
        # A run can print something that looks like success and then die, so
        # the error marker is the one that decides.
        path = self.variant(
            OPT,
            "both.out",
            (
                "****ORCA TERMINATED NORMALLY****",
                "****ORCA TERMINATED NORMALLY****\nORCA finished by error termination",
            ),
        )
        self.assertEqual(tolk.check(path).state, check_module.ERROR)

    def test_no_terminator_and_recent_mtime_reads_as_running(self) -> None:
        path = self.variant(OPT, "live.out", ("****ORCA TERMINATED NORMALLY****", ""))
        self.assertEqual(tolk.check(path).state, check_module.RUNNING)

    def test_no_terminator_and_old_mtime_reads_as_unknown(self) -> None:
        path = self.variant(OPT, "stale.out", ("****ORCA TERMINATED NORMALLY****", ""))
        old = os.path.getmtime(path) - 10_000
        os.utime(path, (old, old))
        self.assertEqual(tolk.check(path).state, check_module.UNKNOWN)

    def test_undetectable_format_is_unknown_not_an_error(self) -> None:
        status = tolk.check(os.path.join(os.path.dirname(__file__), "..", "LICENSE"))
        self.assertEqual(status.state, check_module.UNKNOWN)
        self.assertIn("no spec", str(status.detail))

    def test_spec_without_terminators_is_unknown(self) -> None:
        status = tolk.check(os.path.join(DATA, "nbd.xyz"))
        self.assertEqual(status.state, check_module.UNKNOWN)
        self.assertEqual(status.format, "xyz")

    def test_only_the_tail_is_consulted(self) -> None:
        # A terminator further back than the tail window must not count, or
        # a restarted job would report the previous run's outcome.
        path = self.variant(OPT, "far.out", ("", ""))
        with open(path, "a", encoding="utf-8") as handle:
            handle.write("x" * 20_000 + "\n")
        self.assertNotEqual(tolk.check(path).state, check_module.OK)

    def test_check_many_keeps_order(self) -> None:
        results = tolk.check_many([OPT, FREQ])
        self.assertEqual([status.path for status in results], [OPT, FREQ])


if __name__ == "__main__":
    unittest.main()
