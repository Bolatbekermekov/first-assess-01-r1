"""Candidate tests: exact-email duplicate and conflict classification (CONTRACT.md 3)."""

import json
import unittest
from pathlib import Path

from assess_workbench.api import analyze_rows

ROOT = Path(__file__).resolve().parents[1]
SCOPE = json.loads((ROOT / "fixtures" / "scope.json").read_text(encoding="utf-8"))
ROW = {
    "company_name": "Alpha Labs",
    "contact_email": "buyer@example.test",
    "website_url": "https://alpha.example.test/",
    "country_code": "DK",
    "language": "en-US",
    "source_ref": "candidate:one",
}
UNIQUE = ("UNIQUE", ["VALID_RECORD"], None)
CONFLICT = ("CONFLICT", ["EMAIL_METADATA_CONFLICT"], None)


def duplicate_of(row_number):
    return ("DUPLICATE", ["EXACT_DUPLICATE"], row_number)


def rejected(*codes):
    return ("REJECTED", list(codes), None)


def outcomes(*rows):
    report = analyze_rows(list(rows), scope=SCOPE)
    return [(row["status"], row["codes"], row["duplicate_of_row"]) for row in report["rows"]]


class GroupingTests(unittest.TestCase):
    def test_single_valid_row_is_unique(self):
        self.assertEqual(outcomes(ROW), [UNIQUE])

    def test_identical_rows_point_to_the_first(self):
        self.assertEqual(outcomes(ROW, dict(ROW), dict(ROW)), [UNIQUE, duplicate_of(1), duplicate_of(1)])

    def test_duplicates_are_found_after_normalization_and_keep_their_own_values(self):
        variant = {
            "company_name": "  alpha   LABS ",
            "contact_email": " Buyer@EXAMPLE.test ",
            "website_url": "https://ALPHA.example.test/",
            "country_code": "dk",
            "language": "EN-us",
            "source_ref": "candidate:two",
        }
        rows = analyze_rows([ROW, variant], scope=SCOPE)["rows"]
        self.assertEqual([row["status"] for row in rows], ["UNIQUE", "DUPLICATE"])
        self.assertEqual(rows[1]["normalized"]["company_name"], "alpha LABS")
        self.assertEqual(rows[1]["normalized"]["source_ref"], "candidate:two")

    def test_source_ref_is_not_part_of_the_key(self):
        self.assertEqual(outcomes(ROW, dict(ROW, source_ref="elsewhere")), [UNIQUE, duplicate_of(1)])

    def test_representative_is_the_first_valid_row(self):
        invalid_language = dict(ROW, language="english")
        self.assertEqual(
            outcomes(invalid_language, ROW, dict(ROW)),
            [rejected("INVALID_LANGUAGE"), UNIQUE, duplicate_of(2)],
        )
        self.assertEqual(
            outcomes(None, invalid_language, dict(ROW, source_ref="b"), ROW),
            [rejected("INVALID_ROW_SCHEMA"), rejected("INVALID_LANGUAGE"), UNIQUE, duplicate_of(3)],
        )

    def test_rejected_rows_never_join_or_split_a_group(self):
        other_but_invalid = dict(ROW, company_name="Other", source_ref="")
        self.assertEqual(
            outcomes(ROW, other_but_invalid, dict(ROW)),
            [UNIQUE, rejected("INVALID_SOURCE_REF"), duplicate_of(1)],
        )

    def test_a_late_difference_turns_the_whole_group_into_conflicts(self):
        other = dict(ROW, company_name="Different")
        for rows in ([ROW, ROW, other], [ROW, other, ROW], [other, ROW, ROW]):
            with self.subTest(order=[row["company_name"] for row in rows]):
                self.assertEqual(outcomes(*rows), [CONFLICT] * 3)

    def test_blank_and_populated_values_conflict(self):
        for field in ("website_url", "country_code", "language"):
            with self.subTest(field=field):
                self.assertEqual(outcomes(ROW, dict(ROW, **{field: ""})), [CONFLICT, CONFLICT])

    def test_every_metadata_field_participates(self):
        changes = {
            "company_name": "Alpha Labs Ltd",
            "website_url": "https://alpha.example.test/other",
            "country_code": "SE",
            "language": "en-GB",
        }
        for field, value in changes.items():
            with self.subTest(field=field):
                self.assertEqual(outcomes(ROW, dict(ROW, **{field: value})), [CONFLICT, CONFLICT])

    def test_company_name_is_compared_casefolded_after_nfc(self):
        self.assertEqual(
            outcomes(dict(ROW, company_name="Straße"), dict(ROW, company_name="STRASSE")),
            [UNIQUE, duplicate_of(1)],
        )
        self.assertEqual(
            outcomes(dict(ROW, company_name="Café"), dict(ROW, company_name="Café")),
            [UNIQUE, duplicate_of(1)],
        )
        # U+0130 casefolds to "i" + U+0307, so these names differ under the contract's key.
        self.assertEqual(
            outcomes(dict(ROW, company_name="İstanbul"), dict(ROW, company_name="istanbul")),
            [CONFLICT, CONFLICT],
        )

    def test_url_details_are_significant(self):
        self.assertEqual(
            outcomes(dict(ROW, website_url="https://example.test"), dict(ROW, website_url="https://example.test/")),
            [CONFLICT, CONFLICT],
        )
        self.assertEqual(
            outcomes(dict(ROW, website_url="https://example.test/A"), dict(ROW, website_url="https://example.test/a")),
            [CONFLICT, CONFLICT],
        )
        self.assertEqual(
            outcomes(dict(ROW, website_url="https://EXAMPLE.test/a?"), dict(ROW, website_url="https://example.test/a")),
            [UNIQUE, duplicate_of(1)],
        )

    def test_no_fuzzy_matching_across_emails(self):
        emails = ["buyer@example.test", "buyer+tag@example.test", "b.uyer@example.test", "buyer@example.test.example",
                  "buyer@exarnple.test"]
        self.assertEqual(outcomes(*(dict(ROW, contact_email=email) for email in emails)), [UNIQUE] * 5)

    def test_interleaved_groups_keep_input_order(self):
        group_b = dict(ROW, contact_email="b@example.test")
        group_c = dict(ROW, contact_email="c@example.test")
        self.assertEqual(
            outcomes(ROW, group_b, dict(ROW), group_c, dict(group_b, country_code="SE"), dict(ROW)),
            [UNIQUE, CONFLICT, duplicate_of(1), UNIQUE, CONFLICT, duplicate_of(1)],
        )

    def test_reordering_changes_the_representative(self):
        first, second = dict(ROW, source_ref="first"), dict(ROW, source_ref="second")
        forward = analyze_rows([first, second], scope=SCOPE)["rows"]
        backward = analyze_rows([second, first], scope=SCOPE)["rows"]
        self.assertEqual([row["normalized"]["source_ref"] for row in forward if row["status"] == "UNIQUE"], ["first"])
        self.assertEqual([row["normalized"]["source_ref"] for row in backward if row["status"] == "UNIQUE"], ["second"])
        self.assertEqual(backward[1]["duplicate_of_row"], 1)

    def test_summary_counts_rows_not_groups(self):
        rows = [ROW, dict(ROW), dict(ROW), dict(ROW, contact_email="x@example.test"),
                dict(ROW, contact_email="y@example.test"), dict(ROW, contact_email="y@example.test", language=""), None]
        summary = analyze_rows(rows, scope=SCOPE)["summary"]
        self.assertEqual(summary, {"total": 7, "unique": 2, "duplicate": 2, "conflict": 2, "rejected": 1})


if __name__ == "__main__":
    unittest.main()
