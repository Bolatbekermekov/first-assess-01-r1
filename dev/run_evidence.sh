#!/usr/bin/env bash
# Dev-only: regenerate logs/ and evidence/ — Linux runs inside the network-less Python 3.12 container,
# then a second run on macOS with the CPython 3.12 that uv already installed (nothing is downloaded).
set -euo pipefail
cd "$(dirname "$0")/.."
SCOPE_ARGS=(--client-id synthetic-client --campaign-id synthetic-campaign)
run() { docker compose run --rm -T py python dev/capture.py "$@" 2>/dev/null; }
tools() { docker compose --profile tools run --rm -T tools python dev/capture.py "$@" 2>/dev/null; }
MAC_PY="$HOME/.local/share/uv/python/cpython-3.12-macos-aarch64-none/bin/python3.12"
# The R3 return as reviewed: its RETURN_MANIFEST.json is byte-identical to the one in FIRST_ASSESS_01_RETURN_R3.zip.
# R4 fixes a gap that was present in it, so the new tests must fail on this code and pass on R4.
PREV_COMMIT=f76bd3e29ad1a8dac3a3bdb3e3bb08caa2bce3f2

# R4 regression tests: JSON integers vs sys.set_int_max_str_digits, the environment, out-dir substitution and the
# trusted-parent requirement (ParentTrustTests), the swap window (DirectorySwapTests), trailing slashes.
read -r -d '' REGRESSION_TESTS <<'EOF' || true
python -m unittest discover -s tests -p "test_candidate_*.py" -k IntegerDigitLimitTests -k EnvironmentTests -k ParentTrustTests -k DirectorySwapTests -k test_out_dir_with_trailing_slashes -v
EOF
read -r -d '' REGRESSION_ON_PREV_CODE <<EOF || true
cd out/prev && python -c '
import hashlib, json, pathlib
manifest = json.loads(pathlib.Path("RETURN_MANIFEST.json").read_text(encoding="utf-8"))
code = [entry for entry in manifest["files"] if entry["path"].startswith("assess_workbench/")]
same = sum(hashlib.sha256(pathlib.Path(entry["path"]).read_bytes()).hexdigest() == entry["sha256"] for entry in code)
print(f"code under test is the R3 return: {same}/{len(code)} assess_workbench files match its RETURN_MANIFEST.json")
' && exec $REGRESSION_TESTS
EOF
read -r -d '' OUTDIR_SAFETY <<'EOF' || true
# Success in a trusted (owner-only) parent: out-dir is created 0700 and owned by this user.
rm -rf /tmp/trusted && mkdir -m 700 /tmp/trusted
python -m assess_workbench --input fixtures/leads.json --format json --client-id synthetic-client --campaign-id synthetic-campaign --out-dir /tmp/trusted/own
echo "trusted-parent exit=$?"
python -c 'import os, stat; s = os.stat("/tmp/trusted/own"); print("out-dir mode=%04o owner_is_euid=%s entries=%s" % (stat.S_IMODE(s.st_mode), s.st_uid == os.geteuid(), sorted(os.listdir("/tmp/trusted/own"))))'
# Untrusted (group/other-writable, no sticky) parent: the CLI refuses before writing any report.
rm -rf /tmp/shared && mkdir /tmp/shared && chmod 0777 /tmp/shared
python -m assess_workbench --input fixtures/leads.json --format json --client-id synthetic-client --campaign-id synthetic-campaign --out-dir /tmp/shared/out
echo "untrusted-parent exit=$?"
python -c 'import os; p="/tmp/shared/out"; print("out-dir entries after refusal:", sorted(os.listdir(p)) if os.path.isdir(p) else "absent")'
EOF
read -r -d '' REPRODUCTION_API <<'EOF' || true
import sys
from assess_workbench.api import analyze_rows, load_rows
scope = {"schema_version": "ASSESS_SCOPE_V1", "client_id": "synthetic-client", "campaign_id": "synthetic-campaign"}
data = b"[" + b"9" * 4301 + b"]"  # the reproduction from the R1 review
for limit in (4300, 640, 0):
    sys.set_int_max_str_digits(limit)
    rows = load_rows(data, format="json")
    row = analyze_rows(rows, scope=scope)["rows"][0]
    print(f"set_int_max_str_digits({limit}): load_rows -> the exact 4301-digit int: {rows == [10**4301 - 1]};",
          f"analyze_rows -> {row['status']} {row['codes']}; setting afterwards: {sys.get_int_max_str_digits()}")
EOF
read -r -d '' REPRODUCTION_CLI <<'EOF' || true
python -c 'import sys; sys.stdout.write("[" + "9" * 4301 + "]")' > /tmp/long.json
for setting in "-X int_max_str_digits=4300" "-X int_max_str_digits=640" "-X int_max_str_digits=0"; do
  python $setting -m assess_workbench --input /tmp/long.json --format json --client-id synthetic-client --campaign-id synthetic-campaign --out-dir "/tmp/out-${setting##*=}"
  echo "python $setting: exit=$?"
done
PYTHONINTMAXSTRDIGITS=640 python -m assess_workbench --input /tmp/long.json --format json --client-id synthetic-client --campaign-id synthetic-campaign --out-dir /tmp/out-env
echo "PYTHONINTMAXSTRDIGITS=640 python: exit=$?"
for out in /tmp/out-640 /tmp/out-0 /tmp/out-env; do
  cmp /tmp/out-4300/report.json "$out/report.json" && cmp /tmp/out-4300/report.html "$out/report.html" && echo "$out: report.json and report.html byte-identical to /tmp/out-4300"
done
python -c 'import json; row = json.load(open("/tmp/out-4300/report.json", encoding="utf-8"))["rows"][0]; print("row 1:", row["status"], row["codes"])'
EOF
read -r -d '' LONG_INTEGER_COST <<'EOF' || true
import sys, time
from assess_workbench.api import analyze_rows, load_rows
scope = {"schema_version": "ASSESS_SCOPE_V1", "client_id": "synthetic-client", "campaign_id": "synthetic-campaign"}
data = b"[" + b"9" * (10_485_760 - 2) + b"]"  # one integer filling the whole byte limit: the costliest JSON number
for limit in (4300, 0):
    sys.set_int_max_str_digits(limit)
    started = time.perf_counter()
    rows = load_rows(data, format="json")
    elapsed = time.perf_counter() - started
    row = analyze_rows(rows, scope=scope)["rows"][0]
    print(f"set_int_max_str_digits({limit}): {len(data)} bytes, load_rows {elapsed:.1f} s,",
          f"exact: {rows == [10 ** (len(data) - 2) - 1]}, {row['status']} {row['codes']}")
EOF

rm -rf logs sample_output sample_output_csv sample_output_example
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
run logs/16_cli_candidate_example.txt -- python -m assess_workbench --input candidate_fixtures/sales_leads.csv --format csv "${SCOPE_ARGS[@]}" --out-dir sample_output_example
cp sample_output_example/report.json logs/candidate_example_report.json
cp sample_output_example/report.html logs/candidate_example_report.html
rm -rf sample_output_example
rm -rf out/prev && mkdir -p out/prev && git archive "$PREV_COMMIT" | tar -x -C out/prev
cp tests/test_candidate_*.py out/prev/tests/
run logs/17_r4_regression_tests_on_r3_code.txt -- sh -c "$REGRESSION_ON_PREV_CODE"
rm -rf out/prev
run logs/18_r4_regression_tests.txt -- sh -c "$REGRESSION_TESTS"
run logs/19_r2_review_reproduction_api.txt -- python -c "$REPRODUCTION_API"
run logs/20_r2_review_reproduction_cli.txt -- sh -c "$REPRODUCTION_CLI"
run logs/21_r2_long_integer_cost.txt -- python -c "$LONG_INTEGER_COST"
run logs/22_r4_output_directory_safety.txt -- sh -c "$OUTDIR_SAFETY"
git status --short assess_workbench tests
echo "evidence regenerated"
