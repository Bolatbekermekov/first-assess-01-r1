"""Command line interface (CONTRACT.md, section 7); the only module that touches the filesystem."""

import argparse
import json
import os
import stat
import sys
from collections.abc import Mapping, Sequence
from typing import Final

from .api import WorkbenchError, analyze_rows, load_rows, render_html
from .contract import MAX_INPUT_BYTES, SCOPE_SCHEMA_VERSION, Report

IO_ERROR: Final = "IO_ERROR"
OUTPUT_EXISTS: Final = "OUTPUT_EXISTS"
EXIT_SUCCESS: Final = 0
EXIT_FAILURE: Final = 2

_DIRECTORY_FLAGS: Final = (
    os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
)
_NEW_FILE_FLAGS: Final = (
    os.O_WRONLY
    | os.O_CREAT
    | os.O_EXCL
    | getattr(os, "O_NOFOLLOW", 0)
    | getattr(os, "O_CLOEXEC", 0)
    | getattr(os, "O_BINARY", 0)
)
# Creating and inspecting relative to a directory descriptor needs mkdir/open/stat with dir_fd and listdir(fd).
_DIRECTORY_FD_SUPPORTED: Final = (
    os.mkdir in os.supports_dir_fd
    and os.open in os.supports_dir_fd
    and os.stat in os.supports_dir_fd
    and os.listdir in os.supports_fd
)
# out-dir is created owner-only: the reports hold contact data. The closed mode is also used as a defence-in-depth
# signal (a substitute left accessible to group/other is refused); it is not treated as proof of the directory.
_NEW_DIRECTORY_MODE: Final = 0o700


class _ForeignDirectoryError(OSError):
    """out-dir names a directory that already has entries, or no longer names the one that received the reports."""


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return the process exit code."""
    arguments = _parse_arguments(argv)
    try:
        payload = _read_input(arguments.input)
    except OSError:
        return _fail(IO_ERROR)
    try:
        report = analyze_rows(load_rows(payload, format=arguments.format), scope=_scope(arguments))
        documents = {"report.json": _report_json(report), "report.html": render_html(report).encode("utf-8")}
    except WorkbenchError as error:
        return _fail(error.code)
    try:
        _create_and_write(arguments.out_dir, documents)
    except FileExistsError:  # any existing path, including a (dangling) symlink, or a lost mkdir race
        return _fail(OUTPUT_EXISTS)
    except OSError:
        return _fail(IO_ERROR)
    sys.stdout.write("REPORT_CREATED\n")
    return EXIT_SUCCESS


def _parse_arguments(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m assess_workbench",
        description="Validate a synthetic lead list and write report.json and report.html into a new directory.",
        allow_abbrev=False,
    )
    parser.add_argument("--input", required=True, metavar="FILE", help="JSON or CSV document to read")
    parser.add_argument("--format", required=True, metavar="json|csv", help="input format")
    parser.add_argument("--client-id", required=True, metavar="ID", help="local client identifier")
    parser.add_argument("--campaign-id", required=True, metavar="ID", help="local campaign identifier")
    parser.add_argument("--out-dir", required=True, metavar="NEW_DIRECTORY", help="directory to create")
    return parser.parse_args(argv)


def _read_input(path: str) -> bytes:
    # One byte past the limit is enough for load_rows to report INPUT_TOO_LARGE.
    with open(path, "rb") as stream:
        return stream.read(MAX_INPUT_BYTES + 1)


def _scope(arguments: argparse.Namespace) -> dict[str, str]:
    return {
        "schema_version": SCOPE_SCHEMA_VERSION,
        "client_id": arguments.client_id,
        "campaign_id": arguments.campaign_id,
    }


def _report_json(report: Report) -> bytes:
    return (json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _create_and_write(directory: str, documents: Mapping[str, bytes]) -> None:
    """Create out-dir and write the reports, pinning the parent first so the path cannot be redirected under us.

    POSIX cannot prove that a directory opened by name is the one this run created (mkdir returns no handle; there is
    no renameat2(RENAME_NOREPLACE) or directory O_TMPFILE in the standard library). So the parent is opened, pinned by
    descriptor and checked for trust BEFORE out-dir is created, and out-dir is then created and written relative to
    that descriptor — never by a path that could be re-resolved to a substituted parent. A parent that untrusted
    users could write to cannot be made safe and gives IO_ERROR before anything is created. After writing, success is
    claimed only if out-dir is still the directory we created and the parent path still resolves to the pinned parent
    (samestat); otherwise IO_ERROR. The owner/mode/empty check is defence-in-depth, not a proof of identity. The
    trusted-parent requirement is a proposed operating condition (docs/R5_REWORK.md), pending the reviewer's decision.
    """
    if not _DIRECTORY_FD_SUPPORTED:  # e.g. Windows: exclusive creation by full path, without the parent pinning below
        os.mkdir(directory, _NEW_DIRECTORY_MODE)
        for name, content in documents.items():
            _write_new_file(os.path.join(directory, name), content, dir_fd=None)
        return
    # A trailing slash would let the kernel resolve a final symlink, so strip it: the last component is the out-dir.
    parent_path, name = os.path.split(directory.rstrip("/"))
    parent_path = parent_path or "."
    parent_fd = os.open(parent_path, _DIRECTORY_FLAGS)
    try:
        if not _parent_is_trusted(parent_fd):
            raise _ForeignDirectoryError  # untrusted users could substitute out-dir here: refuse before creating it
        os.mkdir(name, _NEW_DIRECTORY_MODE, dir_fd=parent_fd)  # FileExistsError -> OUTPUT_EXISTS; relative to parent
        dir_fd = os.open(name, _DIRECTORY_FLAGS, dir_fd=parent_fd)
        try:
            if not _is_own_empty_directory(dir_fd):
                raise _ForeignDirectoryError
            for file_name, content in documents.items():
                _write_new_file(file_name, content, dir_fd=dir_fd)
            out_dir_is_ours = os.path.samestat(os.fstat(dir_fd), os.lstat(name, dir_fd=parent_fd))
            parent_unchanged = os.path.samestat(os.fstat(parent_fd), os.stat(parent_path))
            if not (out_dir_is_ours and parent_unchanged):
                raise _ForeignDirectoryError  # the path was redirected after we pinned the parent: do not claim success
        finally:
            os.close(dir_fd)
    finally:
        os.close(parent_fd)


def _parent_is_trusted(parent_fd: int) -> bool:
    """Whether no untrusted user can rename an entry into the out-dir's parent directory.

    True only if the parent is owned by this user or root and is either not writable by group/other or carries the
    sticky bit. A sticky directory (like /tmp) lets only an entry's own owner rename or remove it, so another user
    cannot replace the out-dir we create; a directory not writable by group/other cannot be changed by them at all.
    Ancestors above the immediate parent are assumed trusted — see the operating-condition request in
    docs/R4_REWORK.md.
    """
    status = os.fstat(parent_fd)
    if status.st_uid not in (0, os.geteuid()):
        return False
    return bool(status.st_mode & stat.S_ISVTX) or not status.st_mode & 0o022


def _is_own_empty_directory(dir_fd: int) -> bool:
    """Defence-in-depth check that the open directory is owned by us, closed to group/other and empty.

    This does not prove the directory is the one mkdir() created: a process with write rights on the parent can
    rename an already owner-only, empty directory into place and pass every check. It only rejects opportunistic
    swaps and same-user mistakes; protection against another user comes from _parent_is_trusted.
    """
    status = os.fstat(dir_fd)
    return status.st_uid == os.geteuid() and not stat.S_IMODE(status.st_mode) & 0o077 and not os.listdir(dir_fd)


def _write_new_file(path: str, content: bytes, *, dir_fd: int | None) -> None:
    descriptor = os.open(path, _NEW_FILE_FLAGS, 0o666, dir_fd=dir_fd)
    with open(descriptor, "wb") as stream:
        stream.write(content)


def _fail(code: str) -> int:
    sys.stderr.write(f"ERROR {code}\n")
    return EXIT_FAILURE
