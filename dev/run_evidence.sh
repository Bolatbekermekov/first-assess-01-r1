#!/usr/bin/env bash
# Dev-only: regenerate logs/ and evidence/ — Linux runs inside the network-less Python 3.12 container,
# then a second run on macOS with the CPython 3.12 that uv already installed (nothing is downloaded).
set -euo pipefail
cd "$(dirname "$0")/.."
SCOPE_ARGS=(--client-id synthetic-client --campaign-id synthetic-campaign)
run() { docker compose run --rm -T py python dev/capture.py "$@" 2>/dev/null; }
tools() { docker compose --profile tools run --rm -T tools python dev/capture.py "$@" 2>/dev/null; }
MAC_PY="$HOME/.local/share/uv/python/cpython-3.12-macos-aarch64-none/bin/python3.12"

rm -rf logs sample_output sample_output_csv
mkdir -p logs
dev/py dev/capture.py logs/00_host.txt -- sh -c 'sw_vers; uname -mrs; docker --version; docker compose version; grep -E "image:|FROM|pip install" compose.yaml'
run logs/01_container_environment.txt -- sh -c 'python -VV; python -c "import platform, unicodedata; print(platform.platform(), \"unicodedata\", unicodedata.unidata_version)"; echo "uid=$(id -u) gid=$(id -g)"; grep PRETTY_NAME /etc/os-release; python -c "import socket; socket.create_connection((\"1.1.1.1\", 53), timeout=3)" 2>&1 | tail -n 1'
run logs/02_check_package.txt -- python CHECK_PACKAGE.py
run logs/03_run_acceptance.txt -- python RUN_ACCEPTANCE.py
run logs/04_candidate_tests.txt -- python -m unittest discover -s tests -p "test_candidate_*.py" -v
run logs/05_cli_json.txt -- python -m assess_workbench --input fixtures/leads.json --format json "${SCOPE_ARGS[@]}" --out-dir sample_output
cp sample_output/report.json logs/sample_report.json
cp sample_output/report.html logs/sample_report.html
run logs/06_cli_rerun_output_exists.txt -- python -m assess_workbench --input fixtures/leads.json --format json "${SCOPE_ARGS[@]}" --out-dir sample_output
run logs/07_cli_csv.txt -- python -m assess_workbench --input fixtures/leads.csv --format csv "${SCOPE_ARGS[@]}" --out-dir sample_output_csv
run logs/08_cli_json_csv_identical.txt -- sh -c 'cmp sample_output/report.json sample_output_csv/report.json && cmp sample_output/report.html sample_output_csv/report.html && echo "report.json and report.html are byte-identical for the JSON and CSV inputs"; ls -l sample_output sample_output_csv'
run logs/09_cli_error_cases.txt -- sh -c '
  printf SECRET_SENTINEL_RAW_PAYLOAD > /tmp/bad.json
  for case in "fixtures/leads.json json bad%id" "/tmp/bad.json json synthetic-client" "/tmp/missing.json json synthetic-client" "fixtures/leads.json xml synthetic-client" "/dev/zero json synthetic-client"; do
    set -- $case
    echo "--- --input $1 --format $2 --client-id $3"
    python -m assess_workbench --input "$1" --format "$2" --client-id "$3" --campaign-id synthetic-campaign --out-dir /tmp/out
    echo "exit=$? out_dir_created=$(test -e /tmp/out && echo yes || echo no)"
  done 2>&1'
rm -rf sample_output sample_output_csv
tools logs/10_ruff_check.txt -- sh -c 'ruff --version && ruff check --line-length 120 --target-version py312 --select E,W,F,I,B,UP,SIM,C4,RUF --ignore RUF001,RUF002,RUF003 assess_workbench tests/test_candidate_*.py'
tools logs/11_ruff_format_check.txt -- sh -c 'ruff format --check --line-length 120 assess_workbench tests/test_candidate_*.py'
tools logs/12_mypy_strict.txt -- sh -c 'mypy --version && mypy --strict --python-version 3.12 assess_workbench'
dev/py dev/capture.py logs/13_macos_candidate_tests.txt -- "$MAC_PY" -B -m unittest discover -s tests -p "test_candidate_*.py" -v
dev/py dev/capture.py logs/14_macos_public_tests.txt -- "$MAC_PY" -B -m unittest discover -s tests -p "test_public_acceptance.py" -v
run logs/15_mutation_smoke.txt -- python dev/mutation_smoke.py
git status --short assess_workbench tests
echo "evidence regenerated"
