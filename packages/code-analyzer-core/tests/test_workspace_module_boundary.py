from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_repository_analyzer_has_no_workspace_runtime_dependency() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "duckdb" not in pyproject.lower()
    assert "workspace-knowledge-layer" not in pyproject
    for package in (ROOT / "code_analyzer_core", ROOT / "code_evidence"):
        for path in package.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            assert "workspace_knowledge_layer" not in text, path
            assert "import duckdb" not in text, path


def test_repository_analyzer_does_not_publish_workspace_build_commands() -> None:
    source = (ROOT / "code_analyzer_core" / "cli.py").read_text(encoding="utf-8")
    for command in ("workspace-build", "workspace-update", "workspace-diff-plan", "workspace-status"):
        assert command not in source


def test_repository_analyzer_has_no_workspace_aggregation_modules_or_cli() -> None:
    package = ROOT / "code_analyzer_core"
    forbidden_modules = {"workspace.py", "java_workspace.py", "python_workspace.py", "spec_workspace.py"}
    assert not (forbidden_modules & {path.name for path in package.glob("*.py")})
    cli = (package / "cli.py").read_text(encoding="utf-8")
    for token in ("analyze-java-workspace", "analyze-sql-workspace", "run_java_source_workspace_analysis", "run_sql_source_workspace_analysis"):
        assert token not in cli


def test_repository_facts_only_contract_has_no_ranking_or_role_verdict_fields():
    root = Path(__file__).resolve().parents[1]
    audited = [
        root / "code_evidence" / "source.py",
        root / "code_analyzer_core" / "navigation.py",
        root / "code_evidence" / "commands.py",
    ]
    forbidden_literals = [
        '"score":', '"confidence":', '"severity":',
        '"storage_role":', '"candidate_source_pattern"',
        '"domain_key_relation"',
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in audited)
    for token in forbidden_literals:
        assert token not in combined, token
