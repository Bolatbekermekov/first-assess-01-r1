"""Error type of the public API (CONTRACT.md, section "API")."""

from typing import Final

INVALID_SCOPE: Final = "INVALID_SCOPE"
INVALID_ROWS: Final = "INVALID_ROWS"
TOO_MANY_ROWS: Final = "TOO_MANY_ROWS"
INVALID_DATA: Final = "INVALID_DATA"
INVALID_FORMAT: Final = "INVALID_FORMAT"
INPUT_TOO_LARGE: Final = "INPUT_TOO_LARGE"
INVALID_ENCODING: Final = "INVALID_ENCODING"
INVALID_DOCUMENT: Final = "INVALID_DOCUMENT"


class WorkbenchError(ValueError):
    """A contract violation identified only by its stable ``code``.

    ``str(error) == error.code`` and the error never carries input values. Raise it outside ``except`` blocks:
    an implicit ``__context__`` would keep the original exception, and with it the raw input, attached.
    """

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)
