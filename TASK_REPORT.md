# TASK_REPORT — FIRST-ASSESS-01, возврат R5

| Поле | Значение |
|---|---|
| project_id | `sales-manager-first` |
| task_id | `FIRST-ASSESS-01` |
| revision | `R5` — доработка возврата R4 по итогам повторной проверки. Пакет задания — FIRST-ASSESS-01 R1, `BASE_MANIFEST.json` не изменён |
| Исполнитель | Bolatbek Yermekov |
| Статус автора | `READY_FOR_REVIEW` — не независимый PASS. Замечание о записи отчётов **не считаю закрытым** до согласования условия эксплуатации (`docs/R5_REWORK.md`, раздел 4) |
| Дата | 2026-10-15 |

## 1. Что изменено в R5

Повторная проверка R4 нашла блокирующий дефект **порядка операций** и неверный комментарий. Оба справедливы. Полный разбор — `docs/R5_REWORK.md`. История: `docs/R2_REWORK.md` (R1→R2), `docs/R3_REWORK.md` (R2→R3), `docs/R4_REWORK.md` (R3→R4).

### Признанный дефект R4

- `main()` вызывал `os.mkdir(out_dir)` **по полному пути до** закрепления дескриптора родителя. В окне между `mkdir` и открытием родителя подмена родителя приводила к записи в заранее существовавший каталог и ложному `REPORT_CREATED`; созданный этим запуском `moved/out` оставался пустым.
- Комментарий в R4 утверждал, что `mkdir` идёт относительно дескриптора родителя, хотя он шёл по пути. Исправлено — теперь это действительно так.

### Исправление (замечание 2)

- **Порядок.** Весь путь перенесён в `_create_and_write`: родитель открывается дескриптором и **закрепляется до создания** `out-dir`; проверяется его доверенность (`_parent_is_trusted`); затем `out-dir` создаётся и открывается **относительно закреплённого дескриптора**. Повторного разбора пути нет, поэтому подменить родителя «между `mkdir` и открытием» нельзя.
- **Отказ до создания.** Недоверенный родитель (доступен на запись недоверенным пользователям) → `IO_ERROR` **до создания** `out-dir`, ничего не создаётся.
- **Двойная финальная проверка.** Успех заявляется, только если открытый `out-dir` — тот самый, что мы создали (`samestat`), **и** путь родителя всё ещё указывает на закреплённый родитель (`samestat`). Иначе — `IO_ERROR`: путь перенаправили после закрепления.
- **Защита в глубину (не доказательство):** владелец/режим/пустота открытого каталога. POSIX и stdlib не дают доказать тождество открытого каталога созданному.
- **Регрессионный тест точного сценария проверки** (реальные ФС-операции): `DirectorySwapTests.test_parent_renamed_and_substituted_after_pin_is_not_reported_as_created` — нет записи в подставленный каталог, нет сообщения об успехе. Падает на коде R4, проходит на R5 (журналы 17, 18).
- **Контракт не изменён.** Условие эксплуатации вынесено отдельным запросом — `docs/R5_REWORK.md`, раздел 4. До согласования замечание не закрыто. Нормативные файлы байт-в-байт прежние.

## 2. Итог проверок R5

Выполнено / пропущено / не запускалось:

**Выполнено:**

| Проверка | Результат | Журнал |
|---|---|---|
| Комплектность пакета | `PACKAGE_INPUTS_PASS` | 02 |
| Публичная приёмка `RUN_ACCEPTANCE.py` | `PASS_PUBLIC_ONLY`, 12/12 (Linux и macOS) | 03, `evidence/`, 14 |
| Собственные тесты | 155/155 на Linux (контейнер без сети, не root) и на macOS | 04, 13 |
| Сценарий проверки на коде R4 | падает (ложный `REPORT_CREATED`, запись в подставленный каталог); код R4 сверен с его `RETURN_MANIFEST.json`, 11/11 файлов | 17 |
| Те же регрессионные тесты на R5 | OK | 18 |
| Запись в доверенный/недоверенный родитель | out-dir `0700` в доверенном; `IO_ERROR` до создания в недоверенном (out-dir не создан) | 22 |
| Воспроизведение замечания 1 (API/CLI/стоимость) — остаётся зелёным | точное целое, `REJECTED`, отчёты побайтно равны | 19, 20, 21 |
| Статический анализ | `ruff check`, `ruff format --check`, `mypy --strict` без замечаний | 10, 11, 12 |
| Мутационная проверка | 25 внесённых дефектов, обнаружены все 25 (Linux-контейнер) | 15 |

**Пропущено (намеренно, по условиям окружения):**
- Проверки прав под root — тесты прав пропускаются при uid 0; оба прогона шли не от root, поэтому фактически выполнились.
- Ветка без `dir_fd` (Windows) — на всех прогонах не исполнялась.

**Не запускалось:**
- Windows; другие патч-версии CPython 3.12 и версии Unicode; настоящий параллельный процесс для гонки каталога; отображающие владельца ФС (NFS/sshfs/SMB); покомпонентный обход вышележащих каталогов; стоимость длинного целого на другом оборудовании. Подробно — `TEST_MATRIX.md`, разделы «Не проверено» и «Не гарантируется».

Собственных тестов стало 155 (в R4 было 154): в R5 добавлен тест точного сценария проверки (`DirectorySwapTests.test_parent_renamed_and_substituted_after_pin_is_not_reported_as_created`); тесты окна и доверенности родителя переписаны под новый порядок.

Существенные неясности контракта перечислены до реализации в `docs/CP1_DESIGN.md` (A1–A15). В R2 добавлено A16 и пересмотрено A6; в R3–R5 A16 и A14 уточнены. Ограничения — в `LIMITATIONS.md`, трассировка требований — в `TEST_MATRIX.md`, предложение декомпозиции — в `DECOMPOSITION_PROPOSAL.md`.

**Решение по контракту.** Контракт не определяет модель угроз для выходного каталога, а POSIX не даёт доказать тождество открытого каталога созданному. Нормативные файлы не менялись; точная предлагаемая формулировка условия эксплуатации (доверенный родитель) — `docs/R5_REWORK.md`, раздел 4. До её согласования замечание не считаю закрытым.

## 3. Что реализовано

| Раздел контракта | Реализация |
|---|---|
| API, `WorkbenchError` | `errors.py`: `.code`, `str(error) == code`. Ошибка поднимается вне блоков `except`, поэтому нет `__cause__` и `__context__`, которые хранили бы сырой вход (`UnicodeDecodeError.object`, `JSONDecodeError.doc`) |
| §1 scope и `analyze_rows` | `analysis.py`: проверки в порядке `INVALID_SCOPE` → `INVALID_ROWS` → `TOO_MANY_ROWS`; точные builtin-типы; scope в отчёте — новый `dict` |
| §2 поля | `fields.py`: общее правило на исходном значении (тип `str`, ≤ 4096 code points, без C0/DEL/суррогатов), затем нормализация каждого поля и пределы после неё; не более одного кода на поле, коды в порядке полей |
| §3 группировка | `grouping.py`: валидные ряды группируются по точному email; ключ метаданных — `(casefold(name), url, country, language)`. Хотя бы два разных ключа → вся группа CONFLICT; иначе первый ряд UNIQUE, остальные DUPLICATE со ссылкой на него. O(n) |
| §4 отчёт | `analysis.py`: ровно контрактные ключи и типы (`dict`/`list`/`str`/`int`/`None`); `summary` считает ряды; без сырого входа, времени и случайных ID |
| §5 `load_rows` | `loading.py`: порядок `INVALID_DATA` → `INVALID_FORMAT` → `INPUT_TOO_LARGE` → `INVALID_ENCODING` → `INVALID_DOCUMENT` → `TOO_MANY_ROWS`. JSON: хуки на дубли ключей (на любой глубине) и `NaN`/`Infinity`, перехват `RecursionError`; **R2:** хук `parse_int` даёт точное значение целого любой длины независимо от `sys.set_int_max_str_digits`. CSV: `csv.reader(strict=True)`; `field_size_limit` поднимается под замком и восстанавливается |
| §6 `render_html` | `html_report.py`: полный документ со встроенным CSS и CSP `default-src 'none'`. Все значения проходят только через `html.escape(str(v), quote=True)` и попадают в документ только как текст; атрибуты статические. Ничего не обрезается (`pre-wrap`, `overflow-wrap: anywhere`); есть пояснения кодов и статусов, пустой набор показан явно |
| §7 CLI | `cli.py` (`_create_and_write`): порядок аргументы → чтение (`read(limit + 1)`) → load → analyze → render → запись. Родитель открывается `O_DIRECTORY \| O_NOFOLLOW` (без хвостовых `/`) и **закрепляется дескриптором до создания**; проверяется его доверенность (владелец нам/root и не-групп/прочим-записываемый либо sticky), иначе `IO_ERROR` до создания. Затем `mkdir(name, 0o700, dir_fd=parent)` и открытие/запись — **относительно закреплённого дескриптора** (**R5**, A16). Успех — только если после записи `out-dir` тот же (`samestat`) и путь родителя указывает на закреплённый родитель (`samestat`); иначе `IO_ERROR`. Защита в глубину: владелец/режим/пустота. Файлы — `O_EXCL \| O_NOFOLLOW`. Ровно `ERROR <CODE>\n` в stderr и exit 2; `KeyboardInterrupt` не перехватывается |
| §8 независимость | API не открывает файлов и не использует сеть; импорт без побочных эффектов; импортируются только stdlib и собственный пакет |

**Зависимость от окружения.** Используются только CPython 3.12 и стандартная библиотека.

Проверено тестами, что результат не зависит от:
- сети, времени, случайности и предыдущих запусков;
- `sys.set_int_max_str_digits` и `sys.setrecursionlimit`;
- `PYTHONINTMAXSTRDIGITS`, `PYTHONHASHSEED`, локали и UTF-8 mode;
- `csv.field_size_limit` вызывающего.

Остаётся зависимым:
- граница вложенности JSON — от сборки интерпретатора; контракт сам предписывает `RecursionError` → `INVALID_DOCUMENT`;
- Unicode-операции — от версии Python 3.12;
- работа CLI — от состояния файловой системы и umask.

Подробно — `LIMITATIONS.md`, раздел 2.

## 4. Структура решения

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
tests/test_candidate_*.py   9 модулей собственных тестов (unittest), 155 тестов; R2 добавил test_candidate_environment.py, R4 — ParentTrustTests, R5 — тест точного сценария проверки
candidate_fixtures/         sales_leads.csv — собственный синтетический пример: 12 рядов, все четыре статуса
docs/CP1_DESIGN.md          дизайн и решения по неоднозначностям (CP1, исправления R2/R3 помечены)
docs/R2_REWORK.md           разбор замечаний R1 и запрос уточнения контракта
docs/R3_REWORK.md           доработка замечания 2 (owner/mode/0o700) и запрос решения по контракту
docs/R4_REWORK.md           пересмотр защиты каталога (доверенный родитель), исправление заявлений о гарантиях, запрос условия эксплуатации
docs/R5_REWORK.md           исправление порядка (закрепление родителя до создания), тест сценария проверки
logs/                       фактические журналы запусков; отчёты sample_report.* и candidate_example_report.*
evidence/                   вывод RUN_ACCEPTANCE.py
```

Направление зависимостей: `cli → api → {loading, analysis → {fields, grouping}, html_report} → {contract, errors}`. Фреймворков нет; модули — это чистые функции и небольшие неизменяемые `dataclass`.

## 5. Среда

| Среда | Детали | Журнал |
|---|---|---|
| Linux, основная | Docker-образ `python:3.12.13-slim-trixie@sha256:229a2c5bfa27522db7815ea81f9bed70af17ccb9de9fc7ad142b1877b5830d36`, Debian 13, aarch64. CPython 3.12.13, `unicodedata` 15.0.0. uid 1000, сеть отключена (`Network is unreachable`), корневая ФС только для чтения | `logs/01_container_environment.txt` |
| macOS, дополнительная | macOS 26.6.2 (arm64, Apple M4 Pro), CPython 3.12.13 | `logs/13_*.txt`, `logs/14_*.txt` |
| Хост | Docker 29.6.1, Docker Compose v5.3.0; инструменты `ruff 0.17.0` и `mypy 2.4.0` — только в dev-контейнере | `logs/00_host.txt` |

На Windows не запускалось (см. `LIMITATIONS.md`).

## 6. Команды и фактические результаты

Все журналы получены заново 2026-10-14 на коде R2. Команды из `RETURN_INSTRUCTIONS.md` выполнялись из корня пакета внутри Linux-контейнера (`python` = CPython 3.12.13). В первой строке каждого журнала записана точная команда, в заголовке — среда и код выхода.

| Команда | Фактический результат | Журнал |
|---|---|---|
| `python CHECK_PACKAGE.py` | `{"status": "PACKAGE_INPUTS_PASS", "errors": []}`, exit 0 | `logs/02_check_package.txt` |
| `python RUN_ACCEPTANCE.py` | `{"status": "PASS_PUBLIC_ONLY", "exit_code": 0}`, публичных тестов 12, OK | `logs/03_run_acceptance.txt`, `evidence/` |
| `python -m unittest discover -s tests -p "test_candidate_*.py" -v` | `Ran 155 tests`, `OK` (Linux); то же на macOS | `logs/04_candidate_tests.txt`, `logs/13_macos_candidate_tests.txt` |
| `python -m assess_workbench --input fixtures/leads.json --format json --client-id synthetic-client --campaign-id synthetic-campaign --out-dir sample_output` | exit 0, stdout `REPORT_CREATED`, stderr пуст | `logs/05_cli_json.txt` |
| та же команда повторно | exit 2, stdout пуст, stderr `ERROR OUTPUT_EXISTS`; созданные отчёты не изменены | `logs/06_cli_rerun_output_exists.txt` |
| CSV: `--input fixtures/leads.csv --format csv … --out-dir sample_output_csv` | exit 0, `REPORT_CREATED` | `logs/07_cli_csv.txt` |
| `cmp` отчётов JSON- и CSV-запусков | `report.json` и `report.html` побайтно идентичны | `logs/08_cli_json_csv_identical.txt` |
| Ошибочные запуски CLI | `INVALID_SCOPE`, `INVALID_DOCUMENT` (вход с маркером в данных — маркер не выведен), `IO_ERROR`, `INVALID_FORMAT`, `INPUT_TOO_LARGE` для `/dev/zero`. Во всех случаях exit 2, каталог не создан | `logs/09_cli_error_cases.txt` |
| Собственный пример: `--input candidate_fixtures/sales_leads.csv --format csv … --out-dir sample_output_example` | exit 0, `REPORT_CREATED`; 12 рядов: 5 UNIQUE, 1 DUPLICATE, 3 CONFLICT, 3 REJECTED | `logs/16_cli_candidate_example.txt`, `logs/candidate_example_report.{json,html}` |
| `ruff check` / `ruff format --check` | `All checks passed!` / `20 files already formatted` | `logs/10_*.txt`, `logs/11_*.txt` |
| `mypy --strict` | `Success: no issues found in 11 source files` | `logs/12_mypy_strict.txt` |
| Мутационная проверка тестов | `25/25 injected defects detected` (Linux-контейнер) | `logs/15_mutation_smoke.txt` |
| **R5.** Сценарий проверки на коде R4: `git archive` коммита R4 (`6ccf025`), сверка с его `RETURN_MANIFEST.json`, затем тесты R5 | `11/11` файлов совпадают; `FAILED` — на R4 ложный `REPORT_CREATED` и запись в подставленный каталог, exit 1 — ожидаемо | `logs/17_r5_regression_tests_on_r4_code.txt` |
| **R5.** Те же тесты на R5: `python -m unittest discover -s tests -p "test_candidate_*.py" -k IntegerDigitLimitTests -k EnvironmentTests -k ParentTrustTests -k DirectorySwapTests -k test_out_dir_with_trailing_slashes -v` | `OK` | `logs/18_r5_regression_tests.txt` |
| **R5.** Запись: доверенный родитель → out-dir `0700` владельцу; недоверенный → `IO_ERROR` до создания | `mode=0700 owner_is_euid=True`; при недоверенном — отказ, out-dir не создан | `logs/22_r5_output_directory_safety.txt` |
| Воспроизведение замечания 1 через API: `[` + 4301 девятка + `]` при `set_int_max_str_digits` 4300, 640 и 0 (принято в R2, остаётся зелёным) | во всех трёх случаях точное целое, `REJECTED ['INVALID_ROW_SCHEMA']`, настройка после вызова прежняя | `logs/19_r2_review_reproduction_api.txt` |
| То же через CLI: `python -X int_max_str_digits=4300/640/0 -m assess_workbench …` и `PYTHONINTMAXSTRDIGITS=640` | exit 0 и `REPORT_CREATED` во всех случаях; `report.json` и `report.html` побайтно одинаковы | `logs/20_r2_review_reproduction_cli.txt` |
| Худший случай: один целый литерал на весь лимит 10 485 760 байт | `load_rows` ≈12 с при 4300 и при 0; значение точное, `REJECTED` | `logs/21_r2_long_integer_cost.txt` |

`sample_output`, `sample_output_csv` и `sample_output_example` создавались только для демонстрации и удалены после запуска. Копии отчётов лежат в `logs/sample_report.{json,html}` и `logs/candidate_example_report.{json,html}`; они побайтно совпадают с R1. В R1 `sample_report.html` дополнительно проверен визуально в Chrome: все шесть рядов, коды, пояснения и пустые значения видны; `<script>…` отображается как текст; ничего не обрезано.

Собственный пример `candidate_fixtures/sales_leads.csv` показывает правила на одном наборе:
- нормализацию пробелов и регистра;
- точный дубль с другим регистром названия и другим `source_ref`;
- одну компанию с разными email;
- конфликт всей группы из трёх рядов;
- `+tag` без склейки адресов;
- отказы с одним и с несколькими кодами: кириллица в email, `http://`, `#` в URL, `KAZ`, `russian`, пустые обязательные поля;
- экранирование `<script>` в HTML.

Все адреса — на зарезервированном домене `.test`.

## 7. Как воспроизвести

Без Docker, любым CPython 3.12, из корня распакованного возврата:

```text
python CHECK_PACKAGE.py
python RUN_ACCEPTANCE.py
python -m unittest discover -s tests -p "test_candidate_*.py" -v
python -m assess_workbench --input fixtures/leads.json --format json --client-id synthetic-client --campaign-id synthetic-campaign --out-dir sample_output
```

Только регрессионные проверки R2:

```text
python -m unittest discover -s tests -p "test_candidate_*.py" -k IntegerDigitLimitTests -k EnvironmentTests -k DirectorySwapTests -k test_out_dir_with_trailing_slashes -v
```

Собственный пример со всеми статусами:

```text
python -m assess_workbench --input candidate_fixtures/sales_leads.csv --format csv --client-id synthetic-client --campaign-id synthetic-campaign --out-dir sample_output_example
```

Для повторного запуска CLI нужен новый `--out-dir`: перезапись запрещена контрактом.

Проверка `RETURN_MANIFEST.json` (из корня возврата):

```text
python -c "import hashlib, json, pathlib; m = json.loads(pathlib.Path('RETURN_MANIFEST.json').read_text(encoding='utf-8')); bad = [f['path'] for f in m['files'] if hashlib.sha256(pathlib.Path(f['path']).read_bytes()).hexdigest() != f['sha256']]; print('OK', len(m['files'])) if not bad else print('MISMATCH', bad)"
```

Dev-окружение не входит в возврат: `compose.yaml` (песочница без сети и не от root), `Makefile` с короткими командами, скрипты сбора журналов, мутационной проверки и упаковки. Причины: `RETURN_INSTRUCTIONS.md` разрешает только перечисленные пути, а `00_READ_FIRST_RU.md` указывает, что Docker и Make не нужны. Продукт от этих файлов не зависит.

## 8. Ход работы по чекпоинтам

- **CP0.** На исходном каркасе: `CHECK_PACKAGE.py` → `PACKAGE_INPUTS_PASS`, `RUN_ACCEPTANCE.py` → `NOT_IMPLEMENTED`, exit 1 — ожидаемое состояние подготовки.
- **CP1.** `docs/CP1_DESIGN.md`: как устроены парсер, нормализация, группировка и отчёт, плюс 15 неоднозначностей с решениями. Всё зафиксировано до изменения поведения; каждый спорный случай предварительно проверен на CPython 3.12.13.
- **CP2.** Реализация через тесты, слой за слоем: поля и отчёт → группировка → парсер → HTML → CLI. Для каждого слоя сначала писался тест и проверялось, что он падает. Затем — рандомизированные инварианты с независимым оракулом, тесты изоляции и мутационная проверка.
- **CP3 (R1).** Журналы, документы, `RETURN_MANIFEST.json` и ZIP `FIRST_ASSESS_01_RETURN_R1.zip`.
- **R2.** Оба замечания сначала воспроизведены на коде R1. Затем написаны регрессионные тесты и подтверждено, что на R1 они падают (журнал 17 в R2). После этого внесены минимальные исправления, документы обновлены, все журналы получены заново. ZIP `FIRST_ASSESS_01_RETURN_R2.zip` проверен распаковкой.
- **R3.** Повторная проверка приняла замечание 1 и просила довести замечание 2. Внесена защита (`mkdir 0o700` + проверка владельца/режима/пустоты), обновлены документы, журналы получены заново. ZIP `FIRST_ASSESS_01_RETURN_R3.zip` проверен распаковкой.
- **R4.** Проверка R3 показала, что проверки свойств каталога не доказывают тождество. Защита пересмотрена на доверенность родителя; проверки свойств оставлены как защита в глубину. Условие эксплуатации вынесено на согласование. ZIP `FIRST_ASSESS_01_RETURN_R4.zip` проверен распаковкой.
- **R5.** Проверка R4 нашла дефект порядка: `mkdir` шёл по полному пути до закрепления родителя, и подмена родителя в этом окне давала запись в подставленный каталог и ложный `REPORT_CREATED`; комментарий о mkdir относительно дескриптора не соответствовал коду. Порядок исправлен: родитель закрепляется дескриптором и проверяется **до создания**, создание и запись — относительно дескриптора, финальная двойная проверка (`out-dir` и путь родителя). Сначала написан тест точного сценария и подтверждено, что на коде R4 он падает (журнал 17, 11/11 файлов R4), затем внесён код, исправлены комментарии и отчёт, журналы получены заново. Условие эксплуатации повторно вынесено на согласование (`docs/R5_REWORK.md`, раздел 4), замечание не закрыто. ZIP `FIRST_ASSESS_01_RETURN_R5.zip` с одним корнем `FIRST_ASSESS_01_RETURN_R5/` проверен распаковкой: хеши совпадают с манифестом, `CHECK_PACKAGE.py` и все тесты проходят в распакованной копии.
