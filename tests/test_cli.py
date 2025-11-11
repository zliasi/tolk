import contextlib
import io
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from tolk import registry  # noqa: E402
from tolk.cli import main  # noqa: E402

DATA = os.path.join(os.path.dirname(__file__), "data")
OPT = os.path.join(DATA, "orca-opt.out")
TDDFT = os.path.join(DATA, "orca-tddft.out")
FREQ = os.path.join(DATA, "gaussian-freq.out")
TD = os.path.join(DATA, "gaussian-td.out")
XYZ = os.path.join(DATA, "nbd.xyz")


def run(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(list(argv))
    return code, out.getvalue(), err.getvalue()


class CliTest(unittest.TestCase):
    def setUp(self) -> None:
        registry.refresh()

    def test_no_command_prints_help(self) -> None:
        code, out, _ = run()
        self.assertEqual(code, 2)
        self.assertIn("usage", out)

    def test_get_writes_csv_by_default(self) -> None:
        code, out, _ = run("get", "energy", OPT)
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines()[0], "path,energy")
        self.assertIn("-270.965189516826", out)

    def test_get_across_files_makes_one_table(self) -> None:
        code, out, _ = run("get", "energy", OPT, FREQ)
        self.assertEqual(code, 0)
        self.assertEqual(len(out.strip().splitlines()), 3)

    def test_get_json(self) -> None:
        code, out, _ = run("get", "energy", OPT, "-t", "json")
        payload = json.loads(out)
        self.assertEqual(payload["units"]["energy"], "hartree")
        self.assertEqual(len(payload["rows"]), 1)

    def test_get_expands_a_list_quantity_to_rows(self) -> None:
        code, out, _ = run("get", "energy,excitations", TD)
        self.assertEqual(code, 0)
        # Ten states, one header, and the scalar repeated on every row.
        self.assertEqual(len(out.strip().splitlines()), 11)

    def test_get_survives_a_quantity_the_format_lacks(self) -> None:
        # ORCA has a dipole quantity, the Gaussian spec does not. A sweep
        # over both must still produce the ORCA number.
        code, out, err = run("get", "energy,dipole", OPT, FREQ)
        self.assertEqual(code, 1)
        self.assertIn("0.021864299", out)
        self.assertIn("has no quantity 'dipole'", err)

    def test_get_writes_to_a_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "out.csv")
            code, out, _ = run("get", "energy", OPT, "-o", target)
            self.assertEqual(code, 0)
            self.assertEqual(out, "")
            with open(target, encoding="utf-8") as handle:
                self.assertIn("energy", handle.read())

    def test_an_undetectable_file_does_not_stop_the_others(self) -> None:
        # A sweep reports the file it could not read and keeps going, rather
        # than aborting on the first stray thing in a directory.
        licence = os.path.join(os.path.dirname(__file__), "..", "LICENSE")
        code, out, err = run("get", "energy", licence, OPT)
        self.assertEqual(code, 1)
        self.assertIn("could not detect", err)
        self.assertIn("-270.965189516826", out)

    def test_check_reports_each_file(self) -> None:
        code, out, _ = run("check", OPT, FREQ)
        self.assertEqual(code, 0)
        self.assertEqual(len(out.strip().splitlines()), 2)
        self.assertTrue(all(line.startswith("ok") for line in out.splitlines()))

    def test_check_nonzero_when_something_is_not_ok(self) -> None:
        code, out, _ = run("check", OPT, XYZ)
        self.assertEqual(code, 1)
        self.assertIn("unknown", out)

    def test_check_failed_only(self) -> None:
        code, out, _ = run("check", OPT, XYZ, "--failed")
        self.assertEqual(code, 1)
        self.assertEqual(len(out.strip().splitlines()), 1)

    def test_check_json(self) -> None:
        code, out, _ = run("check", OPT, "-t", "json")
        payload = json.loads(out)
        self.assertEqual(payload["rows"][0]["state"], "ok")
        self.assertEqual(payload["rows"][0]["format"], "orca")

    def test_scan_counts(self) -> None:
        code, out, _ = run("scan", TDDFT, "0-1A", "--count")
        self.assertEqual(code, 0)
        self.assertEqual(int(out.strip()), 11)

    def test_scan_last_with_text(self) -> None:
        code, out, _ = run("scan", OPT, "FINAL SINGLE POINT", "--last", "--text")
        self.assertEqual(code, 0)
        offset, line_no, text = out.strip().split("\t")
        self.assertEqual(int(offset), 3934)
        self.assertEqual(int(line_no), 63)
        self.assertIn("-270.965189516826", text)

    def test_scan_missing_pattern_is_nonzero(self) -> None:
        code, out, _ = run("scan", OPT, "NOT PRESENT ANYWHERE")
        self.assertEqual(code, 1)
        self.assertEqual(out, "")

    def test_cat_line_range(self) -> None:
        code, out, _ = run("cat", XYZ, "--lines", "1:2")
        self.assertEqual(code, 0)
        self.assertEqual(len(out.splitlines()), 2)
        self.assertEqual(out.splitlines()[0].strip(), "15")

    def test_cat_tail(self) -> None:
        code, out, _ = run("cat", OPT, "--tail", "200")
        self.assertEqual(code, 0)
        self.assertIn("ORCA TERMINATED NORMALLY", out)

    def test_sniff(self) -> None:
        code, out, _ = run("sniff", OPT, FREQ, XYZ)
        self.assertEqual(code, 0)
        self.assertEqual(
            [line.split("\t")[0] for line in out.strip().splitlines()],
            ["orca", "gaussian", "xyz"],
        )

    def test_sniff_unknown_is_nonzero(self) -> None:
        licence = os.path.join(os.path.dirname(__file__), "..", "LICENSE")
        code, out, _ = run("sniff", licence)
        self.assertEqual(code, 1)
        self.assertIn("unknown", out)

    def test_spec_list(self) -> None:
        code, out, _ = run("spec", "list")
        self.assertEqual(code, 0)
        self.assertEqual(len(out.strip().splitlines()), 3)

    def test_spec_show(self) -> None:
        code, out, _ = run("spec", "show", "orca")
        self.assertEqual(code, 0)
        self.assertIn("[hartree]", out)

    def test_spec_explain(self) -> None:
        code, out, _ = run("spec", "explain", OPT, "geometry")
        self.assertEqual(code, 0)
        self.assertIn("block    15 lines", out)


if __name__ == "__main__":
    unittest.main()
