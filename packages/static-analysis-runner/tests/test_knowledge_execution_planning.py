from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from static_analysis_runner.knowledge_execution_planning import (
    artifacts_from_repository_run_manifest,
    build_knowledge_input_inventory,
    compile_knowledge_execution_plan,
    inspect_repository_source,
    validate_knowledge_input_inventory,
)
from test_knowledge_planning import _catalog, _core_evidence_payload, _fingerprint, _klc_payload, _profile


def _catalog_for(core: dict, klc: dict) -> dict:
    payload = deepcopy(_catalog())
    payload["source"]["core_evidence_contract_catalog_fingerprint"] = core["catalog_fingerprint"]
    payload["source"]["klc_materialization_catalog_fingerprint"] = klc["catalog_fingerprint"]
    payload["catalog_fingerprint"] = _fingerprint({k: v for k, v in payload.items() if k != "catalog_fingerprint"})
    return payload


def _runtime_klc(*registered_ids: str) -> dict:
    payload = deepcopy(_klc_payload())
    payload["runtime_contract"] = {"contract_id": "knowledge_materialization_runtime/v1"}
    for item in payload["materializations"]:
            materialization_id = item["materialization_id"]
            runtime = item.setdefault("current_implementation", {}).setdefault("runtime", {})
            runtime.update({
                "contract_id": "knowledge_materialization_runtime/v1",
                "registered": materialization_id in set(registered_ids),
                "handler_id": materialization_id if materialization_id in set(registered_ids) else None,
            })
    payload["catalog_fingerprint"] = _fingerprint({k: v for k, v in payload.items() if k != "catalog_fingerprint"})
    return payload


def _inventory(tmp_path: Path, *, knowledge_id: str = "code-declared-data-model", typed_artifacts=()) -> tuple[dict, dict, dict]:
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "Customer.java").write_text("class Customer { String id; }", encoding="utf-8")
    core = _core_evidence_payload()
    klc = _runtime_klc("code-declared-data-model", "physical-model")
    inventory = build_knowledge_input_inventory(
        scope_kind="repository",
        scope_id="client-profile",
        source_snapshots=[inspect_repository_source(repository, source_id="client-profile")],
        core_evidence_catalog=core,
        materialization_catalog=klc,
        typed_artifacts=typed_artifacts,
    )
    return inventory, core, klc


def test_inventory_separates_contract_producer_and_actual_input_availability(tmp_path: Path) -> None:
    inventory, _, _ = _inventory(tmp_path)

    assert inventory["schema_version"] == "knowledge_input_inventory/v1"
    assert inventory["summary"]["source_snapshot_count"] == 1
    contract = next(
        item for item in inventory["producer_catalog"]["core_evidence_contract_catalog"]["contracts"]
        if item["artifact_kind"] == "java-type-structure-evidence"
    )
    assert contract["contract_known"] is True
    assert contract["producer_registered"] is True
    assert inventory["typed_artifacts"] == []
    assert inventory["availability_policy"]["contract_presence_is_not_input_availability"] is True
    validate_knowledge_input_inventory(inventory)


def test_inventory_projects_core_owned_preflight_planning_metadata(tmp_path: Path) -> None:
    inventory, _, _ = _inventory(tmp_path)
    contracts = {
        item["artifact_kind"]: item
        for item in inventory["producer_catalog"]["core_evidence_contract_catalog"]["contracts"]
    }

    repository = contracts["repository-structure-evidence"]["preflight_planning"]
    assert repository["execution_class"] == "always_on"
    assert repository["preflight_phase"] == "p0"

    structured = contracts["structured-file-shape-evidence"]["preflight_planning"]
    assert structured["execution_class"] == "bounded_preflight"
    assert structured["preflight_phase"] == "p1"

    java_type = contracts["java-type-structure-evidence"]["preflight_planning"]
    assert java_type["execution_class"] == "full_analysis"
    assert java_type["selection_safety"]["concept_inference_may_hard_skip"] is False


def test_code_declared_plan_is_ready_and_contains_generic_dag(tmp_path: Path) -> None:
    inventory, core, klc = _inventory(tmp_path)

    plan = compile_knowledge_execution_plan(
        knowledge_catalog=_catalog_for(core, klc),
        knowledge_profile=_profile("code-declared-data-model", scope="repository"),
        input_inventory=inventory,
        core_evidence_catalog=core,
        materialization_catalog=klc,
    )

    assert plan["schema_version"] == "knowledge_execution_plan/v1"
    assert plan["status"]["overall"] == "ready"
    kinds = [item["node_kind"] for item in plan["graph"]["nodes"]]
    assert kinds.count("source_snapshot") == 1
    assert kinds.count("core_evidence_analyzer") == 1
    assert kinds.count("typed_evidence_artifact") == 1
    assert kinds.count("knowledge_materialization") == 1
    assert plan["graph"]["execution_order"] == [
        "analyzer:java-type-structure-analyzer:client-profile",
        "materialization:code-declared-data-model",
    ]
    assert plan["foundation_requirements"] == ["repository-file-index"]
    assert "legacy_fallback" not in plan["semantic_policy"]
    serialized = json.dumps(plan, ensure_ascii=False)
    assert "java_source_observation_build" not in serialized
    assert "future_analyzer_id" not in serialized
    assert "task_id" not in serialized
    assert "suite_id" not in serialized
    assert "core_profile" not in serialized


def test_code_declared_plan_activates_optional_storage_enrichment_when_runtime_is_available(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "Customer.java").write_text("class Customer { String id; }", encoding="utf-8")
    core = _core_evidence_payload()
    klc = _runtime_klc(
        "code-declared-data-model",
        "model-storage-semantics",
        "logical-storage-mapping",
    )
    inventory = build_knowledge_input_inventory(
        scope_kind="repository",
        scope_id="client-profile",
        source_snapshots=[inspect_repository_source(repository, source_id="client-profile")],
        core_evidence_catalog=core,
        materialization_catalog=klc,
        typed_artifacts=(),
    )

    plan = compile_knowledge_execution_plan(
        knowledge_catalog=_catalog_for(core, klc),
        knowledge_profile=_profile("code-declared-data-model", scope="repository"),
        input_inventory=inventory,
        core_evidence_catalog=core,
        materialization_catalog=klc,
    )

    assert plan["status"]["overall"] == "ready"
    materializations = {
        node["materialization_id"]: node
        for node in plan["graph"]["nodes"]
        if node["node_kind"] == "knowledge_materialization"
    }
    assert set(materializations) == {
        "code-declared-data-model",
        "model-storage-semantics",
        "logical-storage-mapping",
    }
    assert materializations["model-storage-semantics"]["execution_requirement"] == "optional"
    assert materializations["logical-storage-mapping"]["execution_requirement"] == "optional"
    order = plan["graph"]["execution_order"]
    assert order.index("materialization:code-declared-data-model") < order.index("materialization:logical-storage-mapping")
    assert order.index("materialization:model-storage-semantics") < order.index("materialization:logical-storage-mapping")
    assert any(
        node["node_kind"] == "core_evidence_analyzer"
        and any(
            req["artifact_kind"] == "model-storage-evidence"
            for req in node["evidence_requirements"]
        )
        for node in plan["graph"]["nodes"]
    )


def test_code_declared_plan_skips_optional_storage_enrichment_when_runtime_is_unavailable(tmp_path: Path) -> None:
    inventory, core, klc = _inventory(tmp_path)

    plan = compile_knowledge_execution_plan(
        knowledge_catalog=_catalog_for(core, klc),
        knowledge_profile=_profile("code-declared-data-model", scope="repository"),
        input_inventory=inventory,
        core_evidence_catalog=core,
        materialization_catalog=klc,
    )

    assert plan["status"]["overall"] == "ready"
    assert [
        node["materialization_id"]
        for node in plan["graph"]["nodes"]
        if node["node_kind"] == "knowledge_materialization"
    ] == ["code-declared-data-model"]
    assert not any(
        node["node_kind"] == "core_evidence_analyzer"
        and any(req["artifact_kind"] == "model-storage-evidence" for req in node["evidence_requirements"])
        for node in plan["graph"]["nodes"]
    )
    skipped = [
        value for value in plan["diagnostics"]
        if value["diagnostic_id"] == "optional_internal_materialization_skipped"
    ]
    assert {value["materialization_id"] for value in skipped} == {
        "logical-storage-mapping",
        "model-storage-semantics",
    }


def test_external_typed_artifact_is_required_explicitly(tmp_path: Path) -> None:
    inventory, core, klc = _inventory(tmp_path)

    blocked = compile_knowledge_execution_plan(
        knowledge_catalog=_catalog_for(core, klc),
        knowledge_profile=_profile("physical-data-model", scope="repository"),
        input_inventory=inventory,
        core_evidence_catalog=core,
        materialization_catalog=klc,
    )

    assert blocked["status"]["overall"] == "blocked"
    assert any(item["diagnostic_id"] == "required_external_typed_artifact_missing" for item in blocked["diagnostics"])
    assert any(item["diagnostic_id"] == "required_evidence_unsatisfied" for item in blocked["diagnostics"])


def test_partial_repository_artifact_remains_available_for_reuse(tmp_path: Path) -> None:
    artifact_path = tmp_path / "java-type-structure-evidence.json"
    artifact_path.write_text('{"schema_version":"java-type-structure-evidence/v1"}\n', encoding="utf-8")
    manifest_path = tmp_path / "repository_analysis_run_manifest.json"
    manifest_path.write_text(json.dumps({
        "schema_version": "static_repository_analysis_run_manifest/v1",
        "evidence_artifacts": [{
            "artifact_id": "partial-java-type-structure",
            "artifact_kind": "java-type-structure-evidence",
            "schema_version": "java-type-structure-evidence/v1",
            "status": "partial",
            "coverage": {"coverage_status": "partial", "gap_count": 2},
            "diagnostics": {"count": 1, "code_counts": {"partial_fixture": 1}},
            "location": {"kind": "file", "path": artifact_path.name},
        }],
    }), encoding="utf-8")
    artifacts = artifacts_from_repository_run_manifest(manifest_path)
    inventory, core, klc = _inventory(tmp_path, typed_artifacts=artifacts)

    assert inventory["summary"]["available_typed_artifact_count"] == 1
    assert inventory["typed_artifacts"][0]["availability"] == "available"
    assert inventory["typed_artifacts"][0]["status"] == "partial"
    assert inventory["typed_artifacts"][0]["coverage"] == {"coverage_status": "partial", "gap_count": 2}
    assert inventory["typed_artifacts"][0]["diagnostics"] == {"count": 1, "code_counts": {"partial_fixture": 1}}

    plan = compile_knowledge_execution_plan(
        knowledge_catalog=_catalog_for(core, klc),
        knowledge_profile=_profile("code-declared-data-model", scope="repository"),
        input_inventory=inventory,
        core_evidence_catalog=core,
        materialization_catalog=klc,
    )
    assert plan["status"]["overall"] == "ready"
    assert plan["status"]["core_analyzer_node_count"] == 0
    assert plan["status"]["existing_typed_artifact_count"] == 1
    assert plan["graph"]["execution_order"] == ["materialization:code-declared-data-model"]
    evidence_node = next(
        item for item in plan["graph"]["nodes"]
        if item.get("node_kind") == "typed_evidence_artifact"
    )
    assert evidence_node["artifact"]["status"] == "partial"
    assert evidence_node["artifact"]["coverage"]["gap_count"] == 2
    assert evidence_node["artifact"]["diagnostics"]["count"] == 1


def test_existing_external_typed_artifact_satisfies_materialization(tmp_path: Path) -> None:
    physical = tmp_path / "physical-model.json"
    physical.write_text('{"schema_version":"physical-model/v1"}\n', encoding="utf-8")
    inventory, core, klc = _inventory(tmp_path, typed_artifacts=[{
        "artifact_id": "physical-model-input",
        "artifact_kind": "physical-model",
        "schema_version": "physical-model/v1",
        "status": "completed",
        "location": {"kind": "file", "path": str(physical)},
    }])

    plan = compile_knowledge_execution_plan(
        knowledge_catalog=_catalog_for(core, klc),
        knowledge_profile=_profile("physical-data-model", scope="repository"),
        input_inventory=inventory,
        core_evidence_catalog=core,
        materialization_catalog=klc,
    )

    assert plan["status"]["overall"] == "ready"
    assert plan["graph"]["execution_order"] == ["materialization:physical-model"]
    assert plan["status"]["existing_typed_artifact_count"] == 1


def test_missing_compatible_source_blocks_core_evidence(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "query.sql").write_text("select 1", encoding="utf-8")
    core = _core_evidence_payload()
    for contract in core["contracts"]:
        if contract["artifact_kind"] == "java-type-structure-evidence":
            contract["producer"]["source_language"] = "java"
            contract["contract_fingerprint"] = _fingerprint({k: v for k, v in contract.items() if k != "contract_fingerprint"})
    core["catalog_fingerprint"] = _fingerprint({k: v for k, v in core.items() if k != "catalog_fingerprint"})
    klc = _runtime_klc("code-declared-data-model")
    inventory = build_knowledge_input_inventory(
        scope_kind="repository",
        scope_id="client-profile",
        source_snapshots=[inspect_repository_source(repository, source_id="client-profile")],
        core_evidence_catalog=core,
        materialization_catalog=klc,
    )

    plan = compile_knowledge_execution_plan(
        knowledge_catalog=_catalog_for(core, klc),
        knowledge_profile=_profile("code-declared-data-model", scope="repository"),
        input_inventory=inventory,
        core_evidence_catalog=core,
        materialization_catalog=klc,
    )

    assert plan["status"]["overall"] == "blocked"
    assert any(item["diagnostic_id"] == "compatible_source_snapshot_missing" for item in plan["diagnostics"])


def test_execution_plan_is_deterministic_and_validates_scope(tmp_path: Path) -> None:
    inventory, core, klc = _inventory(tmp_path)
    kwargs = {
        "knowledge_catalog": _catalog_for(core, klc),
        "knowledge_profile": _profile("code-declared-data-model", scope="repository"),
        "input_inventory": inventory,
        "core_evidence_catalog": core,
        "materialization_catalog": klc,
    }
    first = compile_knowledge_execution_plan(**kwargs)
    second = compile_knowledge_execution_plan(**kwargs)
    assert first == second

    broken = deepcopy(inventory)
    broken["scope"]["scope_id"] = "another"
    broken["inventory_fingerprint"] = _fingerprint({k: v for k, v in broken.items() if k != "inventory_fingerprint"})
    with pytest.raises(ValueError, match="scope does not match"):
        compile_knowledge_execution_plan(**{**kwargs, "input_inventory": broken})


def test_cli_builds_inventory_and_execution_plan(tmp_path: Path) -> None:
    from typer.testing import CliRunner
    from static_analysis_runner.cli import app

    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "Customer.java").write_text("class Customer {}", encoding="utf-8")
    core = _core_evidence_payload()
    klc = _runtime_klc("code-declared-data-model")
    catalog = _catalog_for(core, klc)
    profile = _profile("code-declared-data-model", scope="repository")
    paths = {}
    for name, payload in {
        "core": core,
        "klc": klc,
        "catalog": catalog,
        "profile": profile,
    }.items():
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        paths[name] = path

    cli = CliRunner()
    inventory_path = tmp_path / "inventory.json"
    result = cli.invoke(app, [
        "knowledge-input-inventory",
        "--scope-kind", "repository",
        "--scope-id", "client-profile",
        "--repository", str(repository),
        "--core-evidence-catalog", str(paths["core"]),
        "--materialization-catalog", str(paths["klc"]),
        "--output", str(inventory_path),
    ])
    assert result.exit_code == 0, result.output
    assert json.loads(inventory_path.read_text())["schema_version"] == "knowledge_input_inventory/v1"

    plan_path = tmp_path / "execution-plan.json"
    result = cli.invoke(app, [
        "knowledge-execution-plan",
        "--knowledge-catalog", str(paths["catalog"]),
        "--profile", str(paths["profile"]),
        "--input-inventory", str(inventory_path),
        "--core-evidence-catalog", str(paths["core"]),
        "--materialization-catalog", str(paths["klc"]),
        "--output", str(plan_path),
    ])
    assert result.exit_code == 0, result.output
    plan = json.loads(plan_path.read_text())
    assert plan["status"]["overall"] == "ready"


def test_execution_plan_validator_rejects_tampering_and_dangling_edges(tmp_path: Path) -> None:
    from static_analysis_runner.knowledge_execution_planning import validate_knowledge_execution_plan

    inventory, core, klc = _inventory(tmp_path)
    plan = compile_knowledge_execution_plan(
        knowledge_catalog=_catalog_for(core, klc),
        knowledge_profile=_profile("code-declared-data-model", scope="repository"),
        input_inventory=inventory,
        core_evidence_catalog=core,
        materialization_catalog=klc,
    )
    assert validate_knowledge_execution_plan(plan) == plan
    assert plan["request"]["knowledge_resolution_plan_fingerprint"]

    tampered = deepcopy(plan)
    tampered["status"]["overall"] = "blocked"
    with pytest.raises(ValueError, match="fingerprint"):
        validate_knowledge_execution_plan(tampered)

    dangling = deepcopy(plan)
    dangling["graph"]["edges"].append({"from": "unknown", "to": "materialization:code-declared-data-model", "edge_kind": "required_evidence"})
    dangling["plan_fingerprint"] = _fingerprint({k: v for k, v in dangling.items() if k != "plan_fingerprint"})
    with pytest.raises(ValueError, match="unknown node"):
        validate_knowledge_execution_plan(dangling)


def test_execution_plan_rejects_stale_inventory_catalog_binding(tmp_path: Path) -> None:
    inventory, core, klc = _inventory(tmp_path)
    stale = deepcopy(inventory)
    stale["producer_catalog"]["core_evidence_contract_catalog"]["catalog_fingerprint"] = "f" * 64
    stale["inventory_fingerprint"] = _fingerprint({k: v for k, v in stale.items() if k != "inventory_fingerprint"})

    with pytest.raises(ValueError, match="inventory Core evidence catalog fingerprint"):
        compile_knowledge_execution_plan(
            knowledge_catalog=_catalog_for(core, klc),
            knowledge_profile=_profile("code-declared-data-model", scope="repository"),
            input_inventory=stale,
            core_evidence_catalog=core,
            materialization_catalog=klc,
        )


def test_repository_run_manifest_artifacts_resolve_relative_locations(tmp_path: Path) -> None:
    from static_analysis_runner.knowledge_execution_planning import artifacts_from_repository_run_manifest

    evidence = tmp_path / "core-evidence" / "typed.json"
    evidence.parent.mkdir()
    evidence.write_text('{"schema_version":"example-evidence/v1"}\n', encoding="utf-8")
    manifest = tmp_path / "repository-run.json"
    manifest.write_text(json.dumps({
        "schema_version": "static_repository_analysis_run_manifest/v1",
        "evidence_artifacts": [{
            "artifact_id": "example-evidence",
            "artifact_kind": "example-evidence",
            "schema_version": "example-evidence/v1",
            "status": "completed",
            "location": {"kind": "file", "path": "core-evidence/typed.json"},
        }],
    }), encoding="utf-8")

    artifacts = artifacts_from_repository_run_manifest(manifest)
    assert artifacts[0]["availability"] == "available"
    assert artifacts[0]["location"]["path"] == str(evidence.resolve())
    assert artifacts[0]["location"]["sha256"]


def test_materialization_result_artifacts_require_existing_location(tmp_path: Path) -> None:
    from static_analysis_runner.knowledge_execution_planning import knowledge_from_materialization_result

    manifest = tmp_path / "knowledge-layer-manifest.json"
    manifest.write_text('{"schema_version":"knowledge-layer-manifest/v1"}\n', encoding="utf-8")
    result_path = tmp_path / "materialization-result.json"
    result_path.write_text(json.dumps({
        "schema_version": "knowledge_materialization_execution_run/v1",
        "knowledge_artifacts": [{
            "artifact_id": "model",
            "model_kind": "example-model",
            "schema_version": "example-model/v1",
            "source_materialization_id": "example-materialization",
            "status": "completed",
            "location": {"kind": "knowledge-layer", "manifest_path": "knowledge-layer-manifest.json"},
        }, {
            "artifact_id": "missing-model",
            "model_kind": "missing-model",
            "schema_version": "missing-model/v1",
            "source_materialization_id": "missing-materialization",
            "status": "completed",
            "location": {"kind": "knowledge-layer", "manifest_path": "missing.json"},
        }],
    }), encoding="utf-8")

    artifacts = knowledge_from_materialization_result(result_path)
    assert artifacts[0]["availability"] == "available"
    assert artifacts[1]["availability"] == "unavailable"


def test_topological_order_keeps_all_core_analyzers_before_independent_materializations(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "Customer.java").write_text("class Customer {}", encoding="utf-8")
    core = _core_evidence_payload()
    second = next(
        item for item in core["contracts"]
        if item["artifact_kind"] == "java-persistence-mapping-evidence"
    )
    second["contract_status"] = "runtime_published"
    second["producer"]["required_foundation_sections"] = ["repository-file-index"]
    second["runtime_publication"] = {
        "runtime_contract_id": "core_evidence_runtime/v1",
        "registration_status": "registered",
        "producer_analyzer_id": "java-persistence-mapping-analyzer",
    }
    second["current_state_assessment"] = {"typed_runtime_artifact_published": True}
    second["contract_fingerprint"] = _fingerprint({k: v for k, v in second.items() if k != "contract_fingerprint"})
    core["catalog_fingerprint"] = _fingerprint({k: v for k, v in core.items() if k != "catalog_fingerprint"})

    klc = _runtime_klc("code-declared-data-model", "physical-model", "logical-physical-mapping")
    logical = next(
        item for item in klc["materializations"]
        if item["materialization_id"] == "logical-physical-mapping"
    )
    logical["input_contract"]["required_evidence"] = [{
        "artifact_kind": "java-persistence-mapping-evidence",
        "schema_versions": ["java-persistence-mapping-evidence/v1"],
    }]
    logical["input_contract"]["required_knowledge_models"] = [
        {"model_kind": "code-declared-data-model", "schema_versions": ["code-declared-data-model/v1"], "source_materialization_id": "code-declared-data-model"},
        {"model_kind": "physical-data-model", "schema_versions": ["knowledge_layer_physical_model/v1"], "source_materialization_id": "physical-model"},
    ]
    klc["catalog_fingerprint"] = _fingerprint({k: v for k, v in klc.items() if k != "catalog_fingerprint"})

    physical = tmp_path / "physical-model.json"
    physical.write_text('{"schema_version":"physical-model/v1"}\n', encoding="utf-8")
    inventory = build_knowledge_input_inventory(
        scope_kind="repository",
        scope_id="client-profile",
        source_snapshots=[inspect_repository_source(repository, source_id="client-profile")],
        core_evidence_catalog=core,
        materialization_catalog=klc,
        typed_artifacts=[{
            "artifact_id": "physical-model-input",
            "artifact_kind": "physical-model",
            "schema_version": "physical-model/v1",
            "status": "completed",
            "location": {"kind": "file", "path": str(physical)},
        }],
    )
    catalog = _catalog_for(core, klc)
    logical_type = next(item for item in catalog["knowledge_types"] if item["knowledge_id"] == "logical-physical-mapping")
    logical_type["availability"] = {
        "status": "current_typed",
        "business_knowledge_available_now": True,
        "can_execute_through_target_contracts": True,
        "target_contract_status": "current",
        "explanation": "ready",
    }
    logical_type["materialization"] = {
        "materialization_id": "logical-physical-mapping",
        "lifecycle": "current_typed_input",
        "scope": "repository_or_workspace",
        "definition": "fixture",
        "models": ["logical-physical-model-mapping/v1"],
        "materialized_marts": [],
        "capabilities": ["common.logical-physical-mapping"],
    }
    logical_type["evidence_inputs"] = {"required": [{
        "artifact_kind": "java-persistence-mapping-evidence",
        "schema_version": "java-persistence-mapping-evidence/v1",
        "producer": {
            "producer_analyzer_id": "java-persistence-mapping-analyzer",
            "runtime_contract_id": "core_evidence_runtime/v1",
            "runtime_status": "registered_in_generic_core_evidence_runtime",
            "typed_runtime_artifact_published": True,
        },
        "foundation_requirements": ["repository-file-index"],
    }], "optional": []}
    catalog["catalog_fingerprint"] = _fingerprint({k: v for k, v in catalog.items() if k != "catalog_fingerprint"})

    profile = _profile("logical-physical-mapping", scope="repository")
    plan = compile_knowledge_execution_plan(
        knowledge_catalog=catalog,
        knowledge_profile=profile,
        input_inventory=inventory,
        core_evidence_catalog=core,
        materialization_catalog=klc,
    )
    executable_kinds = {
        node["node_id"]: node["node_kind"]
        for node in plan["graph"]["nodes"]
        if node.get("execution_required") is True
    }
    phases = [executable_kinds[node_id] for node_id in plan["graph"]["execution_order"]]
    assert phases == [
        "core_evidence_analyzer",
        "core_evidence_analyzer",
        "knowledge_materialization",
        "knowledge_materialization",
        "knowledge_materialization",
    ]


def test_workspace_sql_catalog_plan_uses_multiple_existing_repository_knowledge_artifacts(tmp_path: Path) -> None:
    core = _core_evidence_payload()
    klc = _runtime_klc("workspace-sql-catalog")
    artifacts = []
    for repo_id in ("repo-a", "repo-b"):
        root = tmp_path / repo_id
        root.mkdir()
        manifest = root / "knowledge-layer-manifest.json"
        manifest.write_text('{"schema_version":"knowledge_layer/v1"}\n', encoding="utf-8")
        artifacts.append({
            "artifact_id": f"sql-{repo_id}",
            "model_kind": "sql-observed-data-usage",
            "schema_version": "knowledge_layer_sql/v2",
            "source_materialization_id": "sql-analysis",
            "status": "completed",
            "scope_id": repo_id,
            "location": {"kind": "file", "manifest_path": str(manifest), "path": str(manifest)},
        })
    inventory = build_knowledge_input_inventory(
        scope_kind="workspace",
        scope_id="client-profile",
        source_snapshots=[],
        core_evidence_catalog=core,
        materialization_catalog=klc,
        knowledge_artifacts=artifacts,
    )
    plan = compile_knowledge_execution_plan(
        knowledge_catalog=_catalog_for(core, klc),
        knowledge_profile=_profile("workspace-sql-source-inventory", scope="workspace"),
        input_inventory=inventory,
        core_evidence_catalog=core,
        materialization_catalog=klc,
    )

    assert plan["status"]["overall"] == "ready"
    assert plan["graph"]["execution_order"] == ["materialization:workspace-sql-catalog"]
    knowledge_nodes = [node for node in plan["graph"]["nodes"] if node["node_kind"] == "knowledge_artifact" and node.get("satisfaction_mode") == "existing_knowledge_artifact"]
    assert {node["artifact"]["artifact_id"] for node in knowledge_nodes} == {"sql-repo-a", "sql-repo-b"}
    incoming = [edge for edge in plan["graph"]["edges"] if edge["to"] == "materialization:workspace-sql-catalog"]
    assert len([edge for edge in incoming if edge["edge_kind"] == "required_knowledge"]) == 2


def test_optional_existing_only_evidence_does_not_schedule_registered_core_producer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import static_analysis_runner.knowledge_execution_planning as planning

    inventory, core, klc = _inventory(tmp_path)
    original_resolve = planning.resolve_knowledge_profile

    def patched_resolve(catalog, profile):
        resolved = original_resolve(catalog, profile)
        resolved = deepcopy(resolved)
        resolved["technical_plan"]["evidence_requirements"].append({
            "artifact_kind": "reference-data-evidence",
            "schema_version": "reference-data-evidence/v1",
            "required_by": [],
            "optional_by": ["code-declared-data-model"],
            "production_policy": "existing_only",
        })
        return resolved

    monkeypatch.setattr(planning, "resolve_knowledge_profile", patched_resolve)
    plan = planning.compile_knowledge_execution_plan(
        knowledge_catalog=_catalog_for(core, klc),
        knowledge_profile=_profile("code-declared-data-model", scope="repository"),
        input_inventory=inventory,
        core_evidence_catalog=core,
        materialization_catalog=klc,
    )
    analyzers = [item for item in plan["graph"]["nodes"] if item.get("node_kind") == "core_evidence_analyzer"]
    assert [item["analyzer_id"] for item in analyzers] == ["java-type-structure-analyzer"]
    assert any(
        item.get("diagnostic_id") == "optional_evidence_existing_only_not_available"
        and item.get("artifact_kind") == "reference-data-evidence"
        for item in plan["diagnostics"]
    )


def test_conditional_materialization_capability_is_visible_but_not_hard_expected(tmp_path: Path) -> None:
    inventory, core, klc = _inventory(tmp_path)
    materialization = next(
        item for item in klc["materializations"]
        if item["materialization_id"] == "code-declared-data-model"
    )
    guaranteed = list((materialization.get("outputs") or {}).get("capabilities") or [])
    conditional = "common.code-declared-conditional-test"
    materialization["outputs"]["conditional_capabilities"] = [conditional]
    klc["catalog_fingerprint"] = _fingerprint(
        {k: v for k, v in klc.items() if k != "catalog_fingerprint"}
    )
    inventory["producer_catalog"]["knowledge_materialization_catalog"]["catalog_fingerprint"] = klc["catalog_fingerprint"]
    inventory["inventory_fingerprint"] = _fingerprint(
        {k: v for k, v in inventory.items() if k != "inventory_fingerprint"}
    )

    plan = compile_knowledge_execution_plan(
        knowledge_catalog=_catalog_for(core, klc),
        knowledge_profile=_profile("code-declared-data-model", scope="repository"),
        input_inventory=inventory,
        core_evidence_catalog=core,
        materialization_catalog=klc,
    )

    node = next(
        item for item in plan["graph"]["nodes"]
        if item.get("node_id") == "materialization:code-declared-data-model"
    )
    assert node["expected_capabilities"] == sorted(guaranteed)
    assert node["conditional_capabilities"] == [conditional]
    assert conditional not in plan["expected_outputs"]["capabilities"]


def test_repository_inventory_default_plan_schedules_only_required_and_produce_if_missing_preflight(tmp_path: Path) -> None:
    repository = tmp_path / "repository-inventory-source"
    repository.mkdir()
    (repository / "Customer.java").write_text("class Customer { String id; }", encoding="utf-8")
    (repository / "application.yaml").write_text("service:\n  name: customer\n", encoding="utf-8")
    core = _core_evidence_payload()
    for contract in core["contracts"]:
        if contract["artifact_kind"] in {
            "repository-structure-evidence",
            "data-model-candidate-evidence",
            "interaction-boundary-evidence",
            "structured-file-shape-evidence",
        }:
            contract["contract_status"] = "runtime_published"
            contract["runtime_publication"]["registration_status"] = "registered"
            contract["current_state_assessment"]["typed_runtime_artifact_published"] = True
            contract["contract_fingerprint"] = _fingerprint({
                key: value for key, value in contract.items() if key != "contract_fingerprint"
            })
    core["catalog_fingerprint"] = _fingerprint({
        key: value for key, value in core.items() if key != "catalog_fingerprint"
    })
    klc = _runtime_klc("repository-inventory")
    inventory = build_knowledge_input_inventory(
        scope_kind="repository",
        scope_id="client-profile",
        source_snapshots=[inspect_repository_source(repository, source_id="client-profile")],
        core_evidence_catalog=core,
        materialization_catalog=klc,
    )

    plan = compile_knowledge_execution_plan(
        knowledge_catalog=_catalog_for(core, klc),
        knowledge_profile=_profile("repository-inventory", scope="repository"),
        input_inventory=inventory,
        core_evidence_catalog=core,
        materialization_catalog=klc,
    )

    analyzers = {
        item["analyzer_id"]
        for item in plan["graph"]["nodes"]
        if item.get("node_kind") == "core_evidence_analyzer"
    }
    assert analyzers == {
        "repository-structure-analyzer",
        "data-model-candidate-analyzer",
        "interaction-boundary-analyzer",
        "structured-file-shape-analyzer",
    }
    assert not analyzers.intersection({
        "java-type-structure-analyzer",
        "java-persistence-mapping-analyzer",
        "java-storage-usage-analyzer",
        "java-model-storage-analyzer",
        "persistence-lineage-analyzer",
        "reference-data-analyzer",
        "system-description-analyzer",
        "value-flow-analyzer",
        "sql-analysis-analyzer",
    })
    existing_only_diagnostics = {
        item.get("artifact_kind")
        for item in plan["diagnostics"]
        if item.get("diagnostic_id") == "optional_evidence_existing_only_not_available"
    }
    assert {
        "java-type-structure-evidence",
        "java-persistence-mapping-evidence",
        "storage-usage-evidence",
        "model-storage-evidence",
        "persistence-lineage-evidence",
        "reference-data-evidence",
        "sql-analysis",
        "system-description-evidence",
        "value-flow-evidence",
    }.issubset(existing_only_diagnostics)


def _repository_inventory_plan_for_files(tmp_path: Path, files: dict[str, str], *, mutate_core=None) -> tuple[dict, dict]:
    repository = tmp_path / "applicability-source"
    repository.mkdir(parents=True)
    for relative, content in files.items():
        target = repository / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    core = _core_evidence_payload()
    for contract in core["contracts"]:
        if contract["artifact_kind"] in {
            "repository-structure-evidence",
            "data-model-candidate-evidence",
            "interaction-boundary-evidence",
            "structured-file-shape-evidence",
        }:
            contract["contract_status"] = "runtime_published"
            contract["runtime_publication"]["registration_status"] = "registered"
            contract["current_state_assessment"]["typed_runtime_artifact_published"] = True
            applicability = contract["preflight_planning"]["applicability"]
            applicability["status"] = "formalized"
            if contract["artifact_kind"] in {"data-model-candidate-evidence", "interaction-boundary-evidence"}:
                applicability["required_languages_any_of"] = ["java"]
            elif contract["artifact_kind"] == "structured-file-shape-evidence":
                applicability["required_extensions_any_of"] = [".json", ".yaml", ".yml"]
    if mutate_core is not None:
        mutate_core(core)
    for contract in core["contracts"]:
        contract["contract_fingerprint"] = _fingerprint({
            key: value for key, value in contract.items() if key != "contract_fingerprint"
        })
    core["catalog_fingerprint"] = _fingerprint({
        key: value for key, value in core.items() if key != "catalog_fingerprint"
    })

    klc = _runtime_klc("repository-inventory")
    source = inspect_repository_source(repository, source_id="client-profile")
    inventory = build_knowledge_input_inventory(
        scope_kind="repository",
        scope_id="client-profile",
        source_snapshots=[source],
        core_evidence_catalog=core,
        materialization_catalog=klc,
    )
    plan = compile_knowledge_execution_plan(
        knowledge_catalog=_catalog_for(core, klc),
        knowledge_profile=_profile("repository-inventory", scope="repository"),
        input_inventory=inventory,
        core_evidence_catalog=core,
        materialization_catalog=klc,
    )
    return plan, source


def test_repository_source_snapshot_observes_extensions_for_core_owned_applicability(tmp_path: Path) -> None:
    repository = tmp_path / "landscape"
    repository.mkdir()
    (repository / "Customer.JAVA").write_text("class Customer {}", encoding="utf-8")
    (repository / "application.YAML").write_text("service: customer\n", encoding="utf-8")
    (repository / "query.SQL").write_text("select 1", encoding="utf-8")

    source = inspect_repository_source(repository, source_id="landscape")

    assert source["languages"] == ["java", "sql", "yaml"]
    assert source["extensions"] == [".java", ".sql", ".yaml"]
    assert source["file_count"] == 3


def test_repository_inventory_automatic_p1_skips_only_observed_non_applicable_producers(tmp_path: Path) -> None:
    plan, source = _repository_inventory_plan_for_files(
        tmp_path,
        {"query.sql": "select 1"},
    )

    assert source["languages"] == ["sql"]
    assert source["extensions"] == [".sql"]
    analyzers = {
        item["analyzer_id"]
        for item in plan["graph"]["nodes"]
        if item.get("node_kind") == "core_evidence_analyzer"
    }
    assert analyzers == {"repository-structure-analyzer"}
    skipped = {
        item.get("artifact_kind")
        for item in plan["diagnostics"]
        if item.get("diagnostic_id") == "evidence_observed_not_applicable_for_source"
    }
    assert skipped == {
        "data-model-candidate-evidence",
        "interaction-boundary-evidence",
        "structured-file-shape-evidence",
    }
    assert plan["status"]["overall"] == "ready"


def test_repository_inventory_applicability_is_dimension_specific(tmp_path: Path) -> None:
    java_plan, _ = _repository_inventory_plan_for_files(
        tmp_path / "java-case",
        {"Customer.java": "class Customer {}"},
    )
    java_analyzers = {
        item["analyzer_id"]
        for item in java_plan["graph"]["nodes"]
        if item.get("node_kind") == "core_evidence_analyzer"
    }
    assert java_analyzers == {
        "repository-structure-analyzer",
        "data-model-candidate-analyzer",
        "interaction-boundary-analyzer",
    }

    structured_plan, _ = _repository_inventory_plan_for_files(
        tmp_path / "structured-case",
        {"application.yaml": "service: customer\n"},
    )
    structured_analyzers = {
        item["analyzer_id"]
        for item in structured_plan["graph"]["nodes"]
        if item.get("node_kind") == "core_evidence_analyzer"
    }
    assert structured_analyzers == {
        "repository-structure-analyzer",
        "structured-file-shape-analyzer",
    }


def test_unresolved_core_applicability_preserves_automatic_execution_eligibility(tmp_path: Path) -> None:
    def make_candidate_unresolved(core: dict) -> None:
        contract = next(
            item for item in core["contracts"]
            if item["artifact_kind"] == "data-model-candidate-evidence"
        )
        contract["preflight_planning"]["applicability"]["status"] = "not_formalized"

    plan, _ = _repository_inventory_plan_for_files(
        tmp_path,
        {"query.sql": "select 1"},
        mutate_core=make_candidate_unresolved,
    )

    analyzers = {
        item["analyzer_id"]
        for item in plan["graph"]["nodes"]
        if item.get("node_kind") == "core_evidence_analyzer"
    }
    assert "data-model-candidate-analyzer" in analyzers
    assert "interaction-boundary-analyzer" not in analyzers
    assert any(
        item.get("diagnostic_id") == "evidence_applicability_unresolved_execution_preserved"
        and item.get("artifact_kind") == "data-model-candidate-evidence"
        for item in plan["diagnostics"]
    )


def test_explicit_required_evidence_reports_observed_blocking_non_applicability(tmp_path: Path) -> None:
    repository = tmp_path / "sql-only"
    repository.mkdir()
    (repository / "query.sql").write_text("select 1", encoding="utf-8")
    core = _core_evidence_payload()
    java_type = next(
        item for item in core["contracts"]
        if item["artifact_kind"] == "java-type-structure-evidence"
    )
    java_type["preflight_planning"]["applicability"].update({
        "status": "formalized",
        "required_languages_any_of": ["java"],
        "required_extensions_any_of": [],
    })
    java_type["contract_fingerprint"] = _fingerprint({
        key: value for key, value in java_type.items() if key != "contract_fingerprint"
    })
    core["catalog_fingerprint"] = _fingerprint({
        key: value for key, value in core.items() if key != "catalog_fingerprint"
    })
    klc = _runtime_klc("code-declared-data-model")
    inventory = build_knowledge_input_inventory(
        scope_kind="repository",
        scope_id="client-profile",
        source_snapshots=[inspect_repository_source(repository, source_id="client-profile")],
        core_evidence_catalog=core,
        materialization_catalog=klc,
    )

    plan = compile_knowledge_execution_plan(
        knowledge_catalog=_catalog_for(core, klc),
        knowledge_profile=_profile("code-declared-data-model", scope="repository"),
        input_inventory=inventory,
        core_evidence_catalog=core,
        materialization_catalog=klc,
    )

    assert plan["status"]["overall"] == "blocked"
    assert not any(
        item.get("node_kind") == "core_evidence_analyzer"
        and item.get("analyzer_id") == "java-type-structure-analyzer"
        for item in plan["graph"]["nodes"]
    )
    blocking = next(
        item for item in plan["diagnostics"]
        if item.get("diagnostic_id") == "required_evidence_observed_not_applicable"
    )
    assert blocking["artifact_kind"] == "java-type-structure-evidence"
    assert blocking["basis"] == "observed_source_landscape"
    assert blocking["source_decisions"][0]["status"] == "not_applicable"
    assert any(item.get("diagnostic_id") == "required_evidence_unsatisfied" for item in plan["diagnostics"])
