from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from code_analyzer_core.models import Fact, EvidenceRef
from code_analyzer_core.evidence_contract import maturity_props as _maturity_props
from code_analyzer_core.utils import read_text, line_number_for_offset
from code_analyzer_core.scanners.java_syntax import (
    parse_java_files,
    method_params_as_dicts,
    method_syntax_dict,
    class_annotations_text,
    method_visibility as _ts_method_visibility,
)
from code_analyzer_core.scanners.java_trace_common import *
from code_analyzer_core.scanners.java_evidence_pipeline import (
    _candidate_signals_for_access,
    _persistence_maturity_for_access,
    _physical_storage_maturity_for_access,
)
from code_analyzer_core.scanners.java_flow_builder import (
    _parse_params,
    _parameter_names,
    _clean_expression,
    _assignment_map,
    _assignment_map_from_syntax,
    _source_param_for_payload,
    _class_name_for_position,
)
from code_analyzer_core.scanners.java_persistence_jooq import _jooq_field_constant_to_column


def _var_type_maps_from_syntax(method, params: list[dict[str, Any]]) -> tuple[dict[str, str], dict[str, str]]:
    raw_types = {p.get("name", ""): _strip_java_modifiers(p.get("type")) for p in params if p.get("name")}
    simple_types = {name: _simple_type_name(raw) for name, raw in raw_types.items()}
    for assignment in method.assignments:
        if assignment.assignment_kind != "variable_declaration":
            continue
        raw = _strip_java_modifiers(assignment.declared_type)
        if raw == "var":
            creation = next((c for c in method.object_creations if c.start_byte >= assignment.start_byte and c.end_byte <= assignment.end_byte), None)
            raw = creation.type if creation else "unknown"
        if assignment.target and raw and raw != "unknown":
            raw_types[assignment.target] = raw
            simple_types[assignment.target] = _simple_type_name(raw)
    return simple_types, raw_types

def _build_method_index(files: list[Path]) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, str]], dict[str, dict[str, Any]], list[str]]:
    methods: dict[str, dict[str, Any]] = {}
    class_fields: dict[str, dict[str, str]] = defaultdict(dict)
    class_field_declarations: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    class_infos: dict[str, dict[str, Any]] = {}
    warnings: list[str] = []

    parsed_files, parse_warnings = parse_java_files(files)
    warnings.extend(parse_warnings)

    for parsed in parsed_files:
        p = parsed.file
        imports = list(parsed.imports)
        for cls in parsed.classes:
            ann_window = class_annotations_text(cls)
            annotations = sorted({a.name for a in cls.annotations})
            component = next((a.name for a in cls.annotations if a.name in {"RestController", "Controller", "Service", "Component", "Repository"}), None)
            class_infos[cls.name] = {
                "class_name": cls.name,
                "fqcn": f"{parsed.package}.{cls.name}" if parsed.package else cls.name,
                "package": parsed.package,
                "file": str(p),
                "kind": cls.kind,
                "interfaces": list(cls.implements),
                "superclass": _simple_type_name(cls.extends) if cls.extends else None,
                "annotations": annotations,
                "spring_component_kind": component,
                "is_spring_component": bool(component),
                "lombok_required_args": "RequiredArgsConstructor" in annotations,
                "imports": imports,
                "syntax_provider": "tree_sitter",
            }
            for field in cls.fields:
                if field.name != "serialVersionUID":
                    class_fields[cls.name][field.name] = _normalize_java_type(_strip_java_modifiers(field.type))
                    class_field_declarations[cls.name][field.name] = {
                        "name": field.name,
                        "type": _normalize_java_type(_strip_java_modifiers(field.type)),
                        "raw": field.raw,
                        "modifiers": field.modifiers,
                        "initializer": field.initializer,
                        "initializer_tree": field.initializer_tree,
                        "initializer_symbols": list(field.initializer_symbols or ()),
                        "line_start": field.line_start,
                        "line_end": field.line_end,
                    }

            rest_class = any(a.name in {"RestController", "Controller"} for a in cls.annotations)
            for method in cls.methods:
                params = method_params_as_dicts(method)
                parameter_types = [
                    _normalize_java_type(_strip_java_modifiers(param.get("type")))
                    for param in params
                ]
                operation_signature = (
                    f"{class_infos.get(cls.name, {}).get('fqcn', cls.name)}"
                    f"#{method.name}({','.join(parameter_types)})"
                )
                param_names = _parameter_names(params)
                var_types, raw_var_types = _var_type_maps_from_syntax(method, params)
                for field_name, field_type in class_fields.get(cls.name, {}).items():
                    raw_var_types.setdefault(field_name, field_type)
                    var_types.setdefault(field_name, _simple_type_name(field_type))
                method_info = {
                    "operation": method.operation,
                    "operation_signature": operation_signature,
                    "class_name": cls.name,
                    "class_fqcn": class_infos.get(cls.name, {}).get("fqcn", cls.name),
                    "method_name": method.name,
                    "return_type": _normalize_java_type(method.return_type),
                    "params": params,
                    "param_names": param_names,
                    "body": method.body or method.text,
                    "file": p,
                    "line_start": method.line_start,
                    "line_end": method.line_end,
                    "snippet": method.text[:1800] + ("\n... method truncated ..." if len(method.text) > 1800 else ""),
                    "annotation_window": method.annotation_window,
                    "annotations": [{"name": a.name, "arguments": a.arguments, "text": a.text, "line_start": a.line_start} for a in method.annotations],
                    "rest_class": rest_class,
                    "class_annotations": annotations,
                    "class_interfaces": list(cls.implements),
                    **method_syntax_dict(method),
                    "assignments": {
                        **_assignment_map_from_syntax(method.assignments, param_names),
                        **_enhanced_assignment_map_from_method_info(method_syntax_dict(method), param_names),
                    },
                    "var_types": var_types,
                    "raw_var_types": raw_var_types,
                    # Keep declaration provenance separate from local variables.
                    # Constructor lineage uses this to distinguish an implicit
                    # `this.field` pass-through from an unrelated local symbol.
                    "class_field_types": dict(class_fields.get(cls.name, {})),
                    "class_field_declarations": dict(class_field_declarations.get(cls.name, {})),
                    "imports": imports,
                    "method_visibility": _ts_method_visibility(method),
                    "syntax_provider": "tree_sitter",
                }
                # Preserve every source-declared overload.  The legacy `methods`
                # mapping intentionally remains keyed by `Type.method` for callers
                # that consume operation-level identities, but call extraction must
                # not silently discard earlier overload bodies.
                class_infos[cls.name].setdefault("method_variants", []).append(method_info)
                methods[method.operation] = method_info
    return methods, class_fields, class_infos, warnings


def _method_variants(
    methods: dict[str, dict[str, Any]],
    class_infos: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    variants = [
        variant
        for info in class_infos.values()
        for variant in (info.get("method_variants") or [])
        if isinstance(variant, dict)
    ]
    if not variants:
        variants = list(methods.values())
    return sorted(
        variants,
        key=lambda item: (
            str(item.get("operation_signature") or item.get("operation") or ""),
            str(item.get("file") or ""),
            int(item.get("line_start") or 0),
        ),
    )

def _detect_origins(methods: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    origins: list[dict[str, Any]] = []
    seq = 0
    for op, mi in sorted(methods.items()):
        annotations = mi.get("annotations") or []
        params = mi.get("params") or []

        def annotation_named(names: set[str]) -> dict[str, Any] | None:
            return next((a for a in annotations if a.get("name") in names), None)

        def add(kind: str, *, payload_param: str | None, payload_type: str | None, endpoint: str | None, match_strength: float, is_payload_origin: bool = True, payload_resolution_status: str | None = None, payload_resolution_basis: list[dict[str, Any]] | None = None) -> None:
            nonlocal seq
            seq += 1
            origins.append({
                "ingress_id": f"ingress_{seq:06d}",
                "origin_id": f"origin_{seq:06d}",
                "kind": "ingress",
                "ingress_kind": kind,
                "origin_kind": kind,
                "is_payload_origin": is_payload_origin,
                "operation": op,
                "operation_id": op,
                "class_name": mi["class_name"],
                "method_name": mi["method_name"],
                "signature": f"{op}({', '.join(p.get('type', 'unknown') + ' ' + p.get('name', '') for p in params)})",
                "payload_type": payload_type or "unknown",
                "payload_parameter": payload_param,
                "endpoint_or_topic": endpoint,
                "match_strength": match_strength,
                "payload_resolution_status": payload_resolution_status or ("declared_parameter_type" if payload_type else "unknown"),
                "payload_resolution_basis": payload_resolution_basis or [],
                    })

        mapping = annotation_named({"GetMapping", "PostMapping", "PutMapping", "DeleteMapping", "PatchMapping", "RequestMapping"})
        if mi.get("rest_class") and mapping:
            payload_param = None
            payload_type = None
            for p in params:
                if "RequestBody" in (p.get("annotations") or []):
                    payload_param = p.get("name")
                    payload_type = _normalize_java_type(p.get("type"))
                    break
            if not payload_param and params:
                # Fallback: first non-framework object parameter, but mark slightly lower strength.
                for p in params:
                    typ = _normalize_java_type(p.get("type"))
                    if typ not in {"String", "int", "long", "boolean", "HttpServletRequest", "HttpServletResponse"}:
                        payload_param = p.get("name")
                        payload_type = typ
                        break
            add(
                "rest_controller",
                payload_param=payload_param,
                payload_type=payload_type,
                endpoint=_extract_annotation_value(mapping.get("arguments")) or str(mapping.get("name") or ""),
                match_strength=0.88 if payload_param else 0.72,
                is_payload_origin=payload_param is not None,
            )

        kafka = annotation_named({"KafkaListener"})
        if kafka:
            payload_param = params[0].get("name") if params else None
            declared_payload_type = _normalize_java_type(params[0].get("type")) if params else "unknown"
            kafka_payload = _kafka_payload_type_from_method_info(mi)
            resolved_payload_type = kafka_payload.get("payload_type") or declared_payload_type
            resolution_status = str(kafka_payload.get("status") or "not_found")
            if resolution_status == "not_found":
                resolution_status = "declared_parameter_type"
            add(
                "kafka_listener",
                payload_param=payload_param,
                payload_type=resolved_payload_type,
                endpoint=_extract_annotation_value(kafka.get("arguments")),
                match_strength=0.92 if kafka_payload.get("payload_type") else (0.86 if payload_param else 0.70),
                is_payload_origin=payload_param is not None,
                payload_resolution_status=resolution_status,
                payload_resolution_basis=list(kafka_payload.get("basis") or []),
            )

        scheduled = annotation_named({"Scheduled"})
        if scheduled:
            add(
                "scheduled_trigger",
                payload_param=None,
                payload_type=None,
                endpoint=_extract_annotation_value(scheduled.get("arguments")),
                match_strength=0.72,
                is_payload_origin=False,
            )
    return origins
def _interface_impls(class_infos: dict[str, dict[str, Any]], methods: dict[str, dict[str, Any]]) -> dict[str, list[str]]:
    impls: dict[str, list[str]] = defaultdict(list)
    for cls, info in class_infos.items():
        if info.get("kind") == "interface":
            continue
        for iface in info.get("interfaces") or []:
            if iface:
                impls[iface].append(cls)
        superclass = info.get("superclass")
        if superclass and superclass != "unknown":
            impls[superclass].append(cls)
    # Name convention fallback is important in source-only Spring projects.
    classes = {mi["class_name"] for mi in methods.values()}
    for cls in sorted(classes):
        if cls.endswith("Impl"):
            impls.setdefault(cls[:-4], []).append(cls)
    return {k: sorted(set(v)) for k, v in impls.items()}
def _operation_exists(methods: dict[str, dict[str, Any]], class_name: str, method_name: str) -> bool:
    return f"{class_name}.{method_name}" in methods
def _class_has_method(methods: dict[str, dict[str, Any]], class_name: str, method_name: str) -> bool:
    return _operation_exists(methods, class_name, method_name)

MAX_RECEIVER_CANDIDATES_PER_CALL = 8


def _receiver_resolution_index(methods: dict[str, dict[str, Any]], class_infos: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Build O(1) lookup tables for source-only receiver resolution.

    The previous resolver used repeated `any(op.startswith(...))` scans over the
    whole method index for static/name-heuristic resolution. On real Spring
    applications this turns call graph construction into a large N x M loop.
    """
    class_names: set[str] = set(class_infos.keys())
    method_by_class: dict[tuple[str, str], str] = {}
    method_variants_by_class: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    classes_by_method: dict[str, set[str]] = defaultdict(set)
    for mi in _method_variants(methods, class_infos):
        op = str(mi.get("operation") or "")
        cls = str(mi.get("class_name") or op.split(".", 1)[0])
        method = str(mi.get("method_name") or op.rsplit(".", 1)[-1])
        if not cls or not method:
            continue
        class_names.add(cls)
        method_by_class[(cls, method)] = op
        method_variants_by_class[(cls, method)].append(mi)
        classes_by_method[method].add(cls)
    return {
        "class_names": class_names,
        "method_by_class": method_by_class,
        "method_variants_by_class": {
            key: tuple(sorted(value, key=lambda item: str(item.get("operation_signature") or "")))
            for key, value in method_variants_by_class.items()
        },
        "classes_by_method": classes_by_method,
    }


def _class_has_method_index(index: dict[str, Any] | None, class_name: str, method_name: str) -> bool:
    if index:
        return (class_name, method_name) in (index.get("method_by_class") or {})
    return False


def _resolve_receiver_candidates(
    receiver: str | None,
    method_name: str,
    mi: dict[str, Any],
    class_fields: dict[str, dict[str, str]],
    class_infos: dict[str, dict[str, Any]],
    methods: dict[str, dict[str, Any]],
    iface_impls: dict[str, list[str]],
    resolution_index: dict[str, Any] | None = None,
    *,
    argument_count: int | None = None,
    argument_type_hints: list[str | None] | None = None,
) -> list[dict[str, Any]]:
    """Resolve a source-level receiver to possible callee operations.

    This is intentionally source-only and Spring-aware. It does not require bytecode or
    classpath, so interface dispatch and bean resolution are represented as unresolved until inspected
    edges rather than compiler-grade facts.
    """
    out: list[dict[str, Any]] = []
    current_class = mi["class_name"]
    receiver = _clean_expression(receiver) if receiver else ""

    def add(cls: str, kind: str, conf: float, declared_type: str | None = None) -> None:
        variants = list(
            ((resolution_index or {}).get("method_variants_by_class") or {}).get((cls, method_name), ())
        )
        if not variants:
            op = ((resolution_index or {}).get("method_by_class") or {}).get((cls, method_name))
            legacy = methods.get(op or f"{cls}.{method_name}")
            variants = [legacy] if legacy else []
        if argument_count is not None:
            arity_matches = [v for v in variants if len(v.get("params") or []) == argument_count]
            if arity_matches:
                variants = arity_matches

        exact_type_matches: list[dict[str, Any]] = []
        hints = list(argument_type_hints or [])
        if hints and any(hint for hint in hints):
            for variant in variants:
                parameter_types = [
                    _normalize_java_type(param.get("type"))
                    for param in (variant.get("params") or [])
                ]
                comparable = [
                    (hint, parameter_types[index] if index < len(parameter_types) else None)
                    for index, hint in enumerate(hints)
                    if hint
                ]
                if comparable and all(
                    _simple_type_name(hint) == _simple_type_name(parameter)
                    for hint, parameter in comparable
                ):
                    exact_type_matches.append(variant)
            if exact_type_matches:
                variants = exact_type_matches

        overload_count = len(variants)
        exact_overload = bool(exact_type_matches) and overload_count == 1
        for variant in variants:
            op = str(variant.get("operation") or f"{cls}.{method_name}")
            signature = str(variant.get("operation_signature") or op)
            if any(
                x.get("callee_operation_signature") == signature and x["resolution_kind"] == kind
                for x in out
            ):
                continue
            out.append({
                "callee_operation_id": op,
                "callee_operation_signature": signature,
                "callee_method_info": variant,
                "receiver_type": cls,
                "declared_type": declared_type or cls,
                "resolution_kind": kind,
                "overload_resolution": "exact_argument_types" if exact_overload else (
                    "single_arity_candidate" if overload_count == 1 else "ambiguous_same_arity"
                ),
                "overload_candidate_count": overload_count,
                "match_strength": conf if overload_count == 1 else min(conf, 0.62),
            })

    if not receiver or receiver in {"this", "self"}:
        add(current_class, "this_call", 0.90)
        return out

    # Static call: ClassName.method(...). Use the prebuilt class/method index;
    # never scan all operation ids per call.
    class_names = (resolution_index.get("class_names") if resolution_index else None) or set(class_infos.keys())
    if receiver in class_names and (not resolution_index or _class_has_method_index(resolution_index, receiver, method_name) or _class_has_method(methods, receiver, method_name)):
        add(receiver, "static_or_class_call", 0.82)
        return out

    declared_type = None
    if receiver in mi.get("var_types", {}):
        declared_type = _simple_type_name(mi["var_types"][receiver])
    if not declared_type:
        declared_type = _simple_type_name(class_fields.get(current_class, {}).get(receiver)) if class_fields.get(current_class, {}).get(receiver) else None

    if declared_type:
        has_declared_method = _class_has_method_index(resolution_index, declared_type, method_name) if resolution_index else _class_has_method(methods, declared_type, method_name)
        if has_declared_method:
            kind = "direct_local_variable" if receiver in mi.get("var_types", {}) else "spring_field_injection"
            add(declared_type, kind, 0.84 if kind == "direct_local_variable" else 0.76, declared_type)
        for impl in iface_impls.get(declared_type, [])[:MAX_RECEIVER_CANDIDATES_PER_CALL]:
            has_impl_method = _class_has_method_index(resolution_index, impl, method_name) if resolution_index else _class_has_method(methods, impl, method_name)
            if has_impl_method:
                add(impl, "spring_interface_dispatch", 0.70, declared_type)

    # Bean-name convention fallback: phoneBlockResyncHandler -> PhoneBlockResyncHandler.
    candidate = receiver[:1].upper() + receiver[1:]
    if not out and candidate:
        has_candidate_method = _class_has_method_index(resolution_index, candidate, method_name) if resolution_index else _class_has_method(methods, candidate, method_name)
        if has_candidate_method:
            add(candidate, "name_type_heuristic", 0.58, candidate)

    return sorted(out, key=lambda x: float(x.get("match_strength") or 0), reverse=True)[:MAX_RECEIVER_CANDIDATES_PER_CALL]


def _argument_type_hint(expression: str, method_info: dict[str, Any]) -> str | None:
    value = _clean_expression(expression or "")
    if not value:
        return None
    if value.startswith("this."):
        value = value[5:]
    if re.fullmatch(r"[A-Za-z_$][\w$]*", value):
        raw = (method_info.get("raw_var_types") or {}).get(value)
        if raw:
            return _normalize_java_type(raw)
    if re.fullmatch(r'"(?:[^"\\]|\\.)*"', value):
        return "String"
    if value in {"true", "false"}:
        return "boolean"
    return None
def _iter_call_matches(body: str, mi: dict[str, Any], methods: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    same_class_methods = {m["method_name"] for m in methods.values() if m["class_name"] == mi["class_name"]}
    for call in mi.get("method_calls") or []:
        method_name = call.get("method") or ""
        if method_name in CONTROL_WORDS or method_name in NOISE_METHODS:
            continue
        receiver = call.get("receiver")
        if not receiver and method_name not in same_class_methods:
            continue
        matches.append({
            "receiver": receiver or "this",
            "method": method_name,
            "args": call.get("args_text") or ", ".join(call.get("args") or []),
            "args_list": list(call.get("args") or []),
            "line_start": call.get("line_start"),
            "line_end": call.get("line_end"),
            "text": call.get("text") or "",
            "start": int(call.get("start_byte") or 0),
            "end": int(call.get("end_byte") or 0),
        })
    return sorted(matches, key=lambda x: (x.get("line_start") or 0, x.get("start") or 0))

def _build_call_facts(methods: dict[str, dict[str, Any]], class_fields: dict[str, dict[str, str]], class_infos: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    seq = 0
    iface_impls = _interface_impls(class_infos, methods)
    resolution_index = _receiver_resolution_index(methods, class_infos)

    for mi in _method_variants(methods, class_infos):
        op = str(mi.get("operation") or "")
        body = mi.get("body") or ""
        caller_params = mi.get("param_names") or set()
        assignments = mi.get("assignments") or {}
        for cm in _iter_call_matches(body, mi, methods):
            receiver = cm.get("receiver") or ""
            method_name = cm.get("method") or ""
            if method_name in NOISE_METHODS:
                continue
            args = list(cm.get("args_list") or _split_args(cm.get("args") or ""))
            candidates = _resolve_receiver_candidates(
                receiver,
                method_name,
                mi,
                class_fields,
                class_infos,
                methods,
                iface_impls,
                resolution_index,
                argument_count=len(args),
                argument_type_hints=[_argument_type_hint(arg, mi) for arg in args],
            )
            if not candidates:
                continue
            for candidate in candidates:
                callee_operation = candidate["callee_operation_id"]
                callee = candidate.get("callee_method_info") or methods.get(callee_operation)
                if not callee:
                    continue
                callee_params = callee.get("params") or []
                bindings: list[dict[str, Any]] = []
                for idx, arg in enumerate(args):
                    callee_param = callee_params[idx].get("name") if idx < len(callee_params) else None
                    callee_type = _normalize_java_type(callee_params[idx].get("type")) if idx < len(callee_params) else "unknown"
                    source_param, relation, via_local = _source_parameter_from_expression(arg, caller_params, assignments)
                    alias_info = assignments.get(via_local or "") if via_local else None
                    bindings.append({
                        "caller_expression": arg,
                        "caller_source_parameter": source_param,
                        "callee_parameter": callee_param,
                        "relation": relation,
                        "source_type": next((p.get("type") for p in mi.get("params") or [] if p.get("name") == source_param), "unknown"),
                        "target_type": callee_type,
                        "via_local_variable": via_local,
                        "alias_depth": alias_info.get("alias_depth") if isinstance(alias_info, dict) else None,
                        "alias_via": alias_info.get("alias_via") if isinstance(alias_info, dict) else None,
                        "binding_strength": _binding_strength(relation, candidate.get("resolution_kind", "unknown")),
                    })
                seq += 1
                line = int(cm.get("line_start") or mi.get("line_start") or 1)
                relation_summary = _relation_from_bindings(bindings)
                calls.append({
                    "call_id": f"call_{seq:06d}",
                    "kind": "method_call",
                    "caller_operation_id": op,
                    "caller_operation_signature": mi.get("operation_signature") or op,
                    "caller_method": op,
                    "callee_operation_id": callee_operation,
                    "callee_operation_signature": candidate.get("callee_operation_signature") or callee_operation,
                    "callee_method": callee_operation,
                    "receiver_expression": receiver,
                    "receiver_type": candidate.get("receiver_type"),
                    "declared_receiver_type": candidate.get("declared_type"),
                    "method_name": method_name,
                    "resolution_kind": candidate.get("resolution_kind"),
                    "overload_resolution": candidate.get("overload_resolution"),
                    "overload_candidate_count": candidate.get("overload_candidate_count"),
                    "callee_parameter_types": [
                        _normalize_java_type(param.get("type"))
                        for param in (callee.get("params") or [])
                    ],
                    "argument_bindings": bindings,
                    "argument_relation": relation_summary,
                    "file": str(mi["file"]),
                    "line_start": line,
                    "line_end": line,
                    "snippet": str(cm.get("text") or "")[:700],
                    "match_strength": min(float(candidate.get("match_strength") or 0.6), max([b.get("binding_strength", 0.5) for b in bindings] or [0.65]) + 0.1),
                })
    return calls
def _storage_operation_classification(method_name: str, args: list[str], receiver: str | None, sql_literal: str | None) -> dict[str, Any]:
    """Classify storage calls more precisely than the old write/read split.

    The result is technical only. It prevents delete/read/query/list processing from
    becoming false `persistent_write` candidates for ForeignDataPersistence.
    """
    method = str(method_name or "")
    low = method.lower()
    access_kind = "unknown"
    write_kind = "unknown"
    mutation_kind = None
    operation_kind = "unknown"
    writes_new_payload = False
    payload_role = "unknown"
    storage_resolution_level = "unresolved"
    storage_resolution_status = "not_applicable"

    if sql_literal:
        access_kind, write_kind = _write_kind_from_sql(sql_literal)
        if write_kind in {"insert", "merge"}:
            operation_kind = "upsert" if write_kind == "merge" else "insert"
            writes_new_payload = True
            payload_role = "saved_payload"
        elif write_kind == "update":
            operation_kind = "update"
            writes_new_payload = False
            payload_role = "mutation_value_or_key"
        elif write_kind == "delete":
            operation_kind = "delete"
            mutation_kind = "delete"
            payload_role = "delete_key"
        elif write_kind == "select":
            operation_kind = "read"
            payload_role = "filter_key"
        storage_resolution_level = "confirmed_sql" if access_kind in {"write", "mutation"} else "confirmed_sql_read"
        storage_resolution_status = "resolved_sql_literal"
        return {
            "access_kind": access_kind, "write_kind": write_kind, "mutation_kind": mutation_kind,
            "operation_kind": operation_kind, "writes_new_payload": writes_new_payload, "payload_role": payload_role,
            # Internal resolver state only. The public evidence contract exposes this as
            # confirmed/unresolved maturity plus navigation-only candidate_signals.
            "storage_resolution_level": storage_resolution_level,
            "storage_resolution_status": storage_resolution_status,
        }

    if method in WRITE_METHODS:
        write_kind = WRITE_METHODS[method]
        storage_resolution_level = "known_storage_api_or_framework_method"
        storage_resolution_status = "recognized_storage_method"
        if method == "put":
            access_kind = "write"
            operation_kind = "cache_write"
            writes_new_payload = True
            payload_role = "saved_payload"
        elif write_kind in {"save", "insert", "persist", "merge"}:
            access_kind = "write"
            operation_kind = "upsert" if write_kind == "merge" else write_kind
            writes_new_payload = True
            payload_role = "saved_payload"
        elif write_kind == "update":
            access_kind = "mutation"
            operation_kind = "update"
            mutation_kind = "update"
            writes_new_payload = False
            payload_role = "mutation_value_or_key"
        else:
            access_kind = "write"
            operation_kind = write_kind
            writes_new_payload = True
            payload_role = "saved_payload"
    elif method in DELETE_METHODS or low.startswith(("delete", "remove", "unlink", "clear")):
        storage_resolution_level = "known_storage_api_or_framework_method" if method in DELETE_METHODS else "custom_dao_boundary"
        storage_resolution_status = "recognized_storage_method" if method in DELETE_METHODS else "dao_implementation_not_resolved"
        access_kind = "mutation"
        write_kind = "delete"
        mutation_kind = "delete"
        operation_kind = "delete"
        writes_new_payload = False
        payload_role = "delete_key"
    elif low.startswith(DOMAIN_WRITE_METHOD_PREFIXES):
        storage_resolution_level = "custom_dao_boundary"
        storage_resolution_status = "dao_implementation_not_resolved"
        access_kind = "write"
        if low.startswith(("merge", "upsert", "saveorupdate")):
            write_kind = "merge"
            operation_kind = "upsert"
        elif low.startswith("insert"):
            write_kind = "insert"
            operation_kind = "insert"
        elif low.startswith("persist"):
            write_kind = "persist"
            operation_kind = "persist"
        else:
            write_kind = "save"
            operation_kind = "save"
        writes_new_payload = True
        payload_role = "saved_payload"
    elif low.startswith(DOMAIN_MUTATION_METHOD_PREFIXES):
        storage_resolution_level = "custom_dao_boundary"
        storage_resolution_status = "dao_implementation_not_resolved"
        access_kind = "mutation"
        write_kind = "update"
        mutation_kind = "status_update"
        operation_kind = "mutation"
        writes_new_payload = False
        payload_role = "mutation_key_or_status_value"
    elif method.startswith(READ_METHOD_PREFIXES) or low.startswith(READ_METHOD_PREFIXES):
        storage_resolution_level = "read_method"
        storage_resolution_status = "not_applicable"
        access_kind = "read"
        write_kind = "read"
        operation_kind = "read"
        writes_new_payload = False
        payload_role = "filter_key"
    return {
        "access_kind": access_kind, "write_kind": write_kind, "mutation_kind": mutation_kind,
        "operation_kind": operation_kind, "writes_new_payload": writes_new_payload, "payload_role": payload_role,
        # Internal resolver state only. The public evidence contract exposes this as
        # confirmed/unresolved maturity plus navigation-only candidate_signals.
        "storage_resolution_level": storage_resolution_level,
        "storage_resolution_status": storage_resolution_status,
    }


JOOQ_STORAGE_METHODS = {"insertInto", "update", "deleteFrom", "batchInsert", "batchUpdate"}


def _jooq_table_constant(raw: str | None) -> str | None:
    value = _clean_expression(raw)
    if not value:
        return None
    token = value.split(".")[-1].strip()
    token = re.sub(r"[^A-Za-z0-9_]", "_", token).strip("_")
    return token or None


def _jooq_storage_classification(method_name: str) -> dict[str, Any]:
    if method_name == "insertInto":
        return {"access_kind": "write", "write_kind": "insert", "operation_kind": "insert", "writes_new_payload": False, "payload_role": "jooq_insert_builder", "storage_resolution_level": "jooq_dsl_table_argument", "storage_resolution_status": "resolved_jooq_dsl_method"}
    if method_name == "update":
        return {"access_kind": "mutation", "write_kind": "update", "mutation_kind": "update", "operation_kind": "update", "writes_new_payload": False, "payload_role": "jooq_update_bind_or_set_value", "storage_resolution_level": "jooq_dsl_table_argument", "storage_resolution_status": "resolved_jooq_dsl_method"}
    if method_name == "deleteFrom":
        return {"access_kind": "mutation", "write_kind": "delete", "mutation_kind": "delete", "operation_kind": "delete", "writes_new_payload": False, "payload_role": "jooq_delete_key", "storage_resolution_level": "jooq_dsl_table_argument", "storage_resolution_status": "resolved_jooq_dsl_method"}
    if method_name == "batchInsert":
        return {"access_kind": "write", "write_kind": "insert", "operation_kind": "batch_insert", "writes_new_payload": True, "payload_role": "record_collection", "storage_resolution_level": "jooq_record_batch", "storage_resolution_status": "resolved_jooq_batch_method"}
    if method_name == "batchUpdate":
        return {"access_kind": "mutation", "write_kind": "update", "mutation_kind": "update", "operation_kind": "batch_update", "writes_new_payload": False, "payload_role": "record_collection_or_mutation_values", "storage_resolution_level": "jooq_record_batch", "storage_resolution_status": "resolved_jooq_batch_method"}
    return {"access_kind": "unknown", "write_kind": "unknown", "operation_kind": "unknown", "writes_new_payload": False, "payload_role": "unknown", "storage_resolution_level": "unresolved", "storage_resolution_status": "unknown"}


def _jooq_select_chain_accesses(mi: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract physical JOOQ reads represented by `select(...).from(TABLE)` chains.

    `from` is not a storage operation by itself, and `select` does not carry the
    table argument.  The Tree-sitter call receiver preserves the complete nested
    chain, which lets us join the selected fields, physical table and optional
    `fetchInto(Record.class)` target without SQL interpretation or name guessing.
    """
    calls = list(mi.get("method_calls") or [])
    fetch_calls = [call for call in calls if str(call.get("method") or "") == "fetchInto"]
    out: list[dict[str, Any]] = []
    for call in calls:
        if str(call.get("method") or "") != "from":
            continue
        receiver = str(call.get("receiver") or "")
        args = list(call.get("args") or [])
        if not args or ".select" not in receiver:
            continue
        select_match = re.search(r"(?:^|\.)select\s*\((?P<fields>.*)\)\s*$", receiver, re.S)
        if not select_match:
            continue
        table = _jooq_table_constant(args[0])
        if not table:
            continue
        selected_fields: list[str] = []
        selected_field_refs: list[str] = []
        for raw_field in _split_args(select_match.group("fields")):
            field_ref = _clean_expression(raw_field)
            field = _jooq_field_constant_to_column(field_ref)
            if field:
                selected_fields.append(field)
                selected_field_refs.append(field_ref)
        result_type = None
        chain_probe = _clean_expression(str(call.get("text") or receiver))
        for fetch in fetch_calls:
            fetch_receiver = _clean_expression(fetch.get("receiver"))
            if chain_probe and chain_probe not in fetch_receiver:
                continue
            fetch_args = list(fetch.get("args") or [])
            if fetch_args:
                result_type = _simple_type_name(str(fetch_args[0]).removesuffix(".class"))
                break
        out.append({
            "receiver_expression": "dsl",
            "storage_method": "select",
            "access_kind": "read",
            "write_kind": "read",
            "mutation_kind": None,
            "operation_kind": "select",
            "writes_new_payload": False,
            "payload_role": "selected_record_fields",
            "payload_expression": None,
            "storage_resolution_level": "confirmed_sql_read",
            "storage_resolution_status": "resolved_jooq_select_from_chain",
            "table_or_repository": table,
            "jooq_operation": True,
            "selected_fields": selected_fields,
            "selected_field_refs": selected_field_refs,
            "result_type": result_type,
            "line_start": call.get("line_start"),
            "line_end": call.get("line_end"),
            "snippet": str(call.get("text") or "")[:700],
            "match_strength": 0.94,
        })
    return out


def _receiver_jooq_like(receiver: str, mi: dict[str, Any]) -> bool:
    low = str(receiver or "").lower()
    if low in {"dsl", "dslcontext", "ctx", "context"}:
        return True
    raw_types = mi.get("raw_var_types") or {}
    simple_types = mi.get("var_types") or {}
    typ = str(raw_types.get(receiver) or simple_types.get(receiver) or "").lower()
    return "dslcontext" in typ or typ.endswith("dsl")


def _receiver_declared_type(receiver: str, mi: dict[str, Any]) -> str:
    raw_types = mi.get("raw_var_types") or {}
    simple_types = mi.get("var_types") or {}
    class_name = str(mi.get("class_name") or "")
    receiver_root = str(receiver or "").split(".", 1)[0].strip()
    return str(raw_types.get(receiver_root) or simple_types.get(receiver_root) or raw_types.get(receiver) or simple_types.get(receiver) or class_name)


def _ignite_cache_name_expression(receiver: str, args: list[str], method_name: str) -> tuple[str | None, str | None]:
    match = re.search(r"\.cache\s*\(([^()]*)\)", str(receiver or ""))
    if match:
        return _clean_expression(match.group(1)) or None, "nested_ignite_cache_call_argument"
    if method_name == "cache" and args:
        return _clean_expression(args[0]) or None, "ignite_cache_call_argument"
    return None, None


def _ignite_storage_observation(receiver: str, method_name: str, args: list[str], mi: dict[str, Any]) -> dict[str, Any] | None:
    """Classify direct, name/type-backed Ignite/cache API observations.

    The detector uses only Tree-sitter method-call receivers, declared Java types
    and exact method names. It does not infer that arbitrary Map/DAO calls are Ignite.
    """
    receiver_type = _receiver_declared_type(receiver, mi)
    probe = f"{receiver_type} {receiver}".lower()
    typed_ignite = any(token in probe for token in (
        "ignitecache", "igniteclient", "ignite_native", "ignitenativestorage",
        "purecachestorage", "defaultpureignitestorage", "cloudignitewriteradapter",
    ))
    writer_adapter = "ignitewriteradapter" in probe and method_name in {"writeRecord", "writeRichRecord"}
    if not (typed_ignite or writer_adapter):
        return None

    read_methods = {"get", "getAll", "query", "queryByCollocationId", "scan", "iterator", "cache", "storage"}
    write_methods = {"put", "putAll", "writeRecord", "writeRichRecord", "save", "insert", "merge", "persist"}
    delete_methods = {"remove", "removeAll", "delete", "clear"}
    if method_name in write_methods:
        access_kind = "write"
        write_kind = "cache_write"
        operation_kind = "ignite_cache_write"
        writes_new_payload = True
        payload_role = "saved_payload"
        payload_expression = args[-1] if method_name in {"put", "putAll"} and args else (args[0] if args else None)
    elif method_name in delete_methods:
        access_kind = "mutation"
        write_kind = "delete"
        operation_kind = "ignite_cache_delete"
        writes_new_payload = False
        payload_role = "delete_key"
        payload_expression = args[0] if args else None
    elif method_name in read_methods:
        access_kind = "read"
        write_kind = "read"
        operation_kind = "ignite_cache_read" if method_name != "cache" else "ignite_cache_lookup"
        writes_new_payload = False
        payload_role = "filter_key_or_query"
        payload_expression = args[0] if args else None
    else:
        return None

    cache_name_expression, cache_name_basis = _ignite_cache_name_expression(receiver, args, method_name)
    return {
        "access_kind": access_kind,
        "write_kind": write_kind,
        "mutation_kind": "delete" if access_kind == "mutation" else None,
        "operation_kind": operation_kind,
        "writes_new_payload": writes_new_payload,
        "payload_role": payload_role,
        "payload_expression": _clean_expression(payload_expression),
        "storage_resolution_level": "known_storage_api_or_framework_method",
        "storage_resolution_status": "recognized_ignite_storage_api",
        "storage_kind": "ignite_cache",
        "cache_name_expression": cache_name_expression,
        "cache_name_basis": cache_name_basis,
        "receiver_declared_type": receiver_type or None,
        "table_or_repository": cache_name_expression or receiver,
    }


def _build_storage_facts(methods: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    accesses: list[dict[str, Any]] = []
    seq = 0
    for op, mi in sorted(methods.items()):
        body = mi.get("body") or ""
        # Method-call based repository/JDBC/cache/entity-manager access, using Tree-sitter calls.
        for cm in mi.get("method_calls") or []:
            receiver = cm.get("receiver") or ""
            method_name = cm.get("method") or ""
            is_jooq_storage = method_name in JOOQ_STORAGE_METHODS and _receiver_jooq_like(receiver, mi)
            args = list(cm.get("args") or _split_args(cm.get("args_text") or ""))
            ignite_observation = _ignite_storage_observation(receiver, method_name, args, mi)
            if not is_jooq_storage and ignite_observation is None and not _receiver_storage_like(receiver):
                continue
            sql_literal = None
            for arg in args:
                m = SQL_LITERAL_RE.search(arg)
                if m:
                    sql_literal = m.group("sql")
                    break
            if not sql_literal:
                sql_match = SQL_LITERAL_RE.search(cm.get("args_text") or "")
                if sql_match:
                    sql_literal = sql_match.group("sql")
            cls = ignite_observation or (_jooq_storage_classification(method_name) if is_jooq_storage else _storage_operation_classification(method_name, args, receiver, sql_literal))
            access_kind = cls["access_kind"]
            write_kind = cls["write_kind"]
            if access_kind == "unknown":
                continue
            payload_args = [a for a in args if not SQL_LITERAL_RE.search(a)]
            payload_expression = cls.get("payload_expression") if ignite_observation else (payload_args[0] if payload_args else (args[0] if args else None))
            if is_jooq_storage and method_name in {"insertInto", "update", "deleteFrom"}:
                payload_expression = None
            if receiver.lower().endswith("template") and len(payload_args) > 1:
                payload_expression = payload_args[-1]
            # For mutating update/delete methods the first argument is usually a key/filter,
            # not a saved object. Keep it as payload_expression for evidence, but mark role.
            seq += 1
            line = int(cm.get("line_start") or mi.get("line_start") or 1)
            accesses.append({
                "storage_access_id": f"storage_access_{seq:06d}",
                "kind": "storage_access",
                "operation": op,
                "operation_id": op,
                "class_name": mi["class_name"],
                "method_name": mi["method_name"],
                "access_kind": access_kind,
                "write_kind": write_kind,
                "mutation_kind": cls.get("mutation_kind"),
                "operation_kind": cls.get("operation_kind"),
                "writes_new_payload": bool(cls.get("writes_new_payload")),
                "payload_role": cls.get("payload_role") or "unknown",
                "storage_resolution_level": cls.get("storage_resolution_level") or "unresolved",
                "storage_resolution_status": cls.get("storage_resolution_status") or "unknown",
                "table_or_repository": cls.get("table_or_repository") or _table_from_sql(sql_literal or "") or (_jooq_table_constant(args[0]) if is_jooq_storage and args and method_name in {"insertInto", "update", "deleteFrom"} else None) or receiver,
                "storage_kind": cls.get("storage_kind"),
                "cache_name_expression": cls.get("cache_name_expression"),
                "cache_name_basis": cls.get("cache_name_basis"),
                "receiver_declared_type": cls.get("receiver_declared_type"),
                "jooq_operation": bool(is_jooq_storage),
                "receiver_expression": receiver,
                "storage_method": method_name,
                "payload_type": "unknown",
                "payload_expression": _clean_expression(payload_expression),
                "sql_preview": _clean_expression(sql_literal) if sql_literal else None,
                "file": str(mi["file"]),
                "line_start": line,
                "line_end": line,
                "snippet": str(cm.get("text") or "")[:700],
                "match_strength": 0.68 if cls.get("storage_resolution_level") == "custom_dao_boundary" else (0.82 if access_kind in {"write", "mutation", "read"} else 0.55),
            })
        for observation in _jooq_select_chain_accesses(mi):
            seq += 1
            accesses.append({
                "storage_access_id": f"storage_access_{seq:06d}",
                "kind": "storage_access",
                "operation": op,
                "operation_id": op,
                "class_name": mi["class_name"],
                "method_name": mi["method_name"],
                "storage_kind": "jooq_select",
                "cache_name_expression": None,
                "cache_name_basis": None,
                "receiver_declared_type": None,
                "payload_type": observation.get("result_type") or "unknown",
                "sql_preview": None,
                "file": str(mi["file"]),
                **observation,
            })
    for access in accesses:
        access["candidate_signals"] = _candidate_signals_for_access(access)
        access.update(_maturity_props({
            "persistence_write": _persistence_maturity_for_access(access),
            "source_boundary": "not_applicable",
            "field_mapping": "not_applicable",
            "physical_storage": _physical_storage_maturity_for_access(access),
            "end_to_end_trace": "not_applicable",
        }, notes=["storage access facts expose hard evidence only; candidate_signals are navigation hints, not evidence"]))
    return accesses
def _origin_facts(origins: list[dict[str, Any]], methods: dict[str, dict[str, Any]]) -> list[Fact]:
    facts: list[Fact] = []
    for origin in origins:
        mi = methods.get(origin["operation"])
        evidence = _op_file_evidence(mi, "java_trace_builder_ingress") if mi else []
        facts.append(Fact(
            fact_type="system_ingress",
            name=f"{origin['origin_kind']} at {origin['operation']}",
            properties=origin,
            evidence=evidence,
            match_strength=float(origin.get("match_strength") or 0.7),
        ))
    return facts
def _call_facts(calls: list[dict[str, Any]]) -> list[Fact]:
    facts: list[Fact] = []
    for call in calls:
        ev = EvidenceRef(
            file_path=call.get("file") or "",
            line_start=call.get("line_start"),
            line_end=call.get("line_end"),
            snippet=call.get("snippet"),
            extractor="java_trace_builder_call",
        )
        props = {k: v for k, v in call.items() if k not in {"file", "line_start", "line_end", "snippet"}}
        facts.append(Fact(
            fact_type="method_call",
            name=f"{call['caller_method']} -> {call['callee_method']}",
            properties=props,
            evidence=[ev],
            match_strength=float(call.get("match_strength") or 0.7),
        ))
    return facts
def _storage_facts(accesses: list[dict[str, Any]]) -> list[Fact]:
    facts: list[Fact] = []
    for access in accesses:
        ev = EvidenceRef(
            file_path=access.get("file") or "",
            line_start=access.get("line_start"),
            line_end=access.get("line_end"),
            snippet=access.get("snippet"),
            extractor="java_trace_builder_storage",
        )
        props = {k: v for k, v in access.items() if k not in {"file", "line_start", "line_end", "snippet"}}
        facts.append(Fact(
            fact_type="storage_access",
            name=f"{access['operation']}: {access['access_kind']} {access['table_or_repository']}",
            properties=props,
            evidence=[ev],
            match_strength=float(access.get("match_strength") or 0.7),
        ))
    return facts
def _binding_for_callee_param(call: dict[str, Any], callee_param: str | None) -> dict[str, Any] | None:
    bindings = [b for b in (call.get("argument_bindings") or []) if isinstance(b, dict)]
    bindings.sort(key=lambda b: (
        int(b.get("argument_index")) if str(b.get("argument_index") or "").isdigit() else 10**9,
        str(b.get("callee_parameter") or ""),
        str(b.get("caller_source_parameter") or ""),
        str(b.get("relation") or ""),
        str(b.get("argument_expression") or ""),
    ))
    if callee_param:
        for b in bindings:
            if b.get("callee_parameter") == callee_param:
                return b
    return bindings[0] if bindings else None


__all__ = [name for name in globals() if name.startswith("_")]
