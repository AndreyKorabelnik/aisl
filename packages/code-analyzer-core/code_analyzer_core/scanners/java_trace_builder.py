from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from collections import defaultdict, Counter
from pathlib import Path
from typing import Any

from code_analyzer_core.models import Fact, EvidenceRef
from code_analyzer_core.scanners.java_trace_common import *
from code_analyzer_core.scanners.java_call_observations import *
from code_analyzer_core.evidence_contract import maturity_props as _maturity_props
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
from code_analyzer_core.scanners.java_field_lineage import *
from code_analyzer_core.scanners.java_output_provenance import *
from code_analyzer_core.scanners.java_persistence_lineage import *
from code_analyzer_core.scanners.java_persistence_mapping_resolvers import _source_scope_for_file
from code_analyzer_core.utils import read_text, line_number_for_offset, normalize_name, write_json
from code_analyzer_core.scanners.java_flow_builder import (
    _parse_params,
    _parameter_names,
    _clean_expression,
    _contains_symbol,
    _assignment_map,
    _source_param_for_payload,
    _normalize_java_type,
    _class_name_for_position,
    _getter_field,
    _field_role,
)








































































def _fast_local_jooq_batch_bind_mappings(methods: dict[str, dict[str, Any]]) -> list[Fact]:
    """Cheap local-only jOOQ batch.bind mapping for fast system profiles.

    The deep persistence scanner has a richer resolver that can follow helper
    methods. This traceability-side extractor intentionally stays local to the
    same method to avoid expensive cross-method searches on large applications.
    """
    facts: list[Fact] = []
    seq = 0
    for op, mi in sorted(methods.items()):
        body = mi.get("body") or ""
        if ".bind(" not in body or "batch" not in body.lower():
            continue
        statements = _jooq_update_statement_slots(body, bindable_only=True)
        if not statements:
            continue
        batch_links, inline_statements = _jooq_batch_variable_links(body)
        if not batch_links and not inline_statements:
            continue
        for call in _method_calls_with_text_fallback(mi, body, "bind"):
            batch_var = _clean_expression(call.get("receiver"))
            stmt_var = batch_links.get(batch_var)
            stmt = statements.get(stmt_var or "") or inline_statements.get(batch_var or "")
            if not stmt:
                continue
            args = list(call.get("args") or [])
            slots = list(stmt.get("slots") or [])
            lambda_var = _lambda_var_for_bind_call(body, batch_var)
            collection_var = _lambda_collection_for_var(body, lambda_var or "") if lambda_var else None
            sequence_assignments = _sequence_assignments_for_collection(body, collection_var)
            mappings: list[dict[str, Any]] = []
            for i, slot in enumerate(slots):
                source_expr = _clean_expression(args[i]) if i < len(args) else None
                source_var, source_field, resolved_expr = _source_binding_from_expression(source_expr, mi) if source_expr else (None, None, None)
                generation = sequence_assignments.get(str(source_field or "")) if source_var == lambda_var and source_field else None
                mapping = {
                    "bind_index": i,
                    "storage_field": slot.get("field"),
                    "storage_field_ref": slot.get("field_ref"),
                    "field_role": slot.get("role"),
                    "source_expression": resolved_expr or source_expr,
                    "source_object": source_var,
                    "source_field": source_field,
                    "mapping_status": "candidate_bind_order_mapping" if source_expr else "unresolved_missing_bind_arg",
                }
                if generation:
                    mapping["source_generation"] = generation
                mappings.append(mapping)
            seq += 1
            props = {
                "jooq_batch_bind_mapping_id": f"jooq_batch_bind_mapping_fast_{seq:06d}",
                "operation": op,
                "class_name": mi.get("class_name"),
                "method_name": mi.get("method_name"),
                "batch_variable": batch_var,
                "statement_variable": stmt_var,
                "storage_table": stmt.get("table"),
                "storage_table_ref": stmt.get("table_ref"),
                "mapping_kind": "jooq_batch_bind_order",
                "mapping_status": "candidate",
                "resolver_scope": "same_method_local_fast",
                "mappings": mappings,
                "write_target_fields": [m for m in mappings if m.get("field_role") == "write_target_field"],
                "where_key_fields": [m for m in mappings if m.get("field_role") == "where_key_field"],
                "evidence_policy": "fast local bind-order mapping; use deep profile for cross-method helper resolution",
            }
            facts.append(Fact(
                fact_type="jooq_batch_bind_mapping",
                name=f"{op}: {stmt.get('table') or 'unknown'} batch.bind",
                properties={k: v for k, v in props.items() if v not in (None, [], {})},
                evidence=_op_file_evidence(mi, "java_jooq_batch_bind_mapping_fast"),
            ))
    return facts

TRACEABILITY_MAX_DEPTH = 5
TRACEABILITY_MAX_RECEIVER_CANDIDATES_PER_CALL = 8


def _find_origin_path(
    *,
    target_operation: str,
    target_parameter: str | None,
    origins_by_operation: dict[str, list[dict[str, Any]]],
    reverse_calls: dict[str, list[dict[str, Any]]],
    max_depth: int = TRACEABILITY_MAX_DEPTH,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]], list[str]]:
    queue: list[tuple[str, str | None, list[dict[str, Any]], list[str]]] = [(target_operation, target_parameter, [], [])]
    seen: set[tuple[str, str | None]] = set()
    fallback_origin: tuple[dict[str, Any], list[dict[str, Any]], list[str]] | None = None

    while queue:
        op, expected_param, path, relations = queue.pop(0)
        if (op, expected_param) in seen or len(path) > max_depth:
            continue
        seen.add((op, expected_param))

        for origin in sorted(
            origins_by_operation.get(op, []),
            key=lambda item: (
                str(item.get("origin_id") or item.get("ingress_id") or ""),
                str(item.get("payload_parameter") or ""),
                str(item.get("file") or ""),
                int(item.get("line_start") or 0),
            ),
        ):
            payload_param = origin.get("payload_parameter")
            if not payload_param or not expected_param or payload_param == expected_param:
                return origin, list(reversed(path)), list(reversed(relations))
            # Keep a navigation fallback if the operation is the same but parameter mapping is unclear.
            if fallback_origin is None:
                fallback_origin = (
                    origin,
                    list(reversed(path)),
                    list(reversed(relations + ["unknown"])),
                )

        for call in sorted(
            reverse_calls.get(op, []),
            key=lambda item: (
                str(item.get("caller_operation_id") or ""),
                str(item.get("call_id") or ""),
                str(item.get("file") or ""),
                int(item.get("line_start") or 0),
            ),
        ):
            b = _binding_for_callee_param(call, expected_param)
            if not b:
                continue
            caller_param = b.get("caller_source_parameter")
            relation = str(b.get("relation") or "unknown")
            next_param = str(caller_param) if caller_param else None
            queue.append((call["caller_operation_id"], next_param, path + [call], relations + [relation]))

    if fallback_origin:
        return fallback_origin
    return None, [], []


def _flow_props(fact: Fact) -> dict[str, Any]:
    return fact.properties or {}


def _field_refs_for_flow(flow_id: str, field_flow_facts: list[Fact]) -> list[str]:
    refs: list[str] = []
    for f in field_flow_facts:
        props = f.properties or {}
        if props.get("related_flow_id") == flow_id and props.get("field_flow_id"):
            refs.append(str(props["field_flow_id"]))
    return refs


def _trace_fact(
    *,
    trace_id: str,
    trace_type: str,
    origin: dict[str, Any] | None,
    terminal_operation: str,
    terminal_step: dict[str, Any],
    call_path: list[dict[str, Any]],
    relation_chain: list[str],
    evidence_refs: list[str],
    payload_type: str | None,
    payload_expression: str | None,
    unknown_status: str,
    methods: dict[str, dict[str, Any]],
    extra: dict[str, Any] | None = None,
) -> Fact:
    status = _trace_status(origin, relation_chain, unknown_kind=unknown_status)
    quality = _relation_quality(relation_chain)
    missing_links: list[str] = []
    if not origin:
        missing_links.extend([
            "no confirmed ingress/data-origin operation",
            f"no caller chain to {terminal_operation}",
        ])
    elif status == "unresolved":
        missing_links.append("one or more call-chain argument bindings are missing or not confirmed")
    steps: list[dict[str, Any]] = []
    if origin:
        steps.append({
            "kind": "ingress" if origin.get("is_payload_origin") else "entrypoint_or_trigger",
            "ingress_id": origin.get("ingress_id"),
            "origin_id": origin.get("origin_id"),
            "operation_id": origin.get("operation_id"),
            "origin_kind": origin.get("origin_kind"),
            "description": f"{origin.get('origin_kind')} receives or triggers data processing",
        })
    else:
        steps.append({
            "kind": "earliest_observed_operation",
            "operation_id": terminal_operation,
            "description": f"Earliest observed operation is {terminal_operation}; no confirmed system ingress/source chain was found.",
        })
    for call in call_path:
        binding = call.get("argument_bindings", [{}])[0] if call.get("argument_bindings") else {}
        steps.append({
            "kind": "method_call",
            "call_id": call.get("call_id"),
            "from_operation_id": call.get("caller_operation_id"),
            "to_operation_id": call.get("callee_operation_id"),
            "argument_mapping": f"{binding.get('caller_expression')} -> {binding.get('callee_parameter')}",
            "relation": binding.get("relation"),
        })
    steps.append(terminal_step)

    mi = methods.get(terminal_operation)
    evidence = _op_file_evidence(mi, "java_trace_builder_trace") if mi else []
    props: dict[str, Any] = {
        "trace_id": trace_id,
        "kind": "trace",
        "trace_type": trace_type,
        "origin_trace_type": trace_type.replace("ingress_to", "origin_to"),
        "trace_status": status,
        "ingress_id": origin.get("ingress_id") if origin else None,
        "origin_id": origin.get("origin_id") if origin else None,
        "origin_kind": origin.get("origin_kind") if origin else "unknown",
        "is_payload_origin": origin.get("is_payload_origin") if origin else False,
        "ingress_operation_id": origin.get("operation_id") if origin else None,
        "earliest_observed_operation_id": terminal_operation if not origin else origin.get("operation_id"),
        "earliest_observed_reason": "method_parameter_observed_without_confirmed_caller" if not origin else "confirmed_origin_found",
        "terminal_operation_id": terminal_operation,
        "payload_type": payload_type or "unknown",
        "payload_expression": payload_expression,
        "same_data_chain_status": quality,
        "argument_relation_chain": relation_chain,
        "steps": steps,
        "evidence_refs": [x for x in evidence_refs if x],
        "missing_links": missing_links,
    }
    if extra:
        props.update(extra)
    return Fact(
        fact_type="data_trace",
        name=f"{trace_type} {trace_id}: {props.get('origin_kind')} -> {terminal_operation}",
        properties=props,
        evidence=evidence,
    )


def _build_trace_facts(
    *,
    flow_facts: list[Fact],
    field_flow_facts: list[Fact],
    storage_accesses: list[dict[str, Any]],
    methods: dict[str, dict[str, Any]],
    origins: list[dict[str, Any]],
    calls: list[dict[str, Any]],
) -> tuple[list[Fact], dict[str, Any]]:
    traces: list[Fact] = []
    trace_seq = 0
    origins_by_operation: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for origin in origins:
        origins_by_operation[origin["operation"]].append(origin)
    reverse_calls: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for call in calls:
        reverse_calls[call["callee_operation_id"]].append(call)

    # Outbound traces from existing local flow facts.
    for f in flow_facts:
        props = _flow_props(f)
        op = props.get("operation")
        if not op:
            continue
        source_param = props.get("source_parameter")
        origin, call_path, relation_chain = _find_origin_path(
            target_operation=str(op),
            target_parameter=str(source_param) if source_param else None,
            origins_by_operation=origins_by_operation,
            reverse_calls=reverse_calls,
        )
        flow_id = str(props.get("flow_id") or "")
        field_refs = _field_refs_for_flow(flow_id, field_flow_facts)
        trace_seq += 1
        traces.append(_trace_fact(
            trace_id=f"trace_{trace_seq:06d}",
            trace_type="ingress_to_outbound",
            origin=origin,
            terminal_operation=str(op),
            terminal_step={
                "kind": "outbound_sink",
                "operation_id": op,
                "sink_kind": props.get("sink_kind"),
                "description": f"publishes payload to {props.get('sink_kind')} sink",
                "flow_id": flow_id,
            },
            call_path=call_path,
            relation_chain=relation_chain,
            evidence_refs=[origin.get("ingress_id") if origin else None, *[c.get("call_id") for c in call_path], flow_id, *field_refs],
            payload_type=props.get("source_type"),
            payload_expression=props.get("payload_expression"),
            unknown_status="outbound_only_unknown_origin",
            methods=methods,
            extra={
                "outbound_operation_id": op,
                "outbound_sink_id": props.get("target_expression"),
                "sink_kind": props.get("sink_kind"),
                "related_flow_id": flow_id,
                "related_field_flow_ids": field_refs,
            },
        ))

    # Persistence traces for writes/mutations only. Read-only access remains storage evidence.
    for access in storage_accesses:
        if access.get("access_kind") not in {"write", "mutation"}:
            continue
        op = str(access.get("operation") or "")
        mi = methods.get(op)
        if not mi:
            continue
        payload = _clean_expression(access.get("payload_expression"))
        source_param, _, _ = _source_param_for_payload(payload, mi.get("param_names") or set(), mi.get("assignments") or {})
        origin, call_path, relation_chain = _find_origin_path(
            target_operation=op,
            target_parameter=source_param,
            origins_by_operation=origins_by_operation,
            reverse_calls=reverse_calls,
        )
        trace_seq += 1
        traces.append(_trace_fact(
            trace_id=f"trace_{trace_seq:06d}",
            trace_type="ingress_to_persistence",
            origin=origin,
            terminal_operation=op,
            terminal_step={
                "kind": "persistence_sink" if access.get("access_kind") == "write" else "storage_mutation",
                "operation_id": op,
                "storage_access_id": access.get("storage_access_id"),
                "db_write_kind": access.get("write_kind"),
                "table_or_repository": access.get("table_or_repository"),
                "description": f"{access.get('access_kind')} via {access.get('receiver_expression')}.{access.get('storage_method')}",
            },
            call_path=call_path,
            relation_chain=relation_chain,
            evidence_refs=[origin.get("ingress_id") if origin else None, *[c.get("call_id") for c in call_path], access.get("storage_access_id")],
            payload_type=next((p.get("type") for p in mi.get("params") or [] if p.get("name") == source_param), access.get("payload_type")),
            payload_expression=payload,
            unknown_status="persistence_only_unknown_origin",
            methods=methods,
            extra={
                "persistence_operation_id": op,
                "storage_access_id": access.get("storage_access_id"),
                "db_write_kind": access.get("write_kind"),
                "access_kind": access.get("access_kind"),
                "table_or_repository": access.get("table_or_repository"),
                "saved_payload": payload,
            },
        ))

    status_counts = Counter(str((t.properties or {}).get("trace_status")) for t in traces)
    type_counts = Counter(str((t.properties or {}).get("trace_type")) for t in traces)
    return traces, {
        "traces_extracted": len(traces),
        "trace_status_counts": dict(sorted(status_counts.items())),
        "trace_type_counts": dict(sorted(type_counts.items())),
    }




# --- Output field provenance --------------------------------------------------------

OUTPUT_FIELD_ROLES = {
    "returned_in_response",
    "published_to_kafka",
    "sent_to_http_client",
    "persisted_to_storage",
}



def _call_chain_diagnostic_fact(
    *,
    diag_id: str,
    target_operation: str,
    published_boundary: str | None,
    caller_status: str,
    caller_candidates: list[str],
    resolved_call_ids: list[str],
    resolved_callers: list[str],
    reason: str,
    missing_links: list[str],
    evidence: list[EvidenceRef],
) -> Fact:
    props = {
        "call_chain_diagnostic_id": diag_id,
        "target_operation": target_operation,
        "published_boundary": published_boundary,
        "caller_status": caller_status,
        "caller_candidates": caller_candidates,
        "resolved_call_ids": resolved_call_ids,
        "resolved_callers": resolved_callers,
        "earliest_observed_operation": target_operation,
        "system_ingress_status": "not_resolved" if caller_status != "resolved_callers_found" else "caller_chain_unresolved",
        "reason": reason,
        "missing_links": missing_links,
        "evidence_refs": resolved_call_ids,
    }
    return Fact(
        fact_type="call_chain_diagnostic",
        name=f"{target_operation}: caller_status={caller_status}",
        properties=props,
        evidence=evidence,
    )


def _raw_call_candidates_for_method(methods: dict[str, dict[str, Any]], target_operation: str) -> list[str]:
    target_mi = methods.get(target_operation) or {}
    target_method = str(target_mi.get("method_name") or target_operation.rsplit(".", 1)[-1])
    target_class = str(target_mi.get("class_name") or target_operation.split(".", 1)[0])
    candidates: set[str] = set()
    if not target_method:
        return []
    class_bean = target_class[:1].lower() + target_class[1:] if target_class else ""
    for op, mi in methods.items():
        if op == target_operation:
            continue
        for call in mi.get("method_calls") or []:
            if call.get("method") != target_method:
                continue
            receiver = str(call.get("receiver") or "")
            # Prefer likely references to the target class/bean, but keep method-name-only
            # candidates because source-only code may use interface fields.
            if not receiver or not target_class or receiver in {target_class, class_bean} or target_class in receiver or class_bean in receiver:
                candidates.add(op)
                break
    return sorted(candidates)


def _build_call_chain_diagnostic_facts(
    *,
    methods: dict[str, dict[str, Any]],
    calls: list[dict[str, Any]],
    flow_facts: list[Fact],
    trace_facts: list[Fact],
) -> tuple[list[Fact], dict[str, Any]]:
    facts: list[Fact] = []
    seq = 0
    incoming: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for call in calls:
        incoming[str(call.get("callee_operation_id") or "")].append(call)

    trace_status_by_terminal: dict[str, list[str]] = defaultdict(list)
    for tf in trace_facts:
        props = tf.properties or {}
        terminal = str(props.get("terminal_operation_id") or props.get("outbound_operation_id") or props.get("persistence_operation_id") or "")
        if terminal:
            trace_status_by_terminal[terminal].append(str(props.get("trace_status") or ""))

    target_boundary_by_op: dict[str, str] = {}
    for flow in flow_facts:
        props = flow.properties or {}
        op = str(props.get("operation") or "")
        boundary, _role = _target_boundary_for_sink(str(props.get("sink_kind") or ""))
        if op and boundary in {"kafka", "http_client", "rest_response"}:
            target_boundary_by_op[op] = boundary

    for op, boundary in sorted(target_boundary_by_op.items()):
        statuses = trace_status_by_terminal.get(op, [])
        needs_diag = not statuses or any("unknown_origin" in s or "outbound_only" in s or "persistence_only" in s for s in statuses)
        if not needs_diag:
            continue
        mi = methods.get(op) or {}
        resolved = incoming.get(op, [])
        raw_candidates = _raw_call_candidates_for_method(methods, op)
        if resolved:
            caller_status = "resolved_callers_found"
            resolved_callers = sorted({str(c.get("caller_operation_id") or "") for c in resolved if c.get("caller_operation_id")})
            reason = "Direct/in-repository callers were resolved, but no confirmed system ingress chain was established."
            missing = ["caller chain exists but does not connect to confirmed REST/Kafka/system ingress in current evidence"]
        elif raw_candidates:
            caller_status = "candidates_found_not_connected"
            resolved_callers = []
            reason = "Raw source references to target method were found, but source-only call graph did not resolve them to call facts."
            missing = ["possible Spring injection/interface dispatch/generic wrapper/async indirection limitation"]
        else:
            caller_status = "not_found_in_repository"
            resolved_callers = []
            reason = "No direct or indirect callers of target operation were found in analyzed repository source."
            missing = ["caller is outside analyzed scope or method is invoked by runtime/framework/external scheduler"]
        seq += 1
        facts.append(_call_chain_diagnostic_fact(
            diag_id=f"call_chain_diagnostic_{seq:06d}",
            target_operation=op,
            published_boundary=boundary,
            caller_status=caller_status,
            caller_candidates=raw_candidates,
            resolved_call_ids=[str(c.get("call_id") or "") for c in resolved if c.get("call_id")],
            resolved_callers=resolved_callers,
            reason=reason,
            missing_links=missing,
            evidence=_op_file_evidence(mi, "java_call_chain_diagnostic") if mi else [],
        ))

    status_counts = Counter(str((f.properties or {}).get("caller_status")) for f in facts)
    return facts, {
        "call_chain_diagnostics_extracted": len(facts),
        "call_chain_diagnostic_status_counts": dict(sorted(status_counts.items())),
    }





def build_java_data_model_lineage_facts(files: list[Path], *, project_code: str = "UNKNOWN", system_name: str = "unknown-system", repo_id: str | None = None, repo_path: str | None = None, fp_id: str | None = None, fp_name: str | None = None, max_depth: int = 2, persistence_facts: list[Fact] | None = None, persistence_status: dict[str, Any] | None = None, include_persistence_facts: bool = True, progress_path: Path | None = None, model_annotation_contracts: Any = None) -> tuple[list[Fact], dict[str, Any]]:
    """Build fast neutral evidence for AS data model and attribute lineage.

    v0.23.14 keeps this harvesting-first: no Semgrep, no full traceability, no
    deep provenance. It enriches cheap facts for LLM: JPA physical metadata,
    shallow mapper/save lineage, expression kinds and specific gaps.
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
                "artifact": "java_data_model_lineage_progress",
                "status": status if status in {"done", "failed"} else "running",
                "current_phase": phase,
                "elapsed_ms": event["elapsed_ms"],
                "last_event": event,
                "events": phase_events[-80:],
            })

    progress("context.method_index", "running", {"file_count": len(files)})
    ctx = _repo_context(repo_id, project_code, system_name, repo_path)
    if fp_id:
        ctx["fp_id"] = fp_id
    if fp_name:
        ctx["fp_name"] = fp_name
    methods, class_fields, class_infos, warnings = _build_method_index(files)
    progress("context.method_index", "done", {"method_count": len(methods), "class_count": len(class_infos)})

    progress("context.schema_and_containers", "running")
    schema_fields = _extract_all_schema_fields(files)
    containers = _extract_java_attribute_containers(files, model_annotation_contracts=model_annotation_contracts)
    container_by_name = {str(c.get("container_name")): c for c in containers}
    constructor_container_index = _constructor_container_index(containers)
    constructor_diagnostics: Counter[str] = Counter()
    repo_entity_types = _repository_entity_types(files)
    mapper_signatures = _mapper_method_signatures(files)
    progress("context.schema_and_containers", "done", {
        "schema_type_count": len(schema_fields),
        "container_count": len(containers),
        "repository_entity_type_count": sum(len(v) for v in repo_entity_types.values()),
        "mapper_signature_count": sum(len(v) for v in mapper_signatures.values()),
    })
    facts: list[Fact] = []
    inheritance_facts, inheritance_status = _java_type_declaration_and_inheritance_facts(files, ctx=ctx)
    facts.extend(inheritance_facts)
    progress("context.java_inheritance_graph", "done", inheritance_status)
    descendant_facts, descendant_status = _java_type_descendant_facts(inheritance_facts, ctx=ctx)
    facts.extend(descendant_facts)
    progress("context.java_type_descendants", "done", descendant_status)
    effective_field_facts, effective_field_status = _effective_entity_field_facts(containers, inheritance_facts, ctx=ctx)
    facts.extend(effective_field_facts)
    progress("context.effective_entity_fields", "done", effective_field_status)
    effective_association_facts, effective_association_status = _effective_entity_association_facts(
        containers, inheritance_facts, effective_field_facts, ctx=ctx
    )
    facts.extend(effective_association_facts)
    progress("context.effective_entity_associations", "done", effective_association_status)
    bounded_path_facts, bounded_path_status = _bounded_entity_type_path_facts(
        containers, effective_association_facts, ctx=ctx
    )
    facts.extend(bounded_path_facts)
    progress("context.bounded_entity_type_paths", "done", bounded_path_status)

    occ_seq = 0
    struct_seq = 0
    map_seq = 0
    der_seq = 0
    gap_seq = 0

    progress("attribute_occurrence_phase", "running", {"container_count": len(containers)})
    emitted_structure_keys: set[tuple[str, str, str]] = set()
    for c in containers:
        for field in c.get("fields") or []:
            if c.get("container_kind") == "java_class" and _is_dependency_field_candidate(field):
                continue
            occ_seq += 1
            facts.append(_attribute_occurrence_fact(f"attribute_occurrence_{occ_seq:06d}", ctx=ctx, container=c, field=field))
        container_kind = str(c.get("container_kind") or "")
        source_scope = str(c.get("source_scope") or "unknown_code")
        if container_kind in {"entity", "meta_entity", "meta_dictionary"} and source_scope != "test_code":
            storage_kind = "database" if container_kind == "entity" else "conceptual_model"
            container_fqcn = str(c.get("fqcn") or c.get("container_fqcn") or c.get("container_name") or "")
            target = str(c.get("storage_target") or container_fqcn or c.get("container_name") or "unknown")
            structure_key = (storage_kind, target, container_fqcn)
            if structure_key in emitted_structure_keys:
                continue
            emitted_structure_keys.add(structure_key)
            struct_seq += 1
            facts.append(_persistent_structure_fact(
                f"persistent_structure_{struct_seq:06d}", ctx=ctx, storage_kind=storage_kind, storage_target=target,
                container_kind=container_kind, container_name=str(c.get("container_name") or target), fields=c.get("fields") or [],
                source_repositories=repo_entity_types.get(str(c.get("container_name") or ""), []),
                source_scope=source_scope, declaration_source_scope=source_scope, container_fqcn=c.get("fqcn"),
                model_annotation=c.get("model_annotation"), model_annotation_args=c.get("model_annotation_args"),
                super_types=c.get("super_types") or [],
                evidence=[EvidenceRef(file_path=str(c.get("source_path")), line_start=c.get("line_start"), extractor="java_data_model_lineage_structure")],
            ))
    progress("attribute_occurrence_phase", "done", {"fact_count": len(facts), "attribute_occurrence_count": occ_seq, "persistent_structure_count": struct_seq})

    progress("persistence_lineage_reuse", "running", {"reused": persistence_facts is not None})
    reused_persistence_lineage = persistence_facts is not None
    if persistence_facts is None:
        persistence_facts, persistence_status = build_java_persistence_lineage_facts(files, max_depth=max_depth)
    else:
        persistence_status = dict(persistence_status or {})
    progress("persistence_lineage_reuse", "done", {"reused": reused_persistence_lineage, "persistence_fact_count": len(persistence_facts or [])})

    progress("persistence_fact_copy", "running", {
        "persistence_fact_count": len(persistence_facts or []),
        "include_persistence_facts": include_persistence_facts,
    })
    if include_persistence_facts:
        for f in persistence_facts:
            props = dict(f.properties or {})
            props.update(ctx)
            if fp_id:
                props["fp_id"] = fp_id
            if fp_name:
                props["fp_name"] = fp_name
            facts.append(Fact(fact_type=f.fact_type, name=f.name, properties=props, evidence=f.evidence))
    progress("persistence_fact_copy", "done", {
        "fact_count": len(facts),
        "persistence_facts_included": include_persistence_facts,
    })

    progress("persistent_structure_from_writes", "running")
    for f in persistence_facts:
        if f.fact_type != "persistent_write":
            continue
        props = f.properties or {}
        saved_object = str(props.get("saved_object") or "unknown").strip()
        container = container_by_name.get(saved_object)
        fields = (container or {}).get("fields") or schema_fields.get(saved_object) or []
        # A write observation is not itself proof that its receiver/expression is a
        # data structure. Materialize a structure only when the saved Java type was
        # independently declared and has observable fields. The write fact remains.
        declaration_source_scope = str(container.get("source_scope") or "unknown_code") if container else "unknown_code"
        observation_source_scope = str(
            props.get("observation_source_scope")
            or props.get("source_scope")
            or (_source_scope_for_file(f.evidence[0].file_path) if f.evidence else "unknown_code")
        )
        if not container or not fields or declaration_source_scope == "test_code" or observation_source_scope == "test_code":
            continue
        target = str(container.get("storage_target") or props.get("storage_target") or saved_object or "unknown").strip()
        if target == "unknown" or any(ch in target for ch in "(){};=\n\r"):
            continue
        storage_kind = str(props.get("storage_kind") or "storage")
        structure_key = (storage_kind, target, str(container.get("fqcn") or saved_object))
        if structure_key in emitted_structure_keys:
            continue
        emitted_structure_keys.add(structure_key)
        struct_seq += 1
        facts.append(_persistent_structure_fact(
            f"persistent_structure_{struct_seq:06d}", ctx=ctx,
            storage_kind=storage_kind, storage_target=target,
            container_kind="saved_object", container_name=saved_object, fields=fields,
            source_repositories=repo_entity_types.get(saved_object, []),
            source_scope=observation_source_scope, declaration_source_scope=declaration_source_scope,
            observation_source_scope=observation_source_scope, container_fqcn=container.get("fqcn"),
            model_annotation=container.get("model_annotation"), model_annotation_args=container.get("model_annotation_args"),
            super_types=container.get("super_types") or [],
            evidence=f.evidence,
        ))
    progress("persistent_structure_from_writes", "done", {"persistent_structure_count": struct_seq})

    progress("method_attribute_mapping_phase", "running", {"method_count": len(methods)})
    for op, mi in sorted(methods.items()):
        body = mi.get("body") or ""
        var_types = mi.get("var_types") or {}
        bindings = _setter_bindings_any_source(body, mi) + _builder_bindings_any_source(body, mi) + _direct_assignment_bindings(mi)
        for b in bindings:
            target_field = str(b.get("target_field") or "") or None
            target_var = str(b.get("target_variable") or "") or None
            target_container = _simple_type_name(var_types.get(target_var)) if target_var else _simple_type_name(mi.get("return_type"))
            expr = str(b.get("source_expression") or "")
            source_fields = _extract_getter_source_fields(expr, mi)
            expr_kind = _expression_kind_for_expression(expr, source_fields, target_field)
            mapping_kind = _mapping_kind_for_expression(str(b.get("kind") or ""), expr, source_fields)
            if source_fields and len(source_fields) == 1 and expr_kind in {"same_name_assignment", "direct_getter_assignment", "direct_field_assignment"}:
                sf = source_fields[0]
                map_seq += 1
                facts.append(_attribute_mapping_fact(
                    f"attribute_mapping_{map_seq:06d}", ctx=ctx, mi=mi,
                    source_container=sf.get("container"), source_field=sf.get("field"),
                    target_container=target_container, target_field=target_field,
                    mapping_kind=mapping_kind, expression=str(b.get("expression") or expr),
                    expression_kind=expr_kind,
                ))
            elif source_fields:
                der_seq += 1
                facts.append(_attribute_derivation_fact(
                    f"attribute_derivation_{der_seq:06d}", ctx=ctx, mi=mi,
                    source_fields=source_fields, target_container=target_container,
                    target_field=target_field, derivation_kind="expression" if mapping_kind == "expression" else mapping_kind,
                    expression=str(b.get("expression") or expr), expression_kind=expr_kind,
                ))
            elif target_field and target_container and target_container != "unknown":
                gap_seq += 1
                gap_kind = "source_expression_not_resolved"
                facts.append(_data_model_lineage_gap_fact(
                    f"data_model_lineage_gap_{gap_seq:06d}", ctx=ctx,
                    gap_kind=gap_kind, operation=op,
                    container=target_container, field=target_field,
                    reason="target field is assigned, but source expression was not resolved by the fast profile",
                    missing_links=["source expression not resolved", "possible constant/default/method call/dynamic mapping"],
                    evidence=_op_file_evidence(mi, "java_data_model_lineage_gap"),
                ))
        constructor_facts, map_seq, der_seq, gap_seq = _constructor_mappings_for_method(
            mi, constructor_container_index, ctx, map_seq, der_seq, gap_seq,
            diagnostics=constructor_diagnostics,
        )
        facts.extend(constructor_facts)
    progress("method_attribute_mapping_phase", "done", {"attribute_mapping_count": map_seq, "attribute_derivation_count": der_seq, "gap_count": gap_seq, "fact_count": len(facts)})

    progress("mapstruct_annotation_phase", "running")
    ms_facts, map_seq = _mapstruct_annotation_facts(files, ctx=ctx, start_seq=map_seq)
    facts.extend(ms_facts)
    progress("mapstruct_annotation_phase", "done", {"fact_count": len(ms_facts), "attribute_mapping_count": map_seq})

    progress("mapper_save_lineage_phase", "running")
    lineage_seq = sum(1 for f in facts if f.fact_type == "source_to_storage_lineage")
    mapper_save_facts, lineage_seq, gap_seq = _emit_mapper_save_lineage_facts(
        ctx=ctx, methods=methods, mapper_signatures=mapper_signatures, container_by_name=container_by_name,
        start_lineage_seq=lineage_seq, start_gap_seq=gap_seq,
    )
    facts.extend(mapper_save_facts)
    progress("mapper_save_lineage_phase", "done", {"fact_count": len(mapper_save_facts), "lineage_count": lineage_seq, "gap_count": gap_seq})

    progress("gap_finalization", "running")
    sql_files = [x for x in files if x.suffix.lower() == ".sql"]
    if sql_files:
        gap_seq += 1
        facts.append(_data_model_lineage_gap_fact(
            f"data_model_lineage_gap_{gap_seq:06d}", ctx=ctx,
            gap_kind="sql_lineage_unresolved", operation=None, container="sql", field=None,
            reason="SQL files are scanned, but complex SQL-to-attribute lineage may be unresolved in the fast profile",
            missing_links=["complex SQL mappings may require SQL-specific deep analysis"],
            evidence=[EvidenceRef(file_path=str(sql_files[0]), extractor="java_data_model_lineage_gap")],
        ))

    if not repo_entity_types:
        gap_seq += 1
        facts.append(_data_model_lineage_gap_fact(
            f"data_model_lineage_gap_{gap_seq:06d}", ctx=ctx,
            gap_kind="repository_entity_type_unknown", operation=None, container="repository", field=None,
            reason="No JPA/Crud repository generic entity type was resolved in this repository",
            missing_links=["repository entity generic type not found"],
            evidence=[],
        ))
    progress("gap_finalization", "done", {"gap_count": gap_seq})

    progress("status_build", "running", {"fact_count": len(facts)})
    fact_counts = Counter(f.fact_type for f in facts)
    gap_counts = Counter(str((f.properties or {}).get("gap_kind")) for f in facts if f.fact_type == "data_model_lineage_gap")
    status = {
        "requested": True,
        "mode": "source_only_fast_data_model_lineage_v2",
        "files_scanned": len([x for x in files if x.suffix.lower() in {".java", ".sql"}]),
        "classes_indexed": len(class_infos),
        "methods_indexed": len(methods),
        "containers_indexed": len(containers),
        "repository_entity_types_indexed": sum(len(v) for v in repo_entity_types.values()),
        "mapper_signatures_indexed": sum(len(v) for v in mapper_signatures.values()),
        "facts_by_type": dict(sorted(fact_counts.items())),
        "gap_kind_counts": dict(sorted(gap_counts.items())),
        "attribute_occurrences_extracted": fact_counts.get("attribute_occurrence", 0),
        "persistent_structures_extracted": fact_counts.get("persistent_structure", 0),
        **inheritance_status,
        **descendant_status,
        **effective_field_status,
        **effective_association_status,
        **bounded_path_status,
        "attribute_mappings_extracted": fact_counts.get("attribute_mapping", 0),
        "attribute_derivations_extracted": fact_counts.get("attribute_derivation", 0),
        "source_to_storage_lineages_extracted": fact_counts.get("source_to_storage_lineage", 0),
        "data_model_lineage_gaps_extracted": fact_counts.get("data_model_lineage_gap", 0),
        "persistence_lineage_status": persistence_status,
        "reused_persistence_lineage": reused_persistence_lineage,
        "persistence_facts_included": include_persistence_facts,
        "constructor_resolution": dict(sorted(constructor_diagnostics.items())),
        "progress_events": phase_events,
        "elapsed_ms": int((time.perf_counter() - started) * 1000),
        "warnings": warnings,
    }
    progress("done", "done", {"fact_count": len(facts), "elapsed_ms": status["elapsed_ms"]})
    return facts, status

def build_java_traceability_facts(files: list[Path], flow_facts: list[Fact]) -> tuple[list[Fact], dict[str, Any]]:
    """Build targeted interprocedural traceability evidence around ingress, outbound and persistence.

    This is intentionally not a full Java data-flow engine. It builds practical evidence
    for technical source traceability:
    - confirmed ingress/data origins;
    - resolved method calls with argument bindings;
    - storage read/write/mutation classification;
    - aggregate traces from origin to outbound/persistence;
    - outbound/persistence-only traces when no origin is proven.

    v0.23.62 makes the graph build bounded and index-driven. The scanner still emits
    candidate method-call evidence, but receiver resolution no longer performs repeated
    whole-repository scans for every call expression.
    """
    phase_timings: dict[str, float] = {}

    def timed(name: str, fn):
        start = time.perf_counter()
        value = fn()
        phase_timings[name] = round(time.perf_counter() - start, 4)
        return value

    methods, class_fields, class_infos, warnings = timed("method_index", lambda: _build_method_index(files))
    origins = timed("origin_detection", lambda: _detect_origins(methods))
    calls = timed("bounded_call_graph", lambda: _build_call_facts(methods, class_fields, class_infos))
    storage_accesses = timed("storage_access_detection", lambda: _build_storage_facts(methods))
    jooq_batch_bind_facts = timed("jooq_batch_bind_mapping_detection", lambda: _fast_local_jooq_batch_bind_mappings(methods))

    source_to_sink = [f for f in flow_facts if f.fact_type == "source_to_sink_flow"]
    field_flows = [f for f in flow_facts if f.fact_type == "field_identifier_flow"]
    trace_facts, trace_status = timed("origin_to_sink_trace_build", lambda: _build_trace_facts(
        flow_facts=source_to_sink,
        field_flow_facts=field_flows,
        storage_accesses=storage_accesses,
        methods=methods,
        origins=origins,
        calls=calls,
    ))
    field_lineage_facts, field_lineage_status = timed("field_lineage_build", lambda: _build_field_lineage_facts(
        files=files,
        methods=methods,
        origins=origins,
        calls=calls,
        storage_accesses=storage_accesses,
        flow_facts=source_to_sink,
        field_flow_facts=field_flows,
        trace_facts=trace_facts,
    ))
    output_provenance_facts, output_provenance_status = timed("output_provenance_build", lambda: _build_output_field_provenance_facts(
        files=files,
        methods=methods,
        class_fields=class_fields,
        class_infos=class_infos,
        origins=origins,
        storage_accesses=storage_accesses,
        flow_facts=source_to_sink,
        field_lineage_facts=field_lineage_facts,
    ))
    call_chain_diagnostic_facts, call_chain_diagnostic_status = timed("call_chain_diagnostics", lambda: _build_call_chain_diagnostic_facts(
        methods=methods,
        calls=calls,
        flow_facts=source_to_sink,
        trace_facts=trace_facts,
    ))

    facts: list[Fact] = []
    facts.extend(_origin_facts(origins, methods))
    facts.extend(_call_facts(calls))
    facts.extend(_storage_facts(storage_accesses))
    facts.extend(trace_facts)
    facts.extend(field_lineage_facts)
    facts.extend(output_provenance_facts)
    facts.extend(call_chain_diagnostic_facts)
    facts.extend(jooq_batch_bind_facts)

    storage_counts = Counter(str(x.get("access_kind")) for x in storage_accesses)
    raw_method_call_expressions = sum(len(mi.get("method_calls") or []) for mi in methods.values())
    resolution_kind_counts = Counter(str(c.get("resolution_kind") or "unknown") for c in calls)
    argument_relation_counts = Counter(str(c.get("argument_relation") or "unknown") for c in calls)
    payload_edges = sum(
        1 for c in calls for b in (c.get("argument_bindings") or [])
        if b.get("caller_source_parameter") and str(b.get("relation") or "") in {"same_object", "via_local_variable", "field_extracted"}
    )
    status = {
        "requested": True,
        "mode": "source_only_spring_traceability_graph",
        "files_scanned": len([x for x in files if x.suffix.lower() == ".java"]),
        "classes_indexed": len(class_infos),
        "methods_indexed": len(methods),
        "ingress_extracted": len(origins),
        "method_calls_extracted": len(calls),
        "storage_accesses_extracted": len(storage_accesses),
        "storage_access_counts": dict(sorted(storage_counts.items())),
        "jooq_batch_bind_mappings_extracted": len(jooq_batch_bind_facts),
        **trace_status,
        **field_lineage_status,
        **output_provenance_status,
        **call_chain_diagnostic_status,
        "traceability_diagnostics": {
            "phase_timings_seconds": phase_timings,
            "raw_method_call_expressions": raw_method_call_expressions,
            "resolved_method_call_edges": len(calls),
            "unresolved_or_pruned_method_call_expressions": max(0, raw_method_call_expressions - len(calls)),
            "resolution_kind_counts": dict(sorted(resolution_kind_counts.items())),
            "argument_relation_counts": dict(sorted(argument_relation_counts.items())),
            "payload_argument_edges": payload_edges,
            "max_trace_depth": TRACEABILITY_MAX_DEPTH,
            "max_receiver_candidates_per_call": TRACEABILITY_MAX_RECEIVER_CANDIDATES_PER_CALL,
            "graph_build_mode": "bounded_index_driven",
            "graph_build_policy": "index-driven receiver resolution; no per-call whole-repository operation-prefix scans; interface/name heuristics are capped",
        },
        "warnings": warnings,
    }
    return facts, status
