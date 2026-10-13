"""Row validation and normalization (CONTRACT.md, section 2)."""

import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, TypeGuard, cast
from urllib.parse import urlsplit, urlunsplit

from .contract import FIELD_ERROR_CODES, FIELDS, INVALID_ROW_SCHEMA, MAX_RAW_FIELD_LENGTH, NormalizedRow

_FIELD_SET: Final = frozenset(FIELDS)

_MAX_COMPANY_NAME: Final = 200
_MAX_EMAIL: Final = 254
_MAX_EMAIL_LOCAL_PART: Final = 64
_MAX_LABEL: Final = 63
_MAX_URL: Final = 2048
_MAX_HOSTNAME: Final = 253
_MAX_SOURCE_REF: Final = 200

# General rule: NUL and the other C0 controls, DEL, and surrogate code points.
_FORBIDDEN_CHARACTER: Final = re.compile(r"[\x00-\x1f\x7f\ud800-\udfff]")
# The contract's expression verbatim; \x60 is the backtick and \x7c the vertical bar.
_EMAIL: Final = re.compile(
    r"[a-z0-9.!#$%&'*+/=?^_\x60{\x7c}~-]+@[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)+",
    re.ASCII,
)
_HOST_LABEL: Final = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?", re.ASCII)
_COUNTRY_CODE: Final = re.compile(r"[A-Z]{2}", re.ASCII)
_LANGUAGE_TAG: Final = re.compile(r"([A-Za-z]{2})(?:-([A-Za-z]{2}))?", re.ASCII)
_ASCII_WHITESPACE: Final = frozenset(" \t\n\r\x0b\x0c")
_NETLOC_FORBIDDEN: Final = frozenset(":@[]")


@dataclass(frozen=True, slots=True)
class RowCheck:
    """Validation outcome of one input row: its normalized fields, or its error codes in field order."""

    normalized: NormalizedRow | None
    codes: tuple[str, ...]


def check_row(row: object) -> RowCheck:
    """Validate and normalize one row; bad row content never raises."""
    if type(row) is not dict or row.keys() != _FIELD_SET:
        return RowCheck(normalized=None, codes=(INVALID_ROW_SCHEMA,))
    normalized: dict[str, str] = {}
    codes: list[str] = []
    for field in FIELDS:
        value = _normalize(field, row[field])
        if value is None:
            codes.append(FIELD_ERROR_CODES[field])
        else:
            normalized[field] = value
    if codes:
        return RowCheck(normalized=None, codes=tuple(codes))
    return RowCheck(normalized=cast(NormalizedRow, normalized), codes=())


def _normalize(field: str, value: object) -> str | None:
    if not _is_clean_text(value):
        return None
    return _NORMALIZERS[field](value)


def _is_clean_text(value: object) -> TypeGuard[str]:
    """General rule, checked on the raw value before any normalization."""
    return type(value) is str and len(value) <= MAX_RAW_FIELD_LENGTH and _FORBIDDEN_CHARACTER.search(value) is None


def _normalize_company_name(value: str) -> str | None:
    name = " ".join(unicodedata.normalize("NFC", value).split())
    return name if 1 <= len(name) <= _MAX_COMPANY_NAME else None


def _normalize_contact_email(value: str) -> str | None:
    # Every check runs on the normalized value (CP1 decision A1).
    email = value.strip().lower()
    if not email.isascii() or len(email) > _MAX_EMAIL or _EMAIL.fullmatch(email) is None:
        return None
    local_part, _, domain = email.partition("@")
    if (
        len(local_part) > _MAX_EMAIL_LOCAL_PART
        or local_part.startswith(".")
        or local_part.endswith(".")
        or ".." in local_part
        or any(len(label) > _MAX_LABEL for label in domain.split("."))
    ):
        return None
    return email


def _normalize_website_url(value: str) -> str | None:
    url = value.strip()
    if url == "":
        return ""
    if (
        len(url) > _MAX_URL
        or not url.isascii()
        or not _ASCII_WHITESPACE.isdisjoint(url)
        or not url.startswith("https://")
        or "#" in url  # urlsplit reports an empty fragment exactly like a missing one
    ):
        return None
    try:
        parts = urlsplit(url)
    except ValueError:  # e.g. an unbalanced bracket in the netloc
        return None
    if not _NETLOC_FORBIDDEN.isdisjoint(parts.netloc):
        return None
    hostname = parts.hostname
    if hostname is None or not _is_valid_hostname(hostname):
        return None
    return urlunsplit(("https", hostname, parts.path, parts.query, ""))


def _is_valid_hostname(hostname: str) -> bool:
    labels = hostname.split(".")
    return (
        len(hostname) <= _MAX_HOSTNAME
        and len(labels) >= 2
        and all(len(label) <= _MAX_LABEL and _HOST_LABEL.fullmatch(label) is not None for label in labels)
    )


def _normalize_country_code(value: str) -> str | None:
    # The check runs on the normalized value (CP1 decision A2).
    code = value.strip().upper()
    return code if code == "" or _COUNTRY_CODE.fullmatch(code) is not None else None


def _normalize_language(value: str) -> str | None:
    tag = value.strip()
    if tag == "":
        return ""
    match = _LANGUAGE_TAG.fullmatch(tag)
    if match is None:
        return None
    primary, region = match.group(1), match.group(2)
    return primary.lower() if region is None else f"{primary.lower()}-{region.upper()}"


def _normalize_source_ref(value: str) -> str | None:
    reference = value.strip()
    return reference if 1 <= len(reference) <= _MAX_SOURCE_REF else None


_NORMALIZERS: Final[MappingProxyType[str, Callable[[str], str | None]]] = MappingProxyType(
    {
        "company_name": _normalize_company_name,
        "contact_email": _normalize_contact_email,
        "website_url": _normalize_website_url,
        "country_code": _normalize_country_code,
        "language": _normalize_language,
        "source_ref": _normalize_source_ref,
    }
)
