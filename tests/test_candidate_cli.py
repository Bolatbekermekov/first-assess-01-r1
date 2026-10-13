"""Candidate tests: CLI behaviour, exit codes and filesystem safety (CONTRACT.md 7; CP1 A9, A13)."""

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from assess_workbench import cli
from assess_workbench.api import render_html

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "fixtures"
EXPECTED = json.loads((FIX / "expected_report.json").read_text(encoding="utf-8"))
EXPECTED_JSON = (json.dumps(EXPECTED, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
POSIX = os.name == "posix"
IS_ROOT = POSIX and os.geteuid() == 0
DIR_FD = os.open in os.supports_dir_fd


def run_cli(*args, timeout=120):
    command = [sys.executable, "-B", "-m", "assess_workbench", *map(str, args)]
    return subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=timeout)


def arguments(input_path, out_dir, data_format="json", client="synthetic-client", campaign="synthetic-campaign"):
    return ["--input", input_path, "--format", data_format, "--client-id", client, "--campaign-id", campaign,
            "--out-dir", out_dir]


def snapshot(path):
    if path.is_file():
        return {path.name: path.read_bytes()}
    return {item.relative_to(path).as_posix(): item.read_bytes() for item in sorted(path.rglob("*")) if item.is_file()}


class CliTestCase(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.tmp = Path(temporary.name)

    def assert_failure(self, result, code):
        self.assertEqual((result.returncode, result.stdout, result.stderr), (2, "", f"ERROR {code}\n"))

    def assert_success(self, result):
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "REPORT_CREATED\n", ""))

    def copy_fixture(self, name, target_name=None):
        target = self.tmp / (target_name or name)
        target.write_bytes((FIX / name).read_bytes())
        return target


class SuccessTests(CliTestCase):
    def test_json_and_csv_produce_the_same_report_files(self):
        for data_format in ("json", "csv"):
            with self.subTest(data_format):
                out = self.tmp / f"out-{data_format}"
                self.assert_success(run_cli(*arguments(FIX / f"leads.{data_format}", out, data_format)))
                self.assertEqual(sorted(item.name for item in out.iterdir()), ["report.html", "report.json"])
                self.assertEqual((out / "report.json").read_bytes(), EXPECTED_JSON)
                html_bytes = (out / "report.html").read_bytes()
                self.assertEqual(html_bytes, render_html(EXPECTED).encode("utf-8"))
                self.assertFalse(html_bytes.startswith(b"\xef\xbb\xbf"))

    def test_bom_crlf_quoted_header_spreadsheet_export(self):
        header, rest = (FIX / "leads.csv").read_bytes().replace(b"\n", b"\r\n").split(b"\r\n", 1)
        quoted_header = b",".join(b'"' + name + b'"' for name in header.split(b","))
        source = self.tmp / "export.csv"
        source.write_bytes(b"\xef\xbb\xbf" + quoted_header + b"\r\n" + rest)
        out = self.tmp / "out"
        self.assert_success(run_cli(*arguments(source, out, "csv")))
        self.assertEqual((out / "report.json").read_bytes(), EXPECTED_JSON)

    def test_unicode_and_spaces_in_paths(self):
        folder = self.tmp / "входные данные"
        folder.mkdir()
        source = folder / "лиды 2026.json"
        source.write_bytes((FIX / "leads.json").read_bytes())
        out = self.tmp / "отчёт 2026"
        self.assert_success(run_cli(*arguments(source, out)))
        self.assertEqual((out / "report.json").read_bytes(), EXPECTED_JSON)

    def test_input_file_is_not_modified_and_nothing_else_is_created(self):
        source = self.copy_fixture("leads.json")
        before = (source.read_bytes(), source.stat().st_mtime_ns)
        self.assert_success(run_cli(*arguments(source, self.tmp / "out")))
        self.assertEqual((source.read_bytes(), source.stat().st_mtime_ns), before)
        self.assertEqual(sorted(item.name for item in self.tmp.iterdir()), ["leads.json", "out"])


class OutputExistsTests(CliTestCase):
    def test_existing_directory_is_left_untouched(self):
        out = self.tmp / "out"
        out.mkdir()
        (out / "keep.txt").write_text("keep", encoding="utf-8")
        self.assert_failure(run_cli(*arguments(FIX / "leads.json", out)), "OUTPUT_EXISTS")
        self.assertEqual(snapshot(out), {"keep.txt": b"keep"})

    def test_existing_file_is_left_untouched(self):
        out = self.tmp / "out"
        out.write_bytes(b"keep")
        self.assert_failure(run_cli(*arguments(FIX / "leads.json", out)), "OUTPUT_EXISTS")
        self.assertEqual(out.read_bytes(), b"keep")

    def test_input_path_used_as_output_path(self):
        source = self.copy_fixture("leads.json")
        self.assert_failure(run_cli(*arguments(source, source)), "OUTPUT_EXISTS")
        self.assertEqual(source.read_bytes(), (FIX / "leads.json").read_bytes())

    @unittest.skipUnless(POSIX, "symlink semantics are POSIX-specific")
    def test_symlink_to_a_directory_is_not_followed(self):
        target = self.tmp / "target"
        target.mkdir()
        link = self.tmp / "link"
        link.symlink_to(target, target_is_directory=True)
        self.assert_failure(run_cli(*arguments(FIX / "leads.json", link)), "OUTPUT_EXISTS")
        self.assertTrue(link.is_symlink())
        self.assertEqual(list(target.iterdir()), [])

    @unittest.skipUnless(POSIX, "symlink semantics are POSIX-specific")
    def test_dangling_symlink_is_not_followed(self):
        link = self.tmp / "dangling"
        link.symlink_to(self.tmp / "nowhere")
        self.assert_failure(run_cli(*arguments(FIX / "leads.json", link)), "OUTPUT_EXISTS")
        self.assertTrue(link.is_symlink())
        self.assertFalse((self.tmp / "nowhere").exists())


class IoErrorTests(CliTestCase):
    def test_missing_input(self):
        self.assert_failure(run_cli(*arguments(self.tmp / "missing.json", self.tmp / "out")), "IO_ERROR")
        self.assertFalse((self.tmp / "out").exists())

    def test_input_is_a_directory(self):
        self.assert_failure(run_cli(*arguments(self.tmp, self.tmp / "out")), "IO_ERROR")
        self.assertFalse((self.tmp / "out").exists())

    @unittest.skipIf(not POSIX or IS_ROOT, "permission bits are not enforced here")
    def test_unreadable_input(self):
        source = self.copy_fixture("leads.json")
        source.chmod(0)
        self.addCleanup(source.chmod, 0o600)
        self.assert_failure(run_cli(*arguments(source, self.tmp / "out")), "IO_ERROR")
        self.assertFalse((self.tmp / "out").exists())

    def test_missing_parent(self):
        self.assert_failure(run_cli(*arguments(FIX / "leads.json", self.tmp / "missing" / "out")), "IO_ERROR")
        self.assertFalse((self.tmp / "missing").exists())

    def test_parent_is_a_file(self):
        parent = self.tmp / "file"
        parent.write_bytes(b"keep")
        self.assert_failure(run_cli(*arguments(FIX / "leads.json", parent / "out")), "IO_ERROR")
        self.assertEqual(parent.read_bytes(), b"keep")

    @unittest.skipIf(not POSIX or IS_ROOT, "permission bits are not enforced here")
    def test_parent_without_write_permission(self):
        parent = self.tmp / "read-only"
        parent.mkdir()
        parent.chmod(0o555)
        self.addCleanup(parent.chmod, 0o755)
        self.assert_failure(run_cli(*arguments(FIX / "leads.json", parent / "out")), "IO_ERROR")
        self.assertEqual(list(parent.iterdir()), [])

    def test_empty_out_dir_argument(self):
        self.assert_failure(run_cli(*arguments(FIX / "leads.json", "")), "IO_ERROR")  # CP1 A13

    @unittest.skipUnless(os.path.exists("/dev/zero"), "needs /dev/zero")
    def test_endless_input_is_read_only_up_to_the_limit(self):
        result = run_cli(*arguments("/dev/zero", self.tmp / "out"), timeout=60)
        self.assert_failure(result, "INPUT_TOO_LARGE")
        self.assertFalse((self.tmp / "out").exists())


class InputErrorTests(CliTestCase):
    def test_input_errors_create_nothing_and_win_over_an_existing_output(self):
        existing = self.tmp / "existing"
        existing.mkdir()
        cases = {
            "INVALID_DOCUMENT": ("bad.json", b"SECRET_SENTINEL_RAW", "json"),
            "INVALID_ENCODING": ("bad.csv", b"\xff\xfe", "csv"),
            "TOO_MANY_ROWS": ("many.json", json.dumps([None] * 10_001).encode(), "json"),
            "INPUT_TOO_LARGE": ("big.json", b" " * 10_485_761, "json"),
        }
        for code, (name, content, data_format) in cases.items():
            with self.subTest(code):
                source = self.tmp / name
                source.write_bytes(content)
                out = self.tmp / f"out-{code}"
                result = run_cli(*arguments(source, out, data_format))
                self.assert_failure(result, code)
                self.assertNotIn("SECRET_SENTINEL", result.stdout + result.stderr)
                self.assertFalse(out.exists())
                self.assert_failure(run_cli(*arguments(source, existing, data_format)), code)
        self.assertEqual(list(existing.iterdir()), [])

    def test_missing_input_wins_over_an_existing_output(self):
        existing = self.tmp / "existing"
        existing.mkdir()
        self.assert_failure(run_cli(*arguments(self.tmp / "missing.json", existing)), "IO_ERROR")

    def test_invalid_scope_and_format_values_are_not_echoed(self):
        result = run_cli(*arguments(FIX / "leads.json", self.tmp / "out", client="SECRET<b>"))
        self.assert_failure(result, "INVALID_SCOPE")
        result = run_cli(*arguments(FIX / "leads.json", self.tmp / "out", data_format="SECRET-xml"))
        self.assert_failure(result, "INVALID_FORMAT")  # CP1 A9
        self.assertFalse((self.tmp / "out").exists())


class ArgumentTests(CliTestCase):
    def test_missing_arguments_are_reported_by_argparse(self):
        result = run_cli("--input", FIX / "leads.json")
        self.assertEqual((result.returncode, result.stdout), (2, ""))
        self.assertIn("usage:", result.stderr)

    def test_abbreviated_options_are_rejected(self):
        args = arguments(FIX / "leads.json", self.tmp / "out")
        args[0] = "--inp"
        result = run_cli(*args)
        self.assertEqual((result.returncode, result.stdout), (2, ""))
        self.assertFalse((self.tmp / "out").exists())


class InProcessTests(CliTestCase):
    def run_main(self, argv):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = cli.main([str(item) for item in argv])
        return code, stdout.getvalue(), stderr.getvalue()

    def test_successful_run(self):
        out = self.tmp / "out"
        self.assertEqual(self.run_main(arguments(FIX / "leads.json", out)), (0, "REPORT_CREATED\n", ""))
        self.assertEqual((out / "report.json").read_bytes(), EXPECTED_JSON)

    def test_write_failure_after_mkdir_is_an_io_error(self):
        real_open = os.open

        def failing_open(path, flags, *args, **kwargs):
            if os.fspath(path).endswith("report.html"):
                raise OSError(28, "No space left on device")
            return real_open(path, flags, *args, **kwargs)

        out = self.tmp / "out"
        with mock.patch("assess_workbench.cli.os.open", side_effect=failing_open):
            result = self.run_main(arguments(FIX / "leads.json", out))
        self.assertEqual(result, (2, "", "ERROR IO_ERROR\n"))
        self.assertEqual(sorted(item.name for item in out.iterdir()), ["report.json"])

    def test_losing_the_mkdir_race_is_output_exists(self):
        with mock.patch("assess_workbench.cli.os.mkdir", side_effect=FileExistsError):
            result = self.run_main(arguments(FIX / "leads.json", self.tmp / "out"))
        self.assertEqual(result, (2, "", "ERROR OUTPUT_EXISTS\n"))

    @unittest.skipUnless(POSIX and DIR_FD, "needs dir_fd and O_NOFOLLOW")
    def test_directory_swapped_for_a_symlink_after_mkdir_is_not_followed(self):
        victim = self.tmp / "victim"
        victim.mkdir()
        real_mkdir = os.mkdir

        def mkdir_then_swap(path, *args, **kwargs):
            real_mkdir(path, *args, **kwargs)
            os.rmdir(path)
            os.symlink(victim, path)

        with mock.patch("assess_workbench.cli.os.mkdir", side_effect=mkdir_then_swap):
            result = self.run_main(arguments(FIX / "leads.json", self.tmp / "out"))
        self.assertEqual(result, (2, "", "ERROR IO_ERROR\n"))
        self.assertEqual(list(victim.iterdir()), [])

    def test_keyboard_interrupt_is_not_swallowed(self):
        with mock.patch("assess_workbench.cli.load_rows", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.run_main(arguments(FIX / "leads.json", self.tmp / "out"))
        self.assertFalse((self.tmp / "out").exists())


if __name__ == "__main__":
    unittest.main()
