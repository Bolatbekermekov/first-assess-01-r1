"""render_html: a standalone, fully escaped HTML view of a report (CONTRACT.md, section 6).

Report values reach the document only through ``_text`` (``html.escape(str(value), quote=True)``) and only as
element content. Every tag and attribute below is a fixed literal: nothing from the report becomes markup, an
attribute, a link or a resource reference.
"""

import html
from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

from .contract import CONFLICT, DUPLICATE, FIELDS, REJECTED, UNIQUE, Report, ReportRow

_STATUS_CLASSES: Final = MappingProxyType(
    {
        UNIQUE: "status-unique",
        DUPLICATE: "status-duplicate",
        CONFLICT: "status-conflict",
        REJECTED: "status-rejected",
    }
)
_UNKNOWN_STATUS_CLASS: Final = "status-unknown"

_STATUS_NOTES: Final = (
    (
        UNIQUE,
        "в текущем наборе нет другого валидного ряда с этим email. Это не подтверждает существование компании, "
        "доставляемость адреса или разрешение на контакт.",
    ),
    (
        DUPLICATE,
        "тот же email и те же метаданные (название без учёта регистра, сайт, страна, язык), что у более раннего "
        "ряда из колонки duplicate_of_row. Поля рядов не сливаются.",
    ),
    (
        CONFLICT,
        "у рядов с этим email различаются метаданные. Автоматического выбора или обогащения нет: все ряды группы "
        "требуют ручного разбора.",
    ),
    (
        REJECTED,
        "ряд не прошёл проверку и исключён из поиска дублей. Исходные значения в отчёт не попадают, только коды "
        "причин.",
    ),
)

_CODE_EXPLANATIONS: Final = MappingProxyType(
    {
        "VALID_RECORD": "все поля прошли проверку",
        "EXACT_DUPLICATE": "точный дубль более раннего ряда",
        "EMAIL_METADATA_CONFLICT": "метаданные расходятся с другими рядами этого email",
        "INVALID_ROW_SCHEMA": "ряд не является объектом ровно с шестью полями контракта",
        "INVALID_COMPANY_NAME": "название: не строка, недопустимые символы или длина вне 1–200 после нормализации",
        "INVALID_CONTACT_EMAIL": "email не проходит синтаксическую ASCII-проверку контракта",
        "INVALID_WEBSITE_URL": "сайт: допускается пусто или адрес со схемой https без учётных данных, порта и "
        "фрагмента",
        "INVALID_COUNTRY_CODE": "код страны: пусто или две латинские буквы",
        "INVALID_LANGUAGE": "язык: пусто, xx или xx-YY латиницей",
        "INVALID_SOURCE_REF": "источник: строка длиной 1–200 после удаления внешних пробелов",
    }
)

_SUMMARY_COLUMNS: Final = (
    ("total", "Всего рядов"),
    ("unique", UNIQUE),
    ("duplicate", DUPLICATE),
    ("conflict", CONFLICT),
    ("rejected", REJECTED),
)
_ROWS_HEAD: Final = (
    '<thead><tr><th scope="col">№</th><th scope="col">Статус</th><th scope="col">Коды причин</th>'
    + "".join(f'<th scope="col"><code>{name}</code></th>' for name in FIELDS)
    + '<th scope="col"><code>duplicate_of_row</code></th></tr></thead>\n'
)
_NO_DATA_CELL: Final = (
    f'<td class="no-data" colspan="{len(FIELDS)}">'
    "Нормализованные значения отсутствуют: ряд отклонён. Исходные данные не показываются.</td>"
)

_CSS: Final = """\
:root {
  color-scheme: light dark;
  --fg: #1f2328; --muted: #59636e; --bg: #ffffff; --line: #d1d9e0; --head: #f6f8fa;
  --unique: #1a7f37; --duplicate: #9a6700; --conflict: #bc4c00; --rejected: #cf222e; --unknown: #59636e;
}
@media (prefers-color-scheme: dark) {
  :root {
    --fg: #e6edf3; --muted: #9198a1; --bg: #0d1117; --line: #3d444d; --head: #151b23;
    --unique: #3fb950; --duplicate: #d29922; --conflict: #db6d28; --rejected: #f85149; --unknown: #9198a1;
  }
}
* { box-sizing: border-box; }
body { margin: 0; color: var(--fg); background: var(--bg);
       font: 14px/1.5 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
main { max-width: 1680px; margin: 0 auto; padding: 24px 16px 48px; }
h1 { font-size: 22px; margin: 0 0 4px; }
h2 { font-size: 17px; margin: 28px 0 10px; }
code { font: 12.5px/1.45 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
.muted { color: var(--muted); }
table { border-collapse: collapse; width: 100%; }
th, td { border: 1px solid var(--line); padding: 6px 8px; text-align: left; vertical-align: top; }
thead th { background: var(--head); }
table.summary { width: auto; }
table.summary td { font-size: 18px; }
dl.scope { display: grid; grid-template-columns: max-content 1fr; gap: 4px 16px; margin: 0; }
dl.scope dd { margin: 0; overflow-wrap: anywhere; }
.num { text-align: right; white-space: nowrap; font-variant-numeric: tabular-nums; }
.value { white-space: pre-wrap; overflow-wrap: anywhere; }
.empty::before { content: "пусто"; color: var(--muted); font-style: italic; }
.no-data { color: var(--muted); font-style: italic; }
ul.codes { margin: 0; padding: 0; list-style: none; }
ul.codes li + li { margin-top: 4px; }
.explain { color: var(--muted); }
.status { font-weight: 600; }
.status-unique .status { color: var(--unique); }
.status-duplicate .status { color: var(--duplicate); }
.status-conflict .status { color: var(--conflict); }
.status-rejected .status { color: var(--rejected); }
.status-unknown .status { color: var(--unknown); }
tr.status-unique > td:first-child { box-shadow: inset 4px 0 var(--unique); }
tr.status-duplicate > td:first-child { box-shadow: inset 4px 0 var(--duplicate); }
tr.status-conflict > td:first-child { box-shadow: inset 4px 0 var(--conflict); }
tr.status-rejected > td:first-child { box-shadow: inset 4px 0 var(--rejected); }
.empty-set { padding: 12px 16px; border: 1px dashed var(--line); }
dl.legend dt { margin-top: 8px; }
dl.legend dd { margin: 2px 0 0; }
@media print {
  main { max-width: none; padding: 0; }
  body { font-size: 11px; }
}
"""


def render(report: Report) -> str:
    """Return the complete document; the same report always yields the same text."""
    return "".join(
        (
            _head(report),
            "<body>\n<main>\n",
            _intro(report),
            _scope_section(report["scope"]),
            _summary_section(report["summary"]),
            _rows_section(report["rows"]),
            _legend_section(),
            "</main>\n</body>\n</html>\n",
        )
    )


def _text(value: object) -> str:
    """The single way report data enters the document."""
    return html.escape(str(value), quote=True)


def _head(report: Report) -> str:
    scope = report["scope"]
    return (
        "<!DOCTYPE html>\n"
        '<html lang="ru">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        "<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; style-src 'unsafe-inline'\">\n"
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>Отчёт проверки лидов — {_text(scope['client_id'])} / {_text(scope['campaign_id'])}</title>\n"
        f"<style>\n{_CSS}</style>\n"
        "</head>\n"
    )


def _intro(report: Report) -> str:
    return (
        "<header>\n"
        "<h1>Отчёт проверки лидов</h1>\n"
        f'<p class="muted">Схема отчёта <code>{_text(report["schema_version"])}</code>. '
        "Синтаксическая валидность не означает, что компания существует, адрес принимает письма "
        "или есть разрешение на контакт.</p>\n"
        "</header>\n"
    )


def _scope_section(scope: Mapping[str, object]) -> str:
    items = "".join(
        f"<dt><code>{name}</code></dt><dd><code>{_text(scope[name])}</code></dd>\n"
        for name in ("schema_version", "client_id", "campaign_id")
    )
    return f'<section>\n<h2>Scope</h2>\n<dl class="scope">\n{items}</dl>\n</section>\n'


def _summary_section(summary: Mapping[str, object]) -> str:
    head = "".join(f'<th scope="col">{label}</th>' for _, label in _SUMMARY_COLUMNS)
    cells = "".join(f'<td class="num">{_text(summary[key])}</td>' for key, _ in _SUMMARY_COLUMNS)
    return (
        "<section>\n<h2>Сводка</h2>\n"
        f'<table class="summary">\n<thead><tr>{head}</tr></thead>\n<tbody><tr>{cells}</tr></tbody>\n</table>\n'
        "</section>\n"
    )


def _rows_section(rows: list[ReportRow]) -> str:
    if not rows:
        content = '<p class="empty-set">Набор пуст: во входных данных нет ни одного ряда.</p>\n'
    else:
        body = "".join(_row(row) for row in rows)
        content = f'<table class="rows">\n{_ROWS_HEAD}<tbody>\n{body}</tbody>\n</table>\n'
    return f"<section>\n<h2>Ряды</h2>\n{content}</section>\n"


def _row(row: ReportRow) -> str:
    status_class = _STATUS_CLASSES.get(row["status"], _UNKNOWN_STATUS_CLASS)
    normalized = row["normalized"]
    if normalized is None:
        values = _NO_DATA_CELL
    else:
        fields: Mapping[str, object] = normalized
        values = "".join(_value_cell(fields[name]) for name in FIELDS)
    duplicate_of = row["duplicate_of_row"]
    duplicate_cell = (
        '<td class="num muted">—</td>' if duplicate_of is None else f'<td class="num">{_text(duplicate_of)}</td>'
    )
    return (
        f'<tr class="{status_class}">'
        f'<td class="num">{_text(row["row_number"])}</td>'
        f'<td><span class="status">{_text(row["status"])}</span></td>'
        f'<td class="codes">{_codes(row["codes"])}</td>'
        f"{values}{duplicate_cell}</tr>\n"
    )


def _value_cell(value: object) -> str:
    text = _text(value)
    # An empty value is marked by CSS only, so the marker can never be mistaken for data.
    return '<td class="value empty"></td>' if text == "" else f'<td class="value">{text}</td>'


def _codes(codes: list[str]) -> str:
    items = []
    for code in codes:
        explanation = _CODE_EXPLANATIONS.get(code)
        note = "" if explanation is None else f' <span class="explain">— {_text(explanation)}</span>'
        items.append(f"<li><code>{_text(code)}</code>{note}</li>")
    return f'<ul class="codes">{"".join(items)}</ul>'


def _legend_section() -> str:
    items = "".join(
        f'<dt class="{_STATUS_CLASSES[status]}"><span class="status">{status}</span></dt><dd>{_text(note)}</dd>\n'
        for status, note in _STATUS_NOTES
    )
    return f'<section>\n<h2>Что означают статусы</h2>\n<dl class="legend">\n{items}</dl>\n</section>\n'
