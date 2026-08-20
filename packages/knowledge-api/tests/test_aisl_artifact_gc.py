from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from fastapi.testclient import TestClient

from knowledge_api.contract_v1.contract import KNOWLEDGE_API_PREFIX, create_contract_app
from knowledge_api.contract_v1.models import PublishedArtifact
from knowledge_api.contract_v1.runtime import KnowledgeApiSettings, sha256_file
from knowledge_api.contract_v1.service import KnowledgeDomainService
from knowledge_api.publication import stable_fingerprint
from tests.execution_fixtures import KnowledgeArtifactSpec, publication_payload, write_execution_result
from tests.test_aisl_observed_persistence import _write_derived_model, _write_observed_java


def _mixed_execution(root: Path, *, scope_id: str, token: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    derived = root / "code.duckdb"
    _write_derived_model(derived)
    execution = write_execution_result(
        root,
        [KnowledgeArtifactSpec(
            derived,
            "code-declared-data-model",
            "code-declared-data-model/v1",
            "code-declared-data-model",
            ("common.code-declared-data-model",),
            artifact_id="code-product",
        )],
        scope_id=scope_id,
        execution_token=token,
    )
    observed_path = root / "java-type-structure-evidence.json"
    observed_payload = _write_observed_java(observed_path)
    payload = json.loads(execution.read_text(encoding="utf-8"))
    payload["evidence_artifacts"] = [{
        "artifact_id": observed_payload["artifact_id"],
        "artifact_kind": observed_payload["artifact_kind"],
        "schema_version": observed_payload["schema_version"],
        "contract_version": observed_payload["contract_version"],
        "content_fingerprint": observed_payload["content_fingerprint"],
        "coverage": observed_payload["coverage"],
        "diagnostics": {"count": 0, "code_counts": {}, "severity_counts": {}},
        "provenance": {"producer": observed_payload["producer"], "source_snapshot": observed_payload["source_snapshot"]},
        "status": "completed",
        "location": {
            "kind": "file",
            "path": str(observed_path),
            "sha256": sha256_file(observed_path),
            "bytes": observed_path.stat().st_size,
        },
    }]
    payload["materialization_executions"][0]["input_artifact_ids"] = [observed_payload["artifact_id"]]
    payload["result_fingerprint"] = stable_fingerprint({k: v for k, v in payload.items() if k != "result_fingerprint"})
    execution.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return execution


def _client(tmp_path: Path) -> tuple[TestClient, KnowledgeDomainService, Path]:
    store = tmp_path / "aisl" / "artifact-store"
    settings = KnowledgeApiSettings(
        database_path=tmp_path / "aisl" / "catalog.sqlite3",
        allowed_roots=(tmp_path,),
        artifact_store_path=store,
    )
    service = KnowledgeDomainService(settings)
    return TestClient(create_contract_app(service=service)), service, store


def _publish(client: TestClient, *, system_id: str, execution: Path) -> dict:
    response = client.post(
        f"{KNOWLEDGE_API_PREFIX}/systems/{system_id}/revisions",
        json=publication_payload(execution),
    )
    assert response.status_code == 201, response.text
    return response.json()["revision"]


def test_gc_plan_and_sweep_remove_only_old_unreachable_and_crash_staging(tmp_path: Path) -> None:
    producer = tmp_path / "producer"
    execution = _mixed_execution(producer, scope_id="gc-demo", token="v1")
    client, service, store = _client(tmp_path)
    with client:
        assert client.post(
            f"{KNOWLEDGE_API_PREFIX}/systems",
            json={"system_id": "gc-demo", "display_name": "GC Demo"},
        ).status_code == 201
        revision = _publish(client, system_id="gc-demo", execution=execution)
        revision_id = revision["revision_id"]

        # Create one canonical but unreferenced CAS blob. GC must infer no
        # reachability from its mere presence in the store.
        orphan_source = tmp_path / "orphan.bin"
        orphan_source.write_bytes(b"unreachable-artifact")
        orphan = PublishedArtifact(
            uri=orphan_source.resolve().as_uri(),
            sha256=sha256_file(orphan_source),
            media_type="application/octet-stream",
            byte_size=orphan_source.stat().st_size,
        )
        imported = service.artifact_store.import_artifact(orphan, orphan_source)
        orphan_path = service.artifact_store.path_for_digest(imported.sha256)
        os.utime(orphan_path, (1, 1))

        old_staging = store / ".staging" / "crash-old.tmp"
        old_staging.write_bytes(b"partial")
        os.utime(old_staging, (1, 1))
        young_staging = store / ".staging" / "active-young.tmp"
        young_staging.write_bytes(b"active")

        unmanaged = store / "sha256" / "xx" / "not-a-digest" / "mystery"
        unmanaged.parent.mkdir(parents=True, exist_ok=True)
        unmanaged.write_bytes(b"unknown")

        plan = client.post(
            f"{KNOWLEDGE_API_PREFIX}/artifact-store/gc",
            json={"mode": "plan", "grace_period_seconds": 60, "max_details": 100},
        )
        assert plan.status_code == 200, plan.text
        body = plan.json()
        assert body["retained_revision_count"] == 1
        assert body["eligible_blob_count"] == 1
        assert body["deleted_blob_count"] == 0
        assert body["eligible_blob_sha256"] == [imported.sha256]
        assert body["eligible_staging_file_count"] == 1
        assert body["deleted_staging_file_count"] == 0
        assert body["unmanaged_entry_count"] == 1
        assert orphan_path.exists()
        assert old_staging.exists()
        assert young_staging.exists()
        assert unmanaged.exists()

        rejected = client.post(
            f"{KNOWLEDGE_API_PREFIX}/artifact-store/gc",
            json={"mode": "sweep", "grace_period_seconds": 60},
        )
        assert rejected.status_code == 422

        swept = client.post(
            f"{KNOWLEDGE_API_PREFIX}/artifact-store/gc",
            json={
                "mode": "sweep",
                "grace_period_seconds": 60,
                "confirm_delete_unreferenced": True,
                "max_details": 100,
            },
        )
        assert swept.status_code == 200, swept.text
        result = swept.json()
        assert result["deleted_blob_count"] == 1
        assert result["deleted_staging_file_count"] == 1
        assert not orphan_path.exists()
        assert not old_staging.exists()
        assert young_staging.exists()
        assert unmanaged.exists(), "unknown store entries must never be guessed as GC-safe"

        observed = client.get(
            f"{KNOWLEDGE_API_PREFIX}/systems/gc-demo/knowledge-items/java_type_structure_pilot/type_declaration/type-customer",
            params={"revision_id": revision_id},
        )
        derived = client.get(
            f"{KNOWLEDGE_API_PREFIX}/systems/gc-demo/knowledge-items/code-product/declared_object/type-customer-occ",
            params={"revision_id": revision_id},
        )
        assert observed.status_code == 200, observed.text
        assert derived.status_code == 200, derived.text


def test_gc_keeps_active_and_superseded_revisions_readable(tmp_path: Path) -> None:
    client, _, _ = _client(tmp_path)
    producer_v1 = tmp_path / "producer-v1"
    producer_v2 = tmp_path / "producer-v2"
    execution_v1 = _mixed_execution(producer_v1, scope_id="gc-history", token="v1")
    execution_v2 = _mixed_execution(producer_v2, scope_id="gc-history", token="v2")

    with client:
        assert client.post(
            f"{KNOWLEDGE_API_PREFIX}/systems",
            json={"system_id": "gc-history", "display_name": "GC History"},
        ).status_code == 201
        first = _publish(client, system_id="gc-history", execution=execution_v1)
        second = _publish(client, system_id="gc-history", execution=execution_v2)
        assert first["revision_id"] != second["revision_id"]

        revisions = client.get(f"{KNOWLEDGE_API_PREFIX}/systems/gc-history/revisions").json()["items"]
        assert {item["state"] for item in revisions} == {"active", "superseded"}

        shutil.rmtree(producer_v1)
        shutil.rmtree(producer_v2)
        swept = client.post(
            f"{KNOWLEDGE_API_PREFIX}/artifact-store/gc",
            json={"mode": "sweep", "grace_period_seconds": 0, "confirm_delete_unreferenced": True},
        )
        assert swept.status_code == 200, swept.text
        assert swept.json()["deleted_blob_count"] == 0

        for revision_id in (first["revision_id"], second["revision_id"]):
            observed = client.get(
                f"{KNOWLEDGE_API_PREFIX}/systems/gc-history/knowledge-items/java_type_structure_pilot/type_declaration/type-customer",
                params={"revision_id": revision_id},
            )
            derived = client.get(
                f"{KNOWLEDGE_API_PREFIX}/systems/gc-history/knowledge-items/code-product/declared_object/type-customer-occ",
                params={"revision_id": revision_id},
            )
            assert observed.status_code == 200, observed.text
            assert derived.status_code == 200, derived.text


def test_system_delete_removes_reachability_then_gc_reclaims_bytes(tmp_path: Path) -> None:
    producer = tmp_path / "producer"
    execution = _mixed_execution(producer, scope_id="gc-delete", token="v1")
    client, _, store = _client(tmp_path)
    with client:
        assert client.post(
            f"{KNOWLEDGE_API_PREFIX}/systems",
            json={"system_id": "gc-delete", "display_name": "GC Delete"},
        ).status_code == 201
        _publish(client, system_id="gc-delete", execution=execution)
        assert list((store / "sha256").rglob("blob"))

        deleted = client.delete(f"{KNOWLEDGE_API_PREFIX}/systems/gc-delete")
        assert deleted.status_code == 200, deleted.text
        assert deleted.json()["deleted_revision_count"] == 1

        plan = client.post(
            f"{KNOWLEDGE_API_PREFIX}/artifact-store/gc",
            json={"mode": "plan", "grace_period_seconds": 0, "max_details": 1000},
        )
        assert plan.status_code == 200, plan.text
        body = plan.json()
        assert body["retained_revision_count"] == 0
        assert body["reachable_digest_count"] == 0
        assert body["eligible_blob_count"] == body["store_blob_count"]
        assert body["eligible_blob_count"] > 0

        swept = client.post(
            f"{KNOWLEDGE_API_PREFIX}/artifact-store/gc",
            json={"mode": "sweep", "grace_period_seconds": 0, "confirm_delete_unreferenced": True},
        )
        assert swept.status_code == 200, swept.text
        assert swept.json()["deleted_blob_count"] == body["eligible_blob_count"]
        assert not list((store / "sha256").rglob("blob"))


def test_gc_reports_missing_referenced_blob_and_does_not_infer_replacement(tmp_path: Path) -> None:
    producer = tmp_path / "producer"
    execution = _mixed_execution(producer, scope_id="gc-missing", token="v1")
    client, service, _ = _client(tmp_path)
    with client:
        assert client.post(
            f"{KNOWLEDGE_API_PREFIX}/systems",
            json={"system_id": "gc-missing", "display_name": "GC Missing"},
        ).status_code == 201
        revision = _publish(client, system_id="gc-missing", execution=execution)
        descriptor = next(
            member
            for product in revision["knowledge_artifacts"]
            if product["origin_kind"] == "observed"
            for member in product["physical_artifacts"]
            if member["role"] == "descriptor"
        )
        service.artifact_store.path_for_digest(descriptor["sha256"]).unlink()

        plan = client.post(
            f"{KNOWLEDGE_API_PREFIX}/artifact-store/gc",
            json={"mode": "plan", "grace_period_seconds": 0, "max_details": 100},
        )
        assert plan.status_code == 200, plan.text
        body = plan.json()
        assert body["missing_referenced_blob_count"] == 1
        assert body["missing_referenced_sha256"] == [descriptor["sha256"]]
        assert body["deleted_blob_count"] == 0
