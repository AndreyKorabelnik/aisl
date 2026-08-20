from __future__ import annotations

import hashlib
import json
from pathlib import Path

from knowledge_layer_core.materialization_runtime import materialize, registered_materialization_ids


def _fp(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _write(path: Path, payload: dict) -> dict:
    payload = dict(payload)
    payload.setdefault("contract_version", "core_evidence_artifact_contract/v1")
    payload.setdefault("producer", {"component": "code-analyzer-core", "analyzer_id": "test", "analyzer_version": "test"})
    payload.setdefault("source_snapshot", {"source_id": "repo-a", "fingerprint": "source-fp"})
    payload.setdefault("coverage", {"coverage_status": "complete"})
    payload.setdefault("diagnostics", [])
    payload.setdefault("content_fingerprint", _fp({"kind": payload["artifact_kind"], "path": path.name}))
    payload.setdefault("artifact_id", f"artifact-{path.stem}")
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return {
        "artifact_id": payload["artifact_id"],
        "artifact_kind": payload["artifact_kind"],
        "schema_version": payload["schema_version"],
        "content_fingerprint": payload["content_fingerprint"],
        "location": {"kind": "file", "path": str(path)},
    }


def _request(items: list[dict]) -> dict:
    return {
        "schema_version": "knowledge_materialization_request/v1",
        "materialization_id": "repository-inventory",
        "scope_id": "repo-a",
        "inputs": {"evidence_artifacts": items, "knowledge_artifacts": []},
        "parameters": {},
    }


def test_repository_inventory_materializes_official_evidence_without_source_scan(tmp_path: Path) -> None:
    structure = _write(tmp_path / "structure.json", {
        "artifact_kind": "repository-structure-evidence",
        "schema_version": "repository-structure-evidence/v1",
        "coverage": {"coverage_status": "complete", "all_file_count": 2, "analyzer_eligible_file_count": 1, "outside_analyzer_frontier_file_count": 1},
        "files": [
            {"repository_relative_path": "Main.java", "file_name": "Main.java", "extension": ".java", "byte_size": 10, "sha256": "a", "readable": True, "is_symlink": False, "analyzer_eligible": True, "analyzer_frontier_status": "eligible"},
            {"repository_relative_path": "opaque.xyz", "file_name": "opaque.xyz", "extension": ".xyz", "byte_size": 3, "sha256": "b", "readable": True, "is_symlink": False, "analyzer_eligible": False, "analyzer_frontier_status": "outside_frontier"},
        ],
        "extension_inventory": [
            {"extension": ".java", "file_count": 1, "analyzer_eligible_file_count": 1, "outside_analyzer_frontier_file_count": 0},
            {"extension": ".xyz", "file_count": 1, "analyzer_eligible_file_count": 0, "outside_analyzer_frontier_file_count": 1},
        ],
        "outside_analyzer_frontier_extension_families": [{"extension": ".xyz", "file_count": 1, "status": "outside_analyzer_frontier"}],
    })
    data_model = _write(tmp_path / "data-model.json", {
        "artifact_kind": "data-model-candidate-evidence", "schema_version": "data-model-candidate-evidence/v1",
        "coverage": {"coverage_status": "complete", "score": 72, "evidence_count": 4},
        "candidate_profile": {"candidate_status": "candidate", "score": 72},
    })
    boundary_sidecar = tmp_path / "interaction-boundaries.json"
    boundary_sidecar.write_text(json.dumps({"boundaries": [
        {"interface_id": "in-1", "direction": "inbound", "boundary_kind": "rest_request", "protocol": "http", "http_method": "GET", "operation": "Controller.get", "endpoint_or_topic_resolved": "/profile"},
        {"interface_id": "out-1", "direction": "outbound", "boundary_kind": "http_outbound", "protocol": "http", "http_method": "POST", "operation": "Client.update", "endpoint_or_topic_resolved": "/profile"},
    ]}), encoding="utf-8")
    interaction = _write(tmp_path / "interaction.json", {
        "artifact_kind": "interaction-boundary-evidence", "schema_version": "interaction-boundary-evidence/v1",
        "coverage": {"coverage_status": "complete", "boundary_count": 2},
        "payload": {"boundary_catalog": {"relative_path": boundary_sidecar.name, "section": "boundaries"}},
    })
    structure["source_metadata"] = {
        "repository_id": "repo-registry-1", "repository_name": "Profile API", "source_kind": "bitbucket",
        "repository_url": "https://bitbucket.example/scm/team/profile-api.git", "default_branch": "main",
    }
    persistence = _write(tmp_path / "persistence.json", {
        "artifact_kind": "persistence-lineage-evidence", "schema_version": "persistence-lineage-evidence/v1",
        "coverage": {"coverage_status": "complete", "storage_access_count": 2},
        "payload": {"artifacts": []},
    })
    reference = _write(tmp_path / "reference.json", {
        "artifact_kind": "reference-data-evidence", "schema_version": "reference-data-evidence/v1",
        "coverage": {"coverage_status": "complete", "record_count": 5},
        "payload": {"sections": []},
    })
    sql = _write(tmp_path / "sql.json", {
        "artifact_kind": "sql-analysis", "schema_version": "sql-analysis/v1",
        "coverage": {"coverage_status": "complete", "sql_statement_count": 4},
        "payload": {"fact_shards": [{"fact_type": "sql_workflow_binding", "record_count": 1}]},
    })

    out = tmp_path / "inventory"
    result = materialize(_request([structure, data_model, interaction, persistence, reference, sql]), out)
    assert result["materialization_id"] == "repository-inventory"
    assert "repository-inventory" in registered_materialization_ids()
    report = json.loads((out / "repository_inventory.json").read_text(encoding="utf-8"))
    assert report["format"] == "repository-inventory/v5"
    assert report["evaluation"]["phase"] == "post_analysis"
    assert report["summary"]["root_file_count"] == 2
    assert report["identity"]["repository_url"] == "https://bitbucket.example/scm/team/profile-api.git"
    assert report["identity"]["repository_name"] == "Profile API"
    assert report["inputs"]["evaluation_status"] == "evaluated"
    assert len(report["inputs"]["items"]) == 1
    assert len(report["outputs"]["items"]) == 1
    assert report["outputs"]["items"][0]["peer_resolution_status"] == "unresolved"
    assert ".xyz" in {item["extension"] for item in report["outside_analyzer_frontier_extension_families"]}
    family_by_id = {item["family_id"]: item for item in report["structural_report"]["structural_families"]}
    xyz_family = next(item["family_id"] for item in report["structural_report"]["structural_families"] if item["family_label"] == ".xyz")
    assert family_by_id[xyz_family]["discovery_kind"] == "unknown_primitive"
    assert xyz_family in set(report["discovery_report"]["unknown_primitive_family_ids"])
    assert report["discovery_report"]["structural_salience"]["novelty_claim"] is False
    assert report["summary"]["unknown_primitive_count"] == 1
    assert all(item["discovery_kind"] in {"none", "unknown_primitive"} for item in report["structural_report"]["structural_families"])
    assert "concepts" not in report and "concept_report" not in report and "concept_summary" not in report
    assert any(item["subject_kind"] == "structural_family" and item["subject_id"] == xyz_family and item["discovery_kind"] == "unknown_primitive" for item in report["coverage_gaps"])
    assert (out / "knowledge-layer.duckdb").is_file()


def test_repository_inventory_keeps_unknown_frontier_visible_without_concept_layer(tmp_path: Path) -> None:
    structure = _write(tmp_path / "structure.json", {
        "artifact_kind": "repository-structure-evidence", "schema_version": "repository-structure-evidence/v1",
        "coverage": {"coverage_status": "complete", "all_file_count": 1, "analyzer_eligible_file_count": 0, "outside_analyzer_frontier_file_count": 1},
        "files": [{"repository_relative_path": "unknown.bin", "file_name": "unknown.bin", "extension": ".bin", "byte_size": 1, "sha256": "a", "readable": True, "is_symlink": False, "analyzer_eligible": False, "analyzer_frontier_status": "outside_frontier"}],
        "extension_inventory": [{"extension": ".bin", "file_count": 1, "analyzer_eligible_file_count": 0, "outside_analyzer_frontier_file_count": 1}],
        "outside_analyzer_frontier_extension_families": [{"extension": ".bin", "file_count": 1, "status": "outside_analyzer_frontier"}],
    })
    out = tmp_path / "inventory"
    materialize(_request([structure]), out)
    report = json.loads((out / "repository_inventory.json").read_text(encoding="utf-8"))
    assert report["evaluation"]["phase"] == "preflight"
    assert report["interfaces"]["evaluation_status"] == "not_evaluated"
    assert report["summary"]["unknown_primitive_count"] == 1
    assert "concepts" not in report
    assert "concept_report" not in report
    assert all(item["subject_kind"] != "concept" for item in report["coverage_matrix"])
    assert all(not str(item.get("code") or "").startswith("repository_inventory_concept_") for item in report["diagnostics"])
    family = next(item for item in report["structural_report"]["structural_families"] if item["family_label"] == ".bin")
    assert family["discovery_kind"] == "unknown_primitive"
    assert family["structural_salience_score"] > 0



def _structured_member(
    member_id: str,
    path: str,
    *,
    structure_signature: str,
    deleted_state: str = "false",
    columns_length: int = 3,
    include_columns: bool = True,
    include_column_children: bool = True,
) -> dict:
    path_observations = [
        {"path": "/", "value_type": "object", "occurrence_count": 1},
        {"path": "/deleted", "value_type": "boolean", "occurrence_count": 1},
        {"path": "/name", "value_type": "string", "occurrence_count": 1},
    ]
    state_observations = [
        {"path": "/", "value_type": "object", "state": "nonempty", "occurrence_count": 1},
        {"path": "/deleted", "value_type": "boolean", "state": deleted_state, "occurrence_count": 1},
        {"path": "/name", "value_type": "string", "state": "nonempty", "occurrence_count": 1},
    ]
    cardinality_observations = []
    if include_columns:
        path_observations.append({"path": "/columns", "value_type": "array", "occurrence_count": 1})
        state_observations.append({
            "path": "/columns", "value_type": "array",
            "state": "empty" if columns_length == 0 else "nonempty", "occurrence_count": 1,
        })
        cardinality_observations.append({"path": "/columns", "length": columns_length, "bucket": "0" if columns_length == 0 else "2-4"})
        if include_column_children and columns_length:
            path_observations.extend([
                {"path": "/columns/*", "value_type": "object", "occurrence_count": columns_length},
                {"path": "/columns/*/name", "value_type": "string", "occurrence_count": columns_length},
            ])
    return {
        "member_id": member_id,
        "repository_relative_path": path,
        "content_identity": {"sha256": hashlib.sha256(path.encode()).hexdigest(), "byte_size": 100 + columns_length},
        "syntax": "json",
        "parse_status": "parsed",
        "root_type": "object",
        "structure_signature": structure_signature,
        "variant_signature": hashlib.sha256(f"{structure_signature}:{deleted_state}:{columns_length}".encode()).hexdigest(),
        "structural_size": {
            "node_count": 10 + columns_length,
            "object_count": 1 + columns_length,
            "array_count": 1 if include_columns else 0,
            "scalar_count": 2 + columns_length,
            "max_depth": 3,
            "path_type_count": len(path_observations),
            "max_array_length": columns_length,
        },
        "path_observations": path_observations,
        "state_observations": state_observations,
        "cardinality_observations": cardinality_observations,
        "observation_truncated": False,
        "provenance": {"repository_relative_path": path},
    }


def test_repository_inventory_enriches_structural_family_with_exact_members_and_variants(tmp_path: Path) -> None:
    structure = _write(tmp_path / "structure-members.json", {
        "artifact_kind": "repository-structure-evidence", "schema_version": "repository-structure-evidence/v1",
        "coverage": {"coverage_status": "complete", "all_file_count": 6, "analyzer_eligible_file_count": 6, "outside_analyzer_frontier_file_count": 0},
        "files": [
            {"repository_relative_path": f"schemas/m{i}.json", "file_name": f"m{i}.json", "extension": ".json", "byte_size": 100 + i, "sha256": f"sha-{i}", "readable": True, "is_symlink": False, "analyzer_eligible": True, "analyzer_frontier_status": "eligible"}
            for i in range(1, 7)
        ],
        "extension_inventory": [{"extension": ".json", "file_count": 6, "analyzer_eligible_file_count": 6, "outside_analyzer_frontier_file_count": 0}],
        "outside_analyzer_frontier_extension_families": [],
    })
    dominant = "dominant-shape"
    members = [
        _structured_member("m1", "schemas/m1.json", structure_signature=dominant, columns_length=3),
        _structured_member("m2", "schemas/m2.json", structure_signature=dominant, columns_length=4),
        _structured_member("m3", "schemas/m3.json", structure_signature=dominant, columns_length=5),
        _structured_member("m4", "schemas/m4.json", structure_signature=dominant, columns_length=6),
        _structured_member("m5", "schemas/m5.json", structure_signature="empty-columns-shape", columns_length=0, include_column_children=False),
        # Boundary/partial structural variant: columns container is absent, but the remaining shallow structure
        # is still similar enough to be grouped into the same structural family.
        _structured_member("m6", "schemas/m6.json", structure_signature="missing-columns-shape", deleted_state="true", include_columns=False),
    ]
    shapes = _write(tmp_path / "shapes.json", {
        "artifact_kind": "structured-file-shape-evidence", "schema_version": "structured-file-shape-evidence/v1",
        "coverage": {"coverage_status": "complete", "candidate_file_count": 6, "parsed_file_count": 6, "failed_file_count": 0},
        "members": members,
    })

    out = tmp_path / "inventory-members"
    manifest = materialize(_request([structure, shapes]), out)
    report = json.loads((out / "repository_inventory.json").read_text(encoding="utf-8"))
    enriched = report["structural_report"]["structural_members"]
    assert enriched["evaluation_status"] == "evaluated"
    assert len(enriched["families"]) == 1
    assert len(enriched["members"]) == 6
    family = enriched["families"][0]
    assert family["occurrence_count"] == 6
    assert family["dominant_structure_signature"] == dominant
    assert family["dominant_structure_count"] == 4
    assert set(family["member_ids"]) == {f"m{i}" for i in range(1, 7)}

    by_member = {item["member_id"]: item for item in enriched["members"]}
    assert "dominant_structure" in by_member["m1"]["variant_roles"]
    assert "rare_structure" in by_member["m5"]["variant_roles"]
    assert "cardinality_extreme" in by_member["m5"]["variant_roles"]
    assert any(item["path"] == "/columns" and item["length"] == 0 and item["role"] == "minimum" for item in by_member["m5"]["cardinality_extremes"])
    assert "rare_structure" in by_member["m6"]["variant_roles"]
    assert "minority_state" in by_member["m6"]["variant_roles"]
    assert any(item["path"] == "/deleted" and item["state"] == "true" and item["family_member_count"] == 1 for item in by_member["m6"]["minority_states"])
    assert by_member["m6"]["repository_relative_path"] == "schemas/m6.json"

    assert report["summary"]["structural_member_count"] == 6
    assert report["summary"]["structured_shape_family_count"] == 1
    published_manifest = json.loads((out / "knowledge-layer-manifest.json").read_text(encoding="utf-8"))
    assert "common.repository-structural-members" in published_manifest["capabilities"]
    assert "structured-file-shape-evidence" in report["evaluation_policy"]["produce_if_missing"]

    import duckdb
    connection = duckdb.connect(str(out / "knowledge-layer.duckdb"), read_only=True)
    try:
        assert connection.execute("SELECT COUNT(*) FROM repository_inventory_structural_member").fetchone()[0] == 6
        assert connection.execute("SELECT COUNT(DISTINCT family_id) FROM repository_inventory_structural_member").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM repository_inventory_completeness").fetchone()[0] >= 1
        assert connection.execute("SELECT COUNT(*) FROM repository_inventory_source_occurrence").fetchone()[0] >= 6
        assert connection.execute("SELECT COUNT(*) FROM repository_inventory_object_occurrence WHERE object_kind='structural_family'").fetchone()[0] >= 6
        assert connection.execute("SELECT COUNT(*) FROM repository_inventory_coverage_gap WHERE discovery_kind='unclassified_concept_candidate'").fetchone()[0] == 0
    finally:
        connection.close()


def test_repository_inventory_does_not_claim_structural_member_capability_without_shape_evidence(tmp_path: Path) -> None:
    structure = _write(tmp_path / "structure-no-members.json", {
        "artifact_kind": "repository-structure-evidence", "schema_version": "repository-structure-evidence/v1",
        "coverage": {"coverage_status": "complete", "all_file_count": 1, "analyzer_eligible_file_count": 1, "outside_analyzer_frontier_file_count": 0},
        "files": [{"repository_relative_path": "a.json", "file_name": "a.json", "extension": ".json", "byte_size": 1, "sha256": "a", "readable": True, "is_symlink": False, "analyzer_eligible": True, "analyzer_frontier_status": "eligible"}],
        "extension_inventory": [{"extension": ".json", "file_count": 1, "analyzer_eligible_file_count": 1, "outside_analyzer_frontier_file_count": 0}],
        "outside_analyzer_frontier_extension_families": [],
    })
    out = tmp_path / "inventory-no-members"
    manifest = materialize(_request([structure]), out)
    report = json.loads((out / "repository_inventory.json").read_text(encoding="utf-8"))
    assert report["structural_report"]["structural_members"]["evaluation_status"] == "not_evaluated"
    assert report["summary"]["structural_member_count"] == 0
    published_manifest = json.loads((out / "knowledge-layer-manifest.json").read_text(encoding="utf-8"))
    assert "common.repository-structural-members" not in published_manifest["capabilities"]
