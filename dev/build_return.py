"""Dev-only: build RETURN_MANIFEST.json and the return ZIP from an explicit allowlist, and verify the ZIP.

Usage (inside the container, from the project root):
  python dev/build_return.py build    # RETURN_MANIFEST.json + dist/FIRST_ASSESS_01_RETURN_R2.zip
  python dev/build_return.py verify   # extract to a temporary directory; re-check hashes, layout and all tests
"""

import fnmatch
import hashlib
import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REVISION = "R2"
ZIP_ROOT = f"FIRST_ASSESS_01_RETURN_{REVISION}"
ZIP_PATH = ROOT / "dist" / f"{ZIP_ROOT}.zip"
MANIFEST = "RETURN_MANIFEST.json"
RETURN_DOCUMENTS = ("TASK_REPORT.md", "TEST_MATRIX.md", "LIMITATIONS.md", "DECOMPOSITION_PROPOSAL.md")
SHIPPED_TREES = ("candidate_fixtures/", "docs/", "logs/", "evidence/")
# Top-level entries of the repository that never go into the ZIP: dev environment, build output, repository README.
DEV_ONLY = {".git", "dev", "dist", "out", "compose.yaml", "Makefile", "README.md"}
IGNORED_PARTS = {"__pycache__", ".DS_Store", ".ruff_cache", ".mypy_cache"}
ZIP_TIMESTAMP = (2026, 10, 14, 0, 0, 0)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def base_manifest() -> dict[str, Any]:
    return json.loads((ROOT / "BASE_MANIFEST.json").read_text(encoding="utf-8"))


def is_shipped(relative: str, original: set[str]) -> bool:
    return (
        relative in original
        or relative in RETURN_DOCUMENTS
        or (relative.startswith("assess_workbench/") and relative.endswith(".py"))
        or fnmatch.fnmatch(relative, "tests/test_candidate_*.py")
        or relative.startswith(SHIPPED_TREES)
    )


def is_forbidden(name: str) -> bool:
    parts = PurePosixPath(name).parts[1:]  # below the ZIP root
    return bool(parts) and (
        parts[0] in DEV_ONLY or parts[0].startswith("sample_output") or bool(IGNORED_PARTS.intersection(parts))
    )


def collect() -> list[str]:
    base = base_manifest()
    original = {entry["path"] for entry in base["immutable_files"]} | {"BASE_MANIFEST.json"}
    shipped, unexpected = [], []
    for path in sorted(ROOT.rglob("*")):
        relative = path.relative_to(ROOT).as_posix()
        parts = PurePosixPath(relative).parts
        if parts[0] in DEV_ONLY or IGNORED_PARTS.intersection(parts) or path.suffix == ".pyc":
            continue
        if path.is_symlink():
            raise SystemExit(f"symlink in the package: {relative}")
        if path.is_dir() or relative == MANIFEST:
            continue
        (shipped if is_shipped(relative, original) else unexpected).append(relative)
    if unexpected:
        raise SystemExit("outside the RETURN_INSTRUCTIONS allowlist: " + ", ".join(unexpected))
    required = original | set(base["required_candidate_paths"]) | set(RETURN_DOCUMENTS)
    missing = sorted(required - set(shipped))
    if missing:
        raise SystemExit("missing from the return: " + ", ".join(missing))
    return shipped


def build() -> None:
    files = collect()
    manifest = {
        "task_id": "FIRST-ASSESS-01",
        "revision": REVISION,
        "base_manifest_sha256": sha256(ROOT / "BASE_MANIFEST.json"),
        "files": [{"path": relative, "sha256": sha256(ROOT / relative)} for relative in files],
    }
    (ROOT / MANIFEST).write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    ZIP_PATH.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(ZIP_PATH, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        root_entry = zipfile.ZipInfo(f"{ZIP_ROOT}/", date_time=ZIP_TIMESTAMP)
        root_entry.external_attr = (0o40755 << 16) | 0x10
        archive.writestr(root_entry, b"")
        for relative in sorted([*files, MANIFEST]):
            info = zipfile.ZipInfo(f"{ZIP_ROOT}/{relative}", date_time=ZIP_TIMESTAMP)
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, (ROOT / relative).read_bytes())
    print(f"built {ZIP_PATH.relative_to(ROOT)} with {len(files) + 1} files")


def verify() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        with zipfile.ZipFile(ZIP_PATH) as archive:
            names = archive.namelist()
            outside = [name for name in names if not name.startswith(f"{ZIP_ROOT}/")]
            forbidden = [name for name in names if is_forbidden(name)]
            if outside or forbidden:
                raise SystemExit(f"bad layout: outside={outside} forbidden={forbidden}")
            archive.extractall(temporary)
        root = Path(temporary) / ZIP_ROOT
        manifest = json.loads((root / MANIFEST).read_text(encoding="utf-8"))
        listed = {entry["path"]: entry["sha256"] for entry in manifest["files"]}
        actual = {
            path.relative_to(root).as_posix(): sha256(path)
            for path in root.rglob("*")
            if path.is_file() and path.name != MANIFEST
        }
        if listed != actual or manifest["base_manifest_sha256"] != sha256(root / "BASE_MANIFEST.json"):
            raise SystemExit("RETURN_MANIFEST.json does not match the archive")
        commands = (
            [sys.executable, "CHECK_PACKAGE.py"],
            [sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py"],
        )
        for command in commands:
            result = subprocess.run(command, cwd=root, capture_output=True, text=True, check=False)
            tail = (result.stdout + result.stderr).strip().splitlines()[-3:]
            print(f"{' '.join(command[1:])}: exit {result.returncode} | {' | '.join(tail)}")
            if result.returncode != 0:
                raise SystemExit("verification failed")
    print(f"verified {ZIP_PATH.relative_to(ROOT)}: {len(listed)} files match the manifest")


if __name__ == "__main__":
    {"build": build, "verify": verify}[sys.argv[1]]()
