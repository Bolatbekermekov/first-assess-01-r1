"""Exact-email duplicate and conflict classification (CONTRACT.md, section 3). Interim version: Task 3."""

from collections.abc import Iterable
from dataclasses import dataclass

from .contract import UNIQUE, VALID_RECORD, NormalizedRow


@dataclass(frozen=True, slots=True)
class Classification:
    status: str
    code: str
    duplicate_of_row: int | None


def classify(valid_rows: Iterable[tuple[int, NormalizedRow]]) -> dict[int, Classification]:
    return {row_number: Classification(UNIQUE, VALID_RECORD, None) for row_number, _ in valid_rows}
