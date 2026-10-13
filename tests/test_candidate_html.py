"""Candidate tests: render_html completeness, escaping and safety (CONTRACT.md 6; CP1 A15)."""

import copy
import html
import json
import unittest
from html.parser import HTMLParser
from pathlib import Path

from assess_workbench.api import analyze_rows, render_html

ROOT = Path(__file__).resolve().parents[1]
SCOPE = json.loads((ROOT / "fixtures" / "scope.json").read_text(encoding="utf-8"))
EXPECTED = json.loads((ROOT / "fixtures" / "expected_report.json").read_text(encoding="utf-8"))
FIELDS = ("company_name", "contact_email", "website_url", "country_code", "language", "source_ref")
ROW = {
    "company_name": "Example Labs",
    "contact_email": "person@example.test",
    "website_url": "",
    "country_code": "DK",
    "language": "en",
    "source_ref": "candidate:baseline",
}
HOSTILE = "<img src=x onerror=alert(1)> & \"double\" 'single' </td></tr>"
ALLOWED_TAGS = {"html", "head", "meta", "title", "style", "body", "main", "header", "section", "h1", "h2", "p", "dl",
                "dt", "dd", "table", "thead", "tbody", "tr", "th", "td", "code", "span", "ul", "li"}
ALLOWED_ATTRIBUTES = {
    ("html", "lang"): {"ru"},
    ("meta", "charset"): {"utf-8"},
    ("meta", "http-equiv"): {"Content-Security-Policy"},
    ("meta", "name"): {"viewport"},
    ("meta", "content"): {"default-src 'none'; style-src 'unsafe-inline'", "width=device-width, initial-scale=1"},
    ("th", "scope"): {"col"},
    ("td", "colspan"): {"6"},
}
ALLOWED_CLASSES = {"muted", "scope", "summary", "rows", "num", "value", "empty", "no-data", "codes", "explain",
                   "status", "status-unique", "status-duplicate", "status-conflict", "status-rejected",
                   "status-unknown", "empty-set", "legend"}


class DocumentModel(HTMLParser):
    """Tags, attributes, visible text and the cell texts of every table row of a document."""

    def __init__(self, document):
        super().__init__(convert_charrefs=True)
        self.start_tags, self.attributes, self.texts, self.rows = [], [], [], []
        self._cell = None
        self._in_style = False
        self.feed(document)
        self.close()

    def handle_starttag(self, tag, attrs):
        self.start_tags.append(tag)
        self.attributes.extend((tag, name, value) for name, value in attrs)
        if tag == "tr":
            self.rows.append([])
        elif tag in ("td", "th"):
            self._cell = []
        elif tag == "style":
            self._in_style = True

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cell is not None:
            self.rows[-1].append("".join(self._cell))
            self._cell = None
        elif tag == "style":
            self._in_style = False

    def handle_data(self, data):
        if self._in_style:
            return
        self.texts.append(data)
        if self._cell is not None:
            self._cell.append(data)

    def report_rows(self, count):
        start = next(index for index, cells in enumerate(self.rows) if cells and cells[0] == "№")
        return self.rows[start + 1 : start + 1 + count]


def mixed_report():
    rows = [
        dict(ROW, company_name="C" * 200, website_url="https://example.test/" + "p" * 2027, source_ref="a  b   c"),
        dict(ROW, contact_email="dup@example.test", country_code="", language=""),
        dict(ROW, contact_email="dup@example.test", country_code="", language="", source_ref="other"),
        dict(ROW, contact_email="conflict@example.test"),
        dict(ROW, contact_email="conflict@example.test", company_name="Different"),
        None,
        dict(ROW, contact_email="bad", website_url="ftp://x"),
        dict(ROW, contact_email="hostile@example.test", company_name=HOSTILE, source_ref=HOSTILE,
             website_url="https://example.test/?q=\"><script>alert(1)</script>"),
    ]
    return analyze_rows(rows, scope=SCOPE)


class HtmlTests(unittest.TestCase):
    def test_document_skeleton(self):
        document = render_html(EXPECTED)
        model = DocumentModel(document)
        self.assertTrue(document.startswith("<!DOCTYPE html>"))
        for tag in ("html", "head", "title", "style", "body"):
            self.assertEqual(model.start_tags.count(tag), 1, tag)
        self.assertIn(("meta", "charset", "utf-8"), model.attributes)

    def test_only_allowlisted_tags_and_static_attributes(self):
        for report in (EXPECTED, mixed_report(), analyze_rows([], scope=SCOPE)):
            model = DocumentModel(render_html(report))
            self.assertLessEqual(set(model.start_tags), ALLOWED_TAGS)
            for tag, name, value in model.attributes:
                with self.subTest(tag=tag, name=name, value=value):
                    if name == "class":
                        self.assertLessEqual(set(value.split()), ALLOWED_CLASSES)
                    else:
                        self.assertIn(value, ALLOWED_ATTRIBUTES.get((tag, name), set()))

    def test_template_contains_no_active_content_or_resource_references(self):
        document = render_html(analyze_rows([ROW], scope=SCOPE)).lower()
        for marker in ("<script", "<iframe", "<form", "<link", "<img", "<a ", "<object", "<embed", "href", "src=",
                       "url(", "@import", "javascript:", "http:", "https:"):
            self.assertNotIn(marker, document)

    def test_every_row_and_value_is_shown_in_full(self):
        report = mixed_report()
        model = DocumentModel(render_html(report))
        table_rows = model.report_rows(len(report["rows"]))
        self.assertEqual(len(table_rows), len(report["rows"]))
        for cells, row in zip(table_rows, report["rows"], strict=True):
            with self.subTest(row=row["row_number"]):
                self.assertEqual(cells[0], str(row["row_number"]))
                self.assertEqual(cells[1], row["status"])
                for code in row["codes"]:
                    self.assertIn(code, cells[2])
                if row["normalized"] is None:
                    self.assertEqual(len(cells), 5)
                    self.assertIn("ряд отклонён", cells[3])
                else:
                    self.assertEqual(cells[3:9], [row["normalized"][field] for field in FIELDS])
                expected_duplicate = "—" if row["duplicate_of_row"] is None else str(row["duplicate_of_row"])
                self.assertEqual(cells[-1], expected_duplicate)

    def test_scope_and_summary_are_visible(self):
        report = mixed_report()
        text = "".join(DocumentModel(render_html(report)).texts)
        for value in report["scope"].values():
            self.assertIn(value, text)
        summary_row = next(cells for cells in DocumentModel(render_html(report)).rows if cells[:1] == ["8"])
        self.assertEqual(summary_row, [str(report["summary"][key]) for key in
                                       ("total", "unique", "duplicate", "conflict", "rejected")])

    def test_rejected_rows_show_reasons_but_never_raw_input(self):
        secret = "SECRET-SENTINEL-77"
        rows = [dict(ROW, company_name=secret + "\x01"), {"company_name": secret}, secret]
        document = render_html(analyze_rows(rows, scope=SCOPE))
        self.assertNotIn(secret, document)
        for code in ("INVALID_COMPANY_NAME", "INVALID_ROW_SCHEMA"):
            self.assertIn(code, document)

    def test_empty_report_is_explicit(self):
        document = render_html(analyze_rows([], scope=SCOPE))
        self.assertIn("Набор пуст", document)
        self.assertFalse(any(cells[:1] == ["№"] for cells in DocumentModel(document).rows))

    def test_text_is_escaped_with_html_escape_quote_true(self):
        document = render_html(mixed_report())
        self.assertNotIn("<img", document)
        self.assertNotIn("<script", document.lower())
        self.assertIn(html.escape(HOSTILE, quote=True), document)
        self.assertIn(html.escape("https://example.test/?q=\"><script>alert(1)</script>", quote=True), document)

    def test_values_from_a_crafted_report_are_escaped(self):
        crafted = copy.deepcopy(EXPECTED)  # CP1 A15: no re-validation, still escaped
        crafted["scope"]["client_id"] = "<b>client</b>"
        crafted["rows"][0]["status"] = "<i>NEW</i>"
        crafted["rows"][0]["codes"] = ["<u>CODE</u>"]
        document = render_html(crafted)
        for raw in ("<b>client</b>", "<i>NEW</i>", "<u>CODE</u>"):
            self.assertNotIn(raw, document)
            self.assertIn(html.escape(raw, quote=True), document)
        self.assertIn(("tr", "class", "status-unknown"), DocumentModel(document).attributes)

    def test_rendering_is_deterministic_and_does_not_mutate_the_report(self):
        report = copy.deepcopy(EXPECTED)
        first = render_html(report)
        self.assertEqual(report, EXPECTED)
        self.assertEqual(render_html(copy.deepcopy(EXPECTED)), first)

    def test_internal_whitespace_is_kept_for_display(self):
        document = render_html(analyze_rows([dict(ROW, source_ref="a  b   c")], scope=SCOPE))
        self.assertIn("a  b   c", "".join(DocumentModel(document).texts))
        self.assertIn("white-space: pre-wrap", document)


if __name__ == "__main__":
    unittest.main()
