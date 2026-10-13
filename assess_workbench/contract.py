"""Constants and report types fixed by CONTRACT.md."""

from types import MappingProxyType
from typing import Final, TypedDict

SCOPE_SCHEMA_VERSION: Final = "ASSESS_SCOPE_V1"
REPORT_SCHEMA_VERSION: Final = "ASSESS_LEAD_REPORT_V1"
SCOPE_KEYS: Final = ("schema_version", "client_id", "campaign_id")

# Row fields in the order in which they are validated and reported.
FIELDS: Final = ("company_name", "contact_email", "website_url", "country_code", "language", "source_ref")

MAX_ROWS: Final = 10_000
MAX_INPUT_BYTES: Final = 10_485_760
MAX_RAW_FIELD_LENGTH: Final = 4096

UNIQUE: Final = "UNIQUE"
DUPLICATE: Final = "DUPLICATE"
CONFLICT: Final = "CONFLICT"
REJECTED: Final = "REJECTED"

VALID_RECORD: Final = "VALID_RECORD"
EXACT_DUPLICATE: Final = "EXACT_DUPLICATE"
EMAIL_METADATA_CONFLICT: Final = "EMAIL_METADATA_CONFLICT"
INVALID_ROW_SCHEMA: Final = "INVALID_ROW_SCHEMA"
FIELD_ERROR_CODES: Final = MappingProxyType(
    {
        "company_name": "INVALID_COMPANY_NAME",
        "contact_email": "INVALID_CONTACT_EMAIL",
        "website_url": "INVALID_WEBSITE_URL",
        "country_code": "INVALID_COUNTRY_CODE",
        "language": "INVALID_LANGUAGE",
        "source_ref": "INVALID_SOURCE_REF",
    }
)


class Scope(TypedDict):
    schema_version: str
    client_id: str
    campaign_id: str


class NormalizedRow(TypedDict):
    company_name: str
    contact_email: str
    website_url: str
    country_code: str
    language: str
    source_ref: str


class ReportRow(TypedDict):
    row_number: int
    status: str
    codes: list[str]
    normalized: NormalizedRow | None
    duplicate_of_row: int | None


class Summary(TypedDict):
    total: int
    unique: int
    duplicate: int
    conflict: int
    rejected: int


class Report(TypedDict):
    schema_version: str
    scope: Scope
    summary: Summary
    rows: list[ReportRow]
