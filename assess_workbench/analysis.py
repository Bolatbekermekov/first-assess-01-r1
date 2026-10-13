"""analyze_rows: scope and row-list checks, row validation, grouping and report assembly (CONTRACT.md 1-4)."""

import re
from collections import Counter
from typing import Final

from .contract import (
    CONFLICT,
    DUPLICATE,
    MAX_ROWS,
    REJECTED,
    REPORT_SCHEMA_VERSION,
    SCOPE_KEYS,
    SCOPE_SCHEMA_VERSION,
    UNIQUE,
    NormalizedRow,
    Report,
    ReportRow,
    Scope,
    Summary,
)
from .errors import INVALID_ROWS, INVALID_SCOPE, TOO_MANY_ROWS, WorkbenchError
from .fields import check_row
from .grouping import Classification, classify

_SCOPE_KEY_SET: Final = frozenset(SCOPE_KEYS)
_SCOPE_ID: Final = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", re.ASCII)


def analyze(rows: object, scope: object) -> Report:
    """Build a new report; the inputs are never modified or referenced by the result."""
    checked_scope = _check_scope(scope)
    if type(rows) is not list:
        raise WorkbenchError(INVALID_ROWS)
    if len(rows) > MAX_ROWS:
        raise WorkbenchError(TOO_MANY_ROWS)

    checks = [check_row(row) for row in rows]
    classifications = classify(
        (row_number, check.normalized)
        for row_number, check in enumerate(checks, start=1)
        if check.normalized is not None
    )
    report_rows: list[ReportRow] = []
    for row_number, check in enumerate(checks, start=1):
        if check.normalized is None:
            report_rows.append(_rejected_row(row_number, check.codes))
        else:
            report_rows.append(_classified_row(row_number, check.normalized, classifications[row_number]))
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "scope": checked_scope,
        "summary": _summarize(report_rows),
        "rows": report_rows,
    }


def _check_scope(scope: object) -> Scope:
    if (
        type(scope) is dict
        and scope.keys() == _SCOPE_KEY_SET
        and type(scope["schema_version"]) is str
        and scope["schema_version"] == SCOPE_SCHEMA_VERSION
        and _is_scope_id(scope["client_id"])
        and _is_scope_id(scope["campaign_id"])
    ):
        return {
            "schema_version": SCOPE_SCHEMA_VERSION,
            "client_id": scope["client_id"],
            "campaign_id": scope["campaign_id"],
        }
    raise WorkbenchError(INVALID_SCOPE)


def _is_scope_id(value: object) -> bool:
    return type(value) is str and _SCOPE_ID.fullmatch(value) is not None


def _rejected_row(row_number: int, codes: tuple[str, ...]) -> ReportRow:
    return {
        "row_number": row_number,
        "status": REJECTED,
        "codes": list(codes),
        "normalized": None,
        "duplicate_of_row": None,
    }


def _classified_row(row_number: int, normalized: NormalizedRow, classification: Classification) -> ReportRow:
    return {
        "row_number": row_number,
        "status": classification.status,
        "codes": [classification.code],
        "normalized": normalized,
        "duplicate_of_row": classification.duplicate_of_row,
    }


def _summarize(rows: list[ReportRow]) -> Summary:
    counts = Counter(row["status"] for row in rows)
    return {
        "total": len(rows),
        "unique": counts[UNIQUE],
        "duplicate": counts[DUPLICATE],
        "conflict": counts[CONFLICT],
        "rejected": counts[REJECTED],
    }
