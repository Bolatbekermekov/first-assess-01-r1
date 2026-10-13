"""Candidate tests: seeded randomized invariants with an independent oracle (CONTRACT.md 2-5)."""

import csv
import io
import json
import random
import time
import unittest
from pathlib import Path

from assess_workbench.api import analyze_rows, load_rows, render_html

ROOT = Path(__file__).resolve().parents[1]
SCOPE = json.loads((ROOT / "fixtures" / "scope.json").read_text(encoding="utf-8"))
SEED = 20261013
FIELDS = ("company_name", "contact_email", "website_url", "country_code", "language", "source_ref")
POOLS = {
    "company_name": ["Alpha Labs", "alpha labs", " ALPHA  LABS ", "Straße", "STRASSE", "Café", "Café",
                     "", "x" * 201, "Tab\tCo", "Line\nBreak", "Ünïcødé", 7, None],
    "contact_email": ["a@example.test", " A@Example.test ", "b@example.test", "b+tag@example.test", "c@example.test",
                      "not-an-email", "a@example", "Kate@example.test", ""],
    "website_url": ["", "https://example.test", "https://example.test/", "https://EXAMPLE.test/",
                    "http://example.test", "https://example.test/#", "   "],
    "country_code": ["", "DK", "dk", "SE", "XXX", "ß"],
    "language": ["", "en", "EN", "en-US", "en-us", "english"],
    "source_ref": ["ref:1", "ref:2", " ref:3 ", "", "r" * 201],
}
STATUS_KEYS = {"UNIQUE": "unique", "DUPLICATE": "duplicate", "CONFLICT": "conflict", "REJECTED": "rejected"}


def random_row(rng):
    roll = rng.random()
    if roll < 0.04:
        return rng.choice([None, 1, "row", [], {}])
    row = {field: rng.choice(POOLS[field]) for field in FIELDS}
    if roll < 0.07:
        row["extra"] = "x"
    elif roll < 0.10:
        del row[rng.choice(FIELDS)]
    return row


def expected_outcomes(report):
    """Independent restatement of CONTRACT.md section 3 over the normalized rows of a report."""
    groups = {}
    for row in report["rows"]:
        if row["normalized"] is not None:
            groups.setdefault(row["normalized"]["contact_email"], []).append(row)
    expected = {}
    for members in groups.values():
        keys = {
            (m["normalized"]["company_name"].casefold(), m["normalized"]["website_url"],
             m["normalized"]["country_code"], m["normalized"]["language"])
            for m in members
        }
        if len(keys) > 1:
            for member in members:
                expected[member["row_number"]] = ("CONFLICT", ["EMAIL_METADATA_CONFLICT"], None)
            continue
        first = members[0]["row_number"]
        expected[first] = ("UNIQUE", ["VALID_RECORD"], None)
        for member in members[1:]:
            expected[member["row_number"]] = ("DUPLICATE", ["EXACT_DUPLICATE"], first)
    return expected


class RandomizedInvariantTests(unittest.TestCase):
    def test_random_batches_follow_the_contract(self):
        rng = random.Random(SEED)
        for batch in range(150):
            rows = [random_row(rng) for _ in range(rng.randint(0, 40))]
            with self.subTest(batch=batch):
                report = analyze_rows(rows, scope=SCOPE)
                statuses = [row["status"] for row in report["rows"]]
                expected_summary = {"total": len(rows)}
                expected_summary.update({key: statuses.count(status) for status, key in STATUS_KEYS.items()})
                self.assertEqual(report["summary"], expected_summary)
                oracle = expected_outcomes(report)
                for row in report["rows"]:
                    outcome = (row["status"], row["codes"], row["duplicate_of_row"])
                    if row["normalized"] is None:
                        self.assertEqual(row["status"], "REJECTED")
                        self.assertIsNone(row["duplicate_of_row"])
                        self.assertTrue(row["codes"])
                    else:
                        self.assertEqual(outcome, oracle[row["row_number"]])
                render_html(report)

    def test_normalization_is_idempotent(self):
        rng = random.Random(SEED + 1)
        for _ in range(400):
            first = analyze_rows([random_row(rng)], scope=SCOPE)["rows"][0]
            if first["normalized"] is None:
                continue
            again = analyze_rows([dict(first["normalized"])], scope=SCOPE)["rows"][0]
            self.assertEqual(again["normalized"], first["normalized"])

    def test_json_and_csv_inputs_are_equivalent(self):
        rng = random.Random(SEED + 2)
        for _ in range(60):
            rows = [row for row in (random_row(rng) for _ in range(rng.randint(0, 25)))
                    if type(row) is dict and set(row) == set(FIELDS) and all(type(v) is str for v in row.values())]
            header = list(FIELDS)
            rng.shuffle(header)
            buffer = io.StringIO()
            writer = csv.writer(buffer, lineterminator=rng.choice(["\n", "\r\n"]))
            writer.writerow(header)
            writer.writerows([[row[name] for name in header] for row in rows])
            from_csv = load_rows(buffer.getvalue().encode("utf-8"), format="csv")
            from_json = load_rows(json.dumps(rows).encode("utf-8"), format="json")
            self.assertEqual(from_csv, from_json)
            self.assertEqual(analyze_rows(from_csv, scope=SCOPE), analyze_rows(from_json, scope=SCOPE))

    def test_permutation_keeps_rejections_and_conflicts(self):
        rng = random.Random(SEED + 3)
        for _ in range(80):
            rows = [random_row(rng) for _ in range(rng.randint(1, 30))]
            order = list(range(len(rows)))
            rng.shuffle(order)
            base = analyze_rows(rows, scope=SCOPE)
            shuffled = analyze_rows([rows[index] for index in order], scope=SCOPE)
            self.assertEqual(base["summary"], shuffled["summary"])
            for new_index, old_index in enumerate(order):
                before, after = base["rows"][old_index], shuffled["rows"][new_index]
                self.assertEqual(before["normalized"], after["normalized"])
                if before["status"] in ("REJECTED", "CONFLICT"):
                    self.assertEqual((before["status"], before["codes"]), (after["status"], after["codes"]))
                else:
                    self.assertIn(after["status"], ("UNIQUE", "DUPLICATE"))

    def test_maximum_row_count_is_processed_quickly(self):
        rows = [
            {"company_name": f"Company {index % 1500}", "contact_email": f"user{index % 2000}@example.test",
             "website_url": "https://example.test/", "country_code": "DK", "language": "en",
             "source_ref": f"ref:{index}"}
            for index in range(10_000)
        ]
        started = time.perf_counter()
        report = analyze_rows(rows, scope=SCOPE)
        render_html(report)
        elapsed = time.perf_counter() - started
        self.assertEqual(report["summary"]["total"], 10_000)
        self.assertLess(elapsed, 30.0)  # generous: guards against quadratic behaviour, not machine speed


if __name__ == "__main__":
    unittest.main()
