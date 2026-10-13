"""Candidate-owned implementation; intentionally absent in the preparation package."""
class WorkbenchError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)

def load_rows(data: bytes, *, format: str) -> list:
    raise NotImplementedError("NOT_IMPLEMENTED")

def analyze_rows(rows: list, *, scope: dict) -> dict:
    raise NotImplementedError("NOT_IMPLEMENTED")

def render_html(report: dict) -> str:
    raise NotImplementedError("NOT_IMPLEMENTED")
