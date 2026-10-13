"""Candidate tests: independence of the package, import side effects, no I/O in the API (CONTRACT.md API, 8)."""

import ast
import builtins
import io
import json
import os
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from assess_workbench.api import analyze_rows, load_rows, render_html

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "assess_workbench"


class IsolationTests(unittest.TestCase):
    def test_package_imports_only_the_standard_library(self):
        for path in sorted(PACKAGE.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0:
                    names = [node.module or ""]
                else:
                    continue
                for name in names:
                    with self.subTest(file=path.name, module=name):
                        self.assertIn(name.split(".")[0], sys.stdlib_module_names)

    def test_import_has_no_side_effects(self):
        code = (
            "import csv, sys\n"
            "limit = csv.field_size_limit()\n"
            "import assess_workbench, assess_workbench.api, assess_workbench.cli, assess_workbench.__main__\n"
            "network = sorted(m for m in ('socket', 'ssl', 'http.client', 'urllib.request') if m in sys.modules)\n"
            "print(limit == csv.field_size_limit(), network)\n"
        )
        with tempfile.TemporaryDirectory() as empty:
            env = dict(os.environ, PYTHONPATH=str(ROOT))
            result = subprocess.run([sys.executable, "-B", "-c", code], cwd=empty, env=env, capture_output=True,
                                    text=True, timeout=60)
            self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "True []\n", ""))
            self.assertEqual(os.listdir(empty), [])

    def test_api_performs_no_file_or_network_io(self):
        scope = json.loads((ROOT / "fixtures" / "scope.json").read_text(encoding="utf-8"))
        json_bytes = (ROOT / "fixtures" / "leads.json").read_bytes()
        csv_bytes = (ROOT / "fixtures" / "leads.csv").read_bytes()
        forbidden = mock.Mock(side_effect=AssertionError("I/O attempted"))
        with (
            mock.patch.object(builtins, "open", forbidden),
            mock.patch.object(io, "open", forbidden),
            mock.patch.object(os, "open", forbidden),
            mock.patch.object(os, "mkdir", forbidden),
            mock.patch.object(socket, "socket", forbidden),
            mock.patch.object(socket, "create_connection", forbidden),
        ):
            report = analyze_rows(load_rows(json_bytes, format="json"), scope=scope)
            self.assertEqual(analyze_rows(load_rows(csv_bytes, format="csv"), scope=scope), report)
            render_html(report)
        forbidden.assert_not_called()

    def test_package_holds_no_fixture_answers(self):
        source = "\n".join(path.read_text(encoding="utf-8") for path in sorted(PACKAGE.rglob("*.py")))
        for marker in ("fixtures", "expected_report", "leads.json", "leads.csv", "alpha-one", "synthetic-client"):
            self.assertNotIn(marker, source)


if __name__ == "__main__":
    unittest.main()
