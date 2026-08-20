from __future__ import annotations

import json

import duckdb

from prepared_knowledge_runtime.attribute_paths import ATTRIBUTE_PATH_SCHEMA_VERSION
from knowledge_layer_core.evidence import execute_evidence_request, load_evidence_tool_catalog
from prepared_knowledge_runtime.query import KnowledgeLayerQuery
from knowledge_layer_core.value_flow_knowledge_schema import VALUE_FLOW_KNOWLEDGE_DDL


def _node(con, node_id: str, repo_id: str, display_ref: str, *, kind: str = "field", occurrence_id: str | None = None) -> None:
    con.execute(
        """INSERT INTO repository_value_node (
               value_node_id, scope_id, repo_id, occurrence_id, node_kind, operation,
               owner_ref, display_ref, type_ref, wire_path, source_path, provenance_json, payload_json
           ) VALUES (?, 'scope', ?, ?, ?, NULL, NULL, ?, NULL, NULL, NULL, json('{}'), json('{}'))""",
        [node_id, repo_id, occurrence_id or node_id, kind, display_ref],
    )


def _edge(
    con,
    edge_id: str,
    source_repo: str,
    target_repo: str,
    source_node: str,
    target_node: str,
    *,
    flow_kind: str = "assignment",
    source_edge_kind: str = "assignment",
    transformation: str = "identity",
    naming_relation: str = "same_name",
    preservation: str = "preserved",
    confidence: str = "confirmed",
) -> None:
    con.execute(
        """INSERT INTO repository_value_flow_edge (
               value_flow_edge_id, scope_id, source_repo_id, target_repo_id,
               source_value_node_id, target_value_node_id, source_occurrence_id,
               target_occurrence_id, flow_kind, source_edge_kind, transformation_kind,
               naming_relation, value_preservation, confidence, derivation_id,
               derivation_kind, derivation_source_count, guards_json, provenance_json, payload_json
           ) VALUES (?, 'scope', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, 0,
                     json('[]'), json('{}'), json('{}'))""",
        [
            edge_id,
            source_repo,
            target_repo,
            source_node,
            target_node,
            source_node,
            target_node,
            flow_kind,
            source_edge_kind,
            transformation,
            naming_relation,
            preservation,
            confidence,
        ],
    )


def _database(tmp_path):
    db = tmp_path / "knowledge-layer.duckdb"
    con = duckdb.connect(str(db))
    con.execute(VALUE_FLOW_KNOWLEDGE_DDL)
    return db, con


def test_resolves_complete_cross_repository_attribute_path(tmp_path) -> None:
    db, con = _database(tmp_path)
    _node(con, "a-source", "a", "A.Inbound.customerId")
    _node(con, "a-out", "a", "A.Outbound.partyId")
    _node(con, "a-wire", "a", "A HTTP request $.partyId", kind="wire_field")
    _node(con, "b-wire", "b", "B HTTP request $.partyId", kind="wire_field")
    _node(con, "b-target", "b", "B.Inbound.clientId")
    _edge(con, "e1", "a", "a", "a-source", "a-out", naming_relation="renamed")
    _edge(con, "e2", "a", "a", "a-out", "a-wire", flow_kind="serialization", source_edge_kind="http_request_serialization")
    _edge(con, "e3", "a", "b", "a-wire", "b-wire", flow_kind="transport", source_edge_kind="http_request_transport")
    _edge(con, "e4", "b", "b", "b-wire", "b-target", flow_kind="deserialization", source_edge_kind="http_request_deserialization", naming_relation="renamed")
    con.close()

    query = KnowledgeLayerQuery(db)
    result = query.resolve_attribute_paths(
        "A.Inbound.customerId",
        target="B.Inbound.clientId",
        selected_repo_ids=["a", "b"],
    )

    assert result["schema_version"] == ATTRIBUTE_PATH_SCHEMA_VERSION
    assert result["status"] == "confirmed_complete"
    assert result["stats"]["complete_path_count"] == 1
    assert result["stats"]["partial_path_count"] == 0
    assert result["paths"][0]["hop_count"] == 4
    assert [step["flow_kind"] for step in result["paths"][0]["steps"]] == [
        "assignment",
        "serialization",
        "transport",
        "deserialization",
    ]
    assert result["paths"][0]["steps"][2]["source_repo_id"] == "a"
    assert result["paths"][0]["steps"][2]["target_repo_id"] == "b"
    assert "workspace.attribute-path-resolver" in query.capabilities()


def test_returns_partial_path_and_explicit_gap(tmp_path) -> None:
    db, con = _database(tmp_path)
    _node(con, "source", "a", "A.source")
    _node(con, "middle", "a", "A.middle")
    _node(con, "unreachable", "b", "B.target")
    _edge(con, "e1", "a", "a", "source", "middle")
    con.close()

    result = KnowledgeLayerQuery(db).resolve_attribute_paths(
        "source",
        target="unreachable",
        selected_repo_ids=["a", "b"],
    )
    assert result["status"] == "partial"
    assert result["paths"][0]["status"] == "partial"
    assert result["paths"][0]["end"]["value_node_id"] == "middle"
    assert result["paths"][0]["gap"]["reason"] == "no_observed_outgoing_value_flow"
    assert any(gap["reason"] == "no_observed_outgoing_value_flow" for gap in result["gaps"])


def test_reports_ambiguous_complete_paths_without_collapsing_them(tmp_path) -> None:
    db, con = _database(tmp_path)
    for node_id in ("source", "left", "right", "target"):
        _node(con, node_id, "a", node_id)
    _edge(con, "left-1", "a", "a", "source", "left")
    _edge(con, "left-2", "a", "a", "left", "target")
    _edge(con, "right-1", "a", "a", "source", "right")
    _edge(con, "right-2", "a", "a", "right", "target")
    con.close()

    result = KnowledgeLayerQuery(db).resolve_attribute_paths(
        "source", target="target", selected_repo_ids=["a"]
    )
    assert result["status"] == "ambiguous"
    assert result["stats"]["complete_path_count"] == 2
    assert len([path for path in result["paths"] if path["status"] == "complete"]) == 2
    assert result["branch_points"][0]["outgoing_edge_count"] == 2


def test_bounds_branching_cycles_and_confidence(tmp_path) -> None:
    db, con = _database(tmp_path)
    for node_id in ("source", "a", "b", "c"):
        _node(con, node_id, "repo", node_id)
    _edge(con, "e-a", "repo", "repo", "source", "a")
    _edge(con, "e-b", "repo", "repo", "source", "b")
    _edge(con, "e-c", "repo", "repo", "source", "c", confidence="probable")
    _edge(con, "cycle", "repo", "repo", "a", "source")
    con.close()

    query = KnowledgeLayerQuery(db)
    limited = query.resolve_attribute_paths(
        "source",
        selected_repo_ids=["repo"],
        max_branching=1,
        max_paths=5,
        minimum_confidence="confirmed",
    )
    assert limited["stats"]["truncated"] is True
    assert any(gap["reason"] == "branching_limit_reached" for gap in limited["gaps"])
    assert any(gap["reason"] == "cycle_prevented" for gap in limited["gaps"])
    assert limited["stats"]["edge_count"] == 3  # probable e-c is excluded


def test_endpoint_resolution_is_exact_and_repository_scoped(tmp_path) -> None:
    db, con = _database(tmp_path)
    _node(con, "a-id", "a", "Request.customerId")
    _node(con, "b-id", "b", "Request.customerId")
    con.close()

    query = KnowledgeLayerQuery(db)
    ambiguous = query.resolve_attribute_paths(
        "Request.customerId", selected_repo_ids=["a", "b"]
    )
    assert ambiguous["status"] == "source_ambiguous"
    assert len(ambiguous["source_candidates"]) == 2

    resolved = query.resolve_attribute_paths(
        "Request.customerId", selected_repo_ids=["a"]
    )
    assert resolved["status"] == "partial"
    assert resolved["source"]["value_node_id"] == "a-id"


def test_new_evidence_tool_replaces_legacy_path_commands(tmp_path) -> None:
    db, con = _database(tmp_path)
    _node(con, "source", "a", "source")
    _node(con, "target", "a", "target")
    _edge(con, "edge", "a", "a", "source", "target")
    con.close()

    tools = {tool["command_id"]: tool for tool in load_evidence_tool_catalog()["tools"]}
    assert tools["knowledge_layer_attribute_paths"]["required_capabilities"] == [
        "workspace.attribute-path-resolver"
    ]
    for legacy in (
        "knowledge_layer_neighborhood",
        "knowledge_layer_reachable",
        "knowledge_layer_paths",
        "knowledge_layer_boundary_to_storage",
        "knowledge_layer_field_flow",
        "knowledge_layer_unresolved_bridges",
    ):
        assert legacy not in tools

    result = execute_evidence_request(
        {
            "command_id": "knowledge_layer_attribute_paths",
            "arguments": {
                "source": "source",
                "target": "target",
                "selected_repo_ids": ["a"],
            },
        },
        knowledge_layer_path=db,
    )
    assert result["status"] == "confirmed_complete"
    assert result["paths"][0]["hop_count"] == 1


def test_probable_candidate_transport_produces_probable_complete_with_evidence_summary(tmp_path) -> None:
    db, con = _database(tmp_path)
    _node(con, "source", "a", "A.source")
    _node(con, "a-wire", "a", "A HTTP request $.id", kind="wire_field")
    _node(con, "b-wire", "b", "B HTTP request $.id", kind="wire_field")
    _node(con, "target", "b", "B.target")
    _edge(con, "local-a", "a", "a", "source", "a-wire", flow_kind="serialization")
    _edge(con, "candidate", "a", "b", "a-wire", "b-wire", flow_kind="transport", source_edge_kind="http_request_transport", confidence="probable")
    con.execute(
        "UPDATE repository_value_flow_edge SET provenance_json=json(?) WHERE value_flow_edge_id='candidate'",
        [json.dumps({
            "evidence_packet": {
                "edge_status": "candidate",
                "supporting_evidence": ["normalized_path_exact", "property_identity_exact"],
                "conflicting_evidence": [],
                "limitations": ["environment_authority_non_binding"],
            }
        })],
    )
    _edge(con, "local-b", "b", "b", "b-wire", "target", flow_kind="deserialization")
    con.close()

    exploratory = KnowledgeLayerQuery(db).resolve_attribute_paths(
        "A.source", target="B.target", selected_repo_ids=["a", "b"], minimum_confidence="probable"
    )
    assert exploratory["status"] == "probable_complete"
    path = exploratory["paths"][0]
    assert path["confidence"] == "probable"
    assert path["knowledge_class"] == "derived"
    assert path["evidence_summary"]["derived_step_count"] == 1
    assert path["evidence_summary"]["candidate_step_count"] == 0
    assert "property_identity_exact" in path["evidence_summary"]["supporting_evidence"]
    assert "environment_authority_non_binding" in path["evidence_summary"]["limitations"]

    strict = KnowledgeLayerQuery(db).resolve_attribute_paths(
        "A.source", target="B.target", selected_repo_ids=["a", "b"], knowledge_view="strict", minimum_confidence="probable"
    )
    assert strict["status"] == "partial"
    assert strict["stats"]["complete_path_count"] == 0
    assert strict["constraints"]["knowledge_view"] == "strict"


def test_exploratory_view_exposes_candidate_edge_without_promoting_it(tmp_path) -> None:
    db, con = _database(tmp_path)
    _node(con, "a", "source", "Source.value")
    _node(con, "b", "target", "Target.value")
    _edge(
        con,
        "candidate-edge",
        "source",
        "target",
        "a",
        "b",
        flow_kind="transport",
        source_edge_kind="http_request_transport",
        confidence="unknown",
    )
    con.close()

    query = KnowledgeLayerQuery(db)
    assert query.repository_value_flow_edges(knowledge_view="strict")["total_count"] == 0
    assert query.repository_value_flow_edges(knowledge_view="working")["total_count"] == 0
    exploratory = query.repository_value_flow_edges(knowledge_view="exploratory")
    assert exploratory["total_count"] == 1
    assert exploratory["items"][0]["knowledge_class"] == "candidate"

    path = query.resolve_attribute_paths(
        "Source.value",
        target="Target.value",
        selected_repo_ids=["source", "target"],
        knowledge_view="exploratory",
        minimum_confidence="unknown",
    )
    assert path["stats"]["complete_path_count"] == 1
    assert path["paths"][0]["knowledge_class"] == "candidate"
    assert path["paths"][0]["evidence_summary"]["candidate_step_count"] == 1
