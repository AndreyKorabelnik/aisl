from __future__ import annotations

import hashlib
import json
from pathlib import Path

import duckdb

from knowledge_layer_core.materialization_runtime import materialize


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
        "request_contract_signature": [{"attribute_path": "profile.id", "wire_name": "profile.id"}],
    }


def _evidence(root: Path, repo_id: str, interfaces: list[dict], *, service_aliases: list[str]) -> dict:
    evidence_root = root / repo_id / "evidence"
    payload_root = evidence_root / "interaction-boundary-payload" / "compact"
    payload_root.mkdir(parents=True)
    catalog = payload_root / "system_interface_catalog.json"
    catalog.write_text(json.dumps({"all_interfaces": interfaces}), encoding="utf-8")
    envelope = evidence_root / "interaction-boundary-evidence.json"
    content = {
        "contract_version": "core_evidence_artifact_contract/v1",
        "artifact_id": f"artifact-{repo_id}",
        "artifact_kind": "interaction-boundary-evidence",
        "schema_version": "interaction-boundary-evidence/v1",
        "content_fingerprint": f"fingerprint-{repo_id}",
        "source_snapshot": {"source_id": repo_id, "fingerprint": f"source-{repo_id}"},
        "coverage": {"coverage_status": "complete"},
        "diagnostics": [],
        "provenance": {},
        "payload": {
            "repository_identity": {"repo_id": repo_id, "system_id": repo_id, "project_id": "p1", "service_aliases": service_aliases},
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


def test_system_interactions_materializes_from_typed_boundaries(tmp_path: Path) -> None:
    source = _evidence(tmp_path, "source", [
        _interface("source-out", direction="outbound", operation="TargetClient.update", path="/update")
    ], service_aliases=["source-service"])
    target = _evidence(tmp_path, "target", [
        _interface("target-in", direction="inbound", operation="TargetController.update", path="/update")
    ], service_aliases=["target-service"])
    output = tmp_path / "knowledge"
    result = materialize({
        "schema_version": "knowledge_materialization_request/v1",
        "materialization_id": "system-interactions",
        "scope_id": "workspace",
        "inputs": {"evidence_artifacts": [source, target], "knowledge_artifacts": []},
        "parameters": {},
    }, output)

    assert result["status"] == "completed"
    assert result["published_capabilities"] == [
        "workspace.repository-interaction-boundaries",
        "workspace.system-interactions",
    ]
    con = duckdb.connect(str(output / "knowledge-layer.duckdb"), read_only=True)
    try:
        assert con.execute("select count(*) from repository_interaction_boundary").fetchone()[0] == 2
        assert con.execute("select count(*) from system_boundary_interaction").fetchone()[0] == 1
        assert con.execute("select count(*) from system_interaction").fetchone()[0] == 1
        assert not con.execute("select count(*) from information_schema.tables where table_name='analysis_task'").fetchone()[0]
    finally:
        con.close()


def test_loopback_mock_authority_is_non_binding_for_real_route_matching(tmp_path: Path) -> None:
    outbound = _interface(
        "source-out",
        direction="outbound",
        operation="TargetClient.update",
        path="/update",
    )
    outbound.pop("service_aliases", None)
    outbound.update(
        {
            "endpoint_or_topic_raw": "updatePath",
            "endpoint_or_topic_resolved": "client.target.url + updatePath",
            "base_url_property_keys": ["client.target.url"],
            "base_url_observed_values": [
                "http://localhost:8093",
                "${sid.common.target.url}",
            ],
            "endpoint_url_variants": [
                "http://localhost:8093/update",
                "${sid.common.target.url}/update",
            ],
        }
    )
    source = _evidence(tmp_path, "source", [outbound], service_aliases=["source-service"])
    target = _evidence(
        tmp_path,
        "target",
        [_interface("target-in", direction="inbound", operation="TargetController.update", path="/update")],
        service_aliases=["target-service"],
    )
    output = tmp_path / "knowledge"
    result = materialize(
        {
            "schema_version": "knowledge_materialization_request/v1",
            "materialization_id": "system-interactions",
            "scope_id": "workspace",
            "inputs": {"evidence_artifacts": [source, target], "knowledge_artifacts": []},
            "parameters": {},
        },
        output,
    )

    assert result["status"] == "completed"
    con = duckdb.connect(str(output / "knowledge-layer.duckdb"), read_only=True)
    try:
        boundary = con.execute(
            """select confidence, match_basis_json
               from system_boundary_interaction"""
        ).fetchone()
        assert boundary is not None
        assert boundary[0] == "probable"
        match_basis = json.loads(boundary[1]) if isinstance(boundary[1], str) else boundary[1]
        assert match_basis["outbound_environment_authorities"] == ["localhost", "localhost:8093"]
        assert match_basis["candidate_lookup"]["environment_authority_policy"] == "non_binding"

        inventory = con.execute(
            """select authorities_json, service_identities_json
               from repository_interaction_boundary
               where repo_id='source'"""
        ).fetchone()
        assert inventory is not None
        authorities = json.loads(inventory[0]) if isinstance(inventory[0], str) else inventory[0]
        identities = json.loads(inventory[1]) if isinstance(inventory[1], str) else inventory[1]
        assert "localhost" in authorities
        assert "localhost:8093" in authorities
        assert "updatepath" not in authorities
        assert "updatepath" not in identities
    finally:
        con.close()


def test_typed_local_call_candidates_materialize_execution_context(tmp_path: Path) -> None:
    ingress = _interface("source-in", direction="inbound", operation="SourceController.update", path="/local/update")
    outbound = _interface("source-out", direction="outbound", operation="SourceService.callTarget", path="/update")
    outbound["local_call_chain_candidates"] = [
        {
            "caller_operation": "SourceController.update",
            "called_operation": "SourceService.callTarget",
            "distance_to_boundary": 1,
            "basis": "local_receiver_type_and_method_call",
        }
    ]
    source = _evidence(tmp_path, "source", [ingress, outbound], service_aliases=["source-service"])
    target = _evidence(tmp_path, "target", [
        _interface("target-in", direction="inbound", operation="TargetController.update", path="/update")
    ], service_aliases=["target-service"])

    output = tmp_path / "knowledge"
    result = materialize({
        "schema_version": "knowledge_materialization_request/v1",
        "materialization_id": "system-interactions",
        "scope_id": "workspace",
        "inputs": {"evidence_artifacts": [source, target], "knowledge_artifacts": []},
        "parameters": {},
    }, output)

    assert result["status"] == "completed"
    con = duckdb.connect(str(output / "knowledge-layer.duckdb"), read_only=True)
    try:
        assert con.execute("select count(*) from system_boundary_interaction").fetchone()[0] == 1
        row = con.execute(
            """select source_ingress_operation, outbound_operation, call_chain_json, provenance_json
               from system_interaction_execution_context"""
        ).fetchone()
        assert row is not None
        assert row[0] == "SourceController.update"
        assert row[1] == "SourceService.callTarget"
        assert json.loads(row[2]) == ["SourceController.update", "SourceService.callTarget"]
        provenance = json.loads(row[3])
        assert provenance["call_chain_basis"] == "typed_interaction_boundary_local_call_chain_candidates"
        assert provenance["call_chain_evidence_record_ids"]
    finally:
        con.close()


def test_shared_helper_call_sites_compose_one_boundary_with_multiple_execution_contexts(tmp_path: Path) -> None:
    ingress_a = _interface("source-in-a", direction="inbound", operation="SourceController.create", path="/create")
    ingress_b = _interface("source-in-b", direction="inbound", operation="SourceController.refresh", path="/refresh")

    def helper_outbound(interface_id: str, scenario: str, controller: str) -> dict:
        outbound = _interface(interface_id, direction="outbound", operation=scenario, path="/update")
        outbound.update(
            {
                "client_bean_name": "targetRestTemplate",
                "helper_operation": "SharedTargetSender.send",
                "scenario_operation": scenario,
                "composition_basis": "helper_method_template_and_concrete_call_site",
                "local_call_chain_candidates": [
                    {
                        "caller_operation": controller,
                        "called_operation": scenario,
                        "distance_to_boundary": 1,
                        "basis": "local_receiver_type_and_method_call",
                    }
                ],
            }
        )
        return outbound

    source = _evidence(
        tmp_path,
        "source",
        [
            ingress_a,
            ingress_b,
            helper_outbound("source-out-a", "SourceService.create", "SourceController.create"),
            helper_outbound("source-out-b", "SourceService.refresh", "SourceController.refresh"),
        ],
        service_aliases=["source-service"],
    )
    target = _evidence(tmp_path, "target", [
        _interface("target-in", direction="inbound", operation="TargetController.update", path="/update")
    ], service_aliases=["target-service"])

    output = tmp_path / "knowledge"
    result = materialize({
        "schema_version": "knowledge_materialization_request/v1",
        "materialization_id": "system-interactions",
        "scope_id": "workspace",
        "inputs": {"evidence_artifacts": [source, target], "knowledge_artifacts": []},
        "parameters": {},
    }, output)

    assert result["status"] == "completed"
    con = duckdb.connect(str(output / "knowledge-layer.duckdb"), read_only=True)
    try:
        assert con.execute("select count(*) from repository_interaction_boundary").fetchone()[0] == 4
        assert con.execute("select count(*) from system_boundary_interaction").fetchone()[0] == 1
        interaction = con.execute(
            "select operation_count, execution_context_count from system_interaction"
        ).fetchone()
        assert interaction == (1, 2)

        boundary = con.execute(
            "select outbound_operation, provenance_json, payload_json from system_boundary_interaction"
        ).fetchone()
        assert boundary is not None
        assert boundary[0] == "SharedTargetSender.send"
        provenance = json.loads(boundary[1])
        assert len(provenance["outbound_interface_record_ids"]) == 2
        payload = json.loads(boundary[2])
        assert payload["outbound_interface"]["grouped_outbound_observation_count"] == 2
        assert payload["outbound_interface"]["scenario_operations"] == [
            "SourceService.create",
            "SourceService.refresh",
        ]

        contexts = con.execute(
            """select source_ingress_operation, outbound_operation, call_chain_json
               from system_interaction_execution_context
               order by source_ingress_operation"""
        ).fetchall()
        assert len(contexts) == 2
        assert {row[0] for row in contexts} == {"SourceController.create", "SourceController.refresh"}
        assert all(row[1] == "SharedTargetSender.send" for row in contexts)
        assert all(json.loads(row[2])[-1] == "SharedTargetSender.send" for row in contexts)
    finally:
        con.close()


def test_http_path_case_is_not_folded_into_false_exact_match(tmp_path: Path) -> None:
    source = _evidence(tmp_path, "source", [
        _interface("source-out", direction="outbound", operation="TargetClient.update", path="/UpdateOrCreate")
    ], service_aliases=["source-service"])
    target = _evidence(tmp_path, "target", [
        _interface("target-in", direction="inbound", operation="TargetController.update", path="/updateOrCreate")
    ], service_aliases=["target-service"])
    output = tmp_path / "knowledge"
    result = materialize({
        "schema_version": "knowledge_materialization_request/v1",
        "materialization_id": "system-interactions",
        "scope_id": "workspace",
        "inputs": {"evidence_artifacts": [source, target], "knowledge_artifacts": []},
        "parameters": {},
    }, output)

    assert result["status"] == "completed"
    con = duckdb.connect(str(output / "knowledge-layer.duckdb"), read_only=True)
    try:
        assert con.execute("select count(*) from system_boundary_interaction").fetchone()[0] == 0
        diagnostic = con.execute(
            "select match_status from system_interaction_match_diagnostic where source_repo_id='source'"
        ).fetchone()
        assert diagnostic == ("unresolved",)
        paths = con.execute(
            "select normalized_paths_json from repository_interaction_boundary where repo_id='source'"
        ).fetchone()
        assert json.loads(paths[0]) == ["/UpdateOrCreate"]
    finally:
        con.close()


def test_http_suffix_match_preserves_case_and_reports_normalized_path_basis(tmp_path: Path) -> None:
    source = _evidence(tmp_path, "source", [
        _interface("source-out", direction="outbound", operation="TargetClient.update", path="/ucp/updateOrCreate")
    ], service_aliases=["source-service"])
    target = _evidence(tmp_path, "target", [
        _interface("target-in", direction="inbound", operation="TargetController.update", path="/updateOrCreate")
    ], service_aliases=["target-service"])
    output = tmp_path / "knowledge"
    result = materialize({
        "schema_version": "knowledge_materialization_request/v1",
        "materialization_id": "system-interactions",
        "scope_id": "workspace",
        "inputs": {"evidence_artifacts": [source, target], "knowledge_artifacts": []},
        "parameters": {},
    }, output)

    assert result["status"] == "completed"
    con = duckdb.connect(str(output / "knowledge-layer.duckdb"), read_only=True)
    try:
        row = con.execute(
            "select outbound_endpoint, target_ingress_endpoint, confidence, match_basis_json from system_boundary_interaction"
        ).fetchone()
        assert row is not None
        assert row[0] == "/ucp/updateOrCreate"
        assert row[1] == "/updateOrCreate"
        assert row[2] == "confirmed"
        basis = json.loads(row[3])
        assert basis["path_basis"] == "normalized_path"
        assert basis["outbound_path"] == "/ucp/updateOrCreate"
        assert basis["target_path"] == "/updateOrCreate"
    finally:
        con.close()
