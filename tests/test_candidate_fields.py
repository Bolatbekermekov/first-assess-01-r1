"""Candidate tests: field general rule, normalization and limits (CONTRACT.md 2; CP1 A1-A3, A8, A10)."""

import collections
import json
import unicodedata
import unittest
from pathlib import Path

from assess_workbench.api import analyze_rows

ROOT = Path(__file__).resolve().parents[1]
SCOPE = json.loads((ROOT / "fixtures" / "scope.json").read_text(encoding="utf-8"))
FIELD_CODES = {
    "company_name": "INVALID_COMPANY_NAME",
    "contact_email": "INVALID_CONTACT_EMAIL",
    "website_url": "INVALID_WEBSITE_URL",
    "country_code": "INVALID_COUNTRY_CODE",
    "language": "INVALID_LANGUAGE",
    "source_ref": "INVALID_SOURCE_REF",
}
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


def check(**overrides):
    """Analyze VALID_ROW with ``overrides`` applied and return its report row."""
    return analyze_rows([dict(VALID_ROW, **overrides)], scope=SCOPE)["rows"][0]


class FieldTestCase(unittest.TestCase):
    def assert_valid(self, field, raw, expected):
        with self.subTest(field=field, raw=raw):
            row = check(**{field: raw})
            self.assertEqual(row["status"], "UNIQUE", msg=f"{field}={raw!r} -> {row['codes']}")
            self.assertEqual(row["normalized"][field], expected)

    def assert_invalid(self, field, raw):
        with self.subTest(field=field, raw=raw):
            row = check(**{field: raw})
            self.assertEqual(row["status"], "REJECTED", msg=f"{field}={raw!r}")
            self.assertEqual(row["codes"], [FIELD_CODES[field]])
            self.assertIsNone(row["normalized"])
            self.assertIsNone(row["duplicate_of_row"])


class GeneralRuleTests(FieldTestCase):
    def test_values_must_be_exact_str(self):
        for field, value in VALID_ROW.items():
            for raw in [None, 0, 1.5, True, b"x", ["x"], {"x": "y"}, StrSubclass(value)]:
                self.assert_invalid(field, raw)

    def test_raw_length_limit_is_4096_code_points_before_normalization(self):
        baseline = check()["normalized"]
        for field, value in VALID_ROW.items():
            padding = 4096 - len(value)
            self.assert_valid(field, " " * padding + value, baseline[field])
            self.assert_invalid(field, " " * (padding + 1) + value)

    def test_control_characters_and_surrogates_are_rejected_anywhere(self):
        forbidden = [
            "\x00",
            "\x01",
            "\t",
            "\n",
            "\x0b",
            "\x0c",
            "\r",
            "\x1b",
            "\x1f",
            "\x7f",
            "\ud800",
            "\udbff",
            "\udc00",
            "\udfff",
        ]
        for field, value in VALID_ROW.items():
            middle = len(value) // 2
            for char in forbidden:
                for raw in (char + value, value[:middle] + char + value[middle:], value + char):
                    self.assert_invalid(field, raw)

    def test_c1_controls_and_format_characters_are_not_forbidden_by_the_general_rule(self):
        # CP1 A3: only C0, DEL and surrogates are forbidden; ASCII-only fields reject the rest by syntax.
        self.assert_valid("company_name", "Ex\u0080ample\u200b Labs", "Ex\u0080ample\u200b Labs")
        self.assert_valid("source_ref", "ref\u202e\u2066x\u009f", "ref\u202e\u2066x\u009f")
        self.assert_invalid("contact_email", "pers\u200bon@example.test")
        self.assert_invalid("website_url", "https://exa\u0080mple.test/")

    def test_non_ascii_whitespace_is_removed_by_strip_and_split(self):
        # CP1 A3: str.strip()/str.split() also remove Unicode whitespace such as NBSP or U+3000.
        self.assert_valid("company_name", "\u00a0Example\u3000\u2028Labs\u0085", "Example Labs")
        self.assert_valid("contact_email", "\u00a0Person@Example.test\u2003", "person@example.test")
        self.assert_valid("website_url", "\u3000https://example.test/\u00a0", "https://example.test/")
        self.assert_valid("country_code", "\u2009dk\u202f", "DK")
        self.assert_valid("language", "\u205fEN-us\u1680", "en-US")
        self.assert_valid("source_ref", "\u00a0ref\u00a0x\u00a0", "ref\u00a0x")


class CompanyNameTests(FieldTestCase):
    def test_nfc_and_whitespace_collapse(self):
        cases = {
            "  Alpha   Labs ": "Alpha Labs",
            "Cafe\u0301": "Caf\u00e9",
            "A\u030a ngstr\u00f6m": "\u00c5 ngstr\u00f6m",
            "ALPHA labs": "ALPHA labs",
            "\ufb01rm \uff21": "\ufb01rm \uff21",
            "Tom &amp; Jerry": "Tom &amp; Jerry",
            "<b>x</b>": "<b>x</b>",
        }
        for raw, expected in cases.items():
            self.assert_valid("company_name", raw, expected)

    def test_length_after_normalization(self):
        self.assert_valid("company_name", "x", "x")
        self.assert_valid("company_name", "x" * 200, "x" * 200)
        self.assert_valid("company_name", "e\u0301" * 200, "\u00e9" * 200)
        self.assert_valid("company_name", "x " * 100 + "     ", ("x " * 100).strip())
        for raw in ["x" * 201, "", "   ", "\u00a0\u3000"]:
            self.assert_invalid("company_name", raw)

    def test_nfc_can_lengthen_a_value_past_the_limit(self):
        grows = "\u0344"  # COMBINING GREEK DIALYTIKA TONOS: one code point, two after NFC
        self.assertEqual(len(unicodedata.normalize("NFC", grows * 100)), 200)
        self.assert_valid("company_name", grows * 100, unicodedata.normalize("NFC", grows * 100))
        self.assert_invalid("company_name", grows * 101)


class ContactEmailTests(FieldTestCase):
    def test_normalization(self):
        cases = {
            " Person@Example.TEST ": "person@example.test",
            "first.last+tag@example.test": "first.last+tag@example.test",
            "a!#$%&'*+/=?^_`{|}~-z@example.test": "a!#$%&'*+/=?^_`{|}~-z@example.test",
            "x@sub-domain.example.test": "x@sub-domain.example.test",
            "x@example.123": "x@example.123",
        }
        for raw, expected in cases.items():
            self.assert_valid("contact_email", raw, expected)

    def test_length_limits(self):
        local64, label63 = "a" * 64, "b" * 63
        domain189 = f"{label63}.{'c' * 63}.{'d' * 61}"
        self.assertEqual(len(f"{local64}@{domain189}"), 254)
        self.assert_valid("contact_email", f"{local64}@{domain189}", f"{local64}@{domain189}")
        self.assert_invalid("contact_email", f"{local64}@{domain189}d")
        self.assert_invalid("contact_email", f"{'a' * 65}@example.test")
        self.assert_valid("contact_email", f"x@{label63}.test", f"x@{label63}.test")
        self.assert_invalid("contact_email", f"x@{'b' * 64}.test")

    def test_syntax(self):
        invalid = [
            "",
            "   ",
            "no-at-sign",
            "@example.test",
            "x@",
            "x@example",
            "x@@example.test",
            "x@example..test",
            "x@.example.test",
            "x@example.test.",
            "x@-example.test",
            "x@example-.test",
            "x@exa_mple.test",
            ".x@example.test",
            "x.@example.test",
            "x..y@example.test",
            "x y@example.test",
            "x@exa mple.test",
            '"x"@example.test',
            "x@[192.0.2.1]",
            "x(comment)@example.test",
            "x,y@example.test",
        ]
        for raw in invalid:
            self.assert_invalid("contact_email", raw)

    def test_non_ascii_is_rejected(self):
        for raw in [
            "p\u00e9rson@example.test",
            "person@ex\u00e4mple.test",
            "person@example.test\u200b",
            "\u0130@example.test",
        ]:
            self.assert_invalid("contact_email", raw)

    def test_kelvin_sign_lowercases_to_ascii(self):
        # CP1 A1: checks run on the normalized value, and U+212A.lower() == "k".
        self.assert_valid("contact_email", "\u212aate@example.test", "kate@example.test")


class WebsiteUrlTests(FieldTestCase):
    def test_valid_urls_and_normalization(self):
        cases = {
            "": "",
            "   ": "",
            " https://Example.TEST/Path?Q=1 ": "https://example.test/Path?Q=1",
            "https://example.test": "https://example.test",
            "https://example.test/": "https://example.test/",
            "https://example.test/?": "https://example.test/",
            "https://example.test?": "https://example.test",
            "https://example.test/p??q": "https://example.test/p??q",
            "https://example.test/a%20b/%2F?q=%41&x=%zz": "https://example.test/a%20b/%2F?q=%41&x=%zz",
            "https://example.test//double//slash": "https://example.test//double//slash",
            "https://example.test/path@x;p=1": "https://example.test/path@x;p=1",
            "https://sub.a-b.example.test/": "https://sub.a-b.example.test/",
            "https://xn--80ak6aa92e.test/": "https://xn--80ak6aa92e.test/",
            "https://1.2.3.4/": "https://1.2.3.4/",
        }
        for raw, expected in cases.items():
            self.assert_valid("website_url", raw, expected)

    def test_invalid_urls(self):
        invalid = [
            "http://example.test",
            "HTTPS://example.test",
            "Https://example.test",
            "https:/example.test",
            "https//example.test",
            "ftp://example.test",
            "//example.test",
            "example.test",
            "https://",
            "https:///path",
            "https://localhost",
            "https://example",
            "https://example.test:443/",
            "https://example.test:/",
            "https://user@example.test",
            "https://user:pw@example.test",
            "https://[::1]/",
            "https://[example.test/",
            "https://example.test]/",
            "https://example.test/#",
            "https://example.test#",
            "https://example.test/#frag",
            "https://example.test/?q#",
            "https://exa mple.test",
            "https://example.test/has space",
            "https://ex\u00e4mple.test",
            "https://example.test/p\u00e4th",
            "https://-example.test",
            "https://example-.test",
            "https://exa_mple.test",
            "https://example..test",
            "https://.example.test",
            "https://example.test.",
            "https://example.test\\path",
            "https://%65xample.test",
            "https://example.test%2F",
            "https://*.example.test",
        ]
        for raw in invalid:
            self.assert_invalid("website_url", raw)

    def test_length_limits(self):
        base = "https://example.test/"
        self.assert_valid("website_url", base + "p" * (2048 - len(base)), base + "p" * (2048 - len(base)))
        self.assert_invalid("website_url", base + "p" * (2049 - len(base)))
        label63 = "a" * 63
        host253 = f"{label63}.{'b' * 63}.{'c' * 63}.{'d' * 61}"
        self.assertEqual(len(host253), 253)
        self.assert_valid("website_url", f"https://{host253}/", f"https://{host253}/")
        self.assert_invalid("website_url", f"https://{host253}d/")
        self.assert_valid("website_url", f"https://{label63}.test", f"https://{label63}.test")
        self.assert_invalid("website_url", f"https://{'a' * 64}.test")


class CountryCodeTests(FieldTestCase):
    def test_valid(self):
        for raw, expected in {"dk": "DK", " Dk ": "DK", "DK": "DK", "": "", "   ": ""}.items():
            self.assert_valid("country_code", raw, expected)

    def test_invalid(self):
        for raw in ["D", "DNK", "D1", "12", "D K", "DK-", "\u00c4\u00d6", "D\u00a0K", "DK.", "Dk\u200b"]:
            self.assert_invalid("country_code", raw)

    def test_unicode_uppercase_mappings_to_ascii(self):
        # CP1 A2: str.upper() maps some non-ASCII letters to ASCII before the [A-Z]{2} check.
        cases = {"\u00df": "SS", "\u017fe": "SE", "\u0131t": "IT", "\ufb00": "FF", "\ufb06": "ST"}
        for raw, expected in cases.items():
            self.assert_valid("country_code", raw, expected)


class LanguageTests(FieldTestCase):
    def test_valid(self):
        cases = {
            "EN-us": "en-US",
            "en": "en",
            "EN": "en",
            "pt-br": "pt-BR",
            "zh-TW": "zh-TW",
            " ru ": "ru",
            "": "",
            "  ": "",
        }
        for raw, expected in cases.items():
            self.assert_valid("language", raw, expected)

    def test_invalid(self):
        invalid = [
            "english",
            "e",
            "eng",
            "en-",
            "-US",
            "en_US",
            "en-USA",
            "en-U",
            "en-US-x",
            "e1",
            "en US",
            "\u00f1e",
            "\u017fe",
            "en-\u212a\u212a",
        ]
        for raw in invalid:
            self.assert_invalid("language", raw)


class SourceRefTests(FieldTestCase):
    def test_trim_preserves_case_and_inner_spaces(self):
        cases = {
            " fixture:A b  C ": "fixture:A b  C",
            "<unsafe>&amp;": "<unsafe>&amp;",
            "https://example.test/x#y": "https://example.test/x#y",
        }
        for raw, expected in cases.items():
            self.assert_valid("source_ref", raw, expected)

    def test_length(self):
        self.assert_valid("source_ref", "x", "x")
        self.assert_valid("source_ref", "x" * 200, "x" * 200)
        self.assert_valid("source_ref", " " * 100 + "x" * 200 + " " * 100, "x" * 200)
        for raw in ["", "   ", "x" * 201]:
            self.assert_invalid("source_ref", raw)


class RowSchemaAndCodeOrderTests(unittest.TestCase):
    def analyze_one(self, raw):
        return analyze_rows([raw], scope=SCOPE)["rows"][0]

    def test_all_six_codes_in_field_order(self):
        row = self.analyze_one(dict.fromkeys(FIELD_CODES))
        self.assertEqual(row["codes"], list(FIELD_CODES.values()))

    def test_codes_follow_field_order_not_key_order(self):
        raw = {
            "source_ref": "",
            "language": "english",
            "country_code": "DK",
            "website_url": "",
            "contact_email": "bad",
            "company_name": "Ok",
        }
        row = self.analyze_one(raw)
        self.assertEqual(row["codes"], ["INVALID_CONTACT_EMAIL", "INVALID_LANGUAGE", "INVALID_SOURCE_REF"])

    def test_schema_violations_skip_field_checks(self):
        broken = dict(VALID_ROW, company_name=None)
        cases = [
            None,
            1,
            "row",
            [],
            ["company_name"],
            {},
            {key: value for key, value in broken.items() if key != "source_ref"},
            dict(broken, extra="x"),
            {("Company_name" if key == "company_name" else key): value for key, value in VALID_ROW.items()},
            {(1 if key == "company_name" else key): value for key, value in VALID_ROW.items()},
            collections.OrderedDict(VALID_ROW),
        ]
        for raw in cases:
            with self.subTest(raw=repr(raw)[:80]):
                row = self.analyze_one(raw)
                self.assertEqual((row["status"], row["codes"]), ("REJECTED", ["INVALID_ROW_SCHEMA"]))
                self.assertIsNone(row["normalized"])
                self.assertIsNone(row["duplicate_of_row"])


if __name__ == "__main__":
    unittest.main()
