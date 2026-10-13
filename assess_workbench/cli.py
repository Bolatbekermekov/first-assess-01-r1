"""Command line interface (CONTRACT.md, section 7); the only module that touches the filesystem."""

import argparse
import json
import os
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
        os.mkdir(arguments.out_dir)
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
    """Create each file inside the directory this process just made, never following or replacing a path."""
    if os.open not in os.supports_dir_fd:  # e.g. Windows: fall back to exclusive creation by full path
        for name, content in documents.items():
            _write_new_file(os.path.join(directory, name), content, dir_fd=None)
        return
    dir_fd = os.open(directory, _DIRECTORY_FLAGS)
    try:
        for name, content in documents.items():
            _write_new_file(name, content, dir_fd=dir_fd)
    finally:
        os.close(dir_fd)


def _write_new_file(path: str, content: bytes, *, dir_fd: int | None) -> None:
    descriptor = os.open(path, _NEW_FILE_FLAGS, 0o666, dir_fd=dir_fd)
    with open(descriptor, "wb") as stream:
        stream.write(content)


def _fail(code: str) -> int:
    sys.stderr.write(f"ERROR {code}\n")
    return EXIT_FAILURE
