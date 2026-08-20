from __future__ import annotations

import json
from pathlib import Path

from tests.sql_evidence_test_support import canonical_sql_root, read_fact, run_sql_evidence


def test_sql_analysis_publishes_canonical_dependency_join_and_lineage(tmp_path: Path) -> None:
    repo = tmp_path / "mart_a"
    repo.mkdir(parents=True)
    (repo / "build_client.sql").write_text(
        """
insert overwrite table mart_client_profile
select c.client_id, c.state_code as state_code,
       case when s.status_code = 'A' then 1 else 0 end as active_flg
from src_client c
left join src_status s on c.client_id = s.client_id
where c.actual_flg = 1
group by c.client_id, c.state_code, s.status_code;
""".strip(),
        encoding="utf-8",
    )
    out = tmp_path / "analysis"
    artifact = run_sql_evidence(
        repo,
        out,
        repo_id="mart_a",
        project_code="AS1",
        system_name="demo",
    )

    assert artifact["coverage"]["sql_statement_count"] == 1
    dependencies = read_fact(out, "sql_object_dependency")
    assert {
        (item["source_relation_name"], item["target_relation_name"])
        for item in dependencies
    } == {
        ("src_client", "mart_client_profile"),
        ("src_status", "mart_client_profile"),
    }

    joins = read_fact(out, "sql_join_edge")
    assert any(
        pair["left_column"] == "client_id" and pair["right_column"] == "client_id"
        for join in joins
        for pair in join["column_pairs"]
    )

    lineage = read_fact(out, "sql_recursive_column_lineage")
    assert any(
        item["target_relation_name"] == "mart_client_profile"
        and item["target_column"] == "state_code"
        and item["terminal_relation_name"] == "src_client"
        for item in lineage
    )


def test_schema_placeholder_is_logical_template_without_blocking_gap(tmp_path: Path) -> None:
    repo = tmp_path / "mart_a"
    repo.mkdir(parents=True)
    (repo / "template.sql").write_text(
        "insert into mart_x select id, value from ${source_schema}.src_x;",
        encoding="utf-8",
    )
    out = tmp_path / "analysis"
    run_sql_evidence(repo, out, repo_id="mart_a", project_code="AS1", system_name="demo")

    placeholders = read_fact(out, "sql_semantic_placeholder")
    assert any(
        item["placeholder"] == "source_schema"
        and item["resolution_status"] == "logical_template"
        for item in placeholders
    )
    assert read_fact(out, "sql_scoped_lineage_gap") == []


def _walk_json(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_json(child)


def test_canonical_sql_output_has_no_retired_aggregate_contracts(tmp_path: Path) -> None:
    repo = tmp_path / "mart_a"
    repo.mkdir(parents=True)
    (repo / "build.sql").write_text(
        "insert into mart_entity select entity_id, state_code from src_entity;",
        encoding="utf-8",
    )
    out = tmp_path / "analysis"
    run_sql_evidence(repo, out, repo_id="mart_a", project_code="AS1", system_name="demo")

    root = canonical_sql_root(out)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    fact_types = {item["fact_type"] for item in manifest["facts"]}
    assert {
        "mart_inventory",
        "mart_column_lineage",
        "source_table_usage",
        "source_key_candidate",
        "grain_candidate",
        "sql_mart_lineage_gap",
    }.isdisjoint(fact_types)

    forbidden = {
        "confidence",
        "assessment",
        "lineage_assessment",
        "probability",
        "persistent_storage",
        "risk_relevance",
    }
    for fact_type in fact_types:
        for obj in _walk_json(read_fact(out, fact_type)):
            assert not (forbidden & set(obj))

    statements = read_fact(out, "sql_statement")
    assert statements[0]["operation"] == "insert"
    assert statements[0]["evidence_maturity_level"] == "confirmed"
