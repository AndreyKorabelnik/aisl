from __future__ import annotations

from copy import deepcopy
import inspect
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from static_analysis_runner import knowledge_execution as execution_module
from static_analysis_runner import knowledge_materialization_executor as materialization_executor_module
from static_analysis_runner.cli import app
from static_analysis_runner.io_utils import stable_fingerprint, write_json
from static_analysis_runner.producer_reuse import ProducerArtifactStore
from static_analysis_runner.knowledge_execution import (
    _existing_artifacts,
    _registered_evidence,
    execute_knowledge_execution_plan,
    validate_knowledge_execution_result,
)
from static_analysis_runner.knowledge_execution_planning import (
    artifacts_from_repository_run_manifest,
    build_knowledge_input_inventory,
    compile_knowledge_execution_plan,
    inspect_repository_source,
)
from static_analysis_runner.evidence_executor import execute_core_evidence_plan
from test_evidence_executor import _fake_core, _plan as _evidence_plan
from test_knowledge_execution_planning import _catalog_for
from test_knowledge_planning import _core_evidence_payload, _klc_payload, _profile
from test_knowledge_materialization_executor import _catalog as _materialization_catalog

runner = CliRunner()


def _inputs(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "Customer.java").write_text("class Customer { String id; }", encoding="utf-8")
    core = _core_evidence_payload()
    klc_path = _materialization_catalog(tmp_path / "klc.json")
    klc = json.loads(klc_path.read_text(encoding="utf-8"))
    inventory = build_knowledge_input_inventory(
        scope_kind="repository",
        scope_id="client-profile",
        source_snapshots=[inspect_repository_source(repository, source_id="client-profile")],
        core_evidence_catalog=core,
        materialization_catalog=klc,
    )
    knowledge_catalog = _catalog_for(core, klc)
    plan = compile_knowledge_execution_plan(
        knowledge_catalog=knowledge_catalog,
        knowledge_profile=_profile("code-declared-data-model", scope="repository"),
        input_inventory=inventory,
        core_evidence_catalog=core,
        materialization_catalog=klc,
    )
    plan_path = tmp_path / "plan.json"
    core_path = tmp_path / "core.json"
    write_json(plan_path, plan)
    write_json(core_path, core)
    return plan_path, core_path, klc_path, repository




def test_partial_evidence_status_is_preserved_for_fresh_and_reused_inputs(tmp_path: Path) -> None:
    artifact_path = tmp_path / "partial-evidence.json"
    artifact_path.write_text("{}\n", encoding="utf-8")
    manifest_path = tmp_path / "repository_analysis_run_manifest.json"
    manifest = {
        "schema_version": "static_repository_analysis_run_manifest/v1",
        "status": "completed",
        "repository": {"repo_id": "repo-a"},
        "evidence_artifacts": [{
            "artifact_id": "partial-artifact",
            "artifact_kind": "sql-analysis",
            "schema_version": "sql-analysis/v1",
            "content_fingerprint": "a" * 64,
            "status": "partial",
            "coverage": {"coverage_status": "partial", "gap_count": 3},
            "diagnostics": {"count": 1},
            "location": {"kind": "file", "path": artifact_path.name},
        }],
    }
    write_json(manifest_path, manifest)

    fresh = _registered_evidence(manifest=manifest, manifest_path=manifest_path)
    assert fresh[0]["status"] == "partial"
    assert fresh[0]["coverage"]["gap_count"] == 3
    assert fresh[0]["diagnostics"]["count"] == 1

    plan = {
        "graph": {
            "nodes": [{
                "node_kind": "typed_evidence_artifact",
                "satisfaction_mode": "existing_typed_artifact",
                "artifact": {
                    **fresh[0],
                    "availability": "available",
                },
            }]
        }
    }
    reused, knowledge = _existing_artifacts(plan)
    assert knowledge == []
    assert reused[0]["status"] == "partial"
    assert reused[0]["coverage"]["gap_count"] == 3
    assert reused[0]["diagnostics"]["count"] == 1


def test_knowledge_execute_runs_full_generic_path(tmp_path: Path) -> None:
    plan, core, klc, _ = _inputs(tmp_path)
    output = tmp_path / "knowledge-execution"
    result = execute_knowledge_execution_plan(
        execution_plan=plan,
        core_evidence_catalog=core,
        materialization_catalog=klc,
        output=output,
        core_command=str(_fake_core(tmp_path / "fake-core")),
        replace=True,
    )

    assert result["schema_version"] == "knowledge_execution_result/v2"
    assert result["status"] == "completed"
    assert result["execution_order"] == [
        "analyzer:java-type-structure-analyzer:client-profile",
        "materialization:code-declared-data-model",
    ]
    assert [item["node_kind"] for item in result["node_executions"]] == [
        "core_evidence_analyzer",
        "knowledge_materialization",
    ]
    assert len(result["evidence_artifacts"]) == 1
    assert len(result["knowledge_artifacts"]) == 1
    assert "common.code-declared-data-model" in result["published_capabilities"]
    assert "task_suite_profile_semantics" not in result["semantic_policy"]
    assert "legacy_fallback" not in result["semantic_policy"]
    assert "dual_write" not in result["semantic_policy"]
    assert (output / "knowledge_execution_result.json").is_file()
    assert validate_knowledge_execution_result(result) == result


def test_content_addressed_klc_reuse_skips_worker_and_detects_corruption(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan, core, klc, _ = _inputs(tmp_path)
    cache_root = tmp_path / "producer-cache"
    fake_core = _fake_core(tmp_path / "fake-core-klc-reuse")

    first = execute_knowledge_execution_plan(
        execution_plan=plan,
        core_evidence_catalog=core,
        materialization_catalog=klc,
        output=tmp_path / "execution-1",
        core_command=str(fake_core),
        producer_cache_root=cache_root,
        replace=True,
    )
    assert first["producer_reuse"]["summary"] == {"built": 2, "reused": 0}
    materialization_decision = next(
        item for item in first["producer_reuse"]["decisions"]
        if item["producer_kind"] == "knowledge-materialization"
    )
    assert materialization_decision["action"] == "built"
    assert first["node_executions"][-1]["execution_action"] == "built"
    assert first["knowledge_artifacts"][0]["producer_reuse_key"] == materialization_decision["reuse_key"]

    # Core version lookup remains callable, but neither Core analysis nor KLC worker may execute.
    fake_core.write_text(
        "#!/usr/bin/env python3\n"
        "import sys\n"
        "if sys.argv[1:] == ['version']:\n"
        "    print('0.43.27')\n"
        "    raise SystemExit(0)\n"
        "raise SystemExit(97)\n",
        encoding="utf-8",
    )
    fake_core.chmod(0o755)
    original_worker = materialization_executor_module._execute_klc_materialization_isolated

    def forbidden_worker(**_kwargs):
        raise AssertionError("KLC worker executed despite a valid content-addressed hit")

    monkeypatch.setattr(
        materialization_executor_module,
        "_execute_klc_materialization_isolated",
        forbidden_worker,
    )
    second = execute_knowledge_execution_plan(
        execution_plan=plan,
        core_evidence_catalog=core,
        materialization_catalog=klc,
        output=tmp_path / "execution-2",
        core_command=str(fake_core),
        producer_cache_root=cache_root,
        replace=True,
    )
    assert second["producer_reuse"]["summary"] == {"built": 0, "reused": 2}
    assert second["analyzer_executions"] == []
    assert second["node_executions"][-1]["execution_action"] == "reused"
    second_location = second["knowledge_artifacts"][0]["location"]
    assert not Path(second_location["output_path"]).is_absolute()
    assert (tmp_path / "execution-2" / second_location["manifest_path"]).is_file()
    reused_result_path = (
        tmp_path
        / "execution-2/materialization-execution/materializations/001-code-declared-data-model/materialization-result.json"
    )
    reused_result = json.loads(reused_result_path.read_text(encoding="utf-8"))
    assert "execution-2" in reused_result["output"]["path"]
    assert "execution-1" not in reused_result["output"]["path"]
    assert reused_result["result_fingerprint"] == materialization_executor_module._canonical_fingerprint(
        reused_result, fingerprint_field="result_fingerprint"
    )

    # Byte corruption of the cached DuckDB must be quarantined and rebuilt, never silently reused.
    monkeypatch.setattr(
        materialization_executor_module,
        "_execute_klc_materialization_isolated",
        original_worker,
    )
    key = materialization_decision["reuse_key"]
    payload = ProducerArtifactStore(cache_root).entry_root("knowledge-materialization", key) / "payload"
    manifest = json.loads((payload / "knowledge-layer/knowledge-layer-manifest.json").read_text(encoding="utf-8"))
    database_name = manifest.get("database_path") or (manifest.get("artifacts") or {}).get("database") or "knowledge-layer.duckdb"
    database_path = payload / "knowledge-layer" / str(database_name)
    with database_path.open("ab") as stream:
        stream.write(b"corruption")

    # Restore real Core executable for a rebuild path. Core itself should still reuse.
    fake_core = _fake_core(fake_core)
    third = execute_knowledge_execution_plan(
        execution_plan=plan,
        core_evidence_catalog=core,
        materialization_catalog=klc,
        output=tmp_path / "execution-3",
        core_command=str(fake_core),
        producer_cache_root=cache_root,
        replace=True,
    )
    assert third["producer_reuse"]["summary"] == {"built": 1, "reused": 1}
    rebuilt = next(
        item for item in third["producer_reuse"]["decisions"]
        if item["producer_kind"] == "knowledge-materialization"
    )
    assert rebuilt["action"] == "built"
    assert rebuilt["invalidation_reason"] == "cache_invalid"
    assert rebuilt["diagnostics"]
    assert list((cache_root / "invalid" / "knowledge-materialization").glob(f"{key}-*"))

    # Force rebuild executes both canonical producers but does not poison/remove the
    # already valid immutable cache entry for the same semantic key.
    fourth = execute_knowledge_execution_plan(
        execution_plan=plan,
        core_evidence_catalog=core,
        materialization_catalog=klc,
        output=tmp_path / "execution-4",
        core_command=str(fake_core),
        producer_cache_root=cache_root,
        force_rebuild=True,
        replace=True,
    )
    assert fourth["producer_reuse"]["summary"] == {"built": 2, "reused": 0}
    assert {
        item["invalidation_reason"] for item in fourth["producer_reuse"]["decisions"]
    } == {"force_rebuild"}

    fake_core.write_text(
        "#!/usr/bin/env python3\n"
        "import sys\n"
        "if sys.argv[1:] == ['version']:\n"
        "    print('0.43.27')\n"
        "    raise SystemExit(0)\n"
        "raise SystemExit(97)\n",
        encoding="utf-8",
    )
    fake_core.chmod(0o755)
    monkeypatch.setattr(
        materialization_executor_module,
        "_execute_klc_materialization_isolated",
        forbidden_worker,
    )
    fifth = execute_knowledge_execution_plan(
        execution_plan=plan,
        core_evidence_catalog=core,
        materialization_catalog=klc,
        output=tmp_path / "execution-5",
        core_command=str(fake_core),
        producer_cache_root=cache_root,
        replace=True,
    )
    assert fifth["producer_reuse"]["summary"] == {"built": 0, "reused": 2}



def test_knowledge_execute_batches_core_analyzers_for_one_source_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "Customer.java").write_text("class Customer { String id; }", encoding="utf-8")
    core = _core_evidence_payload()
    klc = _klc_payload()
    klc["runtime_contract"] = {
        "contract_id": "knowledge_materialization_runtime/v1",
        "generic_entrypoint": "knowledge_layer_core.materialization_runtime.materialize",
        "request_schema_version": "knowledge_materialization_request/v1",
        "result_schema_version": "knowledge_materialization_execution_result/v1",
        "registered_materialization_ids": ["system-description", "reference-data"],
    }
    klc["catalog_fingerprint"] = stable_fingerprint({
        key: value for key, value in klc.items() if key != "catalog_fingerprint"
    })
    inventory = build_knowledge_input_inventory(
        scope_kind="repository",
        scope_id="client-profile",
        source_snapshots=[inspect_repository_source(repository, source_id="client-profile")],
        core_evidence_catalog=core,
        materialization_catalog=klc,
    )
    plan = compile_knowledge_execution_plan(
        knowledge_catalog=_catalog_for(core, klc),
        knowledge_profile=_profile("system-description", "reference-data", scope="repository"),
        input_inventory=inventory,
        core_evidence_catalog=core,
        materialization_catalog=klc,
    )
    plan_path = tmp_path / "plan.json"
    core_path = tmp_path / "core.json"
    klc_path = tmp_path / "klc.json"
    write_json(plan_path, plan)
    write_json(core_path, core)
    write_json(klc_path, klc)

    calls: list[dict] = []

    def fake_core_execution(**kwargs):
        request = deepcopy(dict(kwargs["request"]))
        calls.append(request)
        artifacts = []
        executions = []
        for index, requirement in enumerate(request["evidence_requirements"], start=1):
            artifact_id = f"artifact-{index}"
            artifacts.append({
                "artifact_id": artifact_id,
                "artifact_kind": requirement["artifact_kind"],
                "schema_version": requirement["schema_version"],
                "content_fingerprint": f"fingerprint-{index}",
                "location": {},
            })
            executions.append({
                "analyzer_execution_id": f"execution-{index}",
                "status": "completed",
                "artifact_ids": [artifact_id],
            })
        return {
            "schema_version": "static_repository_analysis_run_manifest/v1",
            "repository": {"repo_id": "client-profile"},
            "analyzer_executions": executions,
            "evidence_artifacts": artifacts,
            "run_fingerprint": "batched-run",
            "status": "completed",
        }

    def fake_materialization_execution(**kwargs):
        plan_payload = kwargs["execution_plan"]
        materializations = [
            node
            for node in (plan_payload.get("graph") or {}).get("nodes") or []
            if node.get("node_kind") == "knowledge_materialization"
        ]
        expected = plan_payload.get("expected_outputs") or {}
        models = list(expected.get("knowledge_models") or [])
        artifacts = [
            {
                "artifact_id": f"knowledge-{index}",
                "model_kind": f"model-{index}",
                "schema_version": schema_version,
                "status": "completed",
            }
            for index, schema_version in enumerate(models, start=1)
        ]
        executions = []
        for index, node in enumerate(materializations, start=1):
            artifact = artifacts[min(index - 1, len(artifacts) - 1)] if artifacts else None
            executions.append({
                "execution_node_id": node["node_id"],
                "status": "completed",
                "materialization_id": node.get("materialization_id"),
                "materialization_execution_id": f"materialization-{index}",
                "input_artifact_ids": [],
                "input_knowledge_artifact_ids": [],
                "knowledge_artifact_ids": [artifact["artifact_id"]] if artifact else [],
                "published_capabilities": list(expected.get("capabilities") or []),
                "result": f"result-{index}.json",
                "request": f"request-{index}.json",
                "output_manifest": f"manifest-{index}.json",
            })
        return {
            "materialization_executions": executions,
            "produced_knowledge_artifacts": artifacts,
            "published_capabilities": list(expected.get("capabilities") or []),
        }

    monkeypatch.setattr(execution_module, "execute_core_evidence_request", fake_core_execution)
    monkeypatch.setattr(execution_module, "execute_materialization_execution_plan", fake_materialization_execution)

    result = execute_knowledge_execution_plan(
        execution_plan=plan_path,
        core_evidence_catalog=core_path,
        materialization_catalog=klc_path,
        output=tmp_path / "execution",
        replace=True,
    )

    assert len(calls) == 1
    assert calls[0]["orchestration"]["batching_policy"] == "same_source_snapshot_single_core_request"
    assert len(calls[0]["orchestration"]["execution_node_ids"]) == 2
    assert {item["artifact_kind"] for item in calls[0]["evidence_requirements"]} == {
        "system-description-evidence",
        "reference-data-evidence",
    }
    analyzer_nodes = [item for item in result["node_executions"] if item["node_kind"] == "core_evidence_analyzer"]
    assert len(analyzer_nodes) == 2
    assert {item["run_fingerprint"] for item in analyzer_nodes} == {"batched-run"}
    assert len(result["repository_run_manifests"]) == 1


def test_knowledge_execute_rejects_stale_source_snapshot(tmp_path: Path) -> None:
    plan, core, klc, repository = _inputs(tmp_path)
    (repository / "Changed.java").write_text("class Changed {}", encoding="utf-8")

    with pytest.raises(ValueError, match="source snapshot changed"):
        execute_knowledge_execution_plan(
            execution_plan=plan,
            core_evidence_catalog=core,
            materialization_catalog=klc,
            output=tmp_path / "knowledge-execution",
            core_command=str(_fake_core(tmp_path / "fake-core")),
            replace=True,
        )


def test_knowledge_execute_rejects_catalog_not_bound_to_plan(tmp_path: Path) -> None:
    plan, core, klc, _ = _inputs(tmp_path)
    payload = json.loads(core.read_text(encoding="utf-8"))
    payload["core_version"] = "0.43.28"
    payload["catalog_fingerprint"] = stable_fingerprint({k: v for k, v in payload.items() if k != "catalog_fingerprint"})
    write_json(core, payload)

    with pytest.raises(ValueError, match="does not bind"):
        execute_knowledge_execution_plan(
            execution_plan=plan,
            core_evidence_catalog=core,
            materialization_catalog=klc,
            output=tmp_path / "knowledge-execution",
            core_command=str(_fake_core(tmp_path / "fake-core")),
            replace=True,
        )


def test_cli_knowledge_execute_is_canonical_product_route(tmp_path: Path) -> None:
    plan, core, klc, _ = _inputs(tmp_path)
    output = tmp_path / "knowledge-execution"
    invocation = runner.invoke(app, [
        "knowledge-execute",
        "--execution-plan", str(plan),
        "--core-evidence-catalog", str(core),
        "--materialization-catalog", str(klc),
        "--output", str(output),
        "--core-command", str(_fake_core(tmp_path / "fake-core")),
        "--replace",
    ])
    assert invocation.exit_code == 0, invocation.output
    summary = json.loads(invocation.stdout)
    assert summary["schema_version"] == "knowledge_execution_result/v2"
    assert summary["status"] == "completed"
    assert summary["materialization_count"] == 1
    assert (output / "knowledge_execution_result.json").is_file()


def test_product_executor_has_no_concrete_knowledge_or_evidence_branch() -> None:
    source = inspect.getsource(execution_module)
    assert "java-type-structure" not in source
    assert "code-declared-data-model" not in source
    assert "if knowledge_id" not in source
    assert "if materialization_id ==" not in source
    assert "task_id" not in source
    assert "suite_id" not in source
    assert "core_profile" not in source



def test_knowledge_execute_reuses_registered_evidence_without_core_rerun(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "Customer.java").write_text("class Customer { String id; }", encoding="utf-8")
    core = _core_evidence_payload()
    core_path = tmp_path / "core.json"
    write_json(core_path, core)
    evidence_plan = _evidence_plan(
        tmp_path / "evidence-plan.json",
        ("java-type-structure-evidence", "java-type-structure-evidence/v1"),
    )
    evidence_run = tmp_path / "evidence-run"
    execute_core_evidence_plan(
        repository=repository,
        resolution_plan=evidence_plan,
        core_evidence_catalog=core_path,
        output=evidence_run,
        core_command=str(_fake_core(tmp_path / "fake-core")),
        repo_id="client-profile",
        replace=True,
    )
    registration_manifest = evidence_run / "repository_analysis_run_manifest.json"
    typed_artifacts = artifacts_from_repository_run_manifest(registration_manifest)
    klc_path = _materialization_catalog(tmp_path / "klc.json")
    klc = json.loads(klc_path.read_text(encoding="utf-8"))
    inventory = build_knowledge_input_inventory(
        scope_kind="repository",
        scope_id="client-profile",
        source_snapshots=[],
        core_evidence_catalog=core,
        materialization_catalog=klc,
        typed_artifacts=typed_artifacts,
    )
    plan_payload = compile_knowledge_execution_plan(
        knowledge_catalog=_catalog_for(core, klc),
        knowledge_profile=_profile("code-declared-data-model", scope="repository"),
        input_inventory=inventory,
        core_evidence_catalog=core,
        materialization_catalog=klc,
    )
    assert plan_payload["graph"]["execution_order"] == ["materialization:code-declared-data-model"]
    plan_path = tmp_path / "plan.json"
    write_json(plan_path, plan_payload)

    result = execute_knowledge_execution_plan(
        execution_plan=plan_path,
        core_evidence_catalog=core_path,
        materialization_catalog=klc_path,
        output=tmp_path / "knowledge-execution",
        core_command=str(tmp_path / "must-not-be-invoked"),
        replace=True,
    )

    assert result["analyzer_executions"] == []
    assert result["repository_run_manifests"] == [str(registration_manifest)]
    assert len(result["evidence_artifacts"]) == 1
    assert result["evidence_artifacts"][0]["registration_manifest_path"] == str(registration_manifest)
    assert len(result["knowledge_artifacts"]) == 1


def test_knowledge_execution_result_matches_json_schema(tmp_path: Path) -> None:
    import jsonschema

    plan, core, klc, _ = _inputs(tmp_path)
    result = execute_knowledge_execution_plan(
        execution_plan=plan,
        core_evidence_catalog=core,
        materialization_catalog=klc,
        output=tmp_path / "knowledge-execution",
        core_command=str(_fake_core(tmp_path / "fake-core")),
        replace=True,
    )
    schema_path = Path(__file__).parents[1] / "schemas" / "knowledge_execution_result_v2.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    jsonschema.validate(result, schema)

    tampered = deepcopy(result)
    tampered["status"] = "failed"
    with pytest.raises(ValueError, match="fingerprint"):
        validate_knowledge_execution_result(tampered)


def test_knowledge_execution_result_rejects_removed_dual_write_marker(tmp_path: Path) -> None:
    plan, core, klc, _ = _inputs(tmp_path)
    result = execute_knowledge_execution_plan(
        execution_plan=plan,
        core_evidence_catalog=core,
        materialization_catalog=klc,
        output=tmp_path / "knowledge-execution-old-policy",
        core_command=str(_fake_core(tmp_path / "fake-core-old-policy")),
        replace=True,
    )
    tampered = deepcopy(result)
    tampered["semantic_policy"]["dual_write"] = "not_supported"
    tampered["result_fingerprint"] = stable_fingerprint({
        key: deepcopy(value) for key, value in tampered.items() if key != "result_fingerprint"
    })
    with pytest.raises(ValueError, match="semantic policy"):
        validate_knowledge_execution_result(tampered)


def test_knowledge_execution_result_uses_relocatable_knowledge_artifact_locations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan, core, klc, _ = _inputs(tmp_path)
    output = tmp_path / "portable-execution"

    def fake_materialization_execution(**kwargs):
        materialization_root = Path(kwargs["output"]).resolve()
        knowledge_root = materialization_root / "materializations" / "001-code-declared-data-model" / "knowledge-layer"
        manifest_path = knowledge_root / "knowledge-layer-manifest.json"
        artifact = {
            "artifact_id": "knowledge-portable",
            "model_kind": "code-declared-data-model",
            "schema_version": "code-declared-data-model/v1",
            "source_materialization_id": "code-declared-data-model",
            "status": "completed",
            "location": {
                "kind": "knowledge-layer",
                "output_path": str(knowledge_root),
                "manifest_path": str(manifest_path),
            },
        }
        expected_capabilities = list(
            (kwargs["execution_plan"].get("expected_outputs") or {}).get("capabilities") or []
        )
        return {
            "materialization_executions": [{
                "execution_node_id": "materialization:code-declared-data-model",
                "status": "completed",
                "materialization_id": "code-declared-data-model",
                "materialization_execution_id": "materialization-portable",
                "input_artifact_ids": [],
                "input_knowledge_artifact_ids": [],
                "knowledge_artifact_ids": [artifact["artifact_id"]],
                "published_capabilities": expected_capabilities,
                "result": "materializations/001-code-declared-data-model/result.json",
                "request": "materializations/001-code-declared-data-model/request.json",
                "output_manifest": "materializations/001-code-declared-data-model/manifest.json",
            }],
            "produced_knowledge_artifacts": [artifact],
            "published_capabilities": expected_capabilities,
        }

    monkeypatch.setattr(execution_module, "execute_materialization_execution_plan", fake_materialization_execution)
    result = execute_knowledge_execution_plan(
        execution_plan=plan,
        core_evidence_catalog=core,
        materialization_catalog=klc,
        output=output,
        core_command=str(_fake_core(tmp_path / "fake-core-portable")),
        replace=True,
    )

    location = result["knowledge_artifacts"][0]["location"]
    assert location["output_path"] == (
        "materialization-execution/materializations/001-code-declared-data-model/knowledge-layer"
    )
    assert location["manifest_path"] == (
        "materialization-execution/materializations/001-code-declared-data-model/knowledge-layer/knowledge-layer-manifest.json"
    )
    assert not Path(location["output_path"]).is_absolute()
    assert not Path(location["manifest_path"]).is_absolute()
    assert validate_knowledge_execution_result(result) == result


def _fake_materialization_for_reuse_test(**kwargs):
    plan_payload = kwargs["execution_plan"]
    nodes = [
        node for node in (plan_payload.get("graph") or {}).get("nodes") or []
        if node.get("node_kind") == "knowledge_materialization"
    ]
    expected = plan_payload.get("expected_outputs") or {}
    model_versions = list(expected.get("knowledge_models") or [])
    artifacts = [
        {
            "artifact_id": f"knowledge-reuse-{index}",
            "model_kind": schema_version.split("/")[0],
            "schema_version": schema_version,
            "status": "completed",
        }
        for index, schema_version in enumerate(model_versions, start=1)
    ]
    executions = []
    for index, node in enumerate(nodes, start=1):
        artifact_ids = [artifacts[min(index - 1, len(artifacts) - 1)]["artifact_id"]] if artifacts else []
        executions.append({
            "execution_node_id": node["node_id"],
            "status": "completed",
            "materialization_id": node.get("materialization_id"),
            "materialization_execution_id": f"reuse-materialization-{index}",
            "input_artifact_ids": [],
            "input_knowledge_artifact_ids": [],
            "knowledge_artifact_ids": artifact_ids,
            "published_capabilities": list(expected.get("capabilities") or []),
            "result": f"result-{index}.json",
            "request": f"request-{index}.json",
            "output_manifest": f"manifest-{index}.json",
        })
    return {
        "materialization_executions": executions,
        "produced_knowledge_artifacts": artifacts,
        "published_capabilities": list(expected.get("capabilities") or []),
    }


def test_content_addressed_core_node_reuse_skips_analyzer_execution_and_force_rebuilds(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan, core, klc, _repository = _inputs(tmp_path)
    fake_core = _fake_core(tmp_path / "fake-core")
    cache_root = tmp_path / "producer-cache"
    monkeypatch.setattr(
        execution_module,
        "execute_materialization_execution_plan",
        _fake_materialization_for_reuse_test,
    )

    first = execute_knowledge_execution_plan(
        execution_plan=plan,
        core_evidence_catalog=core,
        materialization_catalog=klc,
        output=tmp_path / "execution-1",
        core_command=str(fake_core),
        producer_cache_root=cache_root,
        replace=True,
    )
    assert first["producer_reuse"]["summary"] == {"built": 1, "reused": 0}
    assert len(first["analyzer_executions"]) == 1
    first_fp = first["evidence_artifacts"][0]["content_fingerprint"]

    # Version lookup must still work, but evidence-execute now fails if reuse is not real.
    fake_core.write_text(
        "#!/usr/bin/env python3\n"
        "import sys\n"
        "if sys.argv[1:] == ['version']:\n"
        "    print('0.43.27')\n"
        "    raise SystemExit(0)\n"
        "raise SystemExit(97)\n",
        encoding="utf-8",
    )
    fake_core.chmod(0o755)
    second = execute_knowledge_execution_plan(
        execution_plan=plan,
        core_evidence_catalog=core,
        materialization_catalog=klc,
        output=tmp_path / "execution-2",
        core_command=str(fake_core),
        producer_cache_root=cache_root,
        replace=True,
    )
    assert second["producer_reuse"]["summary"] == {"built": 0, "reused": 1}
    assert second["analyzer_executions"] == []
    assert second["node_executions"][0]["execution_action"] == "reused"
    assert second["evidence_artifacts"][0]["content_fingerprint"] == first_fp

    _fake_core(fake_core)
    forced = execute_knowledge_execution_plan(
        execution_plan=plan,
        core_evidence_catalog=core,
        materialization_catalog=klc,
        output=tmp_path / "execution-3",
        core_command=str(fake_core),
        producer_cache_root=cache_root,
        force_rebuild=True,
        replace=True,
    )
    assert forced["producer_reuse"]["summary"] == {"built": 1, "reused": 0}
    assert forced["producer_reuse"]["decisions"][0]["invalidation_reason"] == "force_rebuild"
    assert len(forced["analyzer_executions"]) == 1
    assert forced["evidence_artifacts"][0]["content_fingerprint"] == first_fp

    fresh_cache = tmp_path / "producer-cache-force-empty"
    forced_empty = execute_knowledge_execution_plan(
        execution_plan=plan,
        core_evidence_catalog=core,
        materialization_catalog=klc,
        output=tmp_path / "execution-4",
        core_command=str(fake_core),
        producer_cache_root=fresh_cache,
        force_rebuild=True,
        replace=True,
    )
    assert forced_empty["producer_reuse"]["summary"] == {"built": 1, "reused": 0}
    fake_core.write_text(
        "#!/usr/bin/env python3\n"
        "import sys\n"
        "if sys.argv[1:] == ['version']:\n"
        "    print('0.43.27')\n"
        "    raise SystemExit(0)\n"
        "raise SystemExit(97)\n",
        encoding="utf-8",
    )
    fake_core.chmod(0o755)
    after_forced = execute_knowledge_execution_plan(
        execution_plan=plan,
        core_evidence_catalog=core,
        materialization_catalog=klc,
        output=tmp_path / "execution-5",
        core_command=str(fake_core),
        producer_cache_root=fresh_cache,
        replace=True,
    )
    assert after_forced["producer_reuse"]["summary"] == {"built": 0, "reused": 1}
    assert after_forced["analyzer_executions"] == []


def test_execution_result_projects_used_prior_revision_knowledge_dependencies() -> None:
    existing = [{
        "artifact_id": "external-code-model",
        "model_kind": "code-declared-data-model",
        "schema_version": "code-declared-data-model/v1",
        "source_materialization_id": "code-declared-data-model",
        "content_fingerprint": "external-fingerprint",
        "status": "completed",
        "location": {"kind": "knowledge-layer", "manifest_path": "/private/path/manifest.json"},
        "provenance": {
            "source": "knowledge-api-revision",
            "source_system_id": "source-system",
            "source_revision_id": "rev-source-1",
            "published_capabilities": ["common.code-declared-data-model"],
        },
    }, {
        "artifact_id": "external-unused",
        "model_kind": "physical-data-model",
        "schema_version": "physical-data-model/v1",
        "source_materialization_id": "physical-data-model",
        "content_fingerprint": "unused-fingerprint",
        "status": "completed",
        "provenance": {
            "source": "knowledge-api-revision",
            "source_system_id": "source-system",
            "source_revision_id": "rev-source-1",
            "published_capabilities": ["common.physical-model"],
        },
    }]
    produced = [{"artifact_id": "local-derived"}]
    executions = [{
        "input_knowledge_artifact_ids": ["external-code-model"],
        "knowledge_artifact_ids": ["local-derived"],
    }, {
        "input_knowledge_artifact_ids": ["local-derived"],
        "knowledge_artifact_ids": [],
    }]

    projected = execution_module._external_knowledge_artifacts_used_by_execution(
        existing_knowledge=existing,
        produced_knowledge=produced,
        materialization_executions=executions,
    )

    assert projected == [{
        "artifact_id": "external-code-model",
        "model_kind": "code-declared-data-model",
        "schema_version": "code-declared-data-model/v1",
        "source_materialization_id": "code-declared-data-model",
        "content_fingerprint": "external-fingerprint",
        "source_system_id": "source-system",
        "source_revision_id": "rev-source-1",
        "published_capabilities": ["common.code-declared-data-model"],
    }]
    assert "location" not in projected[0]
    execution_module._validate_knowledge_dependency_registration({
        "knowledge_artifacts": produced,
        "external_knowledge_artifacts": projected,
        "materialization_executions": executions,
    })


def test_execution_result_rejects_unresolved_or_unused_external_dependency() -> None:
    with pytest.raises(ValueError, match="unresolved knowledge input ids"):
        execution_module._validate_knowledge_dependency_registration({
            "knowledge_artifacts": [{"artifact_id": "local-derived"}],
            "external_knowledge_artifacts": [],
            "materialization_executions": [{"input_knowledge_artifact_ids": ["missing-prior"]}],
        })

    with pytest.raises(ValueError, match="unused external knowledge artifacts"):
        execution_module._validate_knowledge_dependency_registration({
            "knowledge_artifacts": [{"artifact_id": "local-derived"}],
            "external_knowledge_artifacts": [{
                "artifact_id": "unused-prior",
                "model_kind": "code-declared-data-model",
                "schema_version": "code-declared-data-model/v1",
                "source_materialization_id": "code-declared-data-model",
                "content_fingerprint": "fp",
                "source_system_id": "source-system",
                "source_revision_id": "rev-1",
            }],
            "materialization_executions": [],
        })
