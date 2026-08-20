from __future__ import annotations

import time
import re
import json
import hashlib
from datetime import datetime, timezone
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from code_analyzer_core.models import AnalysisResult
from code_analyzer_core.utils import write_json
from code_analyzer_core.evidence_kernel import sanitize_public_payload


ENTITY_KEYWORDS = (
    "profile", "client", "customer", "phone", "card", "device", "link",
    "registration", "subscription", "payment", "account", "ucp", "tariff",
    "push", "reissue", "block", "history", "info",
)
NOISE_KEYWORDS = (
    "test.", "test#", "maskutils", "serializer", "deserializer", "configurationcontroller",
    "reloadconfig", "reconfigure", "health", "actuator", "dictionarycontrollerimpl.dictionarycontrollerimpl",
)
STATUS_ONLY_SCHEMAS = {"boolean", "string", "void", "unknown", "responseentity<string>"}


def _write_compact_json(path: Path, obj: Any) -> None:
    """Write large addressable catalogs without presentation whitespace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(obj, ensure_ascii=False, separators=(",", ":"), default=str),
        encoding="utf-8",
    )


def _enum_value(v: Any) -> str:
    return getattr(v, "value", str(v))


def _first_loc(evidence: list[Any], *, include_snippet: bool = False, max_snippet_chars: int = 900) -> dict[str, Any] | None:
    if not evidence:
        return None
    ev = evidence[0]
    item: dict[str, Any] = {
        "file": ev.file_path,
        "line_start": ev.line_start,
        "line_end": ev.line_end,
        "extractor": ev.extractor,
    }
    if include_snippet:
        snippet = ev.snippet or ""
        item["snippet"] = snippet[:max_snippet_chars] + ("..." if len(snippet) > max_snippet_chars else "")
    return item


def _schema_brief(schema: Any, max_fields: int = 16, *, include_evidence: bool = True) -> dict[str, Any]:
    item: dict[str, Any] = {
        "name": schema.name,
        "source_type": schema.source_type,
        "fields": [
            {
                "name": f.name,
                "type": f.type,
                "nested_type": f.nested_type,
                "annotations": f.annotations,
                "serialized_name": getattr(f, "serialized_name", None),
                "serialized_name_basis": getattr(f, "serialized_name_basis", None),
                "serialization_library": getattr(f, "serialization_library", None),
                "serialization_aliases": getattr(f, "serialization_aliases", []),
            }
            for f in schema.fields[:max_fields]
        ],
        "field_count": len(schema.fields),
    }
    if include_evidence:
        item["evidence"] = [_first_loc(schema.evidence)] if schema.evidence else []
    return item


def _schema_first_pass_brief(schema: Any, max_fields: int = 8) -> dict[str, Any]:
    return {
        "name": schema.name,
        "source_type": schema.source_type,
        "field_count": len(schema.fields),
        "fields": [
            {"name": f.name, "type": f.type, "nested_type": f.nested_type}
            for f in schema.fields[:max_fields]
        ],
    }


def _is_test_or_noise(operation: str, items: list[dict[str, Any]]) -> bool:
    haystack = " ".join([
        operation,
        *[str(x.get("name") or "") for x in items],
        *[str(x.get("path") or "") for x in items],
        *[str((x.get("evidence") or [{}])[0].get("file") if x.get("evidence") else "") for x in items],
    ]).lower()
    if "/src/test/" in haystack or "src\\test" in haystack:
        return True
    return any(token in haystack for token in NOISE_KEYWORDS)


def _has_entity_signal(*values: Any) -> bool:
    haystack = " ".join(str(v or "") for v in values).lower()
    return any(token in haystack for token in ENTITY_KEYWORDS)


def _status_only_output(schemas: list[str]) -> bool:
    normalized = {str(s or "").strip().lower() for s in schemas}
    return bool(normalized) and normalized.issubset(STATUS_ONLY_SCHEMAS)


def _first_pass_observations(operation: dict[str, Any], items: list[dict[str, Any]]) -> list[str]:
    """Return directly observable first-pass signals without ranking or verdicts."""
    observations: list[str] = []
    directions = set(operation.get("directions") or [])
    kinds = set(operation.get("kinds") or [])
    schemas = operation.get("schemas") or []
    interface_names = operation.get("interface_names") or []

    if _is_test_or_noise(operation.get("operation", ""), items):
        observations.append("test_or_noise_token_observed")
    if "inbound" in directions and "outbound" in directions:
        observations.append("has_inbound_and_outbound_interfaces")
    elif "outbound" in directions:
        observations.append("has_outbound_interface")
    if "rest" in kinds:
        observations.append("rest_interface")
    if "kafka" in kinds:
        observations.append("kafka_interface")
    if _has_entity_signal(operation.get("operation"), schemas, interface_names):
        observations.append("entity_name_token_observed")

    propagation = []
    for item in items:
        props = item.get("properties") or {}
        propagation.extend(props.get("request_field_propagation") or [])
    if propagation:
        observations.append("request_field_propagation_observed")
    if _status_only_output([s for s in schemas if s]):
        observations.append("status_or_primitive_schema_only")
    return observations



def _interface_properties_brief(props: dict[str, Any] | None) -> dict[str, Any]:
    props = props or {}
    out: dict[str, Any] = {}
    for key in [
        "method_line_start", "method_line_end", "class_path", "method_path", "full_path_basis",
        "boundary_role", "source_set", "is_test_source", "payload_expression", "message_key_expression",
        "topic_expression", "topic_property_key", "topic_settings_symbol", "consumer_props_symbol", "topic_resolution_basis",
        "client_receiver", "client_receiver_type", "client_call_pattern",
        "endpoint_expression", "endpoint_path", "endpoint_path_resolution_basis", "endpoint_path_symbol",
        "base_config_prefixes", "base_url_property_key", "base_url_resolution_status",
        "request_payload_expression", "request_payload_type", "request_payload_resolution_basis",
        "response_payload_type", "composition_basis", "helper_operation", "scenario_operation",
        "client_bean_name", "endpoint_path_property_key", "endpoint_path_observed_values", "endpoint_path_variants",
        "base_url_property_keys", "base_url_observed_values", "endpoint_url_variants",
        "framework", "annotation", "method_path_expression", "method_path_variants", "method_path_resolution_basis",
        "registration_base_path_variants", "full_path_variants", "registration_records",
        "local_caller_operations", "local_call_chain_candidates", "request_observed_builder_setters",
        "response_payload_candidates", "response_payload_candidate_basis",
    ]:
        if key in props:
            out[key] = props[key]
    rfp = props.get("request_field_propagation") or []
    if isinstance(rfp, list):
        out["request_field_propagation"] = [str(x)[:300] for x in rfp[:8]]
    req_params = props.get("request_parameters") or []
    if isinstance(req_params, list):
        out["request_parameters"] = [x for x in req_params[:16] if isinstance(x, dict)]
    if isinstance(props.get("request_body_parameter"), dict):
        out["request_body_parameter"] = props.get("request_body_parameter")
    return out



def _source_set_from_file_path(path: str | None) -> str:
    normalized = str(path or "").replace('\\', '/')
    if '/src/test/' in normalized or normalized.endswith('/src/test'):
        return 'test'
    return 'main'


def _interface_source_set(item: dict[str, Any]) -> str:
    props = item.get("properties") or {}
    if props.get("source_set"):
        return str(props.get("source_set"))
    ev = item.get("evidence") or []
    file_path = (ev[0] or {}).get("file") if ev else None
    return _source_set_from_file_path(file_path)


def _schema_attributes(schema_by_name: dict[str, Any], schema_ref: str | None, *, source: str = "java_schema", max_fields: int = 128) -> list[dict[str, Any]]:
    if not schema_ref:
        return []
    schema = schema_by_name.get(schema_ref)
    if not schema:
        return []
    out: list[dict[str, Any]] = []
    actual_source = "openapi_schema" if getattr(schema, "source_type", None) == "openapi_schema" else source
    for f in schema.fields[:max_fields]:
        wire_name = getattr(f, "serialized_name", None) or f.name
        out.append({
            "attribute_name": wire_name,
            "attribute_type": f.type,
            "attribute_path": wire_name,
            "java_attribute_name": f.name,
            "wire_name": wire_name,
            "serialized_name_basis": getattr(f, "serialized_name_basis", None),
            "serialization_library": getattr(f, "serialization_library", None),
            "serialization_aliases": getattr(f, "serialization_aliases", []),
            "nested_type": f.nested_type,
            "description": f.description,
            "source": actual_source,
            "annotations": f.annotations,
            "evidence_refs": [_first_loc([ev]) for ev in getattr(f, "evidence", [])],
        })
    return out


def _schema_name_candidates(schema_ref: str | None) -> list[str]:
    if not schema_ref:
        return []
    text = str(schema_ref).strip()
    out = [text]
    # Generic wrappers and containers are navigation noise; expose both the
    # declared type and nested DTO candidates without assigning semantics.
    for token in re.findall(r"[A-Z][A-Za-z0-9_.$]*", text):
        simple = token.split(".")[-1]
        if simple not in out and simple not in {"ResponseEntity", "HttpEntity", "Optional", "List", "Set", "Collection", "Map", "CompletableFuture", "ParameterizedTypeReference"}:
            out.append(simple)
    return out


def _schema_contract_signature(
    schema_by_name: dict[str, Any],
    schema_ref: str | None,
    *,
    max_depth: int = 3,
    max_fields: int = 160,
) -> list[dict[str, Any]]:
    roots = [name for name in _schema_name_candidates(schema_ref) if name in schema_by_name]
    if not roots:
        return []
    out: list[dict[str, Any]] = []
    visited_edges: set[tuple[str, str]] = set()

    def walk(schema_name: str, prefix: str, depth: int) -> None:
        if depth > max_depth or len(out) >= max_fields:
            return
        schema = schema_by_name.get(schema_name)
        if not schema:
            return
        for field in schema.fields:
            if len(out) >= max_fields:
                return
            # Generated Java API constants are class metadata, not serialized payload fields.
            if str(field.name).startswith("SERIALIZED_NAME_") or (str(field.name).isupper() and "_" in str(field.name)):
                continue
            wire_name = getattr(field, "serialized_name", None) or field.name
            path = f"{prefix}.{wire_name}" if prefix else wire_name
            item = {
                "attribute_path": path,
                "attribute_name": wire_name,
                "java_attribute_name": field.name,
                "wire_name": wire_name,
                "attribute_type": field.type,
                "nested_type": field.nested_type,
                "required": any(str(a).endswith(("NotNull", "NotBlank", "NotEmpty")) for a in (field.annotations or [])),
                "source_schema": schema_name,
                "serialized_name_basis": getattr(field, "serialized_name_basis", None),
                "serialization_library": getattr(field, "serialization_library", None),
                "serialization_aliases": getattr(field, "serialization_aliases", []),
                "evidence_refs": [_first_loc([ev]) for ev in getattr(field, "evidence", [])],
            }
            out.append(item)
            nested_candidates = _schema_name_candidates(field.nested_type or field.type)
            for nested in nested_candidates:
                edge = (schema_name, nested)
                if nested in schema_by_name and edge not in visited_edges and nested != schema_name:
                    visited_edges.add(edge)
                    walk(nested, path, depth + 1)
                    break

    for root in roots:
        walk(root, "", 0)
        if out:
            break
    return out


def _observed_builder_signature(setters: list[Any] | None) -> list[dict[str, Any]]:
    return [
        {
            "attribute_path": str(name),
            "attribute_name": str(name),
            "attribute_type": None,
            "nested_type": None,
            "required": None,
            "source_schema": None,
            "source": "observed_builder_setter",
        }
        for name in (setters or [])
        if str(name).strip()
    ]


def _rest_parameter_attributes(props: dict[str, Any] | None) -> list[dict[str, Any]]:
    props = props or {}
    out: list[dict[str, Any]] = []
    for param in props.get("request_parameters") or []:
        if not isinstance(param, dict):
            continue
        out.append({
            "attribute_name": param.get("name"),
            "attribute_type": param.get("java_type"),
            "attribute_path": param.get("name"),
            "source": param.get("source"),
            "java_parameter": param.get("java_parameter"),
            "required": param.get("required"),
            "default_value": param.get("default_value"),
        })
    return out


def _interface_boundary_kind(item: dict[str, Any]) -> str:
    props = item.get("properties") or {}
    role = props.get("boundary_role")
    if role:
        return str(role)
    kind = str(item.get("kind") or "unknown")
    direction = str(item.get("direction") or "unknown")
    if kind == "rest" and direction == "inbound":
        return "rest_request"
    if kind == "rest" and direction == "outbound":
        return "rest_response"
    if kind == "kafka" and direction == "inbound":
        return "kafka_consume"
    if kind == "kafka" and direction == "outbound":
        return "kafka_publish"
    return f"{kind}_{direction}"


def _config_observed_values(config_values: dict[str, Any], key: Any) -> list[Any]:
    if key is None:
        return []
    raw = config_values.get(str(key))
    values = raw if isinstance(raw, list) else [raw]
    out: list[Any] = []
    for value in values:
        if value is None or value in out:
            continue
        out.append(value)
    return out


def _merge_observed_values(*values: Any) -> list[Any]:
    out: list[Any] = []
    for raw in values:
        rows = raw if isinstance(raw, list) else [raw]
        for value in rows:
            if value is None or value == "" or value in out:
                continue
            out.append(value)
    return out


def _contract_field_bindings(
    signature: list[dict[str, Any]],
    *,
    payload_type: str | None,
    binding_kind: str,
    payload_role: str,
    framework: str | None,
) -> list[dict[str, Any]]:
    """Project schema fields into boundary-specific wire bindings.

    The entries describe observed payload typing and Java/wire-name metadata.
    They do not classify whether another system uses the same semantics.
    """
    out: list[dict[str, Any]] = []
    for field in signature:
        wire_path = str(field.get("attribute_path") or "").strip()
        if not wire_path:
            continue
        java_name = str(field.get("java_attribute_name") or field.get("attribute_name") or "").strip()
        out.append({
            "payload_type": payload_type,
            "payload_role": payload_role,
            "binding_kind": binding_kind,
            "java_field_name": java_name or None,
            "wire_field_path": wire_path,
            "wire_field_name": field.get("wire_name") or field.get("attribute_name"),
            "data_type": field.get("attribute_type"),
            "source_schema": field.get("source_schema"),
            "serialized_name_basis": field.get("serialized_name_basis"),
            "serialization_library": field.get("serialization_library"),
            "serialization_aliases": field.get("serialization_aliases") or [],
            "framework": framework,
            "evidence_refs": field.get("evidence_refs") or [],
        })
    return out


def _system_interface_catalog_item(item: dict[str, Any], schema_by_name: dict[str, Any], config_values: dict[str, Any] | None = None) -> dict[str, Any]:
    props = item.get("properties") or {}
    config_values = config_values or {}
    boundary_kind = _interface_boundary_kind(item)
    path_property_key = props.get("endpoint_path_property_key")
    path_observed_values = _merge_observed_values(
        props.get("endpoint_path_observed_values"),
        props.get("endpoint_path_variants"),
        _config_observed_values(config_values, path_property_key),
    )
    base_url_property_keys = _merge_observed_values(
        props.get("base_url_property_keys"),
        props.get("base_url_property_key"),
    )
    base_url_observed_values = _merge_observed_values(
        props.get("base_url_observed_values"),
        *[_config_observed_values(config_values, key) for key in base_url_property_keys],
    )
    endpoint_url_variants = _merge_observed_values(
        props.get("endpoint_url_variants"),
        [str(base).rstrip("/") + "/" + str(path).lstrip("/") for base in base_url_observed_values for path in path_observed_values],
    )
    source_set = _interface_source_set(item)
    schema_ref = item.get("schema_ref")
    attr_source = "java_dto" if schema_ref and schema_ref != "method_parameters" else "method_parameter"
    attributes = _schema_attributes(schema_by_name, schema_ref, source=attr_source)
    if boundary_kind == "rest_request":
        attributes = _rest_parameter_attributes(props) + attributes
    missing_links: list[str] = []

    raw_endpoint = item.get("path") if item.get("kind") == "rest" else item.get("name")
    resolved_endpoint = raw_endpoint
    resolution_status = "resolved" if raw_endpoint else "unresolved"
    endpoint_property_key = None
    endpoint_property_value = None

    if item.get("kind") == "kafka":
        endpoint_property_key = props.get("topic_property_key")
        if endpoint_property_key:
            endpoint_property_values = _config_observed_values(config_values, endpoint_property_key)
            endpoint_property_value = endpoint_property_values[0] if len(endpoint_property_values) == 1 else None
            if endpoint_property_value is not None:
                resolved_endpoint = endpoint_property_value
                resolution_status = "resolved_config_value"
            elif len(endpoint_property_values) > 1:
                resolved_endpoint = endpoint_property_key
                resolution_status = "ambiguous_config_values"
                missing_links.append("kafka_topic_config_value_ambiguous")
            else:
                resolved_endpoint = endpoint_property_key
                resolution_status = "resolved_property_key"
        elif not item.get("name"):
            missing_links.append("kafka_topic_not_resolved")
        elif str(item.get("name") or "").strip().startswith("#{") or str(item.get("name") or "").strip() in {"topic", "unknown"}:
            missing_links.append("kafka_topic_property_key_not_resolved")
    elif boundary_kind == "http_outbound":
        endpoint_property_key = props.get("base_url_property_key")
        endpoint_property_values = _config_observed_values(config_values, endpoint_property_key) if endpoint_property_key else []
        endpoint_property_value = endpoint_property_values[0] if len(endpoint_property_values) == 1 else None
        endpoint_path = props.get("endpoint_path") or (path_observed_values[0] if len(path_observed_values) == 1 else None) or item.get("path")
        if endpoint_property_value is not None and endpoint_path:
            resolved_endpoint = str(endpoint_property_value).rstrip("/") + "/" + str(endpoint_path).lstrip("/")
            resolution_status = "resolved_config_value_and_endpoint_path"
        elif endpoint_property_key and endpoint_path:
            resolved_endpoint = f"{endpoint_property_key} + {endpoint_path}"
            resolution_status = "resolved_property_key_and_endpoint_path"
        elif endpoint_path:
            resolved_endpoint = endpoint_path
            resolution_status = "resolved_endpoint_path_only"
        else:
            resolution_status = "unresolved"
        if props.get("base_url_resolution_status") == "ambiguous_multiple_bean_configuration_properties":
            missing_links.append("http_client_base_config_ambiguous")
        elif not endpoint_property_key:
            missing_links.append("http_client_base_config_not_resolved")
    elif not item.get("path") and item.get("kind") == "rest":
        missing_links.append("rest_path_not_resolved")

    if not attributes and schema_ref not in {None, "void", "unknown", "String", "Boolean", "method_parameters"}:
        missing_links.append("payload_attributes_not_resolved")
    protocol = "http" if boundary_kind == "http_outbound" else item.get("kind")
    request_payload_type = props.get("request_payload_type") if boundary_kind == "http_outbound" else (schema_ref if boundary_kind in {"rest_request", "grpc_request", "framework_callback_request"} else None)
    response_payload_type = props.get("response_payload_type") if boundary_kind == "http_outbound" else (schema_ref if boundary_kind in {"rest_response", "grpc_response", "framework_callback_response"} else None)
    request_signature = _schema_contract_signature(schema_by_name, request_payload_type) or _observed_builder_signature(props.get("request_observed_builder_setters") if boundary_kind == "http_outbound" else None)
    response_signature = _schema_contract_signature(schema_by_name, response_payload_type)
    framework = props.get("framework")
    request_binding_kind = None
    response_binding_kind = None
    if boundary_kind == "http_outbound":
        request_binding_kind = "rest_request_serialization_field"
        response_binding_kind = "rest_response_deserialization_field"
    elif boundary_kind == "rest_request":
        request_binding_kind = "rest_request_deserialization_field"
    elif boundary_kind == "rest_response":
        response_binding_kind = "rest_response_serialization_field"
    elif boundary_kind == "kafka_publish":
        request_binding_kind = "kafka_payload_serialization_field"
    elif boundary_kind == "kafka_consume":
        request_binding_kind = "kafka_payload_deserialization_field"
    elif boundary_kind == "grpc_request":
        request_binding_kind = "grpc_request_deserialization_field"
    elif boundary_kind == "grpc_response":
        response_binding_kind = "grpc_response_serialization_field"
    elif boundary_kind == "framework_callback_request":
        request_binding_kind = "callback_request_deserialization_field"
    elif boundary_kind == "framework_callback_response":
        response_binding_kind = "callback_response_serialization_field"
    request_field_bindings = _contract_field_bindings(
        request_signature, payload_type=request_payload_type, binding_kind=request_binding_kind,
        payload_role=(
            "request"
            if boundary_kind in {"http_outbound", "rest_request", "grpc_request", "framework_callback_request"}
            else "message"
        ),
        framework=framework,
    ) if request_binding_kind else []
    response_field_bindings = _contract_field_bindings(
        response_signature, payload_type=response_payload_type, binding_kind=response_binding_kind,
        payload_role="response", framework=framework,
    ) if response_binding_kind else []
    return {
        "interface_id": item.get("id"),
        "direction": item.get("direction"),
        "boundary_kind": boundary_kind,
        "protocol": protocol,
        "operation": item.get("operation"),
        "endpoint_or_topic_raw": raw_endpoint,
        "endpoint_or_topic_resolved": resolved_endpoint,
        "endpoint_or_topic_property_key": endpoint_property_key,
        "endpoint_or_topic_property_value": endpoint_property_value,
        "endpoint_or_topic_observed_values": _config_observed_values(config_values, endpoint_property_key),
        "endpoint_path_property_key": path_property_key,
        "endpoint_path_observed_values": path_observed_values,
        "endpoint_path_variants": path_observed_values,
        "base_url_property_keys": base_url_property_keys,
        "base_url_observed_values": base_url_observed_values,
        "endpoint_url_variants": endpoint_url_variants,
        "method_path_variants": props.get("method_path_variants") or [],
        "registration_base_path_variants": props.get("registration_base_path_variants") or [],
        "full_path_variants": props.get("full_path_variants") or [],
        "resolution_status": resolution_status,
        "http_method": item.get("method"),
        "payload_schema_ref": schema_ref,
        "request_payload_type": request_payload_type,
        "response_payload_type": response_payload_type,
        "message_payload_type": schema_ref if item.get("kind") in {"kafka", "grpc", "callback"} else None,
        "message_key_expression": props.get("message_key_expression"),
        "message_payload_expression": props.get("payload_expression"),
        "request_contract_signature": request_signature,
        "response_contract_signature": response_signature,
        "request_field_bindings": request_field_bindings,
        "response_field_bindings": response_field_bindings,
        "response_contract_candidates": [
            {"payload_type": payload_type, "contract_signature": _schema_contract_signature(schema_by_name, payload_type)}
            for payload_type in (props.get("response_payload_candidates") or [])
            if payload_type
        ],
        "composition_basis": props.get("composition_basis"),
        "helper_operation": props.get("helper_operation"),
        "scenario_operation": props.get("scenario_operation") or item.get("operation"),
        "client_bean_name": props.get("client_bean_name"),
        "framework": props.get("framework"),
        "local_caller_operations": props.get("local_caller_operations") or [],
        "local_call_chain_candidates": props.get("local_call_chain_candidates") or [],
        "request_observed_builder_setters": props.get("request_observed_builder_setters") or [],
        "source_set": source_set,
        "is_test_source": source_set == "test",
        "attributes": attributes,
        "attribute_count": len(attributes),
        "evidence_refs": item.get("evidence") or [],
        "evidence_level": "confirmed",
        "missing_links": missing_links,
    }


def _access_boundary_brief_from_fact(fact: Any) -> dict[str, Any] | None:
    props = fact.properties or {}
    bid = props.get("access_boundary_id")
    if not bid:
        return None
    source_file = str(props.get("source_file") or "")
    fields = props.get("fields") or []
    attributes = [
        {"attribute_name": str(f), "attribute_path": str(f), "source": "access_boundary_fields"}
        for f in fields[:128]
    ]
    boundary_kind = props.get("boundary_kind")
    protocol = "http" if boundary_kind == "http_outbound" else "rest" if str(boundary_kind or "").startswith("rest") else "kafka" if str(boundary_kind or "").startswith("kafka") else "grpc" if str(boundary_kind or "").startswith("grpc") else "callback" if str(boundary_kind or "").startswith("framework_callback") else "unknown"
    return {
        "interface_id": bid,
        "direction": "outbound",
        "boundary_kind": boundary_kind,
        "protocol": protocol,
        "operation": props.get("operation"),
        "endpoint_or_topic_raw": props.get("endpoint_or_topic"),
        "endpoint_or_topic_resolved": props.get("endpoint_or_topic"),
        "resolution_status": "resolved" if props.get("endpoint_or_topic") else "unresolved",
        "http_method": None,
        "payload_schema_ref": props.get("response_or_payload_type"),
        "request_payload_type": None,
        "response_payload_type": props.get("response_or_payload_type"),
        "message_payload_type": props.get("response_or_payload_type") if protocol == "kafka" else None,
        "message_key_expression": None,
        "message_payload_expression": props.get("payload_expression"),
        "source_set": _source_set_from_file_path(source_file),
        "is_test_source": _source_set_from_file_path(source_file) == "test",
        "attributes": attributes,
        "attribute_count": len(attributes),
        "evidence_refs": [_first_loc(fact.evidence)] if fact.evidence else [],
        "evidence_level": "confirmed" if props.get("external_access") is True else "unresolved",
        "missing_links": [] if props.get("endpoint_or_topic") else ["endpoint_or_topic_not_resolved"],
    }


def _system_interface_catalog_summary(items: list[dict[str, Any]]) -> dict[str, Any]:
    by_boundary = Counter(str(x.get("boundary_kind")) for x in items)
    by_protocol = Counter(str(x.get("protocol")) for x in items)
    by_source_set = Counter(str(x.get("source_set")) for x in items)
    return {
        "total": len(items),
        "production_total": sum(1 for x in items if not x.get("is_test_source")),
        "test_total": sum(1 for x in items if x.get("is_test_source")),
        "by_boundary_kind": dict(sorted(by_boundary.items())),
        "by_protocol": dict(sorted(by_protocol.items())),
        "by_source_set": dict(sorted(by_source_set.items())),
    }

def _interface_first_pass_item(item: dict[str, Any]) -> dict[str, Any]:
    props = item.get("properties") or {}
    propagation = props.get("request_field_propagation") or []
    return {
        "id": item.get("id"),
        "name": item.get("name"),
        "direction": item.get("direction"),
        "kind": item.get("kind"),
        "schema_ref": item.get("schema_ref"),
        "path": item.get("path"),
        "method": item.get("method"),
        "request_field_propagation": propagation[:4],
    }

def _flow_brief_from_fact(fact: Any) -> dict[str, Any] | None:
    props = fact.properties or {}
    flow_id = props.get("flow_id")
    if not flow_id:
        return None
    return {
        "flow_id": flow_id,
        "flow_type": props.get("flow_type"),
        "operation": props.get("operation"),
        "source_kind": props.get("source_kind"),
        "source_parameter": props.get("source_parameter"),
        "source_type": props.get("source_type"),
        "sink_kind": props.get("sink_kind"),
        "sink_pattern": props.get("sink_pattern"),
        "target_expression": props.get("target_expression"),
        "payload_expression": props.get("payload_expression"),
        "flow_mode": props.get("flow_mode"),
        "serialization_kind": props.get("serialization_kind"),
        "missing_links": props.get("missing_links") or [],
        "evidence": [_first_loc(fact.evidence)] if fact.evidence else [],
    }


def _flow_first_pass_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "flow_id": item.get("flow_id"),
        "operation": item.get("operation"),
        "source_parameter": item.get("source_parameter"),
        "source_type": item.get("source_type"),
        "sink_kind": item.get("sink_kind"),
        "payload_expression": item.get("payload_expression"),
        "serialization_kind": item.get("serialization_kind"),
    }


def _field_flow_brief_from_fact(fact: Any) -> dict[str, Any] | None:
    props = fact.properties or {}
    field_flow_id = props.get("field_flow_id")
    if not field_flow_id:
        return None
    return {
        "field_flow_id": field_flow_id,
        "source_object": props.get("source_object"),
        "source_parameter": props.get("source_parameter"),
        "source_field": props.get("source_field"),
        "source_role": props.get("source_role"),
        "field_mode": props.get("field_mode"),
        "sink_channel": props.get("sink_channel"),
        "sink_kind": props.get("sink_kind"),
        "sink_pattern": props.get("sink_pattern"),
        "sink": props.get("sink"),
        "sink_payload": props.get("sink_payload"),
        "payload_expression": props.get("payload_expression"),
        "target_expression": props.get("target_expression"),
        "operation": props.get("operation"),
        "class_name": props.get("class_name"),
        "method_name": props.get("method_name"),
        "related_flow_id": props.get("related_flow_id"),
        "path": props.get("path") or [],
        "evidence": [_first_loc(fact.evidence)] if fact.evidence else [],
    }


def _field_flow_first_pass_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "field_flow_id": item.get("field_flow_id"),
        "source_object": item.get("source_object"),
        "source_parameter": item.get("source_parameter"),
        "source_field": item.get("source_field"),
        "source_role": item.get("source_role"),
        "field_mode": item.get("field_mode"),
        "sink_channel": item.get("sink_channel"),
        "sink_payload": item.get("sink_payload"),
        "related_flow_id": item.get("related_flow_id"),
        "operation": item.get("operation"),
        "path": (item.get("path") or [])[:6],
    }


def _field_lineage_brief_from_fact(fact: Any) -> dict[str, Any] | None:
    props = fact.properties or {}
    lineage_id = props.get("field_lineage_id")
    if not lineage_id:
        return None
    return {
        "field_lineage_id": lineage_id,
        "lineage_type": props.get("lineage_type"),
        "source_boundary": props.get("source_boundary"),
        "source_operation": props.get("source_operation"),
        "source_payload": props.get("source_payload"),
        "source_parameter": props.get("source_parameter"),
        "source_field": props.get("source_field"),
        "source_field_type": props.get("source_field_type"),
        "source_field_role": props.get("source_field_role"),
        "target_boundary": props.get("target_boundary"),
        "target_operation": props.get("target_operation"),
        "target_payload": props.get("target_payload"),
        "target_field": props.get("target_field"),
        "target_location": props.get("target_location"),
        "field_role": props.get("field_role"),
        "path": (props.get("path") or [])[:12],
        "evidence_refs": props.get("evidence_refs") or [],
        "missing_links": props.get("missing_links") or [],
        "lookup_operation": props.get("lookup_operation"),
        "returned_or_published": props.get("returned_or_published"),
        "storage_access_id": props.get("storage_access_id"),
        "table_or_repository": props.get("table_or_repository"),
        "evidence": [_first_loc(fact.evidence)] if fact.evidence else [],
    }


def _field_lineage_first_pass_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "field_lineage_id": item.get("field_lineage_id"),
        "lineage_type": item.get("lineage_type"),
        "source_operation": item.get("source_operation"),
        "source_payload": item.get("source_payload"),
        "source_field": item.get("source_field"),
        "target_boundary": item.get("target_boundary"),
        "target_operation": item.get("target_operation"),
        "target_field": item.get("target_field"),
        "target_location": item.get("target_location"),
        "field_role": item.get("field_role"),
        "evidence_refs": (item.get("evidence_refs") or [])[:8],
        "missing_links": (item.get("missing_links") or [])[:4],
    }




def _output_field_provenance_brief_from_fact(fact: Any) -> dict[str, Any] | None:
    props = fact.properties or {}
    pid = props.get("output_field_provenance_id")
    if not pid:
        return None
    return {
        "output_field_provenance_id": pid,
        "published_boundary": props.get("published_boundary"),
        "published_operation": props.get("published_operation"),
        "published_payload": props.get("published_payload"),
        "published_field": props.get("published_field"),
        "published_location": props.get("published_location"),
        "origin_kind": props.get("origin_kind"),
        "immediate_origin_kind": props.get("immediate_origin_kind"),
        "ultimate_origin_kind": props.get("ultimate_origin_kind"),
        "origin_operation": props.get("origin_operation"),
        "origin_payload": props.get("origin_payload"),
        "origin_field": props.get("origin_field"),
        "origin_expression": props.get("origin_expression"),
        "path": (props.get("path") or [])[:12],
        "evidence_refs": props.get("evidence_refs") or [],
        "missing_links": props.get("missing_links") or [],
        "related_field_lineage_id": props.get("related_field_lineage_id"),
        "storage_access_id": props.get("storage_access_id"),
        "table_or_repository": props.get("table_or_repository"),
        "input_origins": props.get("input_origins") or [],
        "input_origin_kinds": props.get("input_origin_kinds") or [],
        "container_field": props.get("container_field"),
        "container_kind": props.get("container_kind"),
        "element_type": props.get("element_type"),
        "nested_field": props.get("nested_field"),
        "nested_field_provenance": props.get("nested_field_provenance"),
        "provenance_depth": props.get("provenance_depth"),
        "unresolved_boundary": props.get("unresolved_boundary"),
        "callee_operation": props.get("callee_operation"),
        "callee_resolution_kind": props.get("callee_resolution_kind"),
        "evidence": [_first_loc(fact.evidence)] if fact.evidence else [],
    }


def _output_field_provenance_first_pass_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "output_field_provenance_id": item.get("output_field_provenance_id"),
        "published_boundary": item.get("published_boundary"),
        "published_operation": item.get("published_operation"),
        "published_payload": item.get("published_payload"),
        "published_field": item.get("published_field"),
        "published_location": item.get("published_location"),
        "origin_kind": item.get("origin_kind"),
        "immediate_origin_kind": item.get("immediate_origin_kind"),
        "ultimate_origin_kind": item.get("ultimate_origin_kind"),
        "origin_operation": item.get("origin_operation"),
        "origin_payload": item.get("origin_payload"),
        "origin_field": item.get("origin_field"),
        "evidence_refs": (item.get("evidence_refs") or [])[:8],
        "missing_links": (item.get("missing_links") or [])[:4],
        "related_field_lineage_id": item.get("related_field_lineage_id"),
        "container_field": item.get("container_field"),
        "element_type": item.get("element_type"),
        "nested_field": item.get("nested_field"),
        "provenance_depth": item.get("provenance_depth"),
        "unresolved_boundary": item.get("unresolved_boundary"),
    }


def _call_chain_diagnostic_brief_from_fact(fact: Any) -> dict[str, Any] | None:
    props = fact.properties or {}
    did = props.get("call_chain_diagnostic_id")
    if not did:
        return None
    return {
        "call_chain_diagnostic_id": did,
        "target_operation": props.get("target_operation"),
        "published_boundary": props.get("published_boundary"),
        "caller_status": props.get("caller_status"),
        "caller_candidates": props.get("caller_candidates") or [],
        "resolved_call_ids": props.get("resolved_call_ids") or [],
        "resolved_callers": props.get("resolved_callers") or [],
        "system_ingress_status": props.get("system_ingress_status"),
        "reason": props.get("reason"),
        "missing_links": props.get("missing_links") or [],
        "evidence_refs": props.get("evidence_refs") or [],
        "evidence": [_first_loc(fact.evidence)] if fact.evidence else [],
    }


def _call_chain_diagnostic_first_pass_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "call_chain_diagnostic_id": item.get("call_chain_diagnostic_id"),
        "target_operation": item.get("target_operation"),
        "published_boundary": item.get("published_boundary"),
        "caller_status": item.get("caller_status"),
        "system_ingress_status": item.get("system_ingress_status"),
        "reason": item.get("reason"),
        "missing_links": (item.get("missing_links") or [])[:4],
        "caller_candidates": (item.get("caller_candidates") or [])[:8],
        "resolved_callers": (item.get("resolved_callers") or [])[:8],
    }

def _ingress_brief_from_fact(fact: Any) -> dict[str, Any] | None:
    props = fact.properties or {}
    ingress_id = props.get("ingress_id")
    if not ingress_id:
        return None
    return {
        "ingress_id": ingress_id,
        "origin_id": props.get("origin_id"),
        "ingress_kind": props.get("ingress_kind"),
        "origin_kind": props.get("origin_kind"),
        "is_payload_origin": props.get("is_payload_origin"),
        "operation": props.get("operation"),
        "operation_id": props.get("operation_id"),
        "class_name": props.get("class_name"),
        "method_name": props.get("method_name"),
        "payload_type": props.get("payload_type"),
        "payload_parameter": props.get("payload_parameter"),
        "endpoint_or_topic": props.get("endpoint_or_topic"),
        "evidence": [_first_loc(fact.evidence)] if fact.evidence else [],
    }


def _call_brief_from_fact(fact: Any) -> dict[str, Any] | None:
    props = fact.properties or {}
    call_id = props.get("call_id")
    if not call_id:
        return None
    return {
        "call_id": call_id,
        "caller_operation_id": props.get("caller_operation_id"),
        "caller_operation_signature": props.get("caller_operation_signature"),
        "callee_operation_id": props.get("callee_operation_id"),
        "callee_operation_signature": props.get("callee_operation_signature"),
        "caller_method": props.get("caller_method"),
        "callee_method": props.get("callee_method"),
        "receiver_expression": props.get("receiver_expression"),
        "receiver_type": props.get("receiver_type"),
        "overload_resolution": props.get("overload_resolution"),
        "overload_candidate_count": props.get("overload_candidate_count"),
        "callee_parameter_types": props.get("callee_parameter_types") or [],
        "argument_bindings": (props.get("argument_bindings") or [])[:6],
        "evidence": [_first_loc(fact.evidence)] if fact.evidence else [],
    }


def _storage_access_brief_from_fact(fact: Any) -> dict[str, Any] | None:
    props = fact.properties or {}
    storage_access_id = props.get("storage_access_id")
    if not storage_access_id:
        return None
    return {
        "storage_access_id": storage_access_id,
        "operation": props.get("operation"),
        "operation_id": props.get("operation_id"),
        "access_kind": props.get("access_kind"),
        "write_kind": props.get("write_kind"),
        "mutation_kind": props.get("mutation_kind"),
        "table_or_repository": props.get("table_or_repository"),
        "receiver_expression": props.get("receiver_expression"),
        "storage_method": props.get("storage_method"),
        "payload_expression": props.get("payload_expression"),
        "sql_preview": props.get("sql_preview"),
        "candidate_signals": props.get("candidate_signals") or [],
        "evidence_maturity_level": props.get("evidence_maturity_level"),
        "evidence_maturity_dimensions": props.get("evidence_maturity_dimensions") or {},
        "unresolved_gap_lifecycle": props.get("unresolved_gap_lifecycle") or [],
        "source_inspection_required": props.get("source_inspection_required"),
        "source_inspection_request_ids": props.get("source_inspection_request_ids") or [],
        "evidence": [_first_loc(fact.evidence)] if fact.evidence else [],
    }


def _data_source_brief_from_fact(fact: Any) -> dict[str, Any] | None:
    props = fact.properties or {}
    data_source_id = props.get("data_source_id")
    if not data_source_id:
        return None
    return {
        "data_source_id": data_source_id,
        "source_kind": props.get("source_kind"),
        "source_operation": props.get("source_operation"),
        "source_payload": props.get("source_payload"),
        "source_fields": (props.get("source_fields") or [])[:16],
        "source_field_count": props.get("source_field_count"),
        "classification_policy": props.get("classification_policy"),
        "evidence": [_first_loc(fact.evidence)] if fact.evidence else [],
    }


def _persistent_write_brief_from_fact(fact: Any) -> dict[str, Any] | None:
    props = fact.properties or {}
    persistent_write_id = props.get("persistent_write_id")
    if not persistent_write_id:
        return None
    return {
        "persistent_write_id": persistent_write_id,
        "storage_access_id": props.get("storage_access_id"),
        "operation": props.get("operation"),
        "write_kind": props.get("write_kind"),
        "storage_kind": props.get("storage_kind"),
        "storage_target": props.get("storage_target"),
        "storage_resolution_level": props.get("storage_resolution_level"),
        "source_scope": props.get("source_scope"),
        "storage_method": props.get("storage_method"),
        "storage_call": props.get("storage_call"),
        "storage_access_id": props.get("storage_access_id"),
        "persistent_write_id": props.get("persistent_write_id"),
        "source_container": props.get("source_container"),
        "source_container_type": props.get("source_container_type"),
        "source_element_type": props.get("source_element_type"),
        "source_payload_parameter": props.get("source_payload_parameter"),
        "lineage_status": props.get("lineage_status"),
        "source_to_storage_segment": props.get("source_to_storage_segment") or {},
        "source_to_saved_field_mappings": (props.get("source_to_saved_field_mappings") or [])[:32],
        "write_target_fields": (props.get("write_target_fields") or [])[:32],
        "persistence_missing_links": props.get("persistence_missing_links"),
        "candidate_signals": props.get("candidate_signals") or [],
        "evidence_maturity_level": props.get("evidence_maturity_level"),
        "evidence_maturity_dimensions": props.get("evidence_maturity_dimensions") or {},
        "unresolved_gap_lifecycle": props.get("unresolved_gap_lifecycle") or [],
        "source_inspection_required": props.get("source_inspection_required"),
        "source_inspection_request_ids": props.get("source_inspection_request_ids") or [],
        "source_inspection_request_status": props.get("source_inspection_request_status"),
        "saved_object": props.get("saved_object"),
        "payload_expression": props.get("payload_expression"),
        "written_fields": (props.get("written_fields") or [])[:32],
        "written_field_count": props.get("written_field_count"),
        "evidence": [_first_loc(fact.evidence)] if fact.evidence else [],
    }


def _source_to_storage_lineage_brief_from_fact(fact: Any) -> dict[str, Any] | None:
    props = fact.properties or {}
    lineage_id = props.get("source_to_storage_lineage_id")
    if not lineage_id:
        return None
    return {
        "source_to_storage_lineage_id": lineage_id,
        "source_kind": props.get("source_kind"),
        "source_operation": props.get("source_operation"),
        "source_payload": props.get("source_payload"),
        "source_field": props.get("source_field"),
        "source_field_role": props.get("source_field_role"),
        "storage_operation": props.get("storage_operation"),
        "storage_target": props.get("storage_target"),
        "storage_resolution_level": props.get("storage_resolution_level"),
        "source_scope": props.get("source_scope"),
        "storage_method": props.get("storage_method"),
        "storage_call": props.get("storage_call"),
        "storage_access_id": props.get("storage_access_id"),
        "persistent_write_id": props.get("persistent_write_id"),
        "source_container": props.get("source_container"),
        "source_container_type": props.get("source_container_type"),
        "source_element_type": props.get("source_element_type"),
        "source_payload_parameter": props.get("source_payload_parameter"),
        "lineage_status": props.get("lineage_status"),
        "source_to_storage_segment": props.get("source_to_storage_segment") or {},
        "source_to_saved_field_mappings": (props.get("source_to_saved_field_mappings") or [])[:32],
        "write_target_fields": (props.get("write_target_fields") or [])[:32],
        "persistence_missing_links": props.get("persistence_missing_links"),
        "candidate_signals": props.get("candidate_signals") or [],
        "evidence_maturity_level": props.get("evidence_maturity_level"),
        "evidence_maturity_dimensions": props.get("evidence_maturity_dimensions") or {},
        "unresolved_gap_lifecycle": props.get("unresolved_gap_lifecycle") or [],
        "source_inspection_required": props.get("source_inspection_required"),
        "source_inspection_request_ids": props.get("source_inspection_request_ids") or [],
        "source_inspection_request_status": props.get("source_inspection_request_status"),
        "saved_object": props.get("saved_object"),
        "saved_object_field": props.get("saved_object_field"),
        "storage_field": props.get("storage_field"),
        "assignment_kind": props.get("assignment_kind"),
        "assignment_expression": props.get("assignment_expression"),
        "missing_links": props.get("missing_links") or [],
        "path": (props.get("path") or [])[:12],
        "evidence_refs": props.get("evidence_refs") or [],
        "evidence": [_first_loc(fact.evidence)] if fact.evidence else [],
    }


def _storage_to_access_lineage_brief_from_fact(fact: Any) -> dict[str, Any] | None:
    props = fact.properties or {}
    lineage_id = props.get("storage_to_access_lineage_id")
    if not lineage_id:
        return None
    return {
        "storage_to_access_lineage_id": lineage_id,
        "read_evidence_ref": props.get("read_evidence_ref"),
        "access_evidence_ref": props.get("access_evidence_ref"),
        "source_storage_object": props.get("source_storage_object"),
        "access_boundary": props.get("access_boundary"),
        "lineage_status": props.get("lineage_status"),
        "same_method_lineage": props.get("same_method_lineage"),
        "field_mappings": (props.get("field_mappings") or [])[:64],
        "path": (props.get("path") or [])[:12],
        "missing_links": props.get("missing_links") or [],
        "candidate_signals": props.get("candidate_signals") or [],
        "evidence_maturity_level": props.get("evidence_maturity_level"),
        "evidence_maturity_dimensions": props.get("evidence_maturity_dimensions") or {},
        "evidence": [_first_loc(fact.evidence)] if fact.evidence else [],
    }


def _stored_field_to_response_mapping_brief_from_fact(fact: Any) -> dict[str, Any] | None:
    props = fact.properties or {}
    mapping_id = props.get("stored_field_to_response_field_mapping_id")
    if not mapping_id:
        return None
    return {
        "stored_field_to_response_field_mapping_id": mapping_id,
        "storage_to_access_lineage_id": props.get("storage_to_access_lineage_id"),
        "storage_object": props.get("storage_object"),
        "storage_field": props.get("storage_field"),
        "read_type": props.get("read_type"),
        "response_or_payload_type": props.get("response_or_payload_type"),
        "response_field": props.get("response_field"),
        "mapping_type": props.get("mapping_type"),
        "mapping_source": props.get("mapping_source"),
        "evidence_level": props.get("evidence_level") or props.get("evidence_maturity_level"),
        "evidence_maturity_dimensions": props.get("evidence_maturity_dimensions") or {},
        "evidence": [_first_loc(fact.evidence)] if fact.evidence else [],
    }


def _db_schema_item_brief_from_fact(fact: Any) -> dict[str, Any] | None:
    props = fact.properties or {}
    if not str(fact.fact_type).startswith("db_schema_"):
        return None
    keys = (
        "table_name", "qualified_table_name", "schema_name", "column_name",
        "sql_type", "data_type", "nullable", "default", "description",
        "constraint_type", "key_type", "relationship_type", "source_table",
        "target_table", "source_columns", "target_columns", "index_name",
        "index_type", "columns", "sequence_name", "trigger_name",
        "trigger_event", "trigger_timing", "partitioning_type", "source_type",
        "source_set", "is_test_source",
    )
    item = {k: props.get(k) for k in keys if props.get(k) is not None}
    item.setdefault("name", fact.name)
    item.setdefault("fact_type", fact.fact_type)
    if fact.evidence:
        item["evidence"] = [_first_loc(fact.evidence)]
    return item


_DOMAIN_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("cards", ("card", "pprb", "reissue", "pan", "plastic")),
    ("phones", ("phone", "msisdn", "mobile")),
    ("links", ("link", "binding", "relation")),
    ("client_profile_ucp", ("client", "profile", "ucp", "customer")),
    ("devices", ("device", "push", "token", "notification", "channel")),
    ("corporate", ("corporate", "corp", "organization", "terbank", "bank")),
    ("dictionaries_reference", ("dictionary", "dict", "reference", "lookup", "catalog")),
    ("operations_history", ("operation", "journal", "history", "audit", "log")),
]


def _domain_for_values(*values: Any) -> str:
    text = " ".join(str(v or "") for v in values).lower()
    for domain, needles in _DOMAIN_RULES:
        if any(n in text for n in needles):
            return domain
    return "other"


def _compact_domain_items(items: list[dict[str, Any]], *, key_fields: tuple[str, ...], limit: int = 20) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for item in items:
        key = tuple(item.get(k) for k in key_fields)
        if key in seen:
            continue
        seen.add(key)
        out.append({k: item.get(k) for k in key_fields if item.get(k) is not None})
        if len(out) >= limit:
            break
    return out


def _build_domain_summaries(*,
    db_tables: list[dict[str, Any]],
    db_columns: list[dict[str, Any]],
    interfaces: list[dict[str, Any]],
    system_scenarios: list[dict[str, Any]],
    storage_usage: list[dict[str, Any]],
    persistent_writes: list[dict[str, Any]],
    source_to_storage: list[dict[str, Any]],
    access_boundaries: list[dict[str, Any]],
    storage_to_access: list[dict[str, Any]],
    external_dependencies: list[dict[str, Any]],
    declared_value_sets: list[dict[str, Any]],
    transformations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    domains: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "tables": [], "columns_count": 0, "interfaces": [], "scenarios": [],
        "storage_usage": [], "writes": [], "source_to_storage": [],
        "access_boundaries": [], "storage_to_access": [], "external_dependencies": [],
        "declared_value_sets": [], "transformations": [],
    })
    for table in db_tables:
        d = _domain_for_values(table.get("qualified_table_name"), table.get("table_name"), table.get("name"), table.get("description"))
        domains[d]["tables"].append(table)
    table_domain: dict[str, str] = {}
    for d, bucket in domains.items():
        for t in bucket["tables"]:
            for k in ("qualified_table_name", "table_name", "name"):
                if t.get(k):
                    table_domain[str(t.get(k)).lower()] = d
    for col in db_columns:
        t = str(col.get("qualified_table_name") or col.get("table_name") or "").lower()
        d = table_domain.get(t) or _domain_for_values(t, col.get("column_name"), col.get("description"))
        domains[d]["columns_count"] += 1
    for item in interfaces:
        d = _domain_for_values(item.get("name"), item.get("operation"), item.get("path"), item.get("payload_schema_ref"), item.get("request_payload_type"), item.get("response_payload_type"))
        domains[d]["interfaces"].append(item)
    for item in system_scenarios:
        d = _domain_for_values(item.get("operation"), item.get("scenario_id"), item.get("entrypoints"))
        domains[d]["scenarios"].append(item)
    for item in storage_usage:
        d = table_domain.get(str(item.get("storage_target") or "").lower()) or _domain_for_values(item.get("storage_target"))
        domains[d]["storage_usage"].append(item)
    for item in persistent_writes:
        d = table_domain.get(str(item.get("storage_target") or "").lower()) or _domain_for_values(item.get("storage_target"), item.get("operation"), item.get("saved_object"))
        domains[d]["writes"].append(item)
    for item in source_to_storage:
        d = table_domain.get(str(item.get("storage_target") or "").lower()) or _domain_for_values(item.get("storage_target"), item.get("source_payload"), item.get("source_operation"))
        domains[d]["source_to_storage"].append(item)
    for item in access_boundaries:
        d = _domain_for_values(item.get("operation"), item.get("payload_schema_ref"), item.get("response_payload_type"), item.get("endpoint_or_topic_raw"))
        domains[d]["access_boundaries"].append(item)
    for item in storage_to_access:
        d = table_domain.get(str(item.get("source_storage_object") or "").lower()) or _domain_for_values(item.get("source_storage_object"), item.get("access_boundary"))
        domains[d]["storage_to_access"].append(item)
    for item in external_dependencies:
        d = _domain_for_values(item.get("name"), item.get("operation"), item.get("client_receiver_type"), item.get("endpoint_path"))
        domains[d]["external_dependencies"].append(item)
    for item in declared_value_sets:
        d = _domain_for_values(item.get("name"), item.get("display_name"), item.get("syntax_kind"))
        domains[d]["declared_value_sets"].append(item)
    for item in transformations:
        d = _domain_for_values(item.get("source_object"), item.get("target_object"), item.get("source_field"), item.get("target_field"), item.get("operation"))
        domains[d]["transformations"].append(item)

    out: list[dict[str, Any]] = []
    for domain, bucket in sorted(domains.items()):
        activity = sum(len(bucket[k]) for k in bucket if isinstance(bucket[k], list)) + int(bucket.get("columns_count") or 0)
        if activity == 0:
            continue
        out.append({
            "domain": domain,
            "counts": {
                "tables": len(bucket["tables"]),
                "columns": bucket["columns_count"],
                "interfaces": len(bucket["interfaces"]),
                "scenarios": len(bucket["scenarios"]),
                "storage_usage": len(bucket["storage_usage"]),
                "writes": len(bucket["writes"]),
                "source_to_storage_lineage": len(bucket["source_to_storage"]),
                "access_boundaries": len(bucket["access_boundaries"]),
                "storage_to_access_lineage": len(bucket["storage_to_access"]),
                "external_dependencies": len(bucket["external_dependencies"]),
                "declared_value_sets": len(bucket["declared_value_sets"]),
                "transformations": len(bucket["transformations"]),
            },
            "tables": _compact_domain_items(bucket["tables"], key_fields=("qualified_table_name", "table_name", "description"), limit=30),
            "interfaces": _compact_domain_items(bucket["interfaces"], key_fields=("name", "direction", "boundary_kind", "protocol", "path", "http_method", "payload_schema_ref", "response_payload_type"), limit=25),
            "storage_usage": _compact_domain_items(bucket["storage_usage"], key_fields=("storage_target", "read_count", "write_count", "mutation_count", "operation_count"), limit=25),
            "writes": _compact_domain_items(bucket["writes"], key_fields=("operation", "write_kind", "storage_target", "saved_object", "written_field_count"), limit=25),
            "source_to_storage_samples": _compact_domain_items(bucket["source_to_storage"], key_fields=("source_kind", "source_payload", "source_field", "storage_target", "storage_field", "storage_operation"), limit=25),
            "access_boundary_samples": _compact_domain_items(bucket["access_boundaries"], key_fields=("operation", "boundary_kind", "endpoint_or_topic_raw", "payload_schema_ref", "response_payload_type", "attribute_count"), limit=25),
            "storage_to_access_samples": _compact_domain_items(bucket["storage_to_access"], key_fields=("source_storage_object", "access_boundary", "lineage_status", "same_method_lineage"), limit=25),
            "declared_value_set_samples": _compact_domain_items(bucket["declared_value_sets"], key_fields=("name", "display_name", "syntax_kind", "source_set", "entries_count"), limit=20),
        })
    return out


def _storage_lineage_gap_brief_from_fact(fact: Any) -> dict[str, Any] | None:
    props = fact.properties or {}
    gap_id = props.get("storage_lineage_gap_id")
    if not gap_id:
        return None
    return {
        "storage_lineage_gap_id": gap_id,
        "gap_kind": props.get("gap_kind"),
        "storage_access_id": props.get("storage_access_id"),
        "storage_operation": props.get("storage_operation"),
        "storage_target": props.get("storage_target"),
        "storage_method": props.get("storage_method"),
        "storage_call": props.get("storage_call"),
        "storage_access_id": props.get("storage_access_id"),
        "persistent_write_id": props.get("persistent_write_id"),
        "source_container": props.get("source_container"),
        "source_container_type": props.get("source_container_type"),
        "source_element_type": props.get("source_element_type"),
        "source_payload_parameter": props.get("source_payload_parameter"),
        "source_to_storage_segment": props.get("source_to_storage_segment") or {},
        "source_to_saved_field_mappings": (props.get("source_to_saved_field_mappings") or [])[:32],
        "write_target_fields": (props.get("write_target_fields") or [])[:32],
        "persistence_missing_links": props.get("persistence_missing_links"),
        "candidate_signals": props.get("candidate_signals") or [],
        "evidence_maturity_level": props.get("evidence_maturity_level"),
        "evidence_maturity_dimensions": props.get("evidence_maturity_dimensions") or {},
        "unresolved_gap_lifecycle": props.get("unresolved_gap_lifecycle") or [],
        "source_inspection_required": props.get("source_inspection_required"),
        "source_inspection_request_ids": props.get("source_inspection_request_ids") or [],
        "source_inspection_request_status": props.get("source_inspection_request_status"),
        "saved_object": props.get("saved_object"),
        "saved_object_field": props.get("saved_object_field"),
        "reason": props.get("reason"),
        "missing_links": props.get("missing_links") or [],
        "evidence": [_first_loc(fact.evidence)] if fact.evidence else [],
    }


def _source_inspection_request_brief_from_fact(fact: Any) -> dict[str, Any] | None:
    props = fact.properties or {}
    rid = props.get("source_inspection_request_id")
    if not rid:
        return None
    return {
        "source_inspection_request_id": rid,
        "request_type": props.get("request_type"),
        "status": props.get("status"),
        "reason": props.get("reason"),
        "priority": props.get("priority"),
        "target_operation": props.get("target_operation"),
        "target_symbol": props.get("target_symbol"),
        "target_callable": props.get("target_callable"),
        "focus": props.get("focus"),
        "source_payload": props.get("source_payload"),
        "saved_object": props.get("saved_object"),
        "saved_field": props.get("saved_field"),
        "storage_target": props.get("storage_target"),
        "storage_method": props.get("storage_method"),
        "related_evidence_refs": props.get("related_evidence_refs") or [],
        "trigger_blockers": props.get("trigger_blockers") or [],
        "expected_observations": props.get("expected_observations") or [],
        "search_tokens": props.get("search_tokens") or [],
        "suggested_evidence_tools": props.get("suggested_evidence_tools") or [],
        "inspection_policy": props.get("inspection_policy"),
        "iterative_follow_up_policy": props.get("iterative_follow_up_policy"),
        "llm_evidence_rule": props.get("llm_evidence_rule"),
        "evidence": [_first_loc(fact.evidence)] if fact.evidence else [],
    }


def _persistent_structure_brief_from_fact(fact: Any) -> dict[str, Any] | None:
    props = fact.properties or {}
    sid = props.get("persistent_structure_id")
    if not sid:
        return None
    return {
        "persistent_structure_id": sid,
        "project_code": props.get("project_code"),
        "system_name": props.get("system_name"),
        "repo_id": props.get("repo_id"),
        "fp_id": props.get("fp_id"),
        "storage_kind": props.get("storage_kind"),
        "storage_target": props.get("storage_target"),
        "container_kind": props.get("container_kind"),
        "container_name": props.get("container_name"),
        "container_fqcn": props.get("container_fqcn"),
        "source_scope": props.get("source_scope"),
        "source_set": props.get("source_set"),
        "is_test_source": props.get("is_test_source"),
        "module_name": props.get("module_name"),
        "model_annotation": props.get("model_annotation"),
        "model_annotation_args": props.get("model_annotation_args") or {},
        "super_types": props.get("super_types") or [],
        "source_repositories": props.get("source_repositories") or [],
        "fields": (props.get("fields") or [])[:48],
        "field_count": props.get("field_count"),
        "evidence": [_first_loc(fact.evidence)] if fact.evidence else [],
    }


def _attribute_occurrence_brief_from_fact(fact: Any) -> dict[str, Any] | None:
    props = fact.properties or {}
    oid = props.get("attribute_occurrence_id")
    if not oid:
        return None
    return {
        "attribute_occurrence_id": oid,
        "project_code": props.get("project_code"),
        "system_name": props.get("system_name"),
        "repo_id": props.get("repo_id"),
        "fp_id": props.get("fp_id"),
        "container_kind": props.get("container_kind"),
        "container_name": props.get("container_name"),
        "attribute_name": props.get("attribute_name"),
        "attribute_type": props.get("attribute_type"),
        "attribute_role": props.get("attribute_role"),
        "source_path": props.get("source_path"),
        "line_start": props.get("line_start"),
        "evidence": [_first_loc(fact.evidence)] if fact.evidence else [],
    }


def _attribute_mapping_brief_from_fact(fact: Any) -> dict[str, Any] | None:
    props = fact.properties or {}
    mid = props.get("attribute_mapping_id")
    if not mid:
        return None
    return {
        "attribute_mapping_id": mid,
        "project_code": props.get("project_code"),
        "system_name": props.get("system_name"),
        "repo_id": props.get("repo_id"),
        "fp_id": props.get("fp_id"),
        "operation": props.get("operation"),
        "source_container": props.get("source_container"),
        "source_field": props.get("source_field"),
        "target_container": props.get("target_container"),
        "target_field": props.get("target_field"),
        "mapping_kind": props.get("mapping_kind"),
        "expression": props.get("expression"),
        "evidence": [_first_loc(fact.evidence)] if fact.evidence else [],
    }


def _attribute_derivation_brief_from_fact(fact: Any) -> dict[str, Any] | None:
    props = fact.properties or {}
    if props.get("attribute_derivation_id"):
        did = props["attribute_derivation_id"]
    else:
        stable_seed = json.dumps(
            [fact.name, props.get("operation"), props.get("target_field")],
            ensure_ascii=False,
            separators=(",", ":"),
            default=str,
        )
        stable_number = int(hashlib.sha256(stable_seed.encode("utf-8")).hexdigest()[:16], 16) % 10**12
        did = f"derived_{stable_number:012d}"
    target_field = props.get("target_field")
    if not target_field and not props.get("source_fields"):
        return None
    return {
        "attribute_derivation_id": did,
        "project_code": props.get("project_code"),
        "system_name": props.get("system_name"),
        "repo_id": props.get("repo_id"),
        "fp_id": props.get("fp_id"),
        "operation": props.get("operation"),
        "source_object": props.get("source_object"),
        "source_fields": props.get("source_fields") or [],
        "target_object": props.get("target_object"),
        "target_container": props.get("target_container"),
        "target_field": target_field,
        "derivation_kind": props.get("derivation_kind"),
        "expression_kind": props.get("expression_kind"),
        "expression": props.get("expression"),
        "evidence_level": props.get("evidence_maturity_level") or props.get("evidence_level"),
        "evidence": [_first_loc(fact.evidence)] if fact.evidence else [],
    }


def _data_model_lineage_gap_brief_from_fact(fact: Any) -> dict[str, Any] | None:
    props = fact.properties or {}
    gid = props.get("data_model_lineage_gap_id")
    if not gid:
        return None
    return {
        "data_model_lineage_gap_id": gid,
        "project_code": props.get("project_code"),
        "system_name": props.get("system_name"),
        "repo_id": props.get("repo_id"),
        "fp_id": props.get("fp_id"),
        "gap_kind": props.get("gap_kind"),
        "operation": props.get("operation"),
        "container": props.get("container"),
        "field": props.get("field"),
        "reason": props.get("reason"),
        "missing_links": props.get("missing_links") or [],
        "source_scope": props.get("source_scope"),
        "target_container_fqcn": props.get("target_container_fqcn"),
        "target_type_reference": props.get("target_type_reference"),
        "target_resolution_kind": props.get("target_resolution_kind"),
        "candidate_target_fqcns": props.get("candidate_target_fqcns") or [],
        "constructor_argument_index": props.get("constructor_argument_index"),
        "constructor_argument_expression_kind": props.get("constructor_argument_expression_kind"),
        "evidence": [_first_loc(fact.evidence)] if fact.evidence else [],
    }

def _trace_brief_from_fact(fact: Any) -> dict[str, Any] | None:
    props = fact.properties or {}
    trace_id = props.get("trace_id")
    if not trace_id:
        return None
    return {
        "trace_id": trace_id,
        "trace_type": props.get("trace_type"),
        "origin_trace_type": props.get("origin_trace_type"),
        "trace_status": props.get("trace_status"),
        "origin_kind": props.get("origin_kind"),
        "ingress_id": props.get("ingress_id"),
        "origin_id": props.get("origin_id"),
        "is_payload_origin": props.get("is_payload_origin"),
        "ingress_operation_id": props.get("ingress_operation_id"),
        "earliest_observed_operation_id": props.get("earliest_observed_operation_id"),
        "terminal_operation_id": props.get("terminal_operation_id"),
        "outbound_operation_id": props.get("outbound_operation_id"),
        "persistence_operation_id": props.get("persistence_operation_id"),
        "sink_kind": props.get("sink_kind"),
        "storage_access_id": props.get("storage_access_id"),
        "db_write_kind": props.get("db_write_kind"),
        "table_or_repository": props.get("table_or_repository"),
        "payload_type": props.get("payload_type"),
        "payload_expression": props.get("payload_expression"),
        "evidence_refs": props.get("evidence_refs") or [],
        "missing_links": props.get("missing_links") or [],
        "steps": (props.get("steps") or [])[:12],
        "evidence": [_first_loc(fact.evidence)] if fact.evidence else [],
    }


def _trace_first_pass_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "trace_id": item.get("trace_id"),
        "trace_type": item.get("trace_type"),
        "trace_status": item.get("trace_status"),
        "origin_kind": item.get("origin_kind"),
        "ingress_id": item.get("ingress_id"),
        "earliest_observed_operation_id": item.get("earliest_observed_operation_id"),
        "terminal_operation_id": item.get("terminal_operation_id"),
        "sink_kind": item.get("sink_kind"),
        "storage_access_id": item.get("storage_access_id"),
        "evidence_refs": (item.get("evidence_refs") or [])[:10],
        "missing_links": (item.get("missing_links") or [])[:6],
    }



def _declared_value_set_brief_from_fact(fact: Any) -> dict[str, Any] | None:
    props = fact.properties or {}
    set_id = props.get("declared_value_set_id")
    if not set_id:
        return None
    return {
        "declared_value_set_id": set_id,
        "name": props.get("name") or fact.name,
        "display_name": props.get("display_name") or props.get("name") or fact.name,
        "syntax_kind": props.get("syntax_kind"),
        "location_kind": props.get("location_kind"),
        "source_set": props.get("source_set"),
        "entries_count": props.get("entries_count"),
        "entries_observed_count": props.get("entries_observed_count"),
        "sample_entries": (props.get("sample_entries") or [])[:20],
        "key_type": props.get("key_type"),
        "value_type": props.get("value_type"),
        "source_expression": props.get("source_expression"),
        "extraction_truncated": bool(props.get("extraction_truncated")),
        "truncation_reason": props.get("truncation_reason"),
        "retrieval": props.get("retrieval"),
        "evidence": [_first_loc(fact.evidence)] if fact.evidence else [],
    }


def _declared_value_set_first_pass_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "declared_value_set_id": item.get("declared_value_set_id"),
        "name": item.get("name"),
        "syntax_kind": item.get("syntax_kind"),
        "location_kind": item.get("location_kind"),
        "source_set": item.get("source_set"),
        "entries_count": item.get("entries_count"),
        "sample_entries": (item.get("sample_entries") or [])[:8],
        "extraction_truncated": bool(item.get("extraction_truncated")),
    }

def _scanner_status_summary(result: AnalysisResult) -> dict[str, Any]:
    normalized = result.coverage.get("normalized_facts") or {}
    return {
        "artifact": "scanner_status_summary",
        "heavy_tools": result.coverage.get("heavy_tools") or {
            "spoon_scan": {"status": "removed_from_fast_core"},
            "semgrep_scan": {"status": "removed_from_fast_core"},
            "targeted_semgrep_scan": {"status": "removed_from_fast_core"},
        },
        "evidence_coverage": result.coverage.get("evidence_coverage"),
        "normalized_facts": {
            "fact_count": normalized.get("fact_count"),
            "persisted_fact_count": normalized.get("persisted_fact_count"),
            "evidence_count": normalized.get("evidence_count"),
            "persistence_policy": normalized.get("persistence_policy"),
        },
        "low_level_facts": result.coverage.get("low_level_facts"),
    }



def _fact_primary_id(fact: Any) -> str | None:
    props = fact.properties or {}
    for key in (
        "source_inspection_request_id", "storage_access_id", "persistent_write_id",
        "read_from_storage_id", "access_boundary_id", "storage_to_access_lineage_id",
        "stored_field_to_response_field_mapping_id",
        "source_to_storage_lineage_id", "storage_lineage_gap_id", "field_lineage_id",
        "output_field_provenance_id", "data_source_id", "flow_id", "field_flow_id",
        "trace_id", "call_chain_diagnostic_id", "declared_value_set_id", "declared_value_set_summary_id", "declared_value_id",
        "persistent_structure_id", "attribute_mapping_id", "attribute_derivation_id",
        "attribute_occurrence_id", "data_model_lineage_gap_id",
    ):
        if props.get(key):
            return str(props.get(key))
    return fact.name or None


def _strict_location_from_fact(fact: Any) -> dict[str, Any] | None:
    return _first_loc(fact.evidence) if getattr(fact, "evidence", None) else None


def _confirmed_evidence_item_from_fact(fact: Any) -> dict[str, Any] | None:
    props = fact.properties or {}
    dims = props.get("evidence_maturity_dimensions") or {}
    if not isinstance(dims, dict):
        return None
    confirmed = {str(k): v for k, v in dims.items() if str(v) == "confirmed"}
    if not confirmed:
        return None
    return {
        "evidence_id": _fact_primary_id(fact),
        "fact_type": fact.fact_type,
        "name": fact.name,
        "confirmed_dimensions": confirmed,
        "evidence_maturity_level": props.get("evidence_maturity_level"),
        "summary": {k: props.get(k) for k in (
            "operation", "operation_id", "source_operation", "storage_operation",
            "source_payload", "source_field", "storage_target", "storage_field",
            "saved_object", "saved_object_field", "target_field", "published_field",
            "read_from_storage_id", "access_boundary_id", "storage_to_access_lineage_id",
            "stored_field_to_response_field_mapping_id", "storage_symbol", "storage_object",
            "boundary_kind", "endpoint_or_topic", "response_or_payload_type",
            "read_evidence_ref", "access_evidence_ref", "source_storage_object", "access_boundary",
            "response_field", "mapping_type",
        ) if props.get(k) is not None},
        "location": _strict_location_from_fact(fact),
    }


def _candidate_signal_items_from_fact(fact: Any) -> list[dict[str, Any]]:
    props = fact.properties or {}
    signals = props.get("candidate_signals") or []
    if not isinstance(signals, list):
        return []
    out: list[dict[str, Any]] = []
    for idx, signal in enumerate(signals, start=1):
        if not isinstance(signal, dict):
            continue
        out.append({
            "candidate_signal_id": f"{_fact_primary_id(fact) or fact.fact_type}:candidate_signal:{idx}",
            "source_evidence_id": _fact_primary_id(fact),
            "source_fact_type": fact.fact_type,
            "signal_type": signal.get("signal_type"),
            "target": signal.get("target"),
            "basis": signal.get("basis"),
            "is_evidence": False,
            "allowed_use": "navigation_only",
            "requires_source_inspection": signal.get("requires_source_inspection", True),
            "recommended_action": signal.get("recommended_action"),
            "related_evidence_refs": signal.get("related_evidence_refs") or [],
            "location": _strict_location_from_fact(fact),
        })
    return out


def _unresolved_gap_items_from_fact(fact: Any) -> list[dict[str, Any]]:
    props = fact.properties or {}
    lifecycle = props.get("unresolved_gap_lifecycle") or []
    if not isinstance(lifecycle, list):
        return []
    out: list[dict[str, Any]] = []
    for idx, gap in enumerate(lifecycle, start=1):
        if not isinstance(gap, dict):
            continue
        out.append({
            "unresolved_gap_id": f"{_fact_primary_id(fact) or fact.fact_type}:gap:{idx}",
            "source_evidence_id": _fact_primary_id(fact),
            "source_fact_type": fact.fact_type,
            "dimension": gap.get("dimension"),
            "gap_type": gap.get("gap_type"),
            "decision_blocking": gap.get("decision_blocking"),
            "actionability": gap.get("actionability"),
            "source_inspection_required": gap.get("source_inspection_required"),
            "source_inspection_request_status": gap.get("source_inspection_request_status"),
            "source_inspection_request_ids": gap.get("source_inspection_request_ids") or [],
            "reason": gap.get("reason"),
            "location": _strict_location_from_fact(fact),
        })
    return out



def _data_dictionary_brief_from_fact(fact: Any) -> dict[str, Any] | None:
    props = fact.properties or {}
    if not props.get("entry_kind"):
        return None
    return {
        "name": fact.name,
        "entry_kind": props.get("entry_kind"),
        "container_name": props.get("container_name"),
        "table_name": props.get("table_name"),
        "schema_name": props.get("schema_name"),
        "qualified_table_name": props.get("qualified_table_name"),
        "attribute_name": props.get("attribute_name"),
        "attribute_type": props.get("attribute_type"),
        "description": props.get("description"),
        "constraints": props.get("constraints") or [],
        "source_type": props.get("source_type"),
        "source_set": props.get("source_set"),
        "is_test_source": props.get("is_test_source"),
        "evidence_level": props.get("evidence_maturity_level") or props.get("evidence_level"),
        "evidence": [_first_loc(fact.evidence)] if fact.evidence else [],
    }


def _external_dependency_brief_from_fact(fact: Any) -> dict[str, Any] | None:
    props = fact.properties or {}
    kind = props.get("dependency_kind")
    if not kind:
        return None
    return {
        "name": fact.name,
        "dependency_kind": kind,
        "client_class": props.get("client_class"),
        "client_receiver": props.get("client_receiver"),
        "client_receiver_type": props.get("client_receiver_type"),
        "declared_name": props.get("declared_name"),
        "declared_url": props.get("declared_url"),
        "declared_path": props.get("declared_path"),
        "endpoint_expression": props.get("endpoint_expression"),
        "endpoint_path": props.get("endpoint_path"),
        "base_url_property_key": props.get("base_url_property_key"),
        "method": props.get("method"),
        "operation": props.get("operation"),
        "request_payload_type": props.get("request_payload_type"),
        "response_payload_type": props.get("response_payload_type"),
        "source_set": props.get("source_set"),
        "is_test_source": props.get("is_test_source"),
        "evidence_level": props.get("evidence_maturity_level") or props.get("evidence_level"),
        "evidence": [_first_loc(fact.evidence)] if fact.evidence else [],
    }


def _sql_query_model_brief_from_fact(fact: Any) -> dict[str, Any] | None:
    props = fact.properties or {}
    if not props.get("source_tables") and fact.fact_type != "sql_query_model":
        return None
    return {
        "name": fact.name,
        "query_kind": props.get("query_kind"),
        "source_tables": props.get("source_tables") or [],
        "selected_fields": (props.get("selected_fields") or [])[:60],
        "calculated_fields": (props.get("calculated_fields") or [])[:30],
        "filters_preview": props.get("filters_preview"),
        "group_by_preview": props.get("group_by_preview"),
        "statement_preview": props.get("statement_preview"),
        "parser": props.get("parser"),
        "evidence_level": props.get("evidence_maturity_level") or props.get("evidence_level"),
        "evidence": [_first_loc(fact.evidence)] if fact.evidence else [],
    }


def _system_scenario_brief_from_fact(fact: Any) -> dict[str, Any] | None:
    props = fact.properties or {}
    if not props.get("scenario_id"):
        return None
    return {
        "scenario_id": props.get("scenario_id"),
        "operation": fact.name,
        "entrypoints": props.get("entrypoints") or [],
        "interfaces": props.get("interfaces") or [],
        "external_calls": props.get("external_calls") or [],
        "storage_touches": props.get("storage_touches") or [],
        "call_chain": (props.get("call_chain") or [])[:80],
        "reachable_operation_count": props.get("reachable_operation_count"),
        "composition_status": props.get("composition_status"),
        "composition_policy": props.get("composition_policy"),
        "scenario_evidence_kind": props.get("scenario_evidence_kind"),
        "evidence_level": props.get("evidence_maturity_level") or props.get("evidence_level"),
    }



def _storage_usage_summary_brief_from_fact(fact: Any) -> dict[str, Any] | None:
    props = fact.properties or {}
    sid = props.get("storage_usage_summary_id")
    if not sid:
        return None
    return {
        "storage_usage_summary_id": sid,
        "storage_target": props.get("storage_target") or fact.name,
        "access_count": props.get("access_count"),
        "read_count": props.get("read_count"),
        "write_count": props.get("write_count"),
        "mutation_count": props.get("mutation_count"),
        "operation_count": props.get("operation_count"),
        "operations": (props.get("operations") or [])[:30],
        "storage_methods": props.get("storage_methods") or [],
        "source_sets": props.get("source_sets") or [],
        "summary_basis": props.get("summary_basis"),
        "evidence_level": props.get("evidence_maturity_level") or props.get("evidence_level"),
        "evidence": [_first_loc(fact.evidence)] if fact.evidence else [],
    }


def _scenario_storage_summary_brief_from_fact(fact: Any) -> dict[str, Any] | None:
    props = fact.properties or {}
    sid = props.get("scenario_storage_summary_id")
    if not sid:
        return None
    return {
        "scenario_storage_summary_id": sid,
        "operation": props.get("operation") or fact.name,
        "entrypoints": props.get("entrypoints") or [],
        "read_storage_targets": props.get("read_storage_targets") or [],
        "write_storage_targets": props.get("write_storage_targets") or [],
        "mutation_storage_targets": props.get("mutation_storage_targets") or [],
        "storage_touches": (props.get("storage_touches") or [])[:30],
        "trace_samples": (props.get("trace_samples") or [])[:12],
        "external_calls": (props.get("external_calls") or [])[:12],
        "summary_basis": props.get("summary_basis"),
        "evidence_level": props.get("evidence_maturity_level") or props.get("evidence_level"),
        "evidence": [_first_loc(fact.evidence)] if fact.evidence else [],
    }


def _declared_value_set_summary_brief_from_fact(fact: Any) -> dict[str, Any] | None:
    props = fact.properties or {}
    summary_id = props.get("declared_value_set_summary_id")
    if not summary_id:
        return None
    return {
        "declared_value_set_summary_id": summary_id,
        "declared_value_set_id": props.get("declared_value_set_id"),
        "name": props.get("name") or fact.name,
        "display_name": props.get("display_name") or props.get("name") or fact.name,
        "syntax_kind": props.get("syntax_kind"),
        "location_kind": props.get("location_kind"),
        "source_set": props.get("source_set"),
        "entries_count": props.get("entries_count"),
        "sample_entries": (props.get("sample_entries") or [])[:12],
        "key_type": props.get("key_type"),
        "value_type": props.get("value_type"),
        "extraction_truncated": bool(props.get("extraction_truncated")),
        "truncation_reason": props.get("truncation_reason"),
        "retrieval": props.get("retrieval"),
        "summary_policy": props.get("summary_policy"),
        "evidence": [_first_loc(fact.evidence)] if fact.evidence else [],
    }

def _jooq_batch_write_summary_brief_from_fact(fact: Any) -> dict[str, Any] | None:
    props = fact.properties or {}
    sid = props.get("jooq_batch_write_summary_id")
    if not sid:
        return None
    return {
        "jooq_batch_write_summary_id": sid,
        "jooq_batch_bind_mapping_id": props.get("jooq_batch_bind_mapping_id"),
        "operation": props.get("operation"),
        "class_name": props.get("class_name"),
        "method_name": props.get("method_name"),
        "storage_table": props.get("storage_table"),
        "mapping_kind": props.get("mapping_kind"),
        "write_fields": (props.get("write_fields") or [])[:32],
        "summary_basis": props.get("summary_basis"),
        "evidence_level": props.get("evidence_maturity_level") or props.get("evidence_level"),
        "evidence": [_first_loc(fact.evidence)] if fact.evidence else [],
    }


def build_navigation(
    result: AnalysisResult,
    out_dir: str | Path,
    *,
    max_items: int = 500,
    max_fields_per_schema: int = 16,
    max_first_pass_candidates: int = 20,
    max_first_pass_schemas: int = 40,
    progress_path: Path | None = None,
) -> dict[str, Any]:
    """Build machine-first navigation artifacts.

    Only slim machine indexes stay in compact/navigation.json.
    The LLM initial prompt must use compact/first_pass.json instead: it is
    intentionally small and contains only summaries plus ranked candidate flows.
    Detailed facts and source snippets are retrieved lazily through the evidence provider; LLM-facing evidence tool usage is defined only in shared prompt fragments.
    """
    started = time.perf_counter()
    phase_events: list[dict[str, Any]] = []

    def progress(phase: str, status: str, data: dict[str, Any] | None = None) -> None:
        event = {
            "phase": phase,
            "status": status,
            "elapsed_ms": int((time.perf_counter() - started) * 1000),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        if data:
            event.update(data)
        phase_events.append(event)
        if progress_path is not None:
            write_json(progress_path, {
                "artifact": "compact_package_progress",
                "status": status if status in {"done", "failed"} else "running",
                "current_phase": phase,
                "elapsed_ms": event["elapsed_ms"],
                "last_event": event,
                "events": phase_events[-120:],
            })

    out = Path(out_dir)
    compact_dir = out / "compact"
    compact_dir.mkdir(parents=True, exist_ok=True)
    catalog_dir = out / "catalog"
    catalog_dir.mkdir(parents=True, exist_ok=True)

    progress("fact_brief_extraction", "running", {"fact_count": len(result.facts)})
    operations: dict[str, dict[str, Any]] = {}
    interfaces_by_operation: dict[str, list[dict[str, Any]]] = defaultdict(list)
    interface_items: list[dict[str, Any]] = []
    data_flow_items: list[dict[str, Any]] = []
    field_flow_items: list[dict[str, Any]] = []
    field_occurrence_catalog_items: list[dict[str, Any]] = []
    field_flow_edge_catalog_items: list[dict[str, Any]] = []
    field_lineage_items: list[dict[str, Any]] = []
    output_field_provenance_items: list[dict[str, Any]] = []
    call_chain_diagnostic_items: list[dict[str, Any]] = []
    ingress_items: list[dict[str, Any]] = []
    call_items: list[dict[str, Any]] = []
    storage_access_items: list[dict[str, Any]] = []
    access_boundary_items: list[dict[str, Any]] = []
    trace_items: list[dict[str, Any]] = []
    declared_value_set_items: list[dict[str, Any]] = []
    data_source_items: list[dict[str, Any]] = []
    persistent_write_items: list[dict[str, Any]] = []
    source_to_storage_lineage_items: list[dict[str, Any]] = []
    storage_to_access_lineage_items: list[dict[str, Any]] = []
    stored_field_to_response_mapping_items: list[dict[str, Any]] = []
    storage_lineage_gap_items: list[dict[str, Any]] = []
    source_inspection_request_items: list[dict[str, Any]] = []
    persistent_structure_items: list[dict[str, Any]] = []
    attribute_occurrence_items: list[dict[str, Any]] = []
    attribute_mapping_items: list[dict[str, Any]] = []
    attribute_derivation_items: list[dict[str, Any]] = []
    data_model_lineage_gap_items: list[dict[str, Any]] = []
    data_dictionary_items: list[dict[str, Any]] = []
    external_dependency_items: list[dict[str, Any]] = []
    sql_query_model_items: list[dict[str, Any]] = []
    system_scenario_items: list[dict[str, Any]] = []
    storage_usage_summary_items: list[dict[str, Any]] = []
    scenario_storage_summary_items: list[dict[str, Any]] = []
    declared_value_set_summary_items: list[dict[str, Any]] = []
    jooq_batch_write_summary_items: list[dict[str, Any]] = []
    db_schema_table_items: list[dict[str, Any]] = []
    db_schema_column_items: list[dict[str, Any]] = []
    db_schema_key_items: list[dict[str, Any]] = []
    db_schema_relationship_items: list[dict[str, Any]] = []
    db_schema_index_items: list[dict[str, Any]] = []
    db_schema_trigger_items: list[dict[str, Any]] = []
    db_schema_sequence_items: list[dict[str, Any]] = []
    db_schema_constraint_items: list[dict[str, Any]] = []
    db_schema_partitioning_items: list[dict[str, Any]] = []
    strict_confirmed_evidence_items: list[dict[str, Any]] = []
    strict_candidate_signal_items: list[dict[str, Any]] = []
    strict_unresolved_gap_items: list[dict[str, Any]] = []

    facts_by_type: Counter[str] = Counter()
    for fact in result.facts:
        facts_by_type[fact.fact_type] += 1
        props = fact.properties or {}
        if isinstance(props.get("evidence_maturity_dimensions"), dict):
            confirmed_item = _confirmed_evidence_item_from_fact(fact)
            if confirmed_item:
                strict_confirmed_evidence_items.append(confirmed_item)
        if isinstance(props.get("candidate_signals"), list):
            strict_candidate_signal_items.extend(_candidate_signal_items_from_fact(fact))
        if isinstance(props.get("unresolved_gap_lifecycle"), list):
            strict_unresolved_gap_items.extend(_unresolved_gap_items_from_fact(fact))
        if fact.fact_type == "source_to_sink_flow":
            flow_item = _flow_brief_from_fact(fact)
            if flow_item:
                data_flow_items.append(flow_item)
        if fact.fact_type == "field_identifier_flow":
            field_item = _field_flow_brief_from_fact(fact)
            if field_item:
                field_flow_items.append(field_item)
        if fact.fact_type == "field_occurrence":
            item = dict(props)
            item["evidence"] = [_first_loc(fact.evidence, include_snippet=False)] if fact.evidence else []
            field_occurrence_catalog_items.append(item)
        if fact.fact_type == "field_flow_edge":
            item = dict(props)
            item["evidence"] = [_first_loc(fact.evidence, include_snippet=False)] if fact.evidence else []
            field_flow_edge_catalog_items.append(item)
        if fact.fact_type == "field_lineage":
            lineage_item = _field_lineage_brief_from_fact(fact)
            if lineage_item:
                field_lineage_items.append(lineage_item)
        if fact.fact_type == "output_field_provenance":
            provenance_item = _output_field_provenance_brief_from_fact(fact)
            if provenance_item:
                output_field_provenance_items.append(provenance_item)
        if fact.fact_type == "call_chain_diagnostic":
            diag_item = _call_chain_diagnostic_brief_from_fact(fact)
            if diag_item:
                call_chain_diagnostic_items.append(diag_item)
        if fact.fact_type == "system_ingress":
            ingress_item = _ingress_brief_from_fact(fact)
            if ingress_item:
                ingress_items.append(ingress_item)
        if fact.fact_type == "method_call":
            call_item = _call_brief_from_fact(fact)
            if call_item:
                call_items.append(call_item)
        if fact.fact_type == "storage_access":
            storage_item = _storage_access_brief_from_fact(fact)
            if storage_item:
                storage_access_items.append(storage_item)
        if fact.fact_type == "access_boundary":
            access_item = _access_boundary_brief_from_fact(fact)
            if access_item:
                access_boundary_items.append(access_item)
        if fact.fact_type == "data_source":
            data_source_item = _data_source_brief_from_fact(fact)
            if data_source_item:
                data_source_items.append(data_source_item)
        if fact.fact_type == "persistent_write":
            persistent_write_item = _persistent_write_brief_from_fact(fact)
            if persistent_write_item:
                persistent_write_items.append(persistent_write_item)
        if fact.fact_type == "source_to_storage_lineage":
            source_to_storage_item = _source_to_storage_lineage_brief_from_fact(fact)
            if source_to_storage_item:
                source_to_storage_lineage_items.append(source_to_storage_item)
        if fact.fact_type == "storage_to_access_lineage":
            item = _storage_to_access_lineage_brief_from_fact(fact)
            if item:
                storage_to_access_lineage_items.append(item)
        if fact.fact_type == "stored_field_to_response_field_mapping":
            item = _stored_field_to_response_mapping_brief_from_fact(fact)
            if item:
                stored_field_to_response_mapping_items.append(item)
        if fact.fact_type == "storage_lineage_gap":
            gap_item = _storage_lineage_gap_brief_from_fact(fact)
            if gap_item:
                storage_lineage_gap_items.append(gap_item)
        if fact.fact_type == "source_inspection_request":
            inspection_item = _source_inspection_request_brief_from_fact(fact)
            if inspection_item:
                source_inspection_request_items.append(inspection_item)
        if fact.fact_type == "persistent_structure":
            item = _persistent_structure_brief_from_fact(fact)
            if item:
                persistent_structure_items.append(item)
        if fact.fact_type == "attribute_occurrence":
            item = _attribute_occurrence_brief_from_fact(fact)
            if item:
                attribute_occurrence_items.append(item)
        if fact.fact_type == "attribute_mapping":
            item = _attribute_mapping_brief_from_fact(fact)
            if item:
                attribute_mapping_items.append(item)
        if fact.fact_type == "attribute_derivation":
            item = _attribute_derivation_brief_from_fact(fact)
            if item:
                attribute_derivation_items.append(item)
        if fact.fact_type == "data_model_lineage_gap":
            item = _data_model_lineage_gap_brief_from_fact(fact)
            if item:
                data_model_lineage_gap_items.append(item)
        if fact.fact_type == "data_dictionary_entry":
            item = _data_dictionary_brief_from_fact(fact)
            if item:
                data_dictionary_items.append(item)
        if fact.fact_type in {"external_dependency", "external_dependency_call"}:
            item = _external_dependency_brief_from_fact(fact)
            if item:
                external_dependency_items.append(item)
        if fact.fact_type == "sql_query_model":
            item = _sql_query_model_brief_from_fact(fact)
            if item:
                sql_query_model_items.append(item)
        if fact.fact_type == "system_scenario_candidate":
            item = _system_scenario_brief_from_fact(fact)
            if item:
                system_scenario_items.append(item)
        if fact.fact_type == "storage_usage_summary":
            item = _storage_usage_summary_brief_from_fact(fact)
            if item:
                storage_usage_summary_items.append(item)
        if fact.fact_type == "scenario_storage_summary":
            item = _scenario_storage_summary_brief_from_fact(fact)
            if item:
                scenario_storage_summary_items.append(item)
        if fact.fact_type == "declared_value_set_summary":
            item = _declared_value_set_summary_brief_from_fact(fact)
            if item:
                declared_value_set_summary_items.append(item)
        if fact.fact_type == "jooq_batch_write_summary":
            item = _jooq_batch_write_summary_brief_from_fact(fact)
            if item:
                jooq_batch_write_summary_items.append(item)
        if fact.fact_type.startswith("db_schema_"):
            item = _db_schema_item_brief_from_fact(fact)
            if item:
                if fact.fact_type == "db_schema_table":
                    db_schema_table_items.append(item)
                elif fact.fact_type == "db_schema_column":
                    db_schema_column_items.append(item)
                elif fact.fact_type == "db_schema_key":
                    db_schema_key_items.append(item)
                elif fact.fact_type == "db_schema_relationship":
                    db_schema_relationship_items.append(item)
                elif fact.fact_type == "db_schema_index":
                    db_schema_index_items.append(item)
                elif fact.fact_type == "db_schema_trigger":
                    db_schema_trigger_items.append(item)
                elif fact.fact_type == "db_schema_sequence":
                    db_schema_sequence_items.append(item)
                elif fact.fact_type == "db_schema_constraint":
                    db_schema_constraint_items.append(item)
                elif fact.fact_type == "db_schema_partitioning":
                    db_schema_partitioning_items.append(item)
        if fact.fact_type == "data_trace":
            trace_item = _trace_brief_from_fact(fact)
            if trace_item:
                trace_items.append(trace_item)
        if fact.fact_type == "declared_value_set":
            ref_item = _declared_value_set_brief_from_fact(fact)
            if ref_item:
                declared_value_set_items.append(ref_item)
    incoming_field_flow_edges: Counter[str] = Counter()
    outgoing_field_flow_edges: Counter[str] = Counter()
    edge_ids_by_occurrence: dict[str, list[str]] = defaultdict(list)
    for edge in field_flow_edge_catalog_items:
        source_id = str(edge.get("source_occurrence_id") or "")
        target_id = str(edge.get("target_occurrence_id") or "")
        edge_id = str(edge.get("edge_id") or "")
        if source_id:
            outgoing_field_flow_edges[source_id] += 1
            if edge_id:
                edge_ids_by_occurrence[source_id].append(edge_id)
        if target_id:
            incoming_field_flow_edges[target_id] += 1
            if edge_id:
                edge_ids_by_occurrence[target_id].append(edge_id)

    field_flow_index_items: list[dict[str, Any]] = []
    boundary_field_flow_index_items: list[dict[str, Any]] = []
    for occurrence in sorted(field_occurrence_catalog_items, key=lambda x: str(x.get("occurrence_id") or "")):
        occurrence_id = str(occurrence.get("occurrence_id") or "")
        compact_item = {
            "occurrence_id": occurrence_id,
            "relative_file": occurrence.get("relative_file"),
            "operation": occurrence.get("operation"),
            "occurrence_kind": occurrence.get("occurrence_kind"),
            "symbol": occurrence.get("symbol"),
            "field_path": occurrence.get("field_path"),
            # Resolved is the default and is omitted to keep this repository-local
            # navigation index small. Full type/status/AST details remain in catalog/.
            "resolution_status": occurrence.get("resolution_status")
            if occurrence.get("resolution_status") not in (None, "", "resolved") else None,
            "boundary_direction": occurrence.get("boundary_direction"),
            "boundary_kind": occurrence.get("boundary_kind"),
            "boundary_name": occurrence.get("boundary_name"),
            "boundary_path": occurrence.get("boundary_path"),
            "payload_type": occurrence.get("payload_type"),
            "payload_role": occurrence.get("payload_role"),
            "java_field_name": occurrence.get("java_field_name"),
            "wire_field_path": occurrence.get("wire_field_path"),
            "serialized_name_basis": occurrence.get("serialized_name_basis"),
            "serialization_library": occurrence.get("serialization_library"),
            "field_binding_kind": occurrence.get("field_binding_kind"),
            "field_binding_basis": occurrence.get("field_binding_basis"),
            "incoming_edge_count": int(incoming_field_flow_edges.get(occurrence_id, 0)),
            "outgoing_edge_count": int(outgoing_field_flow_edges.get(occurrence_id, 0)),
        }
        compact_item = {k: v for k, v in compact_item.items() if v not in (None, "", [], {})}
        field_flow_index_items.append(compact_item)
        if occurrence.get("occurrence_kind") in {"inbound_payload", "outbound_payload", "boundary_field"}:
            boundary_field_flow_index_items.append({
                **compact_item,
                "direct_edge_ids": sorted(set(edge_ids_by_occurrence.get(occurrence_id) or [])),
            })

    field_flow_edge_index_items: list[dict[str, Any]] = []
    for edge in sorted(field_flow_edge_catalog_items, key=lambda x: str(x.get("edge_id") or "")):
        guards = []
        for guard in edge.get("guards") or []:
            if isinstance(guard, dict):
                guards.append({
                    "expression_text": guard.get("expression_text"),
                    "branch": guard.get("branch"),
                })
        item = {
            "edge_id": edge.get("edge_id"),
            "source_occurrence_id": edge.get("source_occurrence_id"),
            "target_occurrence_id": edge.get("target_occurrence_id"),
            "edge_kind": edge.get("edge_kind"),
            "resolution_status": edge.get("resolution_status")
            if edge.get("resolution_status") not in (None, "", "resolved") else None,
            # Guard expressions and source locations are intentionally addressable
            # through catalog/field_flow_edges.json or field_flow_edge().
            "conditional_branch": edge.get("conditional_branch"),
        }
        field_flow_edge_index_items.append({k: v for k, v in item.items() if v not in (None, "", [], {})})

    progress("fact_brief_extraction", "done", {
        "facts_by_type": dict(sorted(facts_by_type.items())),
        "persistent_writes": len(persistent_write_items),
        "source_to_storage_lineages": len(source_to_storage_lineage_items),
        "attribute_mappings": len(attribute_mapping_items),
        "attribute_derivations": len(attribute_derivation_items),
        "field_occurrences": len(field_occurrence_catalog_items),
        "field_flow_edges": len(field_flow_edge_catalog_items),
    })

    progress("interface_and_schema_catalogs", "running", {"interface_count": len(result.interfaces), "schema_count": len(result.schemas)})
    for idx, i in enumerate(result.interfaces, 1):
        iid = f"interface_{idx:06d}"
        direction = _enum_value(i.direction)
        kind = _enum_value(i.kind)
        op_key = i.operation or i.name or iid
        item = {
            "id": iid,
            "name": i.name,
            "direction": direction,
            "kind": kind,
            "schema_ref": i.schema_ref,
            "operation": i.operation,
            "path": i.path,
            "method": i.method,
            "properties": _interface_properties_brief(i.properties),
            "evidence": [_first_loc(i.evidence)] if i.evidence else [],
        }
        interface_items.append(item)
        interfaces_by_operation[op_key].append(item)

    for idx, (op_key, items) in enumerate(sorted(interfaces_by_operation.items()), 1):
        oid = f"operation_{idx:06d}"
        directions = sorted({x["direction"] for x in items})
        kinds = sorted({x["kind"] for x in items})
        operations[oid] = {
            "id": oid,
            "operation": op_key,
            "directions": directions,
            "kinds": kinds,
            "interfaces": [x["id"] for x in items],
            "interface_names": [x["name"] for x in items],
            "schemas": sorted({x.get("schema_ref") for x in items if x.get("schema_ref")}),
        }

    schema_items: list[dict[str, Any]] = []
    schema_by_name: dict[str, Any] = {}
    schema_by_id: dict[str, Any] = {}
    for idx, s in enumerate(result.schemas, 1):
        sid = f"schema_{idx:06d}"
        existing_schema = schema_by_name.get(s.name)
        if existing_schema is None or (s.source_type == "openapi_schema" and getattr(existing_schema, "source_type", None) != "openapi_schema"):
            schema_by_name[s.name] = s
        schema_by_id[sid] = s
        schema_items.append({
            "id": sid,
            **_schema_brief(s, max_fields=max_fields_per_schema),
        })

    config_values: dict[str, list[Any]] = {}
    for fact in result.config_facts:
        if getattr(fact, "fact_type", None) != "config_property":
            continue
        key = str(fact.name)
        value = (fact.properties or {}).get("value")
        if value is not None and value not in config_values.setdefault(key, []):
            config_values[key].append(value)
    system_interface_catalog_items = [
        _system_interface_catalog_item(item, schema_by_name, config_values)
        for item in interface_items
    ] + access_boundary_items
    # Production-first catalog for cross-system/interface work. Test boundaries are
    # preserved for diagnostics but excluded from production_interfaces by default.
    system_interface_catalog = {
        "artifact": "system_interface_catalog",
        "contract_version": "1.0",
        "catalog_policy": "production_first_direct_interface_evidence_no_business_inference",
        "summary": _system_interface_catalog_summary(system_interface_catalog_items),
        "production_interfaces": [x for x in system_interface_catalog_items if not x.get("is_test_source")],
        "test_interfaces": [x for x in system_interface_catalog_items if x.get("is_test_source")],
        "all_interfaces": system_interface_catalog_items,
    }
    progress("interface_and_schema_catalogs", "done", {"operation_count": len(operations), "schema_items": len(schema_items), "system_interface_count": len(system_interface_catalog_items)})

    progress("navigation_payload_build", "running")
    relations_by_type = Counter(r.relation_type for r in result.relations)
    interfaces_by_kind = Counter(f"{_enum_value(i.direction)}:{_enum_value(i.kind)}" for i in result.interfaces)
    traces_by_status = Counter(str(x.get("trace_status")) for x in trace_items)
    traces_by_type = Counter(str(x.get("trace_type")) for x in trace_items)
    storage_by_access_kind = Counter(str(x.get("access_kind")) for x in storage_access_items)
    field_lineage_by_role = Counter(str(x.get("field_role")) for x in field_lineage_items)
    field_lineage_by_target = Counter(str(x.get("target_boundary")) for x in field_lineage_items if x.get("target_boundary"))
    output_provenance_by_boundary = Counter(str(x.get("published_boundary")) for x in output_field_provenance_items)
    output_provenance_by_origin = Counter(str(x.get("ultimate_origin_kind") or x.get("origin_kind")) for x in output_field_provenance_items)
    nested_output_provenance_count = sum(1 for x in output_field_provenance_items if x.get("nested_field_provenance"))
    call_chain_by_status = Counter(str(x.get("caller_status")) for x in call_chain_diagnostic_items)
    declared_value_sets_by_syntax_kind = Counter(str(x.get("syntax_kind")) for x in declared_value_set_items)
    declared_value_sets_by_source_set = Counter(str(x.get("source_set")) for x in declared_value_set_items)
    data_dictionary_by_kind = Counter(str(x.get("entry_kind")) for x in data_dictionary_items)
    external_dependencies_by_kind = Counter(str(x.get("dependency_kind")) for x in external_dependency_items)
    storage_usage_by_activity = Counter("written" if (x.get("write_count") or 0) else "read_only" for x in storage_usage_summary_items)
    declared_value_set_summaries_by_syntax_kind = Counter(str(x.get("syntax_kind")) for x in declared_value_set_summary_items)
    source_to_storage_by_source_kind = Counter(str(x.get("source_kind")) for x in source_to_storage_lineage_items)
    storage_lineage_gap_by_kind = Counter(str(x.get("gap_kind")) for x in storage_lineage_gap_items)
    storage_to_access_by_status = Counter(str(x.get("lineage_status")) for x in storage_to_access_lineage_items)
    persistent_write_by_target = Counter(str(x.get("storage_target")) for x in persistent_write_items if x.get("storage_target"))
    access_boundary_by_kind = Counter(str(x.get("boundary_kind")) for x in access_boundary_items)
    data_model_lineage_gap_by_kind = Counter(str(x.get("gap_kind")) for x in data_model_lineage_gap_items)
    strict_gap_actionability_counts = Counter(str(x.get("actionability")) for x in strict_unresolved_gap_items if x.get("actionability"))
    actionable_gap_count = strict_gap_actionability_counts.get("actionable", 0)
    exhausted_gap_count = strict_gap_actionability_counts.get("exhausted", 0)

    # Keep public navigation/first-pass artifacts bounded before strict sanitization.
    # Full strict views are already built from allowlisted fields below and are kept
    # complete for evidence tool search, but recursive sanitizer must not walk the same large
    # lists repeatedly on real applications.
    strict_confirmed_evidence_public = strict_confirmed_evidence_items[:max_items]
    strict_candidate_signal_public = strict_candidate_signal_items[:max_items]
    strict_unresolved_gap_public = strict_unresolved_gap_items[:max_items]
    source_inspection_request_public = source_inspection_request_items[:max_items]

    navigation = {
        "artifact": "compact_navigation",
        "contract_version": "1.0",
        "generation_policy": "machine_first_json_only_lazy_evidence",
        "navigation_mode": "bounded_real_app_safe",
        "listing_caps": {
            "navigation_items_per_catalog": max_items,
            "first_pass_candidates": max_first_pass_candidates,
            "first_pass_schemas": max_first_pass_schemas,
        },
        "repository": {
            "system_name": result.system_name,
            "project_code": result.project_code,
            "repo_path": result.repo_path,
            "stack": result.stack,
            "files_analyzed": result.files_analyzed,
        },
        "counts": {
            "interfaces": len(result.interfaces),
            "system_interface_catalog": len(system_interface_catalog_items),
            "system_interface_catalog_production": len(system_interface_catalog["production_interfaces"]),
            "system_interface_catalog_test": len(system_interface_catalog["test_interfaces"]),
            "operations": len(operations),
            "schemas": len(result.schemas),
            "relations": len(result.relations),
            "facts": len(result.facts),
            "data_flows": len(data_flow_items),
            "field_flows": len(field_flow_items),
            "field_lineages": len(field_lineage_items),
            "field_lineage_role_counts": dict(sorted(field_lineage_by_role.items())),
            "field_lineage_target_boundary_counts": dict(sorted(field_lineage_by_target.items())),
            "output_field_provenance": len(output_field_provenance_items),
            "output_field_provenance_boundary_counts": dict(sorted(output_provenance_by_boundary.items())),
            "output_field_provenance_origin_counts": dict(sorted(output_provenance_by_origin.items())),
            "nested_output_field_provenance": nested_output_provenance_count,
            "call_chain_diagnostics": len(call_chain_diagnostic_items),
            "call_chain_diagnostic_status_counts": dict(sorted(call_chain_by_status.items())),
            "ingress": len(ingress_items),
            "method_calls": len(call_items),
            "storage_accesses": len(storage_access_items),
            "traces": len(trace_items),
            "declared_value_sets": len(declared_value_set_items),
            "declared_value_sets_by_syntax_kind": dict(sorted(declared_value_sets_by_syntax_kind.items())),
            "declared_value_sets_by_source_set": dict(sorted(declared_value_sets_by_source_set.items())),
            "data_sources": len(data_source_items),
            "persistent_writes": len(persistent_write_items),
            "persistent_write_top_targets": dict(persistent_write_by_target.most_common(30)),
            "access_boundary_counts": dict(sorted(access_boundary_by_kind.items())),
            "source_to_storage_lineages": len(source_to_storage_lineage_items),
            "source_to_storage_lineage_source_kind_counts": dict(sorted(source_to_storage_by_source_kind.items())),
            "storage_to_access_lineages": len(storage_to_access_lineage_items),
            "storage_to_access_lineage_status_counts": dict(sorted(storage_to_access_by_status.items())),
            "stored_field_to_response_mappings": len(stored_field_to_response_mapping_items),
            "storage_lineage_gaps": len(storage_lineage_gap_items),
            "storage_lineage_gap_kind_counts": dict(sorted(storage_lineage_gap_by_kind.items())),
            "persistent_structures": len(persistent_structure_items),
            "attribute_occurrences": len(attribute_occurrence_items),
            "attribute_mappings": len(attribute_mapping_items),
            "attribute_derivations": len(attribute_derivation_items),
            "data_model_lineage_gaps": len(data_model_lineage_gap_items),
            "data_dictionary_entries": len(data_dictionary_items),
            "external_dependencies": len(external_dependency_items),
            "sql_query_models": len(sql_query_model_items),
            "system_scenarios": len(system_scenario_items),
            "storage_usage_summaries": len(storage_usage_summary_items),
            "storage_usage_by_activity": dict(sorted(storage_usage_by_activity.items())),
            "scenario_storage_summaries": len(scenario_storage_summary_items),
            "declared_value_set_summaries": len(declared_value_set_summary_items),
            "declared_value_set_summaries_by_syntax_kind": dict(sorted(declared_value_set_summaries_by_syntax_kind.items())),
            "jooq_batch_write_summaries": len(jooq_batch_write_summary_items),
            "db_schema_tables": len(db_schema_table_items),
            "db_schema_columns": len(db_schema_column_items),
            "db_schema_keys": len(db_schema_key_items),
            "db_schema_relationships": len(db_schema_relationship_items),
            "db_schema_indexes": len(db_schema_index_items),
            "db_schema_triggers": len(db_schema_trigger_items),
            "db_schema_sequences": len(db_schema_sequence_items),
            "db_schema_constraints": len(db_schema_constraint_items),
            "db_schema_partitioning": len(db_schema_partitioning_items),
            "data_model_lineage_gap_kind_counts": dict(sorted(data_model_lineage_gap_by_kind.items())),
            "trace_status_counts": dict(sorted(traces_by_status.items())),
            "trace_type_counts": dict(sorted(traces_by_type.items())),
            "storage_access_counts": dict(sorted(storage_by_access_kind.items())),
            "mapper_facts": len(result.mapper_facts),
            "config_facts": len(result.config_facts),
            "strict_confirmed_evidence": len(strict_confirmed_evidence_items),
            "strict_candidate_signals": len(strict_candidate_signal_items),
            "strict_unresolved_gaps": len(strict_unresolved_gap_items),
            "source_inspection_requests": len(source_inspection_request_items),
            "confirmed_evidence_count": len(strict_confirmed_evidence_items),
            "candidate_signal_count": len(strict_candidate_signal_items),
            "unresolved_gap_count": len(strict_unresolved_gap_items),
            "source_inspection_request_count": len(source_inspection_request_items),
            "actionable_gap_count": actionable_gap_count,
            "exhausted_gap_count": exhausted_gap_count,
            "gap_actionability_counts": dict(sorted(strict_gap_actionability_counts.items())),
        },
        "interface_summary": dict(sorted(interfaces_by_kind.items())),
        "fact_type_summary": dict(sorted(facts_by_type.items())),
        "relation_type_summary": dict(sorted(relations_by_type.items())),
        "operations": list(operations.values())[:max_items],
        "interfaces": interface_items[:max_items],
        "system_interface_catalog": system_interface_catalog["production_interfaces"][:max_items],
        "schemas": schema_items[:max_items],
        "data_flows": data_flow_items[:max_items],
        "field_flows": field_flow_items[:max_items],
        "field_lineages": field_lineage_items[:max_items],
        "output_field_provenance": output_field_provenance_items[:max_items],
        "call_chain_diagnostics": call_chain_diagnostic_items[:max_items],
        "ingress": ingress_items[:max_items],
        "method_calls": call_items[:max_items],
        "storage_accesses": storage_access_items[:max_items],
        "data_sources": data_source_items[:max_items],
        "persistent_writes": persistent_write_items[:max_items],
        "source_to_storage_lineages": source_to_storage_lineage_items[:max_items],
        "storage_to_access_lineages": storage_to_access_lineage_items[:max_items],
        "stored_field_to_response_mappings": stored_field_to_response_mapping_items[:max_items],
        "storage_lineage_gaps": storage_lineage_gap_items[:max_items],
        "persistent_structures": persistent_structure_items[:max_items],
        "attribute_occurrences": attribute_occurrence_items[:max_items],
        "attribute_mappings": attribute_mapping_items[:max_items],
        "attribute_derivations": attribute_derivation_items[:max_items],
        "data_model_lineage_gaps": data_model_lineage_gap_items[:max_items],
        "traces": trace_items[:max_items],
        "declared_value_sets": declared_value_set_items[:max_items],
        "strict_evidence_contract": {
            "primary_views": ["confirmed_evidence", "candidate_signals", "unresolved_gaps", "source_inspection_requests"],
            "maturity_levels": ["confirmed", "unresolved", "not_applicable"],
            "candidate_signals_are_evidence": False,
            "legacy_probability_fields_public": False,
            "gap_actionability_values": ["actionable", "not_actionable", "exhausted", "not_relevant"],
            "source_inspection_request_status_values": [
                "emitted",
                "required_but_not_emitted",
                "required_pending_request_link",
                "not_required",
                "not_required_exhausted_in_workspace",
                "not_created_no_concrete_target",
                "not_required_not_decision_blocking",
            ],
        },
        "confirmed_evidence": strict_confirmed_evidence_public,
        "candidate_signals": strict_candidate_signal_public,
        "unresolved_gaps": strict_unresolved_gap_public,
    }

    first_pass_operations: list[dict[str, Any]] = []
    referenced_schema_names: set[str] = set()
    for oid, op in operations.items():
        items = interfaces_by_operation.get(op.get("operation") or "", [])
        observations = _first_pass_observations(op, items)
        if not observations:
            continue
        referenced_schema_names.update(str(s) for s in op.get("schemas") or [] if s)
        first_pass_operations.append({
            "id": oid,
            "operation": op.get("operation"),
            "observed_signals": observations,
            "directions": op.get("directions"),
            "kinds": op.get("kinds"),
            "schemas": op.get("schemas"),
            "interfaces": [_interface_first_pass_item(x) for x in items],
        })
    first_pass_operations.sort(key=lambda x: (str(x.get("operation") or ""), str(x.get("id") or "")))
    first_pass_operations = first_pass_operations[:max_first_pass_candidates]
    ranked_flow_candidates = sorted(
        data_flow_items,
        key=lambda x: (
            str(x.get("operation") or ""),
            str(x.get("sink_kind") or ""),
            str(x.get("flow_id") or ""),
        ),
    )[:max_first_pass_candidates]
    referenced_schema_names = {s for c in first_pass_operations for s in (c.get("schemas") or [])}

    first_pass_schema_catalog: list[dict[str, Any]] = []
    for sid, s in schema_by_id.items():
        if s.name not in referenced_schema_names:
            continue
        first_pass_schema_catalog.append({
            "id": sid,
            **_schema_first_pass_brief(s),
        })
        if len(first_pass_schema_catalog) >= max_first_pass_schemas:
            break

    progress("navigation_payload_build", "done", {"navigation_items": len(navigation)})

    progress("first_pass_build", "running")
    first_pass = {
        "artifact": "llm_first_pass_package",
        "contract_version": "1.0",
        "package_policy": "small_llm_ready_index_only_no_core_files_no_full_schemas_no_relations_lazy_evidence",
        "repository": navigation["repository"],
        "counts": navigation["counts"],
        "interface_summary": navigation["interface_summary"],
        "fact_type_summary_top": dict(facts_by_type.most_common(25)),
        "relation_type_summary": navigation["relation_type_summary"],
        "strict_evidence_contract": navigation["strict_evidence_contract"],
        "confirmed_evidence": strict_confirmed_evidence_public[:max_first_pass_candidates],
        "candidate_signals": strict_candidate_signal_public[:max_first_pass_candidates],
        "unresolved_gaps": strict_unresolved_gap_public[:max_first_pass_candidates],
        "source_inspection_requests": source_inspection_request_public[:max_first_pass_candidates],
        "selection_policy": {
            "included": "deterministically ordered operations with observable technical signals; details require lazy evidence",
            "not_filtered_by_strength": True,
            "max_items": max_first_pass_candidates,
        },
        "observed_operations": first_pass_operations,
        "observed_data_flows": [_flow_first_pass_item(x) for x in ranked_flow_candidates],
        "observed_field_flows": [_field_flow_first_pass_item(x) for x in field_flow_items[:max_first_pass_candidates]],
        "observed_field_lineages": [_field_lineage_first_pass_item(x) for x in field_lineage_items[:max_first_pass_candidates]],
        "observed_output_field_provenance": [_output_field_provenance_first_pass_item(x) for x in output_field_provenance_items[:max_first_pass_candidates]],
        "observed_source_to_storage_lineages": source_to_storage_lineage_items[:max_first_pass_candidates],
        "observed_storage_lineage_gaps": storage_lineage_gap_items[:max_first_pass_candidates],
        "observed_persistent_structures": persistent_structure_items[:max_first_pass_candidates],
        "observed_attribute_mappings": attribute_mapping_items[:max_first_pass_candidates],
        "observed_attribute_derivations": attribute_derivation_items[:max_first_pass_candidates],
        "observed_data_model_lineage_gaps": data_model_lineage_gap_items[:max_first_pass_candidates],
        "observed_call_chain_diagnostics": [_call_chain_diagnostic_first_pass_item(x) for x in call_chain_diagnostic_items[:max_first_pass_candidates]],
        "observed_traces": [_trace_first_pass_item(x) for x in trace_items[:max_first_pass_candidates]],
        "declared_value_sets": [_declared_value_set_first_pass_item(x) for x in declared_value_set_items[:max_first_pass_candidates]],
        "referenced_schema_catalog": first_pass_schema_catalog,
    }

    progress("first_pass_build", "done", {"observed_operations": len(first_pass_operations), "referenced_schemas": len(first_pass_schema_catalog)})

    progress("package_manifest_build", "running")
    package_manifest = {
        "artifact": "compact_package_manifest",
        "contract_version": "1.0",
        "package_policy": "evidence_reference_catalog_no_snippets",
        "counts": {
            "operations_listed": len(operations),
            "interfaces_listed": len(interface_items),
            "system_interface_catalog_listed": len(system_interface_catalog_items),
            "system_interface_catalog_production_listed": len(system_interface_catalog["production_interfaces"]),
            "schemas_listed": len(schema_items),
            "data_flows_listed": len(data_flow_items),
            "field_flows_listed": len(field_flow_items),
            "field_occurrences_listed": len(field_flow_index_items),
            "field_flow_edges_listed": len(field_flow_edge_index_items),
            "boundary_field_flow_entries_listed": len(boundary_field_flow_index_items),
            "field_lineages_listed": len(field_lineage_items),
            "output_field_provenance_listed": len(output_field_provenance_items),
            "call_chain_diagnostics_listed": len(call_chain_diagnostic_items),
            "ingress_listed": len(ingress_items),
            "method_calls_listed": len(call_items),
            "storage_accesses_listed": len(storage_access_items),
            "traces_listed": len(trace_items),
            "declared_value_sets_listed": len(declared_value_set_items),
            "data_sources_listed": len(data_source_items),
            "persistent_writes_listed": len(persistent_write_items),
            "source_to_storage_lineages_listed": len(source_to_storage_lineage_items),
            "storage_lineage_gaps_listed": len(storage_lineage_gap_items),
            "source_inspection_requests_listed": len(source_inspection_request_items),
            "persistent_structures_listed": len(persistent_structure_items),
            "attribute_occurrences_listed": len(attribute_occurrence_items),
            "attribute_mappings_listed": len(attribute_mapping_items),
            "attribute_derivations_listed": len(attribute_derivation_items),
            "data_model_lineage_gaps_listed": len(data_model_lineage_gap_items),
            "data_dictionary_entries_listed": len(data_dictionary_items),
            "external_dependencies_listed": len(external_dependency_items),
            "sql_query_models_listed": len(sql_query_model_items),
            "system_scenarios_listed": len(system_scenario_items),
            "strict_confirmed_evidence_listed": len(strict_confirmed_evidence_items),
            "strict_candidate_signals_listed": len(strict_candidate_signal_items),
            "strict_unresolved_gaps_listed": len(strict_unresolved_gap_items),
        },
        "operations": [{"id": x["id"], "operation": x["operation"]} for x in operations.values()],
        "interfaces": [{"id": x["id"], "name": x["name"], "direction": x["direction"], "kind": x["kind"]} for x in interface_items],
        "system_interface_catalog": [{"interface_id": x.get("interface_id"), "direction": x.get("direction"), "boundary_kind": x.get("boundary_kind"), "operation": x.get("operation"), "endpoint_or_topic_resolved": x.get("endpoint_or_topic_resolved")} for x in system_interface_catalog["production_interfaces"]],
        "schemas": [{"id": x["id"], "name": x["name"]} for x in schema_items],
        "data_flows": [{"flow_id": x["flow_id"], "operation": x.get("operation"), "sink_kind": x.get("sink_kind")} for x in data_flow_items],
        "field_flows": [{"field_flow_id": x["field_flow_id"], "source_field": x.get("source_field"), "sink_channel": x.get("sink_channel"), "related_flow_id": x.get("related_flow_id")} for x in field_flow_items],
        "field_occurrences": [{"occurrence_id": x.get("occurrence_id"), "field_path": x.get("field_path"), "occurrence_kind": x.get("occurrence_kind")} for x in field_flow_index_items[:max_items]],
        "field_flow_edges": [{"edge_id": x.get("edge_id"), "source_occurrence_id": x.get("source_occurrence_id"), "target_occurrence_id": x.get("target_occurrence_id"), "edge_kind": x.get("edge_kind")} for x in field_flow_edge_index_items[:max_items]],
        "boundary_field_flow_index": [{"occurrence_id": x.get("occurrence_id"), "boundary_direction": x.get("boundary_direction"), "boundary_path": x.get("boundary_path")} for x in boundary_field_flow_index_items[:max_items]],
        "field_lineages": [{"field_lineage_id": x["field_lineage_id"], "source_field": x.get("source_field"), "field_role": x.get("field_role"), "target_boundary": x.get("target_boundary"), "target_field": x.get("target_field")} for x in field_lineage_items],
        "output_field_provenance": [{"output_field_provenance_id": x["output_field_provenance_id"], "published_boundary": x.get("published_boundary"), "published_field": x.get("published_field"), "origin_kind": x.get("origin_kind"), "nested_field_provenance": x.get("nested_field_provenance")} for x in output_field_provenance_items],
        "call_chain_diagnostics": [{"call_chain_diagnostic_id": x["call_chain_diagnostic_id"], "target_operation": x.get("target_operation"), "caller_status": x.get("caller_status")} for x in call_chain_diagnostic_items],
        "ingress": [{"ingress_id": x["ingress_id"], "origin_kind": x.get("origin_kind"), "operation": x.get("operation")} for x in ingress_items],
        "method_calls": [{
            "call_id": x["call_id"],
            "caller_operation_id": x.get("caller_operation_id"),
            "caller_operation_signature": x.get("caller_operation_signature"),
            "callee_operation_id": x.get("callee_operation_id"),
            "callee_operation_signature": x.get("callee_operation_signature"),
        } for x in call_items],
        "data_sources": [{"data_source_id": x["data_source_id"], "source_kind": x.get("source_kind"), "source_operation": x.get("source_operation"), "source_payload": x.get("source_payload")} for x in data_source_items],
        "source_inspection_requests": [{"source_inspection_request_id": x["source_inspection_request_id"], "reason": x.get("reason"), "priority": x.get("priority"), "target_operation": x.get("target_operation"), "target_symbol": x.get("target_symbol"), "target_callable": x.get("target_callable"), "focus": x.get("focus"), "related_evidence_refs": x.get("related_evidence_refs"), "search_tokens": x.get("search_tokens"), "suggested_evidence_tools": x.get("suggested_evidence_tools"), "iterative_follow_up_policy": x.get("iterative_follow_up_policy")} for x in source_inspection_request_items],
        "persistent_structures": [{"persistent_structure_id": x["persistent_structure_id"], "storage_kind": x.get("storage_kind"), "storage_target": x.get("storage_target"), "container_name": x.get("container_name")} for x in persistent_structure_items],
        "attribute_occurrences": [{"attribute_occurrence_id": x["attribute_occurrence_id"], "container_name": x.get("container_name"), "attribute_name": x.get("attribute_name"), "attribute_type": x.get("attribute_type")} for x in attribute_occurrence_items],
        "attribute_mappings": [{"attribute_mapping_id": x["attribute_mapping_id"], "source_field": x.get("source_field"), "target_field": x.get("target_field"), "mapping_kind": x.get("mapping_kind")} for x in attribute_mapping_items],
        "attribute_derivations": [{"attribute_derivation_id": x["attribute_derivation_id"], "target_field": x.get("target_field"), "derivation_kind": x.get("derivation_kind")} for x in attribute_derivation_items],
        "data_model_lineage_gaps": [{"data_model_lineage_gap_id": x["data_model_lineage_gap_id"], "gap_kind": x.get("gap_kind"), "container": x.get("container"), "field": x.get("field")} for x in data_model_lineage_gap_items],
        "traces": [{"trace_id": x["trace_id"], "trace_type": x.get("trace_type"), "trace_status": x.get("trace_status"), "terminal_operation_id": x.get("terminal_operation_id")} for x in trace_items],
        "declared_value_sets": [{"declared_value_set_id": x["declared_value_set_id"], "name": x.get("name"), "syntax_kind": x.get("syntax_kind"), "source_set": x.get("source_set"), "entries_count": x.get("entries_count"), "extraction_truncated": x.get("extraction_truncated")} for x in declared_value_set_items],
        "data_dictionary": [{"name": x.get("name"), "entry_kind": x.get("entry_kind"), "description": x.get("description")} for x in data_dictionary_items[:max_items]],
        "external_dependencies": [{"name": x.get("name"), "dependency_kind": x.get("dependency_kind"), "operation": x.get("operation")} for x in external_dependency_items[:max_items]],
        "system_scenarios": [{"scenario_id": x.get("scenario_id"), "operation": x.get("operation")} for x in system_scenario_items[:max_items]],
        "storage_usage_summaries": [{"storage_target": x.get("storage_target"), "read_count": x.get("read_count"), "write_count": x.get("write_count")} for x in storage_usage_summary_items[:max_items]],
        "scenario_storage_summaries": [{"operation": x.get("operation"), "read_storage_targets": x.get("read_storage_targets"), "write_storage_targets": x.get("write_storage_targets")} for x in scenario_storage_summary_items[:max_items]],
        "declared_value_set_summaries": [{"declared_value_set_summary_id": x.get("declared_value_set_summary_id"), "declared_value_set_id": x.get("declared_value_set_id"), "name": x.get("name"), "syntax_kind": x.get("syntax_kind"), "source_set": x.get("source_set"), "entries_count": x.get("entries_count")} for x in declared_value_set_summary_items[:max_items]],
        "jooq_batch_write_summaries": [{"operation": x.get("operation"), "storage_table": x.get("storage_table")} for x in jooq_batch_write_summary_items[:max_items]],
    }


    progress("package_manifest_build", "done", {"manifest_sections": len(package_manifest.get("catalogs", {})) if isinstance(package_manifest.get("catalogs"), dict) else 0})
    progress("sanitize_public_payloads", "running")
    navigation = sanitize_public_payload(navigation)
    first_pass = sanitize_public_payload(first_pass)
    package_manifest = sanitize_public_payload(package_manifest)
    progress("sanitize_public_payloads", "done")
    # The full strict views are generated from allowlisted fields by this module.
    # Avoid re-sanitizing them recursively here; that duplicated work dominated
    # compact_package time on large real-app runs without changing semantics.

    progress("write_primary_compact_artifacts", "running")
    write_json(compact_dir / "confirmed_evidence.json", strict_confirmed_evidence_items)
    write_json(compact_dir / "candidate_signals.json", strict_candidate_signal_items)
    write_json(compact_dir / "unresolved_gaps.json", strict_unresolved_gap_items)
    # Do not embed the four full views again.  On large repositories this file
    # duplicated tens of megabytes of already materialized JSON and could dominate
    # finalization time.  The canonical views remain separate artifacts; this file
    # is their compact discoverability manifest.
    write_json(compact_dir / "strict_evidence_views.json", {
        "artifact": "strict_evidence_views",
        "format_version": "2.0",
        "primary_views": {
            "confirmed_evidence": {
                "path": "confirmed_evidence.json",
                "count": len(strict_confirmed_evidence_items),
            },
            "candidate_signals": {
                "path": "candidate_signals.json",
                "count": len(strict_candidate_signal_items),
            },
            "unresolved_gaps": {
                "path": "unresolved_gaps.json",
                "count": len(strict_unresolved_gap_items),
            },
            "source_inspection_requests": {
                "path": "source_inspection_requests.json",
                "count": len(source_inspection_request_items),
            },
        },
        "policy": "LLM should start from these four referenced views before opening legacy fact-type catalogs",
    })

    write_json(compact_dir / "system_interface_catalog.json", system_interface_catalog)
    write_json(compact_dir / "access_boundaries.json", access_boundary_items)
    write_json(compact_dir / "data_flows.json", data_flow_items)
    write_json(compact_dir / "field_flows.json", field_flow_items)
    _write_compact_json(compact_dir / "field_flow_index.json", field_flow_index_items)
    _write_compact_json(compact_dir / "field_flow_edges.json", field_flow_edge_index_items)
    write_json(compact_dir / "boundary_field_flow_index.json", boundary_field_flow_index_items)
    _write_compact_json(catalog_dir / "field_occurrences.json", field_occurrence_catalog_items)
    _write_compact_json(catalog_dir / "field_flow_edges.json", field_flow_edge_catalog_items)
    write_json(compact_dir / "field_lineage.json", field_lineage_items)
    write_json(compact_dir / "output_field_provenance.json", output_field_provenance_items)
    write_json(compact_dir / "call_chain_diagnostics.json", call_chain_diagnostic_items)
    write_json(compact_dir / "ingress.json", ingress_items)
    write_json(compact_dir / "method_calls.json", call_items)
    write_json(compact_dir / "storage_accesses.json", storage_access_items)
    write_json(compact_dir / "data_sources.json", data_source_items)
    write_json(compact_dir / "persistent_writes.json", persistent_write_items)
    write_json(compact_dir / "source_to_storage_lineage.json", source_to_storage_lineage_items)
    write_json(compact_dir / "storage_to_access_lineage.json", storage_to_access_lineage_items)
    write_json(compact_dir / "stored_field_to_response_field_mappings.json", stored_field_to_response_mapping_items)
    write_json(compact_dir / "storage_lineage_gaps.json", storage_lineage_gap_items)
    write_json(compact_dir / "source_inspection_requests.json", source_inspection_request_items)
    write_json(compact_dir / "persistent_structures.json", persistent_structure_items)
    write_json(compact_dir / "attribute_occurrences.json", attribute_occurrence_items)
    write_json(compact_dir / "attribute_mappings.json", attribute_mapping_items)
    write_json(compact_dir / "attribute_derivations.json", attribute_derivation_items)
    write_json(compact_dir / "data_model_lineage_gaps.json", data_model_lineage_gap_items)
    write_json(compact_dir / "traces.json", trace_items)
    write_json(compact_dir / "declared_value_sets.json", declared_value_set_items)
    write_json(compact_dir / "data_dictionary.json", data_dictionary_items)
    write_json(compact_dir / "external_dependencies.json", external_dependency_items)
    write_json(compact_dir / "sql_query_models.json", sql_query_model_items)
    write_json(compact_dir / "system_scenarios.json", system_scenario_items)
    write_json(compact_dir / "storage_usage_summaries.json", storage_usage_summary_items)
    write_json(compact_dir / "scenario_storage_summaries.json", scenario_storage_summary_items)
    write_json(compact_dir / "declared_value_set_summaries.json", declared_value_set_summary_items)
    write_json(compact_dir / "jooq_batch_write_summaries.json", jooq_batch_write_summary_items)
    progress("write_primary_compact_artifacts", "done")

    domain_summaries = _build_domain_summaries(
        db_tables=db_schema_table_items,
        db_columns=db_schema_column_items,
        interfaces=system_interface_catalog["production_interfaces"],
        system_scenarios=system_scenario_items,
        storage_usage=storage_usage_summary_items,
        persistent_writes=persistent_write_items,
        source_to_storage=source_to_storage_lineage_items,
        access_boundaries=access_boundary_items,
        storage_to_access=storage_to_access_lineage_items,
        external_dependencies=external_dependency_items,
        declared_value_sets=declared_value_set_summary_items or declared_value_set_items,
        transformations=attribute_derivation_items,
    )

    progress("write_final_compact_artifacts", "running")
    write_json(compact_dir / "system_description_compact.json", {
        "artifact": "system_description_compact",
        "summary": {
            "data_dictionary_entries": len(data_dictionary_items),
            "data_dictionary_by_kind": dict(sorted(data_dictionary_by_kind.items())),
            "external_dependencies": len(external_dependency_items),
            "external_dependencies_by_kind": dict(sorted(external_dependencies_by_kind.items())),
            "system_scenarios": len(system_scenario_items),
            "storage_usage_summaries": len(storage_usage_summary_items),
            "scenario_storage_summaries": len(scenario_storage_summary_items),
            "declared_value_set_summaries": len(declared_value_set_summary_items),
            "jooq_batch_write_summaries": len(jooq_batch_write_summary_items),
            "db_schema_tables": len(db_schema_table_items),
            "db_schema_columns": len(db_schema_column_items),
            "db_schema_keys": len(db_schema_key_items),
            "db_schema_relationships": len(db_schema_relationship_items),
            "db_schema_indexes": len(db_schema_index_items),
            "db_schema_triggers": len(db_schema_trigger_items),
            "db_schema_sequences": len(db_schema_sequence_items),
            "db_schema_constraints": len(db_schema_constraint_items),
            "db_schema_partitioning": len(db_schema_partitioning_items),
            "sql_query_models": len(sql_query_model_items),
            "attribute_derivations": len(attribute_derivation_items),
        },
        "data_dictionary": data_dictionary_items[:max_items],
        "interfaces": system_interface_catalog["production_interfaces"][:max_items],
        "external_dependencies": external_dependency_items[:max_items],
        "system_scenarios": system_scenario_items[:max_items],
        "storage_usage_summaries": storage_usage_summary_items[:max_items],
        "scenario_storage_summaries": scenario_storage_summary_items[:max_items],
        "declared_value_set_summaries": declared_value_set_summary_items[:max_items],
        "jooq_batch_write_summaries": jooq_batch_write_summary_items[:max_items],
        "persistent_writes": persistent_write_items[:max_items],
        "source_to_storage_lineage": source_to_storage_lineage_items[:max_items],
        "access_boundaries": access_boundary_items[:max_items],
        "storage_to_access_lineage": storage_to_access_lineage_items[:max_items],
        "stored_field_to_response_field_mappings": stored_field_to_response_mapping_items[:max_items],
        "domain_summaries": domain_summaries[:max_items],
        "attribute_derivations": attribute_derivation_items[:max_items],
        "sql_query_models": sql_query_model_items[:max_items],
        "declared_value_sets": declared_value_set_items[:max_items],
        "policy": "compact evidence pack for LLM system description; no business conclusions or inferred source-of-truth",
    })
    write_json(compact_dir / "navigation.json", navigation)
    write_json(compact_dir / "first_pass.json", first_pass)
    write_json(compact_dir / "package_manifest.json", package_manifest)
    write_json(out / "diagnostics" / "scanner_status_summary.json", _scanner_status_summary(result))
    progress("write_final_compact_artifacts", "done")
    progress("done", "done", {"elapsed_ms": int((time.perf_counter() - started) * 1000)})
    return navigation
