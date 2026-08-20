from __future__ import annotations

import hashlib
import json
from pathlib import Path

import duckdb

from knowledge_layer_core.materialization_runtime import materialize, registered_materialization_ids


def _interface(interface_id: str, *, direction: str, operation: str, path: str) -> dict:
    return {
        "interface_id": interface_id,
        "direction": direction,
        "boundary_kind": "rest_request" if direction == "inbound" else "http_outbound",
        "protocol": "http",
        "http_method": "POST",
        "operation": operation,
        "endpoint_or_topic_raw": path,
        "endpoint_or_topic_resolved": path,
        "endpoint_path_variants": [path] if direction == "outbound" else [],
        "full_path_variants": [path] if direction == "inbound" else [],
        "service_aliases": ["target-service"],
        "request_payload_type": "UpdateRequest",
        "request_contract_signature": [
            {"attribute_path": "profile.id", "wire_name": "profile.id", "attribute_type": "String"}
        ],
    }


def _interaction_evidence(root: Path, repo_id: str, interfaces: list[dict], *, aliases: list[str]) -> dict:
    evidence_root = root / f"{repo_id}-interaction" / "evidence"
    payload_root = evidence_root / "interaction-boundary-payload" / "compact"
    payload_root.mkdir(parents=True)
    catalog = payload_root / "system_interface_catalog.json"
    catalog.write_text(json.dumps({"all_interfaces": interfaces}), encoding="utf-8")
    envelope = evidence_root / "interaction-boundary-evidence.json"
    content = {
        "contract_version": "core_evidence_artifact_contract/v1",
        "artifact_id": f"interaction-{repo_id}",
        "artifact_kind": "interaction-boundary-evidence",
        "schema_version": "interaction-boundary-evidence/v1",
        "content_fingerprint": f"interaction-fp-{repo_id}",
        "source_snapshot": {"source_id": repo_id, "fingerprint": f"source-{repo_id}"},
        "coverage": {"coverage_status": "complete"},
        "diagnostics": [],
        "provenance": {},
        "payload": {
            "repository_identity": {"repo_id": repo_id, "system_id": repo_id, "service_aliases": aliases},
            "boundary_catalog": {
                "artifact_name": "system_interface_catalog.json",
                "relative_path": "interaction-boundary-payload/compact/system_interface_catalog.json",
                "sha256": hashlib.sha256(catalog.read_bytes()).hexdigest(),
                "bytes": catalog.stat().st_size,
                "section": "all_interfaces",
            },
        },
    }
    envelope.write_text(json.dumps(content), encoding="utf-8")
    return {
        "artifact_id": content["artifact_id"],
        "artifact_kind": content["artifact_kind"],
        "schema_version": content["schema_version"],
        "content_fingerprint": content["content_fingerprint"],
        "location": {"kind": "file", "path": str(envelope)},
    }


def _value_flow_evidence(root: Path, repo_id: str, interfaces: list[dict]) -> dict:
    evidence_root = root / f"{repo_id}-value-flow" / "evidence"
    payload = evidence_root / "value-flow-payload"
    (payload / "catalog").mkdir(parents=True)
    (payload / "compact").mkdir(parents=True)
    files = [
        (payload / "catalog/field_occurrences.json", "catalog/field_occurrences.json", [], None),
        (payload / "catalog/field_flow_edges.json", "catalog/field_flow_edges.json", [], None),
        (payload / "compact/system_interface_catalog.json", "system_interface_catalog.json", {"all_interfaces": interfaces}, "all_interfaces"),
    ]
    descriptors = []
    for path, name, value, section in files:
        path.write_text(json.dumps(value), encoding="utf-8")
        descriptors.append({
            "artifact_name": name,
            "relative_path": path.relative_to(evidence_root).as_posix(),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "bytes": path.stat().st_size,
            "section": section,
        })
    envelope = evidence_root / "value-flow-evidence.json"
    content = {
        "contract_version": "core_evidence_artifact_contract/v1",
        "artifact_id": f"value-flow-{repo_id}",
        "artifact_kind": "value-flow-evidence",
        "schema_version": "value-flow-evidence/v1",
        "content_fingerprint": f"value-flow-fp-{repo_id}",
        "source_snapshot": {"source_id": repo_id, "fingerprint": f"source-{repo_id}"},
        "coverage": {"coverage_status": "complete"},
        "diagnostics": [],
        "provenance": {},
        "payload": {"repository_identity": {"repo_id": repo_id}, "artifacts": descriptors},
    }
    envelope.write_text(json.dumps(content), encoding="utf-8")
    return {
        "artifact_id": content["artifact_id"],
        "artifact_kind": content["artifact_kind"],
        "schema_version": content["schema_version"],
        "content_fingerprint": content["content_fingerprint"],
        "location": {"kind": "file", "path": str(envelope)},
    }


def test_interaction_field_contracts_are_a_typed_klc_to_klc_materialization(tmp_path: Path) -> None:
    source_interface = _interface("source-out", direction="outbound", operation="TargetClient.update", path="/update")
    target_interface = _interface("target-in", direction="inbound", operation="TargetController.update", path="/update")

    interactions = materialize({
        "schema_version": "knowledge_materialization_request/v1",
        "materialization_id": "system-interactions",
        "scope_id": "workspace",
        "inputs": {"evidence_artifacts": [
            _interaction_evidence(tmp_path, "source", [source_interface], aliases=["source-service"]),
            _interaction_evidence(tmp_path, "target", [target_interface], aliases=["target-service"]),
        ], "knowledge_artifacts": []},
        "parameters": {},
    }, tmp_path / "interactions")

    value_flow = materialize({
        "schema_version": "knowledge_materialization_request/v1",
        "materialization_id": "repository-value-flow",
        "scope_id": "workspace",
        "inputs": {"evidence_artifacts": [
            _value_flow_evidence(tmp_path, "source", [source_interface]),
            _value_flow_evidence(tmp_path, "target", [target_interface]),
        ], "knowledge_artifacts": []},
        "parameters": {},
    }, tmp_path / "value-flow")

    knowledge = [
        next(item for item in value_flow["knowledge_artifacts"] if item["schema_version"] == "repository_value_flow/v6"),
        next(item for item in interactions["knowledge_artifacts"] if item["schema_version"] == "workspace_system_interaction/v6"),
    ]
    result = materialize({
        "schema_version": "knowledge_materialization_request/v1",
        "materialization_id": "interaction-field-contracts",
        "scope_id": "workspace",
        "inputs": {"evidence_artifacts": [], "knowledge_artifacts": knowledge},
        "parameters": {},
    }, tmp_path / "field-contracts")

    assert "interaction-field-contracts" in registered_materialization_ids()
    assert result["status"] == "completed"
    assert result["published_capabilities"] == ["workspace.system-interaction-field-contracts"]
    assert result["knowledge_artifacts"][0]["schema_version"] == "workspace_system_interaction_field_contract/v2"

    con = duckdb.connect(str(tmp_path / "field-contracts" / "knowledge-layer.duckdb"), read_only=True)
    try:
        row = con.execute(
            """select source_repo_id, target_repo_id, wire_path, match_kind, match_status
               from system_interaction_field_contract"""
        ).fetchone()
        assert row == ("source", "target", "profile.id", "exact_wire_path", "confirmed")
        assert con.execute(
            "select count(*) from information_schema.tables where table_name in ('analysis_task','analysis_suite')"
        ).fetchone()[0] == 0
        assert con.execute(
            "select count(*) from information_schema.tables where lower(table_name)='analysis_record'"
        ).fetchone()[0] == 0
    finally:
        con.close()


def test_cross_repository_value_flow_reuses_restored_contracts(tmp_path: Path) -> None:
    source_interface = _interface("source-out", direction="outbound", operation="TargetClient.update", path="/update")
    target_interface = _interface("target-in", direction="inbound", operation="TargetController.update", path="/update")

    interactions = materialize({
        "schema_version": "knowledge_materialization_request/v1",
        "materialization_id": "system-interactions",
        "scope_id": "workspace",
        "inputs": {"evidence_artifacts": [
            _interaction_evidence(tmp_path, "source", [source_interface], aliases=["source-service"]),
            _interaction_evidence(tmp_path, "target", [target_interface], aliases=["target-service"]),
        ], "knowledge_artifacts": []},
        "parameters": {},
    }, tmp_path / "interactions")
    value_flow = materialize({
        "schema_version": "knowledge_materialization_request/v1",
        "materialization_id": "repository-value-flow",
        "scope_id": "workspace",
        "inputs": {"evidence_artifacts": [
            _value_flow_evidence(tmp_path, "source", [source_interface]),
            _value_flow_evidence(tmp_path, "target", [target_interface]),
        ], "knowledge_artifacts": []},
        "parameters": {},
    }, tmp_path / "value-flow")
    contracts = materialize({
        "schema_version": "knowledge_materialization_request/v1",
        "materialization_id": "interaction-field-contracts",
        "scope_id": "workspace",
        "inputs": {"evidence_artifacts": [], "knowledge_artifacts": [
            next(item for item in value_flow["knowledge_artifacts"] if item["schema_version"] == "repository_value_flow/v6"),
            next(item for item in interactions["knowledge_artifacts"] if item["schema_version"] == "workspace_system_interaction/v6"),
        ]},
        "parameters": {},
    }, tmp_path / "field-contracts")

    result = materialize({
        "schema_version": "knowledge_materialization_request/v1",
        "materialization_id": "cross-repository-value-flow",
        "scope_id": "workspace",
        "inputs": {"evidence_artifacts": [], "knowledge_artifacts": [
            next(item for item in value_flow["knowledge_artifacts"] if item["schema_version"] == "repository_value_flow/v6"),
            next(item for item in interactions["knowledge_artifacts"] if item["schema_version"] == "workspace_system_interaction/v6"),
            next(item for item in contracts["knowledge_artifacts"] if item["schema_version"] == "workspace_system_interaction_field_contract/v2"),
        ]},
        "parameters": {},
    }, tmp_path / "cross-value-flow")

    assert result["status"] == "completed"
    assert "workspace.cross-repository-value-flow" in result["published_capabilities"]
    assert result["output"]["counts"]["cross_repository_transport_edge"] == 1
    con = duckdb.connect(str(tmp_path / "cross-value-flow" / "knowledge-layer.duckdb"), read_only=True)
    try:
        row = con.execute(
            """select source_repo_id, target_repo_id, flow_kind, source_edge_kind, confidence
               from repository_value_flow_edge
               where source_repo_id<>target_repo_id"""
        ).fetchone()
        assert row == ("source", "target", "transport", "http_request_transport", "confirmed")
        classified = con.execute(
            "SELECT knowledge_class FROM repository_value_flow_edge_classified WHERE source_repo_id<>target_repo_id"
        ).fetchone()
        assert classified == ("confirmed",)
        assert con.execute("SELECT count(*) FROM repository_value_flow_edge_strict").fetchone()[0] >= 1
        assert con.execute("SELECT count(*) FROM repository_value_flow_edge_working").fetchone()[0] >= 1
        assert con.execute("SELECT count(*) FROM repository_value_flow_edge_exploratory").fetchone()[0] >= 1
        source_node_id, target_node_id = con.execute(
            """select source_value_node_id, target_value_node_id
               from repository_value_flow_edge
               where source_repo_id<>target_repo_id"""
        ).fetchone()
    finally:
        con.close()

    from prepared_knowledge_runtime.query import KnowledgeLayerQuery
    resolved = KnowledgeLayerQuery(tmp_path / "cross-value-flow" / "knowledge-layer.duckdb").resolve_attribute_paths(
        source_node_id,
        target=target_node_id,
        selected_repo_ids=["source", "target"],
        minimum_confidence="confirmed",
    )
    assert resolved["status"] == "confirmed_complete"
    assert resolved["paths"][0]["knowledge_class"] == "confirmed"
    assert resolved["stats"]["complete_path_count"] == 1


def test_cross_repository_value_flow_materializes_wire_nodes_for_composed_outbound_boundary(tmp_path: Path) -> None:
    source_a = _interface("source-out-a", direction="outbound", operation="ScenarioA.update", path="/update")
    source_b = _interface("source-out-b", direction="outbound", operation="ScenarioB.update", path="/update")
    for source, scenario in ((source_a, "ScenarioA.update"), (source_b, "ScenarioB.update")):
        source.update({
            "scenario_operation": scenario,
            "helper_operation": "SharedRestSender.send",
            "client_bean_name": "sharedRestTemplate",
            "composition_basis": "helper_method_template_and_concrete_call_site",
            "local_caller_operations": [scenario],
        })
    target_interface = _interface("target-in", direction="inbound", operation="TargetController.update", path="/update")

    interactions = materialize({
        "schema_version": "knowledge_materialization_request/v1",
        "materialization_id": "system-interactions",
        "scope_id": "workspace",
        "inputs": {"evidence_artifacts": [
            _interaction_evidence(tmp_path, "source", [source_a, source_b], aliases=["source-service"]),
            _interaction_evidence(tmp_path, "target", [target_interface], aliases=["target-service"]),
        ], "knowledge_artifacts": []},
        "parameters": {},
    }, tmp_path / "interactions")

    interaction_db = duckdb.connect(str(tmp_path / "interactions" / "knowledge-layer.duckdb"), read_only=True)
    try:
        outbound_interface_id, boundary_count = interaction_db.execute(
            "SELECT min(outbound_interface_id), count(*) FROM system_boundary_interaction"
        ).fetchone()
        assert boundary_count == 1
        assert outbound_interface_id.startswith("composed_http_outbound_boundary_")
    finally:
        interaction_db.close()

    value_flow = materialize({
        "schema_version": "knowledge_materialization_request/v1",
        "materialization_id": "repository-value-flow",
        "scope_id": "workspace",
        "inputs": {"evidence_artifacts": [
            _value_flow_evidence(tmp_path, "source", [source_a, source_b]),
            _value_flow_evidence(tmp_path, "target", [target_interface]),
        ], "knowledge_artifacts": []},
        "parameters": {},
    }, tmp_path / "value-flow")
    contracts = materialize({
        "schema_version": "knowledge_materialization_request/v1",
        "materialization_id": "interaction-field-contracts",
        "scope_id": "workspace",
        "inputs": {"evidence_artifacts": [], "knowledge_artifacts": [
            next(item for item in value_flow["knowledge_artifacts"] if item["schema_version"] == "repository_value_flow/v6"),
            next(item for item in interactions["knowledge_artifacts"] if item["schema_version"] == "workspace_system_interaction/v6"),
        ]},
        "parameters": {},
    }, tmp_path / "field-contracts")
    result = materialize({
        "schema_version": "knowledge_materialization_request/v1",
        "materialization_id": "cross-repository-value-flow",
        "scope_id": "workspace",
        "inputs": {"evidence_artifacts": [], "knowledge_artifacts": [
            next(item for item in value_flow["knowledge_artifacts"] if item["schema_version"] == "repository_value_flow/v6"),
            next(item for item in interactions["knowledge_artifacts"] if item["schema_version"] == "workspace_system_interaction/v6"),
            next(item for item in contracts["knowledge_artifacts"] if item["schema_version"] == "workspace_system_interaction_field_contract/v2"),
        ]},
        "parameters": {},
    }, tmp_path / "cross-value-flow")

    assert result["status"] == "completed"
    assert result["output"]["counts"]["cross_repository_transport_edge"] == 1
    con = duckdb.connect(str(tmp_path / "cross-value-flow" / "knowledge-layer.duckdb"), read_only=True)
    try:
        source_owner, boundary_id = con.execute(
            """select n.owner_ref, json_extract_string(e.payload_json, '$.transport.boundary_interaction_id')
               from repository_value_flow_edge e
               join repository_value_node n on n.value_node_id=e.source_value_node_id
               where e.source_repo_id<>e.target_repo_id"""
        ).fetchone()
        assert source_owner == outbound_interface_id
        assert boundary_id
        composition_rows = con.execute(
            """select s.owner_ref, t.owner_ref, e.flow_kind, e.confidence
               from repository_value_flow_edge e
               join repository_value_node s on s.value_node_id=e.source_value_node_id
               join repository_value_node t on t.value_node_id=e.target_value_node_id
               where e.flow_kind='boundary_composition'
               order by s.owner_ref"""
        ).fetchall()
        assert composition_rows == [
            ("source-out-a", outbound_interface_id, "boundary_composition", "confirmed"),
            ("source-out-b", outbound_interface_id, "boundary_composition", "confirmed"),
        ]
    finally:
        con.close()
