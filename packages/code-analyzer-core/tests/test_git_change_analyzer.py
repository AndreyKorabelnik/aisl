from __future__ import annotations

import subprocess
from pathlib import Path

from code_analyzer_core.git_change_analyzer import _profile_snapshot_analyzer, run_git_change_analysis
from code_evidence import commands


def _git(repo: Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(repo), *args], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
    return r.stdout.strip()


def test_analyze_git_change_minimal_profile(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "dev@example.invalid")
    _git(repo, "config", "user.name", "Dev")
    (repo / "pipeline.sql").write_text("select 1 as attribute_a;\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "initial")
    base = _git(repo, "rev-parse", "HEAD")
    (repo / "pipeline.sql").write_text("select 1 as attribute_a, 2 as attribute_b;\n", encoding="utf-8")
    (repo / "tests").mkdir()
    (repo / "tests" / "test_pipeline.sql").write_text("select count(*) from object_a;\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "change sql")
    head = _git(repo, "rev-parse", "HEAD")

    profile = tmp_path / "profile.yaml"
    profile.write_text(
        "profile_id: git-change-test\n"
        "profile_version: 1\n"
        "pipeline:\n"
        "  stages:\n"
        "    - id: scan_files\n"
        "    - id: core_output\n",
        encoding="utf-8",
    )
    out = tmp_path / "out"
    result = run_git_change_analysis(
        repo_path=repo,
        analysis_out=out,
        from_ref=base,
        to_ref=head,
        repo_id="repo_a",
        analysis_profile=profile,
    )

    assert result["status"] == "ok"
    git_evidence = out / "git-change-evidence"
    assert (git_evidence / "git_change_metadata.json").exists()
    assert (git_evidence / "changed_file_catalog.json").exists()
    assert (git_evidence / "llm_change_assessment_input.json").exists()
    summary = commands.git_change_summary(out)
    assert summary["risk_signals"]["tests_changed"] is True
    assert summary["change_metadata"]["repo_id"] == "repo_a"
    assert summary["change_metadata"]["commit_count"] == 1
    assert summary["change_metadata"]["authors"][0]["name"] == "Dev"
    assert summary["change_metadata"]["authors"][0]["email_hash"]
    metadata_view = commands.git_change_metadata(out)
    assert metadata_view["change_metadata"]["authoring_note"].startswith("Author/committer metadata")
    assert (out / "facts" / "facts_by_type" / "git_change_metadata.json").exists()
    assert (out / "compact" / "git_change_metadata.json").exists()
    assert (out / "repository-catalog.json").exists()
    assert (out / "compact" / "first_pass.json").exists()
    assert (out / "compact" / "navigation.json").exists()
    assert (out / "core" / "repository.json").exists()
    assert (out / "evidence_coverage.json").exists()
    import json
    first_pass = json.loads((out / "compact" / "first_pass.json").read_text(encoding="utf-8"))
    assert first_pass["workspace_type"] == "git_change"
    assert first_pass["source_type"] == "git_change_analysis"
    assert "git_change_summary" in first_pass["available_evidence_views"]
    coverage = json.loads((out / "evidence_coverage.json").read_text(encoding="utf-8"))
    assert coverage["workspace_type"] == "git_change"
    repository_catalog = json.loads((out / "repository-catalog.json").read_text(encoding="utf-8"))
    assert repository_catalog["artifact"] == "git_change_repository_catalog"
    assert repository_catalog["repositories"][0]["analysis_out"] == str(out)
    assert (out / "repository-catalog" / "repo_a.json").exists()
    analysis_manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert analysis_manifest["workspace_type"] == "git_change"
    assert "git_change_analysis" in analysis_manifest["capabilities"]
    repository_manifest_path = tmp_path / "repository-analysis-manifest.json"
    assert repository_manifest_path.is_file()
    repository_manifest = json.loads(repository_manifest_path.read_text(encoding="utf-8"))
    assert repository_manifest["repo_id"] == "repo_a"
    assert repository_manifest["static_analysis_output"] == "out"
    assert result["repository_analysis_manifest"] == str(repository_manifest_path)
    files = commands.git_change_file_catalog(out)
    assert files["matched_count"] == 2
    assert any(item["is_test"] for item in files["items"])


def test_git_change_cli_reads_evidence_directory(tmp_path: Path):
    out = tmp_path / "git-change-evidence"
    out.mkdir()
    (out / "changed_file_catalog.json").write_text('[{"path":"a.sql","language":"sql","change_kind":"modified"}]', encoding="utf-8")
    (out / "git_change_metadata.json").write_text('{"repo_id":"repo_a"}', encoding="utf-8")
    (out / "diff_summary.json").write_text('{"changed_files_count":1}', encoding="utf-8")
    (out / "complexity_metrics.json").write_text('{"changed_files":1}', encoding="utf-8")
    (out / "risk_signals.json").write_text('{"lineage_changed":false}', encoding="utf-8")
    (out / "data_impact_summary.json").write_text('{"semantic_delta_items":0}', encoding="utf-8")
    (out / "test_doc_delta.json").write_text('{"tests_changed_count":0}', encoding="utf-8")

    summary = commands.git_change_summary(out)
    assert summary["metadata"]["repo_id"] == "repo_a"
    metadata = commands.git_change_metadata(out)
    assert metadata["change_metadata"]["repo_id"] == "repo_a"
    assert metadata["change_metadata"]["metadata_limitations"]
    catalog = commands.git_change_file_catalog(out, "a.sql")
    assert catalog["matched_count"] == 1



def test_git_change_metadata_cli_arguments_are_traceability_only(tmp_path: Path):
    repo = tmp_path / "repo_meta"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "author@example.invalid")
    _git(repo, "config", "user.name", "Author One")
    (repo / "a.sql").write_text("select 1;\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "initial")
    base = _git(repo, "rev-parse", "HEAD")
    _git(repo, "config", "user.email", "committer@example.invalid")
    _git(repo, "config", "user.name", "Committer Two")
    (repo / "a.sql").write_text("select 1, 2;\n", encoding="utf-8")
    _git(repo, "add", ".")
    env = {"GIT_AUTHOR_NAME": "Author One", "GIT_AUTHOR_EMAIL": "author@example.invalid"}
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "change"], check=True, env={**__import__('os').environ, **env}, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    head = _git(repo, "rev-parse", "HEAD")

    profile = tmp_path / "profile.yaml"
    profile.write_text(
        "profile_id: git-change-complexity-assessment\n"
        "profile_version: 1\n"
        "pipeline:\n"
        "  stages:\n"
        "    - id: scan_files\n"
        "    - id: core_output\n",
        encoding="utf-8",
    )
    out = tmp_path / "out_meta"
    run_git_change_analysis(
        repo_path=repo,
        analysis_out=out,
        from_ref=base,
        to_ref=head,
        repo_id="repo_meta",
        analysis_profile=profile,
        change_id="MR-123",
        change_type="mr",
        source_branch="feature/example",
        target_branch="develop",
        reviewers="reviewer1,reviewer2@example.invalid",
    )
    meta = commands.git_change_metadata(out)["change_metadata"]
    assert meta["change_id"] == "MR-123"
    assert meta["change_type"] == "mr"
    assert meta["source_branch"] == "feature/example"
    assert meta["target_branch"] == "develop"
    assert meta["commit_range"]["before"] == base
    assert meta["commit_range"]["after"] == head
    assert meta["commit_count"] == 1
    assert meta["authors"][0]["name"] == "Author One"
    assert meta["committers"][0]["name"] == "Committer Two"
    assert meta["reviewers"]
    assert meta["authoring_note"].endswith("personal evaluation.")

def test_git_change_invalid_ref_has_actionable_message(tmp_path: Path):
    repo = tmp_path / "repo_invalid_ref"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "dev@example.invalid")
    _git(repo, "config", "user.name", "Dev")
    (repo / "a.sql").write_text("select 1;\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "initial")
    base = _git(repo, "rev-parse", "HEAD")

    profile = tmp_path / "profile.yaml"
    profile.write_text(
        "profile_id: git-change-complexity-assessment\n"
        "profile_version: 1\n"
        "pipeline:\n"
        "  stages:\n"
        "    - id: scan_files\n"
        "    - id: core_output\n",
        encoding="utf-8",
    )

    try:
        run_git_change_analysis(
            repo_path=repo,
            analysis_out=tmp_path / "out_invalid_ref",
            from_ref=base,
            to_ref="f" * 40,
            repo_id="repo_invalid_ref",
            analysis_profile=profile,
        )
    except Exception as exc:
        message = str(exc)
    else:
        raise AssertionError("Expected invalid git ref failure")

    assert "Invalid git revision" in message
    assert "--to" in message
    assert "git fetch --all --tags --prune" in message
    assert "git fetch --unshallow" in message




def test_git_change_snapshot_analyzer_is_selected_only_by_typed_requirement() -> None:
    assert _profile_snapshot_analyzer({
        "source_type": "sql_spark_config",
        "workspace_types": ["sql"],
        "git_change_snapshot_analyzer": "sql",
        "pipeline": {"stages": [{"id": "scan_files"}]},
    }) == "core"
    assert _profile_snapshot_analyzer({
        "evidence_requirements": [{
            "artifact_kind": "sql-analysis",
            "schema_version": "sql-analysis/v1",
        }],
    }) == "sql"

def test_git_change_sql_spark_profile_uses_sql_snapshot_analyzer(tmp_path: Path):
    repo = tmp_path / "repo_sql"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "dev@example.invalid")
    _git(repo, "config", "user.name", "Dev")
    (repo / "mart.sql").write_text(
        "insert overwrite table dm.client_mart select client_id, amount from ods.payments;\n",
        encoding="utf-8",
    )
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "initial sql")
    base = _git(repo, "rev-parse", "HEAD")
    (repo / "mart.sql").write_text(
        "insert overwrite table dm.client_mart select client_id, amount, status from ods.payments;\n",
        encoding="utf-8",
    )
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "change sql mart")
    head = _git(repo, "rev-parse", "HEAD")

    profile = tmp_path / "profile.yaml"
    profile.write_text(
        "profile_id: git-change-sql-spark-complexity-assessment\n"
        "profile_version: 1\n"
        "evidence_requirements:\n"
        "  - artifact_kind: sql-analysis\n"
        "    schema_version: sql-analysis/v1\n",
        encoding="utf-8",
    )
    out = tmp_path / "out_sql"
    result = run_git_change_analysis(
        repo_path=repo,
        analysis_out=out,
        from_ref=base,
        to_ref=head,
        repo_id="repo_sql",
        analysis_profile=profile,
    )

    assert result["status"] == "ok"
    meta = commands.git_change_metadata(out)
    assert meta["snapshot_analyzer"] == "sql"
    assert (out / "before-analysis" / "core-evidence-execution-result.json").exists()
    assert (out / "before-analysis" / "evidence" / "sql-analysis-evidence.json").exists()
    assert (out / "before-analysis" / "evidence" / "sql-analysis" / "manifest.json").exists()
    assert (out / "after-analysis" / "core-evidence-execution-result.json").exists()
    assert (out / "after-analysis" / "evidence" / "sql-analysis-evidence.json").exists()
    assert (out / "after-analysis" / "evidence" / "sql-analysis" / "manifest.json").exists()
    transformation = commands.git_change_transformation_delta(out)
    assert transformation["matched_count"] >= 1
