"""Candidate tests: CLI behaviour, exit codes and filesystem safety (CONTRACT.md 7; CP1 A9, A13, A16)."""

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
DIR_FD = os.open in os.supports_dir_fd and os.listdir in os.supports_fd


def run_cli(*args, timeout=120):
    command = [sys.executable, "-B", "-m", "assess_workbench", *map(str, args)]
    return subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=timeout)


def arguments(input_path, out_dir, data_format="json", client="synthetic-client", campaign="synthetic-campaign"):
    return [
        "--input",
        input_path,
        "--format",
        data_format,
        "--client-id",
        client,
        "--campaign-id",
        campaign,
        "--out-dir",
        out_dir,
    ]


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

    def run_main(self, argv):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = cli.main([str(item) for item in argv])
        return code, stdout.getvalue(), stderr.getvalue()


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

    def test_out_dir_with_trailing_slashes(self):
        for suffix in ("/", "//"):
            with self.subTest(suffix=suffix):
                out = self.tmp / f"out{len(suffix)}"
                self.assert_success(run_cli(*arguments(FIX / "leads.json", f"{out}{suffix}")))
                self.assertEqual((out / "report.json").read_bytes(), EXPECTED_JSON)


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

    def test_keyboard_interrupt_is_not_swallowed(self):
        with (
            mock.patch("assess_workbench.cli.load_rows", side_effect=KeyboardInterrupt),
            self.assertRaises(KeyboardInterrupt),
        ):
            self.run_main(arguments(FIX / "leads.json", self.tmp / "out"))
        self.assertFalse((self.tmp / "out").exists())


@unittest.skipUnless(POSIX and DIR_FD, "needs dir_fd and O_NOFOLLOW")
class DirectorySwapTests(CliTestCase):
    """Another process replaces a directory in the create/open window (LIMITATIONS.md A16).

    The CLI pins the parent by descriptor and creates and opens out-dir relative to it, so it cannot be redirected to
    a substituted parent, and refuses (IO_ERROR) if after writing the path no longer resolves to the pinned parent
    and the directory it created. The owner/mode/empty checks are defence-in-depth, not a proof of identity. These
    tests swap directories in that window, in process, the way a same-user process could; protection against another
    user comes from refusing an untrusted-writable parent (ParentTrustTests). R5; docs/R5_REWORK.md.
    """

    def swap_created_out_dir(self, out, replace):
        """Patch os.mkdir so that, right after the real (parent-relative) creation of out-dir, `replace` swaps it.

        The CLI creates out-dir relative to the pinned parent; `out` is that same directory by path, so the swap
        removes it and lets `replace` (os.rename/os.symlink only — never mkdir, which the mock intercepts) put
        something else there, as a same-user process could."""
        real_mkdir = os.mkdir

        def mkdir_then_replace(path, *args, **kwargs):
            real_mkdir(path, *args, **kwargs)  # create out-dir relative to the pinned parent descriptor
            os.rmdir(out)  # the same directory, addressed by path
            replace(out)

        return mock.patch("assess_workbench.cli.os.mkdir", side_effect=mkdir_then_replace)

    def test_parent_renamed_and_substituted_after_pin_is_not_reported_as_created(self):
        # Reviewer's R5 reproduction: after out-dir is created, rename the parent to "moved" and drop a prepared
        # "spare" (holding an empty "out") in its place. The reports must not land in the spare and success must not
        # be claimed. The parent is pinned by descriptor, so the reports go to the directory this run created (under
        # "moved"); the final parent samestat then sees the path no longer resolves to the pinned parent -> IO_ERROR.
        parent = self.tmp / "parent"
        parent.mkdir(mode=0o700)
        moved, spare = self.tmp / "moved", self.tmp / "spare"
        spare.mkdir(mode=0o700)
        (spare / "out").mkdir(mode=0o700)
        out = parent / "out"
        real_mkdir = os.mkdir

        def mkdir_then_swap_parent(path, *args, **kwargs):
            real_mkdir(path, *args, **kwargs)  # create out relative to the pinned parent descriptor
            os.rename(parent, moved)  # the pinned descriptor now refers to "moved"
            os.rename(spare, parent)  # a prepared spare (with an empty "out") takes the parent path

        with mock.patch("assess_workbench.cli.os.mkdir", side_effect=mkdir_then_swap_parent):
            result = self.run_main(arguments(FIX / "leads.json", out))
        self.assertEqual(result, (2, "", "ERROR IO_ERROR\n"))
        self.assertEqual(list((parent / "out").iterdir()), [])  # the substitute received nothing
        self.assertEqual(sorted(p.name for p in (moved / "out").iterdir()), ["report.html", "report.json"])

    def test_symlink_swapped_in_as_out_dir_is_not_followed(self):
        # out-dir is opened relative to the pinned parent with the bare name and O_NOFOLLOW, so a trailing slash on
        # the argument cannot make the kernel follow a swapped-in symlink.
        for suffix in ("", "/", "//"):
            with self.subTest(suffix=suffix):
                victim = self.tmp / f"victim{len(suffix)}"
                victim.mkdir(mode=0o700)
                out = self.tmp / f"out{len(suffix)}"
                with self.swap_created_out_dir(out, lambda path, victim=victim: os.symlink(victim, path)):
                    result = self.run_main(arguments(FIX / "leads.json", f"{out}{suffix}"))
                self.assertEqual(result, (2, "", "ERROR IO_ERROR\n"))
                self.assertEqual(list(victim.iterdir()), [])
                self.assertTrue(out.is_symlink())

    def test_populated_directory_swapped_in_receives_nothing(self):
        substitute = self.tmp / "substitute"
        substitute.mkdir(mode=0o700)  # owner-only, so it is the non-empty check alone that rejects it
        (substitute / "keep.txt").write_bytes(b"keep")
        out = self.tmp / "out"
        with self.swap_created_out_dir(out, lambda path: os.rename(substitute, path)):
            result = self.run_main(arguments(FIX / "leads.json", out))
        self.assertEqual(result, (2, "", "ERROR IO_ERROR\n"))
        self.assertEqual(snapshot(out), {"keep.txt": b"keep"})

    def test_group_or_world_accessible_directory_swapped_in_is_refused(self):
        # Defence-in-depth: a substitute left readable by group/other is refused before any report is written.
        substitute = self.tmp / "substitute"
        substitute.mkdir()
        substitute.chmod(0o755)
        out = self.tmp / "out"
        with self.swap_created_out_dir(out, lambda path: os.rename(substitute, path)):
            result = self.run_main(arguments(FIX / "leads.json", out))
        self.assertEqual(result, (2, "", "ERROR IO_ERROR\n"))
        self.assertEqual(list(out.iterdir()), [])

    def test_same_user_identical_substitute_in_trusted_parent_is_the_only_residual(self):
        # A16, pinned on purpose with a real rename of a pre-existing directory. The parent (self.tmp) is owner-only,
        # so no OTHER user could rename into it; this models the same-user/root case, inside the caller's own trust
        # domain. The property checks cannot tell this substitute apart from the one mkdir() made — which is why they
        # are not relied on as proof. Nothing is overwritten; out-dir ends up with the two reports.
        substitute = self.tmp / "substitute"
        substitute.mkdir(mode=0o700)
        identity = (substitute.stat().st_dev, substitute.stat().st_ino)
        out = self.tmp / "out"
        with self.swap_created_out_dir(out, lambda path: os.rename(substitute, path)):
            result = self.run_main(arguments(FIX / "leads.json", out))
        self.assertEqual(result, (0, "REPORT_CREATED\n", ""))
        self.assertEqual((out.stat().st_dev, out.stat().st_ino), identity)
        self.assertEqual(sorted(snapshot(out)), ["report.html", "report.json"])
        self.assertEqual((out / "report.json").read_bytes(), EXPECTED_JSON)

    def test_directory_replaced_after_it_was_opened_is_not_reported_as_created(self):
        out, moved = self.tmp / "out", self.tmp / "moved"
        real_open = os.open

        def replace_before_first_report(path, flags, *args, **kwargs):
            if os.fspath(path) == "report.json":  # the directory itself is already open at this point
                os.rename(out, moved)
                os.mkdir(out)
            return real_open(path, flags, *args, **kwargs)

        with mock.patch("assess_workbench.cli.os.open", side_effect=replace_before_first_report):
            result = self.run_main(arguments(FIX / "leads.json", out))
        self.assertEqual(result, (2, "", "ERROR IO_ERROR\n"))
        self.assertEqual(list(out.iterdir()), [])
        self.assertEqual(sorted(snapshot(moved)), ["report.html", "report.json"])


@unittest.skipUnless(POSIX and DIR_FD, "needs dir_fd and O_NOFOLLOW")
class ParentTrustTests(CliTestCase):
    """The reports may only be written when no untrusted user can rename a directory into the out-dir path.

    Property checks on the opened directory (owner/mode/empty) cannot prove it is the one this run created: a process
    with write rights on the parent can rename an already owner-only, empty directory into place. So the parent is
    pinned and checked BEFORE out-dir is created, and must be trusted — owned by this user or root and either not
    writable by group/other or carrying the sticky bit. Under that condition no other user can place or replace the
    out-dir entry; otherwise the CLI fails with IO_ERROR before out-dir is even created. This is the proposed
    operating condition in docs/R5_REWORK.md (not yet agreed with the reviewer).
    """

    def test_untrusted_writable_parent_fails_before_creating_out_dir(self):
        parent = self.tmp / "shared"
        parent.mkdir()
        parent.chmod(0o777)  # writable by group/other, no sticky bit: another user could substitute the out-dir
        self.addCleanup(parent.chmod, 0o700)
        out = parent / "out"
        result = self.run_main(arguments(FIX / "leads.json", out))
        self.assertEqual(result, (2, "", "ERROR IO_ERROR\n"))
        self.assertFalse(out.exists())  # refused before creating out-dir: nothing created in the untrusted parent

    def test_sticky_world_writable_parent_is_trusted(self):
        parent = self.tmp / "tmplike"
        parent.mkdir()
        parent.chmod(0o1777)  # world-writable but sticky, like /tmp: non-owners cannot rename our entry
        self.addCleanup(parent.chmod, 0o700)
        out = parent / "out"
        self.assertEqual(self.run_main(arguments(FIX / "leads.json", out)), (0, "REPORT_CREATED\n", ""))
        self.assertEqual((out / "report.json").read_bytes(), EXPECTED_JSON)

    def test_owner_only_parent_is_trusted(self):
        out = self.tmp / "out"  # self.tmp is a mkdtemp directory: owner-only, owned by us
        self.assertEqual(self.run_main(arguments(FIX / "leads.json", out)), (0, "REPORT_CREATED\n", ""))
        self.assertEqual((out / "report.json").read_bytes(), EXPECTED_JSON)


if __name__ == "__main__":
    unittest.main()
