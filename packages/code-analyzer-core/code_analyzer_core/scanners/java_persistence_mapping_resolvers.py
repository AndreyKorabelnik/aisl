from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from code_analyzer_core.models import Fact, EvidenceRef
from code_analyzer_core.utils import normalize_name
from code_analyzer_core.scanners.java_flow_builder import _clean_expression, _synthetic_method_for_body
from code_analyzer_core.scanners.java_syntax import parse_java_files, method_syntax_dict
from code_analyzer_core.scanners.java_trace_common import (
    _getter_binding_from_expression,
    _java_type_details,
    _op_file_evidence,
    _simple_type_name,
    _tree_sitter_builder_bindings,
    _tree_sitter_setter_bindings,
)


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


def _source_scope_for_file(file_value: Any) -> str:
    path = str(file_value or "").replace("\\", "/")
    low = path.lower()
    if "/src/test/" in low or low.endswith("test.java"):
        return "test_code"
    if "/generated/" in low or "/target/generated" in low or "/build/generated" in low:
        return "generated_code"
    if "/src/main/resources/" in low or "/changelog" in low:
        return "config_or_migration"
    if "/src/main/" in low:
        return "production_code"
    return "unknown"



def _mapper_class_candidate(cls: Any) -> bool:
    name = str(getattr(cls, "name", "") or "").lower()
    if any(tok in name for tok in ["mapper", "converter", "assembler", "translator", "transformer"]):
        return True
    annotations = {str(getattr(a, "name", "") or "") for a in getattr(cls, "annotations", ())}
    return bool(annotations & {"Mapper", "org.mapstruct.Mapper"})



def _annotation_string_arg(args: str | None, name: str) -> str | None:
    if not args:
        return None
    m = re.search(rf"\b{re.escape(name)}\s*=\s*\"([^\"]+)\"", args)
    return m.group(1) if m else None



def _mapstruct_mapping_annotations(method: Any) -> list[dict[str, str]]:
    mappings: list[dict[str, str]] = []
    for ann in getattr(method, "annotations", ()) or ():
        ann_name = str(getattr(ann, "name", "") or "").split(".")[-1]
        ann_text = str(getattr(ann, "text", "") or "")
        if ann_name == "Mapping":
            args = getattr(ann, "arguments", None)
            mappings.append({"args": str(args or ""), "text": ann_text or f"@Mapping({args or ''})"})
        elif ann_name == "Mappings":
            # Annotation argument parsing is domain-level MapStruct extraction, not Java syntax parsing.
            for m in re.finditer(r"@(?:org\.mapstruct\.)?Mapping\s*\((?P<args>.*?)\)", ann_text, re.DOTALL):
                mappings.append({"args": m.group("args") or "", "text": m.group(0)})
    return mappings



def _mapper_method_signatures(files: list[Path]) -> dict[str, list[dict[str, Any]]]:
    signatures: dict[str, list[dict[str, Any]]] = defaultdict(list)
    try:
        parsed_files, _warnings = parse_java_files(files)
    except Exception:
        parsed_files = []
    for parsed in parsed_files:
        for cls in parsed.classes:
            if not _mapper_class_candidate(cls):
                continue
            for method in cls.methods:
                params = list(method.params or ())
                if not params:
                    continue
                ret = _simple_type_name(method.return_type)
                if ret in {"", "unknown", "void", "static", "final"}:
                    continue
                first_param = params[0]
                field_mappings: list[dict[str, Any]] = []
                source_container = _simple_type_name(first_param.type)
                for idx, mapping in enumerate(_mapstruct_mapping_annotations(method), start=1):
                    args = mapping.get("args") or ""
                    src_value = _annotation_string_arg(args, "source")
                    tgt_value = _annotation_string_arg(args, "target")
                    if not (src_value and tgt_value):
                        continue
                    field_mappings.append({
                        "mapping_index": idx,
                        "source_field": src_value.split(".")[-1],
                        "source_path": src_value,
                        "source_object": source_container,
                        "target_field": tgt_value.split(".")[-1],
                        "target_path": tgt_value,
                        "target_container": ret,
                        "mapping_kind": "mapstruct_annotation_field_mapping",
                        "mapping_status": "candidate_annotation_mapping",
                        "expression": _clean_expression(mapping.get("text") or f"@Mapping({args})"),
                    })
                signatures[method.name].append({
                    "mapper_class": cls.name,
                    "method": method.name,
                    "source_container": source_container,
                    "source_variable_hint": first_param.name,
                    "target_container": ret,
                    "field_mappings": field_mappings,
                    "source_path": str(method.file),
                    "line_start": method.line_start,
                    "annotation_window": method.annotation_window,
                    "syntax_provider": "tree_sitter",
                })
    return dict(signatures)



def _mapstruct_mapper_signature_facts(mapper_signatures: dict[str, list[dict[str, Any]]]) -> list[Fact]:
    """Expose MapStruct/mapper method signatures as object-level bridges.

    Signature facts do not assert field-level mappings. They let downstream views
    explain that a saved object can be the result of a mapper interface method
    even when generated implementation code is not present in the repository.
    """
    facts: list[Fact] = []
    seq = 0
    for method, sigs in sorted((mapper_signatures or {}).items()):
        for sig in sigs:
            source_container = sig.get("source_container")
            target_container = sig.get("target_container")
            if not source_container or not target_container or target_container == "unknown":
                continue
            seq += 1
            field_mappings = [m for m in (sig.get("field_mappings") or []) if isinstance(m, dict)]
            props = {
                "mapstruct_mapper_signature_id": f"mapstruct_mapper_signature_{seq:06d}",
                "mapper_class": sig.get("mapper_class"),
                "method_name": method,
                "operation": f"{sig.get('mapper_class')}.{method}" if sig.get("mapper_class") else method,
                "source_container": source_container,
                "target_container": target_container,
                "source_variable_hint": sig.get("source_variable_hint"),
                "field_mappings": field_mappings,
                "mapping_kind": "mapstruct_mapper_signature",
                "mapping_status": "candidate_object_bridge_with_field_annotations" if field_mappings else "candidate_object_bridge",
                "lineage_status": "candidate_field_mapping_annotation" if field_mappings else "candidate_object_bridge_no_field_mapping",
                "source_scope": _source_scope_for_file(sig.get("source_path")),
                "evidence_policy": (
                    "MapStruct @Mapping annotations provide candidate field-level mapping; generated implementation/runtime persistence is not confirmed"
                    if field_mappings else
                    "mapper interface signature is object-level candidate evidence only; generated implementation/field-level mapping is not confirmed"
                ),
            }
            facts.append(Fact(
                fact_type="mapstruct_mapper_signature",
                name=f"{source_container} -> {target_container} via {props.get('operation')}",
                properties={k: v for k, v in props.items() if v not in (None, [], {})},
                evidence=[EvidenceRef(file_path=str(sig.get("source_path") or ""), line_start=sig.get("line_start"), extractor="java_mapstruct_mapper_signature")],
            ))
    return facts



def _mapper_signature_for_expression(expr: str, mapper_signatures: dict[str, list[dict[str, Any]]]) -> dict[str, Any] | None:
    expr = _clean_expression(expr)
    syntax = _method_info_syntax({}, f"__x({expr});")
    for ref in syntax.get("method_references") or []:
        method = str(ref.get("method") or "")
        if not method:
            continue
        sigs = mapper_signatures.get(method) or []
        if sigs:
            return {**sigs[0], "source_variable": None, "expression": expr, "mapper_call_kind": "stream_method_ref"}
    calls = [c for c in (syntax.get("method_calls") or []) if c.get("method") not in {"__x", "stream", "map", "flatMap", "collect", "toList"}]
    if not calls:
        return None
    call = calls[0]
    method = str(call.get("method") or "")
    args = list(call.get("args") or [])
    src = _clean_expression(args[0]) if args else None
    sigs = mapper_signatures.get(method) or []
    if not sigs:
        return {"method": method, "source_variable": src, "source_container": "unknown", "target_container": "unknown", "expression": expr, "mapper_call_kind": "method_call"}
    return {**sigs[0], "source_variable": src, "expression": expr, "mapper_call_kind": "method_call"}



def _java_property_name(raw: str | None) -> str | None:
    value = str(raw or "")
    return value[:1].lower() + value[1:] if value else None


def _factory_assignment_expression(mi: dict[str, Any], symbol: str) -> str | None:
    candidates = [
        item for item in (mi.get("syntax_assignments") or [])
        if _clean_expression(item.get("target")) == symbol
    ]
    candidates.sort(key=lambda item: int(item.get("start_byte") or 0))
    return _clean_expression(candidates[-1].get("expression")) if candidates else None


def _factory_source_binding(
    expression: str | None,
    mi: dict[str, Any],
    *,
    visited: set[str] | None = None,
    depth: int = 0,
) -> tuple[str | None, str | None]:
    """Resolve a factory-setter expression to a method parameter field path.

    The resolver is intentionally syntax-bounded.  It follows only local aliases
    and explicit zero-argument Java getter chains.  Wrapper expressions such as
    ``Optional.ofNullable(x.getA()).map(...).orElse(...)`` preserve the getter
    found inside the wrapper; arbitrary helper methods are not interpreted.
    """
    if depth > 6:
        return None, None
    value = _clean_expression(expression)
    if not value:
        return None, None
    visited = visited or set()
    if value in visited:
        return None, None
    visited.add(value)
    params = {str(item.get("name") or "") for item in (mi.get("params") or []) if item.get("name")}

    # Find the first explicit getter chain.  This also works when the chain is
    # nested in Optional/conversion wrappers.
    chain = re.search(
        r"\b(?P<root>[A-Za-z_$][\w$]*)"
        r"(?P<calls>(?:\s*\.\s*(?:get|is)[A-Z][A-Za-z0-9_$]*\s*\(\s*\))+)",
        value,
    )
    if chain:
        root = chain.group("root")
        fields = [
            _java_property_name(name)
            for name in re.findall(r"\.\s*(?:get|is)([A-Z][A-Za-z0-9_$]*)\s*\(", chain.group("calls"))
        ]
        fields = [field for field in fields if field]
        if root in params:
            return root, ".".join(fields) if fields else None
        alias = _factory_assignment_expression(mi, root)
        if alias:
            parent, prefix = _factory_source_binding(alias, mi, visited=visited, depth=depth + 1)
            if parent:
                parts = [part for part in [prefix, ".".join(fields)] if part]
                return parent, ".".join(parts) if parts else None

    direct_obj, direct_field = _getter_binding_from_expression(value, mi)
    if direct_obj and direct_field:
        if direct_obj in params:
            return direct_obj, direct_field
        alias = _factory_assignment_expression(mi, direct_obj)
        if alias:
            parent, prefix = _factory_source_binding(alias, mi, visited=visited, depth=depth + 1)
            if parent:
                return parent, ".".join(part for part in [prefix, direct_field] if part)
        # Preserve local factory evidence even when synthetic/legacy method info
        # does not expose a parameter list.  It remains candidate evidence and
        # cannot be promoted to ingress without an interprocedural binding.
        return direct_obj, direct_field
    return None, None


def _factory_method_mapping_facts(methods: dict[str, dict[str, Any]]) -> list[Fact]:
    """Extract simple factory methods that build an object via setters and return it.

    Example: T x = new T(); x.setA(src.getA()); return x.
    This emits field-mapping evidence for the factory body only. It does not prove
    that the factory result is persisted unless another fact connects the return value
    to a storage operation.
    """
    facts: list[Fact] = []
    seq = 0
    for op, mi in sorted(methods.items()):
        assignments = mi.get("syntax_assignments") or []
        object_creations = mi.get("object_creations") or []
        returns = mi.get("returns") or []
        if not returns:
            continue
        created: dict[str, str] = {}
        for a in assignments:
            if a.get("assignment_kind") != "variable_declaration":
                continue
            target = _clean_expression(a.get("target"))
            if not target:
                continue
            declared = _simple_type_name(a.get("declared_type"))
            expr = _clean_expression(a.get("expression"))
            creation_type = None
            for c in object_creations:
                if int(c.get("start_byte") or -1) >= int(a.get("start_byte") or 0) and int(c.get("end_byte") or -1) <= int(a.get("end_byte") or 0):
                    creation_type = _simple_type_name(c.get("type"))
                    break
            if creation_type or (expr.startswith("new ") and declared):
                created[target] = creation_type or declared
        returned_vars = {_clean_expression(r.get("expression")) for r in returns}
        for target_var, target_type in sorted(created.items()):
            if target_var not in returned_vars:
                continue
            mappings: list[dict[str, Any]] = []
            for b in _tree_sitter_setter_bindings(mi, any_source=True):
                if b.get("target_variable") != target_var:
                    continue
                source_expr = _clean_expression(b.get("source_expression"))
                source_var, source_field = _factory_source_binding(source_expr, mi)
                mappings.append({
                    "target_object_variable": target_var,
                    "target_container": target_type,
                    "target_field": b.get("target_field"),
                    "source_expression": source_expr,
                    "source_object": source_var,
                    "source_payload_parameter": source_var if source_var in {str(p.get("name") or "") for p in (mi.get("params") or [])} else None,
                    "source_field": source_field,
                    "mapping_status": "candidate" if source_field else "target_field_observed_source_unresolved",
                    "mapping_kind": "factory_setter_mapping",
                })
            if not mappings:
                continue
            seq += 1
            props = {
                "factory_method_mapping_id": f"factory_method_mapping_{seq:06d}",
                "operation": op,
                "class_name": mi.get("class_name"),
                "method_name": mi.get("method_name"),
                "target_container": target_type,
                "target_variable": target_var,
                "mapping_status": "candidate",
                "field_mappings": mappings,
                "source_scope": _source_scope_for_file(mi.get("file")),
                "evidence_policy": "factory mapping is local source-level evidence; persistence requires a separate storage/write link",
            }
            facts.append(Fact(
                fact_type="factory_method_mapping",
                name=f"{op}: factory {target_type}",
                properties=props,
                evidence=_op_file_evidence(mi, "java_factory_method_mapping"),
            ))
    return facts



def _builder_field_mapping_facts(
    methods: dict[str, dict[str, Any]],
    *,
    method_variants: list[dict[str, Any]] | None = None,
) -> list[Fact]:
    """Extract local builder/toBuilder field mappings without dropping overloads.

    ``methods`` remains keyed by the legacy ``Type.method`` operation identity and
    therefore contains only one body for overloaded Java methods.  Callers that
    already have signature-level method variants should pass them explicitly.
    The emitted facts keep the operation-level identity for compatibility inside
    the evidence model, while ``operation_signature`` makes each overload
    distinguishable.
    """
    facts: list[Fact] = []
    seq = 0
    variants = list(method_variants or methods.values())
    variants.sort(key=lambda item: (
        str(item.get("operation_signature") or item.get("operation") or ""),
        str(item.get("file") or ""),
        int(item.get("line_start") or 0),
    ))
    for mi in variants:
        op = str(mi.get("operation") or "")
        if not op:
            continue
        bindings = _tree_sitter_builder_bindings(mi, any_source=True)
        if not bindings:
            continue
        to_builder_sources: list[str] = []
        for call in mi.get("method_calls") or []:
            if str(call.get("method") or "") == "toBuilder":
                src = _clean_expression(call.get("receiver"))
                if src and src not in to_builder_sources:
                    to_builder_sources.append(src)
        target_container_candidates: list[str] = []
        for src in to_builder_sources:
            t = _simple_type_name((mi.get("var_types") or {}).get(src) or (mi.get("raw_var_types") or {}).get(src))
            if t and t not in target_container_candidates:
                target_container_candidates.append(t)
        useful = []
        for b in bindings:
            source_expr = _clean_expression(b.get("source_expression"))
            source_var, source_field = _getter_binding_from_expression(source_expr, mi)
            useful.append({
                "target_container": target_container_candidates[0] if len(target_container_candidates) == 1 else None,
                "target_field": b.get("target_field"),
                "source_expression": source_expr,
                "source_object": source_var,
                "source_field": source_field,
                "mapping_status": "candidate" if (source_expr or source_field) else "unresolved",
                "mapping_kind": "builder_field_assignment",
                "expression": b.get("expression"),
            })
        if not useful:
            continue
        seq += 1
        props = {
            "builder_field_mapping_id": f"builder_field_mapping_{seq:06d}",
            "operation": op,
            "operation_signature": mi.get("operation_signature") or op,
            "class_name": mi.get("class_name"),
            "method_name": mi.get("method_name"),
            "builder_origin_kind": "to_builder_clone" if to_builder_sources else "builder_creation_or_fluent_chain",
            "to_builder_source_objects": to_builder_sources,
            "target_container_candidates": target_container_candidates,
            "field_mappings": useful,
            "mapping_status": "candidate",
            "source_scope": _source_scope_for_file(mi.get("file")),
            "evidence_policy": "builder/toBuilder mappings are local candidate field propagation evidence; they do not prove storage persistence",
        }
        facts.append(Fact(
            fact_type="builder_field_mapping",
            name=f"{op}: builder field mapping",
            properties={k: v for k, v in props.items() if v not in (None, [], {})},
            evidence=_op_file_evidence(mi, "java_builder_field_mapping"),
        ))
    return facts



def _stream_collection_lineage_facts(methods: dict[str, dict[str, Any]]) -> list[Fact]:
    """Emit coarse collection provenance facts for stream/lambda-heavy code.

    The fact records observed stream sources and terminal operations, plus mapper
    method refs/calls when visible. It is intentionally navigation/evidence context,
    not confirmed field-level lineage.
    """
    facts: list[Fact] = []
    seq = 0
    for op, mi in sorted(methods.items()):
        calls = mi.get("method_calls") or []
        assignments = mi.get("syntax_assignments") or []
        raw_var_types = mi.get("raw_var_types") or {}
        var_types = mi.get("var_types") or {}
        stream_calls = [c for c in calls if str(c.get("method") or "") == "stream" and _clean_expression(c.get("receiver"))]
        if not stream_calls:
            continue
        terminals = [c for c in calls if str(c.get("method") or "") in {"collect", "toList", "toSet", "toMap", "forEach", "reduce"}]
        method_refs = [
            {"qualifier": r.get("qualifier"), "method": r.get("method"), "text": r.get("text")}
            for r in (mi.get("method_references") or [])
        ]
        lambdas = [
            {"params": list(l.get("params") or []), "body": _clean_expression(l.get("body")), "body_kind": l.get("body_kind")}
            for l in (mi.get("lambdas") or [])[:20]
        ]
        for sc in stream_calls:
            receiver = _clean_expression(sc.get("receiver"))
            source_type_details = _java_type_details(raw_var_types.get(receiver) or var_types.get(receiver))
            mapped_collection_candidates: list[dict[str, Any]] = []
            for a in assignments:
                expr = _clean_expression(a.get("expression"))
                target = _clean_expression(a.get("target"))
                if not expr or not target:
                    continue
                if f"{receiver}.stream" not in expr and f"{receiver}.stream()" not in expr:
                    continue
                mapper_method = None
                for ref in method_refs:
                    text = str(ref.get("text") or "")
                    if text and text in expr:
                        mapper_method = ref.get("method")
                        break
                target_type_details = _java_type_details(raw_var_types.get(target) or var_types.get(target) or a.get("declared_type"))
                batch_write_calls = []
                for call in calls:
                    method_name = str(call.get("method") or "")
                    if method_name not in {"saveAll", "save", "merge", "batchStore", "batchInsert", "batchUpdate", "store", "insert", "update"}:
                        continue
                    args = [_clean_expression(x) for x in (call.get("args") or [])]
                    if target and target in args:
                        batch_write_calls.append({
                            "receiver": _clean_expression(call.get("receiver")),
                            "method": method_name,
                            "argument": target,
                            "line_start": call.get("line_start"),
                        })
                mapped_collection_candidates.append({
                    "target_collection": target,
                    "target_collection_type": target_type_details.get("type") or _simple_type_name(raw_var_types.get(target) or var_types.get(target) or a.get("declared_type")),
                    "target_element_type": target_type_details.get("element_type"),
                    "mapper_method": mapper_method,
                    "expression": expr,
                    "batch_write_calls": batch_write_calls,
                })
            seq += 1
            props = {
                "stream_collection_lineage_id": f"stream_collection_lineage_{seq:06d}",
                "operation": op,
                "class_name": mi.get("class_name"),
                "method_name": mi.get("method_name"),
                "source_collection": receiver,
                "source_collection_type": source_type_details.get("type") or _simple_type_name(raw_var_types.get(receiver) or var_types.get(receiver)) or "unknown",
                "source_element_type": source_type_details.get("element_type"),
                "terminal_operations": sorted({str(t.get("method") or "") for t in terminals if t.get("method")}),
                "method_references": method_refs[:20],
                "lambda_hints": lambdas,
                "mapped_collection_candidates": mapped_collection_candidates[:20],
                "lineage_status": "candidate_collection_provenance",
                "source_scope": _source_scope_for_file(mi.get("file")),
                "evidence_policy": "stream/collection lineage is coarse provenance evidence; field mapping requires setter/builder/factory/storage facts",
            }
            facts.append(Fact(
                fact_type="stream_collection_lineage",
                name=f"{op}: stream({receiver})",
                properties={k: v for k, v in props.items() if v not in (None, [], {})},
                evidence=[EvidenceRef(file_path=str(mi.get("file") or ""), line_start=sc.get("line_start") or mi.get("line_start"), extractor="java_stream_collection_lineage")],
            ))
    return facts
