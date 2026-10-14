# FIRST-ASSESS-01 R1 — `assess_workbench`

Решение  задания FIRST-ASSESS-01 R1 (проект Sales Manager FIRST).

`assess_workbench` — локальный модуль на Python 3.12 без сторонних зависимостей. Он читает синтетический список потенциальных клиентов из JSON или CSV, проверяет и нормализует поля, находит точные дубли email и конфликты и выпускает детерминированный JSON-отчёт и автономный HTML-отчёт с причиной для каждого ряда.

| Что | Где |
|---|---|
| Условие и нормативный контракт | [`00_READ_FIRST_RU.md`](00_READ_FIRST_RU.md), [`CONTRACT.md`](CONTRACT.md) |
| Отчёт о выполнении | [`TASK_REPORT.md`](TASK_REPORT.md) |
| Требования → тесты → журналы | [`TEST_MATRIX.md`](TEST_MATRIX.md) |
| Архитектура и решения по неоднозначностям контракта | [`docs/CP1_DESIGN.md`](docs/CP1_DESIGN.md) |
| Доработка R1 → R2 по замечаниям проверки | [`docs/R2_REWORK.md`](docs/R2_REWORK.md) |
| Доработка R2 → R3 (защита выходного каталога) | [`docs/R3_REWORK.md`](docs/R3_REWORK.md) |
| Доработка R3 → R4 (доверенный родитель, запрос условия) | [`docs/R4_REWORK.md`](docs/R4_REWORK.md) |
| Доработка R4 → R5 (порядок: закрепление родителя до создания) | [`docs/R5_REWORK.md`](docs/R5_REWORK.md) |
| Ограничения | [`LIMITATIONS.md`](LIMITATIONS.md) |
| Предложение декомпозиции | [`DECOMPOSITION_PROPOSAL.md`](DECOMPOSITION_PROPOSAL.md) |
| Журналы запусков и готовые отчёты | [`logs/`](logs/) |

## Результаты

- Публичная приёмка `RUN_ACCEPTANCE.py`: `PASS_PUBLIC_ONLY`, 12/12.
- Собственные тесты: 155/155 в Linux-контейнере без сети и на macOS; регрессионные тесты R5 падают на коде R4 и проходят на R5.
- `ruff check`, `ruff format --check` и `mypy --strict` — без замечаний.
- Мутационная проверка: тесты обнаружили 25 из 25 внесённых дефектов.

## Запуск

Нужен только CPython 3.12:

```text
python CHECK_PACKAGE.py
python RUN_ACCEPTANCE.py
python -m unittest discover -s tests -p "test_*.py"
python -m assess_workbench --input candidate_fixtures/sales_leads.csv --format csv --client-id synthetic-client --campaign-id synthetic-campaign --out-dir sample_output
```

С Docker те же проверки идут в изолированном контейнере без сети: `make all`, `make run`; список команд — `make help`.

## Структура

```text
assess_workbench/      модуль: loading → fields → grouping → analysis → html_report; cli — единственный файловый ввод-вывод
tests/                 публичные (test_public_acceptance.py) и собственные (test_candidate_*.py) тесты
fixtures/              данные задания
candidate_fixtures/    собственный синтетический пример со всеми статусами
docs/ logs/ evidence/  дизайн, журналы запусков, вывод публичного runner
dev/ compose.yaml Makefile  dev-окружение: песочница, сбор журналов, мутационная проверка, сборка ZIP возврата
```

Возврат по `RETURN_INSTRUCTIONS.md` собирается командой `make zip` в `dist/FIRST_ASSESS_01_RETURN_R5.zip` (текущая ревизия возврата — R5); dev-окружение и этот README в него не входят.
