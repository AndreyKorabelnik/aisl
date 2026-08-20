from __future__ import annotations

import json
from pathlib import Path

import duckdb
from fastapi.testclient import TestClient

from knowledge_api.contract_v1.contract import KNOWLEDGE_API_PREFIX, create_contract_app
from knowledge_api.contract_v1.runtime import KnowledgeApiSettings
from knowledge_api.contract_v1.service import KnowledgeDomainService
from knowledge_layer_core.repository_inventory_schema import REPOSITORY_INVENTORY_DDL


def _artifact(tmp_path: Path) -> Path:
    root = tmp_path / "inventory-klc"
    root.mkdir()
    db = root / "knowledge-layer.duckdb"
    con = duckdb.connect(str(db))
    try:
        con.execute(REPOSITORY_INVENTORY_DDL)
        con.execute(
            "INSERT INTO repository_inventory_build VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ["build-1", "scope", "repo-1", "test", "repository-inventory/v5", "complete", "preflight", json.dumps({"basis": "bounded_preflight"}), "2026-08-16T00:00:00Z", "2026-08-16T00:00:01Z", json.dumps({}), json.dumps({})],
        )
        con.execute(
            "INSERT INTO repository_inventory_source VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ["s1", "scope", "repo-1", "ev-structure", "repository-structure-evidence", "repository-structure-evidence/v1", "b" * 64, "/evidence.json", json.dumps({"all_file_count": 1}), json.dumps([])],
        )
        con.execute(
            "INSERT INTO repository_inventory_identity VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ["scope", "repo-1", "registry-1", "Repo", "bitbucket", "https://bitbucket.example/projects/P/repos/R", "main", json.dumps({"source": "registry"})],
        )
        con.execute(
            "INSERT INTO repository_inventory_file VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ["f1", "scope", "repo-1", "src/A.java", "A.java", ".java", 10, "a" * 64, True, True, "analyzer_eligible", "ev-structure"],
        )
        con.execute(
            "INSERT INTO repository_inventory_extension VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ["e1", "scope", "repo-1", ".java", 1, 1, 0, "ev-structure"],
        )
        con.execute(
            "INSERT INTO repository_inventory_technology VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ["t1", "scope", "repo-1", "build", "Gradle", "observed", "confirmed", json.dumps({"file": "build.gradle"})],
        )
        con.execute(
            "INSERT INTO repository_inventory_interface VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ["i1", "scope", "repo-1", "outbound", "http", "http", "GET /profile", "/profile", "GET", None, "unresolved", "observed", "ev-int", json.dumps({"evidence_id": "b1"})],
        )
        con.execute(
            "INSERT INTO repository_inventory_structural_family VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ["fam-1", "scope", "repo-1", "java-model", "Java model", "data-model-candidate-evidence", "data-model-candidate-evidence/v1", 3, 80.0, "none", json.dumps({"reason": "core_observed_structure"}), json.dumps({"types": 3}), json.dumps(["ev-dm"])],
        )
        con.execute(
            "INSERT INTO repository_inventory_structural_family VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ["fam-2", "scope", "repo-1", "unknown-shape", "Unknown shape", "repository-structure-evidence", "repository-structure-evidence/v1", 4, 91.0, "unknown_primitive", json.dumps({"reason": "outside_frontier"}), json.dumps({"outside_analyzer_frontier_extension_family": True}), json.dumps(["ev-structure"])],
        )
        con.execute(
            "INSERT INTO repository_inventory_candidate VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ["cand-1", "scope", "repo-1", "fam-2", "unknown-shape", 91.0, "unknown_primitive", json.dumps({"reason": "outside_frontier"})],
        )
        con.execute(
            "INSERT INTO repository_inventory_completeness VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ["comp-1", "scope", "repo-1", "evidence", "data-model-candidate-evidence", "complete", "evaluated", json.dumps({"evidence": ["ev-dm"]}), json.dumps([])],
        )
        con.execute(
            "INSERT INTO repository_inventory_coverage_gap VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ["gap-1", "scope", "repo-1", "structural_discovery_gap", "structural_family", "fam-2", "unknown_primitive", "supported_with_gaps", "repository_landscape", "fam-2", "ev-structure", "source_occurrence", "localized", json.dumps(["ev-structure"]), json.dumps([]), json.dumps({"reason": "outside_frontier"})],
        )
        con.execute(
            "INSERT INTO repository_inventory_source_occurrence VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ["occ-1", "scope", "repo-1", "src/A.java", "declaration", 3, 9, "a" * 64, json.dumps([{"source_artifact_kind": "data-model-candidate-evidence", "source_schema_version": "data-model-candidate-evidence/v1"}])],
        )
        con.execute(
            "INSERT INTO repository_inventory_object_occurrence VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ["link-1", "scope", "repo-1", "structural_family", "fam-1", "occ-1", "observed_family_occurrence", json.dumps({"evidence_refs": ["ev-dm"]})],
        )
        con.execute(
            "INSERT INTO repository_inventory_diagnostic VALUES (?, ?, ?, ?, ?, ?, ?)",
            ["d1", "scope", "repo-1", "peer_unresolved", "info", "Peer system is unresolved", json.dumps({"interface_id": "i1"})],
        )
    finally:
        con.close()
    return db


def _publish(client: TestClient, artifact: Path) -> str:
    from tests.execution_fixtures import KnowledgeArtifactSpec, publication_payload, write_execution_result

    assert client.post(
        f"{KNOWLEDGE_API_PREFIX}/systems",
        json={"system_id": "inventory", "display_name": "Inventory"},
    ).status_code == 201
    execution = write_execution_result(
        artifact.parent,
        [
            KnowledgeArtifactSpec(
                database=artifact,
                model_kind="repository-inventory",
                schema_version="repository-inventory/v5",
                materialization_id="repository-inventory",
                capabilities=(
                    "common.repository-inventory",
                    "common.repository-identity",
                    "common.repository-technologies",
                    "common.repository-interfaces",
                    "common.repository-inputs-outputs",
                    "common.repository-structural-families",
                    "common.repository-discovery",
                    "common.repository-coverage-gaps",
                    "common.repository-source-occurrences",
                ),
            )
        ],
        scope_id="repo-1",
        execution_token="run-inventory",
    )
    response = client.post(
        f"{KNOWLEDGE_API_PREFIX}/systems/inventory/revisions",
        json=publication_payload(execution),
    )
    assert response.status_code == 201, response.text
    return response.json()["revision"]["revision_id"]


def test_repository_inventory_http_contract(tmp_path: Path) -> None:
    artifact = _artifact(tmp_path)
    settings = KnowledgeApiSettings(database_path=tmp_path / "api.sqlite3", allowed_roots=(tmp_path,))
    with TestClient(create_contract_app(service=KnowledgeDomainService(settings))) as client:
        revision = _publish(client, artifact)
        summary = client.get(f"{KNOWLEDGE_API_PREFIX}/systems/inventory/repository-inventory", params={"revision_id": revision})
        coverage = client.get(f"{KNOWLEDGE_API_PREFIX}/systems/inventory/repository-inventory/coverage", params={"revision_id": revision})
        outputs = client.get(f"{KNOWLEDGE_API_PREFIX}/systems/inventory/repository-inventory/outputs", params={"revision_id": revision})
        technologies = client.get(f"{KNOWLEDGE_API_PREFIX}/systems/inventory/repository-inventory/technologies", params={"revision_id": revision})
        discovery = client.get(f"{KNOWLEDGE_API_PREFIX}/systems/inventory/repository-inventory/discovery", params={"revision_id": revision, "discovery_kind": "unknown_primitive", "min_salience_score": 90})
        gaps = client.get(f"{KNOWLEDGE_API_PREFIX}/systems/inventory/repository-inventory/coverage-gaps", params={"revision_id": revision, "gap_kind": "structural_discovery_gap"})
        occurrences = client.get(f"{KNOWLEDGE_API_PREFIX}/systems/inventory/repository-inventory/source-occurrences", params={"revision_id": revision, "object_kind": "structural_family", "object_id": "fam-1"})
        occurrence = client.get(f"{KNOWLEDGE_API_PREFIX}/systems/inventory/repository-inventory/source-occurrences/occ-1", params={"revision_id": revision})
    assert summary.status_code == 200, summary.text
    assert summary.json()["repository_inventory_schema_version"] == "repository-inventory-query/v5"
    assert summary.json()["inventory_schema_version"] == "repository-inventory/v5"
    assert summary.json()["evaluation_phase"] == "preflight"
    assert summary.json()["identity"]["repository_url"].startswith("https://bitbucket.example/")
    assert summary.json()["counts"]["outbound_interfaces"] == 1
    assert summary.json()["counts"]["structural_families"] == 2
    assert "concepts" not in summary.json()
    assert coverage.status_code == 200, coverage.text
    assert coverage.json()["repository_inventory_schema_version"] == "repository-inventory-coverage-query/v5"
    assert coverage.json()["analyzer_frontier"]["analyzer_eligible"] == 1
    assert "concept_evaluation" not in coverage.json()
    assert coverage.json()["gap_counts"]["structural_discovery_gap"] == 1
    assert outputs.json()["items"][0]["peer_system"] is None
    assert technologies.json()["items"][0]["technology"] == "Gradle"
    assert discovery.json()["page"]["total"] == 1
    assert discovery.json()["items"][0]["discovery_kind"] == "unknown_primitive"
    assert discovery.json()["items"][0]["structural_salience_score"] == 91.0
    assert gaps.json()["page"]["total"] == 1
    assert gaps.json()["items"][0]["subject_id"] == "fam-2"
    assert gaps.json()["items"][0]["localization_scope_kind"] == "source_occurrence"
    assert occurrences.status_code == 200, occurrences.text
    assert occurrences.json()["page"]["total"] == 1
    assert occurrences.json()["items"][0]["repository_relative_path"] == "src/A.java"
    assert occurrences.json()["items"][0]["localization_kind"] == "declaration"
    assert occurrence.status_code == 200, occurrence.text
    assert occurrence.json()["occurrence"]["occurrence_id"] == "occ-1"
    assert occurrence.json()["object_links"][0]["object_id"] == "fam-1"


def test_repository_inventory_missing_canonical_relations_is_explicit(tmp_path: Path) -> None:
    root = tmp_path / "broken-inventory"
    root.mkdir()
    db = root / "knowledge-layer.duckdb"
    con = duckdb.connect(str(db))
    try:
        con.execute("CREATE TABLE unrelated(value VARCHAR)")
    finally:
        con.close()
    settings = KnowledgeApiSettings(database_path=tmp_path / "api-broken.sqlite3", allowed_roots=(tmp_path,))
    from tests.execution_fixtures import KnowledgeArtifactSpec, publication_payload, write_execution_result

    with TestClient(create_contract_app(service=KnowledgeDomainService(settings))) as client:
        assert client.post(
            f"{KNOWLEDGE_API_PREFIX}/systems",
            json={"system_id": "broken", "display_name": "Broken"},
        ).status_code == 201
        execution = write_execution_result(
            root,
            [
                KnowledgeArtifactSpec(
                    database=db,
                    model_kind="repository-inventory",
                    schema_version="repository-inventory/v5",
                    materialization_id="repository-inventory",
                    capabilities=("common.repository-inventory",),
                )
            ],
            scope_id="repo-broken",
            execution_token="run-broken",
        )
        pub = client.post(f"{KNOWLEDGE_API_PREFIX}/systems/broken/revisions", json=publication_payload(execution))
        assert pub.status_code == 201, pub.text
        revision = pub.json()["revision"]["revision_id"]
        response = client.get(f"{KNOWLEDGE_API_PREFIX}/systems/broken/repository-inventory", params={"revision_id": revision})
    assert response.status_code == 409, response.text
    assert response.json()["code"] == "repository_inventory_unavailable"
