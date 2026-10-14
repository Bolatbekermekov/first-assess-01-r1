"""Dev-only: prove the candidate tests have teeth by injecting known defects one at a time.

Each mutation replaces one snippet in a module, runs the named test files and expects a failure; the original
source is always restored. Usage: python dev/mutation_smoke.py
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MUTATIONS = [
    ("duplicate points to the previous row instead of the first", "grouping.py",
     "Classification(DUPLICATE, EXACT_DUPLICATE, first_row_number)",
     "Classification(DUPLICATE, EXACT_DUPLICATE, row_number - 1)", ["grouping", "properties"]),
    ("a late metadata difference is ignored", "grouping.py",
     "if len({key for _, key in members}) > 1:", "if len({key for _, key in members[:2]}) > 1:",
     ["grouping", "properties"]),
    ("source_ref becomes part of the metadata key", "grouping.py",
     'row["country_code"], row["language"])', 'row["country_code"], row["language"], row["source_ref"])',
     ["grouping", "properties"]),
    ("raw length limit measured after strip", "fields.py",
     "len(value) <= MAX_RAW_FIELD_LENGTH", "len(value.strip()) <= MAX_RAW_FIELD_LENGTH", ["fields"]),
    ("empty fragment no longer rejected", "fields.py",
     'or "#" in url  # urlsplit reports an empty fragment exactly like a missing one', "or False", ["fields"]),
    ("email local part limit dropped", "fields.py",
     "len(local_part) > _MAX_EMAIL_LOCAL_PART", "len(local_part) > 10_000", ["fields"]),
    ("company name compared without NFC", "fields.py",
     'unicodedata.normalize("NFC", value).split()', "value.split()", ["fields", "grouping"]),
    ("codes returned as a shared tuple", "analysis.py", '"codes": list(codes),', '"codes": codes,', ["report"]),
    ("csv.field_size_limit not restored", "loading.py",
     "            csv.field_size_limit(previous_limit)", "            pass", ["loading"]),
    ("decode error chained to WorkbenchError", "loading.py",
     "        text = None  # the decode error holds the raw bytes, so raise outside the handler",
     "        raise WorkbenchError(INVALID_ENCODING)", ["loading"]),
    ("blank CSV records skipped", "loading.py",
     "        if len(record) != len(FIELDS):  # also rejects the empty record [] of a blank line",
     "        if not record:\n            continue\n        if len(record) != len(FIELDS):", ["loading"]),
    ("field size limit raised at import time", "loading.py",
     "_CSV_FIELD_LIMIT_LOCK: Final = threading.Lock()",
     "_CSV_FIELD_LIMIT_LOCK: Final = threading.Lock()\ncsv.field_size_limit(MAX_INPUT_BYTES)", ["isolation"]),
    ("JSON integers parsed by the default int() again (R1 A6)", "loading.py",
     "parse_int=_exact_int,", "", ["loading", "environment"]),
    ("integer chunks longer than the digit-limit exemption", "loading.py",
     "_INT_CHUNK_DIGITS: Final = sys.int_info.str_digits_check_threshold",
     "_INT_CHUNK_DIGITS: Final = sys.int_info.default_max_str_digits", ["loading"]),
    ("JSON parsed by the recursive pure-Python scanner (depth follows sys.setrecursionlimit)", "loading.py",
     "import json\n", "import json\nimport json.scanner\n\njson.scanner.make_scanner = json.scanner.py_make_scanner\n",
     ["loading"]),
    ("quotes left unescaped in HTML", "html_report.py",
     "return html.escape(str(value), quote=True)", "return html.escape(str(value), quote=False)", ["html"]),
    ("output directory created with makedirs(exist_ok=True)", "cli.py",
     "os.mkdir(arguments.out_dir, _NEW_DIRECTORY_MODE)", "os.makedirs(arguments.out_dir, exist_ok=True)", ["cli"]),
    ("out-dir created accessible to group/other (R3)", "cli.py",
     "_NEW_DIRECTORY_MODE: Final = 0o700", "_NEW_DIRECTORY_MODE: Final = 0o777", ["cli"]),
    ("whole input read without the size cap", "cli.py",
     "return stream.read(MAX_INPUT_BYTES + 1)", "return stream.read()", ["cli"]),
    ("populated directory swapped in after mkdir accepted", "cli.py",
     " and not os.listdir(dir_fd)", "", ["cli"]),
    ("cross-user swap into a foreign-owned directory accepted (R3)", "cli.py",
     "status.st_uid == os.geteuid() and ", "", ["cli"]),
    ("swap keeping a group/other-accessible mode accepted (R3)", "cli.py",
     "not stat.S_IMODE(status.st_mode) & 0o077 and ", "", ["cli"]),
    ("success reported without re-checking what out-dir names", "cli.py",
     "        if not os.path.samestat(os.fstat(dir_fd), os.lstat(path)):\n            raise _ForeignDirectoryError\n",
     "", ["cli"]),
    ("trailing slash kept, so O_NOFOLLOW does not apply", "cli.py",
     'path = directory.rstrip("/")', "path = directory", ["cli"]),
]


def main() -> int:
    survived = 0
    for title, module, old, new, suites in MUTATIONS:
        path = ROOT / "assess_workbench" / module
        original = path.read_text(encoding="utf-8")
        if original.count(old) != 1:
            print(f"SETUP ERROR  {title}: snippet not found exactly once in {module}")
            return 2
        try:
            path.write_text(original.replace(old, new), encoding="utf-8")
            patterns = [f"test_candidate_{suite}.py" for suite in suites]
            failed = any(
                subprocess.run(
                    [sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests", "-p", pattern],
                    cwd=ROOT, capture_output=True, text=True, timeout=900,
                ).returncode != 0
                for pattern in patterns
            )
        finally:
            path.write_text(original, encoding="utf-8")
        survived += not failed
        print(f"{'KILLED  ' if failed else 'SURVIVED'}  {module:15} {title}  (tests: {', '.join(suites)})")
    print(f"{len(MUTATIONS) - survived}/{len(MUTATIONS)} injected defects detected")
    return 1 if survived else 0


if __name__ == "__main__":
    raise SystemExit(main())
