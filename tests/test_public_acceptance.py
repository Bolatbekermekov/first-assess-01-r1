"""Frozen public contract probes. This is not a reference implementation."""
import copy
import csv
import html
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from assess_workbench.api import WorkbenchError, analyze_rows, load_rows, render_html
ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "fixtures"
def read(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))

class PublicAcceptance(unittest.TestCase):
    def setUp(self):
        self.scope = read("scope.json")
        self.rows = read("leads.json")

    def error(self, code, fn, *args, **kwargs):
        with self.assertRaises(WorkbenchError) as caught:
            fn(*args, **kwargs)
        self.assertEqual(caught.exception.code, code)
        self.assertEqual(str(caught.exception), code)

    def test_literal_golden_and_input_immutability(self):
        original = copy.deepcopy(self.rows)
        scope = copy.deepcopy(self.scope)
        report = analyze_rows(self.rows, scope=self.scope)
        self.assertEqual(report, read("expected_report.json"))
        self.assertEqual(self.rows, original)
        self.assertEqual(self.scope, scope)
        report["scope"]["client_id"] = "changed"
        report["rows"][0]["normalized"]["company_name"] = "changed"
        self.assertEqual(self.scope, scope)
        self.assertEqual(self.rows, original)
        self.assertEqual(analyze_rows(self.rows, scope=self.scope), read("expected_report.json"))

    def test_empty_and_invalid_literal_reports(self):
        for inp, expected in [("empty.json", "empty_expected.json"), ("invalid_rows.json", "invalid_expected.json")]:
            self.assertEqual(analyze_rows(read(inp), scope=self.scope), read(expected))

    def test_json_csv_equivalence_and_bom(self):
        for fmt, path in [("json", "leads.json"), ("csv", "leads.csv")]:
            raw = (FIX / path).read_bytes()
            for data in [raw, b"\xef\xbb\xbf" + raw]:
                self.assertEqual(load_rows(data, format=fmt), self.rows)
                self.assertEqual(analyze_rows(load_rows(data, format=fmt), scope=self.scope), read("expected_report.json"))

    def test_parser_errors_and_precedence(self):
        self.error("INVALID_DATA", load_rows, "[]", format="bad")
        self.error("INVALID_FORMAT", load_rows, b"[]", format="bad")
        self.error("INVALID_ENCODING", load_rows, b"\xff", format="json")
        for raw in [b"", b"{}", b"[NaN]", b"[Infinity]", b"[{\"x\":1,\"x\":2}]", b"[] junk"]:
            self.error("INVALID_DOCUMENT", load_rows, raw, format="json")
        self.error("INPUT_TOO_LARGE", load_rows, b" " * 10485761, format="json")
        for raw in [b"", b"company_name,company_name\nx,y\n", (FIX / "leads.csv").read_bytes() + b"too,few\n"]:
            self.error("INVALID_DOCUMENT", load_rows, raw, format="csv")

    def test_scope_and_row_limits(self):
        self.error("INVALID_SCOPE", analyze_rows, None, scope={})
        self.error("INVALID_ROWS", analyze_rows, None, scope=self.scope)
        self.error("TOO_MANY_ROWS", analyze_rows, [None] * 10001, scope=self.scope)
        self.assertEqual(analyze_rows([None] * 10000, scope=self.scope)["summary"]["rejected"], 10000)

    def test_late_conflict_updates_entire_group(self):
        a = self.rows[0]
        b = copy.deepcopy(a)
        c = dict(a, company_name="Different")
        result = analyze_rows([a, b, c], scope=self.scope)
        self.assertEqual([r["status"] for r in result["rows"]], ["CONFLICT"] * 3)
        self.assertTrue(all(r["duplicate_of_row"] is None for r in result["rows"]))
        self.assertEqual(result["summary"], {"total":3,"unique":0,"duplicate":0,"conflict":3,"rejected":0})

    def test_rejected_row_does_not_poison_group_and_no_fuzzy(self):
        a = self.rows[0]
        invalid = dict(a, company_name="")
        tagged = dict(a, contact_email="buyer+tag@example.test")
        result = analyze_rows([a, invalid, tagged], scope=self.scope)
        self.assertEqual([r["status"] for r in result["rows"]], ["UNIQUE", "REJECTED", "UNIQUE"])
        changed_scope = dict(self.scope, client_id="other-client")
        other = analyze_rows([a], scope=changed_scope)
        self.assertEqual(other["scope"], changed_scope)
        self.assertEqual(other["rows"][0]["status"], "UNIQUE")

    def test_url_and_control_character_boundaries(self):
        for url in ["http://example.test", "https://user@example.test", "https://example.test:443/", "https://example.test/#", "https://localhost", "https://example.test/has space"]:
            report = analyze_rows([dict(self.rows[0], website_url=url)], scope=self.scope)
            self.assertEqual(report["rows"][0]["codes"], ["INVALID_WEBSITE_URL"])
        report = analyze_rows([dict(self.rows[0], company_name="One\nTwo")], scope=self.scope)
        self.assertEqual(report["rows"][0]["codes"], ["INVALID_COMPANY_NAME"])

    def test_surrogate_text_rejected(self):
        result = analyze_rows([dict(self.rows[0], company_name=chr(0xD800))], scope=self.scope)
        self.assertEqual(result["rows"][0]["codes"], ["INVALID_COMPANY_NAME"])
        self.assertIsNone(result["rows"][0]["normalized"])

    def test_html_escapes_visible_data(self):
        report = read("expected_report.json")
        doc = render_html(report)
        self.assertEqual(doc, render_html(report))
        self.assertIn("<!doctype html", doc.lower())
        self.assertNotIn("<script", doc.lower())
        self.assertNotIn("<iframe", doc.lower())
        self.assertNotIn("<form", doc.lower())
        malicious = self.rows[5]["company_name"]
        self.assertIn(html.escape(malicious, quote=True), doc)
        self.assertNotIn(malicious, doc)
        for row in report["rows"]:
            self.assertIn(row["status"], doc)
            for code in row["codes"]:
                self.assertIn(code, doc)
        self.assertIn("synthetic-client", doc)

    def cli(self, inp, out, fmt="json"):
        return subprocess.run([sys.executable, "-B", "-m", "assess_workbench", "--input", str(inp), "--format", fmt,
            "--client-id", "synthetic-client", "--campaign-id", "synthetic-campaign", "--out-dir", str(out)],
            cwd=ROOT, text=True, capture_output=True, timeout=30)

    def test_cli_json_csv_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            for fmt in ["json", "csv"]:
                out = Path(tmp) / fmt
                p = self.cli(FIX / ("leads." + fmt), out, fmt)
                self.assertEqual((p.returncode,p.stdout,p.stderr), (0,"REPORT_CREATED\n",""))
                self.assertEqual(sorted(x.name for x in out.iterdir()), ["report.html", "report.json"])
                raw = (out / "report.json").read_bytes()
                wanted = (json.dumps(read("expected_report.json"), ensure_ascii=False, sort_keys=True, indent=2)+"\n").encode()
                self.assertEqual(raw, wanted)
                before = {x.name:x.read_bytes() for x in out.iterdir()}
                second = self.cli(FIX / ("leads." + fmt), out, fmt)
                self.assertEqual((second.returncode,second.stdout,second.stderr), (2,"","ERROR OUTPUT_EXISTS\n"))
                self.assertEqual({x.name:x.read_bytes() for x in out.iterdir()}, before)

    def test_cli_bad_input_creates_no_output_or_input_leak(self):
        with tempfile.TemporaryDirectory() as tmp:
            inp=Path(tmp)/"bad.json"; out=Path(tmp)/"out"
            inp.write_text("SECRET_SENTINEL_RAW_PAYLOAD", encoding="utf-8")
            result=self.cli(inp,out)
            self.assertEqual((result.returncode,result.stdout,result.stderr), (2,"","ERROR INVALID_DOCUMENT\n"))
            self.assertFalse(out.exists())
            self.assertNotIn("SECRET_SENTINEL",result.stdout+result.stderr)

if __name__ == "__main__":
    unittest.main()
