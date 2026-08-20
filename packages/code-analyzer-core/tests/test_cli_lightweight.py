from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def _run_with_native_imports_blocked(command: str) -> subprocess.CompletedProcess[str]:
    script = f'''\nimport importlib.abc\nimport sys\n\nclass BlockNative(importlib.abc.MetaPathFinder):\n    blocked = {{"tree_sitter", "tree_sitter_java", "sqlglot", "duckdb"}}\n    def find_spec(self, fullname, path=None, target=None):\n        if fullname.split(".", 1)[0] in self.blocked:\n            raise ModuleNotFoundError(f"blocked for lightweight CLI test: {{fullname}}", name=fullname)\n        return None\n\nsys.meta_path.insert(0, BlockNative())\nfrom code_analyzer_core.cli import app\nfrom typer.testing import CliRunner\nresult = CliRunner().invoke(app, ["{command}"])\nprint(result.stdout, end="")\nif result.exception:\n    print(repr(result.exception), file=sys.stderr)\nraise SystemExit(result.exit_code)\n'''
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )


def test_version_does_not_import_native_analysis_dependencies() -> None:
    result = _run_with_native_imports_blocked("version")
    assert result.returncode == 0, result.stderr
    from code_analyzer_core import __version__
    assert __version__ in result.stdout


def test_doctor_reports_missing_native_dependency_without_crashing() -> None:
    result = _run_with_native_imports_blocked("doctor")
    assert result.returncode == 0, result.stderr
    assert "java_syntax_provider" in result.stdout
    assert "tree-sitter-java" in result.stdout
