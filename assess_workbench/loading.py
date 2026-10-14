"""load_rows: decode and parse a JSON or CSV document into raw rows (CONTRACT.md, section 5)."""

import csv
import io
import json
import sys
import threading
from typing import Any, Final, NoReturn

from .contract import FIELDS, MAX_INPUT_BYTES, MAX_ROWS
from .errors import (
    INPUT_TOO_LARGE,
    INVALID_DATA,
    INVALID_DOCUMENT,
    INVALID_ENCODING,
    INVALID_FORMAT,
    TOO_MANY_ROWS,
    WorkbenchError,
)

_FORMATS: Final = frozenset({"json", "csv"})
_FIELD_SET: Final = frozenset(FIELDS)
# csv.field_size_limit is process-wide state; serialize our temporary change of it.
_CSV_FIELD_LIMIT_LOCK: Final = threading.Lock()
# int() never applies sys.set_int_max_str_digits() to a literal of at most this many digits: it is the smallest
# non-zero value the setting accepts (640 in CPython 3.12).
_INT_CHUNK_DIGITS: Final = sys.int_info.str_digits_check_threshold


def load(data: object, data_format: object) -> list[Any]:
    """Check data, format, size, encoding, syntax and row count, in this order."""
    if type(data) is not bytes:
        raise WorkbenchError(INVALID_DATA)
    if type(data_format) is not str or data_format not in _FORMATS:
        raise WorkbenchError(INVALID_FORMAT)
    if len(data) > MAX_INPUT_BYTES:
        raise WorkbenchError(INPUT_TOO_LARGE)
    text = _decode(data)
    rows = _parse_json(text) if data_format == "json" else _parse_csv(text)
    if len(rows) > MAX_ROWS:
        raise WorkbenchError(TOO_MANY_ROWS)
    return rows


def _decode(data: bytes) -> str:
    """Strict UTF-8; a single leading BOM is accepted and removed."""
    try:
        text: str | None = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = None  # the decode error holds the raw bytes, so raise outside the handler
    if text is None:
        raise WorkbenchError(INVALID_ENCODING)
    return text


class _RejectedJson(ValueError):
    """Raised by the parser hooks; carries no input."""


def _object_without_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    obj = dict(pairs)
    if len(obj) != len(pairs):
        raise _RejectedJson
    return obj


def _reject_constant(_name: str) -> NoReturn:
    raise _RejectedJson


def _exact_int(literal: str) -> int:
    """Value of a JSON integer literal under any sys.set_int_max_str_digits() setting, which is left unchanged.

    The default parse_int, int(), rejects literals longer than that process-wide setting, so the same document would
    load or fail depending on the interpreter. Chunks short enough to be exempt are converted with int() and merged
    pairwise by arithmetic, which keeps the cost close to that of int() without the limit (CP1 A6, revised in R2).
    """
    negative = literal.startswith("-")
    digits = literal[1:] if negative else literal
    if len(digits) <= _INT_CHUNK_DIGITS:
        return int(literal)
    # Most significant chunk first; every other chunk has exactly `width` digits.
    width = _INT_CHUNK_DIGITS
    head = len(digits) % width or width
    values = [int(digits[:head])] + [int(digits[start : start + width]) for start in range(head, len(digits), width)]
    scale = 10**width
    while len(values) > 1:
        # Merge neighbours from the least significant end, so a leftover chunk is the most significant one.
        odd = len(values) % 2
        pairs = zip(values[odd::2], values[odd + 1 :: 2], strict=True)
        values = values[:odd] + [high * scale + low for high, low in pairs]
        scale *= scale
    return -values[0] if negative else values[0]


def _parse_json(text: str) -> list[Any]:
    try:
        document: Any = json.loads(
            text,
            object_pairs_hook=_object_without_duplicate_keys,
            parse_constant=_reject_constant,
            parse_int=_exact_int,
        )
    except (ValueError, RecursionError):
        document = None  # JSONDecodeError.doc holds the whole input, so raise outside the handler
    if type(document) is not list:
        raise WorkbenchError(INVALID_DOCUMENT)
    return document


def _parse_csv(text: str) -> list[Any]:
    records = _read_csv_records(text)
    if not records:
        raise WorkbenchError(INVALID_DOCUMENT)
    header, *body = records
    if len(header) != len(FIELDS) or set(header) != _FIELD_SET:
        raise WorkbenchError(INVALID_DOCUMENT)
    position = {name: index for index, name in enumerate(header)}
    rows: list[Any] = []
    for record in body:
        if len(record) != len(FIELDS):  # also rejects the empty record [] of a blank line
            raise WorkbenchError(INVALID_DOCUMENT)
        rows.append({field: record[position[field]] for field in FIELDS})
    return rows


def _read_csv_records(text: str) -> list[list[str]]:
    with _CSV_FIELD_LIMIT_LOCK:
        previous_limit = csv.field_size_limit()
        # No field of an accepted document can be longer than the document itself.
        csv.field_size_limit(MAX_INPUT_BYTES)
        try:
            records = _read_all_records(text)
        finally:
            csv.field_size_limit(previous_limit)
    if records is None:
        raise WorkbenchError(INVALID_DOCUMENT)
    return records


def _read_all_records(text: str) -> list[list[str]] | None:
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=",", quotechar='"', doublequote=True, strict=True)
    try:
        return list(reader)
    except csv.Error:
        return None  # csv.Error messages may quote the input; the caller raises a code-only error
