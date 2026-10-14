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
# Working relative to a directory descriptor needs open/stat with dir_fd and listdir(fd); POSIX systems have them.
_DIRECTORY_FD_SUPPORTED: Final = (
    os.open in os.supports_dir_fd and os.stat in os.supports_dir_fd and os.listdir in os.supports_fd
)
# out-dir is created owner-only: the reports hold contact data, and the mode also marks the directory this process
# made. A substitute left accessible to group/other (the mode a careless same-user swap keeps) is then refused.
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
        os.mkdir(arguments.out_dir, _NEW_DIRECTORY_MODE)
    except FileExistsError:  # any existing path, including a (dangling) symlink, or a lost race
        return _fail(OUTPUT_EXISTS)
    except OSError:
        return _fail(IO_ERROR)
    try:
        _write_new_files(arguments.out_dir, documents)
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


def _write_new_files(directory: str, documents: Mapping[str, bytes]) -> None:
    """Write the reports into the directory just made at `directory`, never following or replacing a path.

    mkdir() returns no handle and POSIX offers no atomic "create and open a directory", so the directory is opened
    again by its path. That lookup is a race: a process with write rights on the parent can rename another directory
    into the out-dir name in between. Properties of the opened directory (owner, mode, emptiness) cannot prove it is
    the one this run created — such a substitute can be made to match them — so protection against another user rests
    on the parent. Unless the parent cannot be written by untrusted users (see _parent_is_trusted), substitution
    cannot be ruled out and the reports are not written (IO_ERROR before writing). Under a trusted parent no other
    user can place or replace the out-dir entry. The owner/mode/empty check and the final samestat stay only as
    defence-in-depth against same-user mistakes and a post-open swap; they are not relied on as proof. The
    trusted-parent requirement is a proposed operating condition (docs/R4_REWORK.md), pending the reviewer's decision.
    """
    if not _DIRECTORY_FD_SUPPORTED:  # e.g. Windows: fall back to exclusive creation by full path
        for name, content in documents.items():
            _write_new_file(os.path.join(directory, name), content, dir_fd=None)
        return
    # A trailing slash would make the kernel resolve a final symlink despite O_NOFOLLOW; mkdir() has succeeded, so the
    # path is not made of slashes only. The parent is pinned by descriptor so its entries cannot be swapped after the
    # trust check, and mkdir/open happen relative to it so no parent component can be redirected mid-operation.
    parent, name = os.path.split(directory.rstrip("/"))
    parent_fd = os.open(parent or ".", _DIRECTORY_FLAGS)
    try:
        if not _parent_is_trusted(parent_fd):
            raise _ForeignDirectoryError  # an untrusted user could substitute out-dir: refuse before writing
        dir_fd = os.open(name, _DIRECTORY_FLAGS, dir_fd=parent_fd)
        try:
            if not _is_own_empty_directory(dir_fd):
                raise _ForeignDirectoryError
            for file_name, content in documents.items():
                _write_new_file(file_name, content, dir_fd=dir_fd)
            if not os.path.samestat(os.fstat(dir_fd), os.lstat(name, dir_fd=parent_fd)):
                raise _ForeignDirectoryError
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
