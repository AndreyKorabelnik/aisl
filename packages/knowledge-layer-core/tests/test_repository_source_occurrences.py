from __future__ import annotations

import json
from pathlib import Path

from knowledge_layer_core.repository_source_occurrences import annotate_gap_localization, build_source_occurrence_graph


def _structure_files():
    return [
        {"repository_relative_path": "src/Main.java", "extension": ".java", "sha256": "java-sha"},
        {"repository_relative_path": "sql/load.sql", "extension": ".sql", "sha256": "sql-sha"},
        {"repository_relative_path": "cfg/model.yaml", "extension": ".yaml", "sha256": "yaml-sha"},
    ]


def test_source_occurrence_preserves_java_declaration_and_family_linkage(tmp_path: Path) -> None:
    family = {
        "family_id": "java-types", "family_kind": "java_structure", "family_label": "type_declarations",
        "source_artifact_kind": "java-type-structure-evidence", "source_schema_version": "java-type-structure-evidence/v1",
        "evidence_refs": [{"artifact_id": "java-art"}],
    }
    envelope = {
        "artifact_kind": "java-type-structure-evidence", "schema_version": "java-type-structure-evidence/v1",
        "payload": {"type_declarations": [{"type_id": "t1", "source_ref": {"repository_relative_path": "src/Main.java", "line_start": 4, "line_end": 12, "extractor": "java_tree_sitter"}}]},
    }
    graph = build_source_occurrence_graph(
        repo_id="repo", families=[family], candidates=[], coverage_gaps=[],
        structural_members={"members": []}, repository_files=_structure_files(),
        envelopes_by_identity={("java-type-structure-evidence", "java-type-structure-evidence/v1"): envelope},
        envelope_paths_by_identity={("java-type-structure-evidence", "java-type-structure-evidence/v1"): tmp_path / "java.json"},
    )
    assert len(graph["occurrences"]) == 1
    occurrence = graph["occurrences"][0]
    assert occurrence["repository_relative_path"] == "src/Main.java"
    assert occurrence["localization_kind"] == "declaration"
    assert (occurrence["line_start"], occurrence["line_end"]) == (4, 12)
    assert occurrence["content_sha256"] == "java-sha"
    assert {(item["object_kind"], item["object_id"]) for item in graph["links"]} == {
        ("structural_family", "java-types")
    }


def test_source_occurrence_reads_official_sql_fact_shard_without_source_parser(tmp_path: Path) -> None:
    shard = tmp_path / "sql-analysis" / "facts" / "sql_statement.jsonl"
    shard.parent.mkdir(parents=True)
    shard.write_text(json.dumps({
        "fact_type": "sql_statement", "sql_statement_id": "s1", "repo_id": "repo",
        "file": "sql/load.sql", "line_start": 20, "line_end": 31, "statement_type": "insert", "evidence": []
    }) + "\n", encoding="utf-8")
    envelope_path = tmp_path / "sql.json"
    envelope_path.write_text("{}", encoding="utf-8")
    envelope = {
        "artifact_kind": "sql-analysis", "schema_version": "sql-analysis/v1",
        "payload": {"fact_shards": [{"fact_type": "sql_statement", "path": "sql-analysis/facts/sql_statement.jsonl", "record_count": 1}]},
    }
    family = {
        "family_id": "sql-statements", "family_kind": "sql_structure", "family_label": "sql_statement",
        "source_artifact_kind": "sql-analysis", "source_schema_version": "sql-analysis/v1", "evidence_refs": [{"artifact_id": "sql-art"}],
    }
    graph = build_source_occurrence_graph(
        repo_id="repo", families=[family], candidates=[], coverage_gaps=[],
        structural_members={"members": []}, repository_files=_structure_files(),
        envelopes_by_identity={("sql-analysis", "sql-analysis/v1"): envelope},
        envelope_paths_by_identity={("sql-analysis", "sql-analysis/v1"): envelope_path},
    )
    assert [(item["repository_relative_path"], item["localization_kind"], item["line_start"], item["line_end"], item["content_sha256"]) for item in graph["occurrences"]] == [
        ("sql/load.sql", "statement", 20, 31, "sql-sha")
    ]


def test_source_occurrence_keeps_structured_members_file_level_and_candidate_links(tmp_path: Path) -> None:
    family = {
        "family_id": "yaml-family", "family_kind": "structured_file_shape", "family_label": "yaml-shape",
        "source_artifact_kind": "structured-file-shape-evidence", "source_schema_version": "structured-file-shape-evidence/v1",
        "evidence_refs": [{"artifact_id": "shape", "member_ids": ["m1"]}],
    }
    candidate = {"candidate_id": "cand-1", "family_id": "yaml-family", "discovery_kind": "unknown_primitive"}
    gap = {"gap_occurrence_id": "gap-1", "family_id": "yaml-family", "gap_kind": "structural_discovery_gap"}
    graph = build_source_occurrence_graph(
        repo_id="repo", families=[family], candidates=[candidate], coverage_gaps=[gap],
        structural_members={"members": [{"member_id": "m1", "family_id": "yaml-family", "repository_relative_path": "cfg/model.yaml"}]},
        repository_files=_structure_files(), envelopes_by_identity={}, envelope_paths_by_identity={},
    )
    occurrence = graph["occurrences"][0]
    assert occurrence["repository_relative_path"] == "cfg/model.yaml"
    assert occurrence["localization_kind"] == "file"
    assert occurrence["line_start"] is None and occurrence["line_end"] is None
    assert occurrence["content_sha256"] == "yaml-sha"
    assert {(item["object_kind"], item["object_id"]) for item in graph["links"]} == {
        ("structural_family", "yaml-family"), ("structural_member", "m1"),
        ("discovery_candidate", "cand-1"), ("coverage_gap", "gap-1")
    }



def test_coverage_gap_uses_only_explicit_diagnostic_source_refs(tmp_path: Path) -> None:
    gap = {
        "gap_occurrence_id": "gap-explicit", "gap_kind": "evidence_coverage_gap",
        "subject_kind": "evidence", "subject_id": "some-evidence", "family_id": None,
        "source_artifact_id": "artifact-1",
        "evidence_refs": [{"artifact_id": "artifact-1", "artifact_kind": "some-evidence", "schema_version": "some-evidence/v1"}],
        "diagnostics": [{
            "code": "partial", "message": "cfg/model.yaml mentioned here must not be parsed as provenance",
            "source_refs": [{"repository_relative_path": "cfg/model.yaml", "line_start": 7, "line_end": 9, "extractor": "official_diagnostic"}],
        }],
    }
    graph = build_source_occurrence_graph(
        repo_id="repo", families=[], candidates=[], coverage_gaps=[gap],
        structural_members={"members": []}, repository_files=_structure_files(),
        envelopes_by_identity={}, envelope_paths_by_identity={},
    )
    assert [(item["repository_relative_path"], item["line_start"], item["line_end"]) for item in graph["occurrences"]] == [("cfg/model.yaml", 7, 9)]
    link = next(item for item in graph["links"] if item["object_kind"] == "coverage_gap")
    assert link["linkage_role"] == "diagnostic_source_occurrence"
    localized = annotate_gap_localization([gap], graph["links"])[0]
    assert localized["localization_scope_kind"] == "source_occurrence"
    assert localized["localization_status"] == "localized"


def test_coverage_gap_scope_is_explicit_without_guessed_source_location() -> None:
    evidence_gap = {
        "gap_occurrence_id": "gap-evidence", "gap_kind": "evidence_coverage_gap",
        "source_artifact_id": "artifact-1", "diagnostics": [],
    }
    analysis_gap = {
        "gap_occurrence_id": "gap-analysis", "gap_kind": "analysis_scope_gap",
        "source_artifact_id": None, "diagnostics": [],
    }
    unknown_gap = {
        "gap_occurrence_id": "gap-unknown", "gap_kind": "other_gap",
        "source_artifact_id": None, "diagnostics": [],
    }
    rows = {item["gap_occurrence_id"]: item for item in annotate_gap_localization([evidence_gap, analysis_gap, unknown_gap], [])}
    assert (rows["gap-evidence"]["localization_scope_kind"], rows["gap-evidence"]["localization_status"]) == ("evidence_artifact", "not_source_localized")
    assert (rows["gap-analysis"]["localization_scope_kind"], rows["gap-analysis"]["localization_status"]) == ("unresolved", "unresolved")
    assert (rows["gap-unknown"]["localization_scope_kind"], rows["gap-unknown"]["localization_status"]) == ("unresolved", "unresolved")
