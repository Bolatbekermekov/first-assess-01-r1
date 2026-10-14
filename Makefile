# Dev-only shortcuts for FIRST-ASSESS-01. NOT part of the return package: 00_READ_FIRST_RU.md says Make is not needed
# and RETURN_INSTRUCTIONS.md does not allow it. Commands run in the network-less containers from compose.yaml, so
# nothing is installed on the host. `make` alone lists the targets; `make test PY=dev/py` uses the host CPython 3.12.

PY := docker compose run --rm -T py python
TOOLS := docker compose --profile tools run --rm -T tools
T :=
INPUT := candidate_fixtures/sales_leads.csv
FORMAT = $(if $(filter %.csv %.CSV,$(INPUT)),csv,json)
CLIENT := synthetic-client
CAMPAIGN := synthetic-campaign
SCOPE_ARGS = --client-id $(CLIENT) --campaign-id $(CAMPAIGN)
# `run` deletes its previous output first, so its directory cannot be redirected from the command line.
override RUN_DIR = out/$(basename $(notdir $(INPUT)))
LINT_PATHS := assess_workbench tests/test_candidate_*.py
RUFF_RULES := --line-length 120 --target-version py312 --select E,W,F,I,B,UP,SIM,C4,RUF --ignore RUF001,RUF002,RUF003

.PHONY: help all check lint test acceptance demo run shell format mutation zip release clean

help: ## Показать этот список
	@awk 'BEGIN { FS = ":.*## " } /^[a-z]+:.*## / { printf "  make %-11s %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

all: check lint test ## Все проверки подряд, файлы не меняются

check: ## CHECK_PACKAGE.py: исходные файлы задания не изменены
	$(PY) CHECK_PACKAGE.py

lint: ## ruff check, ruff format --check и mypy --strict
	$(TOOLS) ruff check $(RUFF_RULES) $(LINT_PATHS)
	$(TOOLS) ruff format --check --line-length 120 $(LINT_PATHS)
	$(TOOLS) mypy --strict --python-version 3.12 assess_workbench

test: ## Все тесты; make test T=fields — только tests/test_*fields*.py
	$(PY) -m unittest discover -s tests -p "test_*$(if $(T),$(T)*).py"

acceptance: ## RUN_ACCEPTANCE.py: публичная приёмка (перезаписывает evidence/)
	$(PY) RUN_ACCEPTANCE.py

demo: ## CLI на fixtures/leads.json и leads.csv, отчёты в out/json и out/csv
	rm -rf out/json out/csv
	mkdir -p out
	$(PY) -m assess_workbench --input fixtures/leads.json --format json $(SCOPE_ARGS) --out-dir out/json
	$(PY) -m assess_workbench --input fixtures/leads.csv --format csv $(SCOPE_ARGS) --out-dir out/csv
	@echo "HTML-отчёт: open out/json/report.html"

run: ## Отчёт по файлу: make run INPUT=путь (по умолчанию candidate_fixtures/sales_leads.csv)
	@case "$(INPUT)" in ""|/*|../*|*/../*) echo "Укажите файл внутри проекта относительным путём: make run INPUT=candidate_fixtures/sales_leads.csv"; exit 2 ;; esac
	@test -f "$(INPUT)" || { echo "Нет такого файла: $(INPUT)"; exit 2; }
	rm -rf "$(RUN_DIR)"
	mkdir -p out
	$(PY) -m assess_workbench --input "$(INPUT)" --format $(FORMAT) $(SCOPE_ARGS) --out-dir "$(RUN_DIR)"
	@echo "HTML-отчёт: open $(RUN_DIR)/report.html"

shell: ## bash в контейнере с Python 3.12
	docker compose run --rm py bash

format: ## Исправить форматирование и простые замечания ruff
	$(TOOLS) ruff check --fix $(RUFF_RULES) $(LINT_PATHS)
	$(TOOLS) ruff format --line-length 120 $(LINT_PATHS)

mutation: ## Мутационная проверка тестов (временно правит код, не прерывать)
	$(PY) dev/mutation_smoke.py

zip: ## Собрать dist/FIRST_ASSESS_01_RETURN_R2.zip и проверить распаковкой
	$(PY) dev/build_return.py build
	$(PY) dev/build_return.py verify

release: all ## После правок кода: проверки, новые logs/ и evidence/, затем zip
	dev/run_evidence.sh
	$(MAKE) zip

clean: ## Удалить out/ и кэши Python
	rm -rf out .ruff_cache .mypy_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
