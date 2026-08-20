from __future__ import annotations

import re
from collections import defaultdict, Counter
from pathlib import Path
from typing import Any

from code_analyzer_core.models import Fact, EvidenceRef
from code_analyzer_core.scanners.java_syntax import method_syntax_dict
from code_analyzer_core.scanners.java_trace_common import *
from code_analyzer_core.scanners.java_call_observations import *
from code_analyzer_core.evidence_contract import maturity_props as _maturity_props
from code_analyzer_core.utils import read_text, line_number_for_offset, normalize_name
from code_analyzer_core.scanners.java_flow_builder import (
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



OUTPUT_FIELD_ROLES = {
    "returned_in_response",
    "published_to_kafka",
    "sent_to_http_client",
    "persisted_to_storage",
}

def _output_boundary_from_field_role(role: str | None, target_boundary: str | None = None) -> str:
    rb = str(target_boundary or "")
    if rb:
        return rb
    if role == "returned_in_response":
        return "rest_response"
    if role == "published_to_kafka":
        return "kafka"
    if role == "sent_to_http_client":
        return "http_client"
    if role == "persisted_to_storage":
        return "storage"
    return "unknown"


def _origin_from_source_boundary(source_boundary: str | None) -> str:
    sb = str(source_boundary or "")
    if sb == "kafka_ingress":
        return "kafka_consumed_field"
    if sb in {"rest_ingress", "rest_controller"}:
        return "ingress_field"
    if sb == "db_source_read":
        return "db_read_field"
    return "ingress_field" if "ingress" in sb else "unknown"

def _strict_origin_trace_status(raw_status: str | None, ultimate_origin_kind: str | None, missing_links: list[str] | None) -> str:
    """Public output provenance uses strict evidence levels only.

    Legacy source-only statuses such as unresolved/unresolved/unknown are internal
    resolver hints and must not be exposed as evidence.
    """
    ultimate = str(ultimate_origin_kind or "unknown")
    if str(raw_status or "") == "confirmed" and ultimate not in {"unknown", ""} and not missing_links:
        return "confirmed"
    return "unresolved"


def _output_provenance_maturity(
    *,
    trace_status: str,
    ultimate_origin_kind: str | None,
    origin_field: str | None,
    missing_links: list[str] | None,
    inspection_target_available: bool,
) -> dict[str, Any]:
    ultimate = str(ultimate_origin_kind or "unknown")
    source_boundary = "confirmed" if ultimate not in {"unknown", "", "computed", "constant"} else ("not_applicable" if ultimate in {"computed", "constant"} else "unresolved")
    field_mapping = "confirmed" if trace_status == "confirmed" and origin_field else "unresolved"
    return _maturity_props(
        {
            "output_provenance": trace_status,
            "source_boundary": source_boundary,
            "field_mapping": field_mapping,
        },
        actionable_dimensions={"output_provenance", "source_boundary", "field_mapping"},
        decision_blocking_dimensions={"output_provenance", "source_boundary", "field_mapping"},
        inspection_target_available=inspection_target_available,
        not_actionable_reason="no concrete output/source method is available for targeted inspection",
        notes=["output_provenance uses strict confirmed/unresolved contract; candidate resolver hints are navigation only"],
    )


def _var_decl_assignments(body: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    method = _synthetic_method_for_body(body)
    for assignment in (method.assignments if method else ()):  # Tree-sitter local variable declarations
        if assignment.assignment_kind != "variable_declaration":
            continue
        out[assignment.target] = {
            "variable": assignment.target,
            "type": _simple_type_name(assignment.declared_type),
            "expression": _clean_expression(assignment.expression),
        }
    return out


def _method_call_origin_kind(expr: str) -> tuple[str, str, str, str]:
    low = (expr or "").lower()
    receiver = ""
    method = ""
    parsed = _synthetic_method_for_body("{ " + (expr or "") + "; }")
    call = (parsed.calls[0] if parsed and parsed.calls else None)
    if call:
        receiver = call.receiver or ""
        method = call.method or ""
    receiver_low = receiver.lower()
    method_low = method.lower()
    if any(tok in receiver_low for tok in CACHE_RECEIVER_TOKENS):
        if method.startswith(READ_METHOD_PREFIXES) or method_low.startswith(READ_METHOD_PREFIXES):
            return "cache_read_field", "cache_read_field", receiver, method
    if _receiver_storage_like(receiver) or "repository" in receiver_low or "repo" in receiver_low or "dao" in receiver_low:
        if method.startswith(READ_METHOD_PREFIXES) or method_low.startswith(READ_METHOD_PREFIXES):
            return "repository_result_field", "db_read_field", receiver, method
    if any(tok in receiver_low or tok in low for tok in EXTERNAL_RECEIVER_TOKENS):
        return "external_service_response_field", "external_service_response_field", receiver, method
    if any(tok in receiver_low for tok in MAPPER_RECEIVER_TOKENS):
        return "mapper_result_field", "unknown", receiver, method
    if any(tok in receiver_low for tok in SERVICE_RECEIVER_TOKENS):
        return "service_result_field", "unknown", receiver, method
    if call:
        return "computed", "computed", receiver, method
    return "unknown", "unknown", receiver, method



def _syntax_method_info_for_body(body: str) -> dict[str, Any]:
    method = _synthetic_method_for_body(body or "")
    if not method:
        return {}
    return method_syntax_dict(method)


def _clean_collection_receiver(receiver: str | None) -> str:
    value = _clean_expression(receiver or "")
    for suffix in (".stream()", ".parallelStream()"):
        if value.endswith(suffix):
            return value[: -len(suffix)]
    return value


def _smallest_enclosing_call(calls: list[dict[str, Any]], start: int, end: int, method_names: set[str]) -> dict[str, Any] | None:
    matches: list[dict[str, Any]] = []
    for call in calls or []:
        try:
            c_start = int(call.get("start_byte") or -1)
            c_end = int(call.get("end_byte") or -1)
        except Exception:
            continue
        if c_start <= start and end <= c_end and str(call.get("method") or "") in method_names:
            matches.append(call)
    return sorted(matches, key=lambda c: int(c.get("end_byte") or 0) - int(c.get("start_byte") or 0))[0] if matches else None


def _getter_receiver_field_from_syntax(expr: str, method_info: dict[str, Any] | None = None) -> tuple[str | None, str | None]:
    e = _clean_expression(expr)
    infos: list[dict[str, Any]] = []
    if method_info:
        infos.append(method_info)
    infos.append(_syntax_method_info_for_body("{ " + e + "; }"))
    for info in infos:
        for call in info.get("method_calls") or []:
            text = _clean_expression(call.get("text") or "")
            if text != e and text not in e:
                continue
            method = str(call.get("method") or "")
            receiver = str(call.get("receiver") or "")
            if receiver and method.startswith("get") and len(method) > 3:
                return receiver, _normalize_field_name(method[3:]) or method[3:]
            if receiver and method.startswith("is") and len(method) > 2:
                return receiver, _normalize_field_name(method[2:]) or method[2:]
        for access in info.get("field_accesses") or []:
            text = _clean_expression(access.get("text") or "")
            if text == e or text in e:
                receiver = str(access.get("receiver") or "")
                field = str(access.get("field") or "")
                if receiver and field:
                    return receiver, _normalize_field_name(field) or field
    return None, None

def _variable_origins(body: str, method_params: list[dict[str, str]], method_info: dict[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    if method_info is not None:
        cached = method_info.get("_variable_origins_cache")
        if isinstance(cached, dict):
            return cached
    origins: dict[str, dict[str, Any]] = {}
    params_by_name = {str(p.get("name")): p for p in method_params or [] if p.get("name")}
    for param in method_params or []:
        name = param.get("name")
        if name:
            details = _java_type_details(param.get("type"))
            origins[name] = {
                "variable": name,
                "type": _simple_type_name(param.get("type")),
                "raw_type": details.get("raw_type"),
                "container_kind": details.get("container_kind"),
                "element_type": details.get("element_type"),
                "immediate_origin_kind": "method_parameter",
                "ultimate_origin_kind": "unknown",
                "origin_operation": None,
                "origin_payload": details.get("element_type") or _simple_type_name(param.get("type")),
                "origin_container": name if details.get("container_kind") else None,
                "origin_container_type": details.get("type") if details.get("container_kind") else None,
                "origin_element_type": details.get("element_type"),
                "origin_expression": name,
                "trace_hint": "unresolved",
            }
    syntax_info = method_info or _syntax_method_info_for_body(body or "")
    for loop in syntax_info.get("enhanced_for") or []:
        coll = _clean_expression(loop.get("iterable") or "")
        var = str(loop.get("var") or "")
        if not coll or not var or var in CONTROL_WORDS:
            continue
        elem_type = _simple_type_name(loop.get("type"))
        coll_param = params_by_name.get(coll)
        coll_details = _java_type_details(coll_param.get("type") if coll_param else None)
        origins[var] = {
            "variable": var,
            "type": elem_type,
            "immediate_origin_kind": "collection_element",
            "ultimate_origin_kind": "unknown",
            "origin_operation": None,
            "origin_payload": elem_type,
            "origin_container": coll,
            "origin_container_type": coll_details.get("type"),
            "origin_element_type": elem_type,
            "origin_expression": f"{coll}[*]",
            "trace_hint": "unresolved",
        }
    calls = list(syntax_info.get("method_calls") or [])
    for lam in syntax_info.get("lambdas") or []:
        params = list(lam.get("params") or [])
        if not params:
            continue
        var = str(params[0] or "")
        if not var or var in CONTROL_WORDS:
            continue
        try:
            l_start = int(lam.get("start_byte") or -1)
            l_end = int(lam.get("end_byte") or -1)
        except Exception:
            continue
        call = _smallest_enclosing_call(calls, l_start, l_end, {"forEach", "map", "flatMap", "filter"})
        if not call:
            continue
        coll = _clean_collection_receiver(call.get("receiver"))
        if not coll:
            continue
        coll_param = params_by_name.get(coll)
        coll_details = _java_type_details(coll_param.get("type") if coll_param else None)
        elem_type = coll_details.get("element_type") or "unknown"
        origins[var] = {
            "variable": var,
            "type": elem_type,
            "immediate_origin_kind": "collection_element",
            "ultimate_origin_kind": "unknown",
            "origin_operation": None,
            "origin_payload": elem_type,
            "origin_container": coll,
            "origin_container_type": coll_details.get("type"),
            "origin_element_type": elem_type,
            "origin_expression": f"{coll}[*]",
            "trace_hint": "unresolved",
        }
    assignment_items: dict[str, dict[str, Any]] = {}
    if syntax_info:
        object_creations = syntax_info.get("object_creations") or []
        for assignment in syntax_info.get("syntax_assignments") or []:
            if assignment.get("assignment_kind") != "variable_declaration":
                continue
            var = str(assignment.get("target") or "")
            if not var:
                continue
            typ = _simple_type_name(assignment.get("declared_type"))
            expr = str(assignment.get("expression") or "")
            a_start = int(assignment.get("start_byte") or -1)
            a_end = int(assignment.get("end_byte") or -1)
            creation_type = None
            for creation in object_creations:
                c_start = int(creation.get("start_byte") or -2)
                c_end = int(creation.get("end_byte") or -2)
                if a_start <= c_start and c_end <= a_end:
                    creation_type = str(creation.get("type") or "")
                    break
            if typ == "unknown" and creation_type:
                typ = _simple_type_name(creation_type)
            assignment_items[var] = {"type": typ, "expression": expr, "constructed": bool(creation_type)}
    else:
        assignment_items = _var_decl_assignments(body)

    for var, info in assignment_items.items():
        expr = str(info.get("expression") or "")
        immediate, ultimate, receiver, method = _method_call_origin_kind(expr)
        typ = _simple_type_name(info.get("type"))
        if info.get("constructed"):
            immediate, ultimate = "constructed_object", "unknown"
        origins[var] = {
            "variable": var,
            "type": typ,
            "immediate_origin_kind": immediate,
            "ultimate_origin_kind": ultimate,
            "origin_operation": f"{receiver}.{method}" if receiver and method else None,
            "origin_payload": typ,
            "origin_expression": expr,
            "trace_hint": "unresolved" if ultimate != "unknown" else "unresolved",
        }
    if method_info is not None:
        method_info["_variable_origins_cache"] = origins
    return origins


def _literal_value(expr: str) -> str | None:
    e = _clean_expression(expr)
    if re.match(r'^"(?:[^"\\]|\\.)*"$', e):
        return e[:120]
    if re.match(r"^(?:true|false|null|\d+(?:\.\d+)?)$", e):
        return e[:120]
    return None


def _source_expr_to_origin(
    expr: str,
    *,
    method_info: dict[str, Any],
    variable_origins: dict[str, dict[str, Any]],
    ingress_by_param: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    e = _clean_expression(expr)
    lit = _literal_value(e)
    if lit is not None:
        return {
            "immediate_origin_kind": "constant",
            "ultimate_origin_kind": "constant",
            "origin_payload": "literal",
            "origin_field": None,
            "origin_expression": lit,
            "trace_hint": "confirmed",
            "path": [lit],
            "input_origins": [],
        }
    for param, origin in ingress_by_param.items():
        gf = _getter_field_expr(e, param)
        if gf:
            kind = _source_boundary_for_origin(origin)
            origin_kind = _origin_from_source_boundary(kind)
            return {
                "immediate_origin_kind": origin_kind,
                "ultimate_origin_kind": origin_kind,
                "origin_operation": origin.get("operation"),
                "origin_payload": origin.get("payload_type"),
                "origin_field": gf,
                "origin_expression": e,
                "trace_hint": "confirmed",
                "path": [f"{param}.{gf}", e],
                "input_origins": [f"{param}.{gf}"],
            }
    # var.getField() / var.field via Tree-sitter method_invocation/field_access nodes.
    var, field = _getter_receiver_field(e, method_info)
    if var and field:
        vorig = variable_origins.get(var, {})
        immediate = str(vorig.get("immediate_origin_kind") or "unknown")
        ultimate = str(vorig.get("ultimate_origin_kind") or immediate or "unknown")
        origin_container = str(vorig.get("origin_container") or "")
        origin_container_type = vorig.get("origin_container_type")
        origin_element_type = vorig.get("origin_element_type") or vorig.get("type")
        if immediate == "method_parameter" and var in ingress_by_param:
            boundary = _source_boundary_for_origin(ingress_by_param[var])
            immediate = ultimate = _origin_from_source_boundary(boundary)
            vorig["origin_operation"] = ingress_by_param[var].get("operation")
        elif immediate == "collection_element" and origin_container in ingress_by_param:
            boundary = _source_boundary_for_origin(ingress_by_param[origin_container])
            immediate = ultimate = _origin_from_source_boundary(boundary)
            vorig["origin_operation"] = ingress_by_param[origin_container].get("operation")
        elif immediate == "collection_element":
            # The element is derived from a method-input collection, but there is no
            # boundary annotation proving REST/Kafka/etc. Keep the technical link
            # to the collection and let the LLM treat source kind separately.
            ultimate = "method_input"
        if immediate == "method_parameter":
            immediate = ultimate = "unknown"
        return {
            "immediate_origin_kind": immediate,
            "ultimate_origin_kind": ultimate,
            "origin_operation": vorig.get("origin_operation") or method_info.get("operation"),
            "origin_payload": origin_element_type if immediate == "collection_element" or origin_container else (vorig.get("origin_payload") or vorig.get("type")),
            "origin_container": origin_container or None,
            "origin_container_type": origin_container_type,
            "origin_element_type": origin_element_type,
            "origin_payload_parameter": origin_container or (var if immediate != "unknown" else None),
            "origin_field": field,
            "origin_expression": e,
            "trace_hint": "unresolved" if ultimate != "unknown" else "unresolved",
            "path": [str(vorig.get("origin_expression") or var), f"{var}.{field}", e],
            "input_origins": [],
        }
    # complex expression: computed when it references known variables; otherwise unknown.
    input_origins: list[str] = []
    origin_kinds: set[str] = set()
    for param, origin in ingress_by_param.items():
        if _contains_symbol(e, param):
            input_origins.append(param)
            origin_kinds.add(_origin_from_source_boundary(_source_boundary_for_origin(origin)))
    for var, vorig in variable_origins.items():
        if _contains_symbol(e, var) and var not in ingress_by_param:
            ok = str(vorig.get("ultimate_origin_kind") or "unknown")
            origin_kinds.add(ok)
            input_origins.append(var)
    if input_origins or re.search(r"[+\-*/]|\w+\s*\(", e):
        return {
            "immediate_origin_kind": "computed",
            "ultimate_origin_kind": "computed" if origin_kinds else "unknown",
            "origin_payload": None,
            "origin_field": None,
            "origin_expression": e,
            "trace_hint": "unresolved" if origin_kinds else "unknown",
            "path": [e],
            "input_origins": sorted(set(input_origins)),
            "input_origin_kinds": sorted(x for x in origin_kinds if x),
        }
    return {
        "immediate_origin_kind": "unknown",
        "ultimate_origin_kind": "unknown",
        "origin_payload": None,
        "origin_field": None,
        "origin_expression": e,
        "trace_hint": "unknown",
        "path": [e] if e else [],
        "input_origins": [],
    }


def _first_call_in_expr(expr: str) -> dict[str, str] | None:
    parsed = _synthetic_method_for_body("{ " + (expr or "") + "; }")
    call = parsed.calls[0] if parsed and parsed.calls else None
    if not call:
        return None
    return {
        "receiver": call.receiver or "",
        "method": call.method or "",
        "args": call.args_text or ", ".join(call.args),
        "expression": _clean_expression(call.text),
    }




def _computed_call_should_descend(expr: str, origin: dict[str, Any]) -> bool:
    return str(origin.get("ultimate_origin_kind") or "") == "computed" and _first_call_in_expr(expr) is not None


def _resolve_call_expr_candidates(
    expr: str,
    *,
    method_info: dict[str, Any],
    methods: dict[str, dict[str, Any]],
    class_fields: dict[str, dict[str, str]],
    class_infos: dict[str, dict[str, Any]],
    iface_impls: dict[str, list[str]],
) -> list[dict[str, Any]]:
    call = _first_call_in_expr(expr)
    if not call:
        return []
    return _resolve_receiver_candidates(
        call.get("receiver"),
        call.get("method") or "",
        method_info,
        class_fields,
        class_infos,
        methods,
        iface_impls,
    )


def _constructor_arg_bindings(expr: str, method_info: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    expression = _clean_expression(expr or "")
    creations = list((method_info or {}).get("object_creations") or [])
    if not creations:
        creations = list(_syntax_method_info_for_body("{ " + expression + "; }").get("object_creations") or [])
    for creation in creations:
        c_text = _clean_expression(creation.get("text") or "")
        if expression and c_text and c_text != expression and c_text not in expression and expression not in c_text:
            continue
        for idx, arg in enumerate(list(creation.get("args") or [])):
            out.append({
                "kind": "constructor_arg",
                "target_type": _simple_type_name(creation.get("type")),
                "target_field": None,
                "target_index": idx,
                "source_expression": _clean_expression(arg),
                "expression": c_text or expression,
            })
    return out


def _local_field_source_expr(body: str, variable: str, field: str, method_info: dict[str, Any] | None = None) -> str | None:
    target_field = _normalize_field_name(field) or field
    for b in _setter_bindings_any_source(body, method_info):
        if str(b.get("target_variable") or "") == variable and str(b.get("target_field") or "") == target_field:
            return str(b.get("source_expression") or "")
    # Builder assignment: Target x = Target.builder().field(source).build();
    # The returned variable itself is handled through assignment expressions; this helper
    # is intentionally limited to explicit target.setField(...) to avoid false positives.
    return None


def _getter_receiver_field(expr: str, method_info: dict[str, Any] | None = None) -> tuple[str | None, str | None]:
    return _getter_receiver_field_from_syntax(expr, method_info)


def _collect_lookup_fields(mi: dict[str, Any], ingress_by_param: dict[str, dict[str, Any]], schema_fields: dict[str, list[dict[str, str]]]) -> list[str]:
    fields: set[str] = set()
    for param, origin in ingress_by_param.items():
        payload_fields = [str(f.get("name") or "") for f in _fields_for_type(schema_fields, origin.get("payload_type")) if f.get("name")]
        for cm in mi.get("method_calls") or []:
            args = list(cm.get("args") or [])
            receiver_low = str(cm.get("receiver") or "").lower()
            method_low = str(cm.get("method") or "").lower()
            call_like_lookup = (
                any(tok in receiver_low for tok in [*SERVICE_RECEIVER_TOKENS, *EXTERNAL_RECEIVER_TOKENS, "repository", "repo", "dao", *CACHE_RECEIVER_TOKENS])
                or method_low.startswith(READ_METHOD_PREFIXES)
                or any(tok in method_low for tok in ["find", "search", "lookup", "query", "filter", "load", "get"])
            )
            if not call_like_lookup:
                continue
            for arg in args:
                gf = _getter_field_expr(arg, param)
                if gf:
                    fields.add(gf)
                elif _contains_symbol(arg, param):
                    for pf in payload_fields:
                        if pf:
                            fields.add(pf)
    return sorted(fields)


def _merge_origin(
    *,
    base: dict[str, Any] | None = None,
    immediate_origin_kind: str,
    ultimate_origin_kind: str,
    origin_operation: str | None,
    origin_payload: str | None,
    origin_field: str | None,
    origin_expression: str | None,
    path: list[str],
    trace_hint: str,
    missing_links: list[str] | None = None,
    resolver_rank: float | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    out = dict(base or {})
    out.update({
        "immediate_origin_kind": immediate_origin_kind,
        "ultimate_origin_kind": ultimate_origin_kind,
        "origin_operation": origin_operation,
        "origin_payload": origin_payload,
        "origin_field": origin_field,
        "origin_expression": origin_expression,
        "path": [str(x) for x in path if x],
        "trace_hint": trace_hint,
        "missing_links": [str(x) for x in (missing_links or []) if x],
    })
    if resolver_rank is not None:
        out["resolver_rank"] = resolver_rank
    if extra:
        out.update(extra)
    return out


def _method_terminal_origin_from_expr(expr: str) -> tuple[str, str, str | None]:
    immediate, ultimate, receiver, method = _method_call_origin_kind(expr)
    receiver_low = (receiver or "").lower()
    method_low = (method or "").lower()
    if any(tok in receiver_low for tok in CACHE_RECEIVER_TOKENS):
        return "cache_read_field", "cache_read_field", f"{receiver}.{method}" if receiver and method else None
    if any(tok in receiver_low for tok in ["repository", "repo", "dao"]):
        if method.startswith(READ_METHOD_PREFIXES) or method_low.startswith(READ_METHOD_PREFIXES):
            return "repository_result_field", "db_read_field", f"{receiver}.{method}" if receiver and method else None
    return immediate, ultimate, f"{receiver}.{method}" if receiver and method else None


def _source_arg_to_origin(
    arg: str,
    *,
    method_info: dict[str, Any],
    ingress_by_param: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    variable_origins = _variable_origins(method_info.get("body") or "", method_info.get("params") or [], method_info)
    a = _clean_expression(arg)
    if a in variable_origins:
        vorig = dict(variable_origins[a])
        if a in ingress_by_param:
            boundary = _source_boundary_for_origin(ingress_by_param[a])
            ok = _origin_from_source_boundary(boundary)
            vorig.update({
                "immediate_origin_kind": ok,
                "ultimate_origin_kind": ok,
                "origin_operation": ingress_by_param[a].get("operation"),
                "origin_payload": ingress_by_param[a].get("payload_type"),
                "origin_expression": a,
                "trace_hint": "confirmed",
            })
        return vorig
    origin = _source_expr_to_origin(a, method_info=method_info, variable_origins=variable_origins, ingress_by_param=ingress_by_param)
    return origin


def _callee_param_origin_overrides(
    expr: str,
    *,
    caller_method_info: dict[str, Any],
    callee_method_info: dict[str, Any],
    root_ingress_by_param: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    call = _first_call_in_expr(expr)
    if not call:
        return {}
    args = _split_args(call.get("args") or "")
    callee_params = callee_method_info.get("params") or []
    out: dict[str, dict[str, Any]] = {}
    for idx, arg in enumerate(args):
        if idx >= len(callee_params):
            continue
        pname = callee_params[idx].get("name")
        if not pname:
            continue
        origin = _source_arg_to_origin(arg, method_info=caller_method_info, ingress_by_param=root_ingress_by_param)
        if origin:
            out[str(pname)] = dict(origin)
            out[str(pname)]["origin_expression"] = _clean_expression(arg)
            out[str(pname)]["passed_from_argument"] = _clean_expression(arg)
    return out


def _resolve_return_field_origin(
    operation: str,
    field: str,
    *,
    methods: dict[str, dict[str, Any]],
    schema_fields: dict[str, list[dict[str, str]]],
    class_fields: dict[str, dict[str, str]],
    class_infos: dict[str, dict[str, Any]],
    iface_impls: dict[str, list[str]],
    root_ingress_by_param: dict[str, dict[str, Any]],
    visited: set[tuple[str, str]],
    depth: int = 0,
    param_origin_overrides: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if depth > PROVENANCE_MAX_DEPTH:
        return _merge_origin(
            immediate_origin_kind="unknown", ultimate_origin_kind="unknown",
            origin_operation=operation, origin_payload=None, origin_field=field, origin_expression=None,
            path=[operation], trace_hint="unresolved",
            missing_links=["maximum source-only provenance depth reached"],
            extra={"provenance_depth": depth, "unresolved_boundary": "max_depth"},
        )
    key = (operation, field)
    if key in visited:
        return _merge_origin(
            immediate_origin_kind="unknown", ultimate_origin_kind="unknown",
            origin_operation=operation, origin_payload=None, origin_field=field, origin_expression=None,
            path=[operation], trace_hint="unresolved",
            missing_links=["recursive/cyclic method provenance path stopped"],
            extra={"provenance_depth": depth, "unresolved_boundary": "cycle"},
        )
    mi = methods.get(operation)
    if not mi:
        return _merge_origin(
            immediate_origin_kind="unknown", ultimate_origin_kind="unknown",
            origin_operation=operation, origin_payload=None, origin_field=field, origin_expression=None,
            path=[operation], trace_hint="unknown",
            missing_links=["method implementation not found in repository"],
            extra={"provenance_depth": depth, "unresolved_boundary": "method_not_found"},
        )
    visited.add(key)
    body = mi.get("body") or ""
    local_ingress = {str(o.get("payload_parameter")): o for o in root_ingress_by_param.values() if o.get("payload_parameter")}
    # Keep method parameters visible. If the callee received the original request object under
    # a different parameter name, source-only binding may not know it; method_parameter then
    # remains unknown rather than being promoted to ingress.
    variable_origins = _variable_origins(body, mi.get("params") or [], mi)
    for pname, override in (param_origin_overrides or {}).items():
        if pname:
            merged = dict(variable_origins.get(pname, {}))
            merged.update({k: v for k, v in dict(override).items() if v is not None})
            merged["variable"] = pname
            variable_origins[pname] = merged

    # Direct setter or builder in the method returning a DTO. Supports both direct
    # fields (target.setA(...)) and nested collection/container fields
    # (target.setItems(source.getItems()) while resolving items[*].a).
    requested_container, requested_nested = _nested_field_parts(field)
    requested_leaf = _leaf_field_name(field)
    for b in _setter_bindings_any_source(body, mi) + _builder_bindings_any_source(body, mi):
        target_field_name = str(b.get("target_field") or "")
        if target_field_name != field and not (requested_nested and target_field_name == requested_container):
            continue
        source_expr = str(b.get("source_expression") or "")
        local_var, local_field = _getter_receiver_field(source_expr, mi)
        redirected_from_local_field = None
        if local_var and local_field:
            local_src = _local_field_source_expr(body, local_var, local_field, mi)
            if local_src:
                redirected_from_local_field = f"{local_var}.{local_field}"
                source_expr = local_src
        if requested_nested:
            # Resolve the leaf field through the source container expression. This is
            # the key step for wrapper/list fields such as response.items[*].state.
            deeper = _resolve_expr_deep_origin(
                source_expr, requested_leaf, method_info=mi, methods=methods,
                schema_fields=schema_fields, class_fields=class_fields, class_infos=class_infos,
                iface_impls=iface_impls, root_ingress_by_param=root_ingress_by_param,
                visited=visited, depth=depth + 1,
            )
            if deeper.get("ultimate_origin_kind") not in {"unknown", None}:
                if not deeper.get("origin_field") or str(deeper.get("origin_field")) == requested_leaf:
                    src_var, src_container = _getter_receiver_field(source_expr, mi)
                    if src_container:
                        deeper["origin_field"] = _origin_field_for_nested(src_container, requested_leaf, "collection")
                deeper["path"] = [operation, *[str(x) for x in (deeper.get("path") or [])], str(b.get("expression") or ""), f"return field {field}"]
                deeper["provenance_depth"] = depth
                deeper["container_field"] = requested_container
                deeper["nested_field"] = requested_leaf
                return deeper
        origin = _source_expr_to_origin(source_expr, method_info=mi, variable_origins=variable_origins, ingress_by_param=local_ingress)
        if origin.get("ultimate_origin_kind") not in {"unknown", None} and not _computed_call_should_descend(source_expr, origin):
            prefix = [operation]
            if redirected_from_local_field:
                prefix.append(f"{redirected_from_local_field} populated from {source_expr}")
            origin["path"] = [*prefix, *[str(x) for x in (origin.get("path") or [])]]
            origin["provenance_depth"] = depth
            return origin
        # If the source expression itself comes from an internal method call, descend.
        deeper = _resolve_expr_deep_origin(
            source_expr, field, method_info=mi, methods=methods,
            schema_fields=schema_fields, class_fields=class_fields, class_infos=class_infos,
            iface_impls=iface_impls, root_ingress_by_param=root_ingress_by_param,
            visited=visited, depth=depth + 1,
        )
        if deeper.get("ultimate_origin_kind") not in {"unknown", None}:
            deeper["path"] = [operation, *[str(x) for x in (deeper.get("path") or [])], str(b.get("expression") or "")]
            deeper["provenance_depth"] = depth
            return deeper

    # Constructor return: best-effort position/name mapping. If the target type fields are
    # known, map constructor argument index to field index. This is unresolved in source-only mode.
    returns = _return_expressions_from_method_info(mi)
    return_blob = " ".join(returns)
    for ret in returns:
        expr = _clean_expression(ret)
        for cb in _constructor_arg_bindings(expr, method_info=mi):
            target_type = cb.get("target_type")
            fields = _fields_for_type(schema_fields, target_type)
            idx = int(cb.get("target_index") or 0)
            target_field = fields[idx].get("name") if idx < len(fields) else None
            if target_field and target_field != field:
                continue
            src_origin = _source_expr_to_origin(str(cb.get("source_expression") or ""), method_info=mi, variable_origins=variable_origins, ingress_by_param=local_ingress)
            src_origin["trace_hint"] = "unresolved" if src_origin.get("ultimate_origin_kind") != "unknown" else src_origin.get("trace_hint", "unresolved")
            src_origin["path"] = [operation, *[str(x) for x in (src_origin.get("path") or [])], f"constructor argument {idx}"]
            src_origin["provenance_depth"] = depth
            src_origin.setdefault("mapping_kind", "constructor_arg")
            return src_origin

        vorig = variable_origins.get(expr)
        if vorig:
            # Returned variable populated locally via setter/builder above was already handled.
            deeper = _resolve_expr_deep_origin(
                str(vorig.get("origin_expression") or expr), field, method_info=mi, methods=methods,
                schema_fields=schema_fields, class_fields=class_fields, class_infos=class_infos,
                iface_impls=iface_impls, root_ingress_by_param=root_ingress_by_param,
                visited=visited, depth=depth + 1,
            )
            if deeper.get("ultimate_origin_kind") not in {"unknown", None}:
                deeper["path"] = [operation, *[str(x) for x in (deeper.get("path") or [])], f"return {expr}"]
                deeper["provenance_depth"] = depth
                return deeper
            immediate = str(vorig.get("immediate_origin_kind") or "unknown")
            ultimate = str(vorig.get("ultimate_origin_kind") or immediate or "unknown")
            return _merge_origin(
                immediate_origin_kind=immediate, ultimate_origin_kind=ultimate,
                origin_operation=vorig.get("origin_operation"), origin_payload=vorig.get("origin_payload"),
                origin_field=field if immediate not in {"constructed_object", "method_parameter"} else None,
                origin_expression=str(vorig.get("origin_expression") or expr),
                path=[operation, str(vorig.get("origin_expression") or expr), f"return {expr}"],
                trace_hint="unresolved" if ultimate != "unknown" else "unresolved",
                missing_links=[] if ultimate != "unknown" else ["returned variable source is not resolved to a concrete field origin"],
                extra={"provenance_depth": depth, "unresolved_boundary": None if ultimate != "unknown" else "returned_variable"},
            )

        # return source.getField() / constant / computed
        origin = _source_expr_to_origin(expr, method_info=mi, variable_origins=variable_origins, ingress_by_param=local_ingress)
        if origin.get("ultimate_origin_kind") not in {"unknown", None} and not _computed_call_should_descend(expr, origin):
            origin["path"] = [operation, *[str(x) for x in (origin.get("path") or [])], f"return {expr}"]
            origin["provenance_depth"] = depth
            return origin

        # return internalCall(...), mapper.map(...), repository.find(...), externalClient.call(...)
        deeper = _resolve_expr_deep_origin(
            expr, field, method_info=mi, methods=methods, schema_fields=schema_fields,
            class_fields=class_fields, class_infos=class_infos, iface_impls=iface_impls,
            root_ingress_by_param=root_ingress_by_param, visited=visited, depth=depth + 1,
        )
        if deeper:
            deeper["path"] = [operation, *[str(x) for x in (deeper.get("path") or [])], f"return {expr}"]
            deeper["provenance_depth"] = depth
            return deeper

    return _merge_origin(
        immediate_origin_kind="unknown", ultimate_origin_kind="unknown",
        origin_operation=operation, origin_payload=mi.get("return_type"), origin_field=field, origin_expression=None,
        path=[operation, f"return field {field}"], trace_hint="unknown",
        missing_links=["field source was not resolved inside available method implementation"],
        extra={"provenance_depth": depth, "unresolved_boundary": "method_return"},
    )


def _resolve_expr_deep_origin(
    expr: str,
    field: str,
    *,
    method_info: dict[str, Any],
    methods: dict[str, dict[str, Any]],
    schema_fields: dict[str, list[dict[str, str]]],
    class_fields: dict[str, dict[str, str]],
    class_infos: dict[str, dict[str, Any]],
    iface_impls: dict[str, list[str]],
    root_ingress_by_param: dict[str, dict[str, Any]],
    visited: set[tuple[str, str]],
    depth: int,
) -> dict[str, Any]:
    expr = _clean_expression(expr)
    leaf_field = _leaf_field_name(field)
    container_field, nested_tail = _nested_field_parts(field)
    variable_origins = _variable_origins(method_info.get("body") or "", method_info.get("params") or [], method_info)
    # If a container expression is taken from a variable that already has a boundary
    # origin (external/repository/cache/service), project the requested nested field
    # through that container instead of stopping at the wrapper/list field.
    recv, getter_field = _getter_receiver_field(expr, method_info)
    if recv and getter_field and recv in variable_origins:
        vorig = variable_origins.get(recv, {})
        immediate_v = str(vorig.get("immediate_origin_kind") or "unknown")
        ultimate_v = str(vorig.get("ultimate_origin_kind") or immediate_v or "unknown")
        if ultimate_v not in {"unknown", "computed", "method_parameter", "constructed_object"}:
            origin_field = _origin_field_for_nested(getter_field, leaf_field, "collection" if getter_field != leaf_field else None)
            return _merge_origin(
                immediate_origin_kind=immediate_v, ultimate_origin_kind=ultimate_v,
                origin_operation=vorig.get("origin_operation"), origin_payload=vorig.get("origin_payload") or vorig.get("type"),
                origin_field=origin_field, origin_expression=expr,
                path=[str(vorig.get("origin_expression") or recv), f"{recv}.{origin_field}", expr],
                trace_hint="unresolved",
                missing_links=[] if ultimate_v not in {"external_service_response_field", "db_read_field", "repository_result_field", "cache_read_field"} else ["nested field projected to boundary result; upstream system/result mapping is outside current repository"],
                resolver_rank=0.62,
                extra={"provenance_depth": depth, "container_field": getter_field, "nested_field": leaf_field},
            )
    if expr in variable_origins:
        vorig = variable_origins.get(expr, {})
        immediate_v = str(vorig.get("immediate_origin_kind") or "unknown")
        ultimate_v = str(vorig.get("ultimate_origin_kind") or immediate_v or "unknown")
        if ultimate_v not in {"unknown", "computed", "method_parameter", "constructed_object"}:
            return _merge_origin(
                immediate_origin_kind=immediate_v, ultimate_origin_kind=ultimate_v,
                origin_operation=vorig.get("origin_operation"), origin_payload=vorig.get("origin_payload") or vorig.get("type"),
                origin_field=leaf_field, origin_expression=expr,
                path=[str(vorig.get("origin_expression") or expr), f"{expr}.{leaf_field}"],
                trace_hint="unresolved", missing_links=[], resolver_rank=0.60,
                extra={"provenance_depth": depth, "nested_field": leaf_field},
            )
    immediate, ultimate, terminal_op = _method_terminal_origin_from_expr(expr)
    candidates = _resolve_call_expr_candidates(
        expr, method_info=method_info, methods=methods, class_fields=class_fields,
        class_infos=class_infos, iface_impls=iface_impls,
    )
    if candidates:
        # Prefer the highest-resolver_rank local implementation. Interface dispatch may
        # produce several candidates; keep unresolved and point out ambiguity.
        cand = sorted(candidates, key=lambda x: float(x.get("resolver_rank") or 0), reverse=True)[0]
        callee_op = str(cand.get("callee_operation_id") or "")
        callee_mi = methods.get(callee_op, {})
        param_overrides = _callee_param_origin_overrides(
            expr, caller_method_info=method_info, callee_method_info=callee_mi,
            root_ingress_by_param=root_ingress_by_param,
        )
        deeper = _resolve_return_field_origin(
            callee_op, field, methods=methods, schema_fields=schema_fields,
            class_fields=class_fields, class_infos=class_infos, iface_impls=iface_impls,
            root_ingress_by_param=root_ingress_by_param, visited=visited, depth=depth,
            param_origin_overrides=param_overrides,
        )
        # Preserve the immediate boundary classification from the original call when useful,
        # but let the callee decide the ultimate origin.
        if immediate in {"service_result_field", "mapper_result_field"} and deeper.get("ultimate_origin_kind") != "unknown":
            deeper["immediate_origin_kind"] = immediate
        deeper["origin_operation"] = deeper.get("origin_operation") or callee_op
        deeper["path"] = [expr, f"resolved to {callee_op}", *[str(x) for x in (deeper.get("path") or [])]]
        if len(candidates) > 1:
            ml = list(deeper.get("missing_links") or [])
            ml.append("multiple source-only dispatch candidates; highest-resolver_rank implementation used")
            deeper["missing_links"] = ml
            deeper["trace_hint"] = "unresolved" if deeper.get("ultimate_origin_kind") != "unknown" else deeper.get("trace_hint", "unresolved")
        deeper["callee_resolution_kind"] = cand.get("resolution_kind")
        deeper["callee_operation"] = callee_op
        return deeper

    if immediate in {"repository_result_field", "db_read_field"}:
        return _merge_origin(
            immediate_origin_kind="repository_result_field", ultimate_origin_kind="repository_result_field",
            origin_operation=terminal_op, origin_payload=None, origin_field=field, origin_expression=expr,
            path=[expr, f"repository result field {field}"], trace_hint="unresolved",
            missing_links=["repository implementation/result mapping not available; field origin resolved to repository boundary"],
            resolver_rank=0.62, extra={"unresolved_boundary": "repository_read", "provenance_depth": depth},
        )
    if immediate == "cache_read_field":
        return _merge_origin(
            immediate_origin_kind="cache_read_field", ultimate_origin_kind="cache_read_field",
            origin_operation=terminal_op, origin_payload=None, origin_field=field, origin_expression=expr,
            path=[expr, f"cache result field {field}"], trace_hint="unresolved",
            missing_links=["cache producer/upstream source is outside this source-only repository path"],
            resolver_rank=0.58, extra={"unresolved_boundary": "cache_read", "provenance_depth": depth},
        )
    if immediate == "external_service_response_field":
        return _merge_origin(
            immediate_origin_kind="external_service_response_field", ultimate_origin_kind="external_service_response_field",
            origin_operation=terminal_op, origin_payload=None, origin_field=field, origin_expression=expr,
            path=[expr, f"external response field {field}"], trace_hint="unresolved",
            missing_links=["external system implementation is outside current repository"],
            resolver_rank=0.60, extra={"unresolved_boundary": "external_service", "provenance_depth": depth},
        )
    if immediate == "mapper_result_field":
        return _merge_origin(
            immediate_origin_kind="mapper_result_field", ultimate_origin_kind="unknown",
            origin_operation=terminal_op, origin_payload=None, origin_field=field, origin_expression=expr,
            path=[expr, f"mapper result field {field}"], trace_hint="unresolved",
            missing_links=["mapper implementation not resolved in repository"],
            resolver_rank=0.38, extra={"unresolved_boundary": "mapper", "provenance_depth": depth},
        )
    return _merge_origin(
        immediate_origin_kind=immediate, ultimate_origin_kind=ultimate,
        origin_operation=terminal_op, origin_payload=None, origin_field=field if ultimate != "unknown" else None,
        origin_expression=expr, path=[expr],
        trace_hint="unresolved" if ultimate != "unknown" else "unknown",
        missing_links=[] if ultimate != "unknown" else ["expression call target not resolved in repository"],
        resolver_rank=0.45 if ultimate != "unknown" else 0.25,
        extra={"unresolved_boundary": None if ultimate != "unknown" else "unresolved_call", "provenance_depth": depth},
    )


def _setter_bindings_any_source(body: str, method_info: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    return _tree_sitter_setter_bindings(method_info, any_source=True)


def _builder_bindings_any_source(body: str, method_info: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    return _tree_sitter_builder_bindings(method_info, any_source=True)


def _response_payload_type_for_method(mi: dict[str, Any], schema_fields: dict[str, list[dict[str, str]]]) -> str:
    ret_type = _simple_type_name(mi.get("return_type"))
    if ret_type in schema_fields:
        return ret_type
    returns = mi.get("returns") or []
    creations = mi.get("object_creations") or []
    for idx, ret in enumerate(_return_expressions_from_method_info(mi)):
        rv = _clean_expression(ret)
        var_type = (mi.get("var_types") or {}).get(rv)
        if var_type:
            vt = _simple_type_name(var_type)
            if vt in schema_fields:
                return vt
        ret_node = returns[idx] if idx < len(returns) else {}
        r_start = int(ret_node.get("start_byte") or -1) if isinstance(ret_node, dict) else -1
        r_end = int(ret_node.get("end_byte") or -1) if isinstance(ret_node, dict) else -1
        for creation in creations:
            c_start = int(creation.get("start_byte") or -2)
            c_end = int(creation.get("end_byte") or -2)
            if r_start <= c_start and c_end <= r_end:
                vt = _simple_type_name(creation.get("type"))
                if vt in schema_fields:
                    return vt
    return ret_type


def _target_fields_for_payload(schema_fields: dict[str, list[dict[str, str]]], payload_type: str | None, target_field: str | None = None) -> list[dict[str, str]]:
    fields = _fields_for_type(schema_fields, payload_type)
    if target_field and target_field not in {"message_key", "header", "url_or_query_param", "unknown", ""}:
        return [f for f in fields if f.get("name") == target_field] or [{"name": target_field, "type": "unknown", "role": _field_role(target_field)}]
    return fields


def _provenance_fact(
    *,
    provenance_id: str,
    published_boundary: str,
    published_operation: str,
    published_payload: str | None,
    published_field: str,
    published_location: str | None,
    immediate_origin_kind: str,
    ultimate_origin_kind: str,
    origin_operation: str | None,
    origin_payload: str | None,
    origin_field: str | None,
    origin_expression: str | None,
    path: list[str],
    trace_hint: str,
    missing_links: list[str],
    evidence_refs: list[str],
    evidence: list[EvidenceRef],
    resolver_rank: float,
    extra: dict[str, Any] | None = None,
) -> Fact:
    trace_status = _strict_origin_trace_status(trace_hint, ultimate_origin_kind, missing_links)
    maturity = _output_provenance_maturity(
        trace_status=trace_status,
        ultimate_origin_kind=ultimate_origin_kind,
        origin_field=origin_field,
        missing_links=missing_links,
        inspection_target_available=bool(published_operation),
    )
    props: dict[str, Any] = {
        "output_field_provenance_id": provenance_id,
        "published_boundary": published_boundary,
        "published_operation": published_operation,
        "published_payload": published_payload or "unknown",
        "published_field": published_field,
        "published_location": published_location,
        "origin_kind": ultimate_origin_kind,
        "immediate_origin_kind": immediate_origin_kind,
        "ultimate_origin_kind": ultimate_origin_kind,
        "origin_operation": origin_operation,
        "origin_payload": origin_payload,
        "origin_field": origin_field,
        "origin_expression": origin_expression,
        "path": path,
        "trace_status": trace_status,
        "missing_links": missing_links,
        "evidence_refs": [x for x in evidence_refs if x],
    }
    props.update(maturity)
    if extra:
        props.update(extra)
    return Fact(
        fact_type="output_field_provenance",
        name=f"{published_operation}: {published_boundary}.{published_field} origin={ultimate_origin_kind}",
        properties=props,
        evidence=evidence,
    )


def _build_output_field_provenance_facts(
    *,
    files: list[Path],
    methods: dict[str, dict[str, Any]],
    class_fields: dict[str, dict[str, str]],
    class_infos: dict[str, dict[str, Any]],
    origins: list[dict[str, Any]],
    storage_accesses: list[dict[str, Any]],
    flow_facts: list[Fact],
    field_lineage_facts: list[Fact],
) -> tuple[list[Fact], dict[str, Any]]:
    schema_fields = _extract_all_schema_fields(files)
    iface_impls = _interface_impls(class_infos, methods)
    facts: list[Fact] = []
    seq = 0
    seen: set[tuple[Any, ...]] = set()
    origins_by_operation: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for origin in origins:
        origins_by_operation[str(origin.get("operation") or "")].append(origin)

    def add(**kwargs: Any) -> None:
        nonlocal seq
        key = (
            kwargs.get("published_boundary"), kwargs.get("published_operation"), kwargs.get("published_payload"),
            kwargs.get("published_field"), kwargs.get("published_location"), kwargs.get("immediate_origin_kind"),
            kwargs.get("ultimate_origin_kind"), kwargs.get("origin_operation"), kwargs.get("origin_payload"),
            kwargs.get("origin_field"), tuple(kwargs.get("path") or []),
        )
        if key in seen:
            return
        seen.add(key)
        seq += 1
        facts.append(_provenance_fact(provenance_id=f"output_field_provenance_{seq:06d}", **kwargs))

    def add_nested_response_fields(
        *,
        op: str,
        response_type: str,
        container_info: dict[str, Any],
        source_expr: str | None,
        method_info: dict[str, Any],
        ingress_by_param: dict[str, dict[str, Any]],
        lookup_fields: list[str],
        evidence: list[EvidenceRef],
        source_variable: str | None = None,
        source_variable_origin: dict[str, Any] | None = None,
        base_path: list[str] | None = None,
    ) -> None:
        container_field = str(container_info.get("name") or "")
        element_type, container_kind, child_fields = _nested_child_fields(schema_fields, container_info)
        if not container_field or not child_fields:
            return
        for child in child_fields:
            child_name = str(child.get("name") or "")
            if not child_name:
                continue
            published_field = _published_nested_field(container_field, child_name, container_kind)
            if any((pf.properties or {}).get("published_boundary") == "rest_response" and (pf.properties or {}).get("published_operation") == op and (pf.properties or {}).get("published_field") == published_field for pf in facts):
                continue
            src = _clean_expression(source_expr or "")
            origin_info: dict[str, Any] = {}
            if src:
                origin_info = _resolve_expr_deep_origin(
                    src, published_field, method_info=method_info, methods=methods, schema_fields=schema_fields,
                    class_fields=class_fields, class_infos=class_infos, iface_impls=iface_impls,
                    root_ingress_by_param=ingress_by_param, visited=set(), depth=1,
                )
                if origin_info.get("ultimate_origin_kind") in {"unknown", None}:
                    origin_info = _resolve_expr_deep_origin(
                        src, child_name, method_info=method_info, methods=methods, schema_fields=schema_fields,
                        class_fields=class_fields, class_infos=class_infos, iface_impls=iface_impls,
                        root_ingress_by_param=ingress_by_param, visited=set(), depth=1,
                    )
            if (not origin_info or origin_info.get("ultimate_origin_kind") in {"unknown", None}) and source_variable_origin:
                immediate = str(source_variable_origin.get("immediate_origin_kind") or "unknown")
                ultimate = str(source_variable_origin.get("ultimate_origin_kind") or immediate or "unknown")
                origin_info = _merge_origin(
                    immediate_origin_kind=immediate, ultimate_origin_kind=ultimate,
                    origin_operation=source_variable_origin.get("origin_operation"),
                    origin_payload=source_variable_origin.get("origin_payload") or response_type,
                    origin_field=published_field if ultimate != "unknown" else None,
                    origin_expression=str(source_variable_origin.get("origin_expression") or source_variable or ""),
                    path=[str(source_variable_origin.get("origin_expression") or source_variable or ""), published_field],
                    trace_hint="unresolved" if ultimate != "unknown" else "unresolved",
                    missing_links=[] if ultimate != "unknown" else ["nested collection field source was not resolved beyond returned object/container"],
                    resolver_rank=0.50 if ultimate != "unknown" else 0.32,
                    extra={"provenance_depth": 0, "unresolved_boundary": None if ultimate != "unknown" else "nested_container"},
                )
            if not origin_info:
                origin_info = _merge_origin(
                    immediate_origin_kind="unknown", ultimate_origin_kind="unknown",
                    origin_operation=None, origin_payload=element_type, origin_field=None, origin_expression=src or None,
                    path=[op, f"REST response.{published_field}"], trace_hint="unknown",
                    missing_links=["nested response field is known, but container field source was not resolved"],
                    resolver_rank=0.25, extra={"provenance_depth": 0, "unresolved_boundary": "nested_container"},
                )
            ultimate = str(origin_info.get("ultimate_origin_kind") or "unknown")
            origin_field = origin_info.get("origin_field")
            if origin_field and str(origin_field) == child_name and src:
                _src_var, src_container = _getter_receiver_field(src)
                if src_container:
                    origin_field = _origin_field_for_nested(src_container, child_name, "collection")
            add(
                published_boundary="rest_response",
                published_operation=op,
                published_payload=response_type,
                published_field=published_field,
                published_location="response_body_nested_field",
                immediate_origin_kind=str(origin_info.get("immediate_origin_kind") or "unknown"),
                ultimate_origin_kind=ultimate,
                origin_operation=origin_info.get("origin_operation"),
                origin_payload=origin_info.get("origin_payload") or element_type,
                origin_field=origin_field,
                origin_expression=origin_info.get("origin_expression") or src or None,
                path=[*(base_path or []), *[str(x) for x in (origin_info.get("path") or [])], f"REST response.{published_field}"],
                trace_hint=str(origin_info.get("trace_hint") or ("unresolved" if ultimate != "unknown" else "unresolved")),
                missing_links=[str(x) for x in (origin_info.get("missing_links") or [])] or ([] if ultimate != "unknown" else ["nested response field provenance stopped at unresolved container/method boundary"]),
                evidence_refs=[str(x.get("ingress_id") or "") for x in ingress_by_param.values()],
                evidence=evidence,
                resolver_rank=float(origin_info.get("resolver_rank") or (0.62 if ultimate != "unknown" else 0.32)),
                extra={
                    "container_field": container_field,
                    "container_kind": container_kind,
                    "element_type": element_type,
                    "nested_field": child_name,
                    "nested_field_provenance": True,
                    "source_variable": source_variable,
                    "lookup_fields": lookup_fields,
                    "provenance_depth": origin_info.get("provenance_depth", 0),
                    "unresolved_boundary": origin_info.get("unresolved_boundary"),
                    "callee_operation": origin_info.get("callee_operation"),
                    "callee_resolution_kind": origin_info.get("callee_resolution_kind"),
                },
            )

    # 1. Any confirmed/unresolved field_lineage to an output/storage target is also
    # output-field provenance with an ingress/Kafka-consumed origin. This preserves
    # exact source_field -> target_field proof without re-inferring it.
    for lf in field_lineage_facts:
        props = lf.properties or {}
        role = str(props.get("field_role") or "")
        if role not in OUTPUT_FIELD_ROLES:
            continue
        boundary = _output_boundary_from_field_role(role, props.get("target_boundary"))
        source_boundary = str(props.get("source_boundary") or "")
        okind = _origin_from_source_boundary(source_boundary)
        trace_hint = str(props.get("trace_hint") or "unresolved")
        add(
            published_boundary=boundary,
            published_operation=str(props.get("target_operation") or props.get("source_operation") or ""),
            published_payload=str(props.get("target_payload") or "unknown"),
            published_field=str(props.get("target_field") or props.get("source_field") or "unknown"),
            published_location=str(props.get("target_location") or boundary),
            immediate_origin_kind=okind,
            ultimate_origin_kind=okind,
            origin_operation=str(props.get("source_operation") or ""),
            origin_payload=str(props.get("source_payload") or "unknown"),
            origin_field=str(props.get("source_field") or ""),
            origin_expression=f"{props.get('source_parameter')}.{props.get('source_field')}",
            path=[str(x) for x in (props.get("path") or [])],
            trace_hint=trace_hint,
            missing_links=[str(x) for x in (props.get("missing_links") or [])],
            evidence_refs=[str(props.get("field_lineage_id") or ""), *[str(x) for x in (props.get("evidence_refs") or [])]],
            evidence=lf.evidence,
            resolver_rank=float(props.get("resolver_rank") or 0.7),
            extra={
                "related_field_lineage_id": props.get("field_lineage_id"),
                "source_boundary": source_boundary,
                "field_role": role,
                "target_boundary": props.get("target_boundary"),
            },
        )

    # 2. REST response fields, including service result passthrough and unknown field
    # origins. This prevents reports from treating all response fields as input data.
    for op, mi in sorted(methods.items()):
        if not mi.get("rest_class"):
            continue
        mapping = next((a for a in (mi.get("annotations") or []) if a.get("name") in {"GetMapping", "PostMapping", "PutMapping", "DeleteMapping", "PatchMapping", "RequestMapping"}), None)
        if not mapping:
            continue
        response_type = _response_payload_type_for_method(mi, schema_fields)
        response_fields = _fields_for_type(schema_fields, response_type)
        if not response_fields:
            continue
        body = mi.get("body") or ""
        evidence = _op_file_evidence(mi, "java_output_field_provenance_rest_response")
        variable_origins = _variable_origins(body, mi.get("params") or [], mi)
        ingress_by_param = {str(o.get("payload_parameter")): o for o in origins_by_operation.get(op, []) if o.get("payload_parameter")}
        lookup_fields = _collect_lookup_fields(mi, ingress_by_param, schema_fields)
        mapped_fields: set[str] = set()
        returns = _return_expressions_from_method_info(mi)
        return_blob = " ".join(returns)
        for b in _setter_bindings_any_source(body, mi) + _builder_bindings_any_source(body, mi):
            target_var = b.get("target_variable")
            if target_var and return_blob and not _contains_symbol(return_blob, str(target_var)):
                continue
            target_field = str(b.get("target_field") or "")
            if not target_field:
                continue
            # If response schema is known, ignore setters that do not target response fields.
            if response_fields and target_field not in {f.get("name") for f in response_fields}:
                continue
            origin_info = _source_expr_to_origin(str(b.get("source_expression") or ""), method_info=mi, variable_origins=variable_origins, ingress_by_param=ingress_by_param)
            if origin_info.get("ultimate_origin_kind") in {"unknown", None}:
                deep_info = _resolve_expr_deep_origin(
                    str(b.get("source_expression") or ""), target_field, method_info=mi, methods=methods,
                    schema_fields=schema_fields, class_fields=class_fields, class_infos=class_infos,
                    iface_impls=iface_impls, root_ingress_by_param=ingress_by_param, visited=set(), depth=1,
                )
                if deep_info and deep_info.get("ultimate_origin_kind") not in {"unknown", None}:
                    origin_info = deep_info
            mapped_fields.add(target_field)
            missing = [] if origin_info.get("ultimate_origin_kind") not in {"unknown", None} else ["source expression could not be resolved to ingress/db/external/constant/computed origin after deep in-repository analysis"]
            add(
                published_boundary="rest_response",
                published_operation=op,
                published_payload=response_type,
                published_field=target_field,
                published_location="response_body_field",
                immediate_origin_kind=str(origin_info.get("immediate_origin_kind") or "unknown"),
                ultimate_origin_kind=str(origin_info.get("ultimate_origin_kind") or "unknown"),
                origin_operation=origin_info.get("origin_operation"),
                origin_payload=origin_info.get("origin_payload"),
                origin_field=origin_info.get("origin_field"),
                origin_expression=origin_info.get("origin_expression"),
                path=[*([op] if op else []), *[str(x) for x in (origin_info.get("path") or [])], f"REST response.{target_field}"],
                trace_hint=str(origin_info.get("trace_hint") or "unresolved"),
                missing_links=missing,
                evidence_refs=[str(x.get("ingress_id") or "") for x in ingress_by_param.values()],
                evidence=evidence,
                resolver_rank=0.78 if origin_info.get("ultimate_origin_kind") != "unknown" else 0.45,
                extra={"mapping_kind": b.get("kind"), "input_origins": origin_info.get("input_origins") or [], "input_origin_kinds": origin_info.get("input_origin_kinds") or [], "lookup_fields": lookup_fields, "provenance_depth": origin_info.get("provenance_depth", 0), "unresolved_boundary": origin_info.get("unresolved_boundary")},
            )
            response_field_info = next((rf for rf in response_fields if rf.get("name") == target_field), None)
            if response_field_info:
                add_nested_response_fields(
                    op=op, response_type=response_type, container_info=response_field_info,
                    source_expr=str(b.get("source_expression") or ""), method_info=mi,
                    ingress_by_param=ingress_by_param, lookup_fields=lookup_fields, evidence=evidence,
                    base_path=[op, str(b.get("expression") or "")],
                )
        # Direct return of a variable whose assignment is a service/repository/external call.
        for ret in returns:
            rv = _clean_expression(ret)
            vorig = variable_origins.get(rv)
            if not vorig:
                continue
            for f in response_fields:
                field = str(f.get("name") or "")
                if not field or field in mapped_fields:
                    continue
                immediate = str(vorig.get("immediate_origin_kind") or "unknown")
                ultimate = str(vorig.get("ultimate_origin_kind") or immediate or "unknown")
                deep_info = _resolve_expr_deep_origin(
                    str(vorig.get("origin_expression") or rv), field, method_info=mi, methods=methods,
                    schema_fields=schema_fields, class_fields=class_fields, class_infos=class_infos,
                    iface_impls=iface_impls, root_ingress_by_param=ingress_by_param, visited=set(), depth=1,
                )
                if deep_info and deep_info.get("ultimate_origin_kind") not in {"unknown", None}:
                    # Keep the local fact that the controller published a service/mapper result,
                    # but use the deeper in-repository source as the ultimate origin.
                    immediate = immediate if immediate not in {"unknown", "computed"} else str(deep_info.get("immediate_origin_kind") or immediate)
                    ultimate = str(deep_info.get("ultimate_origin_kind") or ultimate)
                    origin_operation = deep_info.get("origin_operation") or vorig.get("origin_operation")
                    origin_payload = deep_info.get("origin_payload") or vorig.get("origin_payload") or response_type
                    origin_field = deep_info.get("origin_field") or field
                    origin_expression = deep_info.get("origin_expression") or vorig.get("origin_expression")
                    path = [str(vorig.get("origin_expression") or rv), *[str(x) for x in (deep_info.get("path") or [])], f"return {rv}", f"REST response.{field}"]
                    trace_hint = "unresolved" if deep_info.get("trace_hint") in {"unresolved", "confirmed"} else str(deep_info.get("trace_hint") or "unresolved")
                    missing = [str(x) for x in (deep_info.get("missing_links") or [])]
                    resolver_rank = float(deep_info.get("resolver_rank") or 0.66)
                    extra_deep = {"provenance_depth": deep_info.get("provenance_depth", 1), "unresolved_boundary": deep_info.get("unresolved_boundary"), "callee_operation": deep_info.get("callee_operation"), "callee_resolution_kind": deep_info.get("callee_resolution_kind")}
                else:
                    missing = []
                    if ultimate == "unknown":
                        missing = ["response object is returned from a service/mapper/local variable, but ultimate field source is not resolved after deep in-repository analysis"]
                    origin_operation = vorig.get("origin_operation")
                    origin_payload = vorig.get("origin_payload") or response_type
                    origin_field = field if immediate in {"service_result_field", "repository_result_field", "external_service_response_field", "cache_read_field", "mapper_result_field"} else None
                    origin_expression = vorig.get("origin_expression")
                    path = [str(vorig.get("origin_expression") or rv), f"return {rv}", f"REST response.{field}"]
                    trace_hint = "unresolved" if ultimate != "unknown" else "unresolved"
                    resolver_rank = 0.64 if ultimate != "unknown" else 0.42
                    extra_deep = {"provenance_depth": 0, "unresolved_boundary": "service_result" if ultimate == "unknown" else None}
                add(
                    published_boundary="rest_response",
                    published_operation=op,
                    published_payload=response_type,
                    published_field=field,
                    published_location="response_body_field",
                    immediate_origin_kind=immediate,
                    ultimate_origin_kind=ultimate,
                    origin_operation=origin_operation,
                    origin_payload=origin_payload,
                    origin_field=origin_field,
                    origin_expression=origin_expression,
                    path=path,
                    trace_hint=trace_hint,
                    missing_links=missing,
                    evidence_refs=[str(x.get("ingress_id") or "") for x in ingress_by_param.values()],
                    evidence=evidence,
                    resolver_rank=resolver_rank,
                    extra={"source_variable": rv, "source_variable_type": vorig.get("type"), "lookup_fields": lookup_fields, **extra_deep},
                )
                add_nested_response_fields(
                    op=op, response_type=response_type, container_info=f,
                    source_expr=str(vorig.get("origin_expression") or rv), method_info=mi,
                    ingress_by_param=ingress_by_param, lookup_fields=lookup_fields, evidence=evidence,
                    source_variable=rv, source_variable_origin=vorig,
                    base_path=[str(vorig.get("origin_expression") or rv), f"return {rv}"],
                )
        # If output schema is known but no mapping was found for some fields, keep
        # explicit unknown provenance so downstream reports do not invent origin.
        for f in response_fields:
            field = str(f.get("name") or "")
            if not field or field in mapped_fields:
                continue
            # Avoid duplicate if direct return above already added this field.
            if any((pf.properties or {}).get("published_boundary") == "rest_response" and (pf.properties or {}).get("published_operation") == op and (pf.properties or {}).get("published_field") == field for pf in facts):
                continue
            add(
                published_boundary="rest_response",
                published_operation=op,
                published_payload=response_type,
                published_field=field,
                published_location="response_body_field",
                immediate_origin_kind="unknown",
                ultimate_origin_kind="unknown",
                origin_operation=None,
                origin_payload=None,
                origin_field=None,
                origin_expression=None,
                path=[op, f"REST response schema field {field}"],
                trace_hint="unknown",
                missing_links=["response field is present in response schema, but no field-level assignment or origin was found"],
                evidence_refs=[str(x.get("ingress_id") or "") for x in ingress_by_param.values()],
                evidence=evidence,
                resolver_rank=0.30,
                extra={"source_field_type": f.get("type"), "source_field_role": f.get("role")},
            )
            add_nested_response_fields(
                op=op, response_type=response_type, container_info=f, source_expr=None, method_info=mi,
                ingress_by_param=ingress_by_param, lookup_fields=lookup_fields, evidence=evidence,
                base_path=[op, f"REST response schema field {field}"],
            )

    # 3. Whole outbound payloads not already covered by exact field_lineage. This
    # covers outbound-only public methods and service result publications.
    for flow in flow_facts:
        if flow.fact_type != "source_to_sink_flow":
            continue
        props = flow.properties or {}
        op = str(props.get("operation") or "")
        mi = methods.get(op)
        if not mi:
            continue
        boundary, _role = _target_boundary_for_sink(str(props.get("sink_kind") or ""))
        if boundary not in {"kafka", "http_client", "rest_response"}:
            continue
        source_type = _simple_type_name(props.get("source_type"))
        fields = _fields_for_type(schema_fields, source_type)
        if not fields:
            continue
        evidence = flow.evidence or _op_file_evidence(mi, "java_output_field_provenance_outbound")
        for f in fields:
            field = str(f.get("name") or "")
            if not field:
                continue
            if any((pf.properties or {}).get("published_operation") == op and (pf.properties or {}).get("published_boundary") == boundary and (pf.properties or {}).get("published_field") == field for pf in facts):
                continue
            add(
                published_boundary=boundary,
                published_operation=op,
                published_payload=str(props.get("payload_expression") or source_type),
                published_field=field,
                published_location="message_value_field" if boundary == "kafka" else "request_body_field" if boundary == "http_client" else "response_body_field",
                immediate_origin_kind="method_parameter",
                ultimate_origin_kind="unknown",
                origin_operation=None,
                origin_payload=source_type,
                origin_field=field,
                origin_expression=f"{props.get('source_parameter')}.{field}",
                path=[f"{props.get('source_parameter')}.{field}", f"{boundary}.{field}"],
                trace_hint="unresolved",
                missing_links=["outbound payload field is known, but no confirmed system ingress/db/external origin was resolved"],
                evidence_refs=[str(props.get("flow_id") or "")],
                evidence=evidence,
                resolver_rank=0.40,
                extra={"related_flow_id": props.get("flow_id"), "sink_kind": props.get("sink_kind")},
            )

    # 4. Storage persisted fields that are not exact ingress field_lineage. Read-only
    # and delete/mutation without clear payload are intentionally not persisted fields.
    for access in storage_accesses:
        if access.get("access_kind") != "write":
            continue
        op = str(access.get("operation") or "")
        mi = methods.get(op)
        if not mi:
            continue
        body = mi.get("body") or ""
        payload = _clean_expression(access.get("payload_expression"))
        payload_type = _simple_type_name((mi.get("var_types") or {}).get(payload) or next((p.get("type") for p in mi.get("params") or [] if p.get("name") == payload), None))
        fields = _fields_for_type(schema_fields, payload_type)
        if not fields:
            continue
        variable_origins = _variable_origins(body, mi.get("params") or [], mi)
        ingress_by_param = {str(o.get("payload_parameter")): o for o in origins_by_operation.get(op, []) if o.get("payload_parameter")}
        evidence = _op_file_evidence(mi, "java_output_field_provenance_storage")
        mapped: set[str] = set()
        for b in _setter_bindings_any_source(body, mi):
            target_var = str(b.get("target_variable") or "")
            if target_var and payload and not _contains_symbol(payload, target_var):
                continue
            target_field = str(b.get("target_field") or "")
            if not target_field:
                continue
            if target_field not in {f.get("name") for f in fields}:
                continue
            mapped.add(target_field)
            source_expr = str(b.get("source_expression") or "")
            origin_info = _source_expr_to_origin(source_expr, method_info=mi, variable_origins=variable_origins, ingress_by_param=ingress_by_param)
            if origin_info.get("ultimate_origin_kind") in {"unknown", None}:
                deep_info = _resolve_expr_deep_origin(
                    source_expr, target_field, method_info=mi, methods=methods, schema_fields=schema_fields,
                    class_fields=class_fields, class_infos=class_infos, iface_impls=iface_impls,
                    root_ingress_by_param=ingress_by_param, visited=set(), depth=1,
                )
                if deep_info and deep_info.get("ultimate_origin_kind") not in {"unknown", None}:
                    origin_info = deep_info
            add(
                published_boundary="storage",
                published_operation=op,
                published_payload=payload_type,
                published_field=target_field,
                published_location="storage_payload_field",
                immediate_origin_kind=str(origin_info.get("immediate_origin_kind") or "unknown"),
                ultimate_origin_kind=str(origin_info.get("ultimate_origin_kind") or "unknown"),
                origin_operation=origin_info.get("origin_operation"),
                origin_payload=origin_info.get("origin_payload"),
                origin_field=origin_info.get("origin_field"),
                origin_expression=origin_info.get("origin_expression"),
                path=[*([str(origin_info.get("origin_expression"))] if origin_info.get("origin_expression") else []), f"storage.{target_field}"],
                trace_hint=str(origin_info.get("trace_hint") or "unresolved"),
                missing_links=[] if origin_info.get("ultimate_origin_kind") != "unknown" else ["storage payload field assignment source was not resolved"],
                evidence_refs=[str(access.get("storage_access_id") or ""), *[str(x.get("ingress_id") or "") for x in ingress_by_param.values()]],
                evidence=evidence,
                resolver_rank=0.78 if origin_info.get("ultimate_origin_kind") != "unknown" else 0.42,
                extra={"storage_access_id": access.get("storage_access_id"), "table_or_repository": access.get("table_or_repository"), "provenance_depth": origin_info.get("provenance_depth", 0), "unresolved_boundary": origin_info.get("unresolved_boundary")},
            )
        for f in fields:
            field = str(f.get("name") or "")
            if not field or field in mapped:
                continue
            if any((pf.properties or {}).get("published_boundary") == "storage" and (pf.properties or {}).get("published_operation") == op and (pf.properties or {}).get("published_field") == field for pf in facts):
                continue
            add(
                published_boundary="storage",
                published_operation=op,
                published_payload=payload_type,
                published_field=field,
                published_location="storage_payload_field",
                immediate_origin_kind="unknown",
                ultimate_origin_kind="unknown",
                origin_operation=None,
                origin_payload=None,
                origin_field=None,
                origin_expression=None,
                path=[f"repository.save({payload}).{field}"],
                trace_hint="unknown",
                missing_links=["payload is persisted, but field-level source was not resolved"],
                evidence_refs=[str(access.get("storage_access_id") or "")],
                evidence=evidence,
                resolver_rank=0.30,
                extra={"storage_access_id": access.get("storage_access_id"), "table_or_repository": access.get("table_or_repository")},
            )

    origin_counts = Counter(str((f.properties or {}).get("ultimate_origin_kind") or (f.properties or {}).get("origin_kind")) for f in facts)
    boundary_counts = Counter(str((f.properties or {}).get("published_boundary")) for f in facts)
    trace_status_counts = Counter(str((f.properties or {}).get("trace_status")) for f in facts)
    unresolved_counts = Counter(str((f.properties or {}).get("unresolved_boundary") or "resolved") for f in facts)
    deep_resolved = sum(1 for f in facts if int((f.properties or {}).get("provenance_depth") or 0) > 0 and (f.properties or {}).get("ultimate_origin_kind") not in {"unknown", None})
    nested_fields = sum(1 for f in facts if (f.properties or {}).get("nested_field_provenance"))
    return facts, {
        "output_field_provenance_extracted": len(facts),
        "output_field_provenance_deep_resolved": deep_resolved,
        "output_field_provenance_nested_fields": nested_fields,
        "output_field_provenance_origin_counts": dict(sorted(origin_counts.items())),
        "output_field_provenance_boundary_counts": dict(sorted(boundary_counts.items())),
        "output_field_provenance_trace_status_counts": dict(sorted(trace_status_counts.items())),
        "output_field_provenance_unresolved_boundary_counts": dict(sorted(unresolved_counts.items())),
    }

__all__ = [name for name in globals() if name.startswith("_") or name.startswith("build_java")]
