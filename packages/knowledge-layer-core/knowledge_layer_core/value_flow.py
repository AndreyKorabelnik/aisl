from __future__ import annotations

import json
import re
from collections import defaultdict
from typing import Any, Iterable, Mapping

from .bulk import bulk_insert
from .interaction_contracts import normalize_wire_path
from .metrics import canonical_json
from prepared_knowledge_runtime.normalization import stable_id

VALUE_FLOW_SCHEMA_VERSION = "repository_value_flow/v6"

_TIME_GENERATOR_RE = re.compile(
    r"(?:Instant|OffsetDateTime|LocalDateTime|ZonedDateTime)\.now\s*\(|Clock\.systemUTC\s*\("
)
_HASH_RE = re.compile(
    r"(?:MessageDigest|DigestUtils|Hashing\.|\.digest\s*\(|\b(?:sha(?:1|224|256|384|512)|md5|hashCode)\s*\()",
    re.IGNORECASE,
)
_FORMAT_RE = re.compile(
    r"(?:String\.format\s*\(|\.formatted\s*\(|(?:DateTimeFormatter|SimpleDateFormat)|\.format\s*\()",
    re.IGNORECASE,
)
_NORMALIZE_RE = re.compile(
    r"(?:\.trim\s*\(|\.strip\s*\(|\.stripLeading\s*\(|\.stripTrailing\s*\(|"
    r"\.toLowerCase\s*\(|\.toUpperCase\s*\(|\bnormalize\w*\s*\(|\bcanonicali[sz]e\w*\s*\()",
    re.IGNORECASE,
)
_COMBINE_RE = re.compile(
    r"(?:\.concat\s*\(|String\.join\s*\(|Collectors\.joining\s*\(|\bjoin\s*\()",
    re.IGNORECASE,
)
_DERIVED_HELPER_RE = re.compile(
    r"(?:^|\.)(?:to|from|convert|map|calculate|compute|derive|encode|decode|transform|parse|resolve)[A-Z_\w]*\s*\(",
)
_PASSTHROUGH_CALL_RE = re.compile(
    r"(?:\.stream\s*\(\s*\)|\.parallelStream\s*\(\s*\)|\.iterator\s*\(\s*\))$",
    re.IGNORECASE,
)

_DERIVATION_INPUT_EDGE_KINDS = {
    "expression_component",
    "conditional_branch",
}
_DIRECT_IDENTITY_EDGE_KINDS = {
    "variable_initializer",
    "assignment",
    "assignment_expression",
    "observed_value_flow",
    "parameter_binding",
    "invocation_argument",
    "method_argument_binding_field_projection",
    "method_argument_binding",
    "invocation_receiver",
    "method_return",
    "return_to_caller",
    "implementation_return_to_interface",
    "boundary_response_payload_binding",
    "constructor_argument",
    "setter_argument",
    "builder_argument",
    "builder_field_to_built_object",
    "object_field_contribution_to_built_object",
}

_BOUNDARY_OCCURRENCE_KINDS = {
    "boundary_field",
    "payload_field",
    "boundary_request_field",
    "boundary_response_field",
}

_HTTP_CONTRACT_ROLES = (
    ("request", "request_contract_signature", "request_payload_type"),
    ("response", "response_contract_signature", "response_payload_type"),
)

_LOOPBACK_HOSTS = {"localhost", "0.0.0.0", "::", "::1"}


def _authority_host(value: object) -> str:
    text = str(value or "").strip().casefold()
    if not text:
        return ""
    text = re.sub(r"^[a-z][a-z0-9+.-]*://", "", text)
    text = text.split("/", 1)[0]
    if text.startswith("[") and "]" in text:
        return text[1:text.index("]")]
    return text.rsplit(":", 1)[0] if text.count(":") == 1 else text


def _is_environment_authority(value: object) -> bool:
    host = _authority_host(value)
    if not host:
        return False
    if host in _LOOPBACK_HOSTS:
        return True
    return bool(re.fullmatch(r"127(?:\.\d{1,3}){3}", host))


def _evidence_values(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return _stable_text_values((value,))
    if isinstance(value, Iterable):
        return _stable_text_values(value)
    return _stable_text_values((value,))


def _transport_evidence_packet(
    *,
    boundary_confidence: str,
    boundary_payload: Mapping[str, Any],
    payload_role: str,
    wire_path: str,
    source_item_count: int,
    target_item_count: int,
    matched_item_count: int,
) -> dict[str, Any]:
    match_basis = _mapping(boundary_payload.get("match_basis"))
    candidate_lookup = _mapping(match_basis.get("candidate_lookup"))
    contract = _mapping(match_basis.get("contract"))
    outbound_authorities = list(_evidence_values(match_basis.get("outbound_authorities")))
    target_authorities = list(_evidence_values(match_basis.get("target_authorities")))
    authority_overlap = list(_evidence_values(match_basis.get("authority_overlap")))
    service_overlap = list(_evidence_values(match_basis.get("service_identity_overlap")))
    property_overlap = list(_evidence_values(match_basis.get("property_identity_overlap")))

    supporting: list[str] = []
    if str(match_basis.get("http_method") or "").strip():
        supporting.append("http_method_exact")
    if str(match_basis.get("path_basis") or "") == "exact_path":
        supporting.append("normalized_path_exact")
    if authority_overlap:
        supporting.append("authority_exact")
    if service_overlap:
        supporting.append("service_identity_exact")
    if property_overlap:
        supporting.append("property_identity_exact")
    if int(candidate_lookup.get("indexed_candidate_count") or 0) == 1:
        supporting.append("target_operation_unique")
    supporting.append("wire_path_exact")
    if int(contract.get("request_field_overlap_count") or 0) > 0:
        supporting.append("request_contract_overlap")
    similarity = contract.get("request_field_similarity")
    if isinstance(similarity, (int, float)) and float(similarity) >= 0.999:
        supporting.append("request_contract_exact")

    environment_authorities = [value for value in outbound_authorities if _is_environment_authority(value)]
    non_environment_outbound = [value for value in outbound_authorities if not _is_environment_authority(value)]
    non_environment_target = [value for value in target_authorities if not _is_environment_authority(value)]
    limitations: list[str] = []
    conflicts: list[str] = []
    if str(boundary_confidence) == "probable":
        limitations.append("boundary_interaction_probable")
    if environment_authorities:
        limitations.append("environment_authority_non_binding")
    if not authority_overlap:
        limitations.append("authority_not_confirmed")
    if contract.get("request_payload_type_match") is False:
        limitations.append("request_payload_type_not_equal")
    if isinstance(similarity, (int, float)) and 0 <= float(similarity) < 0.999:
        limitations.append("request_contract_partial")
    if non_environment_outbound and non_environment_target and not authority_overlap:
        conflicts.append("authority_conflict")

    coverage_denominator = max(source_item_count, target_item_count, 1)
    return {
        "edge_status": "confirmed" if str(boundary_confidence) == "confirmed" else "candidate",
        "confidence": str(boundary_confidence),
        "supporting_evidence": list(_stable_text_values(supporting)),
        "conflicting_evidence": list(_stable_text_values(conflicts)),
        "limitations": list(_stable_text_values(limitations)),
        "address_interpretation": {
            "outbound_authorities": outbound_authorities,
            "target_authorities": target_authorities,
            "environment_authorities": environment_authorities,
            "authority_overlap": authority_overlap,
            "binding_strength": "strong" if authority_overlap else "non_binding" if environment_authorities else "unknown",
        },
        "contract_coverage": {
            "payload_role": payload_role,
            "wire_path": wire_path,
            "source_field_count": source_item_count,
            "target_field_count": target_item_count,
            "matched_field_count": matched_item_count,
            "matched_ratio": round(matched_item_count / coverage_denominator, 6),
        },
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


def _has_relation(connection: Any, name: str) -> bool:
    return bool(connection.execute(
        "SELECT count(*) FROM information_schema.tables WHERE lower(table_name)=lower(?)", [name]
    ).fetchone()[0])


def _load_records(connection: Any, artifact_name: str) -> list[tuple[str, str, dict[str, Any]]]:
    rows = connection.execute(
        """SELECT record_occurrence_id, repo_id, payload_json
           FROM value_flow_evidence_record
           WHERE artifact_name=?
           ORDER BY repo_id, occurrence_ordinal, record_occurrence_id""",
        [artifact_name],
    ).fetchall()
    return [(str(record_id), str(repo_id), _mapping(payload)) for record_id, repo_id, payload in rows]


def _richness(payload: Mapping[str, Any]) -> tuple[int, int]:
    return (
        sum(1 for value in payload.values() if value not in (None, "", [], {})),
        len(canonical_json(payload)),
    )


def _expression(payload: Mapping[str, Any]) -> str:
    return str(
        payload.get("expression_text")
        or payload.get("expression")
        or payload.get("source_expression")
        or payload.get("field_path")
        or ""
    ).strip()


def _node_kind(payload: Mapping[str, Any], *, is_derivation: bool = False) -> str:
    if is_derivation:
        return "derivation"
    kind = str(payload.get("occurrence_kind") or "").strip().casefold()
    expression = _expression(payload)
    if kind == "literal":
        return "constant"
    field_path = str(payload.get("field_path") or payload.get("symbol") or "").strip()
    terminal = re.split(r"[./]", field_path)[-1] if field_path else ""
    if kind == "local_field" and terminal and re.fullmatch(r"[A-Z][A-Z0-9_]*", terminal):
        return "constant"
    if kind in {"configuration", "configuration_value", "property_value", "config_value"}:
        return "configuration"
    if kind in {"generated_value", "generated_identifier"}:
        return "generated_value"
    if kind in {"local_variable", "method_invocation"} and _TIME_GENERATOR_RE.search(expression):
        return "generated_value"
    if kind in {
        "parameter",
        "method_parameter",
        "constructor_parameter",
        "constructor_argument",
        "lambda_parameter",
    }:
        return "parameter"
    if kind == "method_return":
        return "return_value"
    if kind in {
        "boundary_field",
        "payload_field",
        "field_access",
        "local_field",
        "builder_target",
        "builder_nested_field",
        "setter_target",
        "projected_object_field",
        "object_field",
        "nested_object_field_projection",
        "observed_nested_object_field_projection",
        "database_column",
        "storage_field",
    }:
        return "database_column" if kind in {"database_column", "storage_field"} else "field"
    return "local_value"


def _display_ref(payload: Mapping[str, Any], occurrence_id: str) -> str:
    return str(
        payload.get("field_path")
        or payload.get("wire_field_path")
        or payload.get("symbol")
        or payload.get("name")
        or _expression(payload)
        or occurrence_id
    ).strip()


def _type_ref(payload: Mapping[str, Any]) -> str | None:
    value = (
        payload.get("declared_type")
        or payload.get("field_type")
        or payload.get("value_type")
        or payload.get("type")
    )
    text = str(value or "").strip()
    return text or None


def _terminal_name(payload: Mapping[str, Any], *, node_kind: str) -> str | None:
    if node_kind not in {"field", "wire_field"}:
        return None
    value = str(
        payload.get("property_name")
        or payload.get("setter_field_tail")
        or payload.get("builder_field_tail")
        or payload.get("wire_field_path")
        or payload.get("field_path")
        or payload.get("field_name")
        or payload.get("symbol")
        or ""
    ).strip()
    if not value:
        return None
    value = value.replace("[]", "").rstrip(".)")
    terminal = re.split(r"[./]", value)[-1]
    if ".builder." in value:
        terminal = value.rsplit(".builder.", 1)[-1]
    return terminal.strip("() ").casefold() or None


def _flow_kind(edge_kind: str) -> str:
    kind = edge_kind.casefold()
    if kind in {"variable_initializer", "assignment", "assignment_expression", "observed_value_flow"} or "assignment" in kind:
        return "assignment"
    if kind in {
        "parameter_binding",
        "invocation_argument",
        "method_argument_binding_field_projection",
        "method_argument_binding",
        "interface_implementation_parameter_binding",
        "invocation_receiver",
    }:
        return "argument_binding"
    if kind in {"method_return", "return_to_caller", "implementation_return_to_interface", "boundary_response_payload_binding"}:
        return "return_flow"
    if "constructor" in kind:
        return "constructor_mapping"
    if "setter" in kind:
        return "setter_mapping"
    if "builder" in kind or kind == "object_field_contribution_to_built_object":
        return "builder_mapping"
    if "deserial" in kind:
        return "deserialization"
    if "serial" in kind:
        return "serialization"
    if "persistence" in kind or "database" in kind or "storage" in kind:
        return "persistence_write" if "write" in kind else "persistence_read"
    if kind in {"expression_component", "conditional_branch", "conditional_expression", "guard_condition_contribution"} or "derivation" in kind:
        return "derived_value"
    if "projection" in kind:
        return "field_mapping"
    return "field_mapping"


def _explicit_transformation(payload: Mapping[str, Any]) -> tuple[str | None, str | None]:
    aliases = {
        "direct": "identity",
        "direct_mapping": "identity",
        "passthrough": "identity",
        "rename": "identity",
        "identity": "identity",
        "normalized": "normalized",
        "normalization": "normalized",
        "formatted": "formatted",
        "formatting": "formatted",
        "hashed": "hashed",
        "hash": "hashed",
        "combined": "combined",
        "concatenation": "combined",
        "concat": "combined",
        "derived": "derived",
        "calculated": "derived",
        "extracted": "extracted",
        "projection": "extracted",
        "unknown": "unknown",
    }
    for key in ("transformation_kind", "derivation_kind", "expression_kind", "mapping_kind"):
        raw = str(payload.get(key) or "").strip().casefold()
        if raw in aliases:
            return aliases[raw], f"edge_metadata:{key}"
    return None, None


def _expression_transformation(payload: Mapping[str, Any], *, allow_generic_helper: bool) -> tuple[str | None, str | None]:
    text = _expression(payload)
    if not text:
        return None, None
    if _TIME_GENERATOR_RE.search(text):
        return "identity", "observed_expression:generated_value"
    if _HASH_RE.search(text):
        return "hashed", "observed_expression:hash_operation"
    if _FORMAT_RE.search(text):
        return "formatted", "observed_expression:format_operation"
    if _NORMALIZE_RE.search(text):
        return "normalized", "observed_expression:normalization_operation"
    if _COMBINE_RE.search(text):
        return "combined", "observed_expression:combining_operation"
    if "+" in text and not re.fullmatch(r"[+\-]?\d+(?:\.\d+)?", text.strip()):
        declared = str(payload.get("declared_type") or payload.get("type") or "").casefold()
        if '"' in text or "'" in text or "string" in declared:
            return "combined", "observed_expression:string_combination"
        return "derived", "observed_expression:additive_derivation"
    kind = str(payload.get("occurrence_kind") or "").strip().casefold()
    if kind == "conditional_expression":
        return "derived", "observed_expression:conditional"
    if allow_generic_helper and kind == "method_invocation":
        if _PASSTHROUGH_CALL_RE.search(text):
            return "identity", "observed_expression:pass_through_invocation"
        if _DERIVED_HELPER_RE.search(text):
            return "derived", "observed_expression:conversion_helper"
        return "unknown", "observed_expression:unclassified_invocation"
    return None, None


def _value_preservation(transformation_kind: str) -> str:
    if transformation_kind in {"identity", "extracted"}:
        return "preserved"
    if transformation_kind in {"normalized", "formatted", "combined"}:
        return "partially_preserved"
    if transformation_kind in {"hashed", "derived"}:
        return "transformed"
    return "unknown"


def _confidence(payload: Mapping[str, Any]) -> str:
    level = str(payload.get("evidence_level") or payload.get("confidence") or "").strip().casefold()
    if level in {"probable", "inferred", "heuristic"}:
        return "probable"
    return "confirmed"


def _stable_text_values(values: Iterable[object]) -> tuple[str, ...]:
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in result:
            result.append(text)
    return tuple(result)


def _interface_records(connection: Any) -> list[tuple[str, str, dict[str, Any]]]:
    return _load_records(connection, "system_interface_catalog.json")


def _composed_outbound_interface_records(
    connection: Any,
    *,
    scope_id: str,
    existing_interface_ids: set[tuple[str, str]],
) -> list[tuple[str, str, dict[str, Any]]]:
    """Expose KLC-composed outbound boundaries as value-flow interface records.

    ``system-interactions`` may replace several concrete Core call-site observations with
    one technical outbound boundary.  That boundary has a new KLC-owned interface ID and
    therefore is intentionally absent from the original Core ``system_interface_catalog``.
    Downstream value-flow must materialize wire nodes for the composed identity itself
    rather than aliasing it to an arbitrary member observation.
    """
    if not _has_relation(connection, "system_boundary_interaction"):
        return []
    rows = connection.execute(
        """SELECT boundary_interaction_id, source_repo_id, outbound_interface_id,
                  provenance_json, payload_json
           FROM system_boundary_interaction
           WHERE scope_id=? AND protocol='http' AND match_status='matched'
           ORDER BY boundary_interaction_id""",
        [scope_id],
    ).fetchall()
    result_by_key: dict[tuple[str, str], tuple[str, str, dict[str, Any]]] = {}
    for boundary_interaction_id, source_repo_id, outbound_interface_id, provenance_raw, payload_raw in rows:
        repo_id = str(source_repo_id or "").strip()
        interface_id = str(outbound_interface_id or "").strip()
        key = (repo_id, interface_id)
        if not repo_id or not interface_id or key in existing_interface_ids:
            continue
        payload = _mapping(payload_raw)
        interface_payload = dict(_mapping(payload.get("outbound_interface")))
        if not interface_payload:
            continue
        interface_payload["interface_id"] = interface_id
        interface_payload.setdefault("direction", "outbound")
        interface_payload.setdefault("protocol", "http")
        interface_payload.setdefault("boundary_kind", "http_outbound")
        interface_payload["klc_composed_boundary"] = True
        record_id = f"system_interaction_composed_outbound_interface:{interface_id}"
        current = result_by_key.get(key)
        if current is None or _richness(interface_payload) > _richness(current[2]):
            result_by_key[key] = (record_id, repo_id, interface_payload)
    return [result_by_key[key] for key in sorted(result_by_key)]


def _interaction_field_contract_records(connection: Any, *, scope_id: str) -> list[dict[str, Any]]:
    if not _has_relation(connection, "system_interaction_field_contract"):
        return []
    rows = connection.execute(
        """SELECT field_contract_id, boundary_interaction_id, source_repo_id,
                  outbound_interface_id, outbound_operation, outbound_payload_type,
                  outbound_field_path, target_repo_id, target_ingress_interface_id,
                  target_field_path, wire_path, match_kind, match_status,
                  provenance_json, payload_json
           FROM system_interaction_field_contract
           WHERE scope_id=?
           ORDER BY boundary_interaction_id, wire_path, field_contract_id""",
        [scope_id],
    ).fetchall()
    result: list[dict[str, Any]] = []
    for row in rows:
        payload = _mapping(row[14])
        provenance = _mapping(row[13])
        source = _mapping(payload.get("source"))
        source_field = _mapping(source.get("field"))
        composition = _mapping(source.get("collection_member_composition"))
        local_occurrence_id = str(
            source.get("local_occurrence_id")
            or source_field.get("source_occurrence_id")
            or composition.get("terminal_builder_occurrence_id")
            or ""
        ).strip() or None
        result.append({
            "field_contract_id": str(row[0]),
            "boundary_interaction_id": str(row[1]),
            "source_repo_id": str(row[2]),
            "outbound_interface_id": str(row[3]),
            "outbound_operation": str(row[4] or ""),
            "outbound_payload_type": str(row[5] or "") or None,
            "outbound_field_path": str(row[6] or ""),
            "target_repo_id": str(row[7]),
            "target_ingress_interface_id": str(row[8]),
            "target_field_path": str(row[9] or ""),
            "wire_path": normalize_wire_path(row[10]),
            "match_kind": str(row[11]),
            "match_status": str(row[12]),
            "local_occurrence_id": local_occurrence_id,
            "source_field": source_field,
            "provenance": provenance,
            "payload": payload,
        })
    return result


def _contract_wire_path(item: Mapping[str, Any]) -> str:
    raw = (
        item.get("attribute_path")
        or item.get("wire_field_path")
        or item.get("wire_name")
        or item.get("attribute_name")
    )
    return normalize_wire_path(raw)


def _contract_items(payload: Mapping[str, Any], key: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for ordinal, raw in enumerate(payload.get(key) or ()):  # pragma: no branch - compact catalog contract
        if not isinstance(raw, Mapping):
            continue
        item = dict(raw)
        wire_path = _contract_wire_path(item)
        if not wire_path:
            continue
        items.append(
            {
                "ordinal": ordinal,
                "wire_path": wire_path,
                "wire_name": str(item.get("wire_name") or item.get("wire_field_name") or "").strip() or None,
                "attribute_name": str(item.get("attribute_name") or "").strip() or None,
                "attribute_path": str(item.get("attribute_path") or item.get("wire_field_path") or "").strip() or None,
                "attribute_type": str(item.get("attribute_type") or item.get("field_type") or "").strip() or None,
                "source_schema": str(item.get("source_schema") or "").strip() or None,
                "evidence_refs": list(item.get("evidence_refs") or []),
                "raw": item,
            }
        )
    return items



def _unique_contract_items(payload: Mapping[str, Any], key: str) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in _contract_items(payload, key):
        grouped[str(item["wire_path"])].append(item)
    return {wire_path: items[0] for wire_path, items in grouped.items() if len(items) == 1}

def _interface_direction(payload: Mapping[str, Any]) -> str:
    return str(payload.get("direction") or "").strip().casefold()


def _interface_protocol(payload: Mapping[str, Any]) -> str:
    value = str(payload.get("protocol") or "").strip().casefold()
    return "http" if value in {"http", "https", "rest"} else value


def _wire_edge_direction(*, interface_direction: str, payload_role: str) -> tuple[str, str]:
    """Return (flow_kind, direction) for a local HTTP contract binding.

    direction is ``local_to_wire`` or ``wire_to_local`` and follows message flow:
    outbound requests and inbound responses serialize; inbound requests and outbound
    responses deserialize.
    """
    serialize = (interface_direction == "outbound" and payload_role == "request") or (
        interface_direction == "inbound" and payload_role == "response"
    )
    return ("serialization", "local_to_wire") if serialize else ("deserialization", "wire_to_local")


def _occurrence_wire_paths(payload: Mapping[str, Any]) -> tuple[str, ...]:
    values = (
        payload.get("wire_field_path"),
        payload.get("attribute_path"),
        payload.get("field_path"),
        payload.get("property_name"),
        payload.get("field_name"),
    )
    normalized = [normalize_wire_path(value) for value in values if value is not None]
    return _stable_text_values(value for value in normalized if value)


def _boundary_occurrence_score(
    payload: Mapping[str, Any],
    *,
    operation: str,
    interface_direction: str,
    payload_role: str,
    wire_path: str,
) -> int | None:
    occurrence_operation = str(payload.get("operation") or "").strip()
    if not operation or occurrence_operation != operation:
        return None
    occurrence_kind = str(payload.get("occurrence_kind") or "").strip().casefold()
    explicit_wire = normalize_wire_path(payload.get("wire_field_path"))
    if occurrence_kind not in _BOUNDARY_OCCURRENCE_KINDS and not explicit_wire:
        return None
    if wire_path not in _occurrence_wire_paths(payload):
        return None

    score = 10
    if explicit_wire == wire_path:
        score += 8
    if occurrence_kind in _BOUNDARY_OCCURRENCE_KINDS:
        score += 2
    observed_direction = str(payload.get("boundary_direction") or "").strip().casefold()
    if observed_direction:
        if observed_direction != interface_direction:
            return None
        score += 4
    observed_role = str(payload.get("payload_role") or "").strip().casefold()
    if observed_role:
        if observed_role != payload_role:
            return None
        score += 4
    return score


def _unique_boundary_occurrence(
    candidates: Mapping[str, tuple[str, dict[str, Any]]],
    *,
    operation: str,
    interface_direction: str,
    payload_role: str,
    wire_path: str,
) -> tuple[str, str, dict[str, Any], int] | None:
    ranked: list[tuple[int, str, str, dict[str, Any]]] = []
    for occurrence_id, (record_id, payload) in candidates.items():
        score = _boundary_occurrence_score(
            payload,
            operation=operation,
            interface_direction=interface_direction,
            payload_role=payload_role,
            wire_path=wire_path,
        )
        if score is not None:
            ranked.append((score, occurrence_id, record_id, payload))
    if not ranked:
        return None
    ranked.sort(key=lambda item: (-item[0], item[1], item[2]))
    best_score = ranked[0][0]
    best = [item for item in ranked if item[0] == best_score]
    if len(best) != 1:
        return None
    score, occurrence_id, record_id, payload = best[0]
    return occurrence_id, record_id, payload, score


def _classify_transformation(
    *,
    edge_kind: str,
    edge_payload: Mapping[str, Any],
    source_payload: Mapping[str, Any],
    target_payload: Mapping[str, Any],
    derivation_kind: str | None,
) -> tuple[str, str]:
    explicit, basis = _explicit_transformation(edge_payload)
    if explicit:
        return explicit, str(basis)
    if derivation_kind:
        return derivation_kind, "grouped_derivation"

    source_kind, source_basis = _expression_transformation(source_payload, allow_generic_helper=True)
    if source_kind not in {None, "identity"}:
        return source_kind, str(source_basis)

    kind = edge_kind.casefold()
    if "projection" in kind:
        return "extracted", "edge_kind:projection"
    if kind == "conditional_branch":
        return "derived", "edge_kind:conditional_branch"
    if kind == "expression_component":
        target_kind, target_basis = _expression_transformation(target_payload, allow_generic_helper=False)
        return target_kind or "derived", str(target_basis or "edge_kind:expression_component")
    if kind in _DIRECT_IDENTITY_EDGE_KINDS or "setter" in kind or "builder" in kind or "constructor" in kind:
        return "identity", "edge_kind:direct_transfer"

    target_kind, target_basis = _expression_transformation(target_payload, allow_generic_helper=False)
    if target_kind:
        return target_kind, str(target_basis)
    if source_kind == "identity":
        return "identity", str(source_basis)
    return "unknown", "unclassified"


def materialize_repository_value_flow(connection: Any, *, scope_id: str) -> dict[str, int]:
    """Materialize repository-local direct value nodes and direct observed flow edges.

    No transitive path composition is performed.  Expression/conditional contributors are
    grouped by a stable derivation identifier, and a transformation is classified only from
    explicit edge metadata or observed AST expression text already published by core.
    """
    connection.execute("DELETE FROM repository_value_flow_edge WHERE scope_id=?", [scope_id])
    connection.execute("DELETE FROM repository_value_node WHERE scope_id=?", [scope_id])

    occurrence_records = _load_records(connection, "catalog/field_occurrences.json")
    edge_records = _load_records(connection, "catalog/field_flow_edges.json")
    interface_records = _interface_records(connection)
    interaction_field_contracts = _interaction_field_contract_records(connection, scope_id=scope_id)
    existing_interface_ids = {
        (str(repo_id), str(payload.get("interface_id") or record_id).strip())
        for record_id, repo_id, payload in interface_records
    }
    interface_records = [
        *interface_records,
        *_composed_outbound_interface_records(
            connection, scope_id=scope_id, existing_interface_ids=existing_interface_ids
        ),
    ]
    if not occurrence_records and not interface_records:
        return {"repository_value_node": 0, "repository_value_flow_edge": 0}

    synthetic_contracts_by_interface: dict[tuple[str, str, str], dict[str, dict[str, Any]]] = defaultdict(dict)
    field_contracts_by_source_interface: dict[tuple[str, str, str], dict[str, dict[str, Any]]] = defaultdict(dict)
    field_contracts_by_boundary: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for contract in interaction_field_contracts:
        wire_path = str(contract["wire_path"])
        if not wire_path:
            continue
        field_contracts_by_boundary[str(contract["boundary_interaction_id"])][wire_path] = contract
        source_interface_key = (
            str(contract["source_repo_id"]),
            str(contract["outbound_interface_id"]),
            "request",
        )
        field_contracts_by_source_interface[source_interface_key][wire_path] = contract
        if str(contract["match_kind"]) == "exact_wire_path":
            continue
        synthetic_contracts_by_interface[source_interface_key][wire_path] = contract

    occurrence_by_repo: dict[str, dict[str, tuple[str, dict[str, Any]]]] = defaultdict(dict)
    for record_id, repo_id, payload in occurrence_records:
        occurrence_id = str(payload.get("occurrence_id") or "").strip()
        if not occurrence_id or not _is_production(payload):
            continue
        current = occurrence_by_repo[repo_id].get(occurrence_id)
        if current is None or _richness(payload) > _richness(current[1]):
            occurrence_by_repo[repo_id][occurrence_id] = (record_id, payload)

    edge_candidates: list[tuple[str, str, dict[str, Any], str, str, str, str]] = []
    seen_source_edges: set[tuple[str, str]] = set()
    outgoing_count: dict[tuple[str, str], int] = defaultdict(int)
    incoming_by_target: dict[tuple[str, str], list[tuple[str, str, dict[str, Any]]]] = defaultdict(list)
    for record_id, repo_id, payload in edge_records:
        if not _is_production(payload):
            continue
        edge_id = str(payload.get("edge_id") or "").strip()
        source_occurrence_id = str(payload.get("source_occurrence_id") or "").strip()
        target_occurrence_id = str(payload.get("target_occurrence_id") or "").strip()
        edge_kind = str(payload.get("edge_kind") or "").strip()
        if not edge_id or not source_occurrence_id or not target_occurrence_id or not edge_kind:
            continue
        if source_occurrence_id not in occurrence_by_repo.get(repo_id, {}) or target_occurrence_id not in occurrence_by_repo.get(repo_id, {}):
            continue
        dedupe_key = (repo_id, edge_id)
        if dedupe_key in seen_source_edges:
            continue
        seen_source_edges.add(dedupe_key)
        edge_candidates.append((record_id, repo_id, payload, edge_id, source_occurrence_id, target_occurrence_id, edge_kind))
        outgoing_count[(repo_id, source_occurrence_id)] += 1
        incoming_by_target[(repo_id, target_occurrence_id)].append((source_occurrence_id, edge_kind, payload))

    derivations: dict[tuple[str, str], dict[str, Any]] = {}
    for (repo_id, target_occurrence_id), incoming in incoming_by_target.items():
        target_payload = occurrence_by_repo[repo_id][target_occurrence_id][1]
        contributor_ids = {
            source_id
            for source_id, edge_kind, _ in incoming
            if edge_kind.casefold() in _DERIVATION_INPUT_EDGE_KINDS
        }
        expression_kind, expression_basis = _expression_transformation(
            target_payload,
            allow_generic_helper=outgoing_count[(repo_id, target_occurrence_id)] > 0,
        )
        invocation_contributors = {
            source_id
            for source_id, edge_kind, _ in incoming
            if edge_kind.casefold() == "invocation_argument"
        }
        if expression_kind in {"normalized", "formatted", "hashed", "combined", "derived", "unknown"}:
            contributor_ids.update(invocation_contributors)
        explicit_ids = {
            str(payload.get("derivation_id") or "").strip()
            for _, _, payload in incoming
            if str(payload.get("derivation_id") or "").strip()
        }
        if not contributor_ids and not explicit_ids:
            continue
        derivation_kind = expression_kind or "derived"
        if len(contributor_ids) > 1 and derivation_kind in {None, "identity", "unknown"}:
            derivation_kind = "derived"
            expression_basis = "multiple_observed_sources"
        derivation_id = sorted(explicit_ids)[0] if len(explicit_ids) == 1 else stable_id(
            "repository_value_derivation", scope_id, repo_id, target_occurrence_id
        )
        derivations[(repo_id, target_occurrence_id)] = {
            "derivation_id": derivation_id,
            "derivation_kind": derivation_kind or "derived",
            "derivation_source_count": len(contributor_ids) or len(incoming),
            "contributor_ids": contributor_ids,
            "classification_basis": expression_basis or "observed_derivation_edges",
        }

    node_rows: list[tuple[Any, ...]] = []
    node_id_by_occurrence: dict[tuple[str, str], str] = {}
    node_meta: dict[tuple[str, str], tuple[str, dict[str, Any]]] = {}
    for repo_id in sorted(occurrence_by_repo):
        for occurrence_id, (record_id, payload) in sorted(occurrence_by_repo[repo_id].items()):
            node_kind = _node_kind(payload, is_derivation=(repo_id, occurrence_id) in derivations)
            value_node_id = stable_id("repository_value_node", scope_id, repo_id, occurrence_id)
            node_id_by_occurrence[(repo_id, occurrence_id)] = value_node_id
            node_meta[(repo_id, occurrence_id)] = (node_kind, payload)
            source_path = str(payload.get("relative_file") or payload.get("file") or "").replace("\\", "/")
            operation = str(payload.get("operation") or "").strip() or None
            display_ref = _display_ref(payload, occurrence_id)
            wire_path = str(payload.get("wire_field_path") or "").strip() or None
            derivation = derivations.get((repo_id, occurrence_id))
            provenance = {
                "field_occurrence_record_id": record_id,
                "artifact_name": "catalog/field_occurrences.json",
                "relative_file": source_path or None,
                "ast_node": payload.get("ast_node"),
            }
            normalized_payload = {
                "schema_version": VALUE_FLOW_SCHEMA_VERSION,
                "value_node_id": value_node_id,
                "repo_id": repo_id,
                "occurrence_id": occurrence_id,
                "node_kind": node_kind,
                "operation": operation,
                "display_ref": display_ref,
                "type_ref": _type_ref(payload),
                "wire_path": wire_path,
                "source_path": source_path or None,
                "expression": _expression(payload) or None,
                "derivation": derivation,
                "source_occurrence": payload,
                "provenance": provenance,
            }
            node_rows.append(
                (
                    value_node_id,
                    scope_id,
                    repo_id,
                    occurrence_id,
                    node_kind,
                    operation,
                    operation,
                    display_ref,
                    _type_ref(payload),
                    wire_path,
                    source_path or None,
                    canonical_json(provenance),
                    canonical_json(normalized_payload),
                )
            )

    wire_bindings: list[dict[str, Any]] = []
    wire_occurrence_by_key: dict[tuple[str, str, str, str], str] = {}
    seen_wire_occurrences: set[tuple[str, str]] = set()
    for interface_record_id, repo_id, interface_payload in interface_records:
        if _interface_protocol(interface_payload) != "http":
            continue
        interface_id = str(interface_payload.get("interface_id") or interface_record_id).strip()
        interface_direction = _interface_direction(interface_payload)
        operation = str(interface_payload.get("operation") or "").strip()
        if not interface_id or interface_direction not in {"inbound", "outbound"} or not operation:
            continue
        for payload_role, contract_key, payload_type_key in _HTTP_CONTRACT_ROLES:
            payload_type = str(interface_payload.get(payload_type_key) or "").strip() or None
            flow_kind, local_direction = _wire_edge_direction(
                interface_direction=interface_direction,
                payload_role=payload_role,
            )
            contract_items = _contract_items(interface_payload, contract_key)
            existing_paths = {str(item["wire_path"]) for item in contract_items}
            for wire_path, contract in sorted(
                synthetic_contracts_by_interface.get((repo_id, interface_id, payload_role), {}).items()
            ):
                if wire_path in existing_paths:
                    continue
                source_field = _mapping(contract.get("source_field"))
                contract_items.append({
                    "ordinal": -1,
                    "wire_path": wire_path,
                    "wire_name": str(source_field.get("wire_name") or wire_path.rsplit(".", 1)[-1]),
                    "attribute_name": str(source_field.get("attribute_name") or wire_path.rsplit(".", 1)[-1]),
                    "attribute_path": str(
                        source_field.get("attribute_path")
                        or contract.get("outbound_field_path")
                        or wire_path
                    ),
                    "attribute_type": str(source_field.get("attribute_type") or "").strip() or None,
                    "source_schema": str(source_field.get("source_schema") or "").strip() or None,
                    "evidence_refs": [],
                    "raw": {
                        **source_field,
                        "attribute_path": str(
                            source_field.get("attribute_path")
                            or contract.get("outbound_field_path")
                            or wire_path
                        ),
                        "wire_field_path": wire_path,
                        "reconstructed": True,
                        "field_contract_id": contract["field_contract_id"],
                        "match_kind": contract["match_kind"],
                        "match_status": contract["match_status"],
                    },
                    "reconstructed": True,
                    "field_contract": contract,
                })

            interface_field_contracts = field_contracts_by_source_interface.get(
                (repo_id, interface_id, payload_role), {}
            )
            for contract_item in contract_items:
                wire_path = str(contract_item["wire_path"])
                if not contract_item.get("field_contract") and wire_path in interface_field_contracts:
                    contract = interface_field_contracts[wire_path]
                    contract_item["field_contract"] = contract
                    contract_item["raw"] = {
                        **dict(contract_item["raw"]),
                        "field_contract_id": contract["field_contract_id"],
                        "match_kind": contract["match_kind"],
                        "match_status": contract["match_status"],
                    }
                wire_occurrence_id = stable_id(
                    "repository_wire_occurrence",
                    scope_id,
                    repo_id,
                    interface_id,
                    payload_role,
                    wire_path,
                )
                wire_key = (repo_id, wire_occurrence_id)
                wire_occurrence_by_key[(repo_id, interface_id, payload_role, wire_path)] = wire_occurrence_id
                if wire_key not in seen_wire_occurrences:
                    seen_wire_occurrences.add(wire_key)
                    value_node_id = stable_id("repository_value_node", scope_id, repo_id, wire_occurrence_id)
                    node_id_by_occurrence[wire_key] = value_node_id
                    endpoint = str(
                        interface_payload.get("endpoint_or_topic_resolved")
                        or interface_payload.get("endpoint_or_topic_raw")
                        or ""
                    ).strip() or None
                    http_method = str(interface_payload.get("http_method") or "").strip().upper() or None
                    display_ref = f"HTTP {payload_role} {wire_path}"
                    provenance = {
                        "system_interface_record_id": interface_record_id,
                        "artifact_name": "system_interface_catalog.json",
                        "interface_id": interface_id,
                        "contract_key": contract_key,
                        "contract_ordinal": contract_item["ordinal"],
                        "evidence_refs": contract_item["evidence_refs"],
                        "reconstructed": bool(contract_item.get("reconstructed")),
                        "field_contract_id": _mapping(contract_item.get("field_contract")).get("field_contract_id"),
                    }
                    wire_payload = {
                        "occurrence_id": wire_occurrence_id,
                        "occurrence_kind": "wire_field",
                        "interface_id": interface_id,
                        "interface_direction": interface_direction,
                        "payload_role": payload_role,
                        "operation": operation,
                        "wire_field_path": wire_path,
                        "wire_name": contract_item["wire_name"],
                        "attribute_name": contract_item["attribute_name"],
                        "attribute_path": contract_item["attribute_path"],
                        "attribute_type": contract_item["attribute_type"],
                        "source_schema": contract_item["source_schema"],
                        "payload_type": payload_type,
                        "protocol": "http",
                        "http_method": http_method,
                        "endpoint": endpoint,
                        "contract_item": contract_item["raw"],
                        "reconstructed": bool(contract_item.get("reconstructed")),
                    }
                    node_meta[wire_key] = ("wire_field", wire_payload)
                    normalized_payload = {
                        "schema_version": VALUE_FLOW_SCHEMA_VERSION,
                        "value_node_id": value_node_id,
                        "repo_id": repo_id,
                        "occurrence_id": wire_occurrence_id,
                        "node_kind": "wire_field",
                        "operation": operation,
                        "owner_ref": interface_id,
                        "display_ref": display_ref,
                        "type_ref": contract_item["attribute_type"] or payload_type,
                        "wire_path": wire_path,
                        "transport": {
                            "protocol": "http",
                            "interface_id": interface_id,
                            "interface_direction": interface_direction,
                            "payload_role": payload_role,
                            "http_method": http_method,
                            "endpoint": endpoint,
                        },
                        "contract_field": contract_item["raw"],
                        "provenance": provenance,
                    }
                    node_rows.append(
                        (
                            value_node_id,
                            scope_id,
                            repo_id,
                            wire_occurrence_id,
                            "wire_field",
                            operation,
                            interface_id,
                            display_ref,
                            contract_item["attribute_type"] or payload_type,
                            wire_path,
                            None,
                            canonical_json(provenance),
                            canonical_json(normalized_payload),
                        )
                    )

                field_contract = _mapping(contract_item.get("field_contract"))
                explicit_occurrence_id = str(field_contract.get("local_occurrence_id") or "").strip()
                explicit_occurrence = occurrence_by_repo.get(repo_id, {}).get(explicit_occurrence_id)
                if explicit_occurrence_id and explicit_occurrence is not None:
                    local_match = (
                        explicit_occurrence_id,
                        explicit_occurrence[0],
                        explicit_occurrence[1],
                        100,
                    )
                else:
                    local_match = _unique_boundary_occurrence(
                        occurrence_by_repo.get(repo_id, {}),
                        operation=operation,
                        interface_direction=interface_direction,
                        payload_role=payload_role,
                        wire_path=wire_path,
                    )
                wire_bindings.append(
                    {
                        "repo_id": repo_id,
                        "interface_record_id": interface_record_id,
                        "interface_id": interface_id,
                        "interface_direction": interface_direction,
                        "operation": operation,
                        "payload_role": payload_role,
                        "payload_type": payload_type,
                        "wire_path": wire_path,
                        "wire_occurrence_id": wire_occurrence_id,
                        "flow_kind": flow_kind,
                        "local_direction": local_direction,
                        "contract_item": contract_item,
                        "field_contract": field_contract,
                        "reconstructed": bool(contract_item.get("reconstructed")),
                        "local_match": local_match,
                        "member_interface_ids": tuple(
                            str(value).strip()
                            for value in (interface_payload.get("observed_interface_ids") or ())
                            if str(value).strip()
                        ) if bool(interface_payload.get("klc_composed_boundary")) else (),
                        "boundary_composition_basis": str(
                            interface_payload.get("boundary_composition_basis") or ""
                        ).strip() or None,
                        "composition_confidence": _confidence(interface_payload),
                    }
                )

    edge_rows: list[tuple[Any, ...]] = []
    for record_id, repo_id, payload, edge_id, source_occurrence_id, target_occurrence_id, edge_kind in edge_candidates:
        source_value_node_id = node_id_by_occurrence[(repo_id, source_occurrence_id)]
        target_value_node_id = node_id_by_occurrence[(repo_id, target_occurrence_id)]
        source_node_kind, source_payload = node_meta[(repo_id, source_occurrence_id)]
        target_node_kind, target_payload = node_meta[(repo_id, target_occurrence_id)]

        target_derivation = derivations.get((repo_id, target_occurrence_id))
        source_derivation = derivations.get((repo_id, source_occurrence_id))
        derivation = None
        if target_derivation and (
            source_occurrence_id in target_derivation["contributor_ids"]
            or edge_kind.casefold() in _DERIVATION_INPUT_EDGE_KINDS
            or edge_kind.casefold() == "invocation_argument"
        ):
            derivation = target_derivation
        elif source_derivation:
            derivation = source_derivation
        elif str(payload.get("derivation_id") or "").strip():
            derivation = {
                "derivation_id": str(payload.get("derivation_id")).strip(),
                "derivation_kind": str(payload.get("derivation_kind") or "derived").strip().casefold(),
                "derivation_source_count": int(payload.get("derivation_source_count") or 1),
                "classification_basis": "edge_metadata:derivation_id",
            }

        transformation_kind, transformation_basis = _classify_transformation(
            edge_kind=edge_kind,
            edge_payload=payload,
            source_payload=source_payload,
            target_payload=target_payload,
            derivation_kind=str(derivation.get("derivation_kind")) if derivation else None,
        )
        source_name = _terminal_name(source_payload, node_kind=source_node_kind)
        target_name = _terminal_name(target_payload, node_kind=target_node_kind)
        if source_name and target_name:
            naming_relation = "same_name" if source_name == target_name else "renamed"
        else:
            naming_relation = "not_applicable"
        flow_kind = _flow_kind(edge_kind)
        value_preservation = _value_preservation(transformation_kind)
        confidence = _confidence(payload)
        value_flow_edge_id = stable_id("repository_value_flow_edge", scope_id, repo_id, edge_id)
        guards = list(payload.get("guards") or [])
        provenance = {
            "field_flow_edge_record_id": record_id,
            "source_field_occurrence_record_id": occurrence_by_repo[repo_id][source_occurrence_id][0],
            "target_field_occurrence_record_id": occurrence_by_repo[repo_id][target_occurrence_id][0],
            "artifact_name": "catalog/field_flow_edges.json",
            "relative_file": str(payload.get("relative_file") or payload.get("file") or "").replace("\\", "/") or None,
        }
        derivation_id = str(derivation.get("derivation_id") or "").strip() if derivation else ""
        derivation_kind = str(derivation.get("derivation_kind") or "").strip() if derivation else ""
        derivation_source_count = int(derivation.get("derivation_source_count") or 0) if derivation else 0
        normalized_payload = {
            "schema_version": VALUE_FLOW_SCHEMA_VERSION,
            "value_flow_edge_id": value_flow_edge_id,
            "source_repo_id": repo_id,
            "target_repo_id": repo_id,
            "source_value_node_id": source_value_node_id,
            "target_value_node_id": target_value_node_id,
            "source_occurrence_id": source_occurrence_id,
            "target_occurrence_id": target_occurrence_id,
            "flow_kind": flow_kind,
            "source_edge_kind": edge_kind,
            "transformation_kind": transformation_kind,
            "transformation_basis": transformation_basis,
            "naming_relation": naming_relation,
            "value_preservation": value_preservation,
            "confidence": confidence,
            "derivation_id": derivation_id or None,
            "derivation_kind": derivation_kind or None,
            "derivation_source_count": derivation_source_count,
            "derivation_classification_basis": derivation.get("classification_basis") if derivation else None,
            "guards": guards,
            "source_edge": payload,
            "provenance": provenance,
        }
        edge_rows.append(
            (
                value_flow_edge_id,
                scope_id,
                repo_id,
                repo_id,
                source_value_node_id,
                target_value_node_id,
                source_occurrence_id,
                target_occurrence_id,
                flow_kind,
                edge_kind,
                transformation_kind,
                naming_relation,
                value_preservation,
                confidence,
                derivation_id or None,
                derivation_kind or None,
                derivation_source_count,
                canonical_json(guards),
                canonical_json(provenance),
                canonical_json(normalized_payload),
            )
        )

    seen_wire_edges: set[tuple[str, str, str, str]] = set()
    for binding in wire_bindings:
        local_match = binding["local_match"]
        if local_match is None:
            continue
        local_occurrence_id, local_record_id, local_payload, match_score = local_match
        repo_id = str(binding["repo_id"])
        wire_occurrence_id = str(binding["wire_occurrence_id"])
        if binding["local_direction"] == "local_to_wire":
            source_occurrence_id = local_occurrence_id
            target_occurrence_id = wire_occurrence_id
        else:
            source_occurrence_id = wire_occurrence_id
            target_occurrence_id = local_occurrence_id
        dedupe_key = (
            repo_id,
            str(binding["interface_id"]),
            str(binding["payload_role"]),
            str(binding["wire_path"]),
        )
        if dedupe_key in seen_wire_edges:
            continue
        seen_wire_edges.add(dedupe_key)

        source_value_node_id = node_id_by_occurrence[(repo_id, source_occurrence_id)]
        target_value_node_id = node_id_by_occurrence[(repo_id, target_occurrence_id)]
        source_node_kind, source_payload = node_meta[(repo_id, source_occurrence_id)]
        target_node_kind, target_payload = node_meta[(repo_id, target_occurrence_id)]
        source_name = _terminal_name(source_payload, node_kind=source_node_kind)
        target_name = _terminal_name(target_payload, node_kind=target_node_kind)
        naming_relation = (
            "same_name" if source_name and target_name and source_name == target_name
            else "renamed" if source_name and target_name
            else "not_applicable"
        )
        flow_kind = str(binding["flow_kind"])
        source_edge_kind = f"http_{binding['payload_role']}_{flow_kind}"
        source_edge_id = stable_id(
            "repository_wire_value_flow_source",
            scope_id,
            repo_id,
            binding["interface_id"],
            binding["payload_role"],
            binding["wire_path"],
            local_occurrence_id,
        )
        value_flow_edge_id = stable_id(
            "repository_value_flow_edge",
            scope_id,
            repo_id,
            source_edge_id,
        )
        reconstructed = bool(binding.get("reconstructed"))
        field_contract = _mapping(binding.get("field_contract"))
        local_confidence = "probable" if reconstructed else "confirmed"
        provenance = {
            "system_interface_record_id": binding["interface_record_id"],
            "field_occurrence_record_id": local_record_id,
            "artifact_names": [
                "system_interface_catalog.json",
                "catalog/field_occurrences.json",
            ],
            "interface_id": binding["interface_id"],
            "match_basis": "unique_operation_wire_path_boundary_occurrence",
            "match_score": match_score,
            "contract_evidence_refs": binding["contract_item"]["evidence_refs"],
            "reconstructed_wire_path": reconstructed,
            "field_contract_id": field_contract.get("field_contract_id"),
        }
        normalized_payload = {
            "schema_version": VALUE_FLOW_SCHEMA_VERSION,
            "value_flow_edge_id": value_flow_edge_id,
            "source_repo_id": repo_id,
            "target_repo_id": repo_id,
            "source_value_node_id": source_value_node_id,
            "target_value_node_id": target_value_node_id,
            "source_occurrence_id": source_occurrence_id,
            "target_occurrence_id": target_occurrence_id,
            "flow_kind": flow_kind,
            "source_edge_kind": source_edge_kind,
            "transformation_kind": "identity",
            "transformation_basis": "exact_local_wire_contract_binding",
            "naming_relation": naming_relation,
            "value_preservation": "preserved",
            "confidence": local_confidence,
            "derivation_id": None,
            "derivation_kind": None,
            "derivation_source_count": 0,
            "guards": [],
            "transport": {
                "protocol": "http",
                "interface_id": binding["interface_id"],
                "interface_direction": binding["interface_direction"],
                "payload_role": binding["payload_role"],
                "wire_path": binding["wire_path"],
                "payload_type": binding["payload_type"],
            },
            "contract_field": binding["contract_item"]["raw"],
            "provenance": provenance,
        }
        edge_rows.append(
            (
                value_flow_edge_id,
                scope_id,
                repo_id,
                repo_id,
                source_value_node_id,
                target_value_node_id,
                source_occurrence_id,
                target_occurrence_id,
                flow_kind,
                source_edge_kind,
                "identity",
                naming_relation,
                "preserved",
                local_confidence,
                None,
                None,
                0,
                canonical_json([]),
                canonical_json(provenance),
                canonical_json(normalized_payload),
            )
        )

    seen_composition_edges: set[tuple[str, str, str, str, str]] = set()
    for binding in wire_bindings:
        member_interface_ids = tuple(binding.get("member_interface_ids") or ())
        if not member_interface_ids:
            continue
        repo_id = str(binding["repo_id"])
        composed_interface_id = str(binding["interface_id"])
        payload_role = str(binding["payload_role"])
        wire_path = str(binding["wire_path"])
        composed_occurrence_id = str(binding["wire_occurrence_id"])
        composition_basis = str(
            binding.get("boundary_composition_basis") or "observed_member_interfaces"
        )
        composition_confidence = str(binding.get("composition_confidence") or "confirmed")
        for member_interface_id in sorted(set(member_interface_ids)):
            member_occurrence_id = wire_occurrence_by_key.get(
                (repo_id, member_interface_id, payload_role, wire_path)
            )
            if not member_occurrence_id or member_occurrence_id == composed_occurrence_id:
                continue
            dedupe_key = (
                repo_id, composed_interface_id, member_interface_id, payload_role, wire_path
            )
            if dedupe_key in seen_composition_edges:
                continue
            seen_composition_edges.add(dedupe_key)

            if payload_role == "request":
                source_occurrence_id = member_occurrence_id
                target_occurrence_id = composed_occurrence_id
            else:
                source_occurrence_id = composed_occurrence_id
                target_occurrence_id = member_occurrence_id
            source_value_node_id = node_id_by_occurrence[(repo_id, source_occurrence_id)]
            target_value_node_id = node_id_by_occurrence[(repo_id, target_occurrence_id)]
            value_flow_edge_id = stable_id(
                "repository_value_flow_edge",
                scope_id,
                repo_id,
                "composed_boundary_member",
                composed_interface_id,
                member_interface_id,
                payload_role,
                wire_path,
            )
            source_edge_kind = f"http_{payload_role}_composed_boundary_member"
            provenance = {
                "composed_interface_record_id": binding["interface_record_id"],
                "composed_interface_id": composed_interface_id,
                "member_interface_id": member_interface_id,
                "match_basis": "observed_interface_member_of_composed_boundary",
                "boundary_composition_basis": composition_basis,
            }
            normalized_payload = {
                "schema_version": VALUE_FLOW_SCHEMA_VERSION,
                "value_flow_edge_id": value_flow_edge_id,
                "source_repo_id": repo_id,
                "target_repo_id": repo_id,
                "source_value_node_id": source_value_node_id,
                "target_value_node_id": target_value_node_id,
                "source_occurrence_id": source_occurrence_id,
                "target_occurrence_id": target_occurrence_id,
                "flow_kind": "boundary_composition",
                "source_edge_kind": source_edge_kind,
                "transformation_kind": "identity",
                "transformation_basis": "shared_composed_http_boundary",
                "naming_relation": "same_name",
                "value_preservation": "preserved",
                "confidence": composition_confidence,
                "derivation_id": None,
                "derivation_kind": None,
                "derivation_source_count": 0,
                "guards": [],
                "boundary_composition": {
                    "composed_interface_id": composed_interface_id,
                    "member_interface_id": member_interface_id,
                    "payload_role": payload_role,
                    "wire_path": wire_path,
                    "basis": composition_basis,
                },
                "provenance": provenance,
            }
            edge_rows.append(
                (
                    value_flow_edge_id,
                    scope_id,
                    repo_id,
                    repo_id,
                    source_value_node_id,
                    target_value_node_id,
                    source_occurrence_id,
                    target_occurrence_id,
                    "boundary_composition",
                    source_edge_kind,
                    "identity",
                    "same_name",
                    "preserved",
                    composition_confidence,
                    None,
                    None,
                    0,
                    canonical_json([]),
                    canonical_json(provenance),
                    canonical_json(normalized_payload),
                )
            )

    seen_transport_edges: set[tuple[str, str, str]] = set()
    boundary_rows = []
    if _has_relation(connection, "system_boundary_interaction"):
        boundary_rows = connection.execute(
        """SELECT boundary_interaction_id, source_repo_id, outbound_interface_id,
                  target_repo_id, target_ingress_interface_id, confidence,
                  provenance_json, payload_json
           FROM system_boundary_interaction
           WHERE scope_id=? AND protocol='http' AND match_status='matched' AND confidence IN ('confirmed', 'probable')
           ORDER BY boundary_interaction_id""",
        [scope_id],
        ).fetchall()
    for (
        boundary_interaction_id,
        source_repo_id,
        outbound_interface_id,
        target_repo_id,
        target_ingress_interface_id,
        boundary_confidence,
        boundary_provenance_raw,
        boundary_payload_raw,
    ) in boundary_rows:
        boundary_payload = _mapping(boundary_payload_raw)
        outbound_interface = _mapping(boundary_payload.get("outbound_interface"))
        target_interface = _mapping(boundary_payload.get("target_ingress_interface"))
        boundary_provenance = _mapping(boundary_provenance_raw)
        directions = (
            (
                "request",
                str(source_repo_id),
                str(outbound_interface_id),
                outbound_interface,
                str(target_repo_id),
                str(target_ingress_interface_id),
                target_interface,
            ),
            (
                "response",
                str(target_repo_id),
                str(target_ingress_interface_id),
                target_interface,
                str(source_repo_id),
                str(outbound_interface_id),
                outbound_interface,
            ),
        )
        for (
            payload_role,
            edge_source_repo_id,
            edge_source_interface_id,
            edge_source_interface,
            edge_target_repo_id,
            edge_target_interface_id,
            edge_target_interface,
        ) in directions:
            contract_key = f"{payload_role}_contract_signature"
            source_items = _unique_contract_items(edge_source_interface, contract_key)
            target_items = _unique_contract_items(edge_target_interface, contract_key)
            if payload_role == "request":
                for wire_path, contract in field_contracts_by_boundary.get(
                    str(boundary_interaction_id), {}
                ).items():
                    if wire_path in source_items:
                        continue
                    source_field = _mapping(contract.get("source_field"))
                    source_items[wire_path] = {
                        "ordinal": -1,
                        "wire_path": wire_path,
                        "wire_name": str(source_field.get("wire_name") or wire_path.rsplit(".", 1)[-1]),
                        "attribute_name": str(source_field.get("attribute_name") or wire_path.rsplit(".", 1)[-1]),
                        "attribute_path": str(
                            source_field.get("attribute_path")
                            or contract.get("outbound_field_path")
                            or wire_path
                        ),
                        "attribute_type": str(source_field.get("attribute_type") or "").strip() or None,
                        "source_schema": str(source_field.get("source_schema") or "").strip() or None,
                        "evidence_refs": [],
                        "raw": {
                            **source_field,
                            "wire_field_path": wire_path,
                            "reconstructed": str(contract.get("match_kind")) != "exact_wire_path",
                            "field_contract_id": contract["field_contract_id"],
                            "match_kind": contract["match_kind"],
                            "match_status": contract["match_status"],
                        },
                        "reconstructed": str(contract.get("match_kind")) != "exact_wire_path",
                        "field_contract": contract,
                    }
            matched_wire_paths = sorted(set(source_items).intersection(target_items))
            for wire_path in matched_wire_paths:
                source_occurrence_id = wire_occurrence_by_key.get(
                    (edge_source_repo_id, edge_source_interface_id, payload_role, wire_path)
                )
                target_occurrence_id = wire_occurrence_by_key.get(
                    (edge_target_repo_id, edge_target_interface_id, payload_role, wire_path)
                )
                if not source_occurrence_id or not target_occurrence_id:
                    continue
                dedupe_key = (str(boundary_interaction_id), payload_role, wire_path)
                if dedupe_key in seen_transport_edges:
                    continue
                seen_transport_edges.add(dedupe_key)
                source_value_node_id = node_id_by_occurrence.get((edge_source_repo_id, source_occurrence_id))
                target_value_node_id = node_id_by_occurrence.get((edge_target_repo_id, target_occurrence_id))
                if not source_value_node_id or not target_value_node_id:
                    continue

                source_edge_kind = f"http_{payload_role}_transport"
                value_flow_edge_id = stable_id(
                    "repository_value_flow_edge",
                    scope_id,
                    str(boundary_interaction_id),
                    payload_role,
                    wire_path,
                )
                source_item = source_items[wire_path]
                target_item = target_items[wire_path]
                reconstructed_source = bool(source_item.get("reconstructed"))
                transport_confidence = (
                    "probable" if reconstructed_source else str(boundary_confidence)
                )
                evidence_packet = _transport_evidence_packet(
                    boundary_confidence=transport_confidence,
                    boundary_payload=boundary_payload,
                    payload_role=payload_role,
                    wire_path=wire_path,
                    source_item_count=len(source_items),
                    target_item_count=len(target_items),
                    matched_item_count=len(matched_wire_paths),
                )
                if reconstructed_source:
                    field_contract = _mapping(source_item.get("field_contract"))
                    evidence_packet = {
                        **evidence_packet,
                        "supporting_evidence": list(dict.fromkeys([
                            *evidence_packet["supporting_evidence"],
                            "nested_wire_path_reconstructed",
                        ])),
                        "limitations": list(dict.fromkeys([
                            *evidence_packet["limitations"],
                            "source_wire_contract_reconstructed",
                        ])),
                        "contract_reconstruction": {
                            "field_contract_id": field_contract.get("field_contract_id"),
                            "match_kind": field_contract.get("match_kind"),
                            "match_status": field_contract.get("match_status"),
                            "provenance": field_contract.get("provenance"),
                        },
                    }
                if evidence_packet["conflicting_evidence"]:
                    continue
                provenance = {
                    "boundary_interaction_id": str(boundary_interaction_id),
                    "boundary_confidence": str(boundary_confidence),
                    "boundary_provenance": boundary_provenance,
                    "source_interface_id": edge_source_interface_id,
                    "target_interface_id": edge_target_interface_id,
                    "source_contract_evidence_refs": source_item["evidence_refs"],
                    "target_contract_evidence_refs": target_item["evidence_refs"],
                    "match_basis": "exact_unique_normalized_wire_path_on_matched_boundary",
                    "evidence_packet": evidence_packet,
                    "contract_reconstruction": evidence_packet.get("contract_reconstruction"),
                }
                normalized_payload = {
                    "schema_version": VALUE_FLOW_SCHEMA_VERSION,
                    "value_flow_edge_id": value_flow_edge_id,
                    "source_repo_id": edge_source_repo_id,
                    "target_repo_id": edge_target_repo_id,
                    "source_value_node_id": source_value_node_id,
                    "target_value_node_id": target_value_node_id,
                    "source_occurrence_id": source_occurrence_id,
                    "target_occurrence_id": target_occurrence_id,
                    "flow_kind": "transport",
                    "source_edge_kind": source_edge_kind,
                    "transformation_kind": "identity",
                    "transformation_basis": "matched_http_boundary_exact_wire_path",
                    "naming_relation": "same_name",
                    "value_preservation": "preserved",
                    "confidence": transport_confidence,
                    "derivation_id": None,
                    "derivation_kind": None,
                    "derivation_source_count": 0,
                    "guards": [],
                    "transport": {
                        "protocol": "http",
                        "payload_role": payload_role,
                        "boundary_interaction_id": str(boundary_interaction_id),
                        "source_interface_id": edge_source_interface_id,
                        "target_interface_id": edge_target_interface_id,
                        "wire_path": wire_path,
                        "edge_status": evidence_packet["edge_status"],
                        "evidence_packet": evidence_packet,
                        "reconstructed_source_wire_path": reconstructed_source,
                    },
                    "source_contract_field": source_item["raw"],
                    "target_contract_field": target_item["raw"],
                    "provenance": provenance,
                }
                edge_rows.append(
                    (
                        value_flow_edge_id,
                        scope_id,
                        edge_source_repo_id,
                        edge_target_repo_id,
                        source_value_node_id,
                        target_value_node_id,
                        source_occurrence_id,
                        target_occurrence_id,
                        "transport",
                        source_edge_kind,
                        "identity",
                        "same_name",
                        "preserved",
                        transport_confidence,
                        None,
                        None,
                        0,
                        canonical_json([]),
                        canonical_json(provenance),
                        canonical_json(normalized_payload),
                    )
                )

    bulk_insert(
        connection,
        """INSERT INTO repository_value_node VALUES (
               ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
           )""",
        node_rows,
    )
    bulk_insert(
        connection,
        """INSERT INTO repository_value_flow_edge VALUES (
               ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
           )""",
        edge_rows,
    )
    return {
        "repository_value_node": len(node_rows),
        "repository_value_flow_edge": len(edge_rows),
    }
