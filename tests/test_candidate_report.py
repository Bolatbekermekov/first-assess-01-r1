"""Candidate tests: analyze_rows scope and row-list checks, report schema and isolation (CONTRACT.md 1, 4)."""

import collections
import copy
import json
import traceback
import unittest
from pathlib import Path

from assess_workbench.api import WorkbenchError, analyze_rows

ROOT = Path(__file__).resolve().parents[1]
SCOPE = json.loads((ROOT / "fixtures" / "scope.json").read_text(encoding="utf-8"))
FIELDS = ("company_name", "contact_email", "website_url", "country_code", "language", "source_ref")
VALID_ROW = {
    "company_name": "Example Labs",
    "contact_email": "person@example.test",
    "website_url": "https://example.test/",
    "country_code": "DK",
    "language": "en",
    "source_ref": "candidate:baseline",
}


class StrSubclass(str):
    pass


class ListSubclass(list):
    pass


def valid_row(index, **overrides):
    """A valid row whose email is unique to ``index``."""
    return dict(VALID_ROW, contact_email=f"person{index}@example.test", **overrides)


class ErrorTestCase(unittest.TestCase):
    def assert_error(self, code, rows, scope):
        with self.assertRaises(WorkbenchError) as caught:
            analyze_rows(rows, scope=scope)
        error = caught.exception
        self.assertIsInstance(error, ValueError)
        self.assertEqual((error.code, str(error), error.args), (code, code, (code,)))
        self.assertIsNone(error.__cause__)
        self.assertIsNone(error.__context__)
        return error


class ScopeAndRowListTests(ErrorTestCase):
    def test_scope_must_be_an_exact_dict_with_exactly_three_keys(self):
        bad_scopes = [
            None,
            [],
            "scope",
            1,
            {},
            collections.OrderedDict(SCOPE),
            {key: value for key, value in SCOPE.items() if key != "campaign_id"},
            dict(SCOPE, extra="x"),
            {**{key.upper(): value for key, value in SCOPE.items()}},
        ]
        for scope in bad_scopes:
            with self.subTest(scope=repr(scope)[:80]):
                self.assert_error("INVALID_SCOPE", [], scope)

    def test_schema_version_is_compared_exactly(self):
        versions = ["assess_scope_v1", "ASSESS_SCOPE_V2", " ASSESS_SCOPE_V1", "ASSESS_SCOPE_V1 ", "", None, 1]
        for version in [*versions, StrSubclass("ASSESS_SCOPE_V1")]:
            with self.subTest(version=repr(version)):
                self.assert_error("INVALID_SCOPE", [], dict(SCOPE, schema_version=version))

    def test_scope_identifiers(self):
        valid = ["a", "Z", "0", "a" * 128, "client_1.2:3-4", "A-b_C.d:E"]
        invalid = ["", "a" * 129, "_client", ".client", ":client", "-client", "client id", "client/1", "клиент",
                   "client\n", "ａ", None, 1, True, b"client", StrSubclass("client")]
        for key in ("client_id", "campaign_id"):
            for value in valid:
                with self.subTest(key=key, value=value):
                    report = analyze_rows([], scope=dict(SCOPE, **{key: value}))
                    self.assertEqual(report["scope"][key], value)
            for value in invalid:
                with self.subTest(key=key, value=repr(value)):
                    self.assert_error("INVALID_SCOPE", [], dict(SCOPE, **{key: value}))

    def test_check_order_is_scope_then_rows_type_then_length(self):
        self.assert_error("INVALID_SCOPE", None, None)
        self.assert_error("INVALID_SCOPE", [None] * 10_001, {})
        for rows in [None, (), {}, "rows", 0, ListSubclass()]:
            with self.subTest(rows=type(rows).__name__):
                self.assert_error("INVALID_ROWS", rows, SCOPE)
        self.assert_error("TOO_MANY_ROWS", [None] * 10_001, SCOPE)

    def test_row_limit_is_inclusive(self):
        report = analyze_rows([valid_row(index) for index in range(10_000)], scope=SCOPE)
        self.assertEqual(report["summary"]["total"], 10_000)
        self.assertEqual(report["summary"]["unique"], 10_000)

    def test_error_traceback_does_not_mention_rows(self):
        secret = "SECRET SENTINEL scope"  # the spaces make it an invalid identifier
        error = self.assert_error("INVALID_SCOPE", [secret], dict(SCOPE, client_id=secret))
        self.assertNotIn(secret, "".join(traceback.format_exception(error)))


class ReportSchemaTests(unittest.TestCase):
    def setUp(self):
        rows = [valid_row(1), None, dict(VALID_ROW, company_name=""), valid_row(2, website_url="")]
        self.report = analyze_rows(rows, scope=SCOPE)

    def test_top_level_shape(self):
        self.assertIs(type(self.report), dict)
        self.assertEqual(set(self.report), {"schema_version", "scope", "summary", "rows"})
        self.assertEqual(self.report["schema_version"], "ASSESS_LEAD_REPORT_V1")
        self.assertEqual(self.report["scope"], SCOPE)
        self.assertIs(type(self.report["scope"]), dict)
        self.assertIs(type(self.report["rows"]), list)

    def test_row_shape_and_exact_builtin_types(self):
        for row in self.report["rows"]:
            with self.subTest(row=row["row_number"]):
                self.assertEqual(set(row), {"row_number", "status", "codes", "normalized", "duplicate_of_row"})
                self.assertIs(type(row["row_number"]), int)
                self.assertIs(type(row["status"]), str)
                self.assertIn(row["status"], {"UNIQUE", "DUPLICATE", "CONFLICT", "REJECTED"})
                self.assertIs(type(row["codes"]), list)
                self.assertTrue(row["codes"])
                for code in row["codes"]:
                    self.assertIs(type(code), str)
                if row["normalized"] is not None:
                    self.assertIs(type(row["normalized"]), dict)
                    self.assertEqual(list(row["normalized"]), list(FIELDS))
                    for value in row["normalized"].values():
                        self.assertIs(type(value), str)
                self.assertIn(type(row["duplicate_of_row"]), {int, type(None)})

    def test_rows_follow_input_order(self):
        self.assertEqual([row["row_number"] for row in self.report["rows"]], [1, 2, 3, 4])
        self.assertEqual([row["status"] for row in self.report["rows"]], ["UNIQUE", "REJECTED", "REJECTED", "UNIQUE"])

    def test_summary_counts_rows(self):
        summary = {"total": 4, "unique": 2, "duplicate": 0, "conflict": 0, "rejected": 2}
        self.assertEqual(self.report["summary"], summary)
        self.assertIs(type(self.report["summary"]["total"]), int)

    def test_rejected_row(self):
        expected = {"row_number": 3, "status": "REJECTED", "codes": ["INVALID_COMPANY_NAME"], "normalized": None,
                    "duplicate_of_row": None}
        self.assertEqual(self.report["rows"][2], expected)

    def test_valid_row(self):
        expected = {"row_number": 4, "status": "UNIQUE", "codes": ["VALID_RECORD"],
                    "normalized": valid_row(2, website_url=""), "duplicate_of_row": None}
        self.assertEqual(self.report["rows"][3], expected)

    def test_empty_rows(self):
        report = analyze_rows([], scope=SCOPE)
        self.assertEqual(report["rows"], [])
        self.assertEqual(report["summary"], {"total": 0, "unique": 0, "duplicate": 0, "conflict": 0, "rejected": 0})


class IsolationTests(unittest.TestCase):
    def test_inputs_are_not_mutated(self):
        rows = [
            valid_row(1),
            {"company_name": ["nested", {"x": 1}], "unexpected": {"deep": [1, 2]}},
            [1, 2],
            valid_row(1, company_name="  Spaced   Name "),
        ]
        scope = dict(SCOPE)
        rows_before, scope_before = copy.deepcopy(rows), copy.deepcopy(scope)
        analyze_rows(rows, scope=scope)
        self.assertEqual(rows, rows_before)
        self.assertEqual(scope, scope_before)

    def test_output_shares_no_mutable_objects_with_input_or_between_rows(self):
        rows = [valid_row(1), valid_row(1), valid_row(2), None]
        scope = dict(SCOPE)
        report = analyze_rows(rows, scope=scope)
        mutable = [report["scope"], report["summary"], report["rows"]]
        for row in report["rows"]:
            mutable += [row, row["codes"]]
            if row["normalized"] is not None:
                mutable.append(row["normalized"])
        identities = [id(item) for item in mutable]
        self.assertEqual(len(identities), len(set(identities)))
        self.assertFalse({id(scope), id(rows), *(id(row) for row in rows if row is not None)} & set(identities))

    def test_mutating_a_report_affects_neither_input_nor_later_reports(self):
        rows = [valid_row(1), None]
        report = analyze_rows(rows, scope=SCOPE)
        report["scope"]["client_id"] = "changed"
        report["rows"][0]["normalized"]["company_name"] = "changed"
        report["rows"][0]["codes"].append("CHANGED")
        report["rows"][1]["codes"].clear()
        again = analyze_rows(rows, scope=SCOPE)
        self.assertEqual(again["rows"][0]["codes"], ["VALID_RECORD"])
        self.assertEqual(again["rows"][1]["codes"], ["INVALID_ROW_SCHEMA"])
        self.assertEqual(again["rows"][0]["normalized"]["company_name"], "Example Labs")
        self.assertEqual(again["scope"], SCOPE)

    def test_result_is_deterministic(self):
        rows = [valid_row(1), valid_row(1, source_ref="other"), None, valid_row(2, company_name="x" * 201)]
        first = json.dumps(analyze_rows(rows, scope=SCOPE), sort_keys=True)
        for _ in range(3):
            self.assertEqual(json.dumps(analyze_rows(copy.deepcopy(rows), scope=SCOPE), sort_keys=True), first)

    def test_report_never_contains_raw_input_of_rejected_rows(self):
        secret = "SECRET-SENTINEL-1234"
        rows = [dict(VALID_ROW, company_name=secret + "\n", contact_email=secret), {"company_name": secret}, secret]
        self.assertNotIn(secret, json.dumps(analyze_rows(rows, scope=SCOPE), ensure_ascii=False))

    def test_scope_does_not_change_classification(self):
        rows = [valid_row(1), valid_row(1), None]
        other_scope = dict(SCOPE, client_id="other-client", campaign_id="other-campaign")
        first, second = analyze_rows(rows, scope=SCOPE), analyze_rows(rows, scope=other_scope)
        self.assertEqual(first["rows"], second["rows"])
        self.assertEqual(second["scope"], other_scope)


if __name__ == "__main__":
    unittest.main()
