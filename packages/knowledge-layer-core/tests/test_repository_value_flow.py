from __future__ import annotations

import json

import duckdb

from prepared_knowledge_runtime.query import KnowledgeLayerQuery
from knowledge_layer_core.interaction_knowledge_schema import INTERACTION_KNOWLEDGE_DDL
from knowledge_layer_core.value_flow import materialize_repository_value_flow
from knowledge_layer_core.value_flow_knowledge_schema import VALUE_FLOW_KNOWLEDGE_DDL


def _record(con, *, record_id: str, artifact: str, ordinal: int, payload: dict, repo_id: str = "source") -> None:
    con.execute(
        """INSERT INTO value_flow_evidence_record (
               record_occurrence_id, scope_id, repo_id, artifact_name,
               local_record_id, occurrence_ordinal, payload_json
           ) VALUES (?, 'scope', ?, ?, ?, ?, json(?))""",
        [record_id, repo_id, artifact, payload.get("occurrence_id") or payload.get("edge_id"), ordinal, json.dumps(payload)],
    )


def test_materializes_direct_typed_value_graph_without_transitive_paths(tmp_path) -> None:
    db = tmp_path / "knowledge-layer.duckdb"
    con = duckdb.connect(str(db))
    con.execute(VALUE_FLOW_KNOWLEDGE_DDL)
    con.execute(INTERACTION_KNOWLEDGE_DDL)

    occurrences = [
        {
            "occurrence_id": "inbound-customer-id",
            "operation": "Controller.handle",
            "occurrence_kind": "boundary_field",
            "field_path": "request.customerId",
            "declared_type": "String",
            "relative_file": "src/main/java/Controller.java",
        },
        {
            "occurrence_id": "parameter-client-id",
            "operation": "Service.process",
            "occurrence_kind": "parameter",
            "symbol": "clientId",
            "declared_type": "String",
            "relative_file": "src/main/java/Service.java",
        },
        {
            "occurrence_id": "outbound-party-id",
            "operation": "Client.send",
            "occurrence_kind": "boundary_field",
            "field_path": "request.partyId",
            "declared_type": "String",
            "relative_file": "src/main/java/Client.java",
        },
        {
            "occurrence_id": "method-return",
            "operation": "Service.process",
            "occurrence_kind": "method_return",
            "field_path": "Service.process.return",
            "declared_type": "String",
            "relative_file": "src/main/java/Service.java",
        },
        {
            "occurrence_id": "literal",
            "operation": "Client.send",
            "occurrence_kind": "literal",
            "expression_text": '"fixed"',
            "relative_file": "src/main/java/Client.java",
        },
        {
            "occurrence_id": "generated-time",
            "operation": "Client.send",
            "occurrence_kind": "method_invocation",
            "expression_text": "Instant.now()",
            "relative_file": "src/main/java/Client.java",
        },
    ]
    for ordinal, payload in enumerate(occurrences, 1):
        _record(
            con,
            record_id=f"occ-{payload['occurrence_id']}",
            artifact="catalog/field_occurrences.json",
            ordinal=ordinal,
            payload=payload,
        )

    edges = [
        ("edge-parameter", "inbound-customer-id", "parameter-client-id", "parameter_binding"),
        ("edge-argument", "parameter-client-id", "outbound-party-id", "invocation_argument"),
        ("edge-return", "parameter-client-id", "method-return", "method_return"),
        ("edge-literal", "literal", "outbound-party-id", "variable_initializer"),
        ("edge-time", "generated-time", "outbound-party-id", "invocation_argument"),
    ]
    for ordinal, (edge_id, source, target, edge_kind) in enumerate(edges, 20):
        _record(
            con,
            record_id=f"record-{edge_id}",
            artifact="catalog/field_flow_edges.json",
            ordinal=ordinal,
            payload={
                "edge_id": edge_id,
                "source_occurrence_id": source,
                "target_occurrence_id": target,
                "edge_kind": edge_kind,
                "guards": [],
                "relative_file": "src/main/java/Flow.java",
            },
        )

    result = materialize_repository_value_flow(con, scope_id="scope")
    assert result == {"repository_value_node": 6, "repository_value_flow_edge": 5}

    nodes = con.execute(
        """SELECT occurrence_id, node_kind FROM repository_value_node ORDER BY occurrence_id"""
    ).fetchall()
    assert nodes == [
        ("generated-time", "generated_value"),
        ("inbound-customer-id", "field"),
        ("literal", "constant"),
        ("method-return", "return_value"),
        ("outbound-party-id", "field"),
        ("parameter-client-id", "parameter"),
    ]

    direct_edges = con.execute(
        """SELECT source_occurrence_id, target_occurrence_id, flow_kind,
                  transformation_kind, naming_relation, value_preservation
           FROM repository_value_flow_edge
           ORDER BY source_occurrence_id, target_occurrence_id"""
    ).fetchall()
    assert direct_edges == [
        ("generated-time", "outbound-party-id", "argument_binding", "identity", "not_applicable", "preserved"),
        ("inbound-customer-id", "parameter-client-id", "argument_binding", "identity", "not_applicable", "preserved"),
        ("literal", "outbound-party-id", "assignment", "identity", "not_applicable", "preserved"),
        ("parameter-client-id", "method-return", "return_flow", "identity", "not_applicable", "preserved"),
        ("parameter-client-id", "outbound-party-id", "argument_binding", "identity", "not_applicable", "preserved"),
    ]

    # No eager transitive edge is fabricated from inbound-customer-id to outbound-party-id.
    assert con.execute(
        """SELECT count(*) FROM repository_value_flow_edge
           WHERE source_occurrence_id='inbound-customer-id'
             AND target_occurrence_id='outbound-party-id'"""
    ).fetchone()[0] == 0
    con.close()

    query = KnowledgeLayerQuery(db)
    assert query.repository_value_nodes(node_kind="constant")["total_count"] == 1
    assert query.repository_value_flow_edges(flow_kind="argument_binding")["total_count"] == 3
    assert "workspace.repository-value-flow" in query.capabilities()
    assert "workspace.attribute-path-resolver" in query.capabilities()


def test_direct_value_graph_ignores_test_sources_and_orphan_edges(tmp_path) -> None:
    db = tmp_path / "knowledge-layer.duckdb"
    con = duckdb.connect(str(db))
    con.execute(VALUE_FLOW_KNOWLEDGE_DDL)
    con.execute(INTERACTION_KNOWLEDGE_DDL)
    _record(
        con,
        record_id="prod",
        artifact="catalog/field_occurrences.json",
        ordinal=1,
        payload={
            "occurrence_id": "prod",
            "occurrence_kind": "local_variable",
            "symbol": "value",
            "relative_file": "src/main/java/App.java",
        },
    )
    _record(
        con,
        record_id="test",
        artifact="catalog/field_occurrences.json",
        ordinal=2,
        payload={
            "occurrence_id": "test",
            "occurrence_kind": "local_variable",
            "symbol": "testValue",
            "relative_file": "src/test/java/AppTest.java",
        },
    )
    _record(
        con,
        record_id="orphan-edge",
        artifact="catalog/field_flow_edges.json",
        ordinal=3,
        payload={
            "edge_id": "orphan-edge",
            "source_occurrence_id": "prod",
            "target_occurrence_id": "missing",
            "edge_kind": "assignment",
            "relative_file": "src/main/java/App.java",
        },
    )
    assert materialize_repository_value_flow(con, scope_id="scope") == {
        "repository_value_node": 1,
        "repository_value_flow_edge": 0,
    }


def test_classifies_renames_transformations_and_groups_multi_source_derivations(tmp_path) -> None:
    db = tmp_path / "knowledge-layer.duckdb"
    con = duckdb.connect(str(db))
    con.execute(VALUE_FLOW_KNOWLEDGE_DDL)
    con.execute(INTERACTION_KNOWLEDGE_DDL)

    occurrences = [
        {
            "occurrence_id": "surname",
            "occurrence_kind": "local_field",
            "field_path": "name.surname",
            "property_name": "surname",
            "relative_file": "src/main/java/Mapper.java",
        },
        {
            "occurrence_id": "family-name",
            "occurrence_kind": "setter_target",
            "field_path": "target.familyName",
            "setter_field_tail": "familyName",
            "relative_file": "src/main/java/Mapper.java",
        },
        {
            "occurrence_id": "birth-date",
            "occurrence_kind": "local_field",
            "field_path": "birthDate.value",
            "property_name": "value",
            "relative_file": "src/main/java/Mapper.java",
        },
        {
            "occurrence_id": "formatted-date",
            "occurrence_kind": "method_invocation",
            "field_path": "dateFormat.format()",
            "expression_text": "dateFormat.format(birthDate.getValue())",
            "relative_file": "src/main/java/Mapper.java",
        },
        {
            "occurrence_id": "birth-date-target",
            "occurrence_kind": "setter_target",
            "field_path": "target.birthDate",
            "setter_field_tail": "birthDate",
            "relative_file": "src/main/java/Mapper.java",
        },
        {
            "occurrence_id": "phone",
            "occurrence_kind": "local_field",
            "field_path": "request.phoneNumber",
            "property_name": "phoneNumber",
            "relative_file": "src/main/java/Mapper.java",
        },
        {
            "occurrence_id": "normalized-phone",
            "occurrence_kind": "method_invocation",
            "field_path": "request.phoneNumber.trim()",
            "expression_text": "request.getPhoneNumber().trim()",
            "relative_file": "src/main/java/Mapper.java",
        },
        {
            "occurrence_id": "phone-target",
            "occurrence_kind": "builder_target",
            "field_path": "builder.phone",
            "builder_field_tail": "phone",
            "relative_file": "src/main/java/Mapper.java",
        },
        {
            "occurrence_id": "raw-id",
            "occurrence_kind": "local_field",
            "field_path": "request.customerId",
            "property_name": "customerId",
            "relative_file": "src/main/java/Mapper.java",
        },
        {
            "occurrence_id": "hashed-id",
            "occurrence_kind": "method_invocation",
            "field_path": "DigestUtils.sha256Hex()",
            "expression_text": "DigestUtils.sha256Hex(request.getCustomerId())",
            "relative_file": "src/main/java/Mapper.java",
        },
        {
            "occurrence_id": "hash-target",
            "occurrence_kind": "setter_target",
            "field_path": "target.customerHash",
            "setter_field_tail": "customerHash",
            "relative_file": "src/main/java/Mapper.java",
        },
        {
            "occurrence_id": "first-name",
            "occurrence_kind": "local_field",
            "field_path": "request.firstName",
            "property_name": "firstName",
            "relative_file": "src/main/java/Mapper.java",
        },
        {
            "occurrence_id": "last-name",
            "occurrence_kind": "local_field",
            "field_path": "request.lastName",
            "property_name": "lastName",
            "relative_file": "src/main/java/Mapper.java",
        },
        {
            "occurrence_id": "full-name-expression",
            "occurrence_kind": "expression",
            "expression_text": 'request.getFirstName() + " " + request.getLastName()',
            "relative_file": "src/main/java/Mapper.java",
        },
        {
            "occurrence_id": "full-name-target",
            "occurrence_kind": "builder_target",
            "field_path": "builder.fullName",
            "builder_field_tail": "fullName",
            "relative_file": "src/main/java/Mapper.java",
        },
        {
            "occurrence_id": "usage-type",
            "occurrence_kind": "local_field",
            "field_path": "phone.usageType",
            "property_name": "usageType",
            "relative_file": "src/main/java/Mapper.java",
        },
        {
            "occurrence_id": "code-expression",
            "occurrence_kind": "method_invocation",
            "field_path": "toCode()",
            "expression_text": "toCode(phone.getUsageType())",
            "relative_file": "src/main/java/Mapper.java",
        },
        {
            "occurrence_id": "code-target",
            "occurrence_kind": "setter_target",
            "field_path": "target.phoneTypeCode",
            "setter_field_tail": "phoneTypeCode",
            "relative_file": "src/main/java/Mapper.java",
        },
    ]
    for ordinal, payload in enumerate(occurrences, 1):
        _record(
            con,
            record_id=f"occ-{payload['occurrence_id']}",
            artifact="catalog/field_occurrences.json",
            ordinal=ordinal,
            payload=payload,
        )

    edges = [
        ("rename", "surname", "family-name", "setter_argument"),
        ("date-input", "birth-date", "formatted-date", "invocation_argument"),
        ("date-output", "formatted-date", "birth-date-target", "setter_argument"),
        ("phone-input", "phone", "normalized-phone", "invocation_receiver"),
        ("phone-output", "normalized-phone", "phone-target", "builder_argument"),
        ("hash-input", "raw-id", "hashed-id", "invocation_argument"),
        ("hash-output", "hashed-id", "hash-target", "setter_argument"),
        ("first-component", "first-name", "full-name-expression", "expression_component"),
        ("last-component", "last-name", "full-name-expression", "expression_component"),
        ("full-name-output", "full-name-expression", "full-name-target", "builder_argument"),
        ("code-input", "usage-type", "code-expression", "invocation_argument"),
        ("code-output", "code-expression", "code-target", "setter_argument"),
    ]
    for ordinal, (edge_id, source, target, edge_kind) in enumerate(edges, 100):
        _record(
            con,
            record_id=f"record-{edge_id}",
            artifact="catalog/field_flow_edges.json",
            ordinal=ordinal,
            payload={
                "edge_id": edge_id,
                "source_occurrence_id": source,
                "target_occurrence_id": target,
                "edge_kind": edge_kind,
                "relative_file": "src/main/java/Mapper.java",
            },
        )

    result = materialize_repository_value_flow(con, scope_id="scope")
    assert result == {"repository_value_node": len(occurrences), "repository_value_flow_edge": len(edges)}

    rename = con.execute(
        """SELECT transformation_kind, naming_relation, value_preservation
           FROM repository_value_flow_edge WHERE source_occurrence_id='surname'"""
    ).fetchone()
    assert rename == ("identity", "renamed", "preserved")

    classified = dict(
        con.execute(
            """SELECT source_occurrence_id,
                      (transformation_kind, value_preservation)
               FROM repository_value_flow_edge
               WHERE source_occurrence_id IN (
                   'formatted-date', 'normalized-phone', 'hashed-id',
                   'full-name-expression', 'code-expression'
               )"""
        ).fetchall()
    )
    assert classified == {
        "formatted-date": ("formatted", "partially_preserved"),
        "normalized-phone": ("normalized", "partially_preserved"),
        "hashed-id": ("hashed", "transformed"),
        "full-name-expression": ("combined", "partially_preserved"),
        "code-expression": ("derived", "transformed"),
    }

    derivation_rows = con.execute(
        """SELECT source_occurrence_id, target_occurrence_id, transformation_kind,
                  derivation_id, derivation_kind, derivation_source_count
           FROM repository_value_flow_edge
           WHERE source_occurrence_id IN ('first-name', 'last-name', 'full-name-expression')
           ORDER BY source_occurrence_id"""
    ).fetchall()
    assert len({row[3] for row in derivation_rows}) == 1
    assert {row[4] for row in derivation_rows} == {"combined"}
    assert {row[5] for row in derivation_rows} == {2}
    assert {row[2] for row in derivation_rows} == {"combined"}

    derivation_node = con.execute(
        """SELECT node_kind FROM repository_value_node
           WHERE occurrence_id='full-name-expression'"""
    ).fetchone()
    assert derivation_node == ("derivation",)
    con.close()

    query = KnowledgeLayerQuery(db)
    assert query.repository_value_flow_edges(derivation_kind="combined")["total_count"] == 3
    assert query.repository_value_flow_edges(transformation_kind="hashed")["total_count"] == 2


def test_static_constant_to_field_is_not_reported_as_attribute_rename(tmp_path) -> None:
    db = tmp_path / "knowledge-layer.duckdb"
    con = duckdb.connect(str(db))
    con.execute(VALUE_FLOW_KNOWLEDGE_DDL)
    con.execute(INTERACTION_KNOWLEDGE_DDL)
    _record(
        con,
        record_id="constant",
        artifact="catalog/field_occurrences.json",
        ordinal=1,
        payload={
            "occurrence_id": "boolean-true",
            "occurrence_kind": "local_field",
            "field_path": "Boolean.TRUE",
            "relative_file": "src/main/java/Mapper.java",
        },
    )
    _record(
        con,
        record_id="target",
        artifact="catalog/field_occurrences.json",
        ordinal=2,
        payload={
            "occurrence_id": "standard-flag",
            "occurrence_kind": "setter_target",
            "field_path": "target.standardFlag",
            "setter_field_tail": "standardFlag",
            "relative_file": "src/main/java/Mapper.java",
        },
    )
    _record(
        con,
        record_id="edge",
        artifact="catalog/field_flow_edges.json",
        ordinal=3,
        payload={
            "edge_id": "constant-to-field",
            "source_occurrence_id": "boolean-true",
            "target_occurrence_id": "standard-flag",
            "edge_kind": "setter_argument",
            "relative_file": "src/main/java/Mapper.java",
        },
    )
    materialize_repository_value_flow(con, scope_id="scope")
    assert con.execute(
        """SELECT n.node_kind, e.naming_relation, e.transformation_kind, e.value_preservation
           FROM repository_value_flow_edge e
           JOIN repository_value_node n ON n.value_node_id=e.source_value_node_id"""
    ).fetchone() == ("constant", "not_applicable", "identity", "preserved")


def test_materializes_http_wire_nodes_and_local_serialization_edges(tmp_path) -> None:
    db = tmp_path / "knowledge-layer.duckdb"
    con = duckdb.connect(str(db))
    con.execute(VALUE_FLOW_KNOWLEDGE_DDL)
    con.execute(INTERACTION_KNOWLEDGE_DDL)

    occurrences = [
        {
            "occurrence_id": "out-request-local",
            "operation": "TargetClient.update",
            "occurrence_kind": "boundary_field",
            "field_path": "request.customer_id",
            "wire_field_path": "customerId",
            "boundary_direction": "outbound",
            "payload_role": "request",
            "relative_file": "src/main/java/TargetClient.java",
        },
        {
            "occurrence_id": "in-request-local",
            "operation": "TargetController.update",
            "occurrence_kind": "boundary_field",
            "field_path": "request.partyId",
            "wire_field_path": "customerId",
            "boundary_direction": "inbound",
            "payload_role": "request",
            "relative_file": "src/main/java/TargetController.java",
        },
        {
            "occurrence_id": "in-response-local",
            "operation": "TargetController.update",
            "occurrence_kind": "boundary_field",
            "field_path": "response.profileId",
            "wire_field_path": "profile.id",
            "boundary_direction": "inbound",
            "payload_role": "response",
            "relative_file": "src/main/java/TargetController.java",
        },
        {
            "occurrence_id": "out-response-local",
            "operation": "TargetClient.update",
            "occurrence_kind": "boundary_field",
            "field_path": "response.remoteProfileId",
            "wire_field_path": "profile.id",
            "boundary_direction": "outbound",
            "payload_role": "response",
            "relative_file": "src/main/java/TargetClient.java",
        },
    ]
    for ordinal, payload in enumerate(occurrences, 1):
        _record(
            con,
            record_id=f"occ-{payload['occurrence_id']}",
            artifact="catalog/field_occurrences.json",
            ordinal=ordinal,
            payload=payload,
        )

    interfaces = [
        {
            "interface_id": "out-http",
            "direction": "outbound",
            "protocol": "http",
            "operation": "TargetClient.update",
            "http_method": "POST",
            "endpoint_or_topic_resolved": "/profiles",
            "request_payload_type": "UpdateRequest",
            "request_contract_signature": [
                {
                    "attribute_path": "customerId",
                    "wire_name": "customerId",
                    "attribute_name": "customerId",
                    "attribute_type": "String",
                }
            ],
            "response_payload_type": "UpdateResponse",
            "response_contract_signature": [
                {
                    "attribute_path": "profile.id",
                    "wire_name": "id",
                    "attribute_name": "profileId",
                    "attribute_type": "String",
                }
            ],
        },
        {
            "interface_id": "in-http",
            "direction": "inbound",
            "protocol": "rest",
            "operation": "TargetController.update",
            "http_method": "POST",
            "endpoint_or_topic_resolved": "/profiles",
            "request_payload_type": "UpdateRequest",
            "request_contract_signature": [
                {
                    "attribute_path": "customerId",
                    "wire_name": "customerId",
                    "attribute_name": "partyId",
                    "attribute_type": "String",
                }
            ],
            "response_payload_type": "UpdateResponse",
            "response_contract_signature": [
                {
                    "attribute_path": "profile.id",
                    "wire_name": "id",
                    "attribute_name": "profileId",
                    "attribute_type": "String",
                }
            ],
        },
    ]
    for ordinal, payload in enumerate(interfaces, 100):
        _record(
            con,
            record_id=f"if-{payload['interface_id']}",
            artifact="system_interface_catalog.json",
            ordinal=ordinal,
            payload=payload,
        )

    result = materialize_repository_value_flow(con, scope_id="scope")
    assert result == {"repository_value_node": 8, "repository_value_flow_edge": 4}

    wire_nodes = con.execute(
        """SELECT owner_ref, operation, wire_path
           FROM repository_value_node
           WHERE node_kind='wire_field'
           ORDER BY owner_ref, wire_path"""
    ).fetchall()
    assert wire_nodes == [
        ("in-http", "TargetController.update", "customerid"),
        ("in-http", "TargetController.update", "profile.id"),
        ("out-http", "TargetClient.update", "customerid"),
        ("out-http", "TargetClient.update", "profile.id"),
    ]

    edges = con.execute(
        """SELECT source_occurrence_id, target_occurrence_id, flow_kind,
                  source_edge_kind, naming_relation, confidence
           FROM repository_value_flow_edge
           ORDER BY flow_kind, source_occurrence_id, target_occurrence_id"""
    ).fetchall()
    assert len(edges) == 4
    assert sum(1 for row in edges if row[2] == "serialization") == 2
    assert sum(1 for row in edges if row[2] == "deserialization") == 2
    assert all(row[5] == "confirmed" for row in edges)

    serializations = con.execute(
        """SELECT source_occurrence_id, target_occurrence_id, source_edge_kind
           FROM repository_value_flow_edge
           WHERE flow_kind='serialization'
           ORDER BY source_edge_kind"""
    ).fetchall()
    assert serializations[0][0] == "out-request-local"
    assert serializations[0][2] == "http_request_serialization"
    assert serializations[1][0] == "in-response-local"
    assert serializations[1][2] == "http_response_serialization"

    deserializations = con.execute(
        """SELECT source_occurrence_id, target_occurrence_id, source_edge_kind
           FROM repository_value_flow_edge
           WHERE flow_kind='deserialization'
           ORDER BY source_edge_kind"""
    ).fetchall()
    assert deserializations[0][1] == "in-request-local"
    assert deserializations[0][2] == "http_request_deserialization"
    assert deserializations[1][1] == "out-response-local"
    assert deserializations[1][2] == "http_response_deserialization"

    con.close()


def test_keeps_wire_node_but_skips_ambiguous_local_binding(tmp_path) -> None:
    db = tmp_path / "knowledge-layer.duckdb"
    con = duckdb.connect(str(db))
    con.execute(VALUE_FLOW_KNOWLEDGE_DDL)
    con.execute(INTERACTION_KNOWLEDGE_DDL)

    for ordinal, occurrence_id in enumerate(("first", "second"), 1):
        _record(
            con,
            record_id=f"occ-{occurrence_id}",
            artifact="catalog/field_occurrences.json",
            ordinal=ordinal,
            payload={
                "occurrence_id": occurrence_id,
                "operation": "Client.send",
                "occurrence_kind": "boundary_field",
                "field_path": "request.customerId",
                "boundary_direction": "outbound",
                "payload_role": "request",
                "relative_file": f"src/main/java/{occurrence_id}.java",
            },
        )
    _record(
        con,
        record_id="if-out",
        artifact="system_interface_catalog.json",
        ordinal=100,
        payload={
            "interface_id": "out-http",
            "direction": "outbound",
            "protocol": "http",
            "operation": "Client.send",
            "request_contract_signature": [{"attribute_path": "customerId"}],
        },
    )

    result = materialize_repository_value_flow(con, scope_id="scope")
    assert result == {"repository_value_node": 3, "repository_value_flow_edge": 0}
    assert con.execute(
        "SELECT count(*) FROM repository_value_node WHERE node_kind='wire_field'"
    ).fetchone()[0] == 1
    con.close()


def _insert_boundary_interaction(
    con,
    *,
    boundary_id: str,
    confidence: str,
    outbound_interface: dict,
    target_interface: dict,
) -> None:
    con.execute(
        """INSERT INTO system_boundary_interaction VALUES (
               ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
           )""",
        [
            boundary_id,
            f"interaction-{boundary_id}",
            "scope",
            "source",
            outbound_interface["interface_id"],
            outbound_interface["operation"],
            "POST",
            "/profiles",
            "target",
            target_interface["interface_id"],
            target_interface["operation"],
            "/profiles",
            "http",
            "matched",
            confidence,
            "unresolved",
            json.dumps({"match_basis": "fixture"}),
            json.dumps({"fixture": True}),
            json.dumps(
                {
                    "outbound_interface": outbound_interface,
                    "target_ingress_interface": target_interface,
                    "match_status": "matched",
                    "confidence": confidence,
                    "local_execution_status": "unresolved",
                    "match_basis": {
                        "http_method": "POST",
                        "path_basis": "exact_path",
                        "outbound_authorities": ["localhost:8093"],
                        "target_authorities": [],
                        "authority_overlap": [],
                        "service_identity_overlap": [],
                        "property_identity_overlap": ["profile-service"],
                        "candidate_lookup": {"indexed_candidate_count": 1},
                        "contract": {
                            "request_field_overlap_count": 1,
                            "request_field_similarity": 1.0,
                            "request_payload_type_match": True,
                        },
                    },
                }
            ),
        ],
    )


def test_confirmed_http_boundary_materializes_request_and_reverse_response_transport_edges(tmp_path) -> None:
    db = tmp_path / "knowledge-layer.duckdb"
    con = duckdb.connect(str(db))
    con.execute(VALUE_FLOW_KNOWLEDGE_DDL)
    con.execute(INTERACTION_KNOWLEDGE_DDL)

    outbound_interface = {
        "interface_id": "source-out",
        "direction": "outbound",
        "protocol": "http",
        "operation": "RemoteClient.update",
        "request_payload_type": "UpdateRequest",
        "request_contract_signature": [
            {"attribute_path": "customerId", "attribute_type": "String"}
        ],
        "response_payload_type": "UpdateResponse",
        "response_contract_signature": [
            {"attribute_path": "profile.id", "attribute_type": "String"}
        ],
    }
    target_interface = {
        "interface_id": "target-in",
        "direction": "inbound",
        "protocol": "http",
        "operation": "ProfileController.update",
        "request_payload_type": "UpdateRequest",
        "request_contract_signature": [
            {"attribute_path": "customerId", "attribute_type": "String"}
        ],
        "response_payload_type": "UpdateResponse",
        "response_contract_signature": [
            {"attribute_path": "profile.id", "attribute_type": "String"}
        ],
    }
    _record(
        con,
        record_id="source-interface",
        artifact="system_interface_catalog.json",
        ordinal=1,
        payload=outbound_interface,
        repo_id="source",
    )
    _record(
        con,
        record_id="target-interface",
        artifact="system_interface_catalog.json",
        ordinal=2,
        payload=target_interface,
        repo_id="target",
    )
    _insert_boundary_interaction(
        con,
        boundary_id="boundary-confirmed",
        confidence="confirmed",
        outbound_interface=outbound_interface,
        target_interface=target_interface,
    )

    result = materialize_repository_value_flow(con, scope_id="scope")
    assert result == {"repository_value_node": 4, "repository_value_flow_edge": 2}
    assert con.execute("SELECT count(*) FROM system_interaction_execution_context").fetchone()[0] == 0

    transports = con.execute(
        """SELECT source_repo_id, target_repo_id, flow_kind, source_edge_kind,
                  source_occurrence_id, target_occurrence_id, confidence
           FROM repository_value_flow_edge
           ORDER BY source_edge_kind"""
    ).fetchall()
    assert len(transports) == 2
    request = next(item for item in transports if item[3] == "http_request_transport")
    response = next(item for item in transports if item[3] == "http_response_transport")
    assert request[:4] == ("source", "target", "transport", "http_request_transport")
    assert response[:4] == ("target", "source", "transport", "http_response_transport")
    assert all(item[6] == "confirmed" for item in transports)
    con.close()

    query = KnowledgeLayerQuery(db)
    assert query.repository_value_flow_edges(flow_kind="transport")["total_count"] == 2
    assert query.repository_value_flow_edges(source_repo_id="source")["total_count"] == 1
    assert query.repository_value_flow_edges(target_repo_id="source")["total_count"] == 1
    assert query.repository_value_flow_edges(repo_id="source")["total_count"] == 2
    strict = query.repository_value_flow_edges(flow_kind="transport", knowledge_view="strict")
    assert strict["total_count"] == 2
    assert {row["knowledge_class"] for row in strict["items"]} == {"confirmed"}


def test_probable_http_boundary_materializes_candidate_transport_edge_with_evidence(tmp_path) -> None:
    db = tmp_path / "knowledge-layer.duckdb"
    con = duckdb.connect(str(db))
    con.execute(VALUE_FLOW_KNOWLEDGE_DDL)
    con.execute(INTERACTION_KNOWLEDGE_DDL)
    outbound_interface = {
        "interface_id": "source-out",
        "direction": "outbound",
        "protocol": "http",
        "operation": "RemoteClient.update",
        "request_contract_signature": [{"attribute_path": "customerId"}],
    }
    target_interface = {
        "interface_id": "target-in",
        "direction": "inbound",
        "protocol": "http",
        "operation": "ProfileController.update",
        "request_contract_signature": [{"attribute_path": "customerId"}],
    }
    _record(
        con,
        record_id="source-interface",
        artifact="system_interface_catalog.json",
        ordinal=1,
        payload=outbound_interface,
        repo_id="source",
    )
    _record(
        con,
        record_id="target-interface",
        artifact="system_interface_catalog.json",
        ordinal=2,
        payload=target_interface,
        repo_id="target",
    )
    _insert_boundary_interaction(
        con,
        boundary_id="boundary-probable",
        confidence="probable",
        outbound_interface=outbound_interface,
        target_interface=target_interface,
    )
    result = materialize_repository_value_flow(con, scope_id="scope")
    assert result == {"repository_value_node": 2, "repository_value_flow_edge": 1}
    confidence, provenance_raw, payload_raw = con.execute(
        "SELECT confidence, provenance_json, payload_json FROM repository_value_flow_edge"
    ).fetchone()
    assert confidence == "probable"
    provenance = json.loads(provenance_raw)
    packet = provenance["evidence_packet"]
    assert packet["edge_status"] == "candidate"
    assert "property_identity_exact" in packet["supporting_evidence"]
    assert "environment_authority_non_binding" in packet["limitations"]
    assert packet["conflicting_evidence"] == []
    payload = json.loads(payload_raw)
    assert payload["transport"]["edge_status"] == "candidate"
    con.close()

    query = KnowledgeLayerQuery(db)
    assert query.repository_value_flow_edges(flow_kind="transport", knowledge_view="strict")["total_count"] == 0
    working = query.repository_value_flow_edges(flow_kind="transport", knowledge_view="working")
    assert working["total_count"] == 1
    assert working["items"][0]["knowledge_class"] == "derived"
    assert query.repository_value_flow_edges(knowledge_class="derived")["total_count"] == 1


def test_probable_boundary_with_explicit_real_authority_conflict_creates_no_transport(tmp_path) -> None:
    db = tmp_path / "knowledge-layer.duckdb"
    con = duckdb.connect(str(db))
    con.execute(VALUE_FLOW_KNOWLEDGE_DDL)
    con.execute(INTERACTION_KNOWLEDGE_DDL)
    outbound_interface = {
        "interface_id": "source-out",
        "direction": "outbound",
        "protocol": "http",
        "operation": "RemoteClient.update",
        "request_contract_signature": [{"attribute_path": "customerId"}],
    }
    target_interface = {
        "interface_id": "target-in",
        "direction": "inbound",
        "protocol": "http",
        "operation": "ProfileController.update",
        "request_contract_signature": [{"attribute_path": "customerId"}],
    }
    _record(con, record_id="source-interface", artifact="system_interface_catalog.json", ordinal=1, payload=outbound_interface, repo_id="source")
    _record(con, record_id="target-interface", artifact="system_interface_catalog.json", ordinal=2, payload=target_interface, repo_id="target")
    _insert_boundary_interaction(con, boundary_id="boundary-conflict", confidence="probable", outbound_interface=outbound_interface, target_interface=target_interface)
    raw = con.execute("SELECT payload_json FROM system_boundary_interaction").fetchone()[0]
    payload = json.loads(raw)
    payload["match_basis"]["outbound_authorities"] = ["source.prod.example:443"]
    payload["match_basis"]["target_authorities"] = ["target.prod.example:443"]
    payload["match_basis"]["authority_overlap"] = []
    con.execute("UPDATE system_boundary_interaction SET payload_json=json(?)", [json.dumps(payload)])
    result = materialize_repository_value_flow(con, scope_id="scope")
    assert result == {"repository_value_node": 2, "repository_value_flow_edge": 0}
    con.close()
