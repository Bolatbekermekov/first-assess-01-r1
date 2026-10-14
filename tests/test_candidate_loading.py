"""Candidate tests: load_rows parsing, limits and error precedence (CONTRACT.md 5; CP1 A4-A7, A11, A12)."""

import csv
import io
import json
import sys
import traceback
import unittest
from pathlib import Path
from unittest import mock

from assess_workbench.api import WorkbenchError, analyze_rows, load_rows

ROOT = Path(__file__).resolve().parents[1]
SCOPE = json.loads((ROOT / "fixtures" / "scope.json").read_text(encoding="utf-8"))
LIMIT = 10_485_760
FIELDS = ("company_name", "contact_email", "website_url", "country_code", "language", "source_ref")
HEADER = ",".join(FIELDS).encode()
BOM = b"\xef\xbb\xbf"
ROW = {
    "company_name": "Example Labs",
    "contact_email": "person@example.test",
    "website_url": "https://example.test/",
    "country_code": "DK",
    "language": "en",
    "source_ref": "candidate:baseline",
}


def csv_bytes(rows, header=FIELDS, newline="\n"):
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator=newline)
    writer.writerow(header)
    writer.writerows([[row[name] for name in header] for row in rows])
    return buffer.getvalue().encode("utf-8")


def json_bytes(value):
    return json.dumps(value).encode("utf-8")


class LoaderTestCase(unittest.TestCase):
    def assert_error(self, code, data, data_format):
        with self.subTest(code=code, data=repr(data)[:60], format=data_format):
            with self.assertRaises(WorkbenchError) as caught:
                load_rows(data, format=data_format)
            error = caught.exception
            self.assertEqual((error.code, str(error), error.args), (code, code, (code,)))
            self.assertIsNone(error.__cause__)
            self.assertIsNone(error.__context__)
            return error


class ErrorPrecedenceTests(LoaderTestCase):
    def test_data_must_be_exact_bytes(self):
        class BytesSubclass(bytes):
            pass

        for data in ["[]", bytearray(b"[]"), memoryview(b"[]"), None, 0, BytesSubclass(b"[]")]:
            self.assert_error("INVALID_DATA", data, "json")
        self.assert_error("INVALID_DATA", None, "xml")

    def test_format_must_be_exactly_json_or_csv(self):
        for data_format in ["JSON", "Csv", "json ", "", "xml", None, b"json", ["json"]]:
            self.assert_error("INVALID_FORMAT", b"[]", data_format)
        self.assert_error("INVALID_FORMAT", b" " * (LIMIT + 1), "xml")

    def test_size_is_checked_before_encoding(self):
        for data_format in ("json", "csv"):
            self.assert_error("INPUT_TOO_LARGE", b"\xff" * (LIMIT + 1), data_format)

    def test_encoding_is_checked_before_syntax(self):
        for data_format in ("json", "csv"):
            self.assert_error("INVALID_ENCODING", b"\xff", data_format)
            self.assert_error("INVALID_ENCODING", b'[{"a": "\xff"', data_format)

    def test_syntax_is_checked_before_row_count(self):
        self.assert_error("INVALID_DOCUMENT", json_bytes([None] * 10_001) + b" junk", "json")
        self.assert_error("INVALID_DOCUMENT", csv_bytes([ROW] * 10_001) + b"too,few\n", "csv")


class LimitTests(LoaderTestCase):
    def test_json_size_limit_is_inclusive(self):
        exact = b"[]" + b" " * (LIMIT - 2)
        self.assertEqual(load_rows(exact, format="json"), [])
        self.assert_error("INPUT_TOO_LARGE", exact + b" ", "json")

    def test_bom_counts_towards_the_size_limit(self):
        exact = BOM + b"[]" + b" " * (LIMIT - 5)
        self.assertEqual(len(exact), LIMIT)
        self.assertEqual(load_rows(exact, format="json"), [])
        self.assert_error("INPUT_TOO_LARGE", exact + b" ", "json")

    def test_csv_size_limit_is_inclusive_and_huge_fields_load(self):
        prefix = csv_bytes([]) + b"Example,person@example.test,,,,"
        data = prefix + b"r" * (LIMIT - len(prefix) - 1) + b"\n"
        self.assertEqual(len(data), LIMIT)
        rows = load_rows(data, format="csv")
        self.assertEqual(len(rows[0]["source_ref"]), LIMIT - len(prefix) - 1)
        self.assert_error("INPUT_TOO_LARGE", data + b"\n", "csv")

    def test_row_count_limit_is_inclusive(self):
        self.assertEqual(len(load_rows(json_bytes([None] * 10_000), format="json")), 10_000)
        self.assert_error("TOO_MANY_ROWS", json_bytes([None] * 10_001), "json")
        self.assertEqual(len(load_rows(csv_bytes([ROW] * 10_000), format="csv")), 10_000)
        self.assert_error("TOO_MANY_ROWS", csv_bytes([ROW] * 10_001), "csv")


class EncodingTests(LoaderTestCase):
    def test_a_single_leading_bom_is_removed(self):
        self.assertEqual(load_rows(BOM + b"[]", format="json"), [])
        self.assertEqual(load_rows(BOM + HEADER + b"\n", format="csv"), [])

    def test_a_second_bom_is_a_document_error(self):
        # CP1 A5: decoding succeeds; the remaining U+FEFF fails the syntax check.
        self.assert_error("INVALID_DOCUMENT", BOM + BOM + b"[]", "json")
        self.assert_error("INVALID_DOCUMENT", BOM + BOM + HEADER + b"\n", "csv")
        self.assert_error("INVALID_DOCUMENT", b"[" + BOM + b"]", "json")

    def test_bom_only_is_an_empty_document(self):
        for data_format in ("json", "csv"):
            self.assert_error("INVALID_DOCUMENT", BOM, data_format)

    def test_invalid_utf8(self):
        samples = [
            b"\xff",
            b"\xc0\x80",
            b'["\xed\xa0\x80"]',
            b'["\xe2\x82"]',
            b"\xff\xfe[\x00]\x00",
            b'["caf\xe9"]',
            b"\xf8\x88\x80\x80\x80",
        ]
        for data_format in ("json", "csv"):
            for data in samples:
                self.assert_error("INVALID_ENCODING", data, data_format)


class JsonDocumentTests(LoaderTestCase):
    def test_array_elements_are_returned_unchanged(self):
        document = [None, 1, -0.5, "x", True, [], {}, {"company_name": "A", "extra": {"nested": [1, {"k": "v"}]}}]
        loaded = load_rows(json_bytes(document), format="json")
        self.assertEqual(loaded, document)
        self.assertEqual(list(loaded[-1]), ["company_name", "extra"])

    def test_json_whitespace_around_the_root(self):
        for data in [b" \t\r\n[] \t\r\n", b"\r\n[\r\n]\r\n"]:
            self.assertEqual(load_rows(data, format="json"), [])

    def test_invalid_documents(self):
        samples = [
            b"",
            b"   ",
            b"{}",
            b'{"rows": []}',
            b'"x"',
            b"1",
            b"null",
            b"true",
            b"[] []",
            b"[],",
            b"[]x",
            b"[]\x0c",
            b"[]\x00",
            b"\x0c[]",
            b"[1,]",
            b"[01]",
            b"['x']",
            b"[undefined]",
            b"[nan]",
            b'["a\x01"]',
            b'["a\nb"]',
            b"/* c */ []",
            b"[] // c",
        ]
        for data in samples:
            self.assert_error("INVALID_DOCUMENT", data, "json")

    def test_non_finite_constants_are_rejected_at_any_depth(self):
        for data in [b"[NaN]", b"[Infinity]", b"[-Infinity]", b'[{"a": [Infinity]}]', b'[{"a": {"b": -Infinity}}]']:
            self.assert_error("INVALID_DOCUMENT", data, "json")

    def test_duplicate_keys_are_rejected_at_any_depth(self):
        samples = [
            b'[{"a": 1, "a": 2}]',
            b'[{"a": 1, "a": 1}]',
            b'[{"x": {"b": {"c": 1, "c": 2}}}]',
            b'[{"x": [{"k": 1, "k": 1}]}]',
            b'[[[{"k": 1, "k": 2}]]]',
            b'[{"a": 1, "\\u0061": 2}]',
            b'[{"company_name": "A", "company_name": "B"}]',
        ]
        for data in samples:
            self.assert_error("INVALID_DOCUMENT", data, "json")

    def test_keys_that_differ_only_in_unicode_normalization_are_distinct(self):
        self.assertEqual(
            load_rows('[{"\u00e9": 1, "e\u0301": 2}]'.encode(), format="json"), [{"\u00e9": 1, "e\u0301": 2}]
        )

    def test_deep_nesting_is_a_document_error(self):
        # CP1 A7: the exact depth limit belongs to the interpreter; only RecursionError is translated.
        self.assert_error("INVALID_DOCUMENT", b"[" * 100_000 + b"]" * 100_000, "json")
        self.assertEqual(len(load_rows(b"[" * 50 + b"]" * 50, format="json")), 1)

    def test_nesting_limit_does_not_follow_sys_setrecursionlimit(self):
        # CP1 A7: the C scanner counts its own depth, so a caller's low recursion limit must not reject 400 levels.
        self.addCleanup(sys.setrecursionlimit, sys.getrecursionlimit())
        arrays = b"[" * 400 + b"]" * 400
        objects = b"[" + b'{"a": ' * 400 + b"1" + b"}" * 400 + b"]"
        for limit in (200, 100_000):
            with self.subTest(limit=limit):
                sys.setrecursionlimit(limit)
                self.assertEqual([len(load_rows(data, format="json")) for data in (arrays, objects)], [1, 1])
                self.assert_error("INVALID_DOCUMENT", b"[" * 100_000 + b"]" * 100_000, "json")

    def test_out_of_range_float_is_passed_to_the_analyzer(self):
        rows = load_rows(b"[1e400, -1e400]", format="json")  # CP1 A11
        self.assertEqual(rows, [float("inf"), float("-inf")])
        report = analyze_rows(rows, scope=SCOPE)
        self.assertEqual([row["codes"] for row in report["rows"]], [["INVALID_ROW_SCHEMA"]] * 2)

    def test_escaped_surrogate_loads_and_is_rejected_by_the_analyzer(self):
        rows = load_rows(json.dumps([dict(ROW, company_name="\ud800")]).encode("ascii"), format="json")
        self.assertEqual(rows[0]["company_name"], "\ud800")
        self.assertEqual(analyze_rows(rows, scope=SCOPE)["rows"][0]["codes"], ["INVALID_COMPANY_NAME"])


class IntegerDigitLimitTests(LoaderTestCase):
    """CP1 A6 as revised in R2: a JSON integer of any length is a valid number that the analyzer rejects.

    int() refuses literals longer than sys.get_int_max_str_digits(), a process-wide setting. load_rows must give the
    same result under every value of it and must not change it. Literals are built as text and expected values by
    arithmetic, because converting between the two is exactly what the setting restricts.
    """

    LIMITS = (4300, 640, 0)  # the CPython default, the smallest non-zero value, no limit

    def setUp(self):
        self.addCleanup(sys.set_int_max_str_digits, sys.get_int_max_str_digits())

    def test_review_reproduction_is_a_rejected_row_under_every_limit(self):
        data = b"[" + b"9" * 4301 + b"]"
        for limit in self.LIMITS:
            with self.subTest(limit=limit):
                sys.set_int_max_str_digits(limit)
                rows = load_rows(data, format="json")
                self.assertEqual(rows, [10**4301 - 1])
                row = analyze_rows(rows, scope=SCOPE)["rows"][0]
                self.assertEqual((row["status"], row["codes"]), ("REJECTED", ["INVALID_ROW_SCHEMA"]))
                self.assertEqual(sys.get_int_max_str_digits(), limit)

    def test_long_integers_keep_their_exact_value_at_any_depth(self):
        cases = [
            ("9" * 640, 10**640 - 1),
            ("9" * 641, 10**641 - 1),
            ("-1" + "0" * 1280, -(10**1280)),
            ("8" * 1280, 8 * (10**1280 - 1) // 9),
            ("10203" * 2000, 10203 * (10**10_000 - 1) // (10**5 - 1)),
            ("-1" + "0" * 99_999 + "7", -(10**100_000 + 7)),
        ]
        for limit in self.LIMITS:
            sys.set_int_max_str_digits(limit)
            for literal, expected in cases:
                with self.subTest(limit=limit, digits=len(literal.lstrip("-"))):
                    data = f'[{literal}, [{literal}], {{"k": {literal}}}]'.encode()
                    rows = load_rows(data, format="json")
                    self.assertEqual(rows, [expected, [expected], {"k": expected}])
                    self.assertIs(type(rows[0]), int)

    def test_long_integer_field_value_reaches_its_field_rule(self):
        data = json.dumps([dict(ROW, company_name=0)]).replace('"company_name": 0', '"company_name": ' + "7" * 5000)
        for limit in self.LIMITS:
            with self.subTest(limit=limit):
                sys.set_int_max_str_digits(limit)
                rows = load_rows(data.encode(), format="json")
                self.assertEqual(rows[0]["company_name"], 7 * (10**5000 - 1) // 9)
                self.assertEqual(analyze_rows(rows, scope=SCOPE)["rows"][0]["codes"], ["INVALID_COMPANY_NAME"])

    def test_the_process_wide_setting_is_never_changed(self):
        sys.set_int_max_str_digits(4300)
        refuse = mock.Mock(side_effect=AssertionError("load_rows changed sys.set_int_max_str_digits"))
        with mock.patch.object(sys, "set_int_max_str_digits", refuse):
            rows = load_rows(b"[" + b"9" * 4301 + b"]", format="json")
        refuse.assert_not_called()
        self.assertEqual(rows, [10**4301 - 1])
        self.assertEqual(sys.get_int_max_str_digits(), 4300)


class CsvDocumentTests(LoaderTestCase):
    def test_header_order_is_free_and_rows_use_canonical_key_order(self):
        rows = load_rows(csv_bytes([ROW], header=tuple(reversed(FIELDS))), format="csv")  # CP1 A12
        self.assertEqual(rows, [ROW])
        self.assertEqual(list(rows[0]), list(FIELDS))

    def test_line_endings(self):
        expected = [ROW, dict(ROW, source_ref="second")]
        lf = csv_bytes(expected)
        samples = {
            "LF": lf,
            "CRLF": csv_bytes(expected, newline="\r\n"),
            "no final newline": lf.rstrip(b"\n"),
            "mixed": lf.replace(b"\n", b"\r\n", 1),
            "lone CR (CP1 A4)": lf.replace(b"\n", b"\r"),
        }
        for name, data in samples.items():
            with self.subTest(name):
                self.assertEqual(load_rows(data, format="csv"), expected)

    def test_header_only(self):
        for data in [HEADER, HEADER + b"\n", HEADER + b"\r\n", BOM + HEADER + b"\r\n"]:
            self.assertEqual(load_rows(data, format="csv"), [])

    def test_quoted_cells(self):
        tricky = dict(ROW, company_name='Comma, "Quote" Co', source_ref="multi\nline", language="")
        data = csv_bytes([tricky])
        self.assertIn(b'"Comma, ""Quote"" Co"', data)
        rows = load_rows(data, format="csv")
        self.assertEqual(rows, [tricky])
        self.assertEqual(analyze_rows(rows, scope=SCOPE)["rows"][0]["codes"], ["INVALID_SOURCE_REF"])

    def test_quoted_header_names_are_plain_csv_quoting(self):
        quoted = b",".join(b'"' + name.encode() + b'"' for name in FIELDS) + b"\r\n"
        self.assertEqual(load_rows(BOM + quoted, format="csv"), [])

    def test_bare_quote_inside_an_unquoted_cell_is_kept(self):
        data = csv_bytes([]) + b'Ex"ample,person@example.test,,,,ref\n'
        self.assertEqual(load_rows(data, format="csv")[0]["company_name"], 'Ex"ample')

    def test_nul_in_a_cell_loads_and_is_rejected_by_the_analyzer(self):
        rows = load_rows(csv_bytes([]) + b"Ex\x00ample,person@example.test,,,,ref\n", format="csv")
        self.assertEqual(rows[0]["company_name"], "Ex\x00ample")
        self.assertEqual(analyze_rows(rows, scope=SCOPE)["rows"][0]["codes"], ["INVALID_COMPANY_NAME"])

    def test_invalid_documents(self):
        row = b"Example,person@example.test,,,,ref"
        samples = {
            "empty": b"",
            "empty header record": b"\n",
            "five columns": ",".join(FIELDS[:5]).encode() + b"\n",
            "seven columns": HEADER + b",extra\n",
            "duplicate column": ",".join((*FIELDS[:5], FIELDS[0])).encode() + b"\n",
            "unknown column": HEADER.replace(b"source_ref", b"source") + b"\n",
            "padded name": HEADER.replace(b"company_name", b" company_name") + b"\n",
            "different case": HEADER.replace(b"company_name", b"Company_name") + b"\n",
            "semicolon delimiter": HEADER.replace(b",", b";") + b"\n",
            "comment line": b"# comment\n" + HEADER + b"\n",
            "five cells": HEADER + b"\nExample,person@example.test,,,\n",
            "seven cells": HEADER + b"\n" + row + b",x\n",
            "blank line in the middle": HEADER + b"\n\n" + row + b"\n",
            "blank line at the end": HEADER + b"\n" + row + b"\n\n",
            "spaces-only line": HEADER + b"\n   \n",
            "text after closing quote": HEADER + b'\n"Ex"ample,person@example.test,,,,ref\n',
            "space after closing quote": HEADER + b'\n"Example" ,person@example.test,,,,ref\n',
            "unterminated quote": HEADER + b'\n"Example,person@example.test,,,,ref\n',
        }
        for name, data in samples.items():
            with self.subTest(name):
                self.assert_error("INVALID_DOCUMENT", data, "csv")


class CsvFieldSizeLimitTests(LoaderTestCase):
    def setUp(self):
        self.original = csv.field_size_limit()
        self.addCleanup(csv.field_size_limit, self.original)

    def test_limit_is_restored_after_success_and_after_errors(self):
        big = dict(ROW, source_ref="r" * 200_000)
        self.assertEqual(load_rows(csv_bytes([big]), format="csv"), [big])
        self.assertEqual(csv.field_size_limit(), self.original)
        self.assert_error("INVALID_DOCUMENT", b'"unterminated', "csv")
        self.assertEqual(csv.field_size_limit(), self.original)
        self.assert_error("INVALID_DOCUMENT", csv_bytes([]) + b"x\n", "csv")
        self.assertEqual(csv.field_size_limit(), self.original)

    def test_the_callers_limit_is_neither_needed_nor_changed(self):
        csv.field_size_limit(10)
        big = dict(ROW, source_ref="r" * 200_000)
        self.assertEqual(load_rows(csv_bytes([big]), format="csv"), [big])
        self.assertEqual(csv.field_size_limit(), 10)


class ErrorHygieneTests(LoaderTestCase):
    SECRET = "SECRET-SENTINEL-8f2c"

    def test_errors_do_not_carry_input(self):
        secret = self.SECRET.encode()
        cases = [
            ("INVALID_ENCODING", secret + b"\xff", "json"),
            ("INVALID_ENCODING", secret + b"\xff", "csv"),
            ("INVALID_DOCUMENT", b'["' + secret + b'" junk', "json"),
            ("INVALID_DOCUMENT", b'[{"' + secret + b'": 1, "' + secret + b'": 2}]', "json"),
            ("INVALID_DOCUMENT", b"[" + secret + b"]", "json"),
            ("INVALID_DOCUMENT", secret + b'\n"' + secret, "csv"),
            ("INVALID_DOCUMENT", secret + b"\n", "csv"),
        ]
        for code, data, data_format in cases:
            error = self.assert_error(code, data, data_format)
            rendered = "".join(traceback.format_exception(error)) + repr(error) + repr(vars(error))
            self.assertNotIn(self.SECRET, rendered)


if __name__ == "__main__":
    unittest.main()
