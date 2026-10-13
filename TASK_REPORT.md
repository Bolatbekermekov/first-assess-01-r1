# TASK_REPORT — FIRST-ASSESS-01 R1

| Поле | Значение |
|---|---|
| project_id | `sales-manager-first` |
| task_id | `FIRST-ASSESS-01` |
| revision | `R1` |
| Исполнитель | Bolatbek Yermekov |
| Статус автора | `READY_FOR_REVIEW` — это не независимый PASS; окончательную приёмку проводит проверяющий |
| Дата | 2026-10-13 |

## 1. Итог

- Модуль `assess_workbench` реализован по `CONTRACT.md`:
  - API `WorkbenchError`, `load_rows`, `analyze_rows`, `render_html`;
  - CLI `python -m assess_workbench`.
- Используются только CPython 3.12 и стандартная библиотека. Сеть, текущее время, случайность и окружение на результат не влияют.
- Публичная приёмка `RUN_ACCEPTANCE.py`: `PASS_PUBLIC_ONLY` (12/12) на Linux; на macOS публичный набор тоже проходит 12/12.
- Собственные тесты: 141/141 на Linux (контейнер без сети, не root) и на macOS.
- Статический анализ: `ruff check`, `ruff format --check` и `mypy --strict` — без замечаний.
- Эффективность собственных тестов: в код поочерёдно вносились 15 типичных дефектов, обнаружены все 15.
- Существенные неясности контракта перечислены до реализации в `docs/CP1_DESIGN.md` (A1–A15). Ограничения — в `LIMITATIONS.md`, трассировка требований — в `TEST_MATRIX.md`, предложение декомпозиции — в `DECOMPOSITION_PROPOSAL.md`.
- Ошибок в условии, которые потребовали бы отдельного воспроизведения, не найдено. Найденные места — это неоднозначности (раздел 10 CP1), а не противоречия: по каждой принято явное решение, закреплённое тестом.

## 2. Что реализовано

| Раздел контракта | Реализация |
|---|---|
| API, `WorkbenchError` | `errors.py`: `.code`, `str(error) == code`. Ошибка поднимается вне блоков `except`, поэтому нет `__cause__` и `__context__`, которые хранили бы сырой вход (`UnicodeDecodeError.object`, `JSONDecodeError.doc`) |
| §1 scope и `analyze_rows` | `analysis.py`: проверки в порядке `INVALID_SCOPE` → `INVALID_ROWS` → `TOO_MANY_ROWS`; точные builtin-типы; scope в отчёте — новый `dict` |
| §2 поля | `fields.py`: общее правило на исходном значении (тип `str`, ≤ 4096 code points, без C0/DEL/суррогатов), затем нормализация каждого поля и пределы после неё; не более одного кода на поле, коды в порядке полей |
| §3 группировка | `grouping.py`: валидные ряды группируются по точному email; ключ метаданных — `(casefold(name), url, country, language)`. Хотя бы два разных ключа → вся группа CONFLICT; иначе первый ряд UNIQUE, остальные DUPLICATE со ссылкой на него. O(n) |
| §4 отчёт | `analysis.py`: ровно контрактные ключи и типы (`dict`/`list`/`str`/`int`/`None`); `summary` считает ряды; без сырого входа, времени и случайных ID |
| §5 `load_rows` | `loading.py`: порядок `INVALID_DATA` → `INVALID_FORMAT` → `INPUT_TOO_LARGE` → `INVALID_ENCODING` → `INVALID_DOCUMENT` → `TOO_MANY_ROWS`. JSON: хуки на дубли ключей (на любой глубине) и `NaN`/`Infinity`, перехват `RecursionError`. CSV: `csv.reader(strict=True)`; `field_size_limit` поднимается под замком и восстанавливается |
| §6 `render_html` | `html_report.py`: полный документ со встроенным CSS и CSP `default-src 'none'`. Все значения проходят только через `html.escape(str(v), quote=True)` и попадают в документ только как текст; атрибуты статические. Ничего не обрезается (`pre-wrap`, `overflow-wrap: anywhere`); есть пояснения кодов и статусов, пустой набор показан явно |
| §7 CLI | `cli.py`: порядок аргументы → чтение (`read(limit + 1)`) → load → analyze → render → `mkdir(exist_ok=False)` → запись. Файлы создаются с `O_EXCL \| O_NOFOLLOW` относительно дескриптора только что созданного каталога (`O_DIRECTORY \| O_NOFOLLOW`). Ровно `ERROR <CODE>\n` в stderr и exit 2; `KeyboardInterrupt` не перехватывается |
| §8 независимость | API не открывает файлов и не использует сеть; импорт без побочных эффектов; импортируются только stdlib и собственный пакет |

## 3. Структура решения

```text
assess_workbench/
  __init__.py      докстринг пакета, без побочных эффектов
  __main__.py      python -m assess_workbench -> cli.main()
  api.py           фасад контракта (WorkbenchError, load_rows, analyze_rows, render_html)
  errors.py        WorkbenchError и коды ошибок API
  contract.py      поля, статусы, коды, лимиты, версии схем, TypedDict-схема отчёта
  loading.py       parsing:      bytes -> list
  fields.py        validation:   общее правило и нормализация шести полей
  grouping.py      grouping:     UNIQUE / DUPLICATE / CONFLICT
  analysis.py      scope и сборка отчёта
  html_report.py   presentation: отчёт -> HTML
  cli.py           единственный модуль с файловым вводом-выводом
tests/test_candidate_*.py   8 модулей собственных тестов (unittest), 141 тест
docs/CP1_DESIGN.md          дизайн и решения по неоднозначностям (CP1)
logs/                       фактические журналы запусков; logs/sample_report.{json,html}
evidence/                   вывод RUN_ACCEPTANCE.py
```

Направление зависимостей: `cli → api → {loading, analysis → {fields, grouping}, html_report} → {contract, errors}`. Фреймворков нет; модули — это чистые функции и небольшие неизменяемые `dataclass`.

## 4. Среда

| Среда | Детали | Журнал |
|---|---|---|
| Linux, основная | Docker-образ `python:3.12.13-slim-trixie@sha256:229a2c5bfa27522db7815ea81f9bed70af17ccb9de9fc7ad142b1877b5830d36`, Debian 13, aarch64. CPython 3.12.13, `unicodedata` 15.0.0. uid 1000, сеть отключена (`Network is unreachable`), корневая ФС только для чтения | `logs/01_container_environment.txt` |
| macOS, дополнительная | macOS 26.6.2 (arm64), CPython 3.12.13 | `logs/13_*.txt`, `logs/14_*.txt` |
| Хост | Docker 29.6.1, Docker Compose v5.3.0; инструменты `ruff 0.17.0` и `mypy 2.4.0` — только в dev-контейнере | `logs/00_host.txt` |

На Windows не запускалось (см. `LIMITATIONS.md`).

## 5. Команды и фактические результаты

Команды из `RETURN_INSTRUCTIONS.md` выполнялись из корня пакета внутри Linux-контейнера (`python` = CPython 3.12.13). В первой строке каждого журнала записана точная команда, в заголовке — среда и код выхода.

| Команда | Фактический результат | Журнал |
|---|---|---|
| `python CHECK_PACKAGE.py` | `{"status": "PACKAGE_INPUTS_PASS", "errors": []}`, exit 0 | `logs/02_check_package.txt` |
| `python RUN_ACCEPTANCE.py` | `{"status": "PASS_PUBLIC_ONLY", "exit_code": 0}`, публичных тестов 12, OK | `logs/03_run_acceptance.txt`, `evidence/` |
| `python -m unittest discover -s tests -p "test_candidate_*.py" -v` | `Ran 141 tests`, `OK` (Linux); то же на macOS | `logs/04_candidate_tests.txt`, `logs/13_macos_candidate_tests.txt` |
| `python -m assess_workbench --input fixtures/leads.json --format json --client-id synthetic-client --campaign-id synthetic-campaign --out-dir sample_output` | exit 0, stdout `REPORT_CREATED`, stderr пуст | `logs/05_cli_json.txt` |
| та же команда повторно | exit 2, stdout пуст, stderr `ERROR OUTPUT_EXISTS`; созданные отчёты не изменены | `logs/06_cli_rerun_output_exists.txt` |
| CSV: `--input fixtures/leads.csv --format csv … --out-dir sample_output_csv` | exit 0, `REPORT_CREATED` | `logs/07_cli_csv.txt` |
| `cmp` отчётов JSON- и CSV-запусков | `report.json` и `report.html` побайтно идентичны | `logs/08_cli_json_csv_identical.txt` |
| Ошибочные запуски CLI | `INVALID_SCOPE`, `INVALID_DOCUMENT` (вход с маркером в данных — маркер не выведен), `IO_ERROR`, `INVALID_FORMAT`, `INPUT_TOO_LARGE` для `/dev/zero`. Во всех случаях exit 2, каталог не создан | `logs/09_cli_error_cases.txt` |
| `ruff check` / `ruff format --check` | `All checks passed!` / `19 files already formatted` | `logs/10_*.txt`, `logs/11_*.txt` |
| `mypy --strict` | `Success: no issues found in 11 source files` | `logs/12_mypy_strict.txt` |
| Мутационная проверка тестов | `15/15 injected defects detected` | `logs/15_mutation_smoke.txt` |

`sample_output` и `sample_output_csv` создавались только для демонстрации и удалены после запуска. Копии отчётов лежат в `logs/sample_report.json` и `logs/sample_report.html`. HTML дополнительно проверен визуально в Chrome: все шесть рядов, коды, пояснения и пустые значения видны; `<script>…` отображается как текст; ничего не обрезано.

## 6. Как воспроизвести

Без Docker, любым CPython 3.12, из корня распакованного возврата:

```text
python CHECK_PACKAGE.py
python RUN_ACCEPTANCE.py
python -m unittest discover -s tests -p "test_candidate_*.py" -v
python -m assess_workbench --input fixtures/leads.json --format json --client-id synthetic-client --campaign-id synthetic-campaign --out-dir sample_output
```

Для повторного запуска CLI нужен новый `--out-dir`: перезапись запрещена контрактом.

Проверка `RETURN_MANIFEST.json` (из корня возврата):

```text
python -c "import hashlib, json, pathlib; m = json.loads(pathlib.Path('RETURN_MANIFEST.json').read_text(encoding='utf-8')); bad = [f['path'] for f in m['files'] if hashlib.sha256(pathlib.Path(f['path']).read_bytes()).hexdigest() != f['sha256']]; print('OK', len(m['files'])) if not bad else print('MISMATCH', bad)"
```

Dev-окружение не входит в возврат: `compose.yaml` (песочница без сети и не от root), скрипты сбора журналов, мутационной проверки и упаковки. Причины: `RETURN_INSTRUCTIONS.md` разрешает только перечисленные пути, а `00_READ_FIRST_RU.md` указывает, что Docker не нужен. Продукт от этих файлов не зависит.

## 7. Ход работы по чекпоинтам

- **CP0.** На исходном каркасе: `CHECK_PACKAGE.py` → `PACKAGE_INPUTS_PASS`, `RUN_ACCEPTANCE.py` → `NOT_IMPLEMENTED`, exit 1 — ожидаемое состояние подготовки.
- **CP1.** `docs/CP1_DESIGN.md`: как устроены парсер, нормализация, группировка и отчёт, плюс 15 неоднозначностей с решениями. Всё зафиксировано до изменения поведения; каждый спорный случай предварительно проверен на CPython 3.12.13.
- **CP2.** Реализация через тесты, слой за слоем: поля и отчёт → группировка → парсер → HTML → CLI. Для каждого слоя сначала писался тест и проверялось, что он падает. Затем — рандомизированные инварианты с независимым оракулом, тесты изоляции и мутационная проверка.
- **CP3.** Журналы, документы, `RETURN_MANIFEST.json` и ZIP с одним корнем `FIRST_ASSESS_01_RETURN_R1/`. ZIP проверен распаковкой: хеши совпадают с манифестом, `CHECK_PACKAGE.py` и все тесты проходят в распакованной копии.
