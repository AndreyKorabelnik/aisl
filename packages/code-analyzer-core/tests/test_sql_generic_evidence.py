from pathlib import Path

from code_analyzer_core.prepared_artifacts.sql_analysis_evidence import build_sql_analysis_evidence
from code_analyzer_core.sql_artifact import validate_sql_analysis_artifact


def test_sql_analysis_runs_behind_generic_evidence_envelope(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    sql = repo / "load.sql"
    sql.parent.mkdir(parents=True)
    sql.write_text("insert into mart.customer select id, name from src.customer", encoding="utf-8")
    output = tmp_path / "out"
    artifact = build_sql_analysis_evidence(
        repository=repo,
        files=[sql],
        repo_id="sql-demo",
        output_root=output,
        parameters={},
    )
    assert artifact["artifact_kind"] == "sql-analysis"
    assert artifact["schema_version"] == "sql-analysis/v1"
    manifest = output / "evidence" / artifact["payload"]["canonical_manifest_path"]
    assert validate_sql_analysis_artifact(manifest)["valid"] is True
    assert artifact["payload"]["fact_shards"]


def test_legacy_analyze_sql_command_is_removed() -> None:
    from typer.testing import CliRunner
    from code_analyzer_core.cli import app
    result = CliRunner().invoke(app, ["analyze-sql", "--help"])
    assert result.exit_code != 0
    assert "No such command" in result.output
