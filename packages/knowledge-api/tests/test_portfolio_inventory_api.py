from __future__ import annotations

import json
from pathlib import Path

import duckdb
from fastapi.testclient import TestClient

from knowledge_api.contract_v1.contract import KNOWLEDGE_API_PREFIX, create_contract_app
from knowledge_api.contract_v1.runtime import KnowledgeApiSettings
from knowledge_api.contract_v1.service import KnowledgeDomainService
from knowledge_layer_core.repository_inventory_schema import REPOSITORY_INVENTORY_DDL
from tests.execution_fixtures import KnowledgeArtifactSpec, publication_payload, write_execution_result


def _inventory_artifact(
    root: Path, *, repo_id: str, repository_name: str, source_kind: str = "bitbucket",
    repository_url: str | None = None, extensions: dict[str, int] | None = None,
    technologies: tuple[tuple[str, str], ...] = (),
    interfaces: tuple[dict[str, object], ...] = (),
    discovery_kind: str | None = None,
) -> Path:
    root.mkdir(parents=True)
    db = root / "knowledge-layer.duckdb"
    con = duckdb.connect(str(db))
    try:
        con.execute(REPOSITORY_INVENTORY_DDL)
        con.execute("INSERT INTO repository_inventory_build VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", [f"build-{repo_id}",repo_id,repo_id,"test","repository-inventory/v5","complete","preflight",json.dumps({"basis":"test"}),"2026-08-16T00:00:00Z","2026-08-16T00:00:01Z",json.dumps({}),json.dumps({})])
        con.execute(
            "INSERT INTO repository_inventory_source VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [f"source-{repo_id}", repo_id, repo_id, "ev-structure", "repository-structure-evidence", "repository-structure-evidence/v1", "b" * 64, "/evidence.json", json.dumps({"all_file_count": sum((extensions or {".java": 1}).values())}), json.dumps([])],
        )
        con.execute(
            "INSERT INTO repository_inventory_identity VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [repo_id, repo_id, f"registry-{repo_id}", repository_name, source_kind, repository_url, "main", json.dumps({"source": "registry"})],
        )
        ordinal = 0
        for extension, count in sorted((extensions or {".java": 1}).items()):
            con.execute(
                "INSERT INTO repository_inventory_extension VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [f"ext-{repo_id}-{ordinal}", repo_id, repo_id, extension, count, count, 0, "ev-structure"],
            )
            for index in range(count):
                con.execute(
                    "INSERT INTO repository_inventory_file VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [f"file-{repo_id}-{ordinal}-{index}", repo_id, repo_id, f"src/{ordinal}-{index}{extension}", f"{ordinal}-{index}{extension}", extension, 10, "a" * 64, True, True, "analyzer_eligible", "ev-structure"],
                )
            ordinal += 1
        first_extension = sorted((extensions or {".java": 1}).items())[0][0]
        first_path = f"src/0-0{first_extension}"
        family_id = f"family-{repo_id}"
        occurrence_id = f"occurrence-{repo_id}"
        con.execute(
            "INSERT INTO repository_inventory_structural_family VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [family_id, repo_id, repo_id, "test-observed-family", "Observed family", "repository-structure-evidence", "repository-structure-evidence/v1", 1, 50.0, discovery_kind or "none", json.dumps({"test": True}), json.dumps({"occurrences": 1}), json.dumps(["ev-structure"])],
        )
        con.execute(
            "INSERT INTO repository_inventory_source_occurrence VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [occurrence_id, repo_id, repo_id, first_path, "file", None, None, "a" * 64, json.dumps([{"source_artifact_kind": "repository-structure-evidence"}])],
        )
        con.execute(
            "INSERT INTO repository_inventory_object_occurrence VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [f"family-link-{repo_id}", repo_id, repo_id, "structural_family", family_id, occurrence_id, "observed_family_occurrence", json.dumps({"test": True})],
        )
        if discovery_kind:
            candidate_id = f"candidate-{repo_id}"
            gap_id = f"gap-{repo_id}"
            con.execute(
                "INSERT INTO repository_inventory_candidate VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [candidate_id, repo_id, repo_id, family_id, "test-observed-family", 88.0, discovery_kind, json.dumps({"test": True})],
            )
            con.execute(
                "INSERT INTO repository_inventory_coverage_gap VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [gap_id, repo_id, repo_id, "structural_discovery_gap", "structural_family", family_id, discovery_kind, "supported_with_gaps", "repository_landscape", family_id, None, "source_occurrence", "localized", json.dumps(["ev-structure"]), json.dumps([]), json.dumps({"test": True})],
            )
            con.execute(
                "INSERT INTO repository_inventory_object_occurrence VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [f"candidate-link-{repo_id}", repo_id, repo_id, "discovery_candidate", candidate_id, occurrence_id, "candidate_family_occurrence", json.dumps({"family_id": family_id})],
            )
            con.execute(
                "INSERT INTO repository_inventory_object_occurrence VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [f"gap-link-{repo_id}", repo_id, repo_id, "coverage_gap", gap_id, occurrence_id, "related_family_occurrence", json.dumps({"family_id": family_id})],
            )
        for index, (category, technology) in enumerate(technologies):
            con.execute(
                "INSERT INTO repository_inventory_technology VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [f"tech-{repo_id}-{index}", repo_id, repo_id, category, technology, "strongly_supported", "high", json.dumps({"observed": True})],
            )
        for index, interface in enumerate(interfaces):
            con.execute(
                "INSERT INTO repository_inventory_interface VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [f"iface-{repo_id}-{index}", repo_id, repo_id, interface["direction"], "http", interface.get("protocol", "http"), interface.get("operation"), interface.get("endpoint"), interface.get("http_method"), interface.get("peer_system"), interface.get("peer_resolution_status", "unresolved"), "observed", "ev-interaction", json.dumps({"repo_id": repo_id})],
            )
    finally:
        con.close()
    return db


def _publish(client: TestClient, *, system_id: str, display_name: str, db: Path, repo_id: str, token: str) -> str:
    existing = client.get(f"{KNOWLEDGE_API_PREFIX}/systems/{system_id}")
    if existing.status_code == 404:
        assert client.post(f"{KNOWLEDGE_API_PREFIX}/systems", json={"system_id": system_id, "display_name": display_name}).status_code == 201
    execution = write_execution_result(
        db.parent,
        [KnowledgeArtifactSpec(
            database=db, model_kind="repository-inventory", schema_version="repository-inventory/v5",
            materialization_id="repository-inventory", capabilities=("common.repository-inventory",),
        )],
        scope_id=repo_id, execution_token=token,
    )
    response = client.post(f"{KNOWLEDGE_API_PREFIX}/systems/{system_id}/revisions", json=publication_payload(execution))
    assert response.status_code == 201, response.text
    return response.json()["revision"]["revision_id"]


def test_portfolio_inventory_aggregates_latest_repository_revisions_and_filters(tmp_path: Path) -> None:
    settings = KnowledgeApiSettings(database_path=tmp_path / "api.sqlite3", allowed_roots=(tmp_path,))
    with TestClient(create_contract_app(service=KnowledgeDomainService(settings))) as client:
        a1 = _inventory_artifact(
            tmp_path / "a1", repo_id="repo-a", repository_name="A repo old",
            repository_url="https://bitbucket.example/projects/P/repos/A",
            technologies=(("build", "Gradle"),),
            interfaces=({"direction": "outbound", "protocol": "http", "operation": "GET /b", "endpoint": "/b", "peer_system": "beta", "peer_resolution_status": "resolved"},),
        )
        _publish(client, system_id="alpha", display_name="Alpha", db=a1, repo_id="repo-a", token="alpha-a1")
        b = _inventory_artifact(
            tmp_path / "b", repo_id="repo-b", repository_name="B repo",
            repository_url="https://bitbucket.example/projects/P/repos/B", extensions={".sql": 3},
            technologies=(("messaging", "Kafka"),),
            interfaces=({"direction": "inbound", "protocol": "kafka", "operation": "topic-x", "endpoint": "topic-x", "peer_system": None, "peer_resolution_status": "unresolved"},),
            discovery_kind="unknown_primitive",
        )
        _publish(client, system_id="alpha", display_name="Alpha", db=b, repo_id="repo-b", token="alpha-b")
        a2 = _inventory_artifact(
            tmp_path / "a2", repo_id="repo-a", repository_name="A repo current",
            repository_url="https://bitbucket.example/projects/P/repos/A", technologies=(("build", "Maven"),),
            interfaces=({"direction": "outbound", "protocol": "http", "operation": "GET /b", "endpoint": "/b", "peer_system": "beta", "peer_resolution_status": "resolved"},),
        )
        latest_a = _publish(client, system_id="alpha", display_name="Alpha", db=a2, repo_id="repo-a", token="alpha-a2")

        beta = _inventory_artifact(
            tmp_path / "beta", repo_id="repo-c", repository_name="Beta repo", source_kind="directory", technologies=(("build", "Gradle"),),
        )
        _publish(client, system_id="beta", display_name="Beta", db=beta, repo_id="repo-c", token="beta-c")
        assert client.post(f"{KNOWLEDGE_API_PREFIX}/systems", json={"system_id": "no-inventory", "display_name": "No Inventory"}).status_code == 201

        alpha = client.get(f"{KNOWLEDGE_API_PREFIX}/portfolio/inventory/alpha")
        filtered = client.get(f"{KNOWLEDGE_API_PREFIX}/portfolio/inventory", params={"has_sql": "true", "source_kind": "bitbucket"})
        facets = client.get(f"{KNOWLEDGE_API_PREFIX}/portfolio/inventory/facets")
        graph = client.get(f"{KNOWLEDGE_API_PREFIX}/portfolio/interaction-graph")
        with_unavailable = client.get(f"{KNOWLEDGE_API_PREFIX}/portfolio/inventory", params={"include_unavailable": "true"})

    assert alpha.status_code == 200, alpha.text
    alpha_json = alpha.json()
    assert alpha_json["repository_count"] == 2
    assert alpha_json["counts"]["preflight_repositories"] == 2
    assert alpha_json["counts"]["post_analysis_repositories"] == 0
    assert all(row["evaluation_phase"] == "preflight" for row in alpha_json["repositories"])
    assert {row["repo_id"] for row in alpha_json["repositories"]} == {"repo-a", "repo-b"}
    assert next(row for row in alpha_json["repositories"] if row["repo_id"] == "repo-a")["revision_id"] == latest_a
    assert {row["technology"] for row in alpha_json["technologies"]} == {"Maven", "Kafka"}
    assert alpha_json["counts"]["sql_files"] == 3
    assert alpha_json["counts"]["unresolved_peers"] == 1
    assert alpha_json["counts"]["source_occurrences"] == 2
    assert "concepts" not in alpha_json
    assert alpha_json["discovery_candidates"] == [{
        "candidate_id": "candidate-repo-b", "family_id": "family-repo-b", "family_kind": "test-observed-family",
        "structural_salience_score": 88.0, "discovery_kind": "unknown_primitive", "basis_json": {"test": True},
        "source_occurrence_ids": ["occurrence-repo-b"], "repo_id": "repo-b", "revision_id": next(row["revision_id"] for row in alpha_json["repositories"] if row["repo_id"] == "repo-b"),
    }]
    assert alpha_json["coverage_gaps"][0]["source_occurrence_ids"] == ["occurrence-repo-b"]
    assert alpha_json["coverage_gaps"][0]["localization_scope_kind"] == "source_occurrence"

    assert filtered.status_code == 200, filtered.text
    assert [row["system_id"] for row in filtered.json()["items"]] == ["alpha"]
    assert facets.status_code == 200, facets.text
    assert "concepts" not in facets.json()["facets"]
    assert facets.json()["facets"]["technologies"]["build:Gradle"] == 1
    assert graph.status_code == 200, graph.text
    observations = graph.json()["observations"]
    assert any(row["source_system"] == "alpha" and row["target_system"] == "beta" and row["target_in_portfolio"] for row in observations)
    assert graph.json()["unresolved_observation_count"] == 1
    assert with_unavailable.status_code == 200
    missing = next(row for row in with_unavailable.json()["items"] if row["system_id"] == "no-inventory")
    assert missing["inventory_status"] == "not_available"
