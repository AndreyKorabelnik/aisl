from __future__ import annotations

import json
from pathlib import Path

from code_analyzer_core.models import AnalysisResult, EvidenceRef, Fact
from code_analyzer_core.prepared_artifacts.reference_data_fact_base import build_reference_data_fact_base
from code_analyzer_core.scanners.db_schema_scanner import scan_database_schema
from code_analyzer_core.scanners.repo_scanner import scan_files


def test_reference_data_fact_base_groups_only_observed_facts(tmp_path: Path) -> None:
    result = AnalysisResult(
        system_name="generic-system",
        project_code="GEN",
        repo_path="/repo",
        stack=["java", "sql"],
        files_analyzed=3,
    )
    result.facts.extend([
        Fact(
            fact_type="db_schema_table",
            name="public.state_values",
            properties={
                "db_schema_table_id": "table_state_values",
                "schema_name": "public",
                "table_name": "state_values",
                "qualified_table_name": "public.state_values",
            },
            evidence=[EvidenceRef(file_path="db/changelog.yaml", line_start=1)],
        ),
        Fact(
            fact_type="declared_value_set",
            name="StateCodes",
            properties={
                "declared_value_set_id": "declared_value_set_state_codes",
                "syntax_kind": "java_enum",
                "source_set": "production",
                "entries_count": 2,
                "sample_entries": [{"key": "A"}, {"key": "B"}],
                "extraction_truncated": False,
            },
            evidence=[EvidenceRef(file_path="StateCodes.java", line_start=1)],
        ),
        Fact(
            fact_type="literal_data_write",
            name="public.state_values",
            properties={
                "literal_data_write_id": "literal_data_write_state",
                "qualified_table_name": "public.state_values",
                "operation": "insert",
                "columns": ["code", "name"],
                "values": {"code": {"value": "A", "value_kind": "value"}},
                "parameterized": False,
            },
            evidence=[EvidenceRef(file_path="db/changelog.yaml", line_start=20)],
        ),
        Fact(
            fact_type="sql_join_observation",
            name="public.object_table->public.state_values",
            properties={
                "source_table": "public.object_table",
                "target_table": "public.state_values",
                "join_condition_preview": "s.code = o.state_code",
                "observation_status": "extracted",
            },
            evidence=[EvidenceRef(file_path="query.sql", line_start=4)],
        ),
        Fact(
            fact_type="storage_lineage_gap",
            name="write source unresolved",
            properties={"storage_lineage_gap_id": "gap_1", "gap_kind": "field_mapping_not_resolved"},
            evidence=[EvidenceRef(file_path="Service.java", line_start=10)],
        ),
    ])
    result.coverage["declared_value_scan"] = {
        "files_discovered": 3,
        "files_scanned": 3,
        "files_skipped": 0,
        "semantic_classification_performed": False,
    }

    status = build_reference_data_fact_base(result=result, out_dir=tmp_path)

    assert status["status"] == "success"
    artifact = json.loads((tmp_path / "compact" / "reference_data_fact_base.json").read_text(encoding="utf-8"))
    assert artifact["semantic_policy"]["analyzer_classifies_nsi_or_reference_data"] is False
    assert artifact["semantic_policy"]["analyzer_forms_nsi_candidates"] is False
    assert artifact["summary"]["declared_value_sets"] == 1
    assert artifact["summary"]["literal_data_writes"] == 1
    assert artifact["summary"]["join_observations"] == 1
    assert artifact["summary"]["unresolved_gaps"] == 1
    assert "candidates" not in artifact
    assert (tmp_path / "compact" / "reference_data_fact_base" / "declared_value_sets.jsonl").exists()
    assert (tmp_path / "compact" / "reference_data_fact_base" / "literal_data_writes.jsonl").exists()
    assert (tmp_path / "compact" / "reference_data_fact_base" / "join_observations.jsonl").exists()


def test_liquibase_yaml_insert_is_literal_data_write_not_reference_classification(tmp_path: Path) -> None:
    changelog = tmp_path / "src" / "main" / "resources" / "db" / "changelog.yaml"
    changelog.parent.mkdir(parents=True)
    changelog.write_text(
        """
databaseChangeLog:
  - changeSet:
      id: add-state
      author: dev
      changes:
        - insert:
            schemaName: public
            tableName: state_values
            columns:
              - column: {name: code, value: A}
              - column: {name: label, value: Active}
""",
        encoding="utf-8",
    )

    schema = scan_database_schema(
        tmp_path,
        scan_files(tmp_path),
        repo_id="repo",
        project_code="GEN",
        system_name="generic-system",
    )

    assert len(schema["literal_data_writes"]) == 1
    write = schema["literal_data_writes"][0]
    assert write["fact_type"] == "literal_data_write"
    assert write["qualified_table_name"] == "public.state_values"
    assert write["operation"] == "insert"
    assert write["parameterized"] is False
    assert write["values"]["code"]["value"] == "A"
    assert "reference" not in " ".join(write.keys()).lower()
    assert all("table_role" not in table for table in schema["tables"])


def test_reference_data_fact_base_infers_source_set_for_all_sections(tmp_path: Path) -> None:
    result = AnalysisResult(
        system_name="generic-system", project_code="GEN", repo_path="/repo", stack=["java"], files_analyzed=1
    )
    result.facts.append(Fact(
        fact_type="storage_access",
        name="read state_values",
        properties={"storage_access_id": "storage_access_1", "table": "state_values"},
        evidence=[EvidenceRef(file_path="src/test/java/StateRepositoryTest.java", line_start=10)],
    ))
    build_reference_data_fact_base(result=result, out_dir=tmp_path)
    rows = (tmp_path / "compact" / "reference_data_fact_base" / "storage_operations.jsonl").read_text(encoding="utf-8").splitlines()
    item = json.loads(rows[0])
    assert item["properties"]["source_set"] == "test"
