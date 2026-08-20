from __future__ import annotations

import re
from collections import defaultdict, Counter
from pathlib import Path
from typing import Any

from code_analyzer_core.models import Fact, EvidenceRef
from code_analyzer_core.scanners.java_trace_common import *
from code_analyzer_core.scanners.java_call_observations import *
from code_analyzer_core.evidence_contract import maturity_props as _maturity_props
from code_analyzer_core.utils import read_text, line_number_for_offset, normalize_name
from code_analyzer_core.scanners.java_syntax import parse_java_files
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
    _return_expressions_from_method_info,
    _return_expressions_from_syntax,
)


def _extract_all_schema_fields(files: list[Path]) -> dict[str, list[dict[str, str]]]:
    """Best-effort Java DTO field index for field-level lineage using Tree-sitter.

    This keeps all fields while relying on Tree-sitter-provided structural facts.
    Getter/setter schema hints are still detected by domain-patterns over exact
    Tree-sitter class text, because those are product evidence heuristics rather
    than Java boundary parsing.
    """
    schemas: dict[str, list[dict[str, str]]] = defaultdict(list)
    seen: dict[str, set[str]] = defaultdict(set)
    parsed_files, _warnings = parse_java_files(files)
    for parsed in parsed_files:
        for cls in parsed.classes:
            class_name = cls.name
            for field in cls.fields:
                fname = field.name
                if not fname or fname in {"serialVersionUID"} or fname in seen[class_name]:
                    continue
                seen[class_name].add(fname)
                info = _java_type_details(field.type)
                schemas[class_name].append({"name": fname, "type": info.get("type"), "raw_type": info.get("raw_type"), "container_kind": info.get("container_kind"), "element_type": info.get("element_type"), "role": _field_role(fname)})

            # Generated persistence classes often expose setX/getX methods instead
            # of fields. Tree-sitter now owns these method boundaries and
            # signatures; the remaining rule is only the product-level schema hint
            # that accessor-style methods can represent generated fields.
            for method in cls.methods:
                mname = method.name or ""
                if mname.startswith("set") and len(mname) > 3 and len(method.params) == 1:
                    fname = _normalize_field_name(mname[3:]) or mname[3:]
                    if not fname or fname in seen[class_name]:
                        continue
                    seen[class_name].add(fname)
                    info = _java_type_details(method.params[0].type)
                    schemas[class_name].append({"name": fname, "type": info.get("type"), "raw_type": info.get("raw_type"), "container_kind": info.get("container_kind"), "element_type": info.get("element_type"), "role": _field_role(fname), "schema_hint": "setter_method"})
                    continue
                getter_prefix = None
                if mname.startswith("get") and len(mname) > 3 and not method.params and mname != "getClass":
                    getter_prefix = "get"
                elif mname.startswith("is") and len(mname) > 2 and not method.params:
                    getter_prefix = "is"
                if getter_prefix:
                    raw_field = mname[len(getter_prefix):]
                    fname = _normalize_field_name(raw_field) or raw_field
                    if not fname or fname in seen[class_name]:
                        continue
                    seen[class_name].add(fname)
                    info = _java_type_details(method.return_type)
                    schemas[class_name].append({"name": fname, "type": info.get("type"), "raw_type": info.get("raw_type"), "container_kind": info.get("container_kind"), "element_type": info.get("element_type"), "role": _field_role(fname), "schema_hint": "getter_method"})
    return {k: v for k, v in schemas.items() if v}


def _fields_for_type(schema_fields: dict[str, list[dict[str, str]]], type_name: str | None) -> list[dict[str, str]]:
    simple = _simple_type_name(type_name)
    return list(schema_fields.get(simple) or [])


def _field_names_for_type(schema_fields: dict[str, list[dict[str, str]]], type_name: str | None) -> list[str]:
    return [str(x.get("name")) for x in _fields_for_type(schema_fields, type_name) if x.get("name")]


def _nested_field_parts(field: str | None) -> tuple[str | None, str | None]:
    value = str(field or "").strip()
    if not value:
        return None, None
    if "[*]." in value:
        head, tail = value.split("[*].", 1)
        return head, tail
    if "." in value:
        head, tail = value.split(".", 1)
        return head, tail
    return value, None


def _leaf_field_name(field: str | None) -> str:
    _container, nested = _nested_field_parts(field)
    if nested:
        return _leaf_field_name(nested)
    return str(field or "")


def _nested_child_fields(schema_fields: dict[str, list[dict[str, str]]], field_info: dict[str, Any]) -> tuple[str | None, str, list[dict[str, str]]]:
    container_kind = str(field_info.get("container_kind") or "object")
    element_type = str(field_info.get("element_type") or field_info.get("type") or "")
    if not element_type or element_type == "unknown":
        return None, container_kind, []
    children = _fields_for_type(schema_fields, element_type)
    return element_type, container_kind, children


def _published_nested_field(container_field: str, child_field: str, container_kind: str | None = None) -> str:
    return f"{container_field}[*].{child_field}" if container_kind in {"collection", "array"} else f"{container_field}.{child_field}"


def _origin_field_for_nested(container_field: str | None, child_field: str, container_kind: str | None = None) -> str:
    if container_field and container_field != child_field:
        return _published_nested_field(container_field, child_field, container_kind)
    return child_field


def _getter_field_expr(expr: str, source_param: str) -> str | None:
    return _getter_field(_clean_expression(expr), source_param)


def _normalize_field_name(raw: str | None) -> str | None:
    return _normalize_mapping_field_name(raw)


def _setter_bindings(body: str, *, source_param: str | None = None, method_info: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    return _tree_sitter_setter_bindings(method_info, source_param=source_param)


def _builder_bindings(body: str, *, source_param: str | None = None, method_info: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    return _tree_sitter_builder_bindings(method_info, source_param=source_param)


def _return_expressions(body: str) -> list[str]:
    # Compatibility helper for older local call sites. Return statements are now
    # extracted by Tree-sitter through a synthetic method, not by scanning return text.
    from code_analyzer_core.scanners.java_flow_builder import _synthetic_method_for_body
    method = _synthetic_method_for_body(body or "")
    return _return_expressions_from_syntax(method.returns if method else ())


def _field_lineage_trace_status(trace_status: str | None, *, explicit: bool = True) -> str:
    """Strict internal status for field lineage.

    Only explicit confirmed traces are hard evidence. Older non-confirmed
    statuses are navigation context and become unresolved at this layer.
    """
    return "confirmed" if str(trace_status or "") == "confirmed" and explicit else "unresolved"


def _target_boundary_for_sink(sink_kind: str | None) -> tuple[str, str]:
    sk = str(sink_kind or "unknown")
    if sk == "kafka":
        return "kafka", "published_to_kafka"
    if sk in {"http_client", "web_client"}:
        return "http_client", "sent_to_http_client"
    if sk == "rest_response":
        return "rest_response", "returned_in_response"
    return sk, "sent_to_outbound"


def _source_boundary_for_origin(origin: dict[str, Any]) -> str:
    kind = str(origin.get("origin_kind") or origin.get("ingress_kind") or "unknown")
    if kind == "rest_controller":
        return "rest_ingress"
    if kind == "kafka_listener":
        return "kafka_ingress"
    if kind == "db_source_read":
        return "db_source_read"
    return kind


def _call_relation_quality(call_path: list[dict[str, Any]]) -> str:
    relations: list[str] = []
    for call in call_path:
        if call.get("argument_relation"):
            relations.append(str(call["argument_relation"]))
        for b in call.get("argument_bindings") or []:
            if b.get("relation"):
                relations.append(str(b["relation"]))
    return _relation_quality(relations)


def _calls_for_trace(trace_props: dict[str, Any], calls_by_id: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    refs = [str(x) for x in (trace_props.get("evidence_refs") or [])]
    return [calls_by_id[x] for x in refs if x in calls_by_id]


def _origin_for_trace(trace_props: dict[str, Any], origins_by_id: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    for key in ["ingress_id", "origin_id"]:
        val = trace_props.get(key)
        if val and str(val) in origins_by_id:
            return origins_by_id[str(val)]
    return None


def _lineage_fact(
    *,
    lineage_id: str,
    lineage_type: str,
    source_boundary: str,
    source_operation: str,
    source_payload: str,
    source_parameter: str | None,
    source_field: str,
    target_boundary: str | None,
    target_operation: str | None,
    target_payload: str | None,
    target_field: str | None,
    field_role: str,
    trace_status: str,
    path: list[str],
    evidence_refs: list[str],
    missing_links: list[str],
    evidence: list[EvidenceRef],
    extra: dict[str, Any] | None = None,
) -> Fact:
    props: dict[str, Any] = {
        "field_lineage_id": lineage_id,
        "lineage_type": lineage_type,
        "source_boundary": source_boundary,
        "source_operation": source_operation,
        "source_payload": source_payload,
        "source_parameter": source_parameter,
        "source_field": source_field,
        "target_boundary": target_boundary,
        "target_operation": target_operation,
        "target_payload": target_payload,
        "target_field": target_field,
        "path": path,
        "field_role": field_role,
        "missing_links": missing_links,
        "evidence_refs": [x for x in evidence_refs if x],
    }
    props.update(_maturity_props({
        "source_boundary": "confirmed" if source_boundary and source_boundary != "unknown" else "unresolved",
        "field_mapping": "confirmed" if trace_status == "confirmed" and not missing_links else "unresolved",
        "end_to_end_trace": "confirmed" if trace_status == "confirmed" else "unresolved",
    }, notes=["field_lineage uses strict confirmed/unresolved semantics; non-confirmed trace statuses are navigation only"]))
    if extra:
        props.update(extra)
    title_target = f" -> {target_boundary}.{target_field}" if target_boundary else ""
    return Fact(
        fact_type="field_lineage",
        name=f"{source_operation}: {source_payload}.{source_field}{title_target}",
        properties=props,
        evidence=evidence,
    )


def _build_field_lineage_facts(
    *,
    files: list[Path],
    methods: dict[str, dict[str, Any]],
    origins: list[dict[str, Any]],
    calls: list[dict[str, Any]],
    storage_accesses: list[dict[str, Any]],
    flow_facts: list[Fact],
    field_flow_facts: list[Fact],
    trace_facts: list[Fact],
) -> tuple[list[Fact], dict[str, Any]]:
    schema_fields = _extract_all_schema_fields(files)
    facts: list[Fact] = []
    seq = 0
    seen: set[tuple[Any, ...]] = set()

    origins_by_id: dict[str, dict[str, Any]] = {}
    for origin in origins:
        if origin.get("ingress_id"):
            origins_by_id[str(origin["ingress_id"])] = origin
        if origin.get("origin_id"):
            origins_by_id[str(origin["origin_id"])] = origin
    calls_by_id = {str(c.get("call_id")): c for c in calls if c.get("call_id")}
    flows_by_id = {str((f.properties or {}).get("flow_id")): f for f in flow_facts if (f.properties or {}).get("flow_id")}
    field_flows_by_flow: dict[str, list[Fact]] = defaultdict(list)
    for ff in field_flow_facts:
        props = ff.properties or {}
        if props.get("related_flow_id"):
            field_flows_by_flow[str(props["related_flow_id"])].append(ff)
    storage_by_id = {str(s.get("storage_access_id")): s for s in storage_accesses if s.get("storage_access_id")}

    def add_fact(**kwargs: Any) -> None:
        nonlocal seq
        key = (
            kwargs.get("lineage_type"), kwargs.get("source_operation"), kwargs.get("source_payload"),
            kwargs.get("source_parameter"), kwargs.get("source_field"), kwargs.get("target_boundary"),
            kwargs.get("target_operation"), kwargs.get("target_payload"), kwargs.get("target_field"),
            kwargs.get("field_role"), tuple(kwargs.get("path") or []),
        )
        if key in seen:
            return
        seen.add(key)
        if "trace_status" not in kwargs:
            kwargs["trace_status"] = "unresolved"
        seq += 1
        facts.append(_lineage_fact(lineage_id=f"field_lineage_{seq:06d}", **kwargs))

    # 1. Input fields received at real payload origins.
    for origin in origins:
        if not origin.get("is_payload_origin", True):
            continue
        source_payload = str(origin.get("payload_type") or "unknown")
        source_param = origin.get("payload_parameter")
        if not source_param or source_payload == "unknown":
            continue
        fields = _fields_for_type(schema_fields, source_payload)
        mi = methods.get(str(origin.get("operation") or ""))
        evidence = _op_file_evidence(mi, "java_field_lineage_ingress") if mi else []
        for f in fields:
            field_name = str(f.get("name") or "")
            if not field_name:
                continue
            add_fact(
                lineage_type="ingress_field_received",
                source_boundary=_source_boundary_for_origin(origin),
                source_operation=str(origin.get("operation") or ""),
                source_payload=source_payload,
                source_parameter=str(source_param),
                source_field=field_name,
                target_boundary=None,
                target_operation=None,
                target_payload=None,
                target_field=None,
                field_role="input_attribute_received",
                trace_status="confirmed",
                path=[f"{source_param}.{field_name}"],
                evidence_refs=[str(origin.get("ingress_id") or "")],
                missing_links=[],
                evidence=evidence,
                extra={"source_field_role": f.get("role"), "source_field_type": f.get("type")},
            )

    # 2. Fields used for service/lookup calls from the ingress operation. Passing the
    # whole request to a service is lookup/use evidence, not dissemination evidence.
    for origin in origins:
        if not origin.get("is_payload_origin", True):
            continue
        op = str(origin.get("operation") or "")
        source_payload = str(origin.get("payload_type") or "unknown")
        source_param = str(origin.get("payload_parameter") or "")
        if not op or not source_param:
            continue
        fields = _fields_for_type(schema_fields, source_payload)
        if not fields:
            continue
        mi = methods.get(op)
        evidence = _op_file_evidence(mi, "java_field_lineage_lookup") if mi else []
        lookup_calls: list[dict[str, Any]] = []
        for call in calls:
            if call.get("caller_operation_id") != op:
                continue
            bindings = call.get("argument_bindings") or []
            lookup_calls.append({
                "call_id": call.get("call_id"),
                "target_operation": call.get("callee_operation_id") or call.get("callee_method"),
                "receiver": call.get("receiver_expression"),
                "bindings": bindings,
                "synthetic": False,
            })
        # Fallback: unresolved interface calls are still field-use evidence when
        # the ingress request is passed to a service/repository-like method. This
        # must not be treated as output dissemination.
        for cm in (mi.get("method_calls") or []) if mi else []:
            receiver = cm.get("receiver") or ""
            method = cm.get("method") or ""
            receiver_low = receiver.lower()
            if any(tok in receiver_low for tok in ["kafka", "resttemplate", "webclient"]):
                continue
            args = list(cm.get("args") or [])
            if not any(_contains_symbol(a, source_param) for a in args):
                continue
            if any(x.get("target_operation") == f"{receiver}.{method}" for x in lookup_calls):
                continue
            lookup_calls.append({
                "call_id": None,
                "target_operation": f"{receiver}.{method}",
                "receiver": receiver,
                "bindings": [{"caller_expression": a, "relation": "same_object" if a == source_param else "field_extracted"} for a in args],
                "synthetic": True,
            })
        for call in lookup_calls:
            if str(call.get("receiver") or "").lower() in {"kafkatemplate", "resttemplate"}:
                continue
            bindings = call.get("bindings") or []
            whole_request = any(_clean_expression(b.get("caller_expression")) == source_param for b in bindings)
            explicit_fields = set()
            for b in bindings:
                expr = _clean_expression(b.get("caller_expression"))
                gf = _getter_field_expr(expr, source_param)
                if gf:
                    explicit_fields.add(gf)
            if not whole_request and not explicit_fields:
                continue
            for f in fields:
                field_name = str(f.get("name") or "")
                if not field_name:
                    continue
                if explicit_fields and field_name not in explicit_fields:
                    continue
                add_fact(
                    lineage_type="ingress_field_used_for_lookup",
                    source_boundary=_source_boundary_for_origin(origin),
                    source_operation=op,
                    source_payload=source_payload,
                    source_parameter=source_param,
                    source_field=field_name,
                    target_boundary="service_or_lookup",
                    target_operation=str(call.get("target_operation") or "service call"),
                    target_payload=None,
                    target_field=None,
                    field_role="input_attribute_used_for_lookup",
                    trace_status="confirmed" if explicit_fields else "unresolved",
                    path=[f"{source_param}.{field_name}", str(call.get("target_operation") or "service call")],
                    evidence_refs=[str(origin.get("ingress_id") or ""), str(call.get("call_id") or "")],
                    missing_links=["field passed as part of whole request object; no outbound target field implied"] if whole_request and not explicit_fields else [],
                    evidence=evidence,
                    extra={"lookup_operation": call.get("target_operation"), "returned_or_published": False, "source_field_role": f.get("role")},
                )

    # 3. Direct REST response field mappings in ingress methods. Only explicit
    # target-field evidence creates returned_in_response lineage.
    for origin in origins:
        if origin.get("origin_kind") != "rest_controller" or not origin.get("is_payload_origin", True):
            continue
        op = str(origin.get("operation") or "")
        mi = methods.get(op)
        if not mi:
            continue
        source_payload = str(origin.get("payload_type") or "unknown")
        source_param = str(origin.get("payload_parameter") or "")
        returns = _return_expressions_from_method_info(mi)
        if not returns or not source_param:
            continue
        setter_bindings = _setter_bindings(mi.get("body") or "", source_param=source_param, method_info=mi) + _builder_bindings(mi.get("body") or "", source_param=source_param, method_info=mi)
        return_blob = " ".join(returns)
        evidence = _op_file_evidence(mi, "java_field_lineage_rest_response")
        for b in setter_bindings:
            target_var = b.get("target_variable")
            if target_var and not _contains_symbol(return_blob, str(target_var)):
                # Builder chains often do not expose target variable, but setter mappings
                # need the mapped object to be returned.
                continue
            add_fact(
                lineage_type="ingress_field_to_output_field",
                source_boundary=_source_boundary_for_origin(origin),
                source_operation=op,
                source_payload=source_payload,
                source_parameter=source_param,
                source_field=str(b.get("source_field") or "unknown"),
                target_boundary="rest_response",
                target_operation=op,
                target_payload="rest_response_body",
                target_field=str(b.get("target_field") or b.get("source_field") or "unknown"),
                field_role="returned_in_response",
                trace_status="confirmed",
                path=[f"{source_param}.{b.get('source_field')}", str(b.get("expression") or "field mapping"), "REST response body"],
                evidence_refs=[str(origin.get("ingress_id") or "")],
                missing_links=[],
                evidence=evidence,
                extra={"target_location": "response_body_field", "mapping_kind": b.get("kind")},
            )
        # Directly returning the request object is a confirmed pass-through response.
        for ret in returns:
            if ret == source_param:
                for f in _fields_for_type(schema_fields, source_payload):
                    field_name = str(f.get("name") or "")
                    if field_name:
                        add_fact(
                            lineage_type="ingress_field_to_output_field",
                            source_boundary=_source_boundary_for_origin(origin),
                            source_operation=op,
                            source_payload=source_payload,
                            source_parameter=source_param,
                            source_field=field_name,
                            target_boundary="rest_response",
                            target_operation=op,
                            target_payload=source_payload,
                            target_field=field_name,
                            field_role="returned_in_response",
                            trace_status="confirmed",
                            path=[f"{source_param}.{field_name}", "return request object as REST response"],
                            evidence_refs=[str(origin.get("ingress_id") or "")],
                            missing_links=[],
                            evidence=evidence,
                            extra={"target_location": "response_body_field", "mapping_kind": "same_object_response"},
                        )

    # 4. Trace-backed outbound/storage lineage. This is the main cross-boundary bridge.
    for trace_fact in trace_facts:
        tprops = trace_fact.properties or {}
        origin = _origin_for_trace(tprops, origins_by_id)
        if not origin or not origin.get("is_payload_origin", True):
            continue
        source_payload = str(origin.get("payload_type") or "unknown")
        source_param = str(origin.get("payload_parameter") or "")
        source_fields = {x["name"]: x for x in _fields_for_type(schema_fields, source_payload) if x.get("name")}
        if not source_fields:
            continue
        trace_status = str(tprops.get("trace_status") or "")
        call_path = _calls_for_trace(tprops, calls_by_id)
        relation_quality = _call_relation_quality(call_path)
        trace_id = str(tprops.get("trace_id") or "")
        terminal_op = str(tprops.get("terminal_operation_id") or tprops.get("outbound_operation_id") or tprops.get("persistence_operation_id") or "")
        terminal_mi = methods.get(terminal_op)
        terminal_body = terminal_mi.get("body") if terminal_mi else ""
        terminal_evidence = _op_file_evidence(terminal_mi, "java_field_lineage_trace") if terminal_mi else (trace_fact.evidence or [])

        if tprops.get("trace_type") == "ingress_to_outbound":
            flow_id = str(tprops.get("related_flow_id") or "")
            flow = flows_by_id.get(flow_id)
            fprops = flow.properties if flow else {}
            sink_kind = fprops.get("sink_kind") or tprops.get("sink_kind")
            target_boundary, field_role = _target_boundary_for_sink(str(sink_kind or ""))
            target_payload = str(fprops.get("payload_expression") or tprops.get("payload_expression") or "outbound_payload")
            terminal_source_param = str(fprops.get("source_parameter") or "")

            # Existing field_flow facts are target-boundary evidence for identifier-like fields.
            for ff in field_flows_by_flow.get(flow_id, []):
                ffprops = ff.properties or {}
                source_field = str(ffprops.get("source_field") or "")
                if source_field not in source_fields:
                    continue
                add_fact(
                    lineage_type="ingress_field_to_output_field",
                    source_boundary=_source_boundary_for_origin(origin),
                    source_operation=str(origin.get("operation") or ""),
                    source_payload=source_payload,
                    source_parameter=source_param,
                    source_field=source_field,
                    target_boundary=target_boundary,
                    target_operation=terminal_op,
                    target_payload=target_payload,
                    target_field=source_field,
                    field_role=field_role,
                    trace_status=_field_lineage_trace_status(trace_status, explicit=ffprops.get("propagation_status") == "confirmed_field_propagation"),
                    path=[f"{source_param}.{source_field}", *[str(c.get("callee_operation_id")) for c in call_path], f"{target_boundary}.{source_field}"],
                    evidence_refs=[str(origin.get("ingress_id") or ""), *[str(c.get("call_id") or "") for c in call_path], trace_id, flow_id, str(ffprops.get("field_flow_id") or "")],
                    missing_links=[] if trace_status == "confirmed" else ["trace is not complete"],
                    evidence=terminal_evidence,
                    extra={"target_location": "message_value_field" if target_boundary == "kafka" else "request_body_field", "same_data_chain_quality": relation_quality},
                )

            # Explicit key/header/url/body mappings in the terminal method.
            if terminal_source_param and terminal_mi:
                explicit_key_fields: set[str] = set()
                for cm in terminal_mi.get("method_calls") or []:
                    if cm.get("method") != "send":
                        continue
                    args = list(cm.get("args") or [])
                    if len(args) < 3:
                        continue
                    gf = _getter_field_expr(str(args[1]), terminal_source_param)
                    if gf:
                        explicit_key_fields.add(gf)
                for oc in terminal_mi.get("object_creations") or []:
                    if str(oc.get("type") or "").split(".")[-1] != "ProducerRecord":
                        continue
                    args = list(oc.get("args") or [])
                    if len(args) < 3:
                        continue
                    gf = _getter_field_expr(str(args[1]), terminal_source_param)
                    if gf:
                        explicit_key_fields.add(gf)
                for source_field in sorted(explicit_key_fields):
                    if source_field not in source_fields:
                        continue
                    add_fact(
                        lineage_type="ingress_field_to_output_field",
                        source_boundary=_source_boundary_for_origin(origin),
                        source_operation=str(origin.get("operation") or ""),
                        source_payload=source_payload,
                        source_parameter=source_param,
                        source_field=source_field,
                        target_boundary="kafka",
                        target_operation=terminal_op,
                        target_payload="kafka_message",
                        target_field="message_key",
                        field_role="published_to_kafka",
                        trace_status=_field_lineage_trace_status(trace_status, explicit=True),
                        path=[f"{source_param}.{source_field}", *[str(c.get("callee_operation_id")) for c in call_path], "Kafka message key"],
                        evidence_refs=[str(origin.get("ingress_id") or ""), *[str(c.get("call_id") or "") for c in call_path], trace_id, flow_id],
                        missing_links=[] if trace_status == "confirmed" else ["trace is not complete"],
                        evidence=terminal_evidence,
                        extra={"target_location": "message_key", "same_data_chain_quality": relation_quality},
                    )
                for hm in KAFKA_HEADER_RE.finditer(terminal_body):
                    gf = _getter_field_expr(hm.group("value"), terminal_source_param)
                    if gf and gf in source_fields:
                        add_fact(
                            lineage_type="ingress_field_to_output_field",
                            source_boundary=_source_boundary_for_origin(origin),
                            source_operation=str(origin.get("operation") or ""),
                            source_payload=source_payload,
                            source_parameter=source_param,
                            source_field=gf,
                            target_boundary="kafka",
                            target_operation=terminal_op,
                            target_payload="kafka_message",
                            target_field="header",
                            field_role="published_to_kafka",
                            trace_status=_field_lineage_trace_status(trace_status, explicit=True),
                            path=[f"{source_param}.{gf}", *[str(c.get("callee_operation_id")) for c in call_path], "Kafka header"],
                            evidence_refs=[str(origin.get("ingress_id") or ""), *[str(c.get("call_id") or "") for c in call_path], trace_id, flow_id],
                            missing_links=[] if trace_status == "confirmed" else ["trace is not complete"],
                            evidence=terminal_evidence,
                            extra={"target_location": "message_header", "same_data_chain_quality": relation_quality},
                        )

                # DTO body fields populated from source param and then sent to Kafka/HTTP/REST.
                setter_bindings = _setter_bindings(terminal_body, source_param=terminal_source_param, method_info=terminal_mi) + _builder_bindings(terminal_body, source_param=terminal_source_param, method_info=terminal_mi)
                for b in setter_bindings:
                    source_field = str(b.get("source_field") or "")
                    if source_field not in source_fields:
                        continue
                    target_var = b.get("target_variable")
                    if target_var and target_payload and not _contains_symbol(target_payload, str(target_var)):
                        continue
                    add_fact(
                        lineage_type="ingress_field_to_output_field",
                        source_boundary=_source_boundary_for_origin(origin),
                        source_operation=str(origin.get("operation") or ""),
                        source_payload=source_payload,
                        source_parameter=source_param,
                        source_field=source_field,
                        target_boundary=target_boundary,
                        target_operation=terminal_op,
                        target_payload=target_payload,
                        target_field=str(b.get("target_field") or source_field),
                        field_role=field_role,
                        trace_status=_field_lineage_trace_status(trace_status, explicit=True),
                        path=[f"{source_param}.{source_field}", *[str(c.get("callee_operation_id")) for c in call_path], str(b.get("expression") or "field mapping"), f"{target_boundary}.{b.get('target_field') or source_field}"],
                        evidence_refs=[str(origin.get("ingress_id") or ""), *[str(c.get("call_id") or "") for c in call_path], trace_id, flow_id],
                        missing_links=[] if trace_status == "confirmed" else ["trace is not complete"],
                        evidence=terminal_evidence,
                        extra={"target_location": "request_body_field" if target_boundary == "http_client" else "message_value_field", "mapping_kind": b.get("kind"), "same_data_chain_quality": relation_quality},
                    )

                # HTTP URL/path/query parameter lineage.
                if target_boundary == "http_client":
                    url_expr = str(fprops.get("target_expression") or "")
                    gf = _getter_field_expr(url_expr, terminal_source_param)
                    if gf and gf in source_fields:
                        add_fact(
                            lineage_type="ingress_field_to_output_field",
                            source_boundary=_source_boundary_for_origin(origin),
                            source_operation=str(origin.get("operation") or ""),
                            source_payload=source_payload,
                            source_parameter=source_param,
                            source_field=gf,
                            target_boundary="http_client",
                            target_operation=terminal_op,
                            target_payload="url_or_query",
                            target_field="url_or_query_param",
                            field_role="sent_to_http_client",
                            trace_status=_field_lineage_trace_status(trace_status, explicit=True),
                            path=[f"{source_param}.{gf}", *[str(c.get("callee_operation_id")) for c in call_path], "HTTP URL/path/query"],
                            evidence_refs=[str(origin.get("ingress_id") or ""), *[str(c.get("call_id") or "") for c in call_path], trace_id, flow_id],
                            missing_links=[] if trace_status == "confirmed" else ["trace is not complete"],
                            evidence=terminal_evidence,
                            extra={"target_location": "url_or_query", "same_data_chain_quality": relation_quality},
                        )

        if tprops.get("trace_type") == "ingress_to_persistence":
            storage_id = str(tprops.get("storage_access_id") or "")
            access = storage_by_id.get(storage_id)
            if not access:
                continue
            if access.get("access_kind") != "write":
                # Mutation/delete may use a field as a selector, but it is not persisted.
                continue
            payload = _clean_expression(access.get("payload_expression"))
            terminal_params = terminal_mi.get("param_names") if terminal_mi else set()
            terminal_source_param = None
            for param in terminal_params or []:
                if _contains_symbol(payload, str(param)):
                    terminal_source_param = str(param)
                    break
            if not terminal_source_param and terminal_mi:
                sp, _, _ = _source_param_for_payload(payload, terminal_mi.get("param_names") or set(), terminal_mi.get("assignments") or {})
                terminal_source_param = sp
            if not terminal_source_param:
                continue
            setter_bindings = _setter_bindings(terminal_body or "", source_param=terminal_source_param, method_info=terminal_mi) + _builder_bindings(terminal_body or "", source_param=terminal_source_param, method_info=terminal_mi)
            explicit = False
            for b in setter_bindings:
                source_field = str(b.get("source_field") or "")
                if source_field not in source_fields:
                    continue
                target_var = b.get("target_variable")
                if target_var and payload and not _contains_symbol(payload, str(target_var)):
                    continue
                explicit = True
                add_fact(
                    lineage_type="ingress_field_to_output_field",
                    source_boundary=_source_boundary_for_origin(origin),
                    source_operation=str(origin.get("operation") or ""),
                    source_payload=source_payload,
                    source_parameter=source_param,
                    source_field=source_field,
                    target_boundary="storage",
                    target_operation=terminal_op,
                    target_payload=payload,
                    target_field=str(b.get("target_field") or source_field),
                    field_role="persisted_to_storage",
                    trace_status=_field_lineage_trace_status(trace_status, explicit=True),
                    path=[f"{source_param}.{source_field}", *[str(c.get("callee_operation_id")) for c in call_path], str(b.get("expression") or "field mapping"), f"storage.{b.get('target_field') or source_field}"],
                    evidence_refs=[str(origin.get("ingress_id") or ""), *[str(c.get("call_id") or "") for c in call_path], trace_id, storage_id],
                    missing_links=[] if trace_status == "confirmed" else ["trace is not complete"],
                    evidence=terminal_evidence,
                    extra={"target_location": "storage_payload_field", "storage_access_id": storage_id, "table_or_repository": access.get("table_or_repository"), "same_data_chain_quality": relation_quality},
                )
            if not explicit and payload == terminal_source_param:
                # Whole object is saved. This is valid field-level persisted evidence,
                # but unresolved because exact column mapping is repository/JPA-level.
                for field_name, f in source_fields.items():
                    add_fact(
                        lineage_type="ingress_field_to_output_field",
                        source_boundary=_source_boundary_for_origin(origin),
                        source_operation=str(origin.get("operation") or ""),
                        source_payload=source_payload,
                        source_parameter=source_param,
                        source_field=field_name,
                        target_boundary="storage",
                        target_operation=terminal_op,
                        target_payload=payload,
                        target_field=field_name,
                        field_role="persisted_to_storage",
                        trace_status="unresolved",
                        path=[f"{source_param}.{field_name}", *[str(c.get("callee_operation_id")) for c in call_path], f"repository.save({payload}).{field_name}"],
                        evidence_refs=[str(origin.get("ingress_id") or ""), *[str(c.get("call_id") or "") for c in call_path], trace_id, storage_id],
                        missing_links=["exact ORM/JDBC column mapping is not available"],
                        evidence=terminal_evidence,
                        extra={"target_location": "storage_payload_field", "storage_access_id": storage_id, "table_or_repository": access.get("table_or_repository"), "same_data_chain_quality": relation_quality, "source_field_role": f.get("role")},
                    )

    role_counts = Counter(str((f.properties or {}).get("field_role")) for f in facts)
    lineage_counts = Counter(str((f.properties or {}).get("lineage_type")) for f in facts)
    boundary_counts = Counter(str((f.properties or {}).get("target_boundary")) for f in facts if (f.properties or {}).get("target_boundary"))
    return facts, {
        "field_lineages_extracted": len(facts),
        "field_lineage_role_counts": dict(sorted(role_counts.items())),
        "field_lineage_type_counts": dict(sorted(lineage_counts.items())),
        "field_lineage_target_boundary_counts": dict(sorted(boundary_counts.items())),
        "schema_types_indexed": len(schema_fields),
    }

__all__ = [name for name in globals() if name.startswith("_") or name.startswith("build_java")]
