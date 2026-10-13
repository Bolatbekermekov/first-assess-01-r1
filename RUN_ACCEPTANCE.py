"""Run frozen public acceptance without hiding NOT_IMPLEMENTED failures."""
from pathlib import Path
import json
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
if __name__ == "__main__":
    evidence = ROOT / "evidence"
    evidence.mkdir(exist_ok=True)
    command = [sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests", "-p", "test_public_acceptance.py", "-v"]
    proc = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    (evidence / "PUBLIC_STDOUT.txt").write_text(proc.stdout, encoding="utf-8")
    (evidence / "PUBLIC_STDERR.txt").write_text(proc.stderr, encoding="utf-8")
    status = "PASS_PUBLIC_ONLY" if proc.returncode == 0 else ("NOT_IMPLEMENTED" if "NOT_IMPLEMENTED" in proc.stdout + proc.stderr else "FAIL")
    summary = {"task_id":"FIRST-ASSESS-01","status":status,"exit_code":proc.returncode,"python":sys.version,"command":command,"independent_acceptance":False}
    (evidence / "PUBLIC_SUMMARY.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({"status":status,"exit_code":proc.returncode}))
    raise SystemExit(proc.returncode)
