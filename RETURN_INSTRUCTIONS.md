# Возврат FIRST-ASSESS-01

Один ZIP с одним корнем `FIRST_ASSESS_01_RETURN_R1/`. Включить полный исходный пакет с неизменёнными контрактом, fixtures и публичными тестами, реализацию `assess_workbench/`, собственные `tests/test_candidate_*.py` и документы ниже. Не включать venv, .git, caches, реальные контакты, credentials или сетевые выгрузки.

Разрешено менять только `assess_workbench/**/*.py`, добавлять `tests/test_candidate_*.py`, свои синтетические `candidate_fixtures/`, `docs/`, `logs/` и перечисленные документы возврата. `evidence/` — выход предоставленного runner; не править вручную вместо настоящего запуска. Предоставленные `CONTRACT.md`, `fixtures/`, `tests/test_public_acceptance.py`, `CHECK_PACKAGE.py`, `RUN_ACCEPTANCE.py`, `BASE_MANIFEST.json` и прочие документы задания сохранять без изменения.

Команды из корня:

```text
python CHECK_PACKAGE.py
python RUN_ACCEPTANCE.py
python -m unittest discover -s tests -p "test_candidate_*.py" -v
python -m assess_workbench --input fixtures/leads.json --format json --client-id synthetic-client --campaign-id synthetic-campaign --out-dir sample_output
```

`sample_output` — временный каталог демонстрации, не включать его в RETURN ZIP; при необходимости скопировать два отчёта в `logs/`. `sample_output` должен отсутствовать перед запуском. Записать stdout/stderr, exit code и фактическую среду. Для повторного запуска использовать новый output directory; не менять поведение запрета перезаписи. В исходной заготовке проверка комплектности проходит, публичные тесты завершаются NOT_IMPLEMENTED — это ожидаемое состояние подготовки, не приёмка реализации.

Обязательные документы:

- `TASK_REPORT.md`: project_id sales-manager-first, task_id FIRST-ASSESS-01, ревизия, имя исполнителя, реализованное, команды и фактические результаты, структура решения.
- `TEST_MATRIX.md`: требование → свой/публичный тест → реальный log → PASS/FAIL/NOT_RUN; отдельно указать что не проверено. Собственные проверки обязательны: прохождения только публичного набора недостаточно.
- `LIMITATIONS.md`: непроверенные условия, найденные неоднозначности и ограничения. Не заявлять запуск на ОС, где его не было.
- `DECOMPOSITION_PROPOSAL.md`: предложить границы будущих небольших частей (parser, validation, grouping, reports/CLI, возможный отдельный адаптер FIRST), входы/выходы, зависимости и критерии приёмки каждой. Не присваивать существующие production task IDs и не менять текущие назначения. Не добавлять планирование трудозатрат или календарные обязательства.
- `RETURN_MANIFEST.json`: task_id, revision, base_manifest_sha256 и список относительных путей с SHA256 всех файлов возврата, кроме самого manifest. Хеши считать по фактическим байтам.
- `logs/`: настоящие журналы собственных тестов/CLI. `evidence/` содержит результаты публичного runner.

Присылать код и доказательства, а не только скриншоты или сообщение «готово». Статус автора READY_FOR_REVIEW не означает независимый PASS. Ни возврат, ни предложение декомпозиции не означают установку в рабочий проект.
