import hashlib
import json
from pathlib import Path

from code_analyzer_core import __version__
from code_analyzer_core.sql_artifact import (
    SQL_ANALYSIS_SCHEMA_VERSION,
    SQL_CANONICAL_FACTS,
    validate_sql_analysis_artifact,
)
from tests.sql_evidence_test_support import canonical_sql_root, run_sql_evidence


def _manifest(out: Path) -> dict:
    return json.loads((canonical_sql_root(out) / "manifest.json").read_text(encoding="utf-8"))


def _run(tmp_path: Path, sql: str, *, suffix: str = "") -> tuple[Path, dict]:
    repo = tmp_path / "repo"
    repo.mkdir(exist_ok=True)
    (repo / "model.sql").write_text(sql, encoding="utf-8")
    out = tmp_path / f"out{suffix}"
    result = run_sql_evidence(
        repo,
        out,
        repo_id="canonical_sql",
    )
    return out, result


def test_canonical_sql_artifact_has_versioned_jsonl_shards_and_portable_evidence(tmp_path: Path) -> None:
    out, result = _run(
        tmp_path,
        """
        WITH prepared AS (
            SELECT a.id, upper(a.value) AS normalized_value
            FROM ${source_schema}.source_a a
        )
        INSERT INTO mart.target (id, normalized_value)
        SELECT p.id, p.normalized_value
        FROM prepared p
        LEFT JOIN source_b b ON p.id = b.id;
        """,
    )

    root = canonical_sql_root(out)
    manifest = _manifest(out)
    expected_types = [fact_type for fact_type, _ in SQL_CANONICAL_FACTS]

    assert manifest["artifact"] == "sql_analysis"
    assert manifest["schema_version"] == SQL_ANALYSIS_SCHEMA_VERSION
    assert manifest["contract_version"] == "1.0"
    assert manifest["producer"]["version"] == __version__
    assert [item["fact_type"] for item in manifest["facts"]] == expected_types
    assert result["payload"]["canonical_manifest_path"] == "sql-analysis/manifest.json"
    assert result["payload"]["canonical_content_fingerprint"] == manifest["content_fingerprint"]

    forbidden_types = {
        "source_join_evidence",
        "mart_column_lineage",
        "source_table_usage",
        "sql_column_lineage",
        "sql_table_lineage",
    }
    assert forbidden_types.isdisjoint(expected_types)

    for shard in manifest["facts"]:
        path = root / shard["path"]
        payload = path.read_bytes()
        lines = payload.splitlines()
        assert len(lines) == shard["record_count"]
        assert hashlib.sha256(payload).hexdigest() == shard["sha256"]
        assert len(payload) == shard["byte_size"]
        for line in lines:
            assert line.startswith(b"{")
            assert not line.startswith(b"[")
            json.loads(line)

    all_canonical_bytes = b"".join(path.read_bytes() for path in sorted(root.rglob("*")) if path.is_file())
    assert str(tmp_path).encode("utf-8") not in all_canonical_bytes
    assert b"absolute_file" not in all_canonical_bytes
    assert b"repo_path" not in all_canonical_bytes

    validation = validate_sql_analysis_artifact(root / "manifest.json")
    assert validation["valid"] is True
    assert validation["errors"] == []
    assert validation["content_fingerprint"] == manifest["content_fingerprint"]

    assert result["provenance"]["execution_runtime"] == "core_evidence_runtime/v1"
    assert "legacy_task_suite_profile_semantics" not in result["provenance"]


def test_canonical_shards_and_content_fingerprint_are_deterministic(tmp_path: Path) -> None:
    sql = """
    INSERT INTO mart.target (id, value)
    SELECT a.id, coalesce(a.value, b.value)
    FROM src.a a
    JOIN src.b b ON b.id = a.id;
    """
    first_out, _ = _run(tmp_path, sql, suffix="-one")
    second_out, _ = _run(tmp_path, sql, suffix="-two")
    first = _manifest(first_out)
    second = _manifest(second_out)

    assert first["content_fingerprint"] == second["content_fingerprint"]
    assert [
        (item["fact_type"], item["record_count"], item["sha256"], item["byte_size"])
        for item in first["facts"]
    ] == [
        (item["fact_type"], item["record_count"], item["sha256"], item["byte_size"])
        for item in second["facts"]
    ]
    assert (canonical_sql_root(first_out) / "coverage.json").read_bytes() == (
        canonical_sql_root(second_out) / "coverage.json"
    ).read_bytes()


def test_canonical_coverage_is_partial_for_ambiguous_join_without_guessing(tmp_path: Path) -> None:
    out, _ = _run(
        tmp_path,
        "SELECT * FROM src.a a JOIN src.b b ON id = b.id;",
    )
    manifest = _manifest(out)
    coverage = json.loads((canonical_sql_root(out) / "coverage.json").read_text(encoding="utf-8"))

    assert manifest["analysis_status"] == "partial"
    assert coverage["analysis_status"] == "partial"
    assert coverage["joins"]["by_resolution_status"] == {"partial": 1}
    assert coverage["column_usages"]["by_resolution_status"]["ambiguous"] >= 1


def test_validator_reports_tampered_shard_without_raising(tmp_path: Path) -> None:
    out, _ = _run(tmp_path, "SELECT id FROM src.a;")
    manifest = _manifest(out)
    statement_entry = next(item for item in manifest["facts"] if item["fact_type"] == "sql_statement")
    shard = canonical_sql_root(out) / statement_entry["path"]
    shard.write_bytes(shard.read_bytes() + b"{}\n")

    validation = validate_sql_analysis_artifact(canonical_sql_root(out) / "manifest.json")
    assert validation["valid"] is False
    assert {item["code"] for item in validation["errors"]} >= {
        "fact_id_missing",
        "fact_count_mismatch",
        "fact_sha256_mismatch",
        "fact_size_mismatch",
    }


def test_source_inventory_coverage_separates_non_source_values_from_resolution_failures(tmp_path: Path) -> None:
    out, _ = _run(
        tmp_path,
        """
        SELECT
          src.id,
          ${business_date} AS business_date,
          generated_value
        FROM source_table src
        LATERAL VIEW EXPLODE(src.items) generated_relation AS generated_value;
        """,
    )
    coverage = json.loads((canonical_sql_root(out) / "coverage.json").read_text(encoding="utf-8"))
    inventory = coverage["column_usages"]["source_inventory"]

    assert inventory["non_source_values"]["semantic_parameter_usages"] == 1
    assert inventory["non_source_values"]["generated_value_usages"] == 1
    assert inventory["source_field_candidate_usages"] == 2
    assert inventory["resolved_source_field_usages"] == 2
    assert inventory["unresolved_source_field_usages"] == 0
    assert inventory["source_field_resolution_rate"] == 1.0
    assert inventory["status"] == "complete"


def test_source_inventory_coverage_reports_real_ambiguity_separately(tmp_path: Path) -> None:
    out, _ = _run(
        tmp_path,
        "SELECT id FROM src.a a JOIN src.b b ON a.key = b.key;",
    )
    coverage = json.loads((canonical_sql_root(out) / "coverage.json").read_text(encoding="utf-8"))
    inventory = coverage["column_usages"]["source_inventory"]

    assert inventory["unresolved_source_field_usages"] >= 1
    assert inventory["unresolved_by_status"]["ambiguous"] >= 1
    assert inventory["unresolved_by_basis"]["ambiguous_unqualified"] >= 1
    assert inventory["status"] == "partial"
