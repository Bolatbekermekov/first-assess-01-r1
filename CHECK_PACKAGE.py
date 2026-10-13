"""Verify immutable preparation inputs. Candidate implementation paths may change."""
from pathlib import Path
import hashlib
import json
import sys
ROOT=Path(__file__).resolve().parent
if __name__ == "__main__":
    manifest=json.loads((ROOT/"BASE_MANIFEST.json").read_text(encoding="utf-8"))
    errors=[]
    for entry in manifest["immutable_files"]:
        p=ROOT/entry["path"]
        if not p.is_file() or p.is_symlink():
            errors.append(entry["path"]+": missing or symlink")
        elif hashlib.sha256(p.read_bytes()).hexdigest()!=entry["sha256"]:
            errors.append(entry["path"]+": changed")
    for entry in manifest["required_candidate_paths"]:
        if not (ROOT/entry).is_file():errors.append(entry+": missing")
    for p in ROOT.rglob("*"):
        if p.is_symlink():errors.append(str(p.relative_to(ROOT))+": symlink")
    print(json.dumps({"status":"PACKAGE_INPUTS_PASS" if not errors else "FAIL","errors":errors},ensure_ascii=False))
    raise SystemExit(0 if not errors else 2)
