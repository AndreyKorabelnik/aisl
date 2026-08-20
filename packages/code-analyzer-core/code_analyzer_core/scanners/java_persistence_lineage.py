from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from collections import defaultdict, Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from code_analyzer_core.models import Fact, EvidenceRef
from code_analyzer_core.scanners.java_trace_common import *
from code_analyzer_core.scanners.java_call_observations import *
from code_analyzer_core.evidence_contract import maturity_props as _maturity_props
from code_analyzer_core.utils import read_text, line_number_for_offset, normalize_name, write_json
from code_analyzer_core.scanners.java_syntax import parse_java_files, class_annotations_text, split_java_arguments, method_syntax_dict, java_type_shape, annotation_args_map as _ts_annotation_args_map, unquote_annotation_value as _ts_unquote_annotation_value, annotation_string_arg as _ts_annotation_string_arg
from code_analyzer_core.scanners.java_flow_builder import (
    _looks_like_outbound_receiver,
    _sink_matches_from_method_info,
    _parse_params,
    _parameter_names,
    _clean_expression,
    _contains_symbol,
    _assignment_map,
    _synthetic_method_for_body,
    _source_param_for_payload,
    _normalize_java_type,
    _class_name_for_position,
    _getter_field,
    _field_role,
    _return_expressions_from_method_info,
)
from code_analyzer_core.scanners.java_field_lineage import *
from code_analyzer_core.scanners.java_output_provenance import *
from code_analyzer_core.scanners.java_persistence_jooq import (
    _jooq_batch_variable_links,
    _jooq_bind_placeholder,
    _jooq_field_constant_to_column,
    _jooq_inline_statement_from_expression,
    _jooq_set_slots_from_chain,
    _jooq_table_constant,
    _jooq_update_statement_slots,
    _jooq_where_slots_from_chain,
)
from code_analyzer_core.scanners.java_persistence_mapping_resolvers import (
    _annotation_string_arg,
    _builder_field_mapping_facts,
    _factory_method_mapping_facts,
    _mapstruct_mapper_signature_facts,
    _mapstruct_mapping_annotations,
    _mapper_method_signatures,
    _mapper_signature_for_expression,
    _source_scope_for_file,
    _stream_collection_lineage_facts,
)
from code_analyzer_core.scanners.java_evidence_pipeline import (
    _attach_source_inspection_links,
    _candidate_signals_for_access,
    _end_to_end_trace_maturity,
    _field_mapping_gap_diagnostic,
    _field_mapping_maturity,
    _inspection_key,
    _physical_storage_maturity_for_access,
    _storage_resolution_level_for_access,
    _persistence_maturity_for_access,
    _source_boundary_maturity,
    _source_inspection_request_fact,
)


def _technical_source_kind(origin_kind: str | None, *, fallback: str = "unknown") -> str:
    """Map internal provenance kinds to neutral technical source kinds.

    This intentionally does not classify sources as own/foreign or risky.
    """
    value = str(origin_kind or "")
    if value in {"rest_controller", "rest_ingress", "ingress_field"}:
        return "rest_ingress"
    if value in {"kafka_listener", "kafka_ingress", "kafka_consumed_field"}:
        return "kafka_consumed"
    if value in {"external_service_response_field", "external_service_response"}:
        return "external_service_response"
    if value in {"db_read_field", "repository_result_field"}:
        return "storage_read"
    if value == "cache_read_field":
        return "cache_read"
    if value == "computed":
        return "computed"
    if value == "constant":
        return "constant"
    if value in {"method_input", "method_parameter", "collection_element"}:
        return "method_input"
    return fallback


# Strict Java evidence public-contract helpers live in java_evidence_pipeline.
# java_trace_builder should focus on raw Java observations and local trace extraction.

def _storage_resolution_status_for_access(access: dict[str, Any]) -> str:
    return str(access.get("storage_resolution_status") or "unknown")


def _persistence_missing_links_for_access(access: dict[str, Any]) -> list[str]:
    level = _storage_resolution_level_for_access(access)
    status = _storage_resolution_status_for_access(access)
    links: list[str] = []
    if level == "custom_dao_boundary" or status == "dao_implementation_not_resolved":
        links.extend(["dao_implementation_not_resolved", "physical_table_not_resolved"])
    return links



def _data_source_fact(source_id: str, *, source_kind: str, operation: str | None, payload: str | None, fields: list[dict[str, Any]], evidence: list[EvidenceRef], payload_resolution_status: str | None = None, payload_resolution_basis: list[dict[str, Any]] | None = None) -> Fact:
    props = {
        "data_source_id": source_id,
        "source_kind": source_kind,
        "source_operation": operation,
        "source_payload": payload or "unknown",
        "source_fields": fields,
        "source_field_count": len(fields),
        "payload_resolution_status": payload_resolution_status or "unknown",
        "payload_resolution_basis": payload_resolution_basis or [],
        "classification_policy": "technical_source_kind_only_no_own_foreign_decision",
    }
    return Fact(
        fact_type="data_source",
        name=f"{source_kind} {operation or 'unknown'} {payload or 'unknown'}",
        properties=props,
        evidence=evidence,
    )


def _persistent_write_fact(write_id: str, access: dict[str, Any], *, saved_object: str | None, written_fields: list[str], evidence: list[EvidenceRef], type_details: dict[str, Any] | None = None, dao_entity_type: str | None = None, dao_type: str | None = None) -> Fact:
    td = type_details or {}
    props = {
        "persistent_write_id": write_id,
        "storage_access_id": access.get("storage_access_id"),
        "operation": access.get("operation"),
        "write_kind": access.get("write_kind"),
        "operation_kind": access.get("operation_kind") or access.get("write_kind"),
        "storage_method": access.get("storage_method"),
        "receiver_expression": access.get("receiver_expression"),
        "writes_new_payload": bool(access.get("writes_new_payload")),
        "payload_role": access.get("payload_role") or "saved_payload",
        "storage_target": access.get("table_or_repository"),
        "candidate_signals": access.get("candidate_signals") or _candidate_signals_for_access(access),
        "saved_object": saved_object or access.get("payload_type") or "unknown",
        "saved_container_kind": td.get("container_kind"),
        "saved_container_type": td.get("type") if td.get("container_kind") else None,
        "saved_element_type": td.get("element_type"),
        "map_key_type": td.get("map_key_type"),
        "map_value_type": td.get("map_value_type"),
        "dao_type": dao_type,
        "dao_entity_type": dao_entity_type,
        "payload_expression": access.get("payload_expression"),
        "written_fields": written_fields,
        "written_field_count": len(written_fields),
        "source_scope": _source_scope_for_file(evidence[0].file_path) if evidence else None,
        "observation_source_scope": _source_scope_for_file(evidence[0].file_path) if evidence else None,
    }
    props.update(_maturity_props({
        "persistence_write": _persistence_maturity_for_access(access),
        "source_boundary": "not_applicable",
        "field_mapping": "not_applicable",
        "physical_storage": _physical_storage_maturity_for_access(access),
        "end_to_end_trace": "not_applicable",
    }, notes=["persistent_write fact does not by itself prove source ownership or field-level lineage"]))
    return Fact(
        fact_type="persistent_write",
        name=f"{access.get('operation')}: write {access.get('table_or_repository')}",
        properties={k: v for k, v in props.items() if v is not None},
        evidence=evidence,
    )


def _lineage_assignment_kind(binding_kind: str | None) -> str:
    value = str(binding_kind or "")
    if value in {"setter_mapping", "helper_setter_mapping"}:
        return "setter"
    if value in {"builder_mapping", "helper_builder_mapping"}:
        return "builder"
    if value in {"constructor_arg", "helper_constructor_arg"}:
        return "constructor"
    if value in {"direct_assignment", "helper_direct_assignment"}:
        return "direct_assignment"
    if value in {"jooq_setter_mapping", "helper_jooq_setter_mapping"}:
        return "jooq_setter"
    if value == "helper_method_return":
        return "helper_method_return"
    return "unknown"


def _java_constant_field_name(raw: str | None) -> str | None:
    """Convert Java field constants to lower-camel field names.

    jOOQ/generated-record APIs often assign fields with expressions such as
    UCP_PHONE_2.PHONE_NUMBER or Tables.UCP_PHONE_2.UCP_ID. Persistence lineage
    facts expose saved object fields as Java-style names (phoneNumber, ucpId), so
    normalize constants before matching against the saved-object schema.
    """
    value = _clean_expression(raw).strip()
    if not value:
        return None
    value = value.strip('"\'')
    token = value.split(".")[-1].strip()
    token = re.sub(r"[^A-Za-z0-9_]", "_", token).strip("_")
    if not token:
        return None
    if "_" in token or token.isupper():
        parts = [p.lower() for p in token.split("_") if p]
        if not parts:
            return None
        return parts[0] + "".join(p[:1].upper() + p[1:] for p in parts[1:])
    return _normalize_field_name(token) or token


def _canonical_field_name(field: str | None, field_names: list[str]) -> str | None:
    """Return schema spelling for a best-effort field candidate."""
    candidate = _normalize_field_name(field) or str(field or "")
    if not candidate:
        return None
    if candidate in field_names:
        return candidate
    c_norm = normalize_name(candidate)
    for name in field_names:
        if normalize_name(name) == c_norm:
            return name
    return candidate


def _replace_java_symbol(expr: str, formal: str, actual: str) -> str:
    if not formal or not actual:
        return expr
    return re.sub(rf"\b{re.escape(formal)}\b", actual, expr or "")


def _substitute_java_symbols(expr: str, arg_map: dict[str, str]) -> str:
    out = expr or ""
    # Longer formals first avoids replacing prefixes in unusual but valid names.
    for formal in sorted(arg_map, key=len, reverse=True):
        out = _replace_java_symbol(out, formal, arg_map[formal])
    return _clean_expression(out)


def _jooq_record_set_bindings(body: str, field_names: list[str] | None = None) -> list[dict[str, Any]]:
    """Extract target.field <- expr from jOOQ/generated-record setter APIs.

    Supported source-only patterns:
      record.set(TABLE.FIELD, expr);
      record.setValue(TABLE.FIELD, expr);
      record.with(TABLE.FIELD, expr);
    """
    out: list[dict[str, Any]] = []
    pat = re.compile(
        r"(?P<target>[A-Za-z_][A-Za-z0-9_]*)\s*\.\s*(?P<method>set|setValue|with)\s*\("
        r"\s*(?P<field>[A-Za-z_][A-Za-z0-9_.$]*|\"[^\"]+\")\s*,\s*(?P<expr>.*?)\s*\)\s*;",
        re.DOTALL,
    )
    for m in pat.finditer(body or ""):
        field = _java_constant_field_name(m.group("field"))
        if field_names:
            field = _canonical_field_name(field, field_names)
        if not field:
            continue
        out.append({
            "kind": "jooq_setter_mapping",
            "target_variable": m.group("target"),
            "target_field": field,
            "source_expression": _clean_expression(m.group("expr")),
            "expression": _clean_expression(m.group(0)),
        })
    return out


def _source_to_storage_lineage_fact(
    lineage_id: str,
    *,
    source_kind: str,
    source_operation: str | None,
    source_payload: str | None,
    source_field: str | None,
    source_field_role: str,
    storage_operation: str,
    storage_target: str | None,
    saved_object: str | None,
    saved_object_field: str | None,
    storage_field: str | None,
    assignment_kind: str,
    assignment_expression: str | None,
    origin_expression: str | None,
    path: list[str],
    missing_links: list[str],
    evidence_refs: list[str],
    evidence: list[EvidenceRef],
    lineage_level: str = "field",
    persistent_write_id: str | None = None,
    storage_access_id: str | None = None,
    storage_call: str | None = None,
    storage_method: str | None = None,
    source_container: str | None = None,
    source_container_type: str | None = None,
    source_element_type: str | None = None,
    saved_container: str | None = None,
    saved_container_type: str | None = None,
    saved_element_type: str | None = None,
    source_payload_parameter: str | None = None,
    storage_resolution_level: str | None = None,
) -> Fact:
    saved_attr = storage_field or saved_object_field
    normalized_missing_links = list(dict.fromkeys(str(item) for item in (missing_links or []) if item))
    maturity = _maturity_props({
        "persistence_write": "confirmed" if str(storage_resolution_level or "") in {"confirmed_sql", "resolved_mapper_sql", "resolved_dao_implementation", "confirmed_bytecode_storage_api"} else "unresolved",
        "source_boundary": _source_boundary_maturity(source_kind),
        "field_mapping": _field_mapping_maturity(
            lineage_level=lineage_level,
            source_field=source_field,
            saved_object_field=saved_object_field,
            storage_field=storage_field or saved_object_field,
            missing_links=normalized_missing_links,
        ),
        "physical_storage": "confirmed" if storage_target and (storage_field or saved_object_field) and str(storage_resolution_level or "") in {"confirmed_sql", "resolved_mapper_sql", "resolved_dao_implementation", "confirmed_bytecode_storage_api"} else "unresolved",
        "end_to_end_trace": _end_to_end_trace_maturity(source_kind, source_operation, storage_operation),
    }, notes=["source_to_storage_lineage is technical evidence only; business own/foreign classification is not asserted"])
    lineage_status = str(maturity.get("evidence_maturity_level") or "unresolved")
    effective_missing_links = [] if lineage_status == "confirmed" else normalized_missing_links
    field_mapping_status = str((maturity.get("evidence_maturity_dimensions") or {}).get("field_mapping") or "unresolved")
    inline_mapping = None
    if saved_attr:
        inline_mapping = {
            "storage_attribute": saved_attr,
            "source_attribute": source_field,
            "source_object": source_container,
            "saved_object": saved_object,
            "mapping_status": "confirmed" if field_mapping_status == "confirmed" else ("candidate" if source_field else "target_field_observed_source_unresolved"),
            "mapping_kind": assignment_kind,
            "evidence_refs": [lineage_id, *[x for x in evidence_refs if x]],
        }
    segment_status = "confirmed" if lineage_status == "confirmed" else ("candidate" if saved_attr else "unresolved")
    props = {
        "source_to_storage_lineage_id": lineage_id,
        "source_kind": source_kind,
        "source_operation": source_operation,
        "source_payload": source_payload or "unknown",
        "source_container": source_container,
        "source_container_type": source_container_type,
        "source_element_type": source_element_type,
        "source_field": source_field,
        "source_field_role": source_field_role,
        "storage_operation": storage_operation,
        "storage_call": storage_call,
        "storage_method": storage_method,
        "storage_target": storage_target,
        "storage_resolution_level": storage_resolution_level,
        "source_scope": _source_scope_for_file(evidence[0].file_path) if evidence else None,
        "persistent_write_id": persistent_write_id,
        "storage_access_id": storage_access_id,
        "candidate_signals": [],
        "lineage_status": lineage_status,
        "source_to_storage_segment": {
            "status": segment_status,
            "field_mapping_status": "confirmed" if field_mapping_status == "confirmed" else ("candidate" if source_field and saved_attr else ("target_field_observed_source_unresolved" if saved_attr else "unresolved")),
            "evidence_policy": "technical source-to-storage segment only; business own/foreign classification is not asserted",
        },
        "source_to_saved_field_mappings": [inline_mapping] if inline_mapping and source_field else [],
        "write_target_fields": [inline_mapping] if inline_mapping and not source_field else [],
        "saved_object": saved_object or "unknown",
        "saved_object_field": saved_object_field,
        "storage_field": storage_field or saved_object_field,
        "saved_container": saved_container,
        "saved_container_type": saved_container_type,
        "saved_element_type": saved_element_type,
        "source_payload_parameter": source_payload_parameter,
        "lineage_level": lineage_level,
        "assignment_kind": assignment_kind,
        "assignment_expression": assignment_expression,
        "origin_expression": origin_expression,
        "path": path,
        "missing_links": effective_missing_links,
        "evidence_refs": [x for x in evidence_refs if x],
    }
    props.update(maturity)
    return Fact(
        fact_type="source_to_storage_lineage",
        name=f"{source_payload or source_kind}.{source_field or 'object'} -> {storage_target or 'storage'}.{saved_object_field or saved_object or 'object'}",
        properties={k: v for k, v in props.items() if v is not None},
        evidence=evidence,
    )


def _storage_lineage_gap_fact(gap_id: str, *, gap_kind: str, storage_access: dict[str, Any], saved_object: str | None, saved_object_field: str | None, reason: str, missing_links: list[str], evidence: list[EvidenceRef], extra: dict[str, Any] | None = None) -> Fact:
    props = {
        "storage_lineage_gap_id": gap_id,
        "gap_kind": gap_kind,
        "storage_access_id": storage_access.get("storage_access_id"),
        "storage_operation": storage_access.get("operation"),
        "storage_target": storage_access.get("table_or_repository"),
        "storage_method": storage_access.get("storage_method"),
        "operation_kind": storage_access.get("operation_kind"),
        "access_kind": storage_access.get("access_kind"),
        "writes_new_payload": bool(storage_access.get("writes_new_payload")),
        "payload_role": storage_access.get("payload_role"),
        "candidate_signals": storage_access.get("candidate_signals") or _candidate_signals_for_access(storage_access),
        "saved_object": saved_object or "unknown",
        "saved_object_field": saved_object_field,
        "reason": reason,
        "missing_links": missing_links,
    }
    if extra:
        props.update(extra)
    if gap_kind == "field_mapping_not_resolved" or "field_mapping_not_resolved" in set(missing_links or []):
        props.update(_field_mapping_gap_diagnostic(
            storage_access=storage_access,
            saved_object=saved_object,
            saved_object_field=saved_object_field,
            extra=extra,
        ))
    props.update(_maturity_props({
        "persistence_write": _persistence_maturity_for_access(storage_access),
        "source_boundary": "unresolved" if bool(storage_access.get("writes_new_payload")) else "not_applicable",
        "field_mapping": "unresolved" if gap_kind in {"field_mapping_not_resolved", "save_payload_from_mapper_result", "mapper_not_resolved"} else "not_applicable",
        "physical_storage": _physical_storage_maturity_for_access(storage_access),
        "end_to_end_trace": "unresolved" if bool(storage_access.get("writes_new_payload")) else "not_applicable",
    }, notes=["gap fact is diagnostic; do not upgrade to confirmed risk without resolving unresolved dimensions"]))
    return Fact(
        fact_type="storage_lineage_gap",
        name=f"{gap_kind}: {storage_access.get('operation')} {saved_object_field or ''}".strip(),
        properties={k: v for k, v in props.items() if v is not None},
        evidence=evidence,
    )




# --- Stored-data access side evidence ----------------------------------------

def _fields_for_java_type(schema_fields: dict[str, list[dict[str, Any]]], type_name: str | None, *, max_fields: int = 32) -> list[str]:
    typ = _simple_type_name(type_name)
    fields = _fields_for_type(schema_fields, typ)
    return [str(f.get("name")) for f in fields[:max_fields] if f.get("name")]


def _result_type_for_read_access(access: dict[str, Any], mi: dict[str, Any]) -> str:
    storage_method = str(access.get("storage_method") or "")
    receiver = str(access.get("receiver_expression") or "")
    if not storage_method or not receiver:
        return "unknown"
    calls = mi.get("method_calls") or []
    for assignment in mi.get("syntax_assignments") or []:
        if assignment.get("assignment_kind") != "variable_declaration":
            continue
        a_start = int(assignment.get("start_byte") or -1)
        a_end = int(assignment.get("end_byte") or -1)
        for call in calls:
            if call.get("receiver") != receiver or call.get("method") != storage_method:
                continue
            c_start = int(call.get("start_byte") or -2)
            c_end = int(call.get("end_byte") or -2)
            if a_start <= c_start and c_end <= a_end:
                return _normalize_java_type(assignment.get("declared_type"))
    return "unknown"


def _physical_read_access_variants(access: dict[str, Any]) -> list[dict[str, Any]]:
    """Split a multi-table JOOQ projection by the declared field owner.

    A ``select(A.ID, B.VALUE).from(A).join(B)`` read is not a read of both
    fields from ``A``.  ``selected_field_refs`` already carries the exact
    physical owner; preserve that evidence as one read projection per table.
    Computed expressions that have no exact owner remain attached to the
    original FROM table.
    """
    if str(access.get("storage_resolution_level") or "") != "confirmed_sql_read":
        return [access]
    refs = [str(ref) for ref in access.get("selected_field_refs") or []]
    fields = [str(field) for field in access.get("selected_fields") or []]
    if not refs or len(refs) != len(fields):
        return [access]
    original_owner = str(access.get("table_or_repository") or "")
    grouped: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for field, ref in zip(fields, refs):
        match = re.fullmatch(r"(?P<table>[A-Za-z_$][\w$]*)\.(?P<field>[A-Za-z_$][\w$]*)", ref)
        owner = match.group("table") if match else original_owner
        grouped[owner].append((match.group("field") if match else field, ref))
    if len(grouped) <= 1:
        return [access]
    variants: list[dict[str, Any]] = []
    for owner in sorted(grouped):
        pairs = grouped[owner]
        variant = dict(access)
        variant["table_or_repository"] = owner
        variant["selected_fields"] = [field for field, _ref in pairs]
        variant["selected_field_refs"] = [ref for _field, ref in pairs]
        variant["projection_owner"] = owner
        variant["storage_resolution_status"] = "resolved_jooq_selected_field_owner"
        variants.append(variant)
    return variants


def _read_from_storage_fact(read_id: str, access: dict[str, Any], mi: dict[str, Any], *, schema_fields: dict[str, list[dict[str, Any]]], evidence: list[EvidenceRef]) -> Fact:
    result_type = str(access.get("result_type") or _result_type_for_read_access(access, mi) or "unknown")
    storage_kind = str(access.get("operation_kind") or access.get("write_kind") or "read")
    if storage_kind not in {"select", "find", "query", "load", "get", "repository_read", "dao_read", "mapper_read", "read"}:
        method = str(access.get("storage_method") or "").lower()
        if method.startswith("find"):
            storage_kind = "find"
        elif method.startswith("query"):
            storage_kind = "query"
        elif method.startswith("load"):
            storage_kind = "load"
        elif method.startswith("get"):
            storage_kind = "get"
        elif method.startswith("select"):
            storage_kind = "select"
        else:
            storage_kind = "repository_read"
    props = {
        "read_from_storage_id": read_id,
        "storage_access_id": access.get("storage_access_id"),
        "repo_id": None,
        "source_file": str(mi.get("file") or access.get("file") or ""),
        "class_name": mi.get("class_name") or access.get("class_name"),
        "method_name": mi.get("method_name") or access.get("method_name"),
        "operation": access.get("operation"),
        "storage_access_kind": storage_kind,
        "storage_symbol": ".".join(x for x in [str(access.get("receiver_expression") or ""), str(access.get("storage_method") or "")] if x),
        "storage_object": access.get("table_or_repository"),
        "result_type": result_type,
        "fields": list(access.get("selected_fields") or _fields_for_java_type(schema_fields, result_type)),
        "selected_field_refs": list(access.get("selected_field_refs") or []),
        "payload_role": access.get("payload_role"),
        "filter_expression": access.get("payload_expression"),
        "sql_preview": access.get("sql_preview"),
    }
    props.update(_maturity_props({
        "storage_read": "confirmed",
        "physical_storage": "confirmed" if str(access.get("storage_resolution_level") or "") == "confirmed_sql_read" else "unresolved",
    }, notes=["read_from_storage is access-side evidence only; it does not imply exposure or risk"], decision_blocking_dimensions={"storage_read", "physical_storage"}, actionable_dimensions={"physical_storage"}, inspection_target_available=True))
    return Fact(fact_type="read_from_storage", name=f"read {props.get('storage_symbol')} in {props.get('operation')}", properties={k:v for k,v in props.items() if v is not None}, evidence=evidence)


def _rest_endpoint_for_method(mi: dict[str, Any]) -> str | None:
    mapping = next((a for a in (mi.get("annotations") or []) if a.get("name") in {"GetMapping", "PostMapping", "PutMapping", "DeleteMapping", "PatchMapping", "RequestMapping"}), None)
    if not mapping:
        return None
    return _extract_annotation_value(mapping.get("arguments")) or str(mapping.get("name") or "")


def _is_external_rest_method(mi: dict[str, Any]) -> bool:
    # Some lightweight method parsing loses the annotation window for compact GetMapping forms.
    # If the owner class is a REST controller and the method returns a body, keep it as a
    # REST response boundary even when the exact endpoint string is unresolved.
    ret = _normalize_java_type(mi.get("return_type"))
    return bool(mi.get("rest_class") and ret and ret != "void")


def _response_payload_for_method(mi: dict[str, Any]) -> tuple[str, str]:
    ret = _normalize_java_type(mi.get("return_type"))
    if not ret or ret == "void":
        return "void", "void"
    return ret, ret


def _access_boundary_fact(boundary_id: str, *, boundary_kind: str, mi: dict[str, Any], endpoint_or_topic: str | None, response_or_payload_type: str | None, fields: list[str], external_access: bool | None, evidence: list[EvidenceRef], payload_expression: str | None = None) -> Fact:
    props = {
        "access_boundary_id": boundary_id,
        "boundary_kind": boundary_kind,
        "source_file": str(mi.get("file") or ""),
        "class_name": mi.get("class_name"),
        "method_name": mi.get("method_name"),
        "operation": mi.get("operation"),
        "endpoint_or_topic": endpoint_or_topic,
        "response_or_payload_type": response_or_payload_type or "unknown",
        "payload_expression": payload_expression,
        "fields": fields[:64],
        "field_count": len(fields),
        "external_access": external_access,
    }
    props.update(_maturity_props({
        "access_boundary": "confirmed" if external_access is True else "unresolved" if external_access is None else "not_applicable",
        "field_mapping": "confirmed" if fields else "unresolved",
    }, notes=["access_boundary describes outward access only; it must be linked to a storage read and matching saved fields before the LLM may discuss access to stored data"], decision_blocking_dimensions={"access_boundary", "field_mapping"}, actionable_dimensions={"access_boundary", "field_mapping"}, inspection_target_available=True))
    return Fact(fact_type="access_boundary", name=f"{boundary_kind} {mi.get('operation')}", properties={k:v for k,v in props.items() if v is not None}, evidence=evidence)


def _extract_return_expressions(body: str) -> list[str]:
    # Compatibility helper for legacy local call sites. Return statements are now
    # extracted by Tree-sitter through a synthetic method.
    method = _synthetic_method_for_body(body or "")
    return _return_expressions_from_method_info({"returns": [r.__dict__ for r in (method.returns if method else ())]})


def _read_assignment_vars(access: dict[str, Any], mi: dict[str, Any]) -> list[str]:
    receiver = str(access.get("receiver_expression") or "")
    method = str(access.get("storage_method") or "")
    if not receiver or not method:
        return []
    out: list[str] = []
    calls = mi.get("method_calls") or []
    for assignment in mi.get("syntax_assignments") or []:
        target = str(assignment.get("target") or "")
        if not target:
            continue
        a_start = int(assignment.get("start_byte") or -1)
        a_end = int(assignment.get("end_byte") or -1)
        for call in calls:
            if call.get("receiver") != receiver or call.get("method") != method:
                continue
            c_start = int(call.get("start_byte") or -2)
            c_end = int(call.get("end_byte") or -2)
            if a_start <= c_start and c_end <= a_end:
                out.append(target)
                break
    return out


def _method_returns_storage_read(access: dict[str, Any], mi: dict[str, Any]) -> tuple[bool, list[str]]:
    body = mi.get("body") or ""
    receiver = str(access.get("receiver_expression") or "")
    method = str(access.get("storage_method") or "")
    returns = _return_expressions_from_method_info(mi)
    reasons: list[str] = []
    for expr in returns:
        if receiver and method and f"{receiver}.{method}" in expr:
            reasons.append("direct_return_of_storage_read_call")
        for var in _read_assignment_vars(access, mi):
            if re.search(rf"\b{re.escape(var)}\b", expr):
                reasons.append(f"return_of_storage_read_variable:{var}")
    return bool(reasons), reasons


def _storage_to_access_lineage_fact(lineage_id: str, *, read_fact_id: str, access_fact_id: str, access: dict[str, Any], read_mi: dict[str, Any], access_mi: dict[str, Any], path: list[dict[str, Any]], fields: list[str], same_method: bool, evidence: list[EvidenceRef], explicit_field_mappings: list[dict[str, Any]] | None = None, lineage_status: str | None = None) -> Fact:
    field_mappings = explicit_field_mappings or [{
        "storage_field": f,
        "response_field": f,
        "mapping_type": "direct" if same_method else "unknown",
        "evidence_level": "confirmed_by_static_analysis" if same_method else "candidate_signal",
    } for f in fields[:64]]
    status = lineage_status or ("confirmed" if same_method and fields else "unresolved")
    props = {
        "storage_to_access_lineage_id": lineage_id,
        "read_evidence_ref": read_fact_id,
        "access_evidence_ref": access_fact_id,
        "source_storage_object": access.get("table_or_repository"),
        "access_boundary": access_mi.get("operation"),
        "path": path,
        "field_mappings": field_mappings,
        "lineage_status": status,
        "same_method_lineage": same_method,
        "missing_links": [] if status == "confirmed" else ["storage_to_access_lineage_unresolved", "field_mapping_storage_to_response_unresolved"],
        "candidate_signals": [] if status == "confirmed" else [{
            "signal_type": "storage_read_near_access_boundary",
            "target": access_mi.get("operation"),
            "basis": "storage read and outward access were found in related operations, but field-level same-data mapping is unresolved",
            "is_evidence": False,
            "allowed_use": "navigation_only",
            "requires_source_inspection": True,
            "recommended_action": "inspect controller/service/mapper path to confirm that the response payload is built from the storage read result",
            "related_evidence_refs": [read_fact_id, access_fact_id],
        }],
    }
    props.update(_maturity_props({
        "storage_read": "confirmed",
        "access_boundary": "confirmed",
        "storage_to_access_lineage": "confirmed" if status == "confirmed" else "unresolved",
        "field_mapping": "confirmed" if status == "confirmed" and field_mappings else "unresolved",
    }, notes=["storage_to_access_lineage is technical evidence only; LLM must combine it with persistence-side evidence before making foreign-data-persistence conclusions"], decision_blocking_dimensions={"storage_read", "access_boundary", "storage_to_access_lineage", "field_mapping"}, actionable_dimensions={"storage_to_access_lineage", "field_mapping"}, inspection_target_available=True))
    return Fact(fact_type="storage_to_access_lineage", name=f"{access.get('table_or_repository')} -> {access_mi.get('operation')}", properties={k:v for k,v in props.items() if v is not None}, evidence=evidence)


def _jooq_record_constructor_field_mappings(
    access: dict[str, Any],
    mi: dict[str, Any],
    *,
    schema_fields: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    selected = [str(x) for x in access.get("selected_fields") or [] if x]
    if not selected:
        return []
    selected_by_token = {_normalized_field_token(field): field for field in selected}
    mappings: list[dict[str, Any]] = []
    for lambda_info in mi.get("lambdas") or []:
        params = list(lambda_info.get("params") or [])
        body = _clean_expression(lambda_info.get("body"))
        if len(params) != 1 or not body.startswith("new "):
            continue
        created = re.match(r"new\s+(?P<type>[A-Za-z_$][\w$<>., ?]*)\s*\((?P<args>.*)\)\s*$", body, re.S)
        if not created:
            continue
        target_type = _simple_type_name(created.group("type"))
        target_fields = [str(field.get("name")) for field in _fields_for_type(schema_fields, target_type) if field.get("name")]
        args = split_java_arguments(created.group("args"))
        if not target_fields or len(args) != len(target_fields):
            continue
        lambda_param = str(params[0])
        for position, (arg, response_field) in enumerate(zip(args, target_fields)):
            getter = re.fullmatch(
                rf"{re.escape(lambda_param)}\s*\.\s*(?:get|is)(?P<field>[A-Z][A-Za-z0-9_$]*)\s*\(\s*\)",
                _clean_expression(arg),
            )
            if not getter:
                continue
            record_field = getter.group("field")[:1].lower() + getter.group("field")[1:]
            storage_field = selected_by_token.get(_normalized_field_token(record_field))
            if not storage_field:
                continue
            mappings.append({
                "storage_field": storage_field,
                "record_type": access.get("result_type"),
                "record_field": record_field,
                "response_container": target_type,
                "response_field": response_field,
                "constructor_position": position,
                "mapping_type": "jooq_record_getter_to_constructor_position",
                "evidence_level": "confirmed_by_static_analysis",
            })
    # Fluent DTO builders are another explicit projection form, e.g.
    # ``Profile.builder().operatorId(r.getValue(PHONE.OPERATORID)).build()``.
    # Only exact record getter arguments for selected physical field refs are
    # accepted; arbitrary same-name builder methods are not treated as evidence.
    selected_refs = {str(ref) for ref in access.get("selected_field_refs") or []}
    for lambda_info in mi.get("lambdas") or []:
        params = list(lambda_info.get("params") or [])
        body = _clean_expression(lambda_info.get("body"))
        if len(params) != 1 or ".builder()" not in body:
            continue
        root = re.search(r"(?P<type>[A-Za-z_$][\w$]*)\s*\.\s*builder\s*\(\s*\)", body)
        if not root:
            continue
        target_type = _simple_type_name(root.group("type"))
        lambda_param = str(params[0])
        pattern = re.compile(
            rf"\.\s*(?P<target>[A-Za-z_$][\w$]*)\s*\(\s*"
            rf"{re.escape(lambda_param)}\s*\.\s*(?:getValue|get)\s*\(\s*"
            r"(?P<ref>[A-Za-z_$][\w$]*\.[A-Za-z_$][\w$]*)\s*\)\s*\)"
        )
        for match in pattern.finditer(body):
            field_ref = match.group("ref")
            if field_ref not in selected_refs:
                continue
            _owner, storage_field = field_ref.split(".", 1)
            item = {
                "storage_field": storage_field,
                "storage_field_ref": field_ref,
                "record_type": access.get("result_type") or "Record",
                "record_field": storage_field[:1].lower() + storage_field[1:],
                "response_container": target_type,
                "response_field": match.group("target"),
                "mapping_type": "jooq_record_getter_to_builder_field",
                "evidence_level": "confirmed_by_static_analysis",
            }
            key = (item["storage_field_ref"], item["response_container"], item["response_field"])
            if not any(
                (existing.get("storage_field_ref"), existing.get("response_container"), existing.get("response_field")) == key
                for existing in mappings
            ):
                mappings.append(item)
    return mappings


def _call_result_propagates(call: dict[str, Any], caller_mi: dict[str, Any]) -> bool:
    receiver = str(call.get("receiver_expression") or "")
    method = str(call.get("method_name") or "")
    call_symbols = [f"{receiver}.{method}" if receiver else method]
    if receiver in {"this", "super"}:
        call_symbols.append(method)
    returns = _return_expressions_from_method_info(caller_mi)
    if any(symbol and symbol in expression for symbol in call_symbols for expression in returns):
        return True
    call_symbol = call_symbols[0]
    line = int(call.get("line_start") or 0)
    assigned: set[str] = set()
    for assignment in caller_mi.get("syntax_assignments") or []:
        target = str(assignment.get("target") or "")
        expression = str(assignment.get("expression") or "")
        if target and call_symbol and call_symbol in expression:
            assigned.add(target)
        elif target and line and int(assignment.get("line_start") or 0) == line:
            assigned.add(target)
    return any(re.search(rf"\b{re.escape(target)}\b", expression) for target in assigned for expression in returns)


def _outward_call_path(
    *,
    start_operation: str,
    access_by_operation: dict[str, Fact],
    calls: list[dict[str, Any]],
    methods: dict[str, dict[str, Any]],
) -> tuple[str, list[dict[str, Any]]] | None:
    reverse: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for call in calls:
        reverse[str(call.get("callee_operation_id") or "")].append(call)
    queue: list[tuple[str, list[dict[str, Any]]]] = [(start_operation, [])]
    visited = {start_operation}
    while queue:
        operation, path = queue.pop(0)
        if operation != start_operation and operation in access_by_operation:
            fact = access_by_operation[operation]
            props = fact.properties or {}
            if props.get("external_access") is True:
                return operation, path
        candidates = sorted(
            reverse.get(operation, []),
            key=lambda call: (
                0 if _rest_endpoint_for_method(methods.get(str(call.get("caller_operation_id") or ""), {})) else 1,
                -float(call.get("match_strength") or 0.0),
                str(call.get("caller_operation_signature") or ""),
            ),
        )
        for call in candidates:
            caller_op = str(call.get("caller_operation_id") or "")
            caller_mi = methods.get(caller_op)
            if caller_op in visited or not _production_method(caller_mi):
                continue
            if not _call_result_propagates(call, caller_mi):
                continue
            visited.add(caller_op)
            queue.append((caller_op, path + [{
                "kind": "method_return_propagation",
                "from": operation,
                "to": caller_op,
                "call_expression": str(call.get("snippet") or ""),
                "resolution_kind": call.get("resolution_kind"),
            }]))
    return None


def _stored_field_to_response_field_mapping_fact(mapping_id: str, *, lineage_id: str, storage_object: str | None, storage_field: str, read_type: str | None, response_type: str | None, response_field: str, mapping_type: str, mapping_source: str, evidence: list[EvidenceRef]) -> Fact:
    level = "confirmed" if mapping_type in {"direct", "rename"} else "unresolved"
    props = {
        "stored_field_to_response_field_mapping_id": mapping_id,
        "storage_to_access_lineage_id": lineage_id,
        "storage_object": storage_object,
        "storage_field": storage_field,
        "read_type": read_type,
        "response_or_payload_type": response_type,
        "response_field": response_field,
        "mapping_type": mapping_type,
        "mapping_source": mapping_source,
        "evidence_level": "confirmed_by_static_analysis" if level == "confirmed" else "unresolved",
    }
    props.update(_maturity_props({
        "field_mapping": level,
    }, notes=["field mapping relates storage-read result fields to outward response fields; it is not by itself a risk decision"], decision_blocking_dimensions={"field_mapping"}, actionable_dimensions={"field_mapping"}, inspection_target_available=True))
    return Fact(fact_type="stored_field_to_response_field_mapping", name=f"{storage_object}.{storage_field} -> {response_type}.{response_field}", properties={k:v for k,v in props.items() if v is not None}, evidence=evidence)


def _method_call_targets(mi: dict[str, Any], *, class_fields: dict[str, str], var_types: dict[str, str]) -> list[tuple[str, str, str]]:
    targets: list[tuple[str, str, str]] = []
    for call in mi.get("method_calls") or []:
        receiver = call.get("receiver") or ""
        method = call.get("method") or ""
        rtype = class_fields.get(receiver) or var_types.get(receiver) or ""
        if rtype:
            targets.append((_simple_type_name(rtype), method, f"{receiver}.{method}"))
    return targets


def _build_stored_data_access_facts(methods: dict[str, dict[str, Any]], class_fields: dict[str, dict[str, str]], storage_accesses: list[dict[str, Any]], schema_fields: dict[str, list[dict[str, Any]]], *, calls: list[dict[str, Any]] | None = None) -> tuple[list[Fact], dict[str, int]]:
    facts: list[Fact] = []
    counts: dict[str, int] = defaultdict(int)
    read_by_operation: dict[str, list[tuple[dict[str, Any], str, Fact]]] = defaultdict(list)
    access_by_operation: dict[str, Fact] = {}
    access_seq = 0
    read_seq = 0
    lineage_seq = 0
    mapping_seq = 0
    request_seq = 0

    # Storage reads.
    for raw_access in storage_accesses:
        if raw_access.get("access_kind") != "read":
            continue
        for access in _physical_read_access_variants(raw_access):
            op = str(access.get("operation") or "")
            mi = methods.get(op)
            if not mi:
                continue
            evidence = _op_file_evidence(mi, "java_stored_data_access_read")
            read_seq += 1
            read_id = f"read_from_storage_{read_seq:06d}"
            fact = _read_from_storage_fact(read_id, access, mi, schema_fields=schema_fields, evidence=evidence)
            facts.append(fact)
            read_by_operation[op].append((access, read_id, fact))
            counts["read_from_storage"] += 1

    # REST response/access boundaries and outbound sinks. REST with a response type is an access boundary.
    for op, mi in sorted(methods.items()):
        evidence = _op_file_evidence(mi, "java_stored_data_access_boundary")
        if _is_external_rest_method(mi):
            response_type, payload = _response_payload_for_method(mi)
            if response_type != "void":
                access_seq += 1
                access_id = f"access_boundary_{access_seq:06d}"
                fact = _access_boundary_fact(
                    access_id,
                    boundary_kind="rest_response",
                    mi=mi,
                    endpoint_or_topic=_rest_endpoint_for_method(mi),
                    response_or_payload_type=response_type,
                    fields=_fields_for_java_type(schema_fields, response_type),
                    external_access=True,
                    evidence=evidence,
                    payload_expression=payload,
                )
                facts.append(fact)
                access_by_operation[op] = fact
                counts["access_boundary"] += 1
        for sink in _sink_matches_from_method_info(mi):
            sink_kind = str(sink.get("sink_kind") or "")
            if sink_kind == "rest_response":
                continue
            payload = _clean_expression(sink.get("payload"))
            if not payload:
                continue
            payload_type = _simple_type_name((mi.get("var_types") or {}).get(payload) or payload)
            access_seq += 1
            access_id = f"access_boundary_{access_seq:06d}"
            boundary_kind = "kafka_outbound" if sink_kind == "kafka" else "http_outbound" if sink_kind == "http_client" else "message_outbound"
            sink_line = int(sink.get("line_start") or mi.get("line_start") or 1)
            ev = evidence + [EvidenceRef(file_path=str(mi.get("file")), line_start=sink_line, line_end=sink_line, snippet=str(sink.get("snippet") or "")[:700], extractor="java_stored_data_access_boundary_sink")]
            fact = _access_boundary_fact(
                access_id,
                boundary_kind=boundary_kind,
                mi=mi,
                endpoint_or_topic=_clean_expression(sink.get("target")),
                response_or_payload_type=payload_type,
                fields=_fields_for_java_type(schema_fields, payload_type),
                external_access=True,
                evidence=ev,
                payload_expression=payload,
            )
            facts.append(fact)
            access_by_operation.setdefault(op, fact)
            counts["access_boundary"] += 1

    # If a method reads from storage and returns a non-void value, expose it as an
    # access boundary candidate. For REST controllers this is external access; for
    # services/helpers it is unknown and must be linked to an actual outward boundary
    # by source inspection or trace evidence.
    for op, reads in read_by_operation.items():
        if op in access_by_operation:
            continue
        mi = methods.get(op)
        if not mi:
            continue
        response_type, payload = _response_payload_for_method(mi)
        if response_type == "void":
            continue
        access_seq += 1
        access_id = f"access_boundary_{access_seq:06d}"
        class_annotations = set(mi.get("class_annotations") or [])
        class_interfaces = [str(x) for x in (mi.get("class_interfaces") or [])]
        method_annotations = {str(x.get("name") or "") for x in (mi.get("annotations") or []) if isinstance(x, dict)}
        if mi.get("rest_class"):
            external = True
            return_boundary_kind = "rest_response"
        elif "GrpcService" in class_annotations:
            external = True
            return_boundary_kind = "grpc_response"
        elif "Override" in method_annotations and any(name.endswith(("Facade", "Callback", "Listener", "Handler", "Provider", "Plugin", "Endpoint")) for name in class_interfaces):
            external = None
            return_boundary_kind = "framework_callback_response"
        else:
            external = None
            return_boundary_kind = "api_response"
        fact = _access_boundary_fact(
            access_id,
            boundary_kind=return_boundary_kind,
            mi=mi,
            endpoint_or_topic=_rest_endpoint_for_method(mi),
            response_or_payload_type=response_type,
            fields=_fields_for_java_type(schema_fields, response_type),
            external_access=external,
            evidence=_op_file_evidence(mi, "java_stored_data_access_return_boundary"),
            payload_expression=payload,
        )
        facts.append(fact)
        access_by_operation[op] = fact
        counts["access_boundary"] += 1

    # Same-method and one-hop storage read -> access boundary chains.
    for access_op, access_fact in list(access_by_operation.items()):
        access_mi = methods.get(access_op)
        if not access_mi:
            continue
        candidates: list[tuple[dict[str, Any], str, Fact, bool, list[dict[str, Any]]]] = []
        for access, read_id, read_fact in read_by_operation.get(access_op, []):
            ok, reasons = _method_returns_storage_read(access, access_mi)
            if ok or read_fact:
                candidates.append((access, read_id, read_fact, True, [
                    {"kind": "dao_read", "symbol": str(read_fact.properties.get("storage_symbol") or "")},
                    {"kind": str(access_fact.properties.get("boundary_kind") or "access_boundary"), "symbol": access_op, "return_reasons": reasons},
                ]))
        # Controller/access method calls a service/repository method that has a storage read.
        cfields = class_fields.get(str(access_mi.get("class_name") or ""), {})
        for target_cls, target_method, call_expr in _method_call_targets(access_mi, class_fields=cfields, var_types=access_mi.get("var_types") or {}):
            target_op = f"{target_cls}.{target_method}"
            for access, read_id, read_fact in read_by_operation.get(target_op, []):
                candidates.append((access, read_id, read_fact, False, [
                    {"kind": "dao_read", "symbol": str(read_fact.properties.get("storage_symbol") or "")},
                    {"kind": "service_method", "symbol": target_op, "call_expression": call_expr},
                    {"kind": str(access_fact.properties.get("boundary_kind") or "access_boundary"), "symbol": access_op},
                ]))
        for access, read_id, read_fact, same_method, path in candidates[:20]:
            if (
                same_method
                and str(access.get("storage_resolution_level") or "") == "confirmed_sql_read"
                and access_fact.properties.get("external_access") is not True
            ):
                # A DAO/helper return is not itself an outward access boundary.  Do
                # not manufacture direct physical-column -> Map/record mappings;
                # the confirmed multi-hop resolver below will attach the read to an
                # actual REST/message boundary and observed DTO projection.
                continue
            read_type = str(read_fact.properties.get("result_type") or "unknown")
            response_type = str(access_fact.properties.get("response_or_payload_type") or "unknown")
            storage_fields = list(read_fact.properties.get("fields") or [])
            response_fields = list(access_fact.properties.get("fields") or [])
            overlap = [f for f in storage_fields if f in set(response_fields)] if response_fields else storage_fields
            lineage_seq += 1
            lineage_id = f"storage_to_access_lineage_{lineage_seq:06d}"
            ev = (read_fact.evidence or []) + (access_fact.evidence or [])
            lineage_fact = _storage_to_access_lineage_fact(lineage_id, read_fact_id=read_id, access_fact_id=str(access_fact.properties.get("access_boundary_id")), access=access, read_mi=methods.get(str(access.get("operation") or ""), access_mi), access_mi=access_mi, path=path, fields=overlap, same_method=same_method, evidence=ev)
            facts.append(lineage_fact)
            counts["storage_to_access_lineage"] += 1
            for f in overlap[:32]:
                mapping_seq += 1
                mapping_type = "direct" if same_method and f in set(response_fields or storage_fields) else "unknown"
                facts.append(_stored_field_to_response_field_mapping_fact(f"stored_field_to_response_field_mapping_{mapping_seq:06d}", lineage_id=lineage_id, storage_object=access.get("table_or_repository"), storage_field=f, read_type=read_type, response_type=response_type, response_field=f, mapping_type=mapping_type, mapping_source="return_expression" if same_method else "service_call", evidence=ev))
                counts["stored_field_to_response_field_mapping"] += 1
            if not overlap:
                request_seq += 1
                facts.append(_source_inspection_request_fact(
                    f"source_inspection_request_access_{request_seq:06d}",
                    reason="field_mapping_storage_to_response_unresolved",
                    priority="high",
                    target_operation=access_op,
                    focus="Inspect how the response/outbound payload is built from the storage read result and list matching fields.",
                    related_evidence_refs=[read_id, str(access_fact.properties.get("access_boundary_id") or ""), lineage_id],
                    source_payload=read_type,
                    saved_object=response_type,
                    trigger_blockers=["field_mapping:unresolved", "storage_to_access_lineage:unresolved"],
                    evidence=ev,
                    expected_observations=["storage read result variable", "mapper/converter entity-to-response mapping", "returned response DTO fields", "whether stored fields are same data as response fields"],
                    tokens=[str(access.get("receiver_expression") or ""), str(access.get("storage_method") or ""), response_type],
                ))

    # Confirmed multi-hop physical read -> outward boundary chains.  This path is
    # stricter than the proximity-based fallback above: every call edge must
    # propagate its result into the caller's return expression, and field mappings
    # must be proven by an observed JOOQ record getter and DTO constructor position.
    if calls:
        emitted_pairs: set[tuple[str, str]] = set()
        for read_op, reads in sorted(read_by_operation.items()):
            outward = _outward_call_path(
                start_operation=read_op,
                access_by_operation=access_by_operation,
                calls=calls,
                methods=methods,
            )
            if not outward:
                continue
            access_op, call_path = outward
            access_fact = access_by_operation[access_op]
            access_mi = methods.get(access_op)
            read_mi = methods.get(read_op)
            if not access_mi or not read_mi:
                continue
            response_type = str(access_fact.properties.get("response_or_payload_type") or "unknown")
            response_schema = _fields_for_type(schema_fields, response_type)
            for access, read_id, read_fact in reads:
                if str(access.get("storage_resolution_level") or "") != "confirmed_sql_read":
                    continue
                pair_key = (str(read_id), str(access_fact.properties.get("access_boundary_id") or ""))
                if pair_key in emitted_pairs:
                    continue
                mappings = _jooq_record_constructor_field_mappings(access, read_mi, schema_fields=schema_fields)
                if not mappings:
                    continue
                projected_type = str(mappings[0].get("response_container") or "unknown")
                wrapper_field = next((
                    str(field.get("name"))
                    for field in response_schema
                    if field.get("container_kind") in {"map", "collection", "array"}
                    and _simple_type_name(field.get("element_type")) == _simple_type_name(projected_type)
                ), None)
                explicit_mappings: list[dict[str, Any]] = []
                for mapping in mappings:
                    item = dict(mapping)
                    if wrapper_field:
                        item["response_field"] = f"{wrapper_field}.{mapping.get('response_field')}"
                    item["response_or_payload_type"] = response_type
                    explicit_mappings.append(item)
                lineage_seq += 1
                lineage_id = f"storage_to_access_lineage_{lineage_seq:06d}"
                path = [
                    {
                        "kind": "jooq_physical_read",
                        "symbol": f"{access.get('table_or_repository')}[{', '.join(access.get('selected_fields') or [])}]",
                        "operation": read_op,
                    },
                    {
                        "kind": "record_constructor_projection",
                        "symbol": f"{access.get('result_type')} -> {projected_type}",
                        "field_mapping_count": len(explicit_mappings),
                    },
                    *call_path,
                    {
                        "kind": str(access_fact.properties.get("boundary_kind") or "access_boundary"),
                        "symbol": access_op,
                        "endpoint_or_topic": access_fact.properties.get("endpoint_or_topic"),
                    },
                ]
                ev = (read_fact.evidence or []) + (access_fact.evidence or [])
                facts.append(_storage_to_access_lineage_fact(
                    lineage_id,
                    read_fact_id=read_id,
                    access_fact_id=str(access_fact.properties.get("access_boundary_id") or ""),
                    access=access,
                    read_mi=read_mi,
                    access_mi=access_mi,
                    path=path,
                    fields=[str(mapping.get("storage_field") or "") for mapping in explicit_mappings],
                    same_method=False,
                    evidence=ev,
                    explicit_field_mappings=explicit_mappings,
                    lineage_status="confirmed",
                ))
                counts["storage_to_access_lineage"] += 1
                for mapping in explicit_mappings:
                    mapping_seq += 1
                    facts.append(_stored_field_to_response_field_mapping_fact(
                        f"stored_field_to_response_field_mapping_{mapping_seq:06d}",
                        lineage_id=lineage_id,
                        storage_object=access.get("table_or_repository"),
                        storage_field=str(mapping.get("storage_field") or ""),
                        read_type=str(access.get("result_type") or "unknown"),
                        response_type=response_type,
                        response_field=str(mapping.get("response_field") or ""),
                        mapping_type="rename" if _normalized_field_token(mapping.get("storage_field")) != _normalized_field_token(mapping.get("response_field")) else "direct",
                        mapping_source="jooq_record_getter_to_constructor_position",
                        evidence=ev,
                    ))
                    counts["stored_field_to_response_field_mapping"] += 1
                emitted_pairs.add(pair_key)

    # Save-only gaps: write side exists but no access boundary found in the repository.
    write_ops = {str(a.get("operation") or "") for a in storage_accesses if a.get("access_kind") == "write" and a.get("writes_new_payload") is True}
    if write_ops and not access_by_operation:
        for op in sorted(write_ops)[:20]:
            mi = methods.get(op)
            if not mi:
                continue
            request_seq += 1
            facts.append(_source_inspection_request_fact(
                f"source_inspection_request_access_{request_seq:06d}",
                reason="access_boundary_not_found",
                priority="medium",
                target_operation=op,
                focus="The repository contains persistence writes but no outward access boundary was detected. Inspect callers/controllers only if access-side proof is decision-blocking.",
                related_evidence_refs=[],
                evidence=_op_file_evidence(mi, "java_stored_data_access_gap"),
                expected_observations=["controller/service exposing persisted object", "Kafka/HTTP outbound publication", "absence of access boundary in this repository"],
            ))
            counts["access_boundary_not_found_requests"] += 1
    return facts, dict(counts)



def _resolve_helper_batch_statement(batch_var: str, body: str, mi: dict[str, Any], methods: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    # Example: BatchBindStep b = prepareInsertHoldBatch(); where the helper returns dsl.batch(insertStep).
    m = re.search(rf"\b{re.escape(batch_var)}\b\s*=\s*(?P<helper>[A-Za-z_][A-Za-z0-9_]*)\s*\(\s*\)\s*;", body or "")
    if not m:
        return None
    helper_name = m.group("helper")
    class_name = str(mi.get("class_name") or "")
    helper = methods.get(f"{class_name}.{helper_name}")
    if not helper:
        return None
    helper_body = helper.get("body") or ""
    statements = _jooq_update_statement_slots(helper_body, bindable_only=True)
    links, inline = _jooq_batch_variable_links(helper_body)
    for stmt in inline.values():
        if stmt.get("slots"):
            return {**stmt, "helper_method": f"{class_name}.{helper_name}"}
    for stmt_var in links.values():
        stmt = statements.get(stmt_var)
        if stmt and stmt.get("slots"):
            return {**stmt, "helper_method": f"{class_name}.{helper_name}"}
    # Helper may return dsl.batch(insertStep) directly.
    ret = re.search(r"return\s+[^;]*?\.\s*batch\s*\(\s*(?P<stmt>[A-Za-z_][A-Za-z0-9_]*)\s*\)\s*;", helper_body, re.DOTALL)
    if ret:
        stmt = statements.get(ret.group("stmt"))
        if stmt and stmt.get("slots"):
            return {**stmt, "helper_method": f"{class_name}.{helper_name}"}
    return None


def _lambda_collection_for_var(body: str, lambda_var: str) -> str | None:
    if not lambda_var:
        return None
    patterns = [
        re.compile(r"(?P<collection>[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*\(\))?)\s*\.\s*forEach\s*\(\s*" + re.escape(lambda_var) + r"\s*->", re.DOTALL),
        re.compile(r"(?P<collection>[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*\(\))?)\s*\.\s*stream\s*\(\s*\)\s*\.\s*map\s*\(\s*" + re.escape(lambda_var) + r"\s*->", re.DOTALL),
    ]
    for pat in patterns:
        m = pat.search(body or "")
        if m:
            return _clean_expression(m.group("collection"))
    return None



def _find_call_spans(text: str, method_name: str) -> list[dict[str, Any]]:
    """Small text fallback for method calls inside lambdas when parsed calls are unavailable/incomplete."""
    out: list[dict[str, Any]] = []
    if not text or not method_name:
        return out
    needle = f".{method_name}("
    pos = 0
    while True:
        idx = text.find(needle, pos)
        if idx < 0:
            break
        # Receiver is the Java-ish expression immediately before `.method(`.
        j = idx - 1
        while j >= 0 and (text[j].isalnum() or text[j] in "_.$"):
            j -= 1
        receiver = text[j + 1:idx].strip()
        start = idx + len(needle) - 1
        depth = 0
        in_str: str | None = None
        esc = False
        end = None
        for k in range(start, len(text)):
            ch = text[k]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == in_str:
                    in_str = None
                continue
            if ch in {'"', "'"}:
                in_str = ch
                continue
            if ch == '(':
                depth += 1
            elif ch == ')':
                depth -= 1
                if depth == 0:
                    end = k
                    break
        if end is None:
            pos = idx + len(needle)
            continue
        args_text = text[start + 1:end]
        try:
            args = split_java_arguments(args_text)
        except Exception:
            args = [x.strip() for x in args_text.split(',') if x.strip()]
        out.append({
            "receiver": receiver,
            "method": method_name,
            "args": args,
            "args_text": args_text,
            "text": text[j + 1:end + 1].strip(),
            "line_start": text[:idx].count('\n') + 1,
            "text_fallback": True,
        })
        pos = end + 1
    return out


def _method_calls_with_text_fallback(mi: dict[str, Any], body: str, method_name: str) -> list[dict[str, Any]]:
    syntax = _method_info_syntax(mi, body)
    calls = [c for c in (syntax.get("method_calls") or []) if str(c.get("method") or "") == method_name]
    def _key(c: dict[str, Any]) -> tuple[str, str, tuple[str, ...]]:
        return (
            _clean_expression(c.get("receiver")),
            str(c.get("method") or ""),
            tuple(_clean_expression(a) for a in (c.get("args") or [])),
        )
    seen = {_key(c) for c in calls}
    seen_text = {_clean_expression(c.get("text")) for c in calls if c.get("text")}
    for c in _find_call_spans(body or "", method_name):
        key = _key(c)
        text_key = _clean_expression(c.get("text"))
        if key not in seen and text_key not in seen_text:
            calls.append(c)
            seen.add(key)
            seen_text.add(text_key)
    return calls


def _first_getter_binding_inside_expression(expr: str | None) -> tuple[str | None, str | None]:
    """Resolve the first direct getter embedded in a larger expression.

    Example: Optional.ofNullable(l.getCardId()).orElse(l.getCardWrapper().getCardId())
    deterministically yields (l, cardId). This is still source-code evidence;
    it is not a naming-only inference because the getter call is explicit.
    """
    value = _clean_expression(expr)
    if not value:
        return None, None
    m = re.search(r"\b(?P<obj>[A-Za-z_][A-Za-z0-9_]*)\s*\.\s*(?P<getter>get[A-Z][A-Za-z0-9_]*|is[A-Z][A-Za-z0-9_]*)\s*\(", value)
    if not m:
        return None, None
    getter = m.group("getter")
    if getter.startswith("get"):
        return m.group("obj"), _normalize_field_name(getter[3:])
    if getter.startswith("is"):
        return m.group("obj"), _normalize_field_name(getter[2:])
    return None, None


def _lambda_var_for_bind_call(body: str, batch_var: str | None) -> str | None:
    if not batch_var:
        return None
    m = re.search(r"\.\s*forEach\s*\(\s*(?P<var>[A-Za-z_][A-Za-z0-9_]*)\s*->\s*" + re.escape(batch_var) + r"\s*\.\s*bind\s*\(", body or "", re.DOTALL)
    return m.group("var") if m else None


def _enhanced_for_iteration_for_bind_call(body: str, batch_var: str | None) -> tuple[str | None, str | None]:
    """Return (iteration variable, collection expression) for an enhanced-for batch bind.

    Example: ``for (Record row : rows) { batch.bind(row.getId()); }``.
    The evidence is purely syntactic and is used only to connect the getter on
    ``row`` back to the declared collection ``rows``.
    """
    if not batch_var:
        return None, None
    pattern = re.compile(
        r"for\s*\([^:;]+\s+(?P<var>[A-Za-z_$][\w$]*)\s*:\s*(?P<collection>[^)]+)\)\s*\{(?P<body>.*?)\}",
        re.DOTALL,
    )
    for match in pattern.finditer(body or ""):
        loop_body = match.group("body") or ""
        if re.search(rf"\b{re.escape(batch_var)}\s*\.\s*bind\s*\(", loop_body):
            return match.group("var"), _clean_expression(match.group("collection"))
    return None, None


def _iteration_binding_for_bind_call(body: str, batch_var: str | None) -> tuple[str | None, str | None]:
    lambda_var = _lambda_var_for_bind_call(body, batch_var)
    if lambda_var:
        return lambda_var, _lambda_collection_for_var(body, lambda_var)
    return _enhanced_for_iteration_for_bind_call(body, batch_var)


def _sequence_assignments_for_collection(body: str, collection_var: str | None) -> dict[str, dict[str, Any]]:
    """Return field -> sequence assignment for simple collection initialization loops.

    Recognized pattern:
      for (T link : links) { link.setLinkId(dsl.nextval(LINK_SEQ)); }
    The result is used only when a later batch bind reads the same field from an
    element of the same collection.
    """
    collection = _clean_expression(collection_var)
    if not collection:
        return {}
    out: dict[str, dict[str, Any]] = {}
    loop_pat = re.compile(
        r"for\s*\([^:;]+\s+(?P<var>[A-Za-z_][A-Za-z0-9_]*)\s*:\s*" + re.escape(collection) + r"\s*\)\s*\{(?P<body>.*?)\}",
        re.DOTALL,
    )
    for lm in loop_pat.finditer(body or ""):
        var = lm.group("var")
        loop_body = lm.group("body") or ""
        set_pat = re.compile(
            re.escape(var) + r"\s*\.\s*set(?P<field>[A-Z][A-Za-z0-9_]*)\s*\(\s*[^;]*?\.\s*nextval\s*\(\s*(?P<seq>[A-Za-z_][A-Za-z0-9_.$]*)\s*\)",
            re.DOTALL,
        )
        for sm in set_pat.finditer(loop_body):
            field = _normalize_field_name(sm.group("field")) or sm.group("field")
            seq = _clean_expression(sm.group("seq"))
            out[field] = {
                "generation_kind": "sequence_nextval",
                "sequence_ref": seq,
                "sequence_name": seq.split(".")[-1] if seq else None,
                "assignment_expression": _clean_expression(sm.group(0)),
                "collection_variable": collection,
                "loop_variable": var,
            }
    return out

def _local_assignment_expression(mi: dict[str, Any], variable_name: str) -> str | None:
    var = _clean_expression(variable_name)
    if not var or not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", var):
        return None
    for assignment in mi.get("syntax_assignments") or []:
        if assignment.get("assignment_kind") != "variable_declaration":
            continue
        if _clean_expression(assignment.get("target")) == var:
            expr = _clean_expression(assignment.get("expression"))
            return expr or None
    return None


def _record_accessor_binding_from_expression(expr: str | None, mi: dict[str, Any]) -> tuple[str | None, str | None]:
    """Resolve Java-record-style accessors such as wrapper.phoneId().

    This is intentionally limited to zero-argument calls on method parameters so
    arbitrary fluent APIs are not treated as data fields.
    """
    value = _clean_expression(expr)
    if not value:
        return None, None
    param_names = {str(p.get("name") or "") for p in mi.get("params") or [] if p.get("name")}
    excluded = {"toString", "hashCode", "getClass", "size", "isEmpty", "stream", "iterator"}
    for call in mi.get("method_calls") or []:
        if _clean_expression(call.get("text")) != value:
            continue
        receiver = _clean_expression(call.get("receiver"))
        method = str(call.get("method") or "")
        if receiver in param_names and method and not (call.get("args") or []) and method not in excluded:
            if not method.startswith(("get", "is", "set", "with")):
                return receiver, _normalize_field_name(method) or method
    m = re.match(r"^(?P<receiver>[A-Za-z_][A-Za-z0-9_]*)\.(?P<method>[A-Za-z_][A-Za-z0-9_]*)\(\)$", value)
    if m and m.group("receiver") in param_names and m.group("method") not in excluded:
        method = m.group("method")
        if not method.startswith(("get", "is", "set", "with")):
            return m.group("receiver"), _normalize_field_name(method) or method
    return None, None


def _source_binding_from_expression(expr: str | None, mi: dict[str, Any], *, _visited: set[str] | None = None) -> tuple[str | None, str | None, str | None]:
    """Return source object, source field and expression for a DAO-local expression."""
    source_expr = _clean_expression(expr)
    if not source_expr:
        return None, None, None
    visited = _visited or set()
    if source_expr in visited:
        return None, None, source_expr
    visited.add(source_expr)

    # Local alias/value variable, e.g. `String phoneId = wrapper.getPhoneId();`
    # followed by `.set(PHONE.PHONEID, phoneId)`.  Resolve it back to the DAO
    # method parameter getter before the cross-DAO formal/actual binding step.
    alias_expr = _local_assignment_expression(mi, source_expr)
    if alias_expr and alias_expr != source_expr:
        source_obj, source_field, resolved_expr = _source_binding_from_expression(alias_expr, mi, _visited=visited)
        if source_obj and source_field:
            return source_obj, source_field, resolved_expr or alias_expr

    if "Optional." in source_expr or ".orElse" in source_expr or ".map(" in source_expr:
        source_obj, source_field = _first_getter_binding_inside_expression(source_expr)
        if source_obj and source_field:
            return source_obj, source_field, source_expr
    source_obj, source_field = _getter_binding_from_expression(source_expr, mi)
    if source_obj and source_field:
        return source_obj, source_field, source_expr
    source_obj, source_field = _first_getter_binding_inside_expression(source_expr)
    if source_obj and source_field:
        return source_obj, source_field, source_expr
    source_obj, source_field = _record_accessor_binding_from_expression(source_expr, mi)
    if source_obj and source_field:
        return source_obj, source_field, source_expr
    for p in mi.get("params") or []:
        name = str(p.get("name") or "")
        if name and re.search(rf"\b{re.escape(name)}\b", source_expr):
            return name, _normalize_field_name(name) or name, source_expr
    return None, None, source_expr


def _jooq_batch_bind_mappings(methods: dict[str, dict[str, Any]]) -> list[Fact]:
    facts: list[Fact] = []
    seq = 0
    for op, mi in sorted(methods.items()):
        body = mi.get("body") or ""
        statements = _jooq_update_statement_slots(body, bindable_only=True)
        batch_links, inline_statements = _jooq_batch_variable_links(body)
        for call in _method_calls_with_text_fallback(mi, body, "bind"):
            batch_var = _clean_expression(call.get("receiver"))
            stmt_var = batch_links.get(batch_var)
            stmt = statements.get(stmt_var or "") or inline_statements.get(batch_var or "") or _resolve_helper_batch_statement(batch_var or "", body, mi, methods)
            if not stmt:
                continue
            args = list(call.get("args") or [])
            slots = list(stmt.get("slots") or [])
            iteration_var, collection_var = _iteration_binding_for_bind_call(body, batch_var)
            sequence_assignments = _sequence_assignments_for_collection(body, collection_var)
            mappings: list[dict[str, Any]] = []
            for i, slot in enumerate(slots):
                source_expr = _clean_expression(args[i]) if i < len(args) else None
                source_var, source_field, source_expr = _source_binding_from_expression(source_expr, mi) if source_expr else (None, None, None)
                generation = sequence_assignments.get(str(source_field or "")) if source_var == iteration_var and source_field else None
                mapping = {
                    "bind_index": i,
                    "storage_field": slot.get("field"),
                    "storage_field_ref": slot.get("field_ref"),
                    "field_role": slot.get("role"),
                    "source_expression": source_expr,
                    "source_object": source_var,
                    "source_collection": collection_var if source_var == iteration_var and collection_var else None,
                    "source_field": source_field,
                    "mapping_status": "candidate_bind_order_mapping" if source_expr else "unresolved_missing_bind_arg",
                }
                if generation:
                    mapping["source_generation"] = generation
                mappings.append(mapping)
            seq += 1
            props = {
                "jooq_batch_bind_mapping_id": f"jooq_batch_bind_mapping_{seq:06d}",
                "operation": op,
                "class_name": mi.get("class_name"),
                "method_name": mi.get("method_name"),
                "batch_variable": batch_var,
                "statement_variable": stmt_var,
                "helper_method": stmt.get("helper_method"),
                "storage_table": stmt.get("table"),
                "storage_table_ref": stmt.get("table_ref"),
                "mapping_kind": "jooq_batch_bind_order",
                "mapping_status": "candidate",
                "mappings": mappings,
                "write_target_fields": [m for m in mappings if m.get("field_role") == "write_target_field"],
                "where_key_fields": [m for m in mappings if m.get("field_role") == "where_key_field"],
                "evidence_policy": "bind-order mapping is technical candidate evidence; it does not make business/risk decisions",
            }
            facts.append(Fact(
                fact_type="jooq_batch_bind_mapping",
                name=f"{op}: {stmt.get('table') or 'unknown'} batch.bind",
                properties={k: v for k, v in props.items() if v not in (None, [], {})},
                evidence=_op_file_evidence(mi, "java_jooq_batch_bind_mapping"),
            ))
    return facts




def _jooq_batch_bind_write_facts(batch_facts: list[Fact]) -> list[Fact]:
    """Promote direct jOOQ batch-bind mapping into persistent write/lineage evidence.

    The underlying `jooq_batch_bind_mapping` remains available as the detailed
    bind-order proof. These additional facts make the write discoverable through
    the ordinary persistent-write and source-to-storage evidence API views.
    """
    facts: list[Fact] = []
    write_seq = 0
    lineage_seq = 0
    for bf in batch_facts:
        props = bf.properties or {}
        op = str(props.get("operation") or "")
        table = str(props.get("storage_table") or "")
        if not op or not table:
            continue
        fields = list(props.get("write_target_fields") or [])
        if not fields:
            continue
        write_seq += 1
        persistent_write_id = f"persistent_write_jooq_batch_{write_seq:06d}"
        access = {
            "storage_access_id": props.get("jooq_batch_bind_mapping_id"),
            "operation": op,
            "access_kind": "write",
            "write_kind": props.get("statement_kind") or "batch_insert",
            "operation_kind": props.get("statement_kind") or "batch_insert",
            "storage_method": "batch.bind",
            "receiver_expression": props.get("batch_variable"),
            "writes_new_payload": True,
            "payload_role": "jooq_batch_bind_arguments",
            "table_or_repository": table,
            "storage_resolution_level": "confirmed_sql",
            "storage_resolution_status": "resolved_jooq_batch_bind_order",
            "payload_expression": props.get("batch_variable"),
            "candidate_signals": [],
        }
        facts.append(_persistent_write_fact(
            persistent_write_id,
            access,
            saved_object=table,
            written_fields=[str(m.get("storage_field")) for m in fields if m.get("storage_field")],
            evidence=list(bf.evidence or []),
            type_details={"container_kind": "batch_bind"},
            dao_type=str(props.get("class_name") or "") or None,
        ))
        for m in fields:
            storage_field = str(m.get("storage_field") or "")
            if not storage_field:
                continue
            source_field = str(m.get("source_field") or "") or None
            source_obj = str(m.get("source_object") or "") or None
            missing = [] if source_field else ["source_field_not_resolved"]
            generation = m.get("source_generation") if isinstance(m.get("source_generation"), dict) else None
            assignment_kind = "jooq_batch_bind_sequence_generated_field" if generation else "jooq_batch_bind_call_argument_mapping"
            lineage_seq += 1
            facts.append(_source_to_storage_lineage_fact(
                f"source_to_storage_lineage_jooq_batch_{lineage_seq:06d}",
                source_kind="method_input",
                source_operation=op,
                source_payload=source_obj or "batch_bind_argument",
                source_field=source_field,
                source_field_role=_field_role(source_field or ""),
                storage_operation=op,
                storage_call=f"{props.get('batch_variable') or 'batch'}.bind(...) -> {table}",
                storage_method="batch.bind",
                storage_access_id=str(props.get("jooq_batch_bind_mapping_id") or "") or None,
                persistent_write_id=persistent_write_id,
                storage_target=table,
                storage_resolution_level="confirmed_sql",
                saved_object=table,
                saved_object_field=storage_field,
                storage_field=storage_field,
                assignment_kind=assignment_kind,
                assignment_expression=str(m.get("source_expression") or ""),
                origin_expression=str((generation or {}).get("assignment_expression") or m.get("source_expression") or ""),
                path=[op, str(props.get("jooq_batch_bind_mapping_id") or "jooq_batch_bind_mapping"), f"{table}.{storage_field}"],
                missing_links=missing,
                evidence_refs=[str(props.get("jooq_batch_bind_mapping_id") or "")],
                evidence=list(bf.evidence or []),
                source_container=source_obj,
            ))
    return facts



def _methods_by_class_method(methods: dict[str, dict[str, Any]]) -> dict[tuple[str, str], list[dict[str, Any]]]:
    out: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for mi in methods.values():
        cls = str(mi.get("class_name") or "")
        meth = str(mi.get("method_name") or "")
        if cls and meth:
            out[(cls, meth)].append(mi)
    return out


def _parsed_methods_by_class_method(files: list[Path]) -> dict[tuple[str, str], list[dict[str, Any]]]:
    """Return all parsed methods keyed by simple class/method, preserving duplicate simple class names.

    The legacy method index is keyed as Class.method, so same simple class
    names in different packages can overwrite each other. Cross-DAO resolution
    needs all DAO implementations because injected fields often expose only a
    simple receiver type. Candidates from this index remain candidate-only.
    """
    out: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    try:
        parsed_files, _warnings = parse_java_files(files)
    except Exception:
        return out
    for parsed in parsed_files:
        for cls in parsed.classes:
            for method in cls.methods:
                params = [{"name": p.name, "type": p.type, "raw": p.raw, "annotations": [a.name for a in p.annotations]} for p in method.params]
                syntax = method_syntax_dict(method)
                raw_var_types = {p.get("name", ""): _strip_java_modifiers(p.get("type")) for p in params if p.get("name")}
                var_types = {name: _simple_type_name(raw) for name, raw in raw_var_types.items()}
                for assignment in syntax.get("syntax_assignments") or []:
                    if assignment.get("assignment_kind") != "variable_declaration":
                        continue
                    target = str(assignment.get("target") or "")
                    raw = _strip_java_modifiers(assignment.get("declared_type"))
                    if target and raw and raw not in {"var", "unknown"}:
                        raw_var_types[target] = raw
                        var_types[target] = _simple_type_name(raw)
                mi = {
                    "operation": f"{cls.name}.{method.name}",
                    "class_name": cls.name,
                    "class_fqcn": f"{parsed.package}.{cls.name}" if parsed.package else cls.name,
                    "package": parsed.package,
                    "method_name": method.name,
                    "return_type": _normalize_java_type(method.return_type),
                    "params": params,
                    "param_names": [p.get("name") for p in params if p.get("name")],
                    "body": method.body or method.text,
                    "file": method.file,
                    "line_start": method.line_start,
                    "line_end": method.line_end,
                    "raw_var_types": raw_var_types,
                    "var_types": var_types,
                    "source_scope": _source_scope_for_file(method.file),
                    **syntax,
                }
                out[(str(cls.name), str(method.name))].append(mi)
    return out


def _storage_call_args_for_access(access: dict[str, Any], mi: dict[str, Any]) -> list[str]:
    receiver = _clean_expression(access.get("receiver_expression"))
    method = str(access.get("storage_method") or "")
    payload = _clean_expression(access.get("payload_expression"))
    if not receiver or not method:
        return []
    syntax = _method_info_syntax(mi, mi.get("body") or "")
    candidates: list[list[str]] = []
    for call in syntax.get("method_calls") or []:
        if _clean_expression(call.get("receiver")) != receiver:
            continue
        if str(call.get("method") or "") != method:
            continue
        args = [_clean_expression(a) for a in (call.get("args") or [])]
        if payload and payload in args:
            return args
        candidates.append(args)
    return candidates[0] if candidates else []


def _dao_jooq_direct_field_mappings(dao_mi: dict[str, Any]) -> list[dict[str, Any]]:
    body = dao_mi.get("body") or ""
    out: list[dict[str, Any]] = []
    patterns = [
        ("insert", re.compile(r"\.\s*insertInto\s*\(\s*(?P<table>[A-Za-z_][A-Za-z0-9_.$]*)\s*\)(?P<chain>.*?);", re.DOTALL)),
        ("update", re.compile(r"\.\s*update\s*\(\s*(?P<table>[A-Za-z_][A-Za-z0-9_.$]*)\s*\)(?P<chain>.*?);", re.DOTALL)),
    ]
    for statement_kind, pat in patterns:
        for m in pat.finditer(body):
            table = _jooq_table_constant(m.group("table"))
            chain = m.group("chain") or ""
            for slot in _jooq_set_slots_from_chain(chain, bindable_only=False):
                expr = slot.get("value_expression")
                source_obj, source_field, source_expr = _source_binding_from_expression(str(expr or ""), dao_mi)
                if not source_obj or not source_expr:
                    continue
                out.append({
                    "mapping_kind": "jooq_direct_set_call_argument_mapping",
                    "statement_kind": statement_kind,
                    "storage_table": table,
                    "storage_table_ref": m.group("table"),
                    "storage_field": slot.get("field"),
                    "storage_field_ref": slot.get("field_ref"),
                    "field_role": "write_target_field",
                    "source_object": source_obj,
                    "source_field": source_field,
                    "source_expression": source_expr,
                    "dao_operation": dao_mi.get("operation"),
                })
    return out


def _dao_jooq_batch_field_mappings(dao_mi: dict[str, Any], methods: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    body = dao_mi.get("body") or ""
    statements = _jooq_update_statement_slots(body, bindable_only=True)
    batch_links, inline_statements = _jooq_batch_variable_links(body)
    out: list[dict[str, Any]] = []
    for call in _method_calls_with_text_fallback(dao_mi, body, "bind"):
        batch_var = _clean_expression(call.get("receiver"))
        stmt_var = batch_links.get(batch_var)
        stmt = statements.get(stmt_var or "") or inline_statements.get(batch_var or "") or _resolve_helper_batch_statement(batch_var or "", body, dao_mi, methods)
        if not stmt:
            continue
        args = [_clean_expression(a) for a in (call.get("args") or [])]
        iteration_var, collection_var = _iteration_binding_for_bind_call(body, batch_var)
        sequence_assignments = _sequence_assignments_for_collection(body, collection_var)
        for i, slot in enumerate(list(stmt.get("slots") or [])):
            if slot.get("role") != "write_target_field":
                continue
            source_expr = args[i] if i < len(args) else None
            source_obj, source_field, source_expr = _source_binding_from_expression(source_expr, dao_mi) if source_expr else (None, None, None)
            if source_obj == iteration_var and collection_var:
                source_obj = collection_var
            elif source_obj and source_obj not in {str(p.get("name")) for p in dao_mi.get("params") or [] if p.get("name")}:
                source_obj = _lambda_collection_for_var(body, source_obj) or source_obj
            if not source_obj or not source_expr:
                continue
            item = {
                "mapping_kind": "jooq_batch_bind_call_argument_mapping",
                "statement_kind": stmt.get("statement_kind"),
                "storage_table": stmt.get("table"),
                "storage_table_ref": stmt.get("table_ref"),
                "storage_field": slot.get("field"),
                "storage_field_ref": slot.get("field_ref"),
                "field_role": "write_target_field",
                "source_object": source_obj,
                "source_field": source_field,
                "source_expression": source_expr,
                "dao_operation": dao_mi.get("operation"),
                "helper_method": stmt.get("helper_method"),
            }
            generation = sequence_assignments.get(str(source_field or "")) if source_obj == collection_var and source_field else None
            if generation:
                item["source_generation"] = generation
            out.append(item)
    return out


def _camel_to_upper_snake(value: str | None) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    raw = re.sub(r"Record$", "", raw)
    raw = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", raw)
    raw = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", "_", raw)
    return raw.upper() if raw else None


def _record_type_by_variable_from_body(body: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for m in re.finditer(r"\b(?P<type>[A-Za-z_][A-Za-z0-9_]*Record)\s+(?P<var>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*new\s+(?P=type)\s*\(", body or ""):
        out[m.group("var")] = m.group("type")
    return out


def _dao_jooq_record_batch_insert_field_mappings(dao_mi: dict[str, Any]) -> list[dict[str, Any]]:
    """Resolve DAO param getter -> generated jOOQ Record setters -> batchInsert.

    Real app pattern:
      List<PhoneRecord> rows = phones.stream().map(p -> {
        PhoneRecord record = new PhoneRecord();
        record.setPhoneid(p.getPhoneId());
        return record;
      }).collect(...);
      dsl.batchInsert(rows).execute();

    The emitted rows remain candidate cross-DAO mappings; constants/computed values
    are ignored because they are not source-to-storage field evidence.
    """
    body = dao_mi.get("body") or ""
    syntax = _method_info_syntax(dao_mi, body)
    batch_insert_args = {
        _clean_expression((call.get("args") or [None])[0])
        for call in syntax.get("method_calls") or []
        if str(call.get("method") or "") == "batchInsert" and (call.get("args") or [])
    }
    if not batch_insert_args:
        return []
    record_type_by_var = _record_type_by_variable_from_body(body)
    out: list[dict[str, Any]] = []
    record_setter_bindings = _jooq_record_set_bindings(body) + _setter_bindings_any_source(body, dao_mi)
    for binding in record_setter_bindings:
        target_var = str(binding.get("target_variable") or "")
        record_type = record_type_by_var.get(target_var)
        if not record_type:
            continue
        source_expr = str(binding.get("source_expression") or "")
        source_obj, source_field, resolved_expr = _source_binding_from_expression(source_expr, dao_mi)
        if source_obj and source_obj not in {str(p.get("name")) for p in dao_mi.get("params") or [] if p.get("name")}:
            source_obj = _lambda_collection_for_var(body, source_obj) or source_obj
        if not source_obj or not source_field:
            continue
        storage_field = binding.get("target_field")
        out.append({
            "mapping_kind": "jooq_record_batch_insert_call_argument_mapping",
            "statement_kind": "batch_insert",
            "storage_table": _camel_to_upper_snake(record_type),
            "storage_table_ref": record_type,
            "storage_field": storage_field,
            "storage_field_ref": f"{record_type}.{storage_field}" if storage_field else None,
            "field_role": "write_target_field",
            "source_object": source_obj,
            "source_field": source_field,
            "source_expression": resolved_expr or source_expr,
            "dao_operation": dao_mi.get("operation"),
            "record_type": record_type,
            "batch_insert_args": sorted(x for x in batch_insert_args if x),
        })
    return out


def _dao_jooq_field_mappings(
    dao_mi: dict[str, Any],
    methods: dict[str, dict[str, Any]],
    *,
    _visited: set[tuple[str, str, int]] | None = None,
    _depth: int = 0,
) -> list[dict[str, Any]]:
    """Return field-level JOOQ mappings visible through a DAO method.

    Besides mappings written directly in the method body, follow deterministic
    same-class helper delegation such as ``merge(add) -> insertRecords(add)``.
    Only a unique source-declared helper with matching arity is followed and a
    child formal parameter is lifted only when the caller passes one of its own
    formal parameters in the same position.  This deliberately does not emulate
    arbitrary Java execution or infer semantic equivalence from method names.
    """
    visited = set(_visited or set())
    visit_key = (
        str(dao_mi.get("file") or ""),
        str(dao_mi.get("operation") or ""),
        int(dao_mi.get("line_start") or 0),
    )
    if visit_key in visited or _depth > 4:
        return []
    visited.add(visit_key)

    out = _dao_jooq_direct_field_mappings(dao_mi)
    out.extend(_dao_jooq_batch_field_mappings(dao_mi, methods))
    out.extend(_dao_jooq_record_batch_insert_field_mappings(dao_mi))

    # Source-declared private/helper delegation inside the same concrete class.
    # This captures thin DAO wrappers without turning every call-chain into a
    # runtime model.
    if _depth < 4:
        parent_file = str(dao_mi.get("file") or "")
        parent_class = str(dao_mi.get("class_fqcn") or dao_mi.get("class_name") or "")
        parent_simple = _simple_type_name(parent_class)
        parent_params = [str(p.get("name") or "") for p in dao_mi.get("params") or []]
        syntax = _method_info_syntax(dao_mi, dao_mi.get("body") or "")
        for call in syntax.get("method_calls") or []:
            receiver = _clean_expression(call.get("receiver"))
            if receiver not in {"", "this", parent_simple, parent_class}:
                continue
            method_name = str(call.get("method") or "")
            args = [_clean_expression(arg) for arg in (call.get("args") or [])]
            if not method_name:
                continue
            candidates = [
                candidate
                for candidate in methods.values()
                if str(candidate.get("file") or "") == parent_file
                and _simple_type_name(candidate.get("class_fqcn") or candidate.get("class_name")) == parent_simple
                and str(candidate.get("method_name") or "") == method_name
                and len(candidate.get("params") or []) == len(args)
                and str(candidate.get("operation") or "") != str(dao_mi.get("operation") or "")
            ]
            # Same-name/same-arity overloads cannot be resolved safely here.
            if len(candidates) != 1:
                continue
            child = candidates[0]
            child_params = [str(p.get("name") or "") for p in child.get("params") or []]
            child_mappings = _dao_jooq_field_mappings(
                child,
                methods,
                _visited=visited,
                _depth=_depth + 1,
            )
            for mapping in child_mappings:
                source_object = str(mapping.get("source_object") or "")
                if source_object not in child_params:
                    continue
                pos = child_params.index(source_object)
                if pos >= len(args):
                    continue
                actual = args[pos]
                # Lift only direct parent parameters.  Local expressions remain
                # available in the child evidence but are not guessed across the
                # wrapper boundary.
                if actual not in parent_params:
                    continue
                lifted = dict(mapping)
                lifted["source_object"] = actual
                helper = str(mapping.get("helper_method") or "")
                child_op = str(child.get("operation") or method_name)
                lifted["helper_method"] = f"{child_op} -> {helper}" if helper else child_op
                lifted["mapping_kind"] = f"same_class_delegate:{mapping.get('mapping_kind') or 'jooq_mapping'}"
                out.append(lifted)

    # Stable de-duplication: same DAO source object/field -> same storage field.
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for item in out:
        key = (
            str(item.get("storage_table") or ""),
            str(item.get("storage_field") or ""),
            str(item.get("source_object") or ""),
            str(item.get("source_field") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _actual_origin_for_cross_dao(
    actual_expr: str,
    *,
    dao_source_object: str | None,
    dao_source_field: str | None,
    caller_mi: dict[str, Any],
    variable_origins: dict[str, dict[str, Any]],
    ingress_by_param: dict[str, dict[str, Any]],
    interprocedural_index: dict[str, Any] | None = None,
) -> dict[str, Any]:
    actual = _clean_expression(actual_expr)
    params = {str(p.get("name")): p for p in caller_mi.get("params") or [] if p.get("name")}
    field = _normalize_field_name(dao_source_field) or _normalize_field_name(dao_source_object) or dao_source_field or dao_source_object

    # Direct actual parameter, e.g. dao.insertHistory(login, phoneNumber, blockCode).
    # A DAO implementation may read a nested zero-argument collection accessor
    # from that parameter (batch.records().field).  Resolve that accessor before
    # falling back to the coarse method-input origin; otherwise the canonical
    # source-to-storage row loses an already-proven upstream ingress path.
    if actual in params:
        if interprocedural_index and field and "." in str(field):
            accessor, target_field = str(field).split(".", 1)
            if accessor and target_field:
                resolved = _interprocedural_container_parameter_origin(
                    operation=str(caller_mi.get("operation") or ""),
                    parameter=actual,
                    accessor=accessor,
                    target_field=target_field,
                    index=interprocedural_index,
                )
                if resolved:
                    return resolved
        p = params[actual]
        details = _java_type_details(p.get("type"))
        origin = ingress_by_param.get(actual)
        source_kind = _technical_source_kind(_source_boundary_for_origin(origin)) if origin else "method_input"
        return {
            "source_kind": source_kind,
            "source_operation": origin.get("operation") if origin else caller_mi.get("operation"),
            "source_payload": details.get("element_type") or _simple_type_name(p.get("type")),
            "source_container": actual if details.get("container_kind") else None,
            "source_container_type": details.get("type") if details.get("container_kind") else None,
            "source_element_type": details.get("element_type"),
            "source_payload_parameter": actual,
            "source_field": field or actual,
            "origin_expression": actual,
            "missing_links": ["cross_dao_call_argument_mapping_candidate"] + ([] if origin else ["source_kind_not_confirmed"]),
        }

    # Collection accessor actual, e.g. new ArrayList<>(batch.forInsertHold()) or batch.history().
    for name, p in params.items():
        if not name or not _contains_symbol(actual, name):
            continue
        details = _java_type_details(p.get("type"))
        accessor = None
        m = re.search(rf"\b{re.escape(name)}\s*\.\s*(?P<method>[A-Za-z_][A-Za-z0-9_]*)\s*\(\s*\)", actual)
        if m:
            accessor = m.group("method")
        origin = ingress_by_param.get(name)
        source_kind = _technical_source_kind(_source_boundary_for_origin(origin)) if origin else "method_input"
        source_field = f"{accessor}.{field}" if accessor and field else (accessor or field or name)
        if interprocedural_index and accessor:
            resolved = _interprocedural_container_parameter_origin(
                operation=str(caller_mi.get("operation") or ""),
                parameter=name,
                accessor=accessor,
                target_field=str(field or ""),
                index=interprocedural_index,
            )
            if resolved:
                return resolved
        return {
            "source_kind": source_kind,
            "source_operation": origin.get("operation") if origin else caller_mi.get("operation"),
            "source_payload": details.get("element_type") or _simple_type_name(p.get("type")),
            "source_container": name if details.get("container_kind") else None,
            "source_container_type": details.get("type") if details.get("container_kind") else None,
            "source_element_type": details.get("element_type"),
            "source_payload_parameter": name,
            "source_field": source_field,
            "origin_expression": actual,
            "missing_links": ["cross_dao_call_argument_mapping_candidate"] + ([] if origin else ["source_kind_not_confirmed"]),
        }

    # Local variable actual. Keep field mapping candidate but do not pretend the upstream source is known.
    if interprocedural_index and _simple_java_identifier(actual) and field:
        local_source = _local_collection_field_source(
            caller_mi=caller_mi,
            collection_symbol=actual,
            target_field=str(field),
        )
        if local_source:
            resolved = _trace_parameter_to_ingress(
                operation=str(caller_mi.get("operation") or ""),
                parameter=local_source["parameter"],
                source_field=local_source["source_field"],
                accessor=None,
                index=interprocedural_index,
                visited=set(),
                depth=0,
            )
            if resolved:
                resolved["missing_links"] = sorted(set(
                    list(resolved.get("missing_links") or [])
                    + ["cross_dao_call_argument_mapping_candidate", "local_collection_field_provenance_candidate"]
                ))
                return resolved
    vorig = variable_origins.get(actual) or {}
    return {
        "source_kind": _technical_source_kind(str(vorig.get("ultimate_origin_kind") or "method_input"), fallback="method_input"),
        "source_operation": vorig.get("origin_operation") or caller_mi.get("operation"),
        "source_payload": vorig.get("origin_payload") or vorig.get("type") or "unknown",
        "source_container": vorig.get("origin_container"),
        "source_container_type": vorig.get("origin_container_type"),
        "source_element_type": vorig.get("origin_element_type"),
        "source_payload_parameter": vorig.get("origin_payload_parameter"),
        "source_field": field,
        "origin_expression": actual,
        "missing_links": ["cross_dao_call_argument_mapping_candidate", "source_kind_not_confirmed"],
    }


def _normalized_field_token(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def _production_method(mi: dict[str, Any] | None) -> bool:
    return bool(mi) and _source_scope_for_file(mi.get("file")) == "production_code"


def _interprocedural_index(
    *,
    methods: dict[str, dict[str, Any]],
    class_infos: dict[str, dict[str, Any]],
    calls: list[dict[str, Any]],
    origins_by_operation: dict[str, list[dict[str, Any]]],
    builder_field_mapping_facts: list[Fact],
    factory_method_mapping_facts: list[Fact] | None = None,
    schema_fields: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    variants = _method_variants(methods, class_infos)
    variants_by_operation: dict[str, list[dict[str, Any]]] = defaultdict(list)
    variants_by_signature: dict[str, dict[str, Any]] = {}
    variants_by_class: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for mi in variants:
        variants_by_operation[str(mi.get("operation") or "")].append(mi)
        signature = str(mi.get("operation_signature") or "")
        if signature:
            variants_by_signature[signature] = mi
        variants_by_class[_simple_type_name(mi.get("class_name"))].append(mi)

    reverse_calls: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for call in calls:
        reverse_calls[str(call.get("callee_operation_id") or "")].append(call)
        signature = str(call.get("callee_operation_signature") or "")
        if signature:
            reverse_calls[signature].append(call)

    synthetic_calls = _synthetic_java_dispatch_calls(
        methods=methods,
        class_infos=class_infos,
        variants_by_class=variants_by_class,
        observed_calls=calls,
    )
    for call in synthetic_calls:
        reverse_calls[str(call.get("callee_operation_id") or "")].append(call)
        signature = str(call.get("callee_operation_signature") or "")
        if signature:
            reverse_calls[signature].append(call)

    builder_mappings: list[dict[str, Any]] = []
    for fact in builder_field_mapping_facts:
        props = dict(fact.properties or {})
        if props.get("source_scope") != "production_code":
            continue
        builder_mappings.append(props)
    factory_mappings: list[dict[str, Any]] = []
    for fact in factory_method_mapping_facts or []:
        props = dict(fact.properties or {})
        if props.get("source_scope") != "production_code":
            continue
        factory_mappings.append(props)
    return {
        "methods": methods,
        "variants_by_operation": variants_by_operation,
        "variants_by_signature": variants_by_signature,
        "variants_by_class": variants_by_class,
        "reverse_calls": reverse_calls,
        "synthetic_dispatch_calls": synthetic_calls,
        "origins_by_operation": origins_by_operation,
        "builder_mappings": builder_mappings,
        "factory_mappings": factory_mappings,
        "schema_fields": schema_fields or {},
    }


def _class_info_by_name(class_infos: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for key, info in class_infos.items():
        if not isinstance(info, dict):
            continue
        simple = _simple_type_name(info.get("class_name") or key)
        fqcn = str(info.get("fqcn") or "")
        if simple:
            out.setdefault(simple, info)
        if fqcn:
            out.setdefault(fqcn, info)
    return out


def _superclass_chain(
    class_name: str | None,
    *,
    class_info_index: dict[str, dict[str, Any]],
) -> list[str]:
    out: list[str] = []
    current = _simple_type_name(class_name)
    seen: set[str] = set()
    while current and current not in seen:
        seen.add(current)
        info = class_info_index.get(current) or {}
        parent = _simple_type_name(info.get("superclass"))
        if not parent:
            break
        out.append(parent)
        current = parent
    return out


def _dispatch_argument_bindings(
    *,
    caller_mi: dict[str, Any],
    callee_mi: dict[str, Any],
    args: list[str],
) -> list[dict[str, Any]]:
    caller_params = {str(p.get("name") or ""): p for p in caller_mi.get("params") or []}
    callee_params = [p for p in callee_mi.get("params") or [] if p.get("name")]
    bindings: list[dict[str, Any]] = []
    for idx, callee_param in enumerate(callee_params):
        if idx >= len(args):
            break
        actual = _clean_expression(args[idx])
        caller_source_parameter = actual if actual in caller_params else None
        bindings.append({
            "caller_expression": actual,
            "caller_source_parameter": caller_source_parameter,
            "callee_parameter": str(callee_param.get("name") or ""),
            "relation": "same_object" if caller_source_parameter else "derived_object",
            "source_type": _simple_type_name((caller_mi.get("raw_var_types") or {}).get(actual)) or "unknown",
            "target_type": _simple_type_name(callee_param.get("type")) or "unknown",
            "via_local_variable": None if caller_source_parameter else actual,
            "binding_strength": 0.72 if caller_source_parameter else 0.58,
        })
    return bindings


def _synthetic_java_dispatch_calls(
    *,
    methods: dict[str, dict[str, Any]],
    class_infos: dict[str, dict[str, Any]],
    variants_by_class: dict[str, list[dict[str, Any]]],
    observed_calls: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Recover source-proven inherited and virtual-dispatch call edges.

    The regular call builder intentionally avoids inventing targets for unresolved
    Java calls.  For persistence provenance we can safely add two narrower edge
    classes that are fully supported by source declarations:

    * a receiver class inherits a concrete method from its declared superclass;
    * a base-class ``this`` call targets an abstract/overridable method that a
      concrete subclass overrides.

    These are candidate execution edges only.  They do not create storage or
    business facts by themselves and remain tied to exact method name/arity.
    """
    info_index = _class_info_by_name(class_infos)
    observed_keys = {
        (
            str(call.get("caller_operation_id") or ""),
            str(call.get("method_name") or ""),
            int((call.get("line_start") or 0)),
            _clean_expression(call.get("receiver_expression")),
        )
        for call in observed_calls
    }
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, int]] = set()

    def add_call(
        *,
        caller_mi: dict[str, Any],
        callee_mi: dict[str, Any],
        call: dict[str, Any],
        resolution_kind: str,
        receiver_type: str,
    ) -> None:
        args = list(call.get("args") or [])
        key = (
            str(caller_mi.get("operation_signature") or caller_mi.get("operation") or ""),
            str(callee_mi.get("operation_signature") or callee_mi.get("operation") or ""),
            _clean_expression(call.get("text")),
            int(call.get("line_start") or 0),
        )
        if key in seen:
            return
        seen.add(key)
        out.append({
            "call_id": f"synthetic_dispatch_{len(out) + 1:06d}",
            "kind": "method_call",
            "caller_operation_id": caller_mi.get("operation"),
            "caller_operation_signature": caller_mi.get("operation_signature"),
            "caller_method": caller_mi.get("operation"),
            "callee_operation_id": callee_mi.get("operation"),
            "callee_operation_signature": callee_mi.get("operation_signature"),
            "callee_method": callee_mi.get("operation"),
            "receiver_expression": _clean_expression(call.get("receiver")) or "this",
            "receiver_type": receiver_type,
            "declared_receiver_type": receiver_type,
            "method_name": call.get("method"),
            "resolution_kind": resolution_kind,
            "overload_resolution": "exact_arity_source_dispatch",
            "overload_candidate_count": 1,
            "callee_parameter_types": [_simple_type_name(p.get("type")) for p in callee_mi.get("params") or []],
            "argument_bindings": _dispatch_argument_bindings(
                caller_mi=caller_mi,
                callee_mi=callee_mi,
                args=args,
            ),
            "argument_relation": "source_dispatch",
            "file": caller_mi.get("file"),
            "line_start": call.get("line_start"),
            "line_end": call.get("line_end"),
            "snippet": _clean_expression(call.get("text")),
            "match_strength": 0.68 if resolution_kind == "inherited_method_dispatch" else 0.62,
        })

    # Calls such as concreteHandler.handle(...) where handle is inherited and
    # therefore absent from the concrete class's own method table.
    for caller_mi in methods.values():
        if not _production_method(caller_mi):
            continue
        var_types = caller_mi.get("raw_var_types") or {}
        for call in caller_mi.get("method_calls") or []:
            receiver = _clean_expression(call.get("receiver"))
            method_name = str(call.get("method") or "")
            if not receiver or not method_name:
                continue
            observed_key = (
                str(caller_mi.get("operation") or ""),
                method_name,
                int(call.get("line_start") or 0),
                receiver,
            )
            if observed_key in observed_keys:
                continue
            receiver_type = _simple_type_name(var_types.get(receiver))
            if not receiver_type:
                continue
            arity = len(call.get("args") or [])
            for parent in _superclass_chain(receiver_type, class_info_index=info_index):
                candidates = [
                    mi for mi in variants_by_class.get(parent, [])
                    if str(mi.get("method_name") or "") == method_name
                    and len(mi.get("params") or []) == arity
                ]
                if len(candidates) == 1:
                    add_call(
                        caller_mi=caller_mi,
                        callee_mi=candidates[0],
                        call=call,
                        resolution_kind="inherited_method_dispatch",
                        receiver_type=receiver_type,
                    )
                    break

    # Template-method calls such as Base.doHandle -> this.handleByDal(request).
    # Add an edge to each exact source override; tracing from a particular
    # override remains deterministic and does not guess which branch executed.
    subclass_names_by_parent: dict[str, set[str]] = defaultdict(set)
    for info in class_infos.values():
        if not isinstance(info, dict):
            continue
        child = _simple_type_name(info.get("class_name"))
        for parent in _superclass_chain(child, class_info_index=info_index):
            if child and parent:
                subclass_names_by_parent[parent].add(child)
    for caller_mi in methods.values():
        caller_class = _simple_type_name(caller_mi.get("class_name"))
        if not caller_class or not _production_method(caller_mi):
            continue
        for call in caller_mi.get("method_calls") or []:
            if _clean_expression(call.get("receiver")) not in {"", "this"}:
                continue
            method_name = str(call.get("method") or "")
            if not method_name:
                continue
            arity = len(call.get("args") or [])
            base_candidates = [
                mi for mi in variants_by_class.get(caller_class, [])
                if str(mi.get("method_name") or "") == method_name
                and len(mi.get("params") or []) == arity
            ]
            if not base_candidates:
                continue
            for child in sorted(subclass_names_by_parent.get(caller_class, set())):
                overrides = [
                    mi for mi in variants_by_class.get(child, [])
                    if str(mi.get("method_name") or "") == method_name
                    and len(mi.get("params") or []) == arity
                ]
                if len(overrides) != 1:
                    continue
                add_call(
                    caller_mi=caller_mi,
                    callee_mi=overrides[0],
                    call=call,
                    resolution_kind="virtual_override_dispatch",
                    receiver_type=child,
                )
    return out


def _method_for_call_side(call: dict[str, Any], *, caller: bool, index: dict[str, Any]) -> dict[str, Any] | None:
    signature_key = "caller_operation_signature" if caller else "callee_operation_signature"
    operation_key = "caller_operation_id" if caller else "callee_operation_id"
    signature = str(call.get(signature_key) or "")
    if signature and signature in index["variants_by_signature"]:
        return index["variants_by_signature"][signature]
    operation = str(call.get(operation_key) or "")
    candidates = index["variants_by_operation"].get(operation) or []
    return candidates[0] if candidates else index["methods"].get(operation)


def _builder_source_for_expression(
    expression: str,
    *,
    target_field: str,
    caller_mi: dict[str, Any],
    index: dict[str, Any],
) -> dict[str, str] | None:
    value = _clean_expression(expression)
    match = re.search(
        r"(?P<receiver>[A-Za-z_$][\w$]*(?:\s*\.\s*[A-Za-z_$][\w$]*)*)\s*\.\s*"
        r"(?P<method>[A-Za-z_$][\w$]*)\s*\((?P<args>.*)\)\s*$",
        value,
        re.S,
    )
    if not match:
        return None
    args = split_java_arguments(match.group("args"))
    if len(args) != 1:
        return None
    source_symbol = _clean_expression(args[0])
    source_type = _simple_type_name((caller_mi.get("raw_var_types") or {}).get(source_symbol))
    method_name = match.group("method")
    target_token = _normalized_field_token(target_field)
    candidates: list[tuple[int, dict[str, Any], dict[str, Any]]] = []
    for mapping in index["builder_mappings"]:
        if str(mapping.get("method_name") or "") != method_name:
            continue
        signature = str(mapping.get("operation_signature") or "")
        score = 10 if source_type and signature.endswith(f"({source_type})") else 0
        for field_mapping in mapping.get("field_mappings") or []:
            if _normalized_field_token(field_mapping.get("target_field")) != target_token:
                continue
            source_object = str(field_mapping.get("source_object") or "")
            source_field = str(field_mapping.get("source_field") or "")
            source_expression = str(field_mapping.get("source_expression") or "")
            getter = re.search(
                rf"\b{re.escape(source_symbol)}\s*\.\s*(?:get|is)([A-Z][A-Za-z0-9_$]*)\s*\(",
                source_expression,
            )
            if getter:
                source_field = getter.group(1)[:1].lower() + getter.group(1)[1:]
            if source_object and source_object != source_symbol and source_symbol not in source_expression:
                continue
            if source_field:
                candidates.append((score, mapping, {"source_symbol": source_symbol, "source_field": source_field}))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (-item[0], str(item[1].get("operation_signature") or "")))
    return candidates[0][2]


def _parameter_for_local_symbol(mi: dict[str, Any], symbol: str) -> str | None:
    params = {str(p.get("name") or "") for p in mi.get("params") or []}
    if symbol in params:
        return symbol
    body = str(mi.get("body") or "")
    assignment = re.search(
        rf"\b{re.escape(symbol)}\s*=\s*(?P<lambda>[A-Za-z_$][\w$]*)\s*\.\s*[A-Za-z_$][\w$]*",
        body,
    )
    if assignment:
        lambda_name = assignment.group("lambda")
        for_each = re.search(
            rf"\b(?P<collection>[A-Za-z_$][\w$]*)\s*\.\s*forEach\s*\(\s*{re.escape(lambda_name)}\s*->",
            body,
            re.S,
        )
        if for_each and for_each.group("collection") in params:
            return for_each.group("collection")
    origins = _variable_origins(body, mi.get("params") or [], method_info=mi)
    origin = origins.get(symbol) or {}
    candidate = str(origin.get("origin_payload_parameter") or origin.get("source_parameter") or "")
    return candidate if candidate in params else None


def _java_property_name(raw: str | None) -> str | None:
    value = str(raw or "")
    if not value:
        return None
    return value[:1].lower() + value[1:]


def _projection_field_path(expression: str | None) -> str | None:
    """Return the DTO field path represented by a lambda or method reference."""
    value = _clean_expression(expression)
    if not value:
        return None
    ref = re.search(r"::\s*(?:get|is)([A-Z][A-Za-z0-9_$]*)\b", value)
    if ref:
        return _java_property_name(ref.group(1))
    body = value.split("->", 1)[1].strip() if "->" in value else value
    getters = re.findall(r"\.\s*(?:get|is)([A-Z][A-Za-z0-9_$]*)\s*\(", body)
    fields = [field for field in (_java_property_name(item) for item in getters) if field]
    return ".".join(fields) if fields else None


def _assignment_for_symbol(mi: dict[str, Any], symbol: str) -> dict[str, Any] | None:
    candidates = [
        assignment
        for assignment in mi.get("syntax_assignments") or []
        if _clean_expression(assignment.get("target")) == symbol
    ]
    candidates.sort(key=lambda item: int(item.get("start_byte") or 0))
    return candidates[-1] if candidates else None


def _stream_to_map_projection(
    *,
    mi: dict[str, Any],
    map_symbol: str,
    target_field: str | None = None,
    index: dict[str, Any] | None = None,
) -> dict[str, str] | None:
    assignment = _assignment_for_symbol(mi, map_symbol)
    if not assignment:
        return None
    expression = _clean_expression(assignment.get("expression"))
    source_match = re.search(r"\b([A-Za-z_$][\w$]*)\s*\.\s*stream\s*\(", expression)
    if not source_match:
        return None
    to_map_calls = [
        call
        for call in mi.get("method_calls") or []
        if str(call.get("method") or "") == "toMap"
        and _span_inside(call, assignment)
        and len(call.get("args") or []) >= 2
    ]
    if not to_map_calls:
        return None
    to_map_calls.sort(key=lambda item: int(item.get("start_byte") or 0))
    value_mapper = _clean_expression(list(to_map_calls[-1].get("args") or [])[1])
    source_field = _projection_field_path(value_mapper)
    if source_field:
        return {
            "parameter_or_symbol": source_match.group(1),
            "source_field": source_field,
            "projection_kind": "stream_to_map_value",
        }

    # Custom value factory, e.g. ``this::createCardUpdate``.  Use only a
    # source-declared factory mapping for the exact requested target field and
    # prefer the caller class, so same-named factories in other classes cannot
    # leak into the trace.
    if index and target_field:
        method_ref = re.search(r"(?:(?P<qualifier>[A-Za-z_$][\w$]*)\s*)?::\s*(?P<method>[A-Za-z_$][\w$]*)", value_mapper)
        method_name = method_ref.group("method") if method_ref else None
        qualifier = method_ref.group("qualifier") if method_ref else None
        if method_name:
            target_token = _normalized_field_token(target_field)
            caller_class = _simple_type_name(mi.get("class_name"))
            candidates: list[tuple[int, dict[str, Any], dict[str, Any]]] = []
            for mapping in index.get("factory_mappings") or []:
                if str(mapping.get("method_name") or "") != method_name:
                    continue
                mapping_class = _simple_type_name(mapping.get("class_name"))
                score = 0
                if qualifier in {None, "this"} and caller_class and mapping_class == caller_class:
                    score += 20
                elif qualifier and _simple_type_name(qualifier) == mapping_class:
                    score += 20
                for field_mapping in mapping.get("field_mappings") or []:
                    if _normalized_field_token(field_mapping.get("target_field")) != target_token:
                        continue
                    source_field_path = str(field_mapping.get("source_field") or "")
                    source_parameter = str(field_mapping.get("source_payload_parameter") or field_mapping.get("source_object") or "")
                    if source_field_path and source_parameter:
                        candidates.append((score, mapping, {
                            "parameter_or_symbol": source_match.group(1),
                            "source_field": source_field_path,
                            "projection_kind": "stream_to_map_factory_method_reference",
                            "factory_parameter": source_parameter,
                        }))
            if candidates:
                candidates.sort(key=lambda item: (-item[0], str(item[1].get("operation") or "")))
                return candidates[0][2]
    return None


def _expression_parameter_field_origin(
    *,
    mi: dict[str, Any],
    expression: str,
    target_field: str,
    visited: set[str] | None = None,
    depth: int = 0,
) -> dict[str, str] | None:
    """Resolve a local value expression to one method parameter and its field.

    The resolver is deliberately limited to direct local assignments, Map.get
    lookups and stream ``Collectors.toMap`` value projections.  It does not infer
    joins or correlate arbitrary map keys; it only preserves the field identity
    that source syntax explicitly assigns to the value.
    """
    if depth > 8:
        return None
    value = _clean_expression(expression)
    if not value:
        return None
    visited = visited or set()
    if value in visited:
        return None
    visited.add(value)
    params = {str(p.get("name") or "") for p in mi.get("params") or []}
    if value in params:
        return {"parameter": value, "source_field": target_field}

    assignment = _assignment_for_symbol(mi, value) if _simple_java_identifier(value) else None
    if assignment:
        return _expression_parameter_field_origin(
            mi=mi,
            expression=str(assignment.get("expression") or ""),
            target_field=target_field,
            visited=visited,
            depth=depth + 1,
        )

    map_get = re.match(
        r"^(?P<map>[A-Za-z_$][\w$]*)\s*\.\s*get\s*\(",
        value,
        re.S,
    )
    if map_get:
        map_symbol = map_get.group("map")
        projection = _stream_to_map_projection(mi=mi, map_symbol=map_symbol, target_field=target_field)
        if projection:
            source_symbol = projection["parameter_or_symbol"]
            source_field = projection["source_field"]
            if source_symbol in params:
                return {"parameter": source_symbol, "source_field": source_field}
            return _expression_parameter_field_origin(
                mi=mi,
                expression=source_symbol,
                target_field=source_field,
                visited=visited,
                depth=depth + 1,
            )
        if map_symbol in params:
            return {"parameter": map_symbol, "source_field": target_field}

    projection = _stream_to_map_projection(mi=mi, map_symbol=value, target_field=target_field) if _simple_java_identifier(value) else None
    if projection:
        source_symbol = projection["parameter_or_symbol"]
        source_field = projection["source_field"]
        if source_symbol in params:
            return {"parameter": source_symbol, "source_field": source_field}
        return _expression_parameter_field_origin(
            mi=mi,
            expression=source_symbol,
            target_field=source_field,
            visited=visited,
            depth=depth + 1,
        )
    return None


def _local_collection_field_source(
    *,
    caller_mi: dict[str, Any],
    collection_symbol: str,
    target_field: str,
) -> dict[str, str] | None:
    """Resolve a collection element field populated before an outbound call."""
    target_token = _normalized_field_token(target_field)
    calls = list(caller_mi.get("method_calls") or [])
    lambdas = list(caller_mi.get("lambdas") or [])

    # Existing objects mutated in a collection: rows.forEach(r -> r.setX(expr)).
    for each_call in [
        call for call in calls
        if _clean_expression(call.get("receiver")) == collection_symbol
        and str(call.get("method") or "") == "forEach"
    ]:
        for lam in [item for item in lambdas if _span_inside(item, each_call)]:
            params = list(lam.get("params") or [])
            if len(params) != 1:
                continue
            element = str(params[0])
            for setter in [item for item in calls if _span_inside(item, lam)]:
                if _clean_expression(setter.get("receiver")) != element:
                    continue
                method_name = str(setter.get("method") or "")
                match = re.fullmatch(r"set([A-Z][A-Za-z0-9_$]*)", method_name)
                args = list(setter.get("args") or [])
                if not match or len(args) != 1:
                    continue
                setter_field = _java_property_name(match.group(1)) or ""
                if _normalized_field_token(setter_field) != target_token:
                    continue
                return _expression_parameter_field_origin(
                    mi=caller_mi,
                    expression=str(args[0]),
                    target_field=setter_field,
                )

    # New DTO accumulated in a collection after explicit setter calls.
    for add_call in [
        call for call in calls
        if _clean_expression(call.get("receiver")) == collection_symbol
        and str(call.get("method") or "") == "add"
        and len(call.get("args") or []) == 1
    ]:
        element = _clean_expression(list(add_call.get("args") or [""])[0])
        if not _simple_java_identifier(element):
            continue
        for setter in calls:
            if _clean_expression(setter.get("receiver")) != element:
                continue
            if int(setter.get("start_byte") or 0) > int(add_call.get("start_byte") or 0):
                continue
            method_name = str(setter.get("method") or "")
            match = re.fullmatch(r"set([A-Z][A-Za-z0-9_$]*)", method_name)
            args = list(setter.get("args") or [])
            if not match or len(args) != 1:
                continue
            setter_field = _java_property_name(match.group(1)) or ""
            if _normalized_field_token(setter_field) != target_token:
                continue
            return _expression_parameter_field_origin(
                mi=caller_mi,
                expression=str(args[0]),
                target_field=setter_field,
            )
    return None


def _container_mutation_source(
    *,
    caller_mi: dict[str, Any],
    container_symbol: str,
    accessor: str,
    target_field: str,
    index: dict[str, Any],
) -> dict[str, str] | None:
    container_type = _simple_type_name((caller_mi.get("raw_var_types") or {}).get(container_symbol))
    if not container_type:
        return None
    variants = list(index["variants_by_class"].get(container_type, []))
    # The accessor may expose a differently named backing collection, e.g.
    # `forUpdateActual() { return records; }`.  Resolve only a direct zero-arg
    # return; computed accessors stay unresolved rather than widening the trace.
    collection_symbols: set[str] = {accessor}
    for variant in variants:
        if str(variant.get("method_name") or "") != accessor or variant.get("params"):
            continue
        accessor_body = str(variant.get("body") or "")
        returned = re.search(r"\breturn\s+(?P<symbol>[A-Za-z_$][\w$]*)\s*;", accessor_body)
        if returned:
            collection_symbols.add(returned.group("symbol"))

    mutator_names: set[str] = set()
    for variant in variants:
        params = [str(p.get("name") or "") for p in variant.get("params") or []]
        if not params:
            continue
        body = str(variant.get("body") or "")
        if any(
            re.search(rf"\b{re.escape(symbol)}\s*\.\s*add\s*\(\s*{re.escape(params[0])}\s*\)", body)
            for symbol in collection_symbols
        ):
            mutator_names.add(str(variant.get("method_name") or ""))
    if not mutator_names:
        return None
    for call in caller_mi.get("method_calls") or []:
        if _clean_expression(call.get("receiver")) != container_symbol:
            continue
        if str(call.get("method") or "") not in mutator_names:
            continue
        args = list(call.get("args") or [])
        if not args:
            continue
        builder_source = _builder_source_for_expression(
            str(args[0]), target_field=target_field, caller_mi=caller_mi, index=index
        )
        if not builder_source:
            continue
        parameter = _parameter_for_local_symbol(caller_mi, builder_source["source_symbol"])
        if parameter:
            return {"parameter": parameter, "source_field": builder_source["source_field"]}
    return None


def _payload_source_field_is_observed(
    *,
    payload_type: str | None,
    source_field: str | None,
    schema_fields: dict[str, list[dict[str, Any]]] | None,
) -> bool | None:
    """Validate only the root field of an ingress payload when its schema is observed.

    ``None`` means that Core has no structural schema for the payload and therefore
    cannot validate the field.  ``False`` is returned only when a payload schema is
    available and the proposed root field is absent.  This keeps best-effort
    lineage for opaque/external DTOs while preventing downstream wrapper fields
    from being silently relabelled as fields of a known ingress DTO.
    """
    fields = _fields_for_type(schema_fields or {}, payload_type)
    if not fields:
        return None
    raw = str(source_field or "").strip()
    if not raw:
        return False
    root = raw.split("[*].", 1)[0].split(".", 1)[0]
    token = _normalized_field_token(root)
    observed = {_normalized_field_token(item.get("name")) for item in fields if item.get("name")}
    return bool(token and token in observed)


def _trace_parameter_to_ingress(
    *,
    operation: str,
    parameter: str,
    source_field: str,
    accessor: str | None,
    index: dict[str, Any],
    visited: set[tuple[str, str, str, str]],
    depth: int,
    dispatch_receiver_type: str | None = None,
) -> dict[str, Any] | None:
    if depth > 8:
        return None
    key = (operation, parameter, source_field, dispatch_receiver_type or "")
    if key in visited:
        return None
    visited.add(key)
    for origin in index["origins_by_operation"].get(operation, []):
        if str(origin.get("payload_parameter") or "") == parameter:
            payload_type = _simple_type_name(origin.get("payload_type"))
            field_observed = _payload_source_field_is_observed(
                payload_type=payload_type,
                source_field=source_field,
                schema_fields=index.get("schema_fields"),
            )
            if field_observed is False:
                # The downstream field exists, but it is not a field of the known
                # ingress DTO.  Do not manufacture an external-source mapping.
                continue
            return {
                "source_kind": _technical_source_kind(_source_boundary_for_origin(origin)),
                "source_operation": origin.get("operation"),
                "source_payload": payload_type,
                "source_container": parameter,
                "source_container_type": None,
                "source_element_type": _simple_type_name(origin.get("payload_type")),
                "source_payload_parameter": parameter,
                "source_field": source_field,
                "origin_expression": f"{parameter}.{source_field}",
                "missing_links": [
                    "cross_dao_call_argument_mapping_candidate",
                    "interprocedural_container_provenance_candidate",
                ],
            }

    reverse = list(index["reverse_calls"].get(operation, []))
    reverse.sort(key=lambda call: (
        0 if _production_method(_method_for_call_side(call, caller=True, index=index)) else 1,
        -float(call.get("match_strength") or 0.0),
        str(call.get("caller_operation_signature") or ""),
    ))
    for call in reverse:
        resolution_kind = str(call.get("resolution_kind") or "")
        call_receiver_type = _simple_type_name(call.get("receiver_type"))
        # A template method may have several concrete overrides.  Once backward
        # tracing entered one override, retain that concrete receiver while
        # walking through base-class methods and reject inherited entry calls
        # belonging to sibling handlers.  This prevents a shared base handler
        # from leaking provenance from an unrelated controller/consumer.
        if (
            resolution_kind == "inherited_method_dispatch"
            and dispatch_receiver_type
            and call_receiver_type != _simple_type_name(dispatch_receiver_type)
        ):
            continue
        next_dispatch_receiver_type = dispatch_receiver_type
        if resolution_kind == "virtual_override_dispatch":
            next_dispatch_receiver_type = call_receiver_type or dispatch_receiver_type
        elif resolution_kind == "inherited_method_dispatch":
            # Crossing the concrete inherited call returns to the concrete
            # caller; the dispatch constraint has served its purpose.
            next_dispatch_receiver_type = None

        caller_mi = _method_for_call_side(call, caller=True, index=index)
        if not _production_method(caller_mi):
            continue
        for binding in call.get("argument_bindings") or []:
            if str(binding.get("callee_parameter") or "") != parameter:
                continue
            actual = _clean_expression(binding.get("caller_expression"))
            if re.fullmatch(r"[A-Za-z_$][\w$]*", actual):
                local_source = _local_collection_field_source(
                    caller_mi=caller_mi,
                    collection_symbol=actual,
                    target_field=source_field,
                )
                if local_source:
                    resolved = _trace_parameter_to_ingress(
                        operation=str(call.get("caller_operation_id") or ""),
                        parameter=local_source["parameter"],
                        source_field=local_source["source_field"],
                        accessor=None,
                        index=index,
                        visited=visited,
                        depth=depth + 1,
                        dispatch_receiver_type=next_dispatch_receiver_type,
                    )
                    if resolved:
                        return resolved

                projection = _stream_to_map_projection(mi=caller_mi, map_symbol=actual, target_field=source_field, index=index)
                if projection:
                    source_symbol = projection["parameter_or_symbol"]
                    params = {str(p.get("name") or "") for p in caller_mi.get("params") or []}
                    if source_symbol in params:
                        resolved = _trace_parameter_to_ingress(
                            operation=str(call.get("caller_operation_id") or ""),
                            parameter=source_symbol,
                            source_field=projection["source_field"],
                            accessor=None,
                            index=index,
                            visited=visited,
                            depth=depth + 1,
                            dispatch_receiver_type=next_dispatch_receiver_type,
                        )
                        if resolved:
                            return resolved
            upstream_parameter = str(binding.get("caller_source_parameter") or "")
            if upstream_parameter:
                resolved = _trace_parameter_to_ingress(
                    operation=str(call.get("caller_operation_id") or ""),
                    parameter=upstream_parameter,
                    source_field=source_field,
                    accessor=accessor,
                    index=index,
                    visited=visited,
                    depth=depth + 1,
                    dispatch_receiver_type=next_dispatch_receiver_type,
                )
                if resolved:
                    return resolved
            if accessor and re.fullmatch(r"[A-Za-z_$][\w$]*", actual):
                mutation = _container_mutation_source(
                    caller_mi=caller_mi,
                    container_symbol=actual,
                    accessor=accessor,
                    target_field=source_field,
                    index=index,
                )
                if mutation:
                    resolved = _trace_parameter_to_ingress(
                        operation=str(call.get("caller_operation_id") or ""),
                        parameter=mutation["parameter"],
                        source_field=mutation["source_field"],
                        accessor=None,
                        index=index,
                        visited=visited,
                        depth=depth + 1,
                        dispatch_receiver_type=next_dispatch_receiver_type,
                    )
                    if resolved:
                        return resolved
    return None


def _interprocedural_container_parameter_origin(
    *,
    operation: str,
    parameter: str,
    accessor: str,
    target_field: str,
    index: dict[str, Any],
) -> dict[str, Any] | None:
    return _trace_parameter_to_ingress(
        operation=operation,
        parameter=parameter,
        source_field=target_field,
        accessor=accessor,
        index=index,
        visited=set(),
        depth=0,
    )


def _dao_method_candidates(
    *,
    receiver_type: str | None,
    storage_method: str,
    methods_by_class_method: dict[tuple[str, str], list[dict[str, Any]]],
    raw_methods_by_class_method: dict[tuple[str, str], list[dict[str, Any]]] | None = None,
) -> list[dict[str, Any]]:
    """Return source-declared DAO implementation candidates without collapsing overloads.

    The canonical method index intentionally keeps one representative under the
    legacy ``Class.method`` key.  Persistence resolution must instead preserve
    all source declarations because overloaded/custom DAO methods are common.
    """
    if not receiver_type or not storage_method:
        return []
    key = (_simple_type_name(receiver_type), storage_method)
    candidates = list(methods_by_class_method.get(key, []))
    if raw_methods_by_class_method:
        seen = {
            (
                str(item.get("file") or ""),
                int(item.get("line_start") or 0),
                str(item.get("class_fqcn") or item.get("class_name") or ""),
            )
            for item in candidates
        }
        for candidate in raw_methods_by_class_method.get(key, []):
            candidate_key = (
                str(candidate.get("file") or ""),
                int(candidate.get("line_start") or 0),
                str(candidate.get("class_fqcn") or candidate.get("class_name") or ""),
            )
            if candidate_key not in seen:
                candidates.append(candidate)
                seen.add(candidate_key)
    return candidates


def _dao_jooq_mappings_for_candidate(
    dao_mi: dict[str, Any],
    *,
    methods: dict[str, dict[str, Any]],
    dao_jooq_mapping_cache: dict[str, list[dict[str, Any]]] | None = None,
) -> list[dict[str, Any]]:
    dao_op = str(dao_mi.get("operation") or f"{dao_mi.get('class_name')}.{dao_mi.get('method_name')}")
    cache_key = "|".join([
        dao_op,
        str(dao_mi.get("file") or ""),
        str(dao_mi.get("line_start") or ""),
        str(dao_mi.get("class_fqcn") or dao_mi.get("class_name") or ""),
    ])
    if dao_jooq_mapping_cache is not None and cache_key in dao_jooq_mapping_cache:
        return dao_jooq_mapping_cache[cache_key]
    mappings = _dao_jooq_field_mappings(dao_mi, methods)
    if dao_jooq_mapping_cache is not None:
        dao_jooq_mapping_cache[cache_key] = mappings
    return mappings


def _custom_dao_mutation_has_concrete_jooq_write(
    *,
    access: dict[str, Any],
    caller_mi: dict[str, Any],
    receiver_type: str | None,
    methods_by_class_method: dict[tuple[str, str], list[dict[str, Any]]],
    raw_methods_by_class_method: dict[tuple[str, str], list[dict[str, Any]]] | None,
    methods: dict[str, dict[str, Any]],
    dao_jooq_mapping_cache: dict[str, list[dict[str, Any]]] | None,
) -> bool:
    """Promote only a source-proven custom DAO mutation with real JOOQ writes.

    A method name containing ``update`` is not evidence by itself.  Promotion is
    allowed only when the resolved source implementation exposes at least one
    concrete DAO-parameter -> physical table/column mapping and the caller
    supplies the corresponding argument.  Deletes and arbitrary status/key
    mutations therefore remain non-write evidence.
    """
    if _storage_resolution_level_for_access(access) != "custom_dao_boundary":
        return False
    if str(access.get("access_kind") or "") != "mutation":
        return False
    operation_kind = str(access.get("operation_kind") or "").lower()
    storage_method = str(access.get("storage_method") or "")
    if operation_kind == "delete" or storage_method.lower().startswith(("delete", "remove")):
        return False
    actual_args = _storage_call_args_for_access(access, caller_mi)
    if not actual_args:
        return False
    candidates = _dao_method_candidates(
        receiver_type=receiver_type,
        storage_method=storage_method,
        methods_by_class_method=methods_by_class_method,
        raw_methods_by_class_method=raw_methods_by_class_method,
    )
    for dao_mi in candidates[:3]:
        params = [str(p.get("name")) for p in dao_mi.get("params") or [] if p.get("name")]
        if not params:
            continue
        mappings = _dao_jooq_mappings_for_candidate(
            dao_mi,
            methods=methods,
            dao_jooq_mapping_cache=dao_jooq_mapping_cache,
        )
        for mapping in mappings:
            source_object = str(mapping.get("source_object") or "")
            formal_source_object = source_object
            if formal_source_object not in params:
                _iter_var, _iter_collection = _enhanced_for_iteration_for_bind_call(
                    str(dao_mi.get("body") or ""), str(mapping.get("batch_variable") or "")
                )
                formal_source_object = (
                    _iter_collection if source_object == _iter_var and _iter_collection else None
                ) or _lambda_collection_for_var(str(dao_mi.get("body") or ""), source_object) or source_object
            if formal_source_object in params and params.index(formal_source_object) < len(actual_args):
                if mapping.get("storage_table") and mapping.get("storage_field"):
                    return True
    return False


def _cross_dao_jooq_lineage_facts(
    *,
    access: dict[str, Any],
    caller_mi: dict[str, Any],
    receiver_type: str | None,
    methods_by_class_method: dict[tuple[str, str], list[dict[str, Any]]],
    methods: dict[str, dict[str, Any]],
    raw_methods_by_class_method: dict[tuple[str, str], list[dict[str, Any]]] | None = None,
    persistent_write_id: str,
    lineage_id_start: int,
    evidence: list[EvidenceRef],
    variable_origins: dict[str, dict[str, Any]],
    ingress_by_param: dict[str, dict[str, Any]],
    dao_jooq_mapping_cache: dict[str, list[dict[str, Any]]] | None = None,
    interprocedural_index: dict[str, Any] | None = None,
) -> tuple[list[Fact], int]:
    if not receiver_type:
        return [], lineage_id_start
    storage_method = str(access.get("storage_method") or "")
    dao_candidates = _dao_method_candidates(
        receiver_type=receiver_type,
        storage_method=storage_method,
        methods_by_class_method=methods_by_class_method,
        raw_methods_by_class_method=raw_methods_by_class_method,
    )
    if not dao_candidates:
        return [], lineage_id_start
    actual_args = _storage_call_args_for_access(access, caller_mi)
    if not actual_args:
        return [], lineage_id_start
    facts: list[Fact] = []
    seq = lineage_id_start
    for dao_mi in dao_candidates[:3]:
        dao_params = [str(p.get("name")) for p in dao_mi.get("params") or [] if p.get("name")]
        if not dao_params:
            continue
        mappings = _dao_jooq_mappings_for_candidate(
            dao_mi,
            methods=methods,
            dao_jooq_mapping_cache=dao_jooq_mapping_cache,
        )
        if not mappings:
            continue
        for mapping in mappings[:64]:
            source_object = str(mapping.get("source_object") or "")
            formal_source_object = source_object
            if formal_source_object not in dao_params:
                formal_source_object = _lambda_collection_for_var(str(dao_mi.get("body") or ""), source_object) or source_object
            try:
                formal_index = dao_params.index(formal_source_object)
            except ValueError:
                continue
            if formal_index >= len(actual_args):
                continue
            actual_expr = actual_args[formal_index]
            origin = _actual_origin_for_cross_dao(
                actual_expr,
                dao_source_object=source_object,
                dao_source_field=mapping.get("source_field"),
                caller_mi=caller_mi,
                variable_origins=variable_origins,
                ingress_by_param=ingress_by_param,
                interprocedural_index=interprocedural_index,
            )
            storage_field = _jooq_field_constant_to_column(str(mapping.get("storage_field") or "")) or mapping.get("storage_field")
            if not storage_field or not origin.get("source_field"):
                continue
            seq += 1
            refs = [str(access.get("storage_access_id") or ""), persistent_write_id]
            helper = mapping.get("helper_method")
            path = [str(origin.get("origin_expression") or actual_expr), f"{dao_mi.get('operation')}.{mapping.get('source_expression')}"]
            if helper:
                path.append(str(helper))
            path.append(f"{mapping.get('storage_table') or access.get('table_or_repository')}.{storage_field}")
            facts.append(_source_to_storage_lineage_fact(
                f"source_to_storage_lineage_{seq:06d}",
                source_kind=str(origin.get("source_kind") or "method_input"),
                source_operation=origin.get("source_operation"),
                source_payload=origin.get("source_payload"),
                source_field=str(origin.get("source_field") or ""),
                source_field_role=_field_role(str(origin.get("source_field") or "")),
                storage_operation=str(caller_mi.get("operation") or access.get("operation") or ""),
                storage_call=f"{access.get('receiver_expression')}.{access.get('storage_method')}({', '.join(actual_args)})",
                storage_method=str(access.get("storage_method") or "") or None,
                storage_access_id=str(access.get("storage_access_id") or "") or None,
                persistent_write_id=persistent_write_id,
                storage_target=mapping.get("storage_table") or access.get("table_or_repository"),
                storage_resolution_level="resolved_dao_implementation",
                saved_object=mapping.get("storage_table") or access.get("table_or_repository"),
                saved_object_field=str(storage_field),
                storage_field=str(storage_field),
                assignment_kind=str(mapping.get("mapping_kind") or "cross_dao_jooq_mapping"),
                assignment_expression=str(mapping.get("source_expression") or actual_expr),
                origin_expression=origin.get("origin_expression") or actual_expr,
                path=path,
                missing_links=list(origin.get("missing_links") or ["cross_dao_call_argument_mapping_candidate"]),
                evidence_refs=[x for x in refs if x],
                evidence=evidence + _op_file_evidence(dao_mi, "java_cross_dao_jooq_mapping"),
                source_container=origin.get("source_container"),
                source_container_type=origin.get("source_container_type"),
                source_element_type=origin.get("source_element_type"),
                source_payload_parameter=origin.get("source_payload_parameter"),
            ))
    return facts, seq



def _compose_observed_factory_to_physical_lineage_facts(
    ctx: "_JavaPersistenceLineageContext",
    write_facts: list[Fact],
) -> list[Fact]:
    """Compose already-observed object, factory-field and DAO-physical facts.

    This is intentionally a narrow evidence composition, not a general Java
    execution model.  A field-level path is emitted only when all of the
    following are observed:

    * an existing source-to-storage fact reaches a concrete saved object;
    * a source-declared factory maps a field of that source payload into the
      same saved-object field; and
    * the called DAO method maps that saved-object field to a physical column.

    The source is promoted to an ingress boundary only through the existing
    interprocedural provenance resolver.  Missing factory mappings stay partial
    instead of being inferred from names or target schemas.
    """
    object_facts = [
        fact
        for fact in write_facts
        if fact.fact_type == "source_to_storage_lineage"
        and not (fact.properties or {}).get("source_field")
        and (fact.properties or {}).get("saved_object")
        and (fact.properties or {}).get("storage_access_id")
    ]
    if not object_facts or not ctx.factory_method_mapping_facts:
        return []

    access_by_id = {
        str(item.get("storage_access_id") or ""): item
        for item in ctx.storage_accesses
        if item.get("storage_access_id")
    }
    factories_by_target: dict[str, list[Fact]] = defaultdict(list)
    for fact in ctx.factory_method_mapping_facts:
        props = fact.properties or {}
        if props.get("source_scope") != "production_code":
            continue
        target = _simple_type_name(props.get("target_container"))
        if target:
            factories_by_target[target].append(fact)

    # Continue the canonical numeric id sequence so downstream consumers do not
    # need a second id grammar for composed facts.
    max_seq = 0
    for fact in write_facts:
        if fact.fact_type != "source_to_storage_lineage":
            continue
        match = re.fullmatch(r"source_to_storage_lineage_(\d+)", str((fact.properties or {}).get("source_to_storage_lineage_id") or ""))
        if match:
            max_seq = max(max_seq, int(match.group(1)))
    seq = max_seq

    existing: set[tuple[str, str, str, str]] = set()
    for fact in write_facts:
        if fact.fact_type != "source_to_storage_lineage":
            continue
        props = fact.properties or {}
        key = (
            _simple_type_name(props.get("source_payload")),
            _normalized_field_token(props.get("source_field")),
            str(props.get("storage_target") or "").upper(),
            _normalized_field_token(props.get("storage_field")),
        )
        if key[0] and key[1] and key[2] and key[3]:
            existing.add(key)

    out: list[Fact] = []
    seen: set[tuple[str, str, str, str]] = set()
    for object_fact in object_facts:
        props = object_fact.properties or {}
        saved_object = _simple_type_name(props.get("saved_object"))
        source_payload = _simple_type_name(props.get("source_payload"))
        source_operation = str(props.get("source_operation") or "")
        source_parameter = str(props.get("source_payload_parameter") or "")
        storage_operation = str(props.get("storage_operation") or "")
        access = access_by_id.get(str(props.get("storage_access_id") or ""))
        caller_mi = ctx.methods.get(storage_operation)
        if not saved_object or not source_payload or not access or not caller_mi:
            continue
        if not source_operation or not source_parameter:
            continue

        receiver_type = _declared_receiver_type(access.get("receiver_expression"), caller_mi, ctx.class_fields)
        storage_method = str(access.get("storage_method") or "")
        dao_candidates = _dao_method_candidates(
            receiver_type=receiver_type,
            storage_method=storage_method,
            methods_by_class_method=ctx.methods_by_class_method,
            raw_methods_by_class_method=ctx.raw_methods_by_class_method,
        )
        if not dao_candidates:
            continue

        physical_by_field: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = defaultdict(list)
        for dao_mi in dao_candidates[:3]:
            for mapping in _dao_jooq_field_mappings(dao_mi, ctx.methods)[:128]:
                source_field = str(mapping.get("source_field") or "")
                storage_field = _jooq_field_constant_to_column(str(mapping.get("storage_field") or "")) or str(mapping.get("storage_field") or "")
                storage_table = str(mapping.get("storage_table") or access.get("table_or_repository") or "")
                if not source_field or not storage_field or not storage_table:
                    continue
                physical_by_field[_normalized_field_token(source_field)].append((mapping, dao_mi))
        if not physical_by_field:
            continue

        for factory_fact in factories_by_target.get(saved_object, []):
            factory_props = factory_fact.properties or {}
            factory_operation = str(factory_props.get("operation") or "")
            factory_mi = ctx.methods.get(factory_operation)
            if not factory_mi:
                continue
            params_by_name = {
                str(param.get("name") or ""): param
                for param in factory_mi.get("params") or []
                if param.get("name")
            }
            for field_mapping in factory_props.get("field_mappings") or []:
                source_field = str(field_mapping.get("source_field") or "")
                target_field = str(field_mapping.get("target_field") or "")
                factory_parameter = str(field_mapping.get("source_payload_parameter") or "")
                if not source_field or not target_field or not factory_parameter:
                    continue
                param = params_by_name.get(factory_parameter)
                if not param:
                    continue
                param_type = _simple_type_name(param.get("type"))
                if param_type != source_payload:
                    continue
                observed = _payload_source_field_is_observed(
                    payload_type=source_payload,
                    source_field=source_field,
                    schema_fields=ctx.schema_fields,
                )
                if observed is False:
                    continue

                origin = _trace_parameter_to_ingress(
                    operation=source_operation,
                    parameter=source_parameter,
                    source_field=source_field,
                    accessor=None,
                    index=ctx.interprocedural_provenance_index,
                    visited=set(),
                    depth=0,
                )
                if not origin:
                    continue

                for physical_mapping, dao_mi in physical_by_field.get(_normalized_field_token(target_field), []):
                    storage_field = _jooq_field_constant_to_column(str(physical_mapping.get("storage_field") or "")) or str(physical_mapping.get("storage_field") or "")
                    storage_table = str(physical_mapping.get("storage_table") or access.get("table_or_repository") or "")
                    key = (
                        _simple_type_name(origin.get("source_payload") or source_payload),
                        _normalized_field_token(origin.get("source_field") or source_field),
                        storage_table.upper(),
                        _normalized_field_token(storage_field),
                    )
                    if key in existing or key in seen:
                        continue
                    seen.add(key)
                    seq += 1
                    evidence = list(object_fact.evidence or []) + list(factory_fact.evidence or []) + _op_file_evidence(dao_mi, "java_factory_dao_physical_composition")
                    helper = str(physical_mapping.get("helper_method") or "")
                    path = [
                        f"{origin.get('source_payload') or source_payload}.{origin.get('source_field') or source_field}",
                        f"{factory_operation}.{source_field}->{saved_object}.{target_field}",
                        f"{dao_mi.get('operation')}.{physical_mapping.get('source_expression') or target_field}",
                    ]
                    if helper:
                        path.append(helper)
                    path.append(f"{storage_table}.{storage_field}")
                    out.append(_source_to_storage_lineage_fact(
                        f"source_to_storage_lineage_{seq:06d}",
                        source_kind=str(origin.get("source_kind") or "method_input"),
                        source_operation=origin.get("source_operation") or source_operation,
                        source_payload=origin.get("source_payload") or source_payload,
                        source_field=str(origin.get("source_field") or source_field),
                        source_field_role=_field_role(str(origin.get("source_field") or source_field)),
                        storage_operation=storage_operation,
                        storage_target=storage_table,
                        saved_object=storage_table,
                        saved_object_field=storage_field,
                        storage_field=storage_field,
                        assignment_kind="factory_to_dao_physical_composition",
                        assignment_expression=str(field_mapping.get("source_expression") or source_field),
                        origin_expression=origin.get("origin_expression"),
                        path=path,
                        # The upstream resolver's candidate notes describe how the
                        # exact source call was traversed.  They are not missing
                        # field/storage links once all three observed facts above
                        # agree, so maturity is determined by the concrete facts.
                        missing_links=[],
                        evidence_refs=[
                            str(props.get("storage_access_id") or ""),
                            str(props.get("persistent_write_id") or ""),
                            str(factory_props.get("factory_method_mapping_id") or ""),
                        ],
                        evidence=evidence,
                        persistent_write_id=str(props.get("persistent_write_id") or "") or None,
                        storage_access_id=str(props.get("storage_access_id") or "") or None,
                        storage_call=props.get("storage_call"),
                        storage_method=storage_method or None,
                        source_container=origin.get("source_container"),
                        source_container_type=origin.get("source_container_type"),
                        source_element_type=origin.get("source_element_type"),
                        source_payload_parameter=origin.get("source_payload_parameter") or source_parameter,
                        storage_resolution_level="resolved_dao_implementation",
                    ))
    return out

def _mapper_result_candidate_field_mappings(
    mapper_sig: dict[str, Any],
    *,
    source_container: str | None,
    target_container: str | None,
    schema_fields: dict[str, list[dict[str, Any]]],
    written_field_names: list[str],
) -> list[dict[str, Any]]:
    """Build candidate field mappings for a mapper result saved by a DAO call.

    Explicit MapStruct @Mapping annotations are used when available.  Otherwise
    this emits only same-normalized-name candidates between source and saved
    object schemas.  The result is intentionally candidate-only: a mapper
    signature or same-name schema match is not a confirmed implementation body.
    """
    source_container = _simple_type_name(source_container)
    target_container = _simple_type_name(target_container)
    target_fields = [f for f in written_field_names if f]
    if not target_fields and target_container:
        target_fields = [str(f.get("name")) for f in _fields_for_type(schema_fields, target_container) if f.get("name")]
    if not target_fields:
        return []

    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    explicit = [m for m in (mapper_sig.get("field_mappings") or []) if isinstance(m, dict)]
    for item in explicit:
        src = str(item.get("source_field") or item.get("source_path") or "").split(".")[-1]
        tgt = str(item.get("target_field") or item.get("target_path") or "").split(".")[-1]
        tgt = _canonical_field_name(tgt, target_fields)
        if not src or not tgt:
            continue
        key = (normalize_name(src), normalize_name(tgt))
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "source_field": src,
            "target_field": tgt,
            "mapping_kind": str(item.get("mapping_kind") or "mapstruct_annotation_field_mapping"),
            "mapping_status": "candidate_mapper_annotation_field_mapping",
            "mapping_basis": "mapstruct_annotation",
            "expression": item.get("expression"),
        })

    if out:
        return out[:64]

    source_fields = [str(f.get("name")) for f in _fields_for_type(schema_fields, source_container) if f.get("name")] if source_container else []
    by_norm: dict[str, str] = {}
    for sf in source_fields:
        by_norm.setdefault(normalize_name(sf), sf)
    for target_field in target_fields:
        sf = by_norm.get(normalize_name(target_field))
        if not sf:
            continue
        key = (normalize_name(sf), normalize_name(target_field))
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "source_field": sf,
            "target_field": target_field,
            "mapping_kind": "mapper_signature_same_name_field_candidate",
            "mapping_status": "candidate_same_name_schema_mapping",
            "mapping_basis": "same_normalized_field_name_between_mapper_source_and_target",
        })
    return out[:64]


def _sql_update_slots(sql: str) -> dict[str, Any] | None:
    """Best-effort positional slots for parameterized UPDATE SQL.

    Only SET columns are exposed as saved-field candidates. WHERE columns are
    kept separately so key/filter values are not presented as persisted fields.
    """
    text = _clean_expression(sql).strip().strip('"\'')
    m = re.search(r"\bupdate\s+(?P<table>[A-Za-z_][A-Za-z0-9_.$]*)\s+set\s+(?P<set>.*?)(?:\s+where\s+(?P<where>.*))?$", text, re.IGNORECASE | re.DOTALL)
    if not m:
        return None
    slots: list[dict[str, Any]] = []
    set_part = m.group("set") or ""
    where_part = m.group("where") or ""
    for sm in re.finditer(r"(?P<field>[A-Za-z_][A-Za-z0-9_.$]*)\s*=\s*\?", set_part):
        field = sm.group("field").split(".")[-1]
        slots.append({"field": field, "field_ref": sm.group("field"), "role": "write_target_field"})
    for wm in re.finditer(r"(?P<field>[A-Za-z_][A-Za-z0-9_.$]*)\s*(?:=|<>|!=|>|<|>=|<=|like)\s*\?", where_part, re.IGNORECASE):
        field = wm.group("field").split(".")[-1]
        slots.append({"field": field, "field_ref": wm.group("field"), "role": "where_key_field"})
    if not slots:
        return None
    return {"table": m.group("table"), "table_ref": m.group("table"), "slots": slots, "statement_expression": text}


def _strip_java_string_literal(value: str | None) -> str | None:
    text = _clean_expression(value).strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        return text[1:-1]
    return None


def _split_sql_csv(text: str) -> list[str]:
    # Lightweight comma splitter for SQL column/value lists. It is intentionally
    # conservative and only tracks nesting and string literals; complex SQL stays
    # unresolved instead of producing aggressive mappings.
    items: list[str] = []
    buf: list[str] = []
    depth = 0
    quote: str | None = None
    i = 0
    while i < len(text):
        ch = text[i]
        if quote:
            buf.append(ch)
            if ch == quote and (i == 0 or text[i - 1] != "\\"):
                quote = None
            i += 1
            continue
        if ch in {'"', "'"}:
            quote = ch
            buf.append(ch)
        elif ch == "(":
            depth += 1
            buf.append(ch)
        elif ch == ")":
            depth = max(0, depth - 1)
            buf.append(ch)
        elif ch == "," and depth == 0:
            items.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
        i += 1
    tail = "".join(buf).strip()
    if tail:
        items.append(tail)
    return items


def _sql_named_parameter_slots(sql: str) -> dict[str, Any] | None:
    """Best-effort named-parameter SQL slots for UPDATE/INSERT.

    Supported examples:
      * update T set A=:a, B=:b where ID=:id
      * insert into T (A, B) values (:a, :b)

    SET/INSERT values are write targets. WHERE values remain key/filter slots.
    """
    text = _clean_expression(sql).strip().strip('"\'')
    slots: list[dict[str, Any]] = []

    upd = re.search(r"\bupdate\s+(?P<table>[A-Za-z_][A-Za-z0-9_.$]*)\s+set\s+(?P<set>.*?)(?:\s+where\s+(?P<where>.*))?$", text, re.IGNORECASE | re.DOTALL)
    if upd:
        set_part = upd.group("set") or ""
        where_part = upd.group("where") or ""
        for sm in re.finditer(r"(?P<field>[A-Za-z_][A-Za-z0-9_.$]*)\s*=\s*:(?P<param>[A-Za-z_][A-Za-z0-9_]*)", set_part):
            field_ref = sm.group("field")
            slots.append({"field": field_ref.split(".")[-1], "field_ref": field_ref, "param": sm.group("param"), "role": "write_target_field"})
        for wm in re.finditer(r"(?P<field>[A-Za-z_][A-Za-z0-9_.$]*)\s*(?:=|<>|!=|>|<|>=|<=|like)\s*:(?P<param>[A-Za-z_][A-Za-z0-9_]*)", where_part, re.IGNORECASE):
            field_ref = wm.group("field")
            slots.append({"field": field_ref.split(".")[-1], "field_ref": field_ref, "param": wm.group("param"), "role": "where_key_field"})
        if slots:
            return {"table": upd.group("table"), "table_ref": upd.group("table"), "slots": slots, "statement_expression": text, "sql_kind": "update"}
        return None

    ins = re.search(r"\binsert\s+into\s+(?P<table>[A-Za-z_][A-Za-z0-9_.$]*)\s*\((?P<cols>.*?)\)\s*values\s*\((?P<vals>.*?)\)", text, re.IGNORECASE | re.DOTALL)
    if ins:
        cols = [_clean_expression(x).split(".")[-1] for x in _split_sql_csv(ins.group("cols") or "")]
        vals = [_clean_expression(x) for x in _split_sql_csv(ins.group("vals") or "")]
        for idx, col in enumerate(cols):
            if not col or idx >= len(vals):
                continue
            vm = re.match(r":(?P<param>[A-Za-z_][A-Za-z0-9_]*)$", vals[idx])
            if not vm:
                continue
            slots.append({"field": col, "field_ref": col, "param": vm.group("param"), "role": "write_target_field"})
        if slots:
            return {"table": ins.group("table"), "table_ref": ins.group("table"), "slots": slots, "statement_expression": text, "sql_kind": "insert"}
    return None


def _local_var_name(target: str | None) -> str | None:
    value = _clean_expression(target)
    if not value:
        return None
    value = value.split("=")[0].strip()
    if "." in value and " " not in value:
        return value.split(".")[-1]
    value = re.sub(r"<[^<>]*>", "", value).strip()
    tokens = [t for t in re.split(r"\s+", value) if t and t not in {"final", "var"}]
    if not tokens:
        return None
    return tokens[-1].strip()


def _call_argument_texts(text: str, method_names: set[str]) -> list[str]:
    calls: list[str] = []
    for m in re.finditer(r"(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*\(", text):
        if m.group("name") not in method_names:
            continue
        open_idx = m.end() - 1
        depth = 0
        quote: str | None = None
        for i in range(open_idx, len(text)):
            ch = text[i]
            if quote:
                if ch == quote and (i == 0 or text[i - 1] != "\\"):
                    quote = None
                continue
            if ch in {'"', "'"}:
                quote = ch
                continue
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    calls.append(text[open_idx + 1:i])
                    break
    return calls


def _named_param_pairs_from_expression(expr: str | None) -> dict[str, str]:
    text = _clean_expression(expr)
    out: dict[str, str] = {}
    if not text:
        return out

    # Map.of("name", expr, "id", expr2) / ImmutableMap.of(...). Use a small
    # parenthesis scanner so nested getters like p.getPhoneId() do not truncate
    # the argument list.
    if ".of(" in text or text.startswith("of("):
        for arg_text in _call_argument_texts(text, {"of"}):
            args = split_java_arguments(arg_text or "")
            if len(args) >= 2 and len(args) % 2 == 0:
                for i in range(0, len(args), 2):
                    key = _strip_java_string_literal(args[i])
                    val = _clean_expression(args[i + 1]) if i + 1 < len(args) else ""
                    if key and val:
                        out[key] = val

    # new MapSqlParameterSource().addValue("name", expr).addValue(...).
    for arg_text in _call_argument_texts(text, {"addValue", "put"}):
        args = split_java_arguments(arg_text or "")
        if len(args) >= 2:
            key = _strip_java_string_literal(args[0])
            val = _clean_expression(args[1])
            if key and val:
                out[key] = val
    return out


def _named_param_bindings(method_info: dict[str, Any], syntax: dict[str, Any], assignment_by_target: dict[str, str]) -> dict[str, dict[str, str]]:
    by_var: dict[str, dict[str, str]] = defaultdict(dict)
    for target, expr in assignment_by_target.items():
        var = _local_var_name(target)
        pairs = _named_param_pairs_from_expression(expr)
        if var and pairs:
            by_var[var].update(pairs)
    for call in syntax.get("method_calls") or []:
        method = str(call.get("method") or "")
        if method not in {"addValue", "put"}:
            continue
        receiver = _local_var_name(call.get("receiver"))
        args = list(call.get("args") or [])
        if not receiver or len(args) < 2:
            continue
        key = _strip_java_string_literal(args[0])
        val = _clean_expression(args[1])
        if key and val:
            by_var[receiver][key] = val
    return {k: dict(v) for k, v in by_var.items()}


def _jooq_parameterized_sql_mappings(methods: dict[str, dict[str, Any]]) -> list[Fact]:
    """Extract candidate mappings for positional and named SQL/JDBC/JOOQ binds.

    Covered patterns are deliberately narrow and explainable:
      * query = dsl.update(TABLE).set(TABLE.COL, null).where(TABLE.ID.eq(null));
        query.bind(src.getCol(), src.getId()).execute();
      * dsl.execute("update T set A=? where ID=?", src.getA(), src.getId());
      * namedParameterJdbcTemplate.update("update T set A=:a where ID=:id", params);
      * namedParameterJdbcTemplate.update("insert into T (A, B) values (:a, :b)", Map.of(...));

    The fact is technical candidate evidence only. It never promotes WHERE/key
    slots to saved attributes.
    """
    facts: list[Fact] = []
    seq = 0
    for op, mi in sorted(methods.items()):
        body = mi.get("body") or ""
        statements = _jooq_update_statement_slots(body)
        syntax = _method_info_syntax(mi, body)
        assignment_by_target: dict[str, str] = {}
        assignment_by_var: dict[str, str] = {}
        for a in mi.get("syntax_assignments") or []:
            target = _clean_expression(a.get("target"))
            expr = _clean_expression(a.get("expression"))
            if target and expr:
                assignment_by_target[target] = expr
                var = _local_var_name(target)
                if var:
                    assignment_by_var[var] = expr
        named_params_by_var = _named_param_bindings(mi, syntax, assignment_by_target)

        def resolve_sql_expr(expr: str | None) -> str:
            value = _clean_expression(expr)
            var = _local_var_name(value)
            if value in assignment_by_target:
                return _clean_expression(assignment_by_target[value])
            if var and var in assignment_by_var:
                return _clean_expression(assignment_by_var[var])
            return value

        def emit_mapping_fact(stmt: dict[str, Any], bind_args: list[str] | None, mapping_kind: str, receiver: str, *, bind_by_name: dict[str, str] | None = None) -> None:
            nonlocal seq
            slots = list(stmt.get("slots") or [])
            if not slots:
                return
            mappings: list[dict[str, Any]] = []
            for i, slot in enumerate(slots):
                if bind_by_name is not None:
                    param = str(slot.get("param") or "")
                    source_expr = _clean_expression(bind_by_name.get(param)) if param in bind_by_name else None
                else:
                    source_expr = _clean_expression((bind_args or [])[i]) if i < len(bind_args or []) else None
                    param = None
                source_var, source_field = _getter_binding_from_expression(source_expr, mi) if source_expr else (None, None)
                row = {
                    "bind_index": i,
                    "storage_field": slot.get("field"),
                    "storage_field_ref": slot.get("field_ref"),
                    "field_role": slot.get("role"),
                    "source_expression": source_expr,
                    "source_object": source_var,
                    "source_field": source_field,
                    "mapping_status": "candidate_bind_order_mapping" if source_expr else "unresolved_missing_bind_arg",
                }
                if bind_by_name is not None:
                    row["bind_parameter"] = param
                    row["mapping_status"] = "candidate_named_parameter_mapping" if source_expr else "unresolved_missing_named_parameter_value"
                mappings.append(row)
            seq += 1
            named = bind_by_name is not None
            props = {
                "jooq_parameterized_sql_mapping_id": f"jooq_parameterized_sql_mapping_{seq:06d}",
                "operation": op,
                "class_name": mi.get("class_name"),
                "method_name": mi.get("method_name"),
                "receiver_expression": receiver,
                "storage_table": stmt.get("table"),
                "storage_table_ref": stmt.get("table_ref"),
                "sql_kind": stmt.get("sql_kind"),
                "mapping_kind": mapping_kind,
                "mapping_status": "candidate",
                "mappings": mappings,
                "write_target_fields": [m for m in mappings if m.get("field_role") == "write_target_field"],
                "where_key_fields": [m for m in mappings if m.get("field_role") == "where_key_field"],
                "evidence_policy": (
                    "named SQL/JDBC parameter mapping is technical candidate evidence; WHERE/key slots are not treated as saved fields"
                    if named else
                    "non-batch positional SQL/jOOQ bind-order mapping is technical candidate evidence; WHERE/key slots are not treated as saved fields"
                ),
            }
            facts.append(Fact(
                fact_type="jooq_parameterized_sql_mapping",
                name=f"{op}: {stmt.get('table') or 'unknown'} {'named' if named else 'positional'} bind",
                properties={k: v for k, v in props.items() if v not in (None, [], {})},
                evidence=_op_file_evidence(mi, "java_jooq_parameterized_sql_mapping"),
            ))

        for call in syntax.get("method_calls") or []:
            method = str(call.get("method") or "")
            args = list(call.get("args") or [])
            receiver = _clean_expression(call.get("receiver"))
            stmt: dict[str, Any] | None = None
            bind_args: list[str] = []
            mapping_kind = "jooq_parameterized_bind_order"

            if method == "bind":
                stmt_var = receiver
                # query.bind(...) where query is an update statement variable.
                if stmt_var in statements:
                    stmt = statements.get(stmt_var)
                # query.bind(...) where query variable was assigned from another variable.
                elif stmt_var in assignment_by_target and assignment_by_target[stmt_var] in statements:
                    stmt = statements.get(assignment_by_target[stmt_var])
                if not stmt:
                    continue
                bind_args = [_clean_expression(x) for x in args]
                emit_mapping_fact(stmt, bind_args, mapping_kind, receiver)
                continue

            if method in {"execute", "executeUpdate"}:
                if args:
                    sql_literal = resolve_sql_expr(args[0]).strip()
                    if sql_literal.startswith('"') or sql_literal.startswith("'"):
                        stmt = _sql_update_slots(sql_literal)
                        bind_args = [_clean_expression(x) for x in args[1:]]
                        mapping_kind = "parameterized_sql_bind_order"
                if not stmt and receiver in statements:
                    stmt = statements.get(receiver)
                    bind_args = []
                if stmt:
                    emit_mapping_fact(stmt, bind_args, mapping_kind, receiver)
                continue

            # Spring NamedParameterJdbcTemplate / similar named-param JDBC update.
            if method in {"update", "batchUpdate"} and args:
                sql_expr = resolve_sql_expr(args[0]).strip()
                if not (sql_expr.startswith('"') or sql_expr.startswith("'")):
                    continue
                stmt = _sql_named_parameter_slots(sql_expr)
                if not stmt:
                    continue
                bind_by_name: dict[str, str] = {}
                if len(args) >= 2:
                    second = _clean_expression(args[1])
                    bind_by_name.update(_named_param_pairs_from_expression(second))
                    var = _local_var_name(second)
                    if var and var in named_params_by_var:
                        bind_by_name.update(named_params_by_var[var])
                emit_mapping_fact(stmt, None, "named_parameter_sql_mapping", receiver, bind_by_name=bind_by_name)
                continue
    return facts



def _java_lineage_pattern_facts(methods: dict[str, dict[str, Any]]) -> list[Fact]:
    facts: list[Fact] = []
    seq = 0
    for op, mi in sorted(methods.items()):
        syntax = _method_info_syntax(mi, mi.get("body") or "")
        for call in syntax.get("method_calls") or []:
            method = str(call.get("method") or "")
            receiver = _clean_expression(call.get("receiver"))
            text = _clean_expression(call.get("text"))
            pattern_kind = None
            details: dict[str, Any] = {}
            if method == "getParsedObject":
                pattern_kind = "kafka_request_get_parsed_object"
                details = {"source_wrapper": receiver, "lineage_hint": "KafkaRequest<T> parsed payload extraction"}
            elif method == "toBuilder":
                pattern_kind = "lombok_to_builder_clone"
                details = {"source_object": receiver, "lineage_hint": "old object cloned into builder before field override"}
            elif method in {"collect", "toList", "toSet", "toMap", "groupingBy"} or method in {"map", "filter", "forEach"}:
                # Too many stream calls can be noisy; keep only calls whose receiver/expression mentions stream.
                if "stream" not in text and ".stream" not in receiver:
                    continue
                pattern_kind = "stream_collection_lineage_hint"
                details = {"receiver": receiver, "method": method, "lineage_hint": "stream/map/filter/collect may carry collection element provenance"}
            if not pattern_kind:
                continue
            seq += 1
            facts.append(Fact(
                fact_type="java_lineage_pattern",
                name=f"{pattern_kind}: {op}",
                properties={
                    "java_lineage_pattern_id": f"java_lineage_pattern_{seq:06d}",
                    "pattern_kind": pattern_kind,
                    "operation": op,
                    "class_name": mi.get("class_name"),
                    "method_name": mi.get("method_name"),
                    "expression": text,
                    "source_scope": "test_code" if "/src/test/" in str(mi.get("file") or "").replace("\\", "/") else "production_code",
                    **details,
                    "evidence_policy": "pattern hint only; use concrete mapping facts before treating as confirmed lineage",
                },
                evidence=[EvidenceRef(file_path=str(mi.get("file")), line_start=call.get("line_start") or mi.get("line_start"), extractor="java_lineage_pattern")],
            ))
    return facts



def _class_file_evidence(class_info: dict[str, Any] | None, extractor: str) -> list[EvidenceRef]:
    if not class_info:
        return []
    return [EvidenceRef(file_path=str(class_info.get("file") or ""), extractor=extractor)]


def _spring_component_dependency_facts(
    *,
    class_fields: dict[str, dict[str, str]],
    class_infos: dict[str, dict[str, Any]],
) -> list[Fact]:
    """Emit source-level Spring dependency hints.

    This is not a runtime bean container.  The fact only says that a component class
    has a typed field that can be used by Spring/Lombok constructor injection or
    field injection.  Business/profile decisions must use it as navigation evidence.
    """
    facts: list[Fact] = []
    seq = 0
    components = {c for c, i in class_infos.items() if i.get("is_spring_component") or i.get("kind") in {"class", "interface"}}
    iface_impls = _interface_impls(class_infos, {})
    for class_name, fields in sorted(class_fields.items()):
        owner = class_infos.get(class_name) or {}
        if not owner.get("is_spring_component"):
            continue
        for field_name, raw_type in sorted(fields.items()):
            dep_type = _simple_type_name(raw_type)
            if not dep_type or dep_type in {"String", "Integer", "Long", "Boolean", "List", "Map", "Set"}:
                continue
            if dep_type not in components and dep_type not in iface_impls and not dep_type.endswith(("Service", "Handler", "Dao", "DAO", "Repository", "Processor", "Producer", "Consumer")):
                continue
            seq += 1
            injection_kind = "lombok_required_args_constructor_candidate" if owner.get("lombok_required_args") else "field_or_constructor_injection_candidate"
            props = {
                "spring_component_dependency_id": f"spring_component_dependency_{seq:06d}",
                "source_class": class_name,
                "source_component_kind": owner.get("spring_component_kind"),
                "field_name": field_name,
                "declared_type": dep_type,
                "candidate_implementations": iface_impls.get(dep_type, []),
                "dependency_resolution_status": "candidate",
                "injection_kind": injection_kind,
                "source_scope": _source_scope_for_file(owner.get("file")),
                "evidence_policy": "source-level Spring dependency hint only; not runtime bean resolution and not business evidence",
            }
            facts.append(Fact(
                fact_type="spring_component_dependency",
                name=f"{class_name}.{field_name}: {dep_type}",
                properties={k: v for k, v in props.items() if v not in (None, [], {})},
                evidence=_class_file_evidence(owner, "java_spring_component_dependency"),
            ))
    return facts


def _template_method_dispatch_facts(methods: dict[str, dict[str, Any]], class_infos: dict[str, dict[str, Any]]) -> list[Fact]:
    """Emit candidate links for common abstract handler/template method patterns."""
    facts: list[Fact] = []
    seq = 0
    override_names = {
        "handleByDal", "handleByMbk", "doHandleByDal", "doHandleByMbk", "handleInternal",
        "doHandle", "processInternal", "executeInternal", "runInternal",
    }
    template_names = {"handle", "process", "execute", "run"}
    for op, mi in sorted(methods.items()):
        method_name = str(mi.get("method_name") or "")
        if method_name not in override_names:
            continue
        class_name = str(mi.get("class_name") or "")
        info = class_infos.get(class_name) or {}
        superclass = _simple_type_name(info.get("superclass"))
        if not superclass:
            continue
        candidate_templates = [f"{superclass}.{name}" for name in sorted(template_names) if f"{superclass}.{name}" in methods]
        if not candidate_templates and not superclass.lower().startswith("abstract") and "handler" not in superclass.lower():
            continue
        seq += 1
        props = {
            "template_method_dispatch_id": f"template_method_dispatch_{seq:06d}",
            "subclass": class_name,
            "superclass": superclass,
            "override_operation": op,
            "override_method": method_name,
            "candidate_template_operations": candidate_templates,
            "dispatch_status": "candidate_template_override",
            "resolution_kind": "abstract_template_method_override",
            "source_scope": _source_scope_for_file(mi.get("file")),
            "evidence_policy": "template dispatch is source-level candidate evidence; verify call chain before confirmed lineage",
        }
        facts.append(Fact(
            fact_type="template_method_dispatch",
            name=f"{superclass} -> {op}",
            properties={k: v for k, v in props.items() if v not in (None, [], {})},
            evidence=_op_file_evidence(mi, "java_template_method_dispatch"),
        ))
    return facts






@dataclass
class _JavaPersistenceLineageContext:
    files: list[Path]
    deep: bool
    methods: dict[str, dict[str, Any]]
    class_fields: dict[str, dict[str, str]]
    class_infos: dict[str, dict[str, Any]]
    warnings: list[str]
    methods_by_class_method: dict[tuple[str, str], list[dict[str, Any]]]
    raw_methods_by_class_method: dict[tuple[str, str], list[dict[str, Any]]]
    origins: list[dict[str, Any]]
    origins_by_operation: dict[str, list[dict[str, Any]]]
    storage_accesses: list[dict[str, Any]]
    schema_fields: dict[str, list[dict[str, Any]]]
    iface_impls: dict[str, list[str]]
    mapper_signatures: dict[str, list[dict[str, Any]]]
    repo_entity_by_repo_type: dict[str, str]
    jooq_batch_bind_facts: list[Fact]
    jooq_parameterized_sql_mapping_facts: list[Fact]
    java_lineage_pattern_facts: list[Fact]
    spring_component_dependency_facts: list[Fact]
    template_method_dispatch_facts: list[Fact]
    factory_method_mapping_facts: list[Fact]
    builder_field_mapping_facts: list[Fact]
    stream_collection_lineage_facts: list[Fact]
    mapstruct_mapper_signature_facts: list[Fact]
    calls: list[dict[str, Any]]
    interprocedural_provenance_index: dict[str, Any]


_ProgressCallback = Callable[[str, str, dict[str, Any] | None], None]


def _build_java_persistence_lineage_context(files: list[Path], *, deep: bool, progress: _ProgressCallback | None = None) -> _JavaPersistenceLineageContext:
    """Build indexes and standalone resolver facts used by persistence lineage phases."""

    def phase(name: str, status: str, **data: Any) -> None:
        if progress:
            progress(f"context.{name}", status, data)

    phase("method_index", "running", file_count=len(files))
    methods, class_fields, class_infos, warnings = _build_method_index(files)
    phase("method_index", "done", method_count=len(methods), class_count=len(class_infos), warning_count=len(warnings))

    phase("method_grouping", "running", method_count=len(methods))
    methods_by_class_method = _methods_by_class_method(methods)
    raw_methods_by_class_method = _parsed_methods_by_class_method(files) if deep else {}
    phase("method_grouping", "done", grouped_method_count=len(methods_by_class_method), raw_grouped_method_count=len(raw_methods_by_class_method))

    phase("origin_detection", "running", method_count=len(methods))
    origins = _detect_origins(methods)
    phase("origin_detection", "done", origin_count=len(origins))

    phase("call_graph", "running", method_count=len(methods), deep=deep)
    calls = _build_call_facts(methods, class_fields, class_infos) if deep else []
    phase("call_graph", "done", call_count=len(calls))

    phase("storage_access_detection", "running", method_count=len(methods))
    storage_accesses = _build_storage_facts(methods)
    phase("storage_access_detection", "done", storage_access_count=len(storage_accesses))

    phase("jooq_batch_bind_mappings", "running", method_count=len(methods))
    jooq_batch_bind_facts = _jooq_batch_bind_mappings(methods)
    phase("jooq_batch_bind_mappings", "done", fact_count=len(jooq_batch_bind_facts))

    phase("jooq_parameterized_sql_mappings", "running", method_count=len(methods))
    jooq_parameterized_sql_mapping_facts = _jooq_parameterized_sql_mappings(methods)
    phase("jooq_parameterized_sql_mappings", "done", fact_count=len(jooq_parameterized_sql_mapping_facts))

    phase("java_lineage_patterns", "running", method_count=len(methods))
    java_lineage_pattern_facts = _java_lineage_pattern_facts(methods)
    phase("java_lineage_patterns", "done", fact_count=len(java_lineage_pattern_facts))

    phase("spring_component_dependencies", "running", class_count=len(class_infos))
    spring_component_dependency_facts = _spring_component_dependency_facts(class_fields=class_fields, class_infos=class_infos)
    phase("spring_component_dependencies", "done", fact_count=len(spring_component_dependency_facts))

    phase("template_method_dispatches", "running", method_count=len(methods))
    template_method_dispatch_facts = _template_method_dispatch_facts(methods, class_infos)
    phase("template_method_dispatches", "done", fact_count=len(template_method_dispatch_facts))

    phase("factory_method_mappings", "running", method_count=len(methods))
    factory_method_mapping_facts = _factory_method_mapping_facts(methods)
    phase("factory_method_mappings", "done", fact_count=len(factory_method_mapping_facts))

    method_variants = [
        variant
        for info in class_infos.values()
        for variant in (info.get("method_variants") or [])
        if isinstance(variant, dict)
    ]
    phase("builder_field_mappings", "running", method_count=len(methods), method_variant_count=len(method_variants))
    builder_field_mapping_facts = _builder_field_mapping_facts(methods, method_variants=method_variants)
    phase("builder_field_mappings", "done", fact_count=len(builder_field_mapping_facts))

    phase("stream_collection_lineages", "running", method_count=len(methods))
    stream_collection_lineage_facts = _stream_collection_lineage_facts(methods)
    phase("stream_collection_lineages", "done", fact_count=len(stream_collection_lineage_facts))

    phase("schema_fields", "running", file_count=len(files))
    schema_fields = _extract_all_schema_fields(files)
    phase("schema_fields", "done", schema_count=len(schema_fields))

    phase("interface_implementations", "running", class_count=len(class_infos))
    iface_impls = _interface_impls(class_infos, methods)
    phase("interface_implementations", "done", interface_count=len(iface_impls))

    phase("mapper_signatures", "running", deep=deep)
    mapper_signatures = _mapper_method_signatures(files) if deep else {}
    mapstruct_mapper_signature_facts = _mapstruct_mapper_signature_facts(mapper_signatures) if deep else []
    phase("mapper_signatures", "done", signature_count=sum(len(v) for v in mapper_signatures.values()), fact_count=len(mapstruct_mapper_signature_facts))

    phase("repository_entity_map", "running", deep=deep)
    repo_entity_by_repo_type = _repository_type_to_entity_map(files, class_infos=class_infos) if deep else {}
    phase("repository_entity_map", "done", mapping_count=len(repo_entity_by_repo_type))
    origins_by_operation: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for origin in origins:
        origins_by_operation[str(origin.get("operation") or "")].append(origin)
    interprocedural_provenance_index = _interprocedural_index(
        methods=methods,
        class_infos=class_infos,
        calls=calls,
        origins_by_operation=origins_by_operation,
        builder_field_mapping_facts=builder_field_mapping_facts,
        factory_method_mapping_facts=factory_method_mapping_facts,
        schema_fields=schema_fields,
    ) if deep else {}
    return _JavaPersistenceLineageContext(
        files=files,
        deep=deep,
        methods=methods,
        class_fields=class_fields,
        class_infos=class_infos,
        warnings=warnings,
        methods_by_class_method=methods_by_class_method,
        raw_methods_by_class_method=raw_methods_by_class_method,
        origins=origins,
        origins_by_operation=origins_by_operation,
        storage_accesses=storage_accesses,
        schema_fields=schema_fields,
        iface_impls=iface_impls,
        mapper_signatures=mapper_signatures,
        repo_entity_by_repo_type=repo_entity_by_repo_type,
        jooq_batch_bind_facts=jooq_batch_bind_facts,
        jooq_parameterized_sql_mapping_facts=jooq_parameterized_sql_mapping_facts,
        java_lineage_pattern_facts=java_lineage_pattern_facts,
        spring_component_dependency_facts=spring_component_dependency_facts,
        template_method_dispatch_facts=template_method_dispatch_facts,
        factory_method_mapping_facts=factory_method_mapping_facts,
        builder_field_mapping_facts=builder_field_mapping_facts,
        stream_collection_lineage_facts=stream_collection_lineage_facts,
        mapstruct_mapper_signature_facts=mapstruct_mapper_signature_facts,
        calls=calls,
        interprocedural_provenance_index=interprocedural_provenance_index,
    )


def _data_source_phase(ctx: _JavaPersistenceLineageContext) -> list[Fact]:
    facts: list[Fact] = []
    data_source_seq = 0
    for origin in ctx.origins:
        if not origin.get("is_payload_origin"):
            continue
        op = str(origin.get("operation") or "")
        payload_type = _simple_type_name(origin.get("payload_type"))
        fields = _fields_for_type(ctx.schema_fields, payload_type)
        data_source_seq += 1
        facts.append(_data_source_fact(
            f"data_source_{data_source_seq:06d}",
            source_kind=_technical_source_kind(_source_boundary_for_origin(origin)),
            operation=op,
            payload=payload_type,
            fields=[{"name": f.get("name"), "type": f.get("type"), "role": f.get("role")} for f in fields],
            evidence=_op_file_evidence(ctx.methods.get(op), "java_persistence_lineage_source") if ctx.methods.get(op) else [],
            payload_resolution_status=origin.get("payload_resolution_status"),
            payload_resolution_basis=list(origin.get("payload_resolution_basis") or []),
        ))
    return facts


def _standalone_mapping_hint_phase(ctx: _JavaPersistenceLineageContext) -> list[Fact]:
    facts: list[Fact] = []
    facts.extend(ctx.jooq_batch_bind_facts)
    facts.extend(_jooq_batch_bind_write_facts(ctx.jooq_batch_bind_facts))
    facts.extend(ctx.jooq_parameterized_sql_mapping_facts)
    facts.extend(ctx.java_lineage_pattern_facts)
    facts.extend(ctx.spring_component_dependency_facts)
    facts.extend(ctx.template_method_dispatch_facts)
    facts.extend(ctx.factory_method_mapping_facts)
    facts.extend(ctx.builder_field_mapping_facts)
    facts.extend(ctx.stream_collection_lineage_facts)
    facts.extend(ctx.mapstruct_mapper_signature_facts)
    return facts


def _persistent_write_lineage_phase(
    ctx: _JavaPersistenceLineageContext,
    progress: _ProgressCallback | None = None,
    *,
    progress_interval: int = 100,
) -> tuple[list[Fact], dict[str, Any]]:
    methods = ctx.methods
    class_fields = ctx.class_fields
    class_infos = ctx.class_infos
    methods_by_class_method = ctx.methods_by_class_method
    raw_methods_by_class_method = ctx.raw_methods_by_class_method
    origins_by_operation = ctx.origins_by_operation
    storage_accesses = ctx.storage_accesses
    schema_fields = ctx.schema_fields
    iface_impls = ctx.iface_impls
    mapper_signatures = ctx.mapper_signatures
    repo_entity_by_repo_type = ctx.repo_entity_by_repo_type
    deep = ctx.deep
    facts: list[Fact] = []
    write_seq = 0
    lineage_seq = 0
    gap_seq = 0
    source_kind_counts: Counter[str] = Counter()
    gap_counts: Counter[str] = Counter()
    access_kind_counts: Counter[str] = Counter()
    operation_kind_counts: Counter[str] = Counter()
    source_inspection_seq = 0
    source_inspection_keys: set[tuple[str, str, str, str, str]] = set()
    dao_jooq_mapping_cache: dict[str, list[dict[str, Any]]] = {}
    variable_origins_cache: dict[str, dict[str, dict[str, Any]]] = {}
    ingress_by_param_cache: dict[str, dict[str, dict[str, Any]]] = {}
    source_candidate_cache: dict[tuple[str, str], dict[str, Any] | None] = {}
    all_bindings_cache: dict[tuple[str, str, tuple[str, ...], str], list[dict[str, Any]]] = {}
    promoted_custom_dao_mutation_count = 0

    total_accesses = len(storage_accesses)
    progress_interval = max(1, int(progress_interval or 100))
    for access_idx, access in enumerate(storage_accesses, start=1):
        if progress and (access_idx == 1 or access_idx % progress_interval == 0 or access_idx == total_accesses):
            progress("persistent_write_lineage_phase.access_loop", "running", {
                "processed_accesses": access_idx - 1,
                "total_accesses": total_accesses,
                "fact_count": len(facts),
                "operation": str(access.get("operation") or ""),
                "access_kind": str(access.get("access_kind") or ""),
                "storage_method": str(access.get("storage_method") or ""),
            })
        access_kind_counts[str(access.get("access_kind") or "unknown")] += 1
        operation_kind_counts[str(access.get("operation_kind") or "unknown")] += 1
        op = str(access.get("operation") or "")
        mi = methods.get(op)
        evidence = _op_file_evidence(mi, "java_persistence_lineage_storage") if mi else []
        if not mi:
            gap_seq += 1
            facts.append(_storage_lineage_gap_fact(
                f"storage_lineage_gap_{gap_seq:06d}",
                gap_kind="storage_operation_not_indexed",
                storage_access=access,
                saved_object=None,
                saved_object_field=None,
                reason="storage operation is present but its method body was not indexed",
                missing_links=["method body not indexed"],
                evidence=evidence,
            ))
            gap_counts["storage_operation_not_indexed"] += 1
            continue

        receiver_expr = str(access.get("receiver_expression") or "")
        receiver_type = _declared_receiver_type(receiver_expr, mi, class_fields)

        # A custom DAO update is initially classified as a generic mutation because
        # its caller only exposes a method boundary.  Promote it to a payload write
        # only after source inspection of the DAO implementation proves concrete
        # parameter -> JOOQ table/column write mappings.  This keeps arbitrary
        # status/key mutations and deletes out of the canonical write catalogue.
        if deep and _custom_dao_mutation_has_concrete_jooq_write(
            access=access,
            caller_mi=mi,
            receiver_type=receiver_type,
            methods_by_class_method=methods_by_class_method,
            raw_methods_by_class_method=raw_methods_by_class_method,
            methods=methods,
            dao_jooq_mapping_cache=dao_jooq_mapping_cache,
        ):
            access = {
                **access,
                "access_kind": "write",
                "writes_new_payload": True,
                "payload_role": access.get("payload_role") or "saved_payload",
                "promoted_from_access_kind": "mutation",
                "promotion_basis": "resolved_custom_dao_jooq_write_mapping",
            }
            promoted_custom_dao_mutation_count += 1

        # Deep profile emits explicit non-write evidence so LLM does not treat reads/deletes
        # as unresolved saved payloads. Quick profile simply ignores non-writes.
        if access.get("access_kind") != "write" or access.get("writes_new_payload") is False:
            if deep:
                gap_kind, reason, missing, conf = _storage_gap_for_non_write(access)
                gap_seq += 1
                facts.append(_storage_lineage_gap_fact(
                    f"storage_lineage_gap_{gap_seq:06d}",
                    gap_kind=gap_kind,
                    storage_access=access,
                    saved_object=None,
                    saved_object_field=None,
                    reason=reason,
                    missing_links=missing,
                    evidence=evidence,
                    extra={"not_saved_payload": True, "decision_relevance": "not_relevant"},
                ))
                gap_counts[gap_kind] += 1
            continue

        body = mi.get("body") or ""
        payload = _clean_expression(access.get("payload_expression"))
        td = _payload_type_details(payload, mi)
        payload_type = _simple_type_name(td.get("type") or (mi.get("var_types") or {}).get(payload) or next((p.get("type") for p in mi.get("params") or [] if p.get("name") == payload), None))
        dao_entity_type = repo_entity_by_repo_type.get(receiver_type or "") if deep else None
        # Never expose a DAO variable/receiver as an entity type. It is better to keep
        # the entity unknown than to let the LLM read `ucpPhoneDao` as a domain schema.
        if dao_entity_type and dao_entity_type.lower() in {receiver_expr.lower(), str(receiver_type or "").lower()}:
            dao_entity_type = None
        mapper_sig = _mapper_signature_for_expression(payload, mapper_signatures) if deep and payload else None

        if op in variable_origins_cache:
            variable_origins = variable_origins_cache[op]
        else:
            variable_origins = _variable_origins(body, mi.get("params") or [], method_info=mi)
            variable_origins_cache[op] = variable_origins
        if op in ingress_by_param_cache:
            ingress_by_param = ingress_by_param_cache[op]
        else:
            ingress_by_param = {str(o.get("payload_parameter")): o for o in origins_by_operation.get(op, []) if o.get("payload_parameter")}
            ingress_by_param_cache[op] = ingress_by_param
        if deep:
            source_candidate_key = (op, payload or "")
            if source_candidate_key in source_candidate_cache:
                source_candidate = source_candidate_cache[source_candidate_key]
            else:
                source_candidate = _collection_source_candidate(body, collection_var=payload, method_info=mi, ingress_by_param=ingress_by_param)
                source_candidate_cache[source_candidate_key] = source_candidate
        else:
            source_candidate = None
        object_lineage_emitted = False

        saved_object = None
        if td.get("container_kind") in {"collection", "array", "map"} and td.get("element_type"):
            saved_object = _simple_type_name(td.get("element_type"))
        if not saved_object and mapper_sig and mapper_sig.get("target_container") and mapper_sig.get("target_container") != "unknown":
            saved_object = _simple_type_name(mapper_sig.get("target_container"))
        if not saved_object and payload_type and payload_type != "unknown":
            saved_object = payload_type
        if (not saved_object or saved_object in {"List", "Set", "Collection", "Iterable", "Map", "HashMap", "ArrayList", "LinkedHashMap", "unknown"}) and dao_entity_type:
            saved_object = dao_entity_type
        if not saved_object:
            saved_object = "unknown"
        if deep and dao_entity_type and saved_object and saved_object != "unknown" and dao_entity_type != saved_object:
            # A suffix-based DAO fallback like UcpPhoneDao -> UcpPhone is weaker than a
            # concrete saved payload/collection element type such as UcpPhone_2Record.
            # Do not expose a misleading DAO entity when the fallback type has no schema.
            if not _fields_for_type(schema_fields, dao_entity_type) and _fields_for_type(schema_fields, saved_object):
                dao_entity_type = saved_object

        fields = _fields_for_type(schema_fields, saved_object)
        written_field_names = [str(f.get("name")) for f in fields if f.get("name")]
        write_seq += 1
        persistent_write_id = f"persistent_write_{write_seq:06d}"
        facts.append(_persistent_write_fact(
            persistent_write_id,
            access,
            saved_object=saved_object,
            written_fields=written_field_names,
            evidence=evidence,
            type_details=td,
            dao_entity_type=dao_entity_type,
            dao_type=receiver_type,
        ))

        cross_facts: list[Fact] = []
        if deep and _storage_resolution_level_for_access(access) == "custom_dao_boundary":
            cross_facts, lineage_seq = _cross_dao_jooq_lineage_facts(
                access=access,
                caller_mi=mi,
                receiver_type=receiver_type,
                methods_by_class_method=methods_by_class_method,
                methods=methods,
                raw_methods_by_class_method=raw_methods_by_class_method,
                persistent_write_id=persistent_write_id,
                lineage_id_start=lineage_seq,
                evidence=evidence,
                variable_origins=variable_origins,
                ingress_by_param=ingress_by_param,
                dao_jooq_mapping_cache=dao_jooq_mapping_cache,
                interprocedural_index=ctx.interprocedural_provenance_index,
            )
            if cross_facts:
                facts.extend(cross_facts)
                for cf in cross_facts:
                    source_kind_counts[str((cf.properties or {}).get("source_kind") or "unknown")] += 1
                object_lineage_emitted = True

        # Request source inspection only when the source implementation did not
        # yield a concrete physical write.  Resolved custom DAO/JOOQ mappings must
        # not coexist with the older `dao_implementation_not_resolved` diagnostic.
        if _storage_resolution_level_for_access(access) == "custom_dao_boundary" and not cross_facts:
            key = _inspection_key("dao_implementation_not_resolved", op, access, saved_object)
            if key not in source_inspection_keys:
                source_inspection_keys.add(key)
                source_inspection_seq += 1
                facts.append(_source_inspection_request_fact(
                    f"source_inspection_request_{source_inspection_seq:06d}",
                    reason="dao_implementation_not_resolved",
                    priority="high" if bool(access.get("writes_new_payload")) else "medium",
                    target_operation=op,
                    focus="Find the implementation or mapper/resource backing this DAO/storage call and verify whether it reaches a real persistent sink.",
                    related_evidence_refs=[persistent_write_id, str(access.get("storage_access_id") or "")],
                    storage_access=access,
                    saved_object=saved_object,
                    trigger_blockers=["persistence_write:candidate", "physical_storage:unresolved"],
                    evidence=evidence,
                    expected_observations=[
                        "DAO implementation class, mapper XML, SQL resource, generated source, or framework descriptor",
                        "Real sink inside implementation: SQL INSERT/UPDATE/MERGE, JdbcTemplate, EntityManager, repository.save, or mapper update/insert",
                        "Physical table/collection name if available",
                    ],
                    tokens=[receiver_type or "", str(access.get("table_or_repository") or "")],
                ))

        pre_mapped_fields: set[str] = set()
        # Direct mapper save: when mapper annotations or safe same-name source/target
        # schema pairs are available, emit candidate field-level source-to-storage
        # lineages instead of leaving the write as a mapper-result gap.
        if mapper_sig:
            source_container = mapper_sig.get("source_container") or "unknown"
            target_container = mapper_sig.get("target_container") or saved_object
            mapper_field_mappings = _mapper_result_candidate_field_mappings(
                mapper_sig,
                source_container=source_container,
                target_container=target_container,
                schema_fields=schema_fields,
                written_field_names=written_field_names,
            ) if deep else []
            mapper_src_expr = _clean_expression(mapper_sig.get("source_variable") or "")
            mapper_origin = _source_expr_to_origin(mapper_src_expr, method_info=mi, variable_origins=variable_origins, ingress_by_param=ingress_by_param) if mapper_src_expr else {}
            mapper_origin_kind = str(mapper_origin.get("ultimate_origin_kind") or "unknown")
            mapper_source_kind = _technical_source_kind(mapper_origin_kind, fallback="method_input") if mapper_origin else "mapper_input"
            mapper_source_operation = mapper_origin.get("origin_operation") or op
            mapper_source_payload = mapper_origin.get("origin_payload") or source_container
            mapper_source_container = mapper_origin.get("origin_container") or source_container
            mapper_source_container_type = mapper_origin.get("origin_container_type")
            mapper_source_element_type = mapper_origin.get("origin_element_type")
            mapper_source_payload_parameter = mapper_origin.get("origin_payload_parameter") or mapper_src_expr or None
            mapper_expression = mapper_sig.get("expression") or payload

            if mapper_field_mappings:
                for mf in mapper_field_mappings:
                    target_field = _canonical_field_name(str(mf.get("target_field") or ""), written_field_names)
                    source_field = str(mf.get("source_field") or "")
                    if not target_field or not source_field:
                        continue
                    pre_mapped_fields.add(target_field)
                    source_kind_counts[mapper_source_kind] += 1
                    lineage_seq += 1
                    mapping_kind = str(mf.get("mapping_kind") or "mapper_result_field_candidate")
                    missing = [
                        "mapper_result_field_mapping_candidate",
                        str(mf.get("mapping_status") or "candidate_mapper_field_mapping"),
                    ]
                    if mapper_origin_kind in {"unknown", ""} and not mapper_src_expr:
                        missing.append("source_kind_not_confirmed")
                    facts.append(_source_to_storage_lineage_fact(
                        f"source_to_storage_lineage_{lineage_seq:06d}",
                        source_kind=mapper_source_kind,
                        source_operation=mapper_source_operation,
                        source_payload=mapper_source_payload,
                        source_field=source_field,
                        source_field_role=_field_role(source_field),
                        storage_operation=op,
                        storage_call=f"{access.get('receiver_expression')}.{access.get('storage_method')}({access.get('payload_expression') or ''})",
                        storage_method=str(access.get("storage_method") or "") or None,
                        storage_access_id=str(access.get("storage_access_id") or "") or None,
                        persistent_write_id=persistent_write_id,
                        storage_target=access.get("table_or_repository"),
                        storage_resolution_level=_storage_resolution_level_for_access(access),
                        saved_object=target_container,
                        saved_object_field=target_field,
                        storage_field=target_field,
                        assignment_kind=mapping_kind,
                        assignment_expression=str(mapper_expression or ""),
                        origin_expression=mapper_src_expr or str(mapper_expression or ""),
                        path=[source_container, f"{mapper_sig.get('method') or 'mapper'}.{source_field}->{target_field}", f"{access.get('receiver_expression')}.{access.get('storage_method')}"] ,
                        missing_links=missing,
                        evidence_refs=[str(access.get("storage_access_id") or "")],
                        evidence=evidence,
                        source_container=mapper_source_container,
                        source_container_type=mapper_source_container_type,
                        source_element_type=mapper_source_element_type,
                        source_payload_parameter=mapper_source_payload_parameter,
                    ))
            else:
                lineage_seq += 1
                missing = ["mapper_not_resolved", "field_mapping_not_resolved"]
                facts.append(_source_to_storage_lineage_fact(
                    f"source_to_storage_lineage_{lineage_seq:06d}",
                    source_kind="mapper_input",
                    source_operation=op,
                    source_payload=source_container,
                    source_field=None,
                    source_field_role="unknown",
                    storage_operation=op,
                    storage_call=f"{access.get('receiver_expression')}.{access.get('storage_method')}({access.get('payload_expression') or ''})",
                    storage_method=str(access.get("storage_method") or "") or None,
                    storage_access_id=str(access.get("storage_access_id") or "") or None,
                    persistent_write_id=persistent_write_id,
                    storage_target=access.get("table_or_repository"),
                    storage_resolution_level=_storage_resolution_level_for_access(access),
                    saved_object=target_container,
                    saved_object_field=None,
                    storage_field=None,
                    assignment_kind="mapper_call",
                    assignment_expression=payload,
                    origin_expression=mapper_sig.get("expression") or payload,
                    path=[source_container, mapper_sig.get("expression") or payload, f"{access.get('receiver_expression')}.{access.get('storage_method')}"],
                    missing_links=missing,
                    evidence_refs=[str(access.get("storage_access_id") or "")],
                    evidence=evidence,
                ))
                # Object-level mapper result -> DAO payload is now resolved as a
                # candidate source-to-storage segment.  Do not emit the older
                # save_payload_from_mapper_result gap here; missing field-level
                # mapper body evidence is still carried in missing_links and,
                # when saved fields are known, by ordinary field_mapping_not_resolved
                # gaps below.
                key = _inspection_key("mapper_or_converter_mapping_not_resolved", op, access, target_container)
                if key not in source_inspection_keys:
                    source_inspection_keys.add(key)
                    source_inspection_seq += 1
                    facts.append(_source_inspection_request_fact(
                        f"source_inspection_request_{source_inspection_seq:06d}",
                        reason="mapper_or_converter_mapping_not_resolved",
                        priority="high",
                        target_operation=op,
                        focus="Inspect mapper/converter call that creates the saved payload and verify field-level mappings inside it.",
                        related_evidence_refs=[persistent_write_id, str(access.get("storage_access_id") or "")],
                        storage_access=access,
                        source_payload=str(source_container or ""),
                        saved_object=str(target_container or saved_object or ""),
                        trigger_blockers=["field_mapping:unresolved"],
                        evidence=evidence,
                        expected_observations=[
                            "Converter/map method body",
                            "Assignments from source fields to saved object fields",
                            "Whether mapping is direct copy, derived value, constant, or unresolved",
                        ],
                        tokens=[str(mapper_sig.get("method") or ""), str(mapper_sig.get("expression") or payload)],
                    ))
            # If target fields were resolved, still continue below to see if local assignments also exist.

        if not fields:
            if deep and source_candidate:
                lineage_seq += 1
                obj_fact = _emit_object_level_lineage(
                    lineage_id=f"source_to_storage_lineage_{lineage_seq:06d}",
                    source_candidate=source_candidate,
                    op=op,
                    access=access,
                    saved_object=saved_object,
                    td=td,
                    evidence=evidence,
                    missing_links=["saved_object_schema_not_resolved", "collection_element_mapping_not_resolved" if td.get("container_kind") else "object_mapping_not_resolved"],
                    persistent_write_id=persistent_write_id,
                )
                if obj_fact:
                    facts.append(obj_fact)
                    source_kind_counts[str(obj_fact.properties.get("source_kind") or "unknown")] += 1
                    object_lineage_emitted = True
                    key = _inspection_key("saved_object_schema_or_mapping_not_resolved", op, access, saved_object)
                    if key not in source_inspection_keys:
                        source_inspection_keys.add(key)
                        source_inspection_seq += 1
                        facts.append(_source_inspection_request_fact(
                            f"source_inspection_request_{source_inspection_seq:06d}",
                            reason="saved_object_schema_or_mapping_not_resolved",
                            priority="medium",
                            target_operation=op,
                            focus="Inspect saved payload construction and type declarations because analyzer did not resolve saved object fields.",
                            related_evidence_refs=[persistent_write_id, str(obj_fact.properties.get("source_to_storage_lineage_id") or ""), str(access.get("storage_access_id") or "")],
                            storage_access=access,
                            source_payload=str(obj_fact.properties.get("source_payload") or ""),
                            saved_object=saved_object,
                            trigger_blockers=["field_mapping:unresolved", "physical_storage:unresolved"],
                            evidence=evidence,
                            expected_observations=["Saved object class fields", "Collection element type", "Payload construction path"],
                            tokens=[saved_object, payload],
                        ))
            gap_kind = "saved_object_schema_unknown"
            missing_links = ["saved object schema not resolved"]
            reason = "persistent write was found, but saved object fields were not resolved"
            extra: dict[str, Any] = {}
            if deep:
                if td.get("container_kind") and not td.get("element_type"):
                    gap_kind = "collection_element_type_unknown" if td.get("container_kind") != "map" else "map_value_type_unknown"
                    missing_links = ["collection/map element type not resolved", "saved object schema not resolved"]
                    reason = "persistent write saves a collection/map, but element/value type was not resolved"
                elif not dao_entity_type and receiver_type and any(tok in str(receiver_type).lower() for tok in ("dao", "repository", "repo")):
                    gap_kind = "dao_entity_type_unknown"
                    missing_links = ["DAO/repository entity type not resolved", "saved object schema not resolved"]
                    reason = "persistent write target is DAO/repository-like, but entity type was not resolved"
                elif mapper_sig:
                    gap_kind = "mapper_not_resolved"
                    missing_links = ["mapper target fields not resolved", "saved object schema not resolved"]
                    reason = "mapper/converter result is saved, but target schema or mapping was not resolved"
                extra = {"saved_container_kind": td.get("container_kind"), "saved_element_type": td.get("element_type"), "dao_type": receiver_type, "dao_entity_type": dao_entity_type}
            gap_seq += 1
            facts.append(_storage_lineage_gap_fact(
                f"storage_lineage_gap_{gap_seq:06d}",
                gap_kind=gap_kind,
                storage_access=access,
                saved_object=saved_object,
                saved_object_field=None,
                reason=reason,
                missing_links=missing_links,
                evidence=evidence,
                extra=extra,
            ))
            gap_counts[gap_kind] += 1
            continue

        mapped_fields: set[str] = set(pre_mapped_fields)
        target_vars = {payload} if payload else set()
        if deep and td.get("container_kind") in {"collection", "array", "map"}:
            target_vars.update(_collection_element_vars(body, payload, method_info=mi))
        simple_payload = bool(payload and re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", payload))
        # Inline saves such as repository.save(Entity.builder()...) should be matched
        # against the payload expression itself, not against every builder/constructor
        # in a large method.  Scanning the whole method for every inline save is both
        # slow and produces cross-product candidate mappings, especially in tests.
        if payload and not simple_payload:
            payload_syntax = _syntax_method_info_for_body(payload)
            all_bindings = (
                _builder_bindings_any_source(payload, payload_syntax)
                + (_constructor_bindings_for_type(payload, saved_object, written_field_names, collection_var=None) if deep else [])
            )
        else:
            bindings_key = (op, saved_object, tuple(written_field_names), payload or "")
            if bindings_key in all_bindings_cache:
                all_bindings = all_bindings_cache[bindings_key]
            else:
                all_bindings = (
                    _setter_bindings_any_source(body, mi)
                    + _builder_bindings_any_source(body, mi)
                    + _direct_assignment_bindings(mi)
                    + (_jooq_record_set_bindings(body, written_field_names) if deep else [])
                    + (_constructor_bindings_for_type(body, saved_object, written_field_names, collection_var=payload) if deep else [])
                    + (_helper_invocation_bindings(
                        caller_body=body,
                        caller_method=mi,
                        methods=methods,
                        saved_object=saved_object,
                        written_field_names=written_field_names,
                        collection_var=payload,
                        target_vars=target_vars,
                    ) if deep and simple_payload else [])
                )
                all_bindings_cache[bindings_key] = all_bindings
        # If payload is not a variable (for example mapper.toEntity(x)), local target var filtering is not useful.
        allow_unbound_target = bool(mapper_sig) or bool(payload and not simple_payload)
        for binding in all_bindings:
            target_var = str(binding.get("target_variable") or "")
            if target_var and target_vars and target_var not in target_vars and not allow_unbound_target:
                continue
            target_field = _canonical_field_name(str(binding.get("target_field") or ""), written_field_names)
            if not target_field or target_field not in set(written_field_names):
                continue
            mapped_fields.add(target_field)
            source_expr = str(binding.get("source_expression") or "")
            origin_info = _source_expr_to_origin(source_expr, method_info=mi, variable_origins=variable_origins, ingress_by_param=ingress_by_param)
            if origin_info.get("ultimate_origin_kind") in {"unknown", None}:
                deep_info = _resolve_expr_deep_origin(
                    source_expr,
                    target_field,
                    method_info=mi,
                    methods=methods,
                    schema_fields=schema_fields,
                    class_fields=class_fields,
                    class_infos=class_infos,
                    iface_impls=iface_impls,
                    root_ingress_by_param=ingress_by_param,
                    visited=set(),
                    depth=1,
                )
                if deep_info and deep_info.get("ultimate_origin_kind") not in {"unknown", None}:
                    origin_info = deep_info
            ultimate = str(origin_info.get("ultimate_origin_kind") or "unknown")
            source_kind = _technical_source_kind(ultimate)
            source_kind_counts[source_kind] += 1
            missing = list(origin_info.get("missing_links") or []) if ultimate == "unknown" else []
            if ultimate == "unknown" and not missing:
                missing = ["storage field assignment source was not resolved"]
            lineage_seq += 1
            facts.append(_source_to_storage_lineage_fact(
                f"source_to_storage_lineage_{lineage_seq:06d}",
                source_kind=source_kind,
                source_operation=origin_info.get("origin_operation"),
                source_payload=origin_info.get("origin_payload"),
                source_field=origin_info.get("origin_field"),
                source_field_role=_field_role(str(origin_info.get("origin_field") or target_field)),
                storage_operation=op,
                storage_call=f"{access.get('receiver_expression')}.{access.get('storage_method')}({access.get('payload_expression') or ''})",
                storage_method=str(access.get("storage_method") or "") or None,
                storage_access_id=str(access.get("storage_access_id") or "") or None,
                persistent_write_id=persistent_write_id,
                storage_target=access.get("table_or_repository"),
                storage_resolution_level=_storage_resolution_level_for_access(access),
                saved_object=saved_object,
                saved_object_field=target_field,
                storage_field=target_field,
                assignment_kind=_lineage_assignment_kind(str(binding.get("kind") or "")),
                assignment_expression=str(binding.get("expression") or ""),
                origin_expression=origin_info.get("origin_expression"),
                path=[*([str(origin_info.get("origin_expression"))] if origin_info.get("origin_expression") else []), f"{saved_object}.{target_field}", f"storage.{target_field}"],
                missing_links=missing,
                evidence_refs=[str(access.get("storage_access_id") or "")],
                evidence=evidence,
                source_container=origin_info.get("origin_container"),
                source_container_type=origin_info.get("origin_container_type"),
                source_element_type=origin_info.get("origin_element_type"),
                source_payload_parameter=origin_info.get("origin_payload_parameter"),
            ))
        if deep and source_candidate and not object_lineage_emitted and not mapped_fields:
            lineage_seq += 1
            obj_fact = _emit_object_level_lineage(
                lineage_id=f"source_to_storage_lineage_{lineage_seq:06d}",
                source_candidate=source_candidate,
                op=op,
                access=access,
                saved_object=saved_object,
                td=td,
                evidence=evidence,
                missing_links=["field_mapping_not_resolved"],
                persistent_write_id=persistent_write_id,
            )
            if obj_fact:
                facts.append(obj_fact)
                source_kind_counts[str(obj_fact.properties.get("source_kind") or "unknown")] += 1
                object_lineage_emitted = True
                key = _inspection_key("field_mapping_not_resolved", op, access, saved_object)
                if key not in source_inspection_keys:
                    source_inspection_keys.add(key)
                    source_inspection_seq += 1
                    facts.append(_source_inspection_request_fact(
                        f"source_inspection_request_{source_inspection_seq:06d}",
                        reason="field_mapping_not_resolved",
                        priority="high",
                        target_operation=op,
                        focus="Inspect how saved object/collection is populated before the storage call and confirm source-field to saved-field mappings if present.",
                        related_evidence_refs=[persistent_write_id, str(obj_fact.properties.get("source_to_storage_lineage_id") or ""), str(access.get("storage_access_id") or "")],
                        storage_access=access,
                        source_payload=str(obj_fact.properties.get("source_payload") or ""),
                        saved_object=saved_object,
                        trigger_blockers=["source_boundary:unresolved", "field_mapping:unresolved"],
                        evidence=evidence,
                        expected_observations=[
                            "Object/collection population code before storage call",
                            "Direct setters/builders/constructors/converters from source payload",
                            "Confirmed field pairs or explicit statement that mapping is not visible in this method",
                        ],
                        tokens=[payload, saved_object, str(obj_fact.properties.get("source_payload") or "")],
                    ))
        for field in written_field_names:
            if field in mapped_fields:
                continue
            gap_seq += 1
            facts.append(_storage_lineage_gap_fact(
                f"storage_lineage_gap_{gap_seq:06d}",
                gap_kind="field_mapping_not_resolved",
                storage_access=access,
                saved_object=saved_object,
                saved_object_field=field,
                reason="persistent write field exists, but assignment source was not resolved",
                missing_links=["field assignment not found", "mapper/builder/constructor may be unresolved"],
                evidence=evidence,
            ))
            gap_counts["field_mapping_not_resolved"] += 1
            key = _inspection_key("field_mapping_not_resolved", op, access, saved_object)
            if key not in source_inspection_keys:
                source_inspection_keys.add(key)
                source_inspection_seq += 1
                facts.append(_source_inspection_request_fact(
                    f"source_inspection_request_{source_inspection_seq:06d}",
                    reason="field_mapping_not_resolved",
                    priority="high",
                    target_operation=op,
                    focus="Inspect local assignments/builders/constructors feeding the saved payload field before the storage call.",
                    related_evidence_refs=[persistent_write_id, str(access.get("storage_access_id") or "")],
                    storage_access=access,
                    saved_object=saved_object,
                    saved_field=field,
                    trigger_blockers=["field_mapping:unresolved"],
                    evidence=evidence,
                    expected_observations=["Source expression for the saved field", "Whether value comes from method input, constant, computed value, or external/storage source"],
                    tokens=[payload, saved_object, field],
                ))


    return facts, {
        "source_kind_counts": source_kind_counts,
        "gap_counts": gap_counts,
        "access_kind_counts": access_kind_counts,
        "operation_kind_counts": operation_kind_counts,
        "promoted_custom_dao_mutation_count": promoted_custom_dao_mutation_count,
    }


def _java_persistence_lineage_status(
    ctx: _JavaPersistenceLineageContext,
    facts: list[Fact],
    *,
    write_phase_counts: dict[str, Any],
    access_side_counts: dict[str, Any],
) -> dict[str, Any]:
    maturity_level_counts = Counter(str((f.properties or {}).get("evidence_maturity_level") or "not_applicable") for f in facts)
    maturity_blocker_counts: Counter[str] = Counter()
    candidate_signal_type_counts: Counter[str] = Counter()
    for f in facts:
        props = f.properties or {}
        for blocker in props.get("evidence_maturity_blockers") or []:
            maturity_blocker_counts[str(blocker)] += 1
        for signal in props.get("candidate_signals") or []:
            if isinstance(signal, dict):
                candidate_signal_type_counts[str(signal.get("signal_type") or "unknown")] += 1

    source_kind_counts = write_phase_counts.get("source_kind_counts") or Counter()
    gap_counts = write_phase_counts.get("gap_counts") or Counter()
    access_kind_counts = write_phase_counts.get("access_kind_counts") or Counter()
    operation_kind_counts = write_phase_counts.get("operation_kind_counts") or Counter()
    return {
        "requested": True,
        "mode": "source_only_persistence_lineage_deep" if ctx.deep else "source_only_persistence_lineage",
        "deep": bool(ctx.deep),
        "files_scanned": len([x for x in ctx.files if x.suffix.lower() == ".java"]),
        "classes_indexed": len(ctx.class_infos),
        "methods_indexed": len(ctx.methods),
        "data_sources_extracted": sum(1 for f in facts if f.fact_type == "data_source"),
        "persistent_writes_extracted": sum(1 for f in facts if f.fact_type == "persistent_write"),
        "source_to_storage_lineages_extracted": sum(1 for f in facts if f.fact_type == "source_to_storage_lineage"),
        "storage_lineage_gaps_extracted": sum(1 for f in facts if f.fact_type == "storage_lineage_gap"),
        "read_from_storage_extracted": sum(1 for f in facts if f.fact_type == "read_from_storage"),
        "access_boundaries_extracted": sum(1 for f in facts if f.fact_type == "access_boundary"),
        "storage_to_access_lineages_extracted": sum(1 for f in facts if f.fact_type == "storage_to_access_lineage"),
        "stored_field_to_response_field_mappings_extracted": sum(1 for f in facts if f.fact_type == "stored_field_to_response_field_mapping"),
        "jooq_batch_bind_mappings_extracted": sum(1 for f in facts if f.fact_type == "jooq_batch_bind_mapping"),
        "jooq_parameterized_sql_mappings_extracted": sum(1 for f in facts if f.fact_type == "jooq_parameterized_sql_mapping"),
        "java_lineage_patterns_extracted": sum(1 for f in facts if f.fact_type == "java_lineage_pattern"),
        "spring_component_dependencies_extracted": sum(1 for f in facts if f.fact_type == "spring_component_dependency"),
        "template_method_dispatches_extracted": sum(1 for f in facts if f.fact_type == "template_method_dispatch"),
        "factory_method_mappings_extracted": sum(1 for f in facts if f.fact_type == "factory_method_mapping"),
        "builder_field_mappings_extracted": sum(1 for f in facts if f.fact_type == "builder_field_mapping"),
        "stream_collection_lineages_extracted": sum(1 for f in facts if f.fact_type == "stream_collection_lineage"),
        "mapstruct_mapper_signatures_extracted": sum(1 for f in facts if f.fact_type == "mapstruct_mapper_signature"),
        "mapstruct_field_mappings_extracted": sum(len((f.properties or {}).get("field_mappings") or []) for f in facts if f.fact_type == "mapstruct_mapper_signature"),
        "stored_data_access_counts": access_side_counts,
        "source_inspection_requests_extracted": sum(1 for f in facts if f.fact_type == "source_inspection_request"),
        "lineage_source_kind_counts": dict(sorted(source_kind_counts.items())),
        "gap_kind_counts": dict(sorted(gap_counts.items())),
        "storage_access_kind_counts": dict(sorted(access_kind_counts.items())),
        "storage_operation_kind_counts": dict(sorted(operation_kind_counts.items())),
        "promoted_custom_dao_mutation_count": int(write_phase_counts.get("promoted_custom_dao_mutation_count") or 0),
        "candidate_signal_type_counts": dict(sorted(candidate_signal_type_counts.items())),
        "evidence_maturity_level_counts": dict(sorted(maturity_level_counts.items())),
        "evidence_maturity_blocker_counts": dict(sorted(maturity_blocker_counts.items())),
        "evidence_maturity_model": {
            "policy": "strict_confirmed_vs_unresolved_candidate_signals_are_navigation_only",
            "levels": ["confirmed", "unresolved", "not_applicable"],
            "candidate_signal_policy": "candidate_signals are navigation hints with is_evidence=false; LLM must inspect source before using them as proof",
            "gap_lifecycle_policy": "decision-blocking actionable unresolved gaps must have source_inspection_required=true and linked source_inspection_request when a concrete target exists",
            "dimensions": ["persistence_write", "source_boundary", "field_mapping", "physical_storage", "end_to_end_trace"],
        },
        "warnings": ctx.warnings,
    }


def build_java_persistence_lineage_facts(
    files: list[Path],
    *,
    max_depth: int = 4,
    deep: bool = False,
    progress_path: Path | None = None,
    progress_interval: int = 100,
) -> tuple[list[Fact], dict[str, Any]]:
    """Build neutral technical evidence for source -> persistent storage lineage.

    `deep=False` is the quick source-only profile. `deep=True` keeps the same
    neutral semantics but uses more already-built indexes and emits more specific
    evidence around read/delete/update classification, collection element types,
    DAO/repository entity resolution and mapper-result saves. It still does not
    make any business/risk conclusion.
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
                "artifact": "java_persistence_lineage_progress",
                "status": status if status in {"done", "failed"} else "running",
                "current_phase": phase,
                "elapsed_ms": event["elapsed_ms"],
                "last_event": event,
                "events": phase_events[-80:],
            })

    try:
        progress("context", "running", {"file_count": len(files), "deep": deep})
        ctx = _build_java_persistence_lineage_context(files, deep=deep, progress=progress)
        progress("context", "done", {"method_count": len(ctx.methods), "storage_access_count": len(ctx.storage_accesses)})

        facts: list[Fact] = []

        progress("data_source_phase", "running", {"origin_count": len(ctx.origins)})
        data_source_facts = _data_source_phase(ctx)
        facts.extend(data_source_facts)
        progress("data_source_phase", "done", {"fact_count": len(data_source_facts)})

        progress("persistent_write_lineage_phase", "running", {"storage_access_count": len(ctx.storage_accesses)})
        write_facts, write_phase_counts = _persistent_write_lineage_phase(
            ctx, progress=progress, progress_interval=progress_interval
        )
        facts.extend(write_facts)
        progress("persistent_write_lineage_phase", "done", {"fact_count": len(write_facts), "counts": write_phase_counts})

        progress("observed_factory_physical_composition", "running", {"write_fact_count": len(write_facts)})
        composed_facts = _compose_observed_factory_to_physical_lineage_facts(ctx, write_facts)
        facts.extend(composed_facts)
        progress("observed_factory_physical_composition", "done", {"fact_count": len(composed_facts)})

        progress("standalone_mapping_hint_phase", "running")
        hint_facts = _standalone_mapping_hint_phase(ctx)
        facts.extend(hint_facts)
        progress("standalone_mapping_hint_phase", "done", {"fact_count": len(hint_facts)})

        progress("stored_data_access_phase", "running", {"storage_access_count": len(ctx.storage_accesses)})
        access_side_facts, access_side_counts = _build_stored_data_access_facts(ctx.methods, ctx.class_fields, ctx.storage_accesses, ctx.schema_fields, calls=ctx.calls)
        facts.extend(access_side_facts)
        progress("stored_data_access_phase", "done", {"fact_count": len(access_side_facts), "counts": access_side_counts})

        progress("source_inspection_links", "running", {"fact_count": len(facts)})
        _attach_source_inspection_links(facts)
        progress("source_inspection_links", "done", {"fact_count": len(facts)})

        progress("status_build", "running", {"fact_count": len(facts)})
        status = _java_persistence_lineage_status(ctx, facts, write_phase_counts=write_phase_counts, access_side_counts=access_side_counts)
        status["progress_events"] = phase_events
        status["elapsed_ms"] = int((time.perf_counter() - started) * 1000)
        progress("done", "done", {"fact_count": len(facts), "elapsed_ms": status["elapsed_ms"]})
        return facts, status
    except Exception as exc:
        progress("failed", "failed", {"error": str(exc)})
        raise

# --- Data-model-lineage fast technical facts ---------------------------------

def _repo_context(repo_id: str | None, project_code: str | None, system_name: str | None, repo_path: str | None = None) -> dict[str, Any]:
    fp_id = repo_id or (Path(repo_path).name if repo_path else None)
    return {
        "project_code": project_code or "UNKNOWN",
        "system_name": system_name or "unknown-system",
        "repo_id": repo_id or fp_id or "unknown-repo",
        "fp_id": fp_id or "unknown-fp",
        "repo_path": repo_path,
    }


def _container_kind_for_java(class_name: str, text: str = "", ann_window: str = "", annotations: Any = None, model_annotation_contracts: Any = None) -> str:
    low = class_name.lower()
    ann_names = {_annotation_simple_name(a) for a in (annotations or ())}
    meta_kind, _meta_annotation = _meta_model_annotation(annotations, model_annotation_contracts)
    if meta_kind:
        return meta_kind
    if {"Entity", "Table"} & ann_names:
        return "entity"
    if any(tok in low for tok in ["event", "message", "payload"]):
        return "event_payload"
    if any(tok in low for tok in ["request", "response", "dto", "rq", "rs"]):
        return "dto"
    if {"RestController", "Controller"} & ann_names or "@RestController" in ann_window or "@Controller" in ann_window:
        return "controller"
    if "Repository" in ann_names or low.endswith("repository") or low.endswith("repo") or low.endswith("dao"):
        return "repository"
    return "java_class"





_DEPENDENCY_TYPE_SUFFIXES = (
    "repository",
    "repo",
    "dao",
    "service",
    "gateway",
    "adapter",
    "client",
    "mapper",
    "converter",
    "template",
    "logger",
    "cache",
)


def _is_dependency_field_candidate(field: dict[str, Any]) -> bool:
    """Return whether a plain Java-class field has an infrastructure-role type.

    The observation filter intentionally relies on the declared type role, not on
    arbitrary substrings in the field name. A business field such as
    ``MergeClientInfo mergeClientInfo`` must remain observable, while types such
    as ``RemoteClient`` or ``CustomerRepository`` keep their existing dependency
    treatment.
    """
    declared_type = str(field.get("raw_type") or field.get("type") or "").strip()
    simple_type = _simple_type_name(declared_type).lower()
    return bool(simple_type) and simple_type.endswith(_DEPENDENCY_TYPE_SUFFIXES)

def _attribute_occurrence_fact(occ_id: str, *, ctx: dict[str, Any], container: dict[str, Any], field: dict[str, Any]) -> Fact:
    props = {
        "attribute_occurrence_id": occ_id,
        **ctx,
        "container_kind": container.get("container_kind"),
        "container_name": container.get("container_name"),
        "container_fqcn": container.get("fqcn"),
        "attribute_name": field.get("name"),
        "attribute_type": field.get("type"),
        "raw_type": field.get("raw_type"),
        "field_container_kind": field.get("container_kind"),
        "field_element_type": field.get("element_type"),
        "field_annotations": field.get("annotations") or [],
        "display_name": field.get("display_name"),
        "description": field.get("description"),
        "documentation_summary": field.get("documentation_summary"),
        "documentation_tags": field.get("documentation_tags") or {},
        "model_exclusion_observed": bool(field.get("model_exclusion_observed")),
        "model_exclusion_annotations": field.get("model_exclusion_annotations") or [],
        "attribute_role": field.get("role"),
        "source_path": container.get("source_path"),
        "source_scope": container.get("source_scope"),
        "model_annotation": container.get("model_annotation"),
        "line_start": field.get("line_start") or container.get("line_start"),
        "evidence_maturity_level": "confirmed",
        "evidence_maturity_dimensions": {"attribute_occurrence": "confirmed"},
    }
    return Fact(
        fact_type="attribute_occurrence",
        name=f"{container.get('container_name')}.{field.get('name')}",
        properties=props,
        evidence=[EvidenceRef(file_path=str(container.get("source_path")), line_start=field.get("line_start") or container.get("line_start"), extractor="java_data_model_lineage")],
    )








def _data_model_lineage_gap_fact(gap_id: str, *, ctx: dict[str, Any], gap_kind: str, operation: str | None, container: str | None, field: str | None, reason: str, missing_links: list[str], evidence: list[EvidenceRef], details: dict[str, Any] | None = None) -> Fact:
    props = {
        "data_model_lineage_gap_id": gap_id,
        **ctx,
        "gap_kind": gap_kind,
        "operation": operation,
        "container": container,
        "field": field,
        "reason": reason,
        "missing_links": missing_links,
        **(details or {}),
    }
    return Fact(
        fact_type="data_model_lineage_gap",
        name=f"{gap_kind}: {container or operation or 'unknown'} {field or ''}".strip(),
        properties=props,
        evidence=evidence,
    )









# --- v0.23.14 enhanced data-model-lineage helpers ---------------------------


_REPOSITORY_SUPERTYPES = {"JpaRepository", "CrudRepository", "PagingAndSortingRepository"}
_RELATIONSHIP_ANNOTATIONS = {"ManyToOne", "OneToMany", "OneToOne", "ManyToMany"}
# Known observable Java annotation contracts. These are project-neutral parser
# capabilities, not profile switches: callers may add annotation names through
# the analysis-profile stage options without changing scanner code.
# Project/domain annotation meanings must be supplied explicitly by an analysis
# profile. The generic core has no built-in project-specific annotation contracts.
_DEFAULT_MODEL_ANNOTATION_CONTRACTS: dict[str, str] = {}


def _normalized_model_annotation_contracts(raw: Any = None) -> dict[str, str]:
    contracts = dict(_DEFAULT_MODEL_ANNOTATION_CONTRACTS)
    if raw is None:
        return contracts
    if isinstance(raw, dict):
        items = raw.items()
    elif isinstance(raw, (list, tuple)):
        pairs: list[tuple[Any, Any]] = []
        for item in raw:
            if isinstance(item, dict):
                annotation = item.get("annotation") or item.get("name")
                model_kind = item.get("model_kind") or item.get("kind")
                pairs.append((annotation, model_kind))
        items = pairs
    else:
        raise ValueError("model_annotation_contracts must be a mapping or list of mappings")
    for annotation, model_kind in items:
        name = str(annotation or "").split(".")[-1].strip()
        kind = str(model_kind or "").strip()
        if not name or kind not in {"meta_entity", "meta_dictionary"}:
            raise ValueError(f"invalid model annotation contract: {annotation!r} -> {model_kind!r}")
        contracts[name] = kind
    return contracts


def _java_source_scope(path: str | Path | None) -> str:
    normalized = "/" + str(path or "").replace("\\", "/").strip("/").lower() + "/"
    if any(token in normalized for token in ("/src/test/", "/src/testfixtures/", "/src/integrationtest/", "/tests/", "/test/")):
        return "test_code"
    if any(token in normalized for token in ("/generated/", "/target/generated/", "/build/generated/")):
        return "generated_code"
    if "/src/main/" in normalized:
        return "production_code"
    return "unknown_code"


def _meta_model_annotation(annotations: Any, model_annotation_contracts: Any = None) -> tuple[str | None, str | None]:
    names = {_annotation_simple_name(a) for a in (annotations or ())}
    contracts = _normalized_model_annotation_contracts(model_annotation_contracts)
    for name in sorted(names):
        model_kind = contracts.get(name)
        if model_kind:
            return model_kind, name
    return None, None


def _annotation_simple_name(annotation: Any) -> str:
    return str(getattr(annotation, "name", "") or "").split(".")[-1]


def _unquote_annotation_value(value: str | None) -> str | None:
    return _ts_unquote_annotation_value(value)


def _annotation_args_map(annotation: Any) -> dict[str, str]:
    return _ts_annotation_args_map(getattr(annotation, "arguments", None))


def _annotation_arg_from_annotations(annotations: Any, annotation: str, arg: str = "name") -> str | None:
    expected = annotation.split(".")[-1]
    for ann in annotations or ():
        if _annotation_simple_name(ann) != expected:
            continue
        args = _annotation_args_map(ann)
        return _unquote_annotation_value(args.get(arg) or args.get("value"))
    return None


def _annotation_bool_arg_from_annotations(annotations: Any, annotation: str, arg: str) -> bool | None:
    expected = annotation.split(".")[-1]
    for ann in annotations or ():
        if _annotation_simple_name(ann) != expected:
            continue
        value = _annotation_args_map(ann).get(arg)
        if value is None:
            return None
        normalized = str(value).strip().lower()
        if normalized in {"true", "false"}:
            return normalized == "true"
    return None


def _has_annotation(annotations: Any, annotation: str) -> bool:
    expected = annotation.split(".")[-1]
    return any(_annotation_simple_name(ann) == expected for ann in annotations or ())


def _field_annotation_meta_from_annotations(annotations: Any, field_name: str) -> dict[str, Any]:
    storage_field = (
        _annotation_arg_from_annotations(annotations, "Column", "name")
        or _annotation_arg_from_annotations(annotations, "JoinColumn", "name")
        or field_name
    )
    referenced = _annotation_arg_from_annotations(annotations, "JoinColumn", "referencedColumnName")
    relationship_kind = next((ann for ann in _RELATIONSHIP_ANNOTATIONS if _has_annotation(annotations, ann)), None)
    if _has_annotation(annotations, "EmbeddedId"):
        key_role = "primary_key"
    elif _has_annotation(annotations, "Id"):
        key_role = "primary_key"
    elif _has_annotation(annotations, "JoinColumn") or relationship_kind:
        key_role = "foreign_key"
    elif field_name.lower() in {"id", "uuid"} or field_name.lower().endswith("id"):
        key_role = "business_key_signal"
    else:
        key_role = "attribute"
    return {
        "storage_field": storage_field,
        "java_field": field_name,
        "key_role": key_role,
        "nullable": _annotation_bool_arg_from_annotations(annotations, "Column", "nullable"),
        "unique": _annotation_bool_arg_from_annotations(annotations, "Column", "unique"),
        "relationship_kind": relationship_kind,
        "join_column": storage_field if (_has_annotation(annotations, "JoinColumn") or relationship_kind) else None,
        "referenced_column": referenced,
    }


def _repository_entity_from_super_type(super_type: str | None) -> str | None:
    raw = str(super_type or "").strip()
    if not raw:
        return None
    head = raw.split("<", 1)[0].strip().split()[-1].split(".")[-1]
    if head not in _REPOSITORY_SUPERTYPES:
        return None
    if "<" not in raw or ">" not in raw:
        return None
    inside = raw[raw.find("<") + 1: raw.rfind(">")]
    args = split_java_arguments(inside)
    if not args:
        return None
    return _simple_type_name(args[0])


def _repository_entity_types(files: list[Path]) -> dict[str, list[str]]:
    by_entity: dict[str, list[str]] = defaultdict(list)
    try:
        parsed_files, _warnings = parse_java_files(files)
    except Exception:
        parsed_files = []
    for parsed in parsed_files:
        for cls in parsed.classes:
            for super_type in getattr(cls, "super_types", ()) or ():
                entity = _repository_entity_from_super_type(super_type)
                if entity and cls.name not in by_entity[entity]:
                    by_entity[entity].append(cls.name)
    return dict(by_entity)


def _repository_type_to_entity_map(files: list[Path], *, class_infos: dict[str, dict[str, Any]] | None = None) -> dict[str, str]:
    mapping: dict[str, str] = {}
    # Prefer the already-built Tree-sitter class index.  Full combined runs execute
    # traceability before persistence; reparsing every Java file here can become a
    # second expensive syntax pass and has no additional evidence value.
    if class_infos:
        for class_name, info in sorted(class_infos.items()):
            super_types: list[Any] = []
            super_types.extend(info.get("interfaces") or [])
            if info.get("superclass"):
                super_types.append(info.get("superclass"))
            for super_type in super_types:
                entity = _repository_entity_from_super_type(str(super_type or ""))
                if entity:
                    mapping.setdefault(_simple_type_name(class_name), _simple_type_name(entity))
    else:
        for entity, repos in _repository_entity_types(files).items():
            for repo in repos:
                mapping[_simple_type_name(repo)] = _simple_type_name(entity)
    # Lightweight source-text fallback for repository generic signatures.  The
    # class index stores simple superclass/interface names and may not retain
    # generic entity arguments such as JpaRepository<ProfileEntity, String>.
    # This avoids a full second Tree-sitter parse while preserving entity mapping.
    repo_generic_pattern = re.compile(
        r"\b(?:interface|class)\s+(?P<repo>[A-Za-z_][A-Za-z0-9_]*)\s+[^{};]*?(?:extends|implements)\s+[^{};]*?(?:JpaRepository|CrudRepository|PagingAndSortingRepository|Repository)\s*<\s*(?P<entity>[A-Za-z_][A-Za-z0-9_.$]*)",
        re.DOTALL,
    )
    for p in [x for x in files if x.suffix.lower() == ".java"]:
        text = read_text(p)
        if "Repository" not in text and "JpaRepository" not in text and "CrudRepository" not in text:
            continue
        for m in repo_generic_pattern.finditer(text):
            mapping.setdefault(_simple_type_name(m.group("repo")), _simple_type_name(m.group("entity")))
    # Naming convention fallback: UcpPhoneDao -> UcpPhone, ProfileRepository -> Profile.
    for p in [x for x in files if x.suffix.lower() == ".java"]:
        cls = p.stem
        for suffix in ("Repository", "Dao", "DAO", "Mapper"):
            if cls.endswith(suffix) and len(cls) > len(suffix):
                mapping.setdefault(cls, cls[: -len(suffix)])
    return mapping

def _declared_receiver_type(receiver: str | None, mi: dict[str, Any], class_fields: dict[str, dict[str, str]]) -> str | None:
    if not receiver:
        return None
    if receiver in (mi.get("var_types") or {}):
        return _simple_type_name((mi.get("var_types") or {}).get(receiver))
    current_class = mi.get("class_name")
    if current_class and receiver in class_fields.get(current_class, {}):
        return _simple_type_name(class_fields[current_class].get(receiver))
    candidate = receiver[:1].upper() + receiver[1:] if receiver else ""
    return candidate or None


def _payload_type_details(payload: str | None, mi: dict[str, Any]) -> dict[str, Any]:
    payload = _clean_expression(payload)
    raw = None
    if payload:
        raw = (mi.get("raw_var_types") or {}).get(payload)
        if raw is None:
            raw = next((p.get("type") for p in mi.get("params") or [] if p.get("name") == payload), None)
    if not raw:
        raw = None
    return _java_type_details(raw)


def _simple_java_identifier(value: str | None) -> bool:
    value = _clean_expression(value)
    return bool(value and re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", value) and value not in CONTROL_WORDS)


def _syntax_for_body(body: str):
    return _synthetic_method_for_body(body or "")


def _method_info_syntax(mi: dict[str, Any], body: str | None = None) -> dict[str, Any]:
    cached = mi.get("_method_info_syntax_cache") if mi else None
    if isinstance(cached, dict):
        return cached
    if mi and any(mi.get(k) for k in ("method_calls", "syntax_assignments", "returns", "lambdas", "method_references")):
        mi["_method_info_syntax_cache"] = mi
        return mi
    method = _syntax_for_body(body or "") if "_syntax_for_body" in globals() else _synthetic_method_for_body(body or "")
    if not method:
        out = {"method_calls": [], "syntax_assignments": [], "returns": [], "lambdas": [], "method_references": []}
    else:
        out = method_syntax_dict(method)
    if mi is not None:
        mi["_method_info_syntax_cache"] = out
    return out


def _span_inside(item: dict[str, Any], outer: dict[str, Any]) -> bool:
    s = int(item.get("start_byte") or -1)
    e = int(item.get("end_byte") or -1)
    os = int(outer.get("start_byte") or -2)
    oe = int(outer.get("end_byte") or -2)
    return os <= s and e <= oe


def _collection_add_expressions_from_method(method_info: dict[str, Any], collection_var: str | None) -> list[str]:
    if not collection_var:
        return []
    out: list[str] = []
    for call in method_info.get("method_calls") or []:
        receiver = str(call.get("receiver") or "")
        method = str(call.get("method") or "")
        args = list(call.get("args") or [])
        if receiver == collection_var and method == "add" and args:
            out.append(_clean_expression(args[0]))
        elif receiver == "Collections" and method == "addAll" and args and _clean_expression(args[0]) == collection_var:
            out.extend(_clean_expression(a) for a in args[1:] if _clean_expression(a))
    return out


def _collection_stream_return_vars_from_method(method_info: dict[str, Any], collection_var: str | None) -> list[str]:
    """Return local vars that become elements of a saved collection via Tree-sitter stream/map syntax."""
    if not collection_var:
        return []
    out: set[str] = set()
    assignments = [a for a in (method_info.get("syntax_assignments") or []) if a.get("target") == collection_var]
    if not assignments:
        return []
    calls = method_info.get("method_calls") or []
    returns = method_info.get("returns") or []
    lambdas = method_info.get("lambdas") or []
    for assignment in assignments:
        streamish = any(_span_inside(c, assignment) and c.get("method") in {"stream", "map", "flatMap", "collect", "toList"} for c in calls)
        if not streamish:
            continue
        for ret in returns:
            if not _span_inside(ret, assignment):
                continue
            expr = _clean_expression(ret.get("expression"))
            if _simple_java_identifier(expr):
                out.add(expr)
        for lam in lambdas:
            if not _span_inside(lam, assignment):
                continue
            body_expr = _clean_expression(lam.get("body"))
            if _simple_java_identifier(body_expr):
                out.add(body_expr)
    return sorted(out)


def _collection_element_vars_from_method(method_info: dict[str, Any], collection_var: str | None) -> list[str]:
    if not collection_var:
        return []
    out: list[str] = []
    for expr in _collection_add_expressions_from_method(method_info, collection_var):
        if _simple_java_identifier(expr):
            out.append(expr)
    out.extend(_collection_stream_return_vars_from_method(method_info, collection_var))
    return sorted(set(out))


def _collection_element_vars(body: str, collection_var: str | None, method_info: dict[str, Any] | None = None) -> list[str]:
    return _collection_element_vars_from_method(_method_info_syntax(method_info or {}, body), collection_var)



def _call_signature_from_expression(expr: str) -> tuple[str | None, list[str], str]:
    """Extract the outer call from an expression using Tree-sitter syntax."""
    method = _syntax_for_body(f"__x({expr});")
    if not method or not method.calls:
        return None, [], _clean_expression(expr)
    # The wrapper call is __x(...); choose the first real call that appears inside the argument.
    calls = [c for c in method.calls if c.method != "__x"]
    if not calls:
        return None, [], _clean_expression(expr)
    call = calls[0]
    return str(call.method or ""), list(call.args or []), _clean_expression(call.text)


def _method_name_from_call(expr: str) -> tuple[str | None, list[str]]:
    method, args, _text_value = _call_signature_from_expression(expr)
    return method, args


def _collection_add_expressions(body: str, collection_var: str | None, method_info: dict[str, Any] | None = None) -> list[str]:
    return _collection_add_expressions_from_method(_method_info_syntax(method_info or {}, body), collection_var)


def _stream_mapper_invocations_from_method(method_info: dict[str, Any], assignment: dict[str, Any]) -> list[tuple[str | None, str, list[str], str]]:
    """Find helper invocations used as stream map functions inside one assignment."""
    out: list[tuple[str | None, str, list[str], str]] = []
    calls = method_info.get("method_calls") or []
    lambdas = method_info.get("lambdas") or []
    method_refs = method_info.get("method_references") or []
    for call in calls:
        if not _span_inside(call, assignment) or call.get("method") not in {"map", "flatMap"}:
            continue
        args = list(call.get("args") or [])
        if not args:
            continue
        first_arg = _clean_expression(args[0])
        if "::" in first_arg:
            method = first_arg.rsplit("::", 1)[-1].strip()
            if method:
                out.append((None, method, [], first_arg))
            continue
        refs = [r for r in method_refs if _span_inside(r, call)]
        for ref in refs:
            method = str(ref.get("method") or "")
            if method:
                out.append((None, method, [], str(ref.get("text") or method)))
        lambda_spans = [l for l in lambdas if _span_inside(l, call)]
        for lam in lambda_spans:
            inner_calls = [c for c in calls if _span_inside(c, lam) and c.get("method") not in {"stream", "map", "flatMap", "collect", "toList"}]
            for inner in inner_calls:
                method = str(inner.get("method") or "")
                if method:
                    out.append((None, method, list(inner.get("args") or []), _clean_expression(inner.get("text"))))
    return out


def _constructor_invocations(body: str, target_type: str | None = None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    method = _syntax_for_body(body or "")
    if not method:
        return out
    for creation in method.object_creations:
        typ = _simple_type_name(creation.type)
        if target_type and typ != _simple_type_name(target_type):
            continue
        out.append({
            "type": typ,
            "args": list(creation.args),
            "expression": _clean_expression(creation.text),
            "start": creation.start_byte,
            "end": creation.end_byte,
        })
    return out


def _constructor_bindings_for_type(body: str, target_type: str | None, field_names: list[str], *, collection_var: str | None = None) -> list[dict[str, Any]]:
    """Best-effort constructor argument -> target field bindings from Tree-sitter object creation nodes."""
    target = _simple_type_name(target_type)
    if not target or target == "unknown" or not field_names:
        return []
    out: list[dict[str, Any]] = []
    for inv in _constructor_invocations(body or "", target):
        for idx, arg in enumerate(inv.get("args") or []):
            if idx >= len(field_names):
                continue
            out.append({
                "kind": "constructor_arg",
                "target_variable": None,
                "target_type": target,
                "target_field": field_names[idx],
                "target_index": idx,
                "source_expression": _clean_expression(arg),
                "expression": str(inv.get("expression") or ""),
            })
    return out



def _resolve_helper_method(method_name: str | None, *, caller: dict[str, Any], methods: dict[str, dict[str, Any]], target_type: str | None = None) -> dict[str, Any] | None:
    if not method_name:
        return None
    same_class_key = f"{caller.get('class_name')}.{method_name}"
    candidates: list[dict[str, Any]] = []
    if same_class_key in methods:
        candidates.append(methods[same_class_key])
    for op, mi in methods.items():
        if op == same_class_key:
            continue
        if mi.get("method_name") == method_name:
            candidates.append(mi)
    if target_type:
        target = _simple_type_name(target_type)
        typed = [mi for mi in candidates if _simple_type_name(mi.get("return_type")) == target]
        if typed:
            return typed[0]
    return candidates[0] if candidates else None


def _return_target_vars(body: str, method_info: dict[str, Any] | None = None) -> set[str]:
    out: set[str] = set()
    syntax = _method_info_syntax(method_info or {}, body)
    for ret in syntax.get("returns") or []:
        e = _clean_expression(ret.get("expression"))
        if _simple_java_identifier(e):
            out.add(e)
    return out


def _helper_invocation_bindings(
    *,
    caller_body: str,
    caller_method: dict[str, Any],
    methods: dict[str, dict[str, Any]],
    saved_object: str | None,
    written_field_names: list[str],
    collection_var: str | None,
    target_vars: set[str],
) -> list[dict[str, Any]]:
    """Resolve one-hop helper/converter methods that create saved collection elements.

    The builder already resolves local setters/constructors. This extends it to
    common source-only shapes where a collection payload contains objects returned
    from a helper method, e.g. `toAdd.add(toRecord(rq))` or
    `UcpPhone_2Record rec = toRecord(rq); toAdd.add(rec);`.
    """
    if not saved_object or saved_object == "unknown":
        return []
    relevant_calls: list[tuple[str | None, str, list[str], str]] = []
    caller_syntax = _method_info_syntax(caller_method, caller_body)

    # Inline collection.add(helper(args)).
    for add_expr in _collection_add_expressions(caller_body, collection_var, method_info=caller_syntax):
        method, args = _method_name_from_call(add_expr)
        if method:
            relevant_calls.append((None, method, args, add_expr))

    # Local variable assigned from helper(args) and later added to the saved collection.
    for assignment in caller_syntax.get("syntax_assignments") or []:
        if assignment.get("assignment_kind") != "variable_declaration":
            continue
        var = str(assignment.get("target") or "")
        if target_vars and var not in target_vars:
            continue
        expr = str(assignment.get("expression") or "")
        method, args = _method_name_from_call(expr)
        if method:
            relevant_calls.append((var, method, args, expr))

    # Stream/collect assignment to the saved collection with .map(this::toRecord) or .map(rq -> toRecord(rq)).
    if collection_var:
        for assignment in caller_syntax.get("syntax_assignments") or []:
            if assignment.get("target") != collection_var:
                continue
            relevant_calls.extend(_stream_mapper_invocations_from_method(caller_syntax, assignment))

    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for result_var, method, args, call_expr in relevant_calls:
        helper = _resolve_helper_method(method, caller=caller_method, methods=methods, target_type=saved_object)
        if not helper or helper is caller_method:
            continue
        params = helper.get("params") or []
        arg_map = {str(p.get("name")): _clean_expression(args[i]) for i, p in enumerate(params) if p.get("name") and i < len(args)}
        # Method references do not expose the lambda variable in the call expression. Keep
        # helper formal names as-is; origin resolution may still resolve params if names match
        # caller lambda/loop variables elsewhere.
        helper_body = helper.get("body") or ""
        helper_return_vars = _return_target_vars(helper_body, helper)
        helper_bindings = (
            _setter_bindings_any_source(helper_body, helper)
            + _builder_bindings_any_source(helper_body, helper)
            + _direct_assignment_bindings(helper)
            + _jooq_record_set_bindings(helper_body, written_field_names)
            + _constructor_bindings_for_type(helper_body, saved_object, written_field_names)
        )
        for b in helper_bindings:
            target_var = str(b.get("target_variable") or "")
            if target_var and helper_return_vars and target_var not in helper_return_vars:
                continue
            field = _canonical_field_name(str(b.get("target_field") or ""), written_field_names)
            if not field or field not in set(written_field_names):
                continue
            source_expr = _substitute_java_symbols(str(b.get("source_expression") or ""), arg_map)
            if not source_expr:
                continue
            key = (field, source_expr, str(b.get("expression") or call_expr))
            if key in seen:
                continue
            seen.add(key)
            out.append({
                **b,
                "kind": f"helper_{b.get('kind')}",
                "target_variable": result_var,
                "target_field": field,
                "source_expression": source_expr,
                "expression": f"{_clean_expression(call_expr)} -> {_clean_expression(str(b.get('expression') or ''))}",
                "helper_operation": helper.get("operation"),
            })
    return out


def _collection_source_candidate(
    body: str,
    *,
    collection_var: str | None,
    method_info: dict[str, Any],
    ingress_by_param: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    """Find the best object-level source for a saved collection.

    This intentionally produces object-level evidence, not a business decision.
    Preference order:
    1. input parameter referenced in collection.add/new/builder expressions;
    2. any single payload-origin parameter referenced in the method body;
    3. any single method parameter when there is only one plausible payload.
    """
    add_exprs = _collection_add_expressions(body, collection_var, method_info=method_info)
    search_text = "\n".join(add_exprs) if add_exprs else (body or "")
    params = method_info.get("params") or []
    by_name = {str(p.get("name")): p for p in params if p.get("name")}
    candidates: list[dict[str, Any]] = []
    for name, param in by_name.items():
        if not name or not _contains_symbol(search_text, name):
            continue
        origin = ingress_by_param.get(name)
        source_kind = _technical_source_kind(_source_boundary_for_origin(origin)) if origin else "method_input"
        if origin:
            source_kind = _technical_source_kind(_source_boundary_for_origin(origin))
        details = _java_type_details(param.get("type"))
        source_payload = details.get("element_type") if details.get("container_kind") else _simple_type_name(param.get("type"))
        candidates.append({
            "source_payload_parameter": name,
            "source_payload": source_payload,
            "source_container": name if details.get("container_kind") else None,
            "source_container_type": details.get("type") if details.get("container_kind") else None,
            "source_element_type": details.get("element_type"),
            "source_kind": source_kind,
            "source_operation": origin.get("operation") if origin else method_info.get("operation"),
            "origin_expression": name,
            "trace_status": "confirmed" if origin else "unresolved",
            "resolution_kind": "ingress_param_reference" if origin else "method_input_reference",
            "missing_links": [] if origin else ["source_kind_not_confirmed"],
        })
    if candidates:
        # Prefer known ingress/source params over method-input-only hints.
        candidates.sort(key=lambda x: (0 if x.get("source_kind") == "method_input" else 1, 1 if x.get("trace_status") == "confirmed" else 0), reverse=True)
        return candidates[0]
    ingress_candidates = []
    for name, origin in ingress_by_param.items():
        if name and _contains_symbol(body or "", name):
            param = by_name.get(name, {})
            details = _java_type_details(param.get("type"))
            ingress_candidates.append({
                "source_payload_parameter": name,
                "source_payload": details.get("element_type") or _simple_type_name(origin.get("payload_type")),
                "source_container": name if details.get("container_kind") else None,
                "source_container_type": details.get("type") if details.get("container_kind") else None,
                "source_element_type": details.get("element_type"),
                "source_kind": _technical_source_kind(_source_boundary_for_origin(origin)),
                "source_operation": origin.get("operation"),
                "origin_expression": name,
                "trace_status": "confirmed",
                "resolution_kind": "ingress_param_reference",
                "missing_links": [],
            })
    if len(ingress_candidates) == 1:
        return ingress_candidates[0]
    payload_like = [p for p in params if _simple_type_name(p.get("type")) not in {"String", "Long", "Integer", "Boolean", "int", "long", "boolean"}]
    if len(payload_like) == 1:
        p0 = payload_like[0]
        details = _java_type_details(p0.get("type"))
        return {
            "source_payload_parameter": p0.get("name"),
            "source_payload": details.get("element_type") or _simple_type_name(p0.get("type")),
            "source_container": p0.get("name") if details.get("container_kind") else None,
            "source_container_type": details.get("type") if details.get("container_kind") else None,
            "source_element_type": details.get("element_type"),
            "source_kind": "method_input",
            "source_operation": method_info.get("operation"),
            "origin_expression": p0.get("name"),
            "trace_status": "unresolved",
            "resolution_kind": "single_payload_like_parameter_hint",
            "missing_links": ["source_kind_not_confirmed", "source_field_not_resolved"],
        }
    return None


def _emit_object_level_lineage(
    *,
    lineage_id: str,
    source_candidate: dict[str, Any] | None,
    op: str,
    access: dict[str, Any],
    saved_object: str,
    td: dict[str, Any],
    evidence: list[EvidenceRef],
    missing_links: list[str] | None = None,
    persistent_write_id: str | None = None,
) -> Fact | None:
    if not source_candidate:
        return None
    missing = list(missing_links or [])
    missing.extend([m for m in source_candidate.get("missing_links") or [] if m not in missing])
    if "field_mapping_not_resolved" not in missing:
        missing.append("field_mapping_not_resolved")
    if "storage_field_not_resolved" not in missing:
        missing.append("storage_field_not_resolved")
    return _source_to_storage_lineage_fact(
        lineage_id,
        source_kind=str(source_candidate.get("source_kind") or "method_input"),
        source_operation=source_candidate.get("source_operation") or op,
        source_payload=source_candidate.get("source_payload"),
        source_field=None,
        source_field_role="object",
        storage_operation=op,
        storage_call=f"{access.get('receiver_expression')}.{access.get('storage_method')}({access.get('payload_expression') or ''})",
        storage_method=str(access.get("storage_method") or "") or None,
        storage_access_id=str(access.get("storage_access_id") or "") or None,
        persistent_write_id=persistent_write_id,
        storage_target=access.get("table_or_repository"),
        storage_resolution_level=_storage_resolution_level_for_access(access),
        saved_object=saved_object,
        saved_object_field=None,
        storage_field=None,
        assignment_kind="collection_payload" if td.get("container_kind") else "object_payload",
        assignment_expression=str(access.get("payload_expression") or ""),
        origin_expression=source_candidate.get("origin_expression"),
        path=[
            str(source_candidate.get("source_payload") or source_candidate.get("source_payload_parameter") or "source"),
            str(access.get("payload_expression") or "payload"),
            str(saved_object or "saved_object"),
            f"{access.get('receiver_expression')}.{access.get('storage_method')}",
        ],
        missing_links=missing,
        evidence_refs=[str(access.get("storage_access_id") or "")],
        evidence=evidence,
        lineage_level="collection_element" if td.get("container_kind") in {"collection", "array", "map"} else "object",
        source_container=source_candidate.get("source_container"),
        source_container_type=source_candidate.get("source_container_type"),
        source_element_type=source_candidate.get("source_element_type"),
        saved_container=str(access.get("payload_expression") or "") or None,
        saved_container_type=td.get("type") if td.get("container_kind") else None,
        saved_element_type=td.get("element_type"),
        source_payload_parameter=source_candidate.get("source_payload_parameter"),
    )


def _storage_gap_for_non_write(access: dict[str, Any]) -> tuple[str, str, list[str], float]:
    kind = str(access.get("operation_kind") or access.get("access_kind") or "unknown")
    if kind == "read" or access.get("access_kind") == "read":
        return "storage_operation_is_read", "storage access is a read/query operation, not a persistent write of a payload", ["not a persistent write", "payload role is filter/read key"], 0.70
    if kind == "delete":
        return "storage_operation_is_delete", "storage access deletes/removes data or links by key; payload is not a saved object", ["not a saved payload", "payload role is delete_key"], 0.72
    if kind in {"update", "mutation"} or access.get("access_kind") == "mutation":
        return "persistent_mutation_by_key", "storage access mutates existing records; arguments may be keys/status values rather than a saved object", ["not confirmed saved payload", "mutation field mapping not assessed"], 0.62
    return "storage_operation_not_a_confirmed_write", "storage access is not a confirmed payload write", ["operation kind not classified as write"], 0.50




def _substitute_java_type(value: Any, substitutions: dict[str, str]) -> str:
    """Replace exact Java identifier tokens in Tree-sitter-derived type text."""
    text = str(value or "").strip()
    if not text or not substitutions:
        return text
    out: list[str] = []
    pos = 0
    while pos < len(text):
        ch = text[pos]
        if ch.isalpha() or ch in {"_", "$"}:
            end = pos + 1
            while end < len(text) and (text[end].isalnum() or text[end] in {"_", "$"}):
                end += 1
            token = text[pos:end]
            out.append(str(substitutions.get(token, token)))
            pos = end
        else:
            out.append(ch)
            pos += 1
    return "".join(out)

def _java_type_declaration_and_inheritance_facts(
    files: list[Path], *, ctx: dict[str, Any]
) -> tuple[list[Fact], dict[str, Any]]:
    """Publish a repository-wide Java type graph from Tree-sitter declarations.

    This is a structural facts-only graph. Resolution records the lexical basis used
    to connect a child declaration to an observed parent declaration. Missing or
    ambiguous parents are retained instead of being dropped.
    """
    parsed_files, warnings = parse_java_files(files)
    declarations: list[dict[str, Any]] = []
    for parsed in parsed_files:
        for cls in parsed.classes:
            fqcn = f"{parsed.package}.{cls.name}" if parsed.package else cls.name
            declarations.append({
                "fqcn": fqcn,
                "simple_name": cls.name,
                "package_name": parsed.package,
                "class_kind": cls.kind,
                "modifiers": cls.modifiers,
                "is_abstract": "abstract" in set(cls.modifier_tokens or ()),
                "annotations": sorted({_annotation_simple_name(a) for a in cls.annotations or () if _annotation_simple_name(a)}),
                "display_name": (cls.documentation or {}).get("display_name"),
                "description": (cls.documentation or {}).get("description"),
                "documentation_summary": (cls.documentation or {}).get("summary"),
                "documentation_tags": (cls.documentation or {}).get("tags") or {},
                "extends": str(cls.extends_base or "").strip(),
                "extends_raw": str(cls.extends or "").strip(),
                "extends_type_arguments": list(cls.extends_type_arguments or ()),
                "implements": [str(x).strip() for x in cls.implements_bases or () if str(x).strip()],
                "implements_raw": [str(x).strip() for x in cls.implements or () if str(x).strip()],
                "implements_type_arguments": [list(x) for x in cls.implements_type_arguments or ()],
                "type_parameters": list(cls.type_parameters or ()),
                "imports": list(parsed.imports or ()),
                "source_path": str(parsed.file),
                "source_scope": _java_source_scope(parsed.file),
                "line_start": cls.line_start,
                "line_end": cls.line_end,
            })
    declarations.sort(key=lambda x: (str(x.get("fqcn")), str(x.get("source_path")), int(x.get("line_start") or 0)))

    by_fqcn: dict[str, dict[str, Any]] = {}
    by_simple: dict[str, list[str]] = defaultdict(list)
    for decl in declarations:
        fqcn = str(decl["fqcn"])
        by_fqcn.setdefault(fqcn, decl)
        by_simple[str(decl["simple_name"])].append(fqcn)
    for values in by_simple.values():
        values.sort()

    def resolve(reference: str, child: dict[str, Any]) -> dict[str, Any]:
        raw = str(reference or "").strip()
        simple = raw.rsplit(".", 1)[-1]
        if not raw:
            return {"resolution_kind": "unresolved", "candidate_parent_fqcns": []}
        if raw in by_fqcn:
            return {"resolution_kind": "exact_fqcn", "resolved_parent_fqcn": raw, "candidate_parent_fqcns": [raw]}
        package = str(child.get("package_name") or "")
        same_package = f"{package}.{simple}" if package else simple
        if same_package in by_fqcn:
            return {"resolution_kind": "same_package", "resolved_parent_fqcn": same_package, "candidate_parent_fqcns": [same_package]}
        explicit: list[str] = []
        wildcard: list[str] = []
        for imp in child.get("imports") or []:
            imp_text = str(imp or "").strip()
            if imp_text.startswith("static "):
                continue
            if imp_text.endswith(".*"):
                candidate = f"{imp_text[:-2]}.{simple}"
                if candidate in by_fqcn:
                    wildcard.append(candidate)
            elif imp_text.rsplit(".", 1)[-1] == simple and imp_text in by_fqcn:
                explicit.append(imp_text)
            elif f"{imp_text}.{simple}" in by_fqcn:
                # java_syntax normalizes wildcard imports to the package name.
                wildcard.append(f"{imp_text}.{simple}")
        explicit = sorted(set(explicit))
        wildcard = sorted(set(wildcard))
        if len(explicit) == 1:
            return {"resolution_kind": "explicit_import", "resolved_parent_fqcn": explicit[0], "candidate_parent_fqcns": explicit}
        if len(explicit) > 1:
            return {"resolution_kind": "ambiguous", "candidate_parent_fqcns": explicit}
        if len(wildcard) == 1:
            return {"resolution_kind": "wildcard_import", "resolved_parent_fqcn": wildcard[0], "candidate_parent_fqcns": wildcard}
        if len(wildcard) > 1:
            return {"resolution_kind": "ambiguous", "candidate_parent_fqcns": wildcard}
        candidates = list(by_simple.get(simple) or [])
        if len(candidates) == 1:
            return {"resolution_kind": "unique_simple_name", "resolved_parent_fqcn": candidates[0], "candidate_parent_fqcns": candidates}
        return {"resolution_kind": "ambiguous" if candidates else "unresolved", "candidate_parent_fqcns": candidates}

    edges: list[dict[str, Any]] = []
    for child in declarations:
        refs: list[tuple[str, str, str]] = []
        if child.get("extends"):
            refs.append(("extends", str(child["extends"]), str(child.get("extends_raw") or child["extends"]), list(child.get("extends_type_arguments") or [])))
        impl_raw = list(child.get("implements_raw") or [])
        impl_args = list(child.get("implements_type_arguments") or [])
        for pos, value in enumerate(child.get("implements") or []):
            refs.append(("implements", str(value), str(impl_raw[pos] if pos < len(impl_raw) else value), list(impl_args[pos] if pos < len(impl_args) else [])))
        for relation_kind, reference, declared_parent_type, declared_parent_args in refs:
            resolution = resolve(reference, child)
            edges.append({
                "child_fqcn": child["fqcn"],
                "child_simple_name": child["simple_name"],
                "relation_kind": relation_kind,
                "declared_parent_reference": reference,
                "declared_parent_type": declared_parent_type,
                "declared_parent_type_arguments": declared_parent_args,
                **resolution,
                "source_path": child["source_path"],
                "source_scope": child["source_scope"],
                "line_start": child["line_start"],
                "line_end": child["line_end"],
            })

    # Mark only mechanically observed cycles among resolved repository declarations.
    adjacency: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        parent = edge.get("resolved_parent_fqcn")
        if parent:
            adjacency[str(edge["child_fqcn"])].append(str(parent))
    cycle_nodes: set[str] = set()
    visiting: list[str] = []
    state: dict[str, int] = {}
    def visit(node: str) -> None:
        state[node] = 1
        visiting.append(node)
        for parent in adjacency.get(node, []):
            if state.get(parent, 0) == 0:
                visit(parent)
            elif state.get(parent) == 1 and parent in visiting:
                cycle_nodes.update(visiting[visiting.index(parent):])
        visiting.pop()
        state[node] = 2
    for node in sorted(by_fqcn):
        if state.get(node, 0) == 0:
            visit(node)

    facts: list[Fact] = []
    for idx, decl in enumerate(declarations, 1):
        facts.append(Fact(
            fact_type="java_type_declaration",
            name=str(decl["fqcn"]),
            properties={
                "java_type_declaration_id": f"java_type_declaration_{idx:06d}",
                **ctx,
                **{k: v for k, v in decl.items() if k != "imports"},
                "declared_imports": decl.get("imports") or [],
                "cycle_observed": str(decl["fqcn"]) in cycle_nodes,
                "evidence_maturity_level": "confirmed",
                "syntax_provider": "tree_sitter",
            },
            evidence=[EvidenceRef(file_path=str(decl["source_path"]), line_start=decl.get("line_start"), line_end=decl.get("line_end"), extractor="java_tree_sitter_type_declaration")],
        ))
    for idx, edge in enumerate(edges, 1):
        facts.append(Fact(
            fact_type="java_inheritance_observation",
            name=f"{edge['child_fqcn']} {edge['relation_kind']} {edge['declared_parent_reference']}",
            properties={
                "java_inheritance_observation_id": f"java_inheritance_observation_{idx:06d}",
                **ctx,
                **edge,
                "resolved": bool(edge.get("resolved_parent_fqcn")),
                "cycle_observed": str(edge["child_fqcn"]) in cycle_nodes and str(edge.get("resolved_parent_fqcn") or "") in cycle_nodes,
                "evidence_maturity_level": "confirmed",
                "syntax_provider": "tree_sitter",
            },
            evidence=[EvidenceRef(file_path=str(edge["source_path"]), line_start=edge.get("line_start"), line_end=edge.get("line_end"), extractor="java_tree_sitter_inheritance")],
        ))
    status = {
        "java_type_declarations_extracted": len(declarations),
        "java_inheritance_observations_extracted": len(edges),
        "java_inheritance_resolved": sum(1 for x in edges if x.get("resolved_parent_fqcn")),
        "java_inheritance_unresolved": sum(1 for x in edges if x.get("resolution_kind") == "unresolved"),
        "java_inheritance_ambiguous": sum(1 for x in edges if x.get("resolution_kind") == "ambiguous"),
        "java_inheritance_cycle_nodes": len(cycle_nodes),
        "java_type_parse_warnings": len(warnings),
    }
    return facts, status


def _effective_entity_field_facts(
    containers: list[dict[str, Any]], inheritance_facts: list[Fact], *, ctx: dict[str, Any]
) -> tuple[list[Fact], dict[str, Any]]:
    """Project declared fields through resolved class inheritance for entity types."""
    container_by_fqcn = {str(c.get("fqcn") or ""): c for c in containers if c.get("fqcn")}
    extends_edge: dict[str, dict[str, Any]] = {}
    declaration_by_fqcn: dict[str, dict[str, Any]] = {}
    for fact in inheritance_facts:
        p = fact.properties or {}
        if fact.fact_type == "java_type_declaration" and p.get("fqcn"):
            declaration_by_fqcn[str(p["fqcn"])] = p
        elif fact.fact_type == "java_inheritance_observation" and p.get("relation_kind") == "extends" and p.get("child_fqcn"):
            extends_edge[str(p["child_fqcn"])] = p

    target_kinds = {"entity", "meta_entity", "meta_dictionary"}
    facts: list[Fact] = []
    exclusion_annotation_count = 0
    inherited_count = 0
    direct_count = 0
    unresolved_paths = 0
    seq = 0

    for owner in sorted(containers, key=lambda x: str(x.get("fqcn") or "")):
        owner_fqcn = str(owner.get("fqcn") or "")
        if not owner_fqcn or str(owner.get("container_kind") or "") not in target_kinds or str(owner.get("source_scope") or "") == "test_code":
            continue
        chain: list[tuple[str, dict[str, str]]] = [(owner_fqcn, {})]
        visited = {owner_fqcn}
        current = owner_fqcn
        substitutions: dict[str, str] = {}
        while current in extends_edge:
            edge = extends_edge[current]
            parent = str(edge.get("resolved_parent_fqcn") or "")
            if not parent or parent in visited:
                unresolved_paths += 1
                break
            child_decl = declaration_by_fqcn.get(current) or {}
            parent_decl = declaration_by_fqcn.get(parent) or {}
            parent_params = list(parent_decl.get("type_parameters") or [])
            raw_args = list(edge.get("declared_parent_type_arguments") or [])
            resolved_args = [_substitute_java_type(arg, substitutions) for arg in raw_args]
            next_substitutions = dict(substitutions)
            for param, arg in zip(parent_params, resolved_args):
                next_substitutions[str(param)] = str(arg)
            substitutions = next_substitutions
            chain.append((parent, dict(substitutions)))
            visited.add(parent)
            current = parent

        seen_names: set[str] = set()
        for depth, (declared_in_fqcn, subst) in enumerate(chain):
            source = container_by_fqcn.get(declared_in_fqcn)
            if not source:
                continue
            path = [fqcn for fqcn, _ in chain[: depth + 1]]
            for field in source.get("fields") or []:
                field_name = str(field.get("name") or "")
                if not field_name or field_name in seen_names:
                    continue
                seen_names.add(field_name)
                model_exclusion_annotations = list(field.get("model_exclusion_annotations") or [])
                model_exclusion_observed = bool(model_exclusion_annotations)
                exclusion_annotation_count += int(model_exclusion_observed)
                raw_type = str(field.get("raw_type") or field.get("type") or "")
                effective_type = _substitute_java_type(raw_type, subst)
                seq += 1
                inherited = depth > 0
                inherited_count += int(inherited)
                direct_count += int(not inherited)
                facts.append(Fact(
                    fact_type="effective_entity_field",
                    name=f"{owner_fqcn}.{field_name}",
                    properties={
                        "effective_entity_field_id": f"effective_entity_field_{seq:06d}",
                        **ctx,
                        "effective_owner_fqcn": owner_fqcn,
                        "effective_owner_name": owner.get("container_name"),
                        "effective_owner_kind": owner.get("container_kind"),
                        "field_name": field_name,
                        "declared_type": raw_type,
                        "effective_type": effective_type,
                        "field_container_kind": field.get("container_kind"),
                        "field_element_type": _substitute_java_type(field.get("element_type"), subst),
                        "declared_in_fqcn": declared_in_fqcn,
                        "declared_in_name": source.get("container_name"),
                        "association_origin": "inherited_field" if inherited else "direct_field",
                        "inherited": inherited,
                        "inheritance_depth": depth,
                        "inheritance_path": path,
                        "field_annotations": field.get("annotations") or [],
                        "display_name": field.get("display_name"),
                        "description": field.get("description"),
                        "documentation_summary": field.get("documentation_summary"),
                        "documentation_tags": field.get("documentation_tags") or {},
                        "model_exclusion_observed": model_exclusion_observed,
                        "model_exclusion_annotations": model_exclusion_annotations,
                        "source_path": source.get("source_path"),
                        "source_scope": source.get("source_scope"),
                        "line_start": field.get("line_start"),
                        "line_end": field.get("line_end"),
                        "evidence_maturity_level": "confirmed",
                        "syntax_provider": "tree_sitter",
                    },
                    evidence=[EvidenceRef(file_path=str(source.get("source_path")), line_start=field.get("line_start"), line_end=field.get("line_end"), extractor="java_effective_entity_field")],
                ))
    status = {
        "effective_entity_fields_extracted": len(facts),
        "effective_entity_fields_direct": direct_count,
        "effective_entity_fields_inherited": inherited_count,
        "effective_entity_fields_excluded": 0,
        "effective_entity_fields_with_model_exclusion_annotation": exclusion_annotation_count,
        "effective_entity_field_unresolved_paths": unresolved_paths,
    }
    return facts, status




def _java_declared_type_references(value: Any) -> list[str]:
    shape = java_type_shape(str(value or ""))
    return [str(x) for x in shape.get("type_references") or [] if str(x).strip()]


_STANDARD_NON_ASSOCIATION_TYPES = {
    "String", "CharSequence", "Object", "Class", "Enum", "Boolean", "Byte", "Short", "Integer", "Long", "Float", "Double", "Character",
    "BigDecimal", "BigInteger", "UUID", "Date", "Calendar", "Instant", "LocalDate", "LocalDateTime", "LocalTime", "OffsetDateTime", "ZonedDateTime",
    "List", "Set", "Collection", "Iterable", "Map", "Optional", "Stream", "Page", "Slice",
    "byte", "short", "int", "long", "float", "double", "boolean", "char", "void",
}


def _effective_entity_association_facts(
    containers: list[dict[str, Any]],
    inheritance_facts: list[Fact],
    effective_field_facts: list[Fact],
    *,
    ctx: dict[str, Any],
) -> tuple[list[Fact], dict[str, Any]]:
    """Resolve effective field types into facts-only entity associations."""
    target_kinds = {"entity", "meta_entity", "meta_dictionary"}
    conceptual_fqcns = {
        str(c.get("fqcn")) for c in containers
        if c.get("fqcn") and str(c.get("container_kind") or "") in target_kinds and str(c.get("source_scope") or "") != "test_code"
    }
    declarations: dict[str, dict[str, Any]] = {}
    simple_index: dict[str, list[str]] = defaultdict(list)
    parent_by_child: dict[str, str] = {}
    children_by_parent: dict[str, list[str]] = defaultdict(list)
    for fact in inheritance_facts:
        p = fact.properties or {}
        if fact.fact_type == "java_type_declaration" and p.get("fqcn"):
            fqcn = str(p["fqcn"])
            declarations[fqcn] = p
            simple_index[str(p.get("simple_name") or fqcn.rsplit(".", 1)[-1])].append(fqcn)
        elif fact.fact_type == "java_inheritance_observation" and p.get("relation_kind") == "extends" and p.get("resolved_parent_fqcn"):
            child = str(p.get("child_fqcn") or "")
            parent = str(p.get("resolved_parent_fqcn") or "")
            if child and parent:
                parent_by_child[child] = parent
                children_by_parent[parent].append(child)
    for values in simple_index.values():
        values.sort()
    for values in children_by_parent.values():
        values.sort()

    def resolve(reference: str, source_fqcn: str) -> dict[str, Any]:
        raw = str(reference or "").strip()
        simple = raw.rsplit(".", 1)[-1]
        source_decl = declarations.get(source_fqcn) or {}
        if raw in declarations:
            return {"target_resolution_kind": "exact_fqcn", "target_observed_fqcn": raw, "target_candidates": [raw]}
        package = str(source_decl.get("package_name") or (source_fqcn.rsplit(".", 1)[0] if "." in source_fqcn else ""))
        same_package = f"{package}.{simple}" if package else simple
        if same_package in declarations:
            return {"target_resolution_kind": "same_package", "target_observed_fqcn": same_package, "target_candidates": [same_package]}
        explicit: list[str] = []
        wildcard: list[str] = []
        for imp in source_decl.get("declared_imports") or []:
            imp_text = str(imp or "").strip()
            if imp_text.startswith("static "):
                continue
            if imp_text.rsplit(".", 1)[-1] == simple and imp_text in declarations:
                explicit.append(imp_text)
            elif f"{imp_text}.{simple}" in declarations:
                wildcard.append(f"{imp_text}.{simple}")
        explicit = sorted(set(explicit))
        wildcard = sorted(set(wildcard))
        if len(explicit) == 1:
            return {"target_resolution_kind": "explicit_import", "target_observed_fqcn": explicit[0], "target_candidates": explicit}
        if len(explicit) > 1:
            return {"target_resolution_kind": "ambiguous", "target_candidates": explicit}
        if len(wildcard) == 1:
            return {"target_resolution_kind": "wildcard_import", "target_observed_fqcn": wildcard[0], "target_candidates": wildcard}
        if len(wildcard) > 1:
            return {"target_resolution_kind": "ambiguous", "target_candidates": wildcard}
        candidates = list(simple_index.get(simple) or [])
        if len(candidates) == 1:
            return {"target_resolution_kind": "unique_simple_name", "target_observed_fqcn": candidates[0], "target_candidates": candidates}
        return {"target_resolution_kind": "ambiguous" if candidates else "unresolved", "target_candidates": candidates}

    def conceptual_descendants(fqcn: str) -> list[str]:
        out: list[str] = []
        queue = list(children_by_parent.get(fqcn) or [])
        seen: set[str] = set()
        while queue:
            child = queue.pop(0)
            if child in seen:
                continue
            seen.add(child)
            if child in conceptual_fqcns:
                out.append(child)
            queue.extend(children_by_parent.get(child) or [])
        return sorted(out)

    facts: list[Fact] = []
    seen: set[tuple[str, str, str, str]] = set()
    seq = 0
    counts = Counter()
    for field_fact in effective_field_facts:
        p = field_fact.properties or {}
        owner_fqcn = str(p.get("effective_owner_fqcn") or "")
        declared_in_fqcn = str(p.get("declared_in_fqcn") or owner_fqcn)
        effective_type = str(p.get("effective_type") or p.get("declared_type") or "")
        references = _java_declared_type_references(effective_type)
        for reference in references:
            simple = reference.rsplit(".", 1)[-1]
            if simple in _STANDARD_NON_ASSOCIATION_TYPES:
                continue
            resolution = resolve(reference, declared_in_fqcn)
            target_fqcn = str(resolution.get("target_observed_fqcn") or "")
            if not target_fqcn and resolution.get("target_resolution_kind") == "unresolved":
                # Keep custom-looking unresolved types, but discard scalar/library noise.
                if not re.fullmatch(r"[A-Z_$][A-Za-z0-9_$]*", simple):
                    continue
            target_model_kind = "conceptual_entity" if target_fqcn in conceptual_fqcns else ("observed_java_type" if target_fqcn else "unresolved_type")
            descendants = conceptual_descendants(target_fqcn) if target_fqcn and target_fqcn not in conceptual_fqcns else []
            key = (owner_fqcn, str(p.get("field_name") or ""), target_fqcn or reference, str(p.get("declared_in_fqcn") or ""))
            if key in seen:
                continue
            seen.add(key)
            seq += 1
            counts[str(resolution.get("target_resolution_kind") or "unknown")] += 1
            facts.append(Fact(
                fact_type="effective_entity_association",
                name=f"{owner_fqcn}.{p.get('field_name')}->{target_fqcn or reference}",
                properties={
                    "effective_entity_association_id": f"effective_entity_association_{seq:06d}",
                    **ctx,
                    "effective_owner_fqcn": owner_fqcn,
                    "effective_owner_name": p.get("effective_owner_name"),
                    "effective_owner_kind": p.get("effective_owner_kind"),
                    "source_field": p.get("field_name"),
                    "declared_type": p.get("declared_type"),
                    "effective_type": effective_type,
                    "target_type_reference": simple,
                    "target_type_reference_observed": reference,
                    **resolution,
                    "target_model_kind": target_model_kind,
                    "target_is_conceptual_entity": target_fqcn in conceptual_fqcns,
                    "conceptual_descendant_fqcns": descendants,
                    "declaration_owner_fqcn": declared_in_fqcn,
                    "declaration_owner_name": p.get("declared_in_name"),
                    "association_origin": p.get("association_origin"),
                    "inherited": bool(p.get("inherited")),
                    "inheritance_depth": p.get("inheritance_depth"),
                    "inheritance_path": p.get("inheritance_path") or [],
                    "container_kind": p.get("field_container_kind"),
                    "element_type": p.get("field_element_type"),
                    "model_exclusion_observed": bool(p.get("model_exclusion_observed")),
                    "model_exclusion_annotations": p.get("model_exclusion_annotations") or [],
                    "source_path": p.get("source_path"),
                    "source_scope": p.get("source_scope"),
                    "line_start": p.get("line_start"),
                    "line_end": p.get("line_end"),
                    "evidence_maturity_level": "confirmed" if target_fqcn else "unresolved",
                    "syntax_provider": "tree_sitter",
                    "limitations": [
                        "Declared/effective Java field type does not establish a physical foreign key or runtime cardinality.",
                        *([
                            "The field carries a model-exclusion annotation; the relation is retained as observable Java structure and is not asserted to belong to the application's generated meta model."
                        ] if p.get("model_exclusion_observed") else []),
                    ],
                },
                evidence=list(field_fact.evidence or []),
            ))
    return facts, {
        "effective_entity_associations_extracted": len(facts),
        "effective_entity_associations_inherited": sum(1 for f in facts if (f.properties or {}).get("inherited")),
        "effective_entity_associations_direct": sum(1 for f in facts if not (f.properties or {}).get("inherited")),
        "effective_entity_association_resolution_counts": dict(sorted(counts.items())),
        "effective_entity_association_supporting_type_targets": sum(1 for f in facts if (f.properties or {}).get("target_model_kind") == "observed_java_type"),
        "effective_entity_association_unresolved_targets": sum(1 for f in facts if (f.properties or {}).get("target_model_kind") == "unresolved_type"),
    }



def _java_type_descendant_facts(
    inheritance_facts: list[Fact], *, ctx: dict[str, Any]
) -> tuple[list[Fact], dict[str, Any]]:
    """Publish transitive descendant observations from resolved repository inheritance edges."""
    declarations: dict[str, dict[str, Any]] = {}
    children_by_parent: dict[str, list[tuple[str, str]]] = defaultdict(list)
    edge_evidence: dict[tuple[str, str], list[EvidenceRef]] = {}
    for fact in inheritance_facts:
        props = fact.properties or {}
        if fact.fact_type == "java_type_declaration" and props.get("fqcn"):
            declarations[str(props["fqcn"])] = props
        elif fact.fact_type == "java_inheritance_observation" and props.get("resolved_parent_fqcn"):
            child = str(props.get("child_fqcn") or "")
            parent = str(props.get("resolved_parent_fqcn") or "")
            if child and parent:
                children_by_parent[parent].append((child, str(props.get("relation_kind") or "unknown")))
                edge_evidence[(parent, child)] = list(fact.evidence or [])
    for values in children_by_parent.values():
        values.sort(key=lambda item: (item[0], item[1]))

    facts: list[Fact] = []
    seq = 0
    cycle_paths = 0
    for ancestor in sorted(declarations):
        stack: list[tuple[str, list[str], list[str]]] = [(ancestor, [ancestor], [])]
        while stack:
            current, path, relation_path = stack.pop()
            for child, relation_kind in reversed(children_by_parent.get(current, [])):
                if child in path:
                    cycle_paths += 1
                    continue
                next_path = [*path, child]
                next_relations = [*relation_path, relation_kind]
                seq += 1
                child_decl = declarations.get(child) or {}
                facts.append(Fact(
                    fact_type="java_type_descendant_observation",
                    name=f"{ancestor}->{child}",
                    properties={
                        "java_type_descendant_observation_id": f"java_type_descendant_observation_{seq:06d}",
                        **ctx,
                        "ancestor_fqcn": ancestor,
                        "descendant_fqcn": child,
                        "depth": len(next_path) - 1,
                        "direct": len(next_path) == 2,
                        "inheritance_path": next_path,
                        "relation_path": next_relations,
                        "descendant_kind": child_decl.get("class_kind"),
                        "descendant_is_abstract": bool(child_decl.get("is_abstract")),
                        "evidence_maturity_level": "confirmed",
                        "syntax_provider": "tree_sitter",
                    },
                    evidence=list(edge_evidence.get((current, child)) or []),
                ))
                stack.append((child, next_path, next_relations))
    return facts, {
        "java_type_descendant_observations_extracted": len(facts),
        "java_type_descendant_ancestors": len({(f.properties or {}).get("ancestor_fqcn") for f in facts}),
        "java_type_descendant_cycle_paths_skipped": cycle_paths,
    }


def _bounded_entity_type_path_facts(
    containers: list[dict[str, Any]],
    association_facts: list[Fact],
    *,
    ctx: dict[str, Any],
    max_depth: int = 12,
) -> tuple[list[Fact], dict[str, Any]]:
    """Walk observed entity-field associations with explicit bounds and stop reasons."""
    target_kinds = {"entity", "meta_entity", "meta_dictionary"}
    roots = sorted({
        str(c.get("fqcn") or "") for c in containers
        if c.get("fqcn") and str(c.get("container_kind") or "") in target_kinds and str(c.get("source_scope") or "") != "test_code"
    })
    edges_by_source: dict[str, list[Fact]] = defaultdict(list)
    for fact in association_facts:
        props = fact.properties or {}
        source = str(props.get("effective_owner_fqcn") or "")
        if source:
            edges_by_source[source].append(fact)
    for values in edges_by_source.values():
        values.sort(key=lambda f: (str((f.properties or {}).get("source_field") or ""), str((f.properties or {}).get("target_observed_fqcn") or (f.properties or {}).get("target_type_reference_observed") or "")))

    facts: list[Fact] = []
    seq = 0
    stop_counts: Counter[str] = Counter()
    for root in roots:
        stack: list[tuple[str, list[str], list[str], list[str]]] = [(root, [root], [], [])]
        while stack:
            current, type_path, field_path, observation_path = stack.pop()
            outgoing = edges_by_source.get(current) or []
            if not outgoing:
                stop_counts["no_observed_outgoing_association"] += 1
                continue
            for edge in reversed(outgoing):
                props = edge.properties or {}
                target = str(props.get("target_observed_fqcn") or "")
                target_reference = str(props.get("target_type_reference_observed") or props.get("target_type_reference") or "")
                next_target = target or target_reference
                next_field_path = [*field_path, str(props.get("source_field") or "")]
                next_observation_path = [*observation_path, str(props.get("effective_entity_association_id") or "")]
                stop_reason = None
                if not target:
                    stop_reason = str(props.get("target_resolution_kind") or "unresolved_target")
                elif target in type_path:
                    stop_reason = "cycle"
                elif len(type_path) - 1 >= max_depth:
                    stop_reason = "max_depth"
                elif target not in edges_by_source:
                    stop_reason = "no_observed_outgoing_association"
                next_type_path = [*type_path, next_target]
                seq += 1
                facts.append(Fact(
                    fact_type="bounded_entity_type_path_observation",
                    name=f"{root}:{'.'.join(next_field_path)}",
                    properties={
                        "bounded_entity_type_path_observation_id": f"bounded_entity_type_path_observation_{seq:06d}",
                        **ctx,
                        "root_fqcn": root,
                        "source_fqcn": current,
                        "source_field": props.get("source_field"),
                        "target_observed_fqcn": target or None,
                        "target_type_reference_observed": target_reference or None,
                        "depth": len(next_type_path) - 1,
                        "type_path": next_type_path,
                        "field_path": next_field_path,
                        "association_observation_path": next_observation_path,
                        "stop_reason": stop_reason,
                        "traversal_continues": stop_reason is None,
                        "max_depth": max_depth,
                        "evidence_maturity_level": "confirmed" if target else "unresolved",
                        "syntax_provider": "tree_sitter",
                    },
                    evidence=list(edge.evidence or []),
                ))
                if stop_reason:
                    stop_counts[stop_reason] += 1
                else:
                    stack.append((target, next_type_path, next_field_path, next_observation_path))
    return facts, {
        "bounded_entity_type_path_observations_extracted": len(facts),
        "bounded_entity_type_path_roots": len(roots),
        "bounded_entity_type_path_max_depth": max_depth,
        "bounded_entity_type_path_stop_counts": dict(sorted(stop_counts.items())),
    }

def _extract_java_attribute_containers(files: list[Path], *, model_annotation_contracts: Any = None) -> list[dict[str, Any]]:
    """Extract lightweight Java containers with JPA/storage metadata using Tree-sitter.

    Tree-sitter owns Java class/record/field boundaries and annotation attachment.
    Domain metadata such as @Table/@Column/@Id/@JoinColumn is now read from
    Tree-sitter annotation nodes, not from raw class/field text scans.
    """
    containers: list[dict[str, Any]] = []
    seen_containers: set[tuple[str, str]] = set()
    parsed_files, _warnings = parse_java_files(files)
    for parsed in parsed_files:
        p = parsed.file
        package = parsed.package
        for cls in parsed.classes:
            class_name = cls.name
            key = (str(p), class_name)
            if key in seen_containers:
                continue
            # Builder/helper classes are implementation details and duplicate the
            # owning data structure's fields. Keep other nested types observable.
            is_nested = any(
                other.line_start < cls.line_start and other.line_end > cls.line_end
                for other in parsed.classes if other is not cls
            )
            if is_nested and class_name in {"Builder", "BuilderImpl", "Factory", "Companion"}:
                continue
            fields: list[dict[str, Any]] = []
            seen_fields: set[str] = set()
            for field in cls.fields:
                fname = field.name
                modifier_tokens = set(str(field.modifiers or "").split())
                if fname in {"serialVersionUID"} or fname in seen_fields or "static" in modifier_tokens:
                    continue
                seen_fields.add(fname)
                info = _java_type_details(field.type)
                meta = _field_annotation_meta_from_annotations(field.annotations, fname)
                annotation_names = sorted({_annotation_simple_name(a) for a in field.annotations or () if _annotation_simple_name(a)})
                model_exclusion_annotations = [x for x in annotation_names if x in {"Transient"}]
                fields.append({
                    "name": fname,
                    "type": info.get("type"),
                    "raw_type": info.get("raw_type"),
                    "container_kind": info.get("container_kind"),
                    "element_type": info.get("element_type"),
                    "line_start": field.line_start,
                    "line_end": field.line_end,
                    "role": _field_role(fname),
                    "annotations": annotation_names,
                    "display_name": (field.documentation or {}).get("display_name"),
                    "description": (field.documentation or {}).get("description"),
                    "documentation_summary": (field.documentation or {}).get("summary"),
                    "documentation_tags": (field.documentation or {}).get("tags") or {},
                    "model_exclusion_observed": bool(model_exclusion_annotations),
                    "model_exclusion_annotations": model_exclusion_annotations,
                    **meta,
                })
            meta_kind, meta_annotation = _meta_model_annotation(cls.annotations, model_annotation_contracts)
            if not fields and not meta_kind:
                continue
            ann_window = class_annotations_text(cls)
            meta_args: dict[str, str] = {}
            if meta_annotation:
                for ann in cls.annotations or ():
                    if _annotation_simple_name(ann) == meta_annotation:
                        meta_args = {k: str(v) for k, v in _annotation_args_map(ann).items()}
                        break
            seen_containers.add(key)
            containers.append({
                "container_name": class_name,
                "fqcn": f"{package}.{class_name}" if package else class_name,
                "container_kind": _container_kind_for_java(class_name, ann_window=ann_window, annotations=cls.annotations, model_annotation_contracts=model_annotation_contracts),
                "source_path": str(p),
                "source_scope": _java_source_scope(p),
                "line_start": cls.line_start,
                "storage_target": _annotation_arg_from_annotations(cls.annotations, "Table", "name"),
                "model_annotation": meta_annotation,
                "model_annotation_args": meta_args,
                "display_name": (cls.documentation or {}).get("display_name"),
                "description": (cls.documentation or {}).get("description"),
                "documentation_summary": (cls.documentation or {}).get("summary"),
                "documentation_tags": (cls.documentation or {}).get("tags") or {},
                "super_types": list(cls.super_types or ()),
                "is_nested": is_nested,
                "fields": fields,
                "syntax_provider": "tree_sitter",
            })
    return containers


def _persistent_structure_fact(struct_id: str, *, ctx: dict[str, Any], storage_kind: str, storage_target: str, container_kind: str | None, container_name: str | None, fields: list[dict[str, Any]], evidence: list[EvidenceRef], source_repositories: list[str] | None = None, source_scope: str | None = None, declaration_source_scope: str | None = None, observation_source_scope: str | None = None, container_fqcn: str | None = None, model_annotation: str | None = None, model_annotation_args: dict[str, Any] | None = None, super_types: list[str] | None = None) -> Fact:
    normalized_fields: list[dict[str, Any]] = []
    relations: list[dict[str, Any]] = []
    for f in fields or []:
        row = {
            "name": f.get("name"),
            "java_field": f.get("java_field") or f.get("name"),
            "storage_field": f.get("storage_field") or f.get("name"),
            "type": f.get("type"),
            "raw_type": f.get("raw_type"),
            "role": f.get("role"),
            "key_role": f.get("key_role") or ("key_like_identifier" if str(f.get("name") or "").lower().endswith("id") else "attribute"),
            "nullable": f.get("nullable"),
            "unique": f.get("unique"),
            "relationship_kind": f.get("relationship_kind"),
            "join_column": f.get("join_column"),
            "referenced_column": f.get("referenced_column"),
        }
        normalized_fields.append({k: v for k, v in row.items() if v is not None})
        if row.get("relationship_kind") or row.get("key_role") == "foreign_key":
            relations.append({
                "relation_kind": row.get("relationship_kind") or "join_column",
                "source_field": row.get("java_field"),
                "source_storage_field": row.get("storage_field"),
                "target_container": f.get("type"),
                "target_storage_field": row.get("referenced_column"),
                "candidate_signals": [{"signal_type": "relationship_like_field", "is_evidence": False, "allowed_use": "navigation_only", "requires_source_inspection": True}],
            })
    props = {
        "persistent_structure_id": struct_id,
        **ctx,
        "storage_kind": storage_kind,
        "storage_target": storage_target,
        "container_kind": container_kind,
        "container_name": container_name,
        "container_fqcn": container_fqcn,
        "source_scope": source_scope,
        "source_set": source_scope,
        "declaration_source_scope": declaration_source_scope or source_scope,
        "observation_source_scope": observation_source_scope,
        "is_test_source": source_scope == "test_code",
        "model_annotation": model_annotation,
        "model_annotation_args": model_annotation_args or {},
        "super_types": super_types or [],
        "entity_type": container_name if container_kind in {"entity", "meta_entity", "meta_dictionary", "saved_object"} else None,
        "source_repositories": source_repositories or [],
        "fields": normalized_fields,
        "relations": relations,
        "field_count": len(normalized_fields),
        "evidence_maturity_level": "unresolved",
        "evidence_maturity_dimensions": {"physical_storage": "unresolved", "field_mapping": "unresolved"},
    }
    return Fact(
        fact_type="persistent_structure",
        name=f"{storage_kind} {storage_target}",
        properties={k: v for k, v in props.items() if v not in (None, [], {})},
        evidence=evidence,
    )


def _expression_kind_for_expression(expr: str, source_fields: list[dict[str, Any]], target_field: str | None = None) -> str:
    clean = _clean_expression(expr or "")
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*\.(?:get|is)[A-Z][A-Za-z0-9_]*\s*\(\s*\)", clean) and len(source_fields) == 1:
        sf = str(source_fields[0].get("field") or "")
        if target_field and normalize_name(sf) == normalize_name(target_field):
            return "same_name_assignment"
        return "direct_getter_assignment"
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*", clean) and len(source_fields) == 1:
        return "direct_field_assignment"
    if re.fullmatch(r"(?:null|true|false|\d+(?:\.\d+)?|\"[^\"]*\")", clean):
        return "constant_or_default"
    low = clean.lower()
    if any(tok in low for tok in ["map", "dict", "dictionary", "lookup", "getdescription", "resolve"]):
        return "dictionary_lookup"
    if len(source_fields) == 1 and ("(" in clean or any(op in clean for op in ["+", "-", "*", "/", "?", ":"])):
        return "expression_with_one_source_field"
    if len(source_fields) > 1:
        return "expression_with_multiple_source_fields"
    if re.search(r"\b(sum|avg|min|max|count|groupingBy|reduce)\b", clean, re.IGNORECASE):
        return "aggregation"
    if "(" in clean:
        return "method_call"
    return "unknown"


def _mapping_kind_for_expression(binding_kind: str, expr: str, source_fields: list[dict[str, Any]]) -> str:
    if binding_kind == "setter_mapping":
        base = "setter"
    elif binding_kind == "builder_mapping":
        base = "builder"
    elif binding_kind == "direct_assignment":
        base = "direct_assignment"
    elif binding_kind == "constructor_mapping":
        base = "constructor"
    else:
        base = "unknown"
    if len(source_fields) == 1 and _expression_kind_for_expression(expr, source_fields) in {"same_name_assignment", "direct_getter_assignment", "direct_field_assignment"}:
        return base
    if source_fields:
        return "expression"
    return base


def _attribute_mapping_fact(mapping_id: str, *, ctx: dict[str, Any], mi: dict[str, Any], source_container: str | None, source_field: str | None, target_container: str | None, target_field: str | None, mapping_kind: str, expression: str, expression_kind: str | None = None) -> Fact:
    props = {
        "attribute_mapping_id": mapping_id,
        **ctx,
        "operation": mi.get("operation"),
        "source_container": source_container or "unknown",
        "source_field": source_field,
        "target_container": target_container or "unknown",
        "target_field": target_field,
        "mapping_kind": mapping_kind,
        "expression_kind": expression_kind or _expression_kind_for_expression(expression, [{"field": source_field}] if source_field else [], target_field),
        "expression": expression,
        "evidence_maturity_level": "unresolved",
        "evidence_maturity_dimensions": {"physical_storage": "unresolved", "field_mapping": "unresolved"},
    }
    return Fact(
        fact_type="attribute_mapping",
        name=f"{source_container or 'unknown'}.{source_field or 'unknown'} -> {target_container or 'unknown'}.{target_field or 'unknown'}",
        properties=props,
        evidence=_op_file_evidence(mi, "java_data_model_lineage_mapping"),
    )


def _attribute_derivation_fact(derivation_id: str, *, ctx: dict[str, Any], mi: dict[str, Any], source_fields: list[dict[str, Any]], target_container: str | None, target_field: str | None, derivation_kind: str, expression: str, expression_kind: str | None = None) -> Fact:
    props = {
        "attribute_derivation_id": derivation_id,
        **ctx,
        "operation": mi.get("operation"),
        "source_fields": source_fields,
        "target_container": target_container or "unknown",
        "target_field": target_field,
        "derivation_kind": derivation_kind,
        "expression_kind": expression_kind or _expression_kind_for_expression(expression, source_fields, target_field),
        "expression": expression,
        "evidence_maturity_level": "unresolved",
        "evidence_maturity_dimensions": {"physical_storage": "unresolved", "field_mapping": "unresolved"},
    }
    return Fact(
        fact_type="attribute_derivation",
        name=f"{','.join(str(x.get('field')) for x in source_fields) or 'unknown'} -> {target_container or 'unknown'}.{target_field or 'unknown'}",
        properties=props,
        evidence=_op_file_evidence(mi, "java_data_model_lineage_derivation"),
    )


def _source_container_for_variable(var: str | None, mi: dict[str, Any]) -> str:
    var_types = mi.get("var_types") or {}
    params = {str(p.get("name")): _simple_type_name(p.get("type")) for p in mi.get("params") or [] if p.get("name")}
    return _simple_type_name(var_types.get(var or "") or params.get(var or "")) or "unknown"


def _expr_contains_syntax_node(expr: str, node_text: str | None) -> bool:
    value = _clean_expression(expr)
    node_value = _clean_expression(node_text)
    if not value or not node_value:
        return False
    return value == node_value or node_value in value


def _data_model_getter_source_index(mi: dict[str, Any]) -> list[tuple[str, str | None, str | None]]:
    """Return cached normalized getter/field-access texts for one method.

    Data-model lineage may inspect dozens of target assignments in the same Java
    method.  Building this normalized Tree-sitter lookup once avoids repeatedly
    cleaning/scanning the whole method_calls/field_accesses lists for each target
    expression while preserving the same matching semantics.
    """
    cached = mi.get("_data_model_getter_source_index")
    if isinstance(cached, list):
        return cached
    out: list[tuple[str, str | None, str | None]] = []
    for call in mi.get("method_calls") or []:
        text = _clean_expression_for_method(call.get("text"), mi)
        receiver = _clean_expression_for_method(call.get("receiver"), mi)
        method = str(call.get("method") or "")
        if not text or not receiver or call.get("args"):
            continue
        if method.startswith("get") and len(method) > 3:
            out.append((text, receiver, method[3:]))
        elif method.startswith("is") and len(method) > 2:
            out.append((text, receiver, method[2:]))
    for access in mi.get("field_accesses") or []:
        text = _clean_expression_for_method(access.get("text"), mi)
        receiver = _clean_expression_for_method(access.get("receiver"), mi)
        field = _clean_expression_for_method(access.get("field"), mi)
        if text and receiver and field:
            out.append((text, receiver, field))
    mi["_data_model_getter_source_index"] = out
    return out


def _extract_getter_source_fields(expr: str, mi: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract source fields from a Java expression using cached Tree-sitter syntax facts."""
    value = _clean_expression_for_method(expr, mi)
    if not value or ("." not in value and "get" not in value and "is" not in value):
        return []
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    ignored_receivers = {"this", "super", "String", "Objects", "Collections", "List", "Set", "Map"}
    ignored_fields = {"class", "builder", "stream", "map", "collect", "toList"}

    def add(var: str | None, field: str | None) -> None:
        var = _clean_expression_for_method(var, mi)
        field = _normalize_field_name(field)
        if not var or not field or var in ignored_receivers or field in ignored_fields:
            return
        container = _source_container_for_variable(var, mi)
        key = (container or "unknown", field, var)
        if key in seen:
            return
        seen.add(key)
        out.append({"container": container or "unknown", "field": field, "variable": var})

    indexed = _getter_binding_index(mi).get(value)
    if indexed:
        add(indexed[0], indexed[1])
        return out

    for node_text, receiver, field in _data_model_getter_source_index(mi):
        if not node_text:
            continue
        if value == node_text or node_text in value:
            add(receiver, field)
    return out


def _direct_assignment_target(target: str | None) -> tuple[str | None, str | None]:
    value = _clean_expression(target)
    if not value or "." not in value or "(" in value or ")" in value:
        return None, None
    receiver, field = value.rsplit(".", 1)
    receiver = _clean_expression(receiver)
    field = _clean_expression(field)
    if not receiver or not field:
        return None, None
    # Keep this as lightweight validation of the Tree-sitter target text, not Java parsing.
    valid = field.replace("_", "").isalnum() and not field[:1].isdigit()
    if not valid:
        return None, None
    return receiver, _normalize_field_name(field)


def _direct_assignment_bindings(mi: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Extract target.field = expr from Tree-sitter assignment_expression nodes."""
    out: list[dict[str, Any]] = []
    if not mi:
        return out
    seen: set[tuple[str, str, str]] = set()
    for assignment in mi.get("syntax_assignments") or []:
        if assignment.get("assignment_kind") != "assignment_expression":
            continue
        target_var, target_field = _direct_assignment_target(assignment.get("target"))
        expr = _clean_expression(assignment.get("expression"))
        if not target_var or not target_field or not expr:
            continue
        key = (target_var, target_field, expr)
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "kind": "direct_assignment",
            "target_variable": target_var,
            "target_field": target_field,
            "source_expression": expr,
            "expression": _clean_expression(assignment.get("text")) or f"{target_var}.{target_field} = {expr}",
            "syntax_provider": "tree_sitter",
        })
    return out






def _mapstruct_annotation_facts(files: list[Path], *, ctx: dict[str, Any], start_seq: int = 0) -> tuple[list[Fact], int]:
    facts: list[Fact] = []
    seq = start_seq
    try:
        parsed_files, _warnings = parse_java_files(files)
    except Exception:
        parsed_files = []
    for parsed in parsed_files:
        for cls in parsed.classes:
            for method in cls.methods:
                mapping_annotations = _mapstruct_mapping_annotations(method)
                if not mapping_annotations:
                    continue
                params = list(method.params or ())
                src_container = _simple_type_name(params[0].type) if params else "unknown"
                tgt_container = _simple_type_name(method.return_type)
                mi = {"operation": f"{cls.name}.{method.name}", "file": str(method.file), "line_start": method.line_start}
                for mapping in mapping_annotations:
                    args = mapping.get("args") or ""
                    src_value = _annotation_string_arg(args, "source")
                    tgt_value = _annotation_string_arg(args, "target")
                    if not (src_value and tgt_value):
                        continue
                    seq += 1
                    facts.append(_attribute_mapping_fact(
                        f"attribute_mapping_{seq:06d}", ctx=ctx, mi=mi,
                        source_container=src_container, source_field=src_value.split(".")[-1],
                        target_container=tgt_container, target_field=tgt_value.split(".")[-1],
                        mapping_kind="mapper_annotation", expression=_clean_expression(mapping.get("text") or f"@Mapping({args})"), expression_kind="renamed_assignment" if normalize_name(src_value) != normalize_name(tgt_value) else "same_name_assignment",
                    ))
    return facts, seq


def _span_contains(span: tuple[int, int] | None, child: dict[str, Any]) -> bool:
    if not span:
        return False
    start = child.get("start_byte")
    end = child.get("end_byte")
    return isinstance(start, int) and isinstance(end, int) and start >= span[0] and end <= span[1]


def _mapper_like_receiver(receiver: str | None) -> bool:
    value = str(receiver or "").strip()
    if not value or any(tok in value for tok in ["(", ")", "::", "->"]):
        return False
    simple = value.split(".")[-1].lower()
    return any(tok in simple for tok in ["mapper", "converter", "assembler", "translator", "transformer"])


def _expression_call_candidates(mi: dict[str, Any], expression: str, span: tuple[int, int] | None = None) -> list[dict[str, Any]]:
    expr = _clean_expression(expression)
    out: list[dict[str, Any]] = []
    for call in mi.get("method_calls") or []:
        if span and _span_contains(span, call):
            out.append(call)
            continue
        call_text = _clean_expression(call.get("text"))
        if call_text and (call_text == expr or call_text in expr):
            out.append(call)
    return out


def _expression_method_reference_candidates(mi: dict[str, Any], expression: str, span: tuple[int, int] | None = None) -> list[dict[str, Any]]:
    expr = _clean_expression(expression)
    out: list[dict[str, Any]] = []
    for ref in mi.get("method_references") or []:
        if span and _span_contains(span, ref):
            out.append(ref)
            continue
        ref_text = _clean_expression(ref.get("text"))
        if ref_text and ref_text in expr:
            out.append(ref)
    return out


def _stream_source_for_expression(mi: dict[str, Any], expression: str, span: tuple[int, int] | None = None) -> str | None:
    for call in _expression_call_candidates(mi, expression, span):
        if call.get("method") == "stream" and call.get("receiver"):
            return _clean_expression(call.get("receiver"))
    return None


def _mapper_candidate_from_expression(mi: dict[str, Any], expression: str, mapper_signatures: dict[str, list[dict[str, Any]]], *, span: tuple[int, int] | None = None) -> dict[str, Any] | None:
    for call in _expression_call_candidates(mi, expression, span):
        method = str(call.get("method") or "")
        receiver = call.get("receiver")
        if not method:
            continue
        if method not in mapper_signatures and not _mapper_like_receiver(receiver):
            continue
        args = list(call.get("args") or [])
        src_var = _clean_expression(args[0]) if args else None
        return {
            "kind": "method_call",
            "method": method,
            "mapper": receiver,
            "src_var": src_var,
            "expression": _clean_expression(call.get("text")),
        }
    for ref in _expression_method_reference_candidates(mi, expression, span):
        method = str(ref.get("method") or "")
        qualifier = ref.get("qualifier")
        if not method:
            continue
        if method not in mapper_signatures and not _mapper_like_receiver(qualifier):
            continue
        return {
            "kind": "method_reference",
            "method": method,
            "mapper": qualifier,
            "src_var": _stream_source_for_expression(mi, expression, span),
            "expression": _clean_expression(ref.get("text")),
        }
    return None


def _save_arg_candidate_expressions(mi: dict[str, Any], arg: str) -> list[dict[str, Any]]:
    arg_expr = _clean_expression(arg)
    out = [{"expression": arg_expr, "span": None}]
    for assignment in mi.get("syntax_assignments") or []:
        if assignment.get("assignment_kind") != "variable_declaration":
            continue
        if _clean_expression(assignment.get("target")) == arg_expr:
            out.append({
                "expression": _clean_expression(assignment.get("expression")),
                "span": (assignment.get("start_byte"), assignment.get("end_byte")),
            })
    return out


def _emit_mapper_save_lineage_facts(*, ctx: dict[str, Any], methods: dict[str, dict[str, Any]], mapper_signatures: dict[str, list[dict[str, Any]]], container_by_name: dict[str, dict[str, Any]], start_lineage_seq: int, start_gap_seq: int) -> tuple[list[Fact], int, int]:
    facts: list[Fact] = []
    lineage_seq = start_lineage_seq
    gap_seq = start_gap_seq
    for op, mi in sorted(methods.items()):
        var_types = mi.get("var_types") or {}
        for save_call in [c for c in (mi.get("method_calls") or []) if c.get("method") in {"save", "saveAll"}]:
            args = list(save_call.get("args") or [])
            if not args:
                continue
            mapper_candidate: dict[str, Any] | None = None
            for candidate_expr in _save_arg_candidate_expressions(mi, args[0]):
                mapper_candidate = _mapper_candidate_from_expression(mi, candidate_expr.get("expression") or "", mapper_signatures, span=candidate_expr.get("span"))
                if mapper_candidate:
                    break
            if not mapper_candidate:
                continue
            method = str(mapper_candidate.get("method") or "")
            src_var = mapper_candidate.get("src_var")
            sigs = mapper_signatures.get(method) or []
            sig = sigs[0] if sigs else {}
            source_container = sig.get("source_container") or _simple_type_name(var_types.get(src_var))
            target_container = sig.get("target_container") or "unknown"
            c = container_by_name.get(str(target_container)) or {}
            storage_target = c.get("storage_target") or target_container
            lineage_seq += 1
            missing = ["mapper_not_resolved", "field_mapping_not_resolved"]
            mapper_expr = _clean_expression(mapper_candidate.get("expression"))
            facts.append(Fact(
                fact_type="source_to_storage_lineage",
                name=f"{source_container or 'unknown'} -> {target_container} -> {storage_target}",
                properties={
                    "source_to_storage_lineage_id": f"source_to_storage_lineage_{lineage_seq:06d}",
                    **ctx,
                    "source_kind": "mapper_input",
                    "source_operation": op,
                    "source_payload": source_container or "unknown",
                    "source_field": None,
                    "source_field_role": "unknown",
                    "storage_operation": f"{save_call.get('receiver')}.save",
                    "storage_target": storage_target,
                    "saved_object": target_container,
                    "saved_object_field": None,
                    "storage_field": None,
                    "assignment_kind": "mapper_call" if mapper_candidate.get("kind") == "method_call" else "mapper_method_reference",
                    "assignment_expression": mapper_expr,
                    "path": [f"{source_container or src_var or 'unknown'}", mapper_expr, _clean_expression(save_call.get("text"))],
                    "missing_links": missing,
                    "gap_kind": "save_payload_from_mapper_result",
                },
                evidence=_op_file_evidence(mi, "java_data_model_lineage_mapper_save"),
            ))
            gap_seq += 1
            facts.append(_data_model_lineage_gap_fact(
                f"data_model_lineage_gap_{gap_seq:06d}", ctx=ctx,
                gap_kind="save_payload_from_mapper_result", operation=op,
                container=target_container, field=None,
                reason="persistent save payload is produced by mapper/converter; field-level mapper body was not resolved by the fast profile",
                missing_links=missing,
                evidence=_op_file_evidence(mi, "java_data_model_lineage_mapper_save_gap"),
            ))
    return facts, lineage_seq, gap_seq


def _constructor_container_index(containers: Any) -> dict[str, Any]:
    """Build a deterministic Java type index without simple-name overwrites."""
    if isinstance(containers, dict):
        values: list[dict[str, Any]] = []
        for key, value in containers.items():
            if not isinstance(value, dict):
                continue
            row = dict(value)
            row.setdefault("container_name", str(key))
            row.setdefault("fqcn", row.get("container_name"))
            values.append(row)
    else:
        values = [dict(value) for value in (containers or []) if isinstance(value, dict)]

    by_fqcn: dict[str, dict[str, Any]] = {}
    by_simple: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for container in values:
        simple = str(container.get("container_name") or "").strip()
        fqcn = str(container.get("fqcn") or simple).strip()
        if not simple:
            continue
        container["container_name"] = simple
        container["fqcn"] = fqcn or simple
        by_fqcn.setdefault(container["fqcn"], container)
        by_simple[simple].append(container)
    for candidates in by_simple.values():
        candidates.sort(key=lambda item: (str(item.get("fqcn") or ""), str(item.get("source_path") or "")))
    return {"by_fqcn": by_fqcn, "by_simple": by_simple}


def _constructor_type_reference(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    depth = 0
    out: list[str] = []
    for char in raw:
        if char == "<":
            depth += 1
            continue
        if char == ">" and depth:
            depth -= 1
            continue
        if depth == 0:
            out.append(char)
    return "".join(out).replace("[]", "").replace("...", "").strip()


def _resolve_constructor_container(type_reference: Any, mi: dict[str, Any], containers: Any) -> dict[str, Any]:
    """Resolve an object-creation target using normal Java source context.

    The resolver intentionally refuses to choose between several declarations
    sharing one simple name unless the creation type, declaring package or import
    statements identify one deterministic candidate.
    """
    index = containers if isinstance(containers, dict) and "by_fqcn" in containers and "by_simple" in containers else _constructor_container_index(containers)
    by_fqcn = index.get("by_fqcn") or {}
    by_simple = index.get("by_simple") or {}
    raw = _constructor_type_reference(type_reference)
    simple = _simple_type_name(raw)
    base = {
        "target_type_reference": raw or None,
        "target_simple_name": simple or None,
        "candidate_target_fqcns": [],
    }
    if not raw or not simple:
        return {**base, "resolution_kind": "unresolved", "container": None}
    if raw in by_fqcn:
        return {**base, "resolution_kind": "exact_fqcn", "container": by_fqcn[raw], "candidate_target_fqcns": [raw]}

    class_fqcn = str(mi.get("class_fqcn") or "")
    package = class_fqcn.rsplit(".", 1)[0] if "." in class_fqcn else ""
    same_package = f"{package}.{simple}" if package else simple
    if same_package in by_fqcn:
        return {**base, "resolution_kind": "same_package", "container": by_fqcn[same_package], "candidate_target_fqcns": [same_package]}

    explicit: set[str] = set()
    wildcard: set[str] = set()
    for import_value in mi.get("imports") or []:
        imp = str(import_value or "").strip()
        if not imp or imp.startswith("static "):
            continue
        if imp.endswith(f".{simple}") and imp in by_fqcn:
            explicit.add(imp)
            continue
        package_import = imp[:-2] if imp.endswith(".*") else imp
        candidate = f"{package_import}.{simple}"
        if candidate in by_fqcn:
            wildcard.add(candidate)
    if len(explicit) == 1:
        fqcn = next(iter(explicit))
        return {**base, "resolution_kind": "explicit_import", "container": by_fqcn[fqcn], "candidate_target_fqcns": [fqcn]}
    if len(explicit) > 1:
        candidates = sorted(explicit)
        return {**base, "resolution_kind": "ambiguous", "container": None, "candidate_target_fqcns": candidates}
    if len(wildcard) == 1:
        fqcn = next(iter(wildcard))
        return {**base, "resolution_kind": "wildcard_import", "container": by_fqcn[fqcn], "candidate_target_fqcns": [fqcn]}
    if len(wildcard) > 1:
        candidates = sorted(wildcard)
        return {**base, "resolution_kind": "ambiguous", "container": None, "candidate_target_fqcns": candidates}

    candidates = list(by_simple.get(simple) or [])
    candidate_fqcns = [str(item.get("fqcn") or simple) for item in candidates]
    if len(candidates) == 1:
        return {**base, "resolution_kind": "unique_simple_name", "container": candidates[0], "candidate_target_fqcns": candidate_fqcns}
    return {
        **base,
        "resolution_kind": "ambiguous" if candidates else "unresolved",
        "container": None,
        "candidate_target_fqcns": candidate_fqcns,
    }


def _constructor_named_constant_expression(value: Any) -> bool:
    """Return True for a Java-style named constant reference.

    This intentionally accepts only the conventional all-uppercase identifier
    shape.  Mixed-case identifiers remain data-flow candidates and are never
    silently converted into constants.
    """
    clean = _clean_expression(value)
    return bool(clean and re.fullmatch(r"[A-Z][A-Z0-9_]*", clean))


def _constructor_direct_value_source(value: Any, mi: dict[str, Any]) -> dict[str, Any] | None:
    """Resolve an exact parameter, implicit class field or `this` pass-through."""
    clean = _clean_expression(value)
    if not clean:
        return None
    params = {
        str(item.get("name") or ""): _simple_type_name(item.get("type"))
        for item in mi.get("params") or []
        if item.get("name")
    }
    if clean in params:
        return {
            "container": params.get(clean) or "unknown",
            "field": _normalize_field_name(clean) or clean,
            "variable": clean,
            "source_kind": "method_parameter",
        }
    if clean == "this":
        return {
            "container": _simple_type_name(mi.get("class_fqcn") or mi.get("class_name")) or "unknown",
            "field": "this",
            "variable": "this",
            "source_kind": "enclosing_instance",
        }
    class_fields = mi.get("class_field_types") or {}
    if clean in class_fields:
        return {
            "container": _simple_type_name(mi.get("class_fqcn") or mi.get("class_name")) or "unknown",
            "field": _normalize_field_name(clean) or clean,
            "variable": clean,
            "value_type": _simple_type_name(class_fields.get(clean)) or None,
            "source_kind": "class_field",
        }
    return None


def _constructor_position_span(position: dict[str, Any] | None) -> tuple[int | None, int | None]:
    if not isinstance(position, dict):
        return None, None
    try:
        start = int(position.get("start_byte")) if position.get("start_byte") is not None else None
        end = int(position.get("end_byte")) if position.get("end_byte") is not None else start
    except (TypeError, ValueError):
        return None, None
    return start, end


def _constructor_local_declaration(
    mi: dict[str, Any],
    variable_name: str,
    *,
    position: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Return the nearest visible local declaration for one constructor use.

    Byte ranges from Tree-sitter are used when available so a declaration in an
    unrelated nested scope is not treated as provenance for the constructor.
    """
    variable = _clean_expression(variable_name)
    if not _simple_java_identifier(variable):
        return None
    use_start, use_end = _constructor_position_span(position)
    candidates: list[dict[str, Any]] = []
    for assignment in mi.get("syntax_assignments") or []:
        if assignment.get("assignment_kind") != "variable_declaration":
            continue
        if _clean_expression(assignment.get("target")) != variable:
            continue
        if use_start is not None:
            try:
                declaration_start = int(assignment.get("start_byte") or -1)
                scope_start = int(assignment.get("lexical_scope_start_byte") or -1)
                scope_end = int(assignment.get("lexical_scope_end_byte") or 2**63 - 1)
            except (TypeError, ValueError):
                continue
            if declaration_start > use_start:
                continue
            if scope_start >= 0 and use_start < scope_start:
                continue
            if use_end is not None and scope_end >= 0 and use_end > scope_end:
                continue
        candidates.append(assignment)
    if not candidates:
        return None
    candidates.sort(key=lambda item: int(item.get("start_byte") or -1), reverse=True)
    return candidates[0]


def _constructor_local_value_source(
    value: Any,
    mi: dict[str, Any],
    *,
    position: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    clean = _clean_expression(value)
    declaration = _constructor_local_declaration(mi, clean, position=position)
    if not declaration:
        return None
    declared_type = declaration.get("declared_type") or (mi.get("raw_var_types") or {}).get(clean)
    return {
        "container": _simple_type_name(declared_type) or _source_container_for_variable(clean, mi),
        "field": _normalize_field_name(clean) or clean,
        "variable": clean,
        "value_type": _simple_type_name(declared_type) or None,
        "source_kind": "local_variable",
        "declaration_expression": _clean_expression(declaration.get("expression")) or None,
        "declaration_line": declaration.get("line_start"),
    }


def _constructor_lexical_parameter_source(
    value: Any,
    mi: dict[str, Any],
    *,
    position: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Resolve a lambda parameter only inside the lambda that declares it."""
    clean = _clean_expression(value)
    if not _simple_java_identifier(clean):
        return None
    use_start, use_end = _constructor_position_span(position)
    if use_start is None:
        return None
    candidates: list[dict[str, Any]] = []
    for lambda_info in mi.get("lambdas") or []:
        params = {str(item or "") for item in lambda_info.get("params") or []}
        if clean not in params:
            continue
        try:
            start = int(lambda_info.get("start_byte") or -1)
            end = int(lambda_info.get("end_byte") or -1)
        except (TypeError, ValueError):
            continue
        if start <= use_start and (use_end is None or use_end <= end):
            candidates.append(lambda_info)
    if candidates:
        candidates.sort(key=lambda item: int(item.get("end_byte") or 0) - int(item.get("start_byte") or 0))
        return {
            "container": "lambda_parameter",
            "field": _normalize_field_name(clean) or clean,
            "variable": clean,
            "source_kind": "lambda_parameter",
            "lambda_line": candidates[0].get("line_start"),
        }

    loop_candidates: list[dict[str, Any]] = []
    for loop in mi.get("enhanced_for") or []:
        if _clean_expression(loop.get("var")) != clean:
            continue
        try:
            start = int(loop.get("start_byte") or -1)
            end = int(loop.get("end_byte") or -1)
        except (TypeError, ValueError):
            continue
        if start <= use_start and (use_end is None or use_end <= end):
            loop_candidates.append(loop)
    if not loop_candidates:
        return None
    loop_candidates.sort(key=lambda item: int(item.get("end_byte") or 0) - int(item.get("start_byte") or 0))
    loop = loop_candidates[0]
    return {
        "container": _simple_type_name(loop.get("type")) or "enhanced_for_variable",
        "field": _normalize_field_name(clean) or clean,
        "variable": clean,
        "value_type": _simple_type_name(loop.get("type")) or None,
        "source_kind": "enhanced_for_variable",
        "enhanced_for_line": loop.get("line_start"),
        "enhanced_for_iterable": _clean_expression(loop.get("iterable")) or None,
    }


def _constructor_exact_method_call(expression: str, mi: dict[str, Any]) -> dict[str, Any] | None:
    clean = _clean_expression(expression)
    for call in mi.get("method_calls") or []:
        if _clean_expression(call.get("text")) == clean:
            return call
    return None


def _constructor_java_empty_collection_origin(expression: str, mi: dict[str, Any]) -> dict[str, Any] | None:
    """Recognize only exact JDK empty-collection factories with import proof."""
    clean = _clean_expression(expression)
    match = re.fullmatch(
        r"(?:(?:java\.util\.)?Collections\.)?(?:<[^>]+>)?(emptyMap|emptyList|emptySet)\(\)",
        clean,
    )
    if not match:
        return None
    method = match.group(1)
    qualified = clean.startswith("Collections.") or clean.startswith("java.util.Collections.")
    imports = {str(item or "").strip().removeprefix("static ") for item in mi.get("imports") or []}
    statically_imported = f"java.util.Collections.{method}" in imports or "java.util.Collections.*" in imports
    if not qualified and not statically_imported:
        return None
    return {
        "source_fields": [],
        "resolution_kind": "java_empty_collection_factory",
        "resolved_expression": clean,
        "observed_origin_kind": "constant_or_default",
        "factory_api": f"java.util.Collections.{method}",
    }


def _constructor_java_class_literal_origin(expression: str) -> dict[str, Any] | None:
    """Recognize a Java class literal as a fully observed constant value."""
    clean = _clean_expression(expression)
    match = re.fullmatch(
        r"(?P<type>(?:[A-Za-z_$][A-Za-z0-9_$]*(?:\.[A-Za-z_$][A-Za-z0-9_$]*)*|byte|short|int|long|float|double|boolean|char|void)(?:\[\])?)\.class",
        clean,
    )
    if not match:
        return None
    return {
        "source_fields": [],
        "resolution_kind": "java_class_literal",
        "resolved_expression": clean,
        "observed_origin_kind": "constant_or_default",
        "class_literal_type": match.group("type"),
    }


def _constructor_jooq_record_value_source(expression: str, mi: dict[str, Any]) -> dict[str, Any] | None:
    """Resolve Record.getValue(Field) through the observed Field initializer."""
    call = _constructor_exact_method_call(expression, mi)
    if not call or str(call.get("method") or "") != "getValue":
        return None
    args = list(call.get("args") or [])
    receiver = _clean_expression(call.get("receiver"))
    if len(args) != 1 or not _simple_java_identifier(receiver):
        return None
    field_reference = _clean_expression(args[0])
    if not _simple_java_identifier(field_reference):
        return None
    declaration = (mi.get("class_field_declarations") or {}).get(field_reference) or {}
    initializer = _clean_expression(declaration.get("initializer"))
    field_match = re.search(r"(?:^|\.)field\s*\(\s*\"(?P<name>[^\"]+)\"\s*(?:,|\))", initializer)
    if not field_match:
        return None
    receiver_container = _source_container_for_variable(receiver, mi)
    return {
        "container": receiver_container if receiver_container != "unknown" else "jooq.Record",
        "field": field_match.group("name"),
        "variable": receiver,
        "source_kind": "jooq_record_field",
        "field_reference": field_reference,
        "field_initializer": initializer,
    }


def _constructor_optional_unwrap_source(expression: str, mi: dict[str, Any]) -> dict[str, Any] | None:
    call = _constructor_exact_method_call(expression, mi)
    if not call or str(call.get("method") or "") not in {"orElse", "orElseGet", "orElseThrow"}:
        return None
    receiver = _clean_expression(call.get("receiver"))
    if not _simple_java_identifier(receiver):
        return None
    raw_type = str((mi.get("raw_var_types") or {}).get(receiver) or "")
    match = re.search(r"(?:java\.util\.)?Optional\s*<\s*([^>]+)\s*>", raw_type)
    if not match:
        return None
    value_type = _simple_type_name(match.group(1)) or "unknown"
    return {
        "container": value_type,
        "field": _normalize_field_name(receiver) or receiver,
        "variable": receiver,
        "value_type": value_type,
        "source_kind": "optional_value",
    }


def _constructor_expression_identifier_sources(
    expression: Any,
    mi: dict[str, Any],
    *,
    visited: set[str],
    position: dict[str, Any] | None = None,
    allow_class_fields: bool = False,
) -> list[dict[str, Any]]:
    """Resolve observed lexical inputs mentioned by a larger expression.

    Class fields are included only for a same-class constructor target.  This
    supports copy constructors while avoiding false lineage from arbitrary
    service or DAO receivers.
    """
    clean = _clean_expression(expression)
    if not clean:
        return []
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()

    def add(item: dict[str, Any]) -> None:
        key = (
            str(item.get("container") or "unknown"),
            str(item.get("field") or "unknown"),
            str(item.get("variable") or ""),
        )
        if key in seen:
            return
        seen.add(key)
        out.append(item)

    for param in mi.get("params") or []:
        name = str(param.get("name") or "")
        if name and re.search(rf"\b{re.escape(name)}\b", clean):
            add({
                "container": _simple_type_name(param.get("type")) or "unknown",
                "field": _normalize_field_name(name) or name,
                "variable": name,
                "source_kind": "method_parameter",
            })

    assignment_targets = {
        _clean_expression(item.get("target"))
        for item in mi.get("syntax_assignments") or []
        if item.get("assignment_kind") == "variable_declaration" and item.get("target")
    }
    for symbol in sorted(x for x in assignment_targets if x):
        if not re.search(rf"\b{re.escape(symbol)}\b", clean):
            continue
        declaration = _constructor_local_declaration(mi, symbol, position=position)
        alias_expression = _clean_expression((declaration or {}).get("expression"))
        if alias_expression and alias_expression not in visited:
            nested = _constructor_source_resolution(
                alias_expression,
                mi,
                visited=visited,
                position=position,
                allow_class_field_expression_inputs=allow_class_fields,
            )
            for item in nested.get("source_fields") or []:
                add(item)
            if nested.get("source_fields"):
                continue
        local_source = _constructor_local_value_source(symbol, mi, position=position)
        if local_source:
            add(local_source)

    if allow_class_fields:
        class_name = _simple_type_name(mi.get("class_fqcn") or mi.get("class_name")) or "unknown"
        for field_name, field_type in sorted((mi.get("class_field_types") or {}).items()):
            if re.search(rf"\b{re.escape(str(field_name))}\b", clean):
                add({
                    "container": class_name,
                    "field": _normalize_field_name(field_name) or field_name,
                    "variable": field_name,
                    "value_type": _simple_type_name(field_type) or None,
                    "source_kind": "class_field",
                })
    return out


def _constructor_source_resolution(
    expression: Any,
    mi: dict[str, Any],
    *,
    visited: set[str] | None = None,
    position: dict[str, Any] | None = None,
    allow_class_field_expression_inputs: bool = False,
) -> dict[str, Any]:
    """Resolve constructor argument provenance without guessing helper returns."""
    clean = _clean_expression(expression)
    chain = set(visited or set())
    if not clean or clean in chain:
        return {
            "source_fields": [],
            "resolution_kind": "unresolved",
            "resolved_expression": clean or None,
        }
    chain.add(clean)

    source_fields = _extract_getter_source_fields(clean, mi)
    if source_fields:
        return {
            "source_fields": source_fields,
            "resolution_kind": "direct_source_field_expression",
            "resolved_expression": clean,
        }

    empty_origin = _constructor_java_empty_collection_origin(clean, mi)
    if empty_origin:
        return empty_origin

    class_literal_origin = _constructor_java_class_literal_origin(clean)
    if class_literal_origin:
        return class_literal_origin

    jooq_source = _constructor_jooq_record_value_source(clean, mi)
    if jooq_source:
        return {
            "source_fields": [jooq_source],
            "resolution_kind": "jooq_record_get_value",
            "resolved_expression": clean,
        }

    optional_source = _constructor_optional_unwrap_source(clean, mi)
    if optional_source:
        return {
            "source_fields": [optional_source],
            "resolution_kind": "optional_value_unwrap",
            "resolved_expression": clean,
        }

    expression_kind = _expression_kind_for_expression(clean, [], None)
    if expression_kind == "constant_or_default" or _constructor_named_constant_expression(clean):
        return {
            "source_fields": [],
            "resolution_kind": "named_constant" if _constructor_named_constant_expression(clean) else "constant_or_default",
            "resolved_expression": clean,
            "observed_origin_kind": "constant_or_default",
        }

    if _simple_java_identifier(clean):
        lexical = _constructor_lexical_parameter_source(clean, mi, position=position)
        if lexical:
            return {
                "source_fields": [lexical],
                "resolution_kind": str(lexical.get("source_kind") or "lexical_parameter"),
                "resolved_expression": clean,
            }
        declaration = _constructor_local_declaration(mi, clean, position=position)
        alias_expression = _clean_expression((declaration or {}).get("expression"))
        if alias_expression and alias_expression not in chain:
            nested = _constructor_source_resolution(
                alias_expression,
                mi,
                visited=chain,
                position=position,
                allow_class_field_expression_inputs=allow_class_field_expression_inputs,
            )
            if nested.get("source_fields") or nested.get("observed_origin_kind"):
                return {
                    **nested,
                    "resolution_kind": "local_alias",
                    "alias_variable": clean,
                    "alias_expression": alias_expression,
                }
        direct = _constructor_direct_value_source(clean, mi)
        if direct:
            return {
                "source_fields": [direct],
                "resolution_kind": str(direct.get("source_kind") or "direct_value"),
                "resolved_expression": clean,
            }
        local_source = _constructor_local_value_source(clean, mi, position=position)
        if local_source:
            return {
                "source_fields": [local_source],
                "resolution_kind": "local_variable",
                "resolved_expression": clean,
            }

    if clean.startswith("new "):
        input_sources = _constructor_expression_identifier_sources(
            clean,
            mi,
            visited=chain,
            position=position,
            allow_class_fields=allow_class_field_expression_inputs,
        )
        return {
            "source_fields": input_sources,
            "resolution_kind": "object_creation_with_inputs" if input_sources else "object_creation",
            "resolved_expression": clean,
            "observed_origin_kind": "object_creation",
        }

    # Do not infer the return lineage of an arbitrary helper/DAO call from its
    # receiver or arguments.  A local variable that stores such a return is
    # handled as an observed local value by the caller.  Same-class copy
    # expressions are the only broader call form allowed below because their
    # class-field inputs are explicit and the target is the enclosing type.
    if _constructor_exact_method_call(clean, mi) and not allow_class_field_expression_inputs:
        return {
            "source_fields": [],
            "resolution_kind": "unresolved",
            "resolved_expression": clean,
        }

    # For a local declaration, source inputs are safe to follow because the
    # assignment itself is observed in the same lexical method.  This resolves
    # `value = request.getId(); new Target(value)` and parameter-based local
    # computations, while direct DAO/helper return calls remain unresolved.
    input_sources = _constructor_expression_identifier_sources(
        clean,
        mi,
        visited=chain,
        position=position,
        allow_class_fields=allow_class_field_expression_inputs,
    )
    if input_sources and (visited or allow_class_field_expression_inputs):
        return {
            "source_fields": input_sources,
            "resolution_kind": "same_class_expression_inputs" if allow_class_field_expression_inputs and not visited else "local_expression_inputs",
            "resolved_expression": clean,
        }
    return {
        "source_fields": [],
        "resolution_kind": "unresolved",
        "resolved_expression": clean,
    }

def _annotate_constructor_fact(fact: Fact, resolution: dict[str, Any], *, argument_expression: str) -> Fact:
    props = fact.properties or {}
    props.update({
        "constructor_source_resolution_kind": resolution.get("resolution_kind"),
        "constructor_argument_expression": _clean_expression(argument_expression),
        "constructor_resolved_source_expression": resolution.get("resolved_expression"),
    })
    if resolution.get("alias_variable"):
        props["constructor_alias_variable"] = resolution.get("alias_variable")
    if resolution.get("alias_expression"):
        props["constructor_alias_expression"] = resolution.get("alias_expression")
    if resolution.get("factory_api"):
        props["constructor_factory_api"] = resolution.get("factory_api")
    source_fields = list(resolution.get("source_fields") or [])
    if len(source_fields) == 1:
        source = source_fields[0]
        props.update({
            "constructor_source_kind": source.get("source_kind"),
            "constructor_source_variable": source.get("variable"),
            "constructor_source_value_type": source.get("value_type"),
            "constructor_source_declaration_expression": source.get("declaration_expression"),
            "constructor_source_declaration_line": source.get("declaration_line"),
            "constructor_source_field_reference": source.get("field_reference"),
            "constructor_source_field_initializer": source.get("field_initializer"),
            "constructor_lambda_line": source.get("lambda_line"),
            "constructor_enhanced_for_line": source.get("enhanced_for_line"),
            "constructor_enhanced_for_iterable": source.get("enhanced_for_iterable"),
        })
    if resolution.get("class_literal_type"):
        props["constructor_class_literal_type"] = resolution.get("class_literal_type")
    fact.properties = {k: v for k, v in props.items() if v not in (None, [], {})}
    return fact


def _constructor_mappings_for_method(mi: dict[str, Any], containers: Any, ctx: dict[str, Any], start_map_seq: int, start_der_seq: int, start_gap_seq: int, *, diagnostics: Counter[str] | None = None) -> tuple[list[Fact], int, int, int]:
    facts: list[Fact] = []
    map_seq, der_seq, gap_seq = start_map_seq, start_der_seq, start_gap_seq
    stats = diagnostics if diagnostics is not None else Counter()
    container_index = containers if isinstance(containers, dict) and "by_fqcn" in containers and "by_simple" in containers else _constructor_container_index(containers)
    source_scope = _source_scope_for_file(mi.get("file"))
    publish_unresolved = source_scope not in {"test_code", "generated_code"}

    for creation in mi.get("object_creations") or []:
        args = list(creation.get("args") or [])
        if not args:
            continue
        stats["object_creations_with_arguments"] += 1
        resolution = _resolve_constructor_container(creation.get("type"), mi, container_index)
        resolution_kind = str(resolution.get("resolution_kind") or "unresolved")
        stats[f"target_resolution_{resolution_kind}"] += 1
        container = resolution.get("container") or {}
        target = str(container.get("container_name") or resolution.get("target_simple_name") or "unknown")
        fields = container.get("fields") or []

        if not container:
            # Preserve the old behavior for entirely unknown external/JDK types,
            # but make real simple-name collisions explicit instead of choosing a
            # physically unrelated declaration and emitting false field gaps.
            if resolution_kind == "ambiguous" and resolution.get("candidate_target_fqcns"):
                if publish_unresolved:
                    gap_seq += 1
                    stats["target_type_ambiguity_gaps"] += 1
                    facts.append(_data_model_lineage_gap_fact(
                        f"data_model_lineage_gap_{gap_seq:06d}", ctx=ctx,
                        gap_kind="constructor_target_type_ambiguous", operation=mi.get("operation"),
                        container=target, field=None,
                        reason="constructor target simple name resolves to multiple observed Java declarations",
                        missing_links=["constructor target FQCN is ambiguous", "package/import resolution did not select one declaration"],
                        evidence=_op_file_evidence(mi, "java_data_model_lineage_constructor_type_gap"),
                        details={
                            "source_scope": source_scope,
                            "target_type_reference": resolution.get("target_type_reference"),
                            "target_resolution_kind": resolution_kind,
                            "candidate_target_fqcns": resolution.get("candidate_target_fqcns") or [],
                        },
                    ))
                else:
                    stats[f"suppressed_{source_scope}_target_type_ambiguity"] += 1
            continue
        if not fields:
            continue

        target_fqcn = str(container.get("fqcn") or target)
        for idx, arg in enumerate(args[:len(fields)]):
            target_field = fields[idx].get("name") if idx < len(fields) else None
            source_resolution = _constructor_source_resolution(
                arg,
                mi,
                position=creation,
                allow_class_field_expression_inputs=target_fqcn == str(mi.get("class_fqcn") or ""),
            )
            source_fields = list(source_resolution.get("source_fields") or [])
            resolved_expression = str(source_resolution.get("resolved_expression") or arg)
            expr_kind = _expression_kind_for_expression(resolved_expression, source_fields, target_field)
            direct_resolution_kinds = {
                "method_parameter",
                "class_field",
                "enclosing_instance",
                "local_variable",
                "lambda_parameter",
                "enhanced_for_variable",
                "jooq_record_get_value",
            }
            if len(source_fields) == 1 and source_resolution.get("resolution_kind") in direct_resolution_kinds:
                source_name = str(source_fields[0].get("field") or "")
                expr_kind = "same_name_assignment" if target_field and normalize_name(source_name) == normalize_name(target_field) else "direct_value_assignment"
            if len(source_fields) == 1 and expr_kind in {"same_name_assignment", "direct_getter_assignment", "direct_field_assignment"}:
                sf = source_fields[0]
                map_seq += 1
                stats["attribute_mappings"] += 1
                fact = _attribute_mapping_fact(
                    f"attribute_mapping_{map_seq:06d}", ctx=ctx, mi=mi,
                    source_container=sf.get("container"), source_field=sf.get("field"),
                    target_container=target, target_field=target_field,
                    mapping_kind="constructor_local_alias" if source_resolution.get("resolution_kind") == "local_alias" else "constructor",
                    expression=f"new {target}(... arg {idx+1}: {_clean_expression(arg)})", expression_kind=expr_kind,
                )
                facts.append(_annotate_constructor_fact(fact, source_resolution, argument_expression=arg))
            elif source_fields:
                der_seq += 1
                stats["attribute_derivations"] += 1
                fact = _attribute_derivation_fact(
                    f"attribute_derivation_{der_seq:06d}", ctx=ctx, mi=mi,
                    source_fields=source_fields, target_container=target, target_field=target_field,
                    derivation_kind="constructor_expression", expression=f"new {target}(... arg {idx+1}: {_clean_expression(arg)})", expression_kind=expr_kind,
                )
                facts.append(_annotate_constructor_fact(fact, source_resolution, argument_expression=arg))
            elif target_field and source_resolution.get("observed_origin_kind"):
                # A literal/default or explicit object creation has a fully
                # observed origin even when there is no upstream attribute.
                if not publish_unresolved:
                    stats[f"suppressed_{source_scope}_observed_origins"] += 1
                    continue
                der_seq += 1
                stats["attribute_derivations"] += 1
                stats[f"observed_origin_{source_resolution.get('observed_origin_kind')}"] += 1
                fact = _attribute_derivation_fact(
                    f"attribute_derivation_{der_seq:06d}", ctx=ctx, mi=mi,
                    source_fields=[], target_container=target, target_field=target_field,
                    derivation_kind=f"constructor_{source_resolution.get('observed_origin_kind')}",
                    expression=f"new {target}(... arg {idx+1}: {_clean_expression(arg)})",
                    expression_kind="constant_or_default" if source_resolution.get("observed_origin_kind") == "constant_or_default" else "object_creation",
                )
                facts.append(_annotate_constructor_fact(fact, source_resolution, argument_expression=arg))
            elif target_field:
                if not publish_unresolved:
                    stats[f"suppressed_{source_scope}_unresolved_arguments"] += 1
                    continue
                gap_seq += 1
                stats["mapping_gaps"] += 1
                facts.append(_data_model_lineage_gap_fact(
                    f"data_model_lineage_gap_{gap_seq:06d}", ctx=ctx,
                    gap_kind="constructor_mapping_not_resolved", operation=mi.get("operation"),
                    container=target, field=target_field,
                    reason="constructor argument could not be resolved to source fields by the fast profile",
                    missing_links=["constructor argument source not resolved"],
                    evidence=_op_file_evidence(mi, "java_data_model_lineage_constructor_gap"),
                    details={
                        "source_scope": source_scope,
                        "target_container_fqcn": target_fqcn,
                        "target_type_reference": resolution.get("target_type_reference"),
                        "target_resolution_kind": resolution_kind,
                        "constructor_argument_index": idx,
                        "constructor_argument_expression_kind": expr_kind,
                        "constructor_argument_expression": _clean_expression(arg),
                        "constructor_resolved_source_expression": source_resolution.get("resolved_expression"),
                        "constructor_source_resolution_kind": source_resolution.get("resolution_kind"),
                    },
                ))
    return facts, map_seq, der_seq, gap_seq



__all__ = [name for name in globals() if name.startswith("_") or name.startswith("build_java")]
