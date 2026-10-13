"""Public API of the assessment module (CONTRACT.md, section "API").

The three functions are pure computations: they never open files and never use the network.
"""

from typing import Any

from .analysis import analyze
from .contract import Report
from .errors import WorkbenchError
from .html_report import render
from .loading import load

__all__ = ["WorkbenchError", "analyze_rows", "load_rows", "render_html"]


# The keyword-only parameter `format` shadows the builtin on purpose: its name is fixed by the contract.
def load_rows(data: bytes, *, format: str) -> list[Any]:
    """Decode and parse a JSON array or CSV document into raw rows (CONTRACT.md, section 5)."""
    return load(data, format)


def analyze_rows(rows: list[Any], *, scope: dict[str, Any]) -> Report:
    """Validate, normalize and classify rows into a new report (CONTRACT.md, sections 1-4)."""
    return analyze(rows, scope)


def render_html(report: Report) -> str:
    """Render a report produced by analyze_rows as a standalone HTML document (CONTRACT.md, section 6)."""
    return render(report)
