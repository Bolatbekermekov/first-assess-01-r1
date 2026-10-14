"""Candidate tests: the CLI result does not depend on interpreter settings or the process environment (CONTRACT.md).

R1 broke this for JSON integers longer than sys.get_int_max_str_digits() (CP1 A6). Every run below gets the same input
and must produce the same exit status, output and byte-identical reports.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "fixtures"
EXPECTED = json.loads((FIX / "expected_report.json").read_text(encoding="utf-8"))
LONG_INTEGER_ROW = (
    '{"company_name": -1' + "0" * 5000 + ', "contact_email": "env@example.test", "website_url": "", '
    '"country_code": "", "language": "", "source_ref": "env:long-integer"}'
)
# The six fixture rows (every status, text that needs escaping), then a bare 4301-digit integer and a row whose
# company_name is a 5001-digit integer.
DOCUMENT = (
    json.dumps(json.loads((FIX / "leads.json").read_text(encoding="utf-8")), ensure_ascii=False)[:-1]
    + f", {'9' * 4301}, {LONG_INTEGER_ROW}]"
).encode("utf-8")
VARIANTS = {
    "defaults": ([], {}),
    "-X int_max_str_digits=640": (["-X", "int_max_str_digits=640"], {}),
    "-X int_max_str_digits=0": (["-X", "int_max_str_digits=0"], {}),
    "PYTHONINTMAXSTRDIGITS=4300": ([], {"PYTHONINTMAXSTRDIGITS": "4300"}),
    "PYTHONHASHSEED=0": ([], {"PYTHONHASHSEED": "0"}),
    "PYTHONHASHSEED=4242": ([], {"PYTHONHASHSEED": "4242"}),
    "LC_ALL=C PYTHONUTF8=0": ([], {"LC_ALL": "C", "PYTHONUTF8": "0"}),
}


def clean_environment():
    """The caller's environment without the Python and locale settings that the variants control."""
    return {
        name: value
        for name, value in os.environ.items()
        if not name.startswith(("PYTHON", "LC_")) and name not in {"LANG", "LANGUAGE"}
    }


class EnvironmentTests(unittest.TestCase):
    def test_interpreter_settings_and_locale_do_not_change_the_result(self):
        reports = {}
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "leads.json"
            source.write_bytes(DOCUMENT)
            for index, (name, (options, overrides)) in enumerate(VARIANTS.items()):
                out = Path(temporary) / f"out{index}"
                command = [
                    *(sys.executable, *options, "-B", "-m", "assess_workbench"),
                    *("--input", str(source), "--format", "json", "--out-dir", str(out)),
                    *("--client-id", "synthetic-client", "--campaign-id", "synthetic-campaign"),
                ]
                result = subprocess.run(
                    command,
                    cwd=ROOT,
                    env={**clean_environment(), **overrides},
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "REPORT_CREATED\n", ""), name)
                reports[name] = {item.name: item.read_bytes() for item in sorted(out.iterdir())}

        report = json.loads(reports["defaults"]["report.json"])
        self.assertEqual(report["rows"][:6], EXPECTED["rows"])
        self.assertEqual(
            [(row["status"], row["codes"]) for row in report["rows"][6:]],
            [("REJECTED", ["INVALID_ROW_SCHEMA"]), ("REJECTED", ["INVALID_COMPANY_NAME"])],
        )
        for name, files in reports.items():
            self.assertEqual(files, reports["defaults"], name)


if __name__ == "__main__":
    unittest.main()
