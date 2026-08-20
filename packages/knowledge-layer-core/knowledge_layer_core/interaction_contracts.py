from __future__ import annotations

import json
import re
from collections import defaultdict, deque
from typing import Any, Mapping

from .bulk import bulk_insert
from .metrics import canonical_json
from prepared_knowledge_runtime.normalization import stable_id


FIELD_CONTRACT_SCHEMA_VERSION = "workspace_system_interaction_field_contract/v2"

_BOUNDARY_OCCURRENCE_KINDS = {
    "boundary_field",
    "payload_field",
    "boundary_request_field",
    "boundary_response_field",
}


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return dict(parsed) if isinstance(parsed, Mapping) else {}
    return {}


def _is_production(payload: Mapping[str, Any]) -> bool:
    relative = str(payload.get("relative_file") or payload.get("file") or "").replace("\\", "/")
    lowered = f"/{relative.casefold().lstrip('/')}"
    return "/src/test/" not in lowered and "/test/" not in lowered


def _simple_type_name(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = re.sub(r"<.*>", "", text).strip()
    return text.rsplit(".", 1)[-1]


def _load_records(
    connection: Any,
    artifact_name: str,
    *,
    evidence_relation: str = "value_flow_evidence_record",
) -> list[tuple[str, str, dict[str, Any]]]:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)?", evidence_relation):
        raise ValueError(f"invalid typed evidence relation: {evidence_relation!r}")
    rows = connection.execute(
        f"""SELECT record_occurrence_id, repo_id, payload_json
           FROM {evidence_relation}
           WHERE artifact_name=?
           ORDER BY repo_id, occurrence_ordinal, record_occurrence_id""",
        [artifact_name],
    ).fetchall()
    return [(str(record_id), str(repo_id), _mapping(payload)) for record_id, repo_id, payload in rows]


def normalize_wire_path(value: object) -> str:
    """Return the comparison form of an observed serialized request path.

    The normalization is deliberately narrow: array-member markers are removed,
    separators are canonicalized to dots, and comparison is case-insensitive.
    No token similarity, pluralization, alias guessing, or leaf-name matching is
    performed.
    """

    text = str(value or "").strip()
    if not text:
        return ""
    text = re.sub(r"\[\s*\]", "", text)
    text = re.sub(r"[\\/]+", ".", text)
    text = re.sub(r"\.+", ".", text).strip(".")
    return text.casefold()


def _contract_items(interface: Mapping[str, Any]) -> list[dict[str, Any]]:
    signature = interface.get("request_contract_signature")
    if not isinstance(signature, list):
        return []
    items: list[dict[str, Any]] = []
    for raw in signature:
        item = _mapping(raw)
        path = str(item.get("attribute_path") or item.get("wire_field_path") or "").strip()
        normalized = normalize_wire_path(path)
        if not path or not normalized:
            continue
        items.append(
            {
                "path": path,
                "normalized_path": normalized,
                "attribute_name": str(item.get("attribute_name") or "").strip() or None,
                "wire_name": str(item.get("wire_name") or item.get("wire_field_name") or "").strip() or None,
                "attribute_type": str(item.get("attribute_type") or item.get("data_type") or "").strip() or None,
                "source_schema": str(item.get("source_schema") or "").strip() or None,
                "serialization_aliases": list(item.get("serialization_aliases") or []),
                "serialization_library": str(item.get("serialization_library") or "").strip() or None,
                "serialized_name_basis": str(item.get("serialized_name_basis") or "").strip() or None,
                "evidence_refs": list(item.get("evidence_refs") or []),
                "raw": item,
            }
        )
    return items


def _unique_by_normalized(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        grouped[str(item["normalized_path"])].append(item)
    return {key: values[0] for key, values in grouped.items() if len(values) == 1}


def _type_compatibility(source_type: str | None, target_type: str | None) -> str:
    if not source_type or not target_type:
        return "unknown"
    if source_type.casefold() == target_type.casefold():
        return "exact"
    return "different_declared_types"



def _ast_span(payload: Mapping[str, Any]) -> tuple[int, int] | None:
    node = payload.get("ast_node")
    if not isinstance(node, Mapping):
        return None
    start = node.get("start_byte")
    end = node.get("end_byte")
    if isinstance(start, int) and isinstance(end, int) and 0 <= start <= end:
        return start, end
    return None

def _shortest_path(
    adjacency: Mapping[str, tuple[tuple[str, str], ...]],
    source_id: str,
    target_id: str,
    *,
    max_depth: int = 64,
) -> tuple[list[str], list[str]] | None:
    queue = deque([source_id])
    depth = {source_id: 0}
    predecessor: dict[str, tuple[str, str]] = {}
    while queue:
        current = queue.popleft()
        if current == target_id:
            nodes = [current]
            edges: list[str] = []
            while current != source_id:
                parent, edge_id = predecessor[current]
                nodes.append(parent)
                edges.append(edge_id)
                current = parent
            return list(reversed(nodes)), list(reversed(edges))
        if depth[current] >= max_depth:
            continue
        for next_id, edge_id in adjacency.get(current, ()):
            if next_id in depth:
                continue
            depth[next_id] = depth[current] + 1
            predecessor[next_id] = (current, edge_id)
            queue.append(next_id)
    return None


def _builder_target_owner(
    payload: Mapping[str, Any],
    *,
    local_builder_types: Mapping[str, str],
) -> tuple[str, str] | None:
    path = str(payload.get("field_path") or "").strip()
    direct = re.match(r"^([A-Z][A-Za-z0-9_$]*)\.builder\.([A-Za-z_$][A-Za-z0-9_$]*)$", path)
    if direct:
        return direct.group(1), direct.group(2)
    variable = re.match(r"^([A-Za-z_$][A-Za-z0-9_$]*)\.([A-Za-z_$][A-Za-z0-9_$]*)$", path)
    if not variable:
        return None
    owner_type = local_builder_types.get(variable.group(1), "")
    return (owner_type, variable.group(2)) if owner_type else None


def _payload_nested_path(payload_type: str, payload: Mapping[str, Any]) -> str:
    field_path = str(payload.get("field_path") or "").strip()
    prefixes = (
        f"{payload_type}.builder.build().",
        f"{payload_type}.builder.",
    )
    for prefix in prefixes:
        if field_path.startswith(prefix):
            return field_path[len(prefix):].strip(".")
    return ""


def _inferred_method_references(
    occurrences_by_operation: Mapping[str, list[tuple[str, dict[str, Any]]]],
) -> list[tuple[str, dict[str, Any]]]:
    """Recover exact ``stream().map(Type::method)`` bindings from core occurrences.

    Some flow profiles publish the method-reference syntax only inside a local
    variable initializer. This fallback is deliberately strict: same-class helper,
    one matching helper operation, one parameter and one declared return type.
    """

    result: list[tuple[str, dict[str, Any]]] = []
    operation_names = set(occurrences_by_operation)
    for owner_operation, records in occurrences_by_operation.items():
        owner_type = owner_operation.rsplit(".", 1)[0] if "." in owner_operation else ""
        if not owner_type:
            continue
        for record_id, payload in records:
            if str(payload.get("occurrence_kind") or "") != "local_variable":
                continue
            expression = str(payload.get("expression_text") or "")
            matches = re.findall(
                r"(?:this|[A-Za-z_$][A-Za-z0-9_$]*)::([A-Za-z_$][A-Za-z0-9_$]*)",
                expression,
            )
            if len(set(matches)) != 1:
                continue
            method_name = matches[0]
            helper_operation = f"{owner_type}.{method_name}"
            if helper_operation not in operation_names:
                continue
            helper_records = occurrences_by_operation[helper_operation]
            parameters = [
                item
                for _rid, item in helper_records
                if str(item.get("occurrence_kind") or "") in {"method_parameter", "parameter"}
            ]
            returns = [
                item
                for _rid, item in helper_records
                if str(item.get("occurrence_kind") or "") == "method_return"
                and _simple_type_name(item.get("declared_type"))
            ]
            if len(parameters) != 1 or len(returns) != 1:
                continue
            member_type = _simple_type_name(returns[0].get("declared_type"))
            parameter_name = str(parameters[0].get("symbol") or "parameter").strip()
            parameter_type = _simple_type_name(parameters[0].get("declared_type")) or None
            result.append(
                (
                    record_id,
                    {
                        "method_reference_id": stable_id(
                            "inferred_method_reference", owner_operation, helper_operation, expression
                        ),
                        "owner_operation": owner_operation,
                        "reference_text": f"this::{method_name}",
                        "resolution": "exact_same_class_method_reference_from_initializer",
                        "resolved_operation": helper_operation,
                        "resolved_method_signature": helper_operation,
                        "resolved_return_type": member_type,
                        "functional_parameter_bindings": [
                            {
                                "functional_parameter_position": 0,
                                "callee_parameter": parameter_name,
                                "callee_parameter_type": parameter_type,
                                "binding_kind": "collection_member_to_method_parameter",
                                "binding_basis": (
                                    "tree_sitter_method_reference_initializer_and_unique_same_class_helper"
                                ),
                            }
                        ],
                        "relative_file": payload.get("relative_file") or payload.get("file"),
                        "inference_basis": "local_variable_stream_map_method_reference",
                    },
                )
            )
    return result


def _direct_nested_contract_candidates(
    *,
    outbound_operation: str,
    target_items: Mapping[str, dict[str, Any]],
    occurrences_by_operation: Mapping[str, list[tuple[str, dict[str, Any]]]],
) -> list[dict[str, Any]]:
    """Publish nested paths already observed at the outbound boundary.

    This covers intermediate nested objects where the compact interface catalog is
    shallow but core has an exact operation-scoped boundary occurrence.
    """

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record_id, payload in occurrences_by_operation.get(outbound_operation, ()):
        if str(payload.get("occurrence_kind") or "") not in _BOUNDARY_OCCURRENCE_KINDS:
            continue
        occurrence_id = str(payload.get("occurrence_id") or "").strip()
        path = str(
            payload.get("wire_field_path")
            or payload.get("field_path")
            or payload.get("attribute_path")
            or ""
        ).strip()
        normalized = normalize_wire_path(path)
        if not occurrence_id or not normalized or normalized not in target_items:
            continue
        grouped[normalized].append(
            {
                "wire_path": normalized,
                "outbound_path": path,
                "outbound_attribute_name": path.rsplit(".", 1)[-1],
                "outbound_wire_name": path.rsplit(".", 1)[-1],
                "outbound_attribute_type": str(
                    payload.get("attribute_type") or payload.get("declared_type") or ""
                ).strip() or None,
                "outbound_source_schema": str(payload.get("source_schema") or "").strip() or None,
                "target": target_items[normalized],
                "source_occurrence_id": occurrence_id,
                "source_record_id": record_id,
                "source_payload": payload,
            }
        )
    result: list[dict[str, Any]] = []
    for _path, values in sorted(grouped.items()):
        # Core may publish boundary_field and payload_field views for the same fact.
        values.sort(
            key=lambda item: (
                0 if str(item["source_payload"].get("occurrence_kind")) == "boundary_field" else 1,
                item["source_occurrence_id"],
            )
        )
        semantic_keys = {
            (
                str(item["source_payload"].get("operation") or ""),
                normalize_wire_path(
                    item["source_payload"].get("wire_field_path")
                    or item["source_payload"].get("field_path")
                ),
                str(item["source_payload"].get("payload_role") or "request"),
                str(item["source_payload"].get("boundary_direction") or "outbound"),
            )
            for item in values
        }
        if len(semantic_keys) == 1:
            result.append(values[0])
    return result


def _collection_member_contract_candidates(
    *,
    repo_id: str,
    boundary_payload: Mapping[str, Any],
    outbound_operation: str,
    outbound_payload_type: str,
    target_items: Mapping[str, dict[str, Any]],
    method_references: list[tuple[str, dict[str, Any]]],
    occurrences_by_operation: Mapping[str, list[tuple[str, dict[str, Any]]]],
    occurrence_by_id: Mapping[str, dict[str, Any]],
    occurrence_record_id: Mapping[str, str],
    adjacency: Mapping[str, tuple[tuple[str, str], ...]],
    edge_record_id: Mapping[str, str],
) -> list[dict[str, Any]]:
    """Derive exact nested outbound request paths for mapped collection members."""

    call_chain = {
        str(item).strip()
        for item in boundary_payload.get("call_chain") or ()
        if str(item).strip()
    }
    if not outbound_payload_type:
        return []

    candidates: list[dict[str, Any]] = []
    for method_reference_record_id, method_reference in method_references:
        owner_operation = str(method_reference.get("owner_operation") or "").strip()
        helper_operation = str(method_reference.get("resolved_operation") or "").strip()
        member_type = _simple_type_name(method_reference.get("resolved_return_type"))
        reference_text = str(method_reference.get("reference_text") or "").strip()
        bindings = [
            dict(item)
            for item in method_reference.get("functional_parameter_bindings") or ()
            if isinstance(item, Mapping)
            and str(item.get("binding_kind") or "") == "collection_member_to_method_parameter"
        ]
        if (
            not helper_operation
            or not member_type
            or not reference_text
            or len(bindings) != 1
            or not str(method_reference.get("resolution") or "").startswith("exact_")
        ):
            continue

        owner_occurrences = occurrences_by_operation.get(owner_operation, ())
        local_results = [
            (record_id, payload)
            for record_id, payload in owner_occurrences
            if str(payload.get("occurrence_kind") or "") == "local_variable"
            and reference_text in str(payload.get("expression_text") or "")
            and str(payload.get("occurrence_id") or "").strip()
        ]
        if len(local_results) != 1:
            continue
        local_record_id, local_payload = local_results[0]
        local_occurrence_id = str(local_payload.get("occurrence_id") or "").strip()

        nested_path_matches: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for nested_record_id, nested_payload in owner_occurrences:
            if str(nested_payload.get("occurrence_kind") or "") not in {
                "builder_nested_field",
                "projected_object_field",
            }:
                continue
            nested_occurrence_id = str(nested_payload.get("occurrence_id") or "").strip()
            nested_path = _payload_nested_path(outbound_payload_type, nested_payload)
            if not nested_occurrence_id or not nested_path:
                continue
            path = _shortest_path(adjacency, local_occurrence_id, nested_occurrence_id)
            if path is None:
                continue
            normalized_nested_path = normalize_wire_path(nested_path)
            if normalized_nested_path not in target_items:
                continue
            nested_path_matches[normalized_nested_path].append(
                {
                    "path": nested_path,
                    "occurrence_id": nested_occurrence_id,
                    "record_id": nested_record_id,
                    "path_nodes": path[0],
                    "path_edges": path[1],
                }
            )
        if len(nested_path_matches) != 1:
            continue
        collection_path, matches = next(iter(nested_path_matches.items()))
        matches.sort(
            key=lambda item: (
                len(item["path_edges"]),
                0
                if str(occurrence_by_id.get(item["occurrence_id"], {}).get("occurrence_kind"))
                == "builder_nested_field"
                else 1,
                item["occurrence_id"],
            )
        )
        outer = matches[0]

        # Execution context is optional. If absent, require an observed direct flow
        # from the nested object to an outbound boundary occurrence.
        execution_context_observed = owner_operation in call_chain
        outbound_boundary_candidates = [
            str(payload.get("occurrence_id") or "").strip()
            for _record_id, payload in occurrences_by_operation.get(outbound_operation, ())
            if str(payload.get("occurrence_kind") or "") in _BOUNDARY_OCCURRENCE_KINDS
            and str(payload.get("occurrence_id") or "").strip()
            and normalize_wire_path(
                payload.get("wire_field_path")
                or payload.get("field_path")
                or payload.get("attribute_path")
            )
            == collection_path
        ]
        field_flow_to_outbound = [
            item
            for item in (
                _shortest_path(adjacency, outer["occurrence_id"], occurrence_id)
                for occurrence_id in outbound_boundary_candidates
            )
            if item is not None
        ]
        if not execution_context_observed and not field_flow_to_outbound:
            continue
        outbound_link_path = (
            sorted(field_flow_to_outbound, key=lambda item: (len(item[1]), tuple(item[1]), tuple(item[0])))[0]
            if field_flow_to_outbound
            else None
        )

        helper_occurrences = occurrences_by_operation.get(helper_operation, ())
        local_builder_types: dict[str, str] = {}
        for _record_id, payload in helper_occurrences:
            if str(payload.get("occurrence_kind") or "") != "local_variable":
                continue
            symbol = str(payload.get("symbol") or "").strip()
            declared = _simple_type_name(payload.get("declared_type"))
            if symbol and declared.endswith("Builder"):
                local_builder_types[symbol] = declared[: -len("Builder")]

        invocation_ids_by_span: dict[tuple[int, int], list[str]] = defaultdict(list)
        for _record_id, payload in helper_occurrences:
            if str(payload.get("occurrence_kind") or "") != "method_invocation":
                continue
            occurrence_id = str(payload.get("occurrence_id") or "").strip()
            span = _ast_span(payload)
            if occurrence_id and span is not None:
                invocation_ids_by_span[span].append(occurrence_id)

        builder_targets: list[dict[str, Any]] = []
        for record_id, payload in helper_occurrences:
            if str(payload.get("occurrence_kind") or "") != "builder_target":
                continue
            occurrence_id = str(payload.get("occurrence_id") or "").strip()
            owner = _builder_target_owner(payload, local_builder_types=local_builder_types)
            if not occurrence_id or owner is None:
                continue
            equivalent_invocations = tuple(
                sorted(invocation_ids_by_span.get(_ast_span(payload) or (-1, -1), ()))
            )
            builder_targets.append(
                {
                    "owner_type": owner[0],
                    "field": owner[1],
                    "occurrence_id": occurrence_id,
                    "record_id": record_id,
                    "path_origins": (occurrence_id, *equivalent_invocations),
                }
            )

        return_targets = [item for item in builder_targets if item["owner_type"] == member_type]
        if not return_targets:
            continue

        member_paths: list[dict[str, Any]] = []
        for item in builder_targets:
            if item["owner_type"] == member_type:
                member_paths.append(
                    {
                        "member_path": item["field"],
                        "source_schema": item["owner_type"],
                        "builder_occurrence_ids": [item["occurrence_id"]],
                        "builder_record_ids": [item["record_id"]],
                        "field_flow_edge_ids": [],
                    }
                )
                continue

            parent_matches: list[tuple[int, dict[str, Any], tuple[list[str], list[str]], str]] = []
            for parent in return_targets:
                for origin_id in item["path_origins"]:
                    path = _shortest_path(adjacency, origin_id, parent["occurrence_id"])
                    if path is not None:
                        parent_matches.append((len(path[1]), parent, path, origin_id))
            if not parent_matches:
                continue
            min_length = min(length for length, _parent, _path, _origin in parent_matches)
            nearest = [entry for entry in parent_matches if entry[0] == min_length]
            if len(nearest) != 1:
                continue
            _length, parent, path, path_origin_id = nearest[0]
            member_paths.append(
                {
                    "member_path": f"{parent['field']}.{item['field']}",
                    "source_schema": item["owner_type"],
                    "builder_occurrence_ids": [item["occurrence_id"], path_origin_id, parent["occurrence_id"]],
                    "builder_record_ids": [item["record_id"], parent["record_id"]],
                    "field_flow_edge_ids": path[1],
                }
            )

        normalized_member_paths = [normalize_wire_path(item["member_path"]) for item in member_paths]
        terminal_paths = [
            item
            for item, normalized in zip(member_paths, normalized_member_paths)
            if not any(
                other != normalized and other.startswith(f"{normalized}.")
                for other in normalized_member_paths
            )
        ]

        for item in terminal_paths:
            outbound_path = f"{outer['path']}.{item['member_path']}"
            normalized_outbound_path = normalize_wire_path(outbound_path)
            target = target_items.get(normalized_outbound_path)
            if target is None:
                continue
            candidates.append(
                {
                    "wire_path": normalized_outbound_path,
                    "outbound_path": outbound_path,
                    "outbound_attribute_name": item["member_path"].rsplit(".", 1)[-1],
                    "outbound_wire_name": item["member_path"].rsplit(".", 1)[-1],
                    "outbound_attribute_type": None,
                    "outbound_source_schema": item["source_schema"],
                    "target": target,
                    "method_reference_record_id": method_reference_record_id,
                    "method_reference_id": method_reference.get("method_reference_id"),
                    "owner_operation": owner_operation,
                    "helper_operation": helper_operation,
                    "helper_signature": method_reference.get("resolved_method_signature"),
                    "member_type": member_type,
                    "collection_path": outer["path"],
                    "collection_result_record_id": local_record_id,
                    "collection_result_occurrence_id": local_occurrence_id,
                    "outer_path_record_id": outer["record_id"],
                    "outer_path_occurrence_id": outer["occurrence_id"],
                    "outer_path_edge_ids": outer["path_edges"],
                    "builder_occurrence_ids": item["builder_occurrence_ids"],
                    "builder_record_ids": item["builder_record_ids"],
                    "member_field_flow_edge_ids": item["field_flow_edge_ids"],
                    "functional_parameter_binding": bindings[0],
                    "terminal_builder_occurrence_id": item["builder_occurrence_ids"][0],
                    "terminal_builder_record_id": item["builder_record_ids"][0],
                    "outbound_link_basis": (
                        "execution_context" if execution_context_observed else "direct_field_flow_to_outbound_boundary"
                    ),
                    "outbound_link_edge_ids": outbound_link_path[1] if outbound_link_path else [],
                }
            )

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for candidate in candidates:
        grouped[str(candidate["wire_path"])].append(candidate)
    unique: list[dict[str, Any]] = []
    for _wire_path, values in sorted(grouped.items()):
        deduplicated: dict[tuple[Any, ...], dict[str, Any]] = {}
        for item in values:
            key = (
                item["method_reference_id"],
                item["helper_signature"],
                item["collection_path"],
                item["outbound_path"],
                tuple(item["builder_occurrence_ids"]),
            )
            deduplicated[key] = item
        if len(deduplicated) == 1:
            unique.append(next(iter(deduplicated.values())))
    return unique

def materialize_system_interaction_field_contracts(
    connection: Any,
    *,
    scope_id: str,
    value_flow_evidence_relation: str = "value_flow_evidence_record",
) -> dict[str, int]:
    """Materialize exact and reconstructed request-wire contracts for matched edges.

    The primary contract class requires one exact normalized path on both sides.
    A second strict class may reconstruct nested collection-member paths when the
    source outbound interface is shallow but exact method-reference, builder and
    target wire-contract evidence proves the missing nested structure.
    """

    connection.execute("DELETE FROM system_interaction_field_contract WHERE scope_id=?", [scope_id])
    boundary_rows = connection.execute(
        """SELECT boundary_interaction_id, interaction_id, source_repo_id,
                  outbound_interface_id, outbound_operation, target_repo_id,
                  target_ingress_interface_id, target_ingress_operation,
                  match_status, confidence, payload_json
           FROM system_boundary_interaction
           WHERE scope_id=?
           ORDER BY boundary_interaction_id""",
        [scope_id],
    ).fetchall()

    execution_paths_by_boundary: dict[str, list[str]] = defaultdict(list)
    for boundary_interaction_id, call_chain_raw in connection.execute(
        """SELECT boundary_interaction_id, call_chain_json
           FROM system_interaction_execution_context
           WHERE scope_id=?
           ORDER BY boundary_interaction_id, execution_context_id""",
        [scope_id],
    ).fetchall():
        values = json.loads(call_chain_raw) if isinstance(call_chain_raw, str) else (call_chain_raw or [])
        bucket = execution_paths_by_boundary[str(boundary_interaction_id)]
        for value in values:
            text = str(value).strip()
            if text and text not in bucket:
                bucket.append(text)

    method_reference_records = _load_records(connection, "method_references.json", evidence_relation=value_flow_evidence_relation)
    occurrence_records = _load_records(connection, "catalog/field_occurrences.json", evidence_relation=value_flow_evidence_relation)
    edge_records = _load_records(connection, "catalog/field_flow_edges.json", evidence_relation=value_flow_evidence_relation)

    method_references_by_repo: dict[str, list[tuple[str, dict[str, Any]]]] = defaultdict(list)
    for record_id, repo_id, payload in method_reference_records:
        if _is_production(payload):
            method_references_by_repo[repo_id].append((record_id, payload))

    occurrence_by_repo: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    occurrence_record_id_by_repo: dict[str, dict[str, str]] = defaultdict(dict)
    occurrences_by_repo_operation: dict[str, dict[str, list[tuple[str, dict[str, Any]]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for record_id, repo_id, payload in occurrence_records:
        occurrence_id = str(payload.get("occurrence_id") or "").strip()
        operation = str(payload.get("operation") or "").strip()
        if not occurrence_id or not operation or not _is_production(payload):
            continue
        occurrence_by_repo[repo_id][occurrence_id] = payload
        occurrence_record_id_by_repo[repo_id][occurrence_id] = record_id
        occurrences_by_repo_operation[repo_id][operation].append((record_id, payload))

    for repo_id, operations in occurrences_by_repo_operation.items():
        existing = {
            (
                str(payload.get("owner_operation") or ""),
                str(payload.get("resolved_operation") or ""),
                str(payload.get("reference_text") or ""),
            )
            for _record_id, payload in method_references_by_repo.get(repo_id, ())
        }
        for record_id, payload in _inferred_method_references(operations):
            key = (
                str(payload.get("owner_operation") or ""),
                str(payload.get("resolved_operation") or ""),
                str(payload.get("reference_text") or ""),
            )
            if key not in existing:
                method_references_by_repo[repo_id].append((record_id, payload))
                existing.add(key)

    adjacency_by_repo: dict[str, dict[str, list[tuple[str, str]]]] = defaultdict(lambda: defaultdict(list))
    edge_record_id_by_repo: dict[str, dict[str, str]] = defaultdict(dict)
    for record_id, repo_id, payload in edge_records:
        source = str(payload.get("source_occurrence_id") or "").strip()
        target = str(payload.get("target_occurrence_id") or "").strip()
        edge_id = str(payload.get("edge_id") or "").strip()
        if (
            not source
            or not target
            or not edge_id
            or not _is_production(payload)
            or source not in occurrence_by_repo.get(repo_id, {})
            or target not in occurrence_by_repo.get(repo_id, {})
        ):
            continue
        adjacency_by_repo[repo_id][source].append((target, edge_id))
        edge_record_id_by_repo[repo_id][edge_id] = record_id
    adjacency = {
        repo_id: {source: tuple(sorted(targets)) for source, targets in values.items()}
        for repo_id, values in adjacency_by_repo.items()
    }

    rows: list[tuple[Any, ...]] = []
    for (
        boundary_interaction_id,
        interaction_id,
        source_repo_id,
        outbound_interface_id,
        outbound_operation,
        target_repo_id,
        target_ingress_interface_id,
        target_ingress_operation,
        boundary_match_status,
        boundary_confidence,
        payload_json,
    ) in boundary_rows:
        if str(boundary_match_status) != "matched" or str(boundary_confidence) not in {"confirmed", "probable"}:
            continue
        boundary_payload = _mapping(payload_json)
        boundary_payload["call_chain"] = execution_paths_by_boundary.get(str(boundary_interaction_id), [])
        outbound_interface = _mapping(boundary_payload.get("outbound_interface"))
        target_interface = _mapping(boundary_payload.get("target_ingress_interface"))
        outbound_items = _unique_by_normalized(_contract_items(outbound_interface))
        target_items = _unique_by_normalized(_contract_items(target_interface))
        emitted_wire_paths: set[str] = set()

        for wire_path in sorted(set(outbound_items).intersection(target_items)):
            outbound = outbound_items[wire_path]
            target = target_items[wire_path]
            field_contract_id = stable_id(
                "system_interaction_field_contract",
                str(boundary_interaction_id),
                wire_path,
            )
            type_compatibility = _type_compatibility(outbound["attribute_type"], target["attribute_type"])
            provenance = {
                "schema_version": FIELD_CONTRACT_SCHEMA_VERSION,
                "boundary_interaction_id": boundary_interaction_id,
                "boundary_match_status": boundary_match_status,
                "boundary_confidence": boundary_confidence,
                "match_basis": "exact_unique_normalized_request_wire_path",
                "normalization": "casefold_remove_array_member_markers_canonicalize_separators",
                "outbound_evidence_refs": outbound["evidence_refs"],
                "target_evidence_refs": target["evidence_refs"],
            }
            payload = {
                "schema_version": FIELD_CONTRACT_SCHEMA_VERSION,
                "field_contract_id": field_contract_id,
                "boundary_interaction_id": boundary_interaction_id,
                "interaction_id": interaction_id,
                "source": {
                    "repo_id": source_repo_id,
                    "interface_id": outbound_interface_id,
                    "operation": outbound_operation,
                    "payload_type": outbound_interface.get("request_payload_type"),
                    "field": outbound["raw"],
                },
                "target": {
                    "repo_id": target_repo_id,
                    "interface_id": target_ingress_interface_id,
                    "operation": target_ingress_operation,
                    "payload_type": target_interface.get("request_payload_type"),
                    "field": target["raw"],
                },
                "wire_path": wire_path,
                "match_kind": "exact_wire_path",
                "match_status": str(boundary_confidence),
                "type_compatibility": type_compatibility,
                "provenance": provenance,
            }
            rows.append(
                (
                    field_contract_id,
                    boundary_interaction_id,
                    interaction_id,
                    scope_id,
                    source_repo_id,
                    outbound_interface_id,
                    outbound_operation,
                    outbound_interface.get("request_payload_type"),
                    outbound["path"],
                    outbound["attribute_name"],
                    outbound["wire_name"],
                    outbound["attribute_type"],
                    outbound["source_schema"],
                    target_repo_id,
                    target_ingress_interface_id,
                    target_ingress_operation,
                    target_interface.get("request_payload_type"),
                    target["path"],
                    target["attribute_name"],
                    target["wire_name"],
                    target["attribute_type"],
                    target["source_schema"],
                    wire_path,
                    "exact_wire_path",
                    str(boundary_confidence),
                    type_compatibility,
                    canonical_json(provenance),
                    canonical_json(payload),
                )
            )
            emitted_wire_paths.add(wire_path)

        direct_nested_candidates = _direct_nested_contract_candidates(
            outbound_operation=str(outbound_operation or ""),
            target_items=target_items,
            occurrences_by_operation=occurrences_by_repo_operation.get(str(source_repo_id), {}),
        )
        for derived in direct_nested_candidates:
            wire_path = str(derived["wire_path"])
            if wire_path in emitted_wire_paths:
                continue
            target = derived["target"]
            field_contract_id = stable_id(
                "system_interaction_field_contract", str(boundary_interaction_id), wire_path
            )
            provenance = {
                "schema_version": FIELD_CONTRACT_SCHEMA_VERSION,
                "boundary_interaction_id": boundary_interaction_id,
                "boundary_match_status": boundary_match_status,
                "boundary_confidence": boundary_confidence,
                "match_basis": "exact_observed_outbound_boundary_wire_path_and_target_wire_path",
                "source_occurrence_id": derived["source_occurrence_id"],
                "source_record_id": derived["source_record_id"],
                "target_evidence_refs": target["evidence_refs"],
            }
            outbound_raw = {
                "attribute_name": derived["outbound_attribute_name"],
                "attribute_path": derived["outbound_path"],
                "attribute_type": derived["outbound_attribute_type"],
                "wire_name": derived["outbound_wire_name"],
                "source_schema": derived["outbound_source_schema"],
                "source": "observed_outbound_boundary_occurrence",
                "source_occurrence_id": derived["source_occurrence_id"],
                "serialized_name_basis": "exact_operation_scoped_boundary_wire_path",
            }
            payload = {
                "schema_version": FIELD_CONTRACT_SCHEMA_VERSION,
                "field_contract_id": field_contract_id,
                "boundary_interaction_id": boundary_interaction_id,
                "interaction_id": interaction_id,
                "source": {
                    "repo_id": source_repo_id,
                    "interface_id": outbound_interface_id,
                    "operation": outbound_operation,
                    "payload_type": outbound_interface.get("request_payload_type"),
                    "field": outbound_raw,
                    "local_occurrence_id": derived["source_occurrence_id"],
                },
                "target": {
                    "repo_id": target_repo_id,
                    "interface_id": target_ingress_interface_id,
                    "operation": target_ingress_operation,
                    "payload_type": target_interface.get("request_payload_type"),
                    "field": target["raw"],
                },
                "wire_path": wire_path,
                "match_kind": "exact_observed_nested_boundary_path",
                "match_status": str(boundary_confidence),
                "type_compatibility": _type_compatibility(
                    derived["outbound_attribute_type"], target["attribute_type"]
                ),
                "provenance": provenance,
            }
            rows.append((
                field_contract_id, boundary_interaction_id, interaction_id, scope_id,
                source_repo_id, outbound_interface_id, outbound_operation,
                outbound_interface.get("request_payload_type"), derived["outbound_path"],
                derived["outbound_attribute_name"], derived["outbound_wire_name"],
                derived["outbound_attribute_type"], derived["outbound_source_schema"],
                target_repo_id, target_ingress_interface_id, target_ingress_operation,
                target_interface.get("request_payload_type"), target["path"],
                target["attribute_name"], target["wire_name"], target["attribute_type"],
                target["source_schema"], wire_path, "exact_observed_nested_boundary_path",
                str(boundary_confidence), payload["type_compatibility"],
                canonical_json(provenance), canonical_json(payload),
            ))
            emitted_wire_paths.add(wire_path)

        derived_candidates = _collection_member_contract_candidates(
            repo_id=str(source_repo_id),
            boundary_payload=boundary_payload,
            outbound_operation=str(outbound_operation or ""),
            outbound_payload_type=str(outbound_interface.get("request_payload_type") or "").strip(),
            target_items=target_items,
            method_references=method_references_by_repo.get(str(source_repo_id), []),
            occurrences_by_operation=occurrences_by_repo_operation.get(str(source_repo_id), {}),
            occurrence_by_id=occurrence_by_repo.get(str(source_repo_id), {}),
            occurrence_record_id=occurrence_record_id_by_repo.get(str(source_repo_id), {}),
            adjacency=adjacency.get(str(source_repo_id), {}),
            edge_record_id=edge_record_id_by_repo.get(str(source_repo_id), {}),
        )
        for derived in derived_candidates:
            wire_path = str(derived["wire_path"])
            if wire_path in emitted_wire_paths:
                continue
            target = derived["target"]
            field_contract_id = stable_id(
                "system_interaction_field_contract",
                str(boundary_interaction_id),
                wire_path,
            )
            provenance = {
                "schema_version": FIELD_CONTRACT_SCHEMA_VERSION,
                "boundary_interaction_id": boundary_interaction_id,
                "boundary_match_status": boundary_match_status,
                "boundary_confidence": boundary_confidence,
                "match_basis": "exact_collection_member_method_reference_builder_path_and_target_wire_path",
                "normalization": "casefold_remove_array_member_markers_canonicalize_separators",
                "method_reference_record_id": derived["method_reference_record_id"],
                "method_reference_id": derived["method_reference_id"],
                "collection_result_record_id": derived["collection_result_record_id"],
                "outer_path_record_id": derived["outer_path_record_id"],
                "builder_record_ids": derived["builder_record_ids"],
                "terminal_builder_occurrence_id": derived["terminal_builder_occurrence_id"],
                "terminal_builder_record_id": derived["terminal_builder_record_id"],
                "outbound_link_basis": derived["outbound_link_basis"],
                "field_flow_edge_record_ids": [
                    edge_record_id_by_repo.get(str(source_repo_id), {}).get(edge_id)
                    for edge_id in [
                        *derived["outer_path_edge_ids"],
                        *derived["member_field_flow_edge_ids"],
                        *derived["outbound_link_edge_ids"],
                    ]
                    if edge_record_id_by_repo.get(str(source_repo_id), {}).get(edge_id)
                ],
                "target_evidence_refs": target["evidence_refs"],
            }
            outbound_raw = {
                "attribute_name": derived["outbound_attribute_name"],
                "attribute_path": derived["outbound_path"],
                "attribute_type": derived["outbound_attribute_type"],
                "wire_name": derived["outbound_wire_name"],
                "source_schema": derived["outbound_source_schema"],
                "source": "observed_collection_member_builder_composition",
                "serialized_name_basis": "exact_observed_builder_path_confirmed_by_target_contract",
            }
            payload = {
                "schema_version": FIELD_CONTRACT_SCHEMA_VERSION,
                "field_contract_id": field_contract_id,
                "boundary_interaction_id": boundary_interaction_id,
                "interaction_id": interaction_id,
                "source": {
                    "repo_id": source_repo_id,
                    "interface_id": outbound_interface_id,
                    "operation": outbound_operation,
                    "payload_type": outbound_interface.get("request_payload_type"),
                    "field": outbound_raw,
                    "local_occurrence_id": derived["terminal_builder_occurrence_id"],
                    "collection_member_composition": {
                        "owner_operation": derived["owner_operation"],
                        "helper_operation": derived["helper_operation"],
                        "helper_signature": derived["helper_signature"],
                        "member_type": derived["member_type"],
                        "collection_path": derived["collection_path"],
                        "functional_parameter_binding": derived["functional_parameter_binding"],
                        "terminal_builder_occurrence_id": derived["terminal_builder_occurrence_id"],
                        "outbound_link_basis": derived["outbound_link_basis"],
                    },
                },
                "target": {
                    "repo_id": target_repo_id,
                    "interface_id": target_ingress_interface_id,
                    "operation": target_ingress_operation,
                    "payload_type": target_interface.get("request_payload_type"),
                    "field": target["raw"],
                },
                "wire_path": wire_path,
                "match_kind": "exact_collection_member_builder_path",
                "match_status": "probable",
                "type_compatibility": "unknown",
                "provenance": provenance,
            }
            rows.append(
                (
                    field_contract_id,
                    boundary_interaction_id,
                    interaction_id,
                    scope_id,
                    source_repo_id,
                    outbound_interface_id,
                    outbound_operation,
                    outbound_interface.get("request_payload_type"),
                    derived["outbound_path"],
                    derived["outbound_attribute_name"],
                    derived["outbound_wire_name"],
                    derived["outbound_attribute_type"],
                    derived["outbound_source_schema"],
                    target_repo_id,
                    target_ingress_interface_id,
                    target_ingress_operation,
                    target_interface.get("request_payload_type"),
                    target["path"],
                    target["attribute_name"],
                    target["wire_name"],
                    target["attribute_type"],
                    target["source_schema"],
                    wire_path,
                    "exact_collection_member_builder_path",
                    "probable",
                    "unknown",
                    canonical_json(provenance),
                    canonical_json(payload),
                )
            )
            emitted_wire_paths.add(wire_path)

    bulk_insert(connection, "INSERT INTO system_interaction_field_contract VALUES", rows)
    return {"system_interaction_field_contract": len(rows)}
