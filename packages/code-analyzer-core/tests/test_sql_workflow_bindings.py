import json
from pathlib import Path

from code_analyzer_core.sql_artifact import validate_sql_analysis_artifact
from tests.sql_evidence_test_support import canonical_sql_root, run_sql_evidence


def _facts(out: Path) -> list[dict]:
    path = canonical_sql_root(out) / "facts" / "sql_workflow_binding.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_sql_analysis_publishes_yaml_and_json_workflow_bindings(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "load.sql").write_text(
        "INSERT INTO ${target_schema}.${$main_table_name} SELECT id FROM src.individual;",
        encoding="utf-8",
    )
    (repo / "workflow.yaml").write_text(
        """trigger: start-after-deploy
param:
  sql.file: load.sql
  main_table_name: epk_client
  main_table_name_stg: "${main_table_name}_stg"
""",
        encoding="utf-8",
    )
    (repo / "pipeline.json").write_text(
        json.dumps({"stage": {"filePath": "load.sql", "table": "${main_table_name_stg}"}}, indent=2),
        encoding="utf-8",
    )
    out = tmp_path / "out"
    run_sql_evidence(
        repo,
        out,
        repo_id="workflow_fixture",
    )

    facts = _facts(out)
    by_key = {(item["file"], item["binding_path"]): item for item in facts}

    main = by_key[("workflow.yaml", "param.main_table_name")]
    assert by_key[("workflow.yaml", "param.sql.file")]["binding_name"] == "sql.file"
    assert main["scalar_value"] == "epk_client"
    assert main["resolution_status"] == "literal"
    assert main["referenced_placeholders"] == []
    assert main["line_start"] == 4

    staged = by_key[("workflow.yaml", "param.main_table_name_stg")]
    assert staged["value_expression"] == "${main_table_name}_stg"
    assert staged["resolution_status"] == "template"
    assert staged["referenced_placeholders"] == ["main_table_name"]

    pipeline = by_key[("pipeline.json", "stage.table")]
    assert pipeline["referenced_placeholders"] == ["main_table_name_stg"]
    assert pipeline["config_format"] == "json"

    for item in facts:
        for evidence in item["evidence"]:
            assert not Path(evidence["file"]).is_absolute()
            assert evidence["file"] == item["file"]

    validation = validate_sql_analysis_artifact(canonical_sql_root(out) / "manifest.json")
    assert validation["valid"] is True
    assert validation["errors"] == []


def test_workflow_bindings_are_limited_to_sql_relevant_config_hints(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "model.sql").write_text("SELECT id FROM src.a;", encoding="utf-8")
    (repo / "workflow.yaml").write_text("param:\n  sql.file: model.sql\n  main_table_name: target_a\n", encoding="utf-8")
    (repo / "unrelated.yaml").write_text("feature:\n  enabled: true\n  label: unrelated\n", encoding="utf-8")
    out = tmp_path / "out"
    run_sql_evidence(
        repo,
        out,
        repo_id="workflow_scope_fixture",
    )

    facts = _facts(out)
    assert any(item["file"] == "workflow.yaml" for item in facts)
    assert all(item["file"] != "unrelated.yaml" for item in facts)


def test_workflow_bindings_include_repository_config_referenced_from_dsl(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "wf").mkdir(parents=True)
    (repo / "wf" / "load.sql").write_text(
        'if $load_type = \'inc\' then historicity("$root/wf/model_historicity.json"); end if;',
        encoding="utf-8",
    )
    (repo / "wf" / "model_historicity.json").write_text(
        json.dumps({
            "params": {
                "increment": {"tableName": "target_prestg"},
                "output": {"tableNameSnp": "target_stg"},
            }
        }),
        encoding="utf-8",
    )
    (repo / "unrelated.json").write_text(json.dumps({"feature": {"enabled": True}}), encoding="utf-8")
    out = tmp_path / "out"
    run_sql_evidence(repo, out, repo_id="referenced_config_fixture")

    facts = _facts(out)
    assert any(
        item["file"] == "wf/model_historicity.json"
        and item["binding_path"] == "params.increment.tableName"
        and item["scalar_value"] == "target_prestg"
        for item in facts
    )
    assert any(
        item["file"] == "wf/model_historicity.json"
        and item["binding_path"] == "params.output.tableNameSnp"
        and item["scalar_value"] == "target_stg"
        for item in facts
    )
    assert all(item["file"] != "unrelated.json" for item in facts)


def test_workflow_bindings_keep_all_configs_matching_static_suffix_after_nested_placeholder(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "wf" / "common").mkdir(parents=True)
    (repo / "wf" / "alpha").mkdir(parents=True)
    (repo / "wf" / "beta").mkdir(parents=True)
    (repo / "wf" / "common" / "stage.sql").write_text(
        'historicity("$root/wf/$main_table_name/t_dim_historicity_conf.json");',
        encoding="utf-8",
    )
    for table in ("alpha", "beta"):
        (repo / "wf" / table / "t_dim_historicity_conf.json").write_text(
            json.dumps({"params": {"increment": {"tableName": f"{table}_prestg"}}}),
            encoding="utf-8",
        )
    (repo / "unrelated.json").write_text(json.dumps({"feature": {"enabled": True}}), encoding="utf-8")

    out = tmp_path / "out"
    run_sql_evidence(repo, out, repo_id="nested_config_suffix_fixture")
    facts = _facts(out)
    observed = {
        (item["file"], item["binding_path"], item["scalar_value"])
        for item in facts
        if item["binding_path"] == "params.increment.tableName"
    }
    assert observed == {
        ("wf/alpha/t_dim_historicity_conf.json", "params.increment.tableName", "alpha_prestg"),
        ("wf/beta/t_dim_historicity_conf.json", "params.increment.tableName", "beta_prestg"),
    }
    assert all(item["file"] != "unrelated.json" for item in facts)


def test_sql_analysis_recovers_bare_template_yaml_scalars_without_losing_other_bindings(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "load.sql").write_text("SELECT 1;", encoding="utf-8")
    (repo / "workflow.yml").write_text(
        """workflow:
  profile: {{global.CTL_PROFILE_NAME}}
  params:
    - param: { name: "s2t.source.table.name", prior_value: "source_table" }
    - param: { name: "s2t.target.table.name", prior_value: "target_table" }
  sql.file: load.sql
""",
        encoding="utf-8",
    )

    out = tmp_path / "out"
    run_sql_evidence(repo, out, repo_id="template_yaml_fixture")
    facts = _facts(out)
    observed = {(item["binding_name"], item["scalar_value"]): item for item in facts}
    assert ("profile", "{{global.CTL_PROFILE_NAME}}") in observed
    assert ("name", "s2t.source.table.name") in observed
    assert ("prior_value", "source_table") in observed
    assert ("name", "s2t.target.table.name") in observed
    assert ("prior_value", "target_table") in observed
    profile_evidence = observed[("profile", "{{global.CTL_PROFILE_NAME}}")] ["evidence"][0]
    assert profile_evidence["config_parse_mode"] == "template_tolerant"
    assert profile_evidence["recovered_template_lines"] == [2]
