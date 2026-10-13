"""Exact-email duplicate and conflict classification (CONTRACT.md, section 3)."""

from collections.abc import Iterable
from dataclasses import dataclass

from .contract import CONFLICT, DUPLICATE, EMAIL_METADATA_CONFLICT, EXACT_DUPLICATE, UNIQUE, VALID_RECORD, NormalizedRow

MetadataKey = tuple[str, str, str, str]


@dataclass(frozen=True, slots=True)
class Classification:
    status: str
    code: str
    duplicate_of_row: int | None


def metadata_key(row: NormalizedRow) -> MetadataKey:
    """What rows sharing an email must agree on; source_ref is deliberately not part of it."""
    return (row["company_name"].casefold(), row["website_url"], row["country_code"], row["language"])


def classify(valid_rows: Iterable[tuple[int, NormalizedRow]]) -> dict[int, Classification]:
    """Classify valid rows, given as (row_number, normalized) in input order, by exact normalized email."""
    groups: dict[str, list[tuple[int, MetadataKey]]] = {}
    for row_number, row in valid_rows:
        groups.setdefault(row["contact_email"], []).append((row_number, metadata_key(row)))

    result: dict[int, Classification] = {}
    for members in groups.values():
        if len({key for _, key in members}) > 1:
            for row_number, _ in members:
                result[row_number] = Classification(CONFLICT, EMAIL_METADATA_CONFLICT, None)
            continue
        first_row_number = members[0][0]
        result[first_row_number] = Classification(UNIQUE, VALID_RECORD, None)
        for row_number, _ in members[1:]:
            result[row_number] = Classification(DUPLICATE, EXACT_DUPLICATE, first_row_number)
    return result
