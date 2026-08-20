from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from code_analyzer_core.models import EvidenceRef
from code_analyzer_core.utils import line_number_for_offset
from code_analyzer_core.scanners.java_syntax import java_type_shape
from code_analyzer_core.scanners.java_flow_builder import (
    _clean_expression,
    _contains_symbol,
    _normalize_java_type,
    _assignment_map,
    _synthetic_method_for_body,
)

SQL_LITERAL_RE = re.compile(r'"(?P<sql>\s*(?:insert|update|merge|delete|select)\b[^"]*)"', re.IGNORECASE | re.DOTALL)
RETURN_RE = re.compile(r"\breturn\s+(?P<expr>[^;]+);", re.DOTALL)
KAFKA_HEADER_RE = re.compile(
    r"(?:headers\s*\(\s*\)|headers)\s*\.\s*add\s*\(\s*[^,]+,\s*(?P<value>[^;)]+)",
    re.DOTALL,
)
CONTROL_WORDS = {"if", "for", "while", "switch", "catch", "return", "new", "throw", "assert", "synchronized"}

WRITE_METHODS: dict[str, str] = {
    "save": "save",
    "saveAll": "save",
    "insert": "insert",
    "update": "update",
    "upsert": "merge",
    "merge": "merge",
    "persist": "persist",
    "flush": "persist",
    "executeUpdate": "update",
    "batchUpdate": "update",
    "put": "cache_write",
}
# Exact names cover framework APIs; prefixes below cover domain DAO APIs such as
# mergeInternalLead(...) and updateIsHidden(...), which are common in corporate
# repositories and otherwise become false negatives in persistence analysis.
DOMAIN_WRITE_METHOD_PREFIXES = ("save", "saveorupdate", "insert", "create", "add", "persist", "merge", "upsert")
DOMAIN_MUTATION_METHOD_PREFIXES = ("update", "actualize", "synchronize", "sync", "refresh", "lock", "unlock", "mark", "revert", "set", "change", "process")
READ_METHOD_PREFIXES = ("find", "query", "get", "load", "fetch", "exists", "count", "select", "read")
DELETE_METHODS = {"delete", "deleteById", "deleteAll", "remove"}
STORAGE_RECEIVER_TOKENS = (
    "repository", "repo", "dao", "jdbc", "template", "entitymanager", "entity_manager", "cache", "store", "locker"
)
CACHE_RECEIVER_TOKENS = ("cache", "redis", "hazelcast", "memcached", "caffeine")
EXTERNAL_RECEIVER_TOKENS = ("resttemplate", "webclient", "http", "api", "connector", "gateway", "feign", "adapter", "proxy", "remote")
SERVICE_RECEIVER_TOKENS = ("service", "handler", "manager", "provider", "facade", "processor", "usecase")
MAPPER_RECEIVER_TOKENS = ("mapper", "converter", "assembler", "translator", "transformer")
PROVENANCE_MAX_DEPTH = 7
NOISE_RECEIVER_TOKENS = ("log", "logger", "metrics", "metric", "timer")
NOISE_METHODS = {"toString", "hashCode", "equals", "getClass", "debug", "info", "warn", "error", "trace"}


def _normalize_mapping_field_name(raw: str | None) -> str | None:
    if not raw:
        return None
    value = str(raw).strip()
    if not value:
        return None
    return value[:1].lower() + value[1:] if value[:1].isupper() else value


def _clean_expression_for_method(value: str | None, method_info: dict[str, Any] | None = None) -> str:
    """Normalize expressions with a tiny per-method cache.

    Deep Java lineage calls expression normalisation heavily while matching
    builder/getter mappings.  The same method-call texts are compared many times
    inside one method, so caching avoids repeated regex whitespace folding.
    """
    if not method_info:
        return _clean_expression(value)
    cache = method_info.setdefault("_clean_expression_cache", {})
    key = "" if value is None else str(value)
    cached = cache.get(key)
    if cached is not None:
        return cached
    normalized = _clean_expression(value)
    cache[key] = normalized
    return normalized


def _getter_binding_index(method_info: dict[str, Any] | None) -> dict[str, tuple[str | None, str | None]]:
    if not method_info:
        return {}
    cached = method_info.get("_getter_binding_index")
    if isinstance(cached, dict):
        return cached
    index: dict[str, tuple[str | None, str | None]] = {}
    for call in method_info.get("method_calls") or []:
        text = _clean_expression_for_method(call.get("text"), method_info)
        if not text or text in index:
            continue
        receiver = _clean_expression_for_method(call.get("receiver"), method_info)
        method = str(call.get("method") or "")
        if receiver and not (call.get("args") or ()):
            if method.startswith("get") and len(method) > 3:
                index[text] = (receiver, _normalize_mapping_field_name(method[3:]))
            elif method.startswith("is") and len(method) > 2:
                index[text] = (receiver, _normalize_mapping_field_name(method[2:]))
    for access in method_info.get("field_accesses") or []:
        text = _clean_expression_for_method(access.get("text"), method_info)
        if not text or text in index:
            continue
        receiver = _clean_expression_for_method(access.get("receiver"), method_info)
        field = _clean_expression_for_method(access.get("field"), method_info)
        if receiver and field:
            index[text] = (receiver, _normalize_mapping_field_name(field))
    method_info["_getter_binding_index"] = index
    return index


def _getter_binding_from_expression(expr: str | None, method_info: dict[str, Any] | None = None) -> tuple[str | None, str | None]:
    """Return (source variable, source field) for a Tree-sitter expression.

    The preferred path uses a per-method Tree-sitter lookup built once from
    method_calls/field_accesses.  A small string fallback is retained for
    synthetic expressions already produced by Tree-sitter helpers, not for
    scanning Java method bodies.
    """
    value = _clean_expression_for_method(expr, method_info)
    if not value:
        return None, None
    if method_info:
        indexed = _getter_binding_index(method_info).get(value)
        if indexed:
            return indexed
    if value.endswith(")") and "." in value:
        receiver, tail = value.rsplit(".", 1)
        method = tail[:-2] if tail.endswith("()") else tail
        if receiver and method.startswith("get") and len(method) > 3:
            return receiver, _normalize_mapping_field_name(method[3:])
        if receiver and method.startswith("is") and len(method) > 2:
            return receiver, _normalize_mapping_field_name(method[2:])
    if "." in value and "(" not in value and ")" not in value:
        receiver, field = value.rsplit(".", 1)
        if receiver and field:
            return receiver, _normalize_mapping_field_name(field)
    return None, None


_BUILDER_MAPPING_EXCLUDED_METHODS = {
    "builder", "build", "map", "flatMap", "filter", "collect", "stream", "of", "ok",
    "find", "findById", "findAll", "get", "load", "query", "select", "fetch",
    "save", "saveAll", "insert", "update", "delete", "deleteById", "send",
    "postForObject", "exchange", "bodyValue", "add", "put", "forEach", "peek",
}


def _tree_sitter_setter_bindings(method_info: dict[str, Any] | None, *, source_param: str | None = None, any_source: bool = False) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not method_info:
        return out
    for call in method_info.get("method_calls") or []:
        method = str(call.get("method") or "")
        receiver = _clean_expression(call.get("receiver"))
        args = list(call.get("args") or [])
        if not receiver or not method.startswith("set") or len(method) <= 3 or not args:
            continue
        source_var, source_field = _getter_binding_from_expression(args[0], method_info)
        if not any_source:
            if not source_var or not source_field:
                continue
            if source_param and source_var != source_param:
                continue
            entry = {
                "kind": "setter_derived",
                "target_variable": receiver,
                "target_field": _normalize_mapping_field_name(method[3:]),
                "source_parameter": source_var,
                "source_field": source_field,
                "expression": _clean_expression(call.get("text")),
                "syntax_provider": "tree_sitter",
            }
        else:
            entry = {
                "kind": "setter_mapping",
                "target_variable": receiver,
                "target_field": _normalize_mapping_field_name(method[3:]),
                "source_expression": _clean_expression(args[0]),
                "expression": _clean_expression(call.get("text")),
                "syntax_provider": "tree_sitter",
            }
        if entry not in out:
            out.append(entry)
    return out


def _tree_sitter_builder_bindings(method_info: dict[str, Any] | None, *, source_param: str | None = None, any_source: bool = False) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not method_info:
        return out
    for call in method_info.get("method_calls") or []:
        field = str(call.get("method") or "")
        args = list(call.get("args") or [])
        receiver = _clean_expression(call.get("receiver"))
        if not field or not args or not receiver:
            continue
        if field in _BUILDER_MAPPING_EXCLUDED_METHODS or field.startswith(READ_METHOD_PREFIXES):
            continue
        # Fluent builder mapping methods are usually lower camel-case. Excluding
        # setX here avoids double-counting setter calls already handled above.
        if not field[:1].islower() or field.startswith("set"):
            continue
        source_var, source_field = _getter_binding_from_expression(args[0], method_info)
        if not any_source:
            if not source_var or not source_field:
                continue
            if source_param and source_var != source_param:
                continue
            entry = {
                "kind": "builder_derived",
                "target_variable": None,
                "target_field": _normalize_mapping_field_name(field),
                "source_parameter": source_var,
                "source_field": source_field,
                "expression": _clean_expression(call.get("text")),
                "syntax_provider": "tree_sitter",
            }
        else:
            entry = {
                "kind": "builder_mapping",
                "target_variable": None,
                "target_field": _normalize_mapping_field_name(field),
                "source_expression": _clean_expression(args[0]),
                "expression": _clean_expression(call.get("text")),
                "syntax_provider": "tree_sitter",
            }
        if entry not in out:
            out.append(entry)
    return out



def _annotation_window(text: str, method_start: int) -> str:
    start = max(0, method_start - 900)
    window = text[start:method_start]
    # Keep the direct annotation block only. This avoids picking up annotations from
    # the previous method while still allowing comments/blank lines between annotations.
    last_boundary = max(window.rfind("}"), window.rfind(";"))
    if last_boundary >= 0:
        window = window[last_boundary + 1:]
    return window


PLACEHOLDER_PAYLOAD_TYPES = {"unknown", "object", "message", "messages", "string", "void", "null", "none"}


def _is_placeholder_java_type(value: str | None) -> bool:
    simple = _simple_type_name(value) if value else ""
    return not simple or simple.lower() in PLACEHOLDER_PAYLOAD_TYPES


def _class_literal_type(expr: str | None) -> str | None:
    value = _clean_expression(expr)
    m = re.search(r"(?:^|[^A-Za-z0-9_])([A-Za-z_][A-Za-z0-9_.$]*)\s*\.\s*class(?:\b|$)", value or "")
    if not m:
        return None
    return _simple_type_name(m.group(1))


def _payload_type_from_class_literal_args(args: list[str] | tuple[str, ...] | None) -> str | None:
    for arg in args or []:
        typ = _class_literal_type(str(arg))
        if typ and not _is_placeholder_java_type(typ):
            return typ
    return None


def _kafka_payload_type_from_method_info(method_info: dict[str, Any] | None) -> dict[str, Any]:
    """Infer Kafka payload type from deserialize(..., Payload.class, ...) wrappers.

    Many Spring Kafka consumers receive List<Message<String>> and only expose the
    domain payload type inside a deserialization call. This helper returns
    deterministic technical evidence; it does not infer source ownership.
    """
    if not method_info:
        return {"payload_type": None, "status": "not_found", "basis": []}
    hits: list[dict[str, Any]] = []
    for call in method_info.get("method_calls") or []:
        method = str(call.get("method") or "")
        if "deserialize" not in method.lower():
            continue
        payload_type = _payload_type_from_class_literal_args(list(call.get("args") or []))
        if not payload_type:
            continue
        hits.append({
            "payload_type": payload_type,
            "method": method,
            "expression": _clean_expression(call.get("text")),
            "line_start": call.get("line_start"),
        })
    unique = sorted({h["payload_type"] for h in hits if h.get("payload_type")})
    if len(unique) == 1:
        return {
            "payload_type": unique[0],
            "status": "resolved_from_deserialize_class_literal",
            "basis": hits[:5],
        }
    if len(unique) > 1:
        return {
            "payload_type": None,
            "status": "ambiguous_multiple_deserialize_payload_types",
            "basis": hits[:8],
        }
    return {"payload_type": None, "status": "not_found", "basis": []}

def _extract_annotation_value(args: str | None) -> str | None:
    if not args:
        return None
    for pat in [r'topics\s*=\s*"([^"]+)"', r'topic\s*=\s*"([^"]+)"', r'value\s*=\s*"([^"]+)"', r'path\s*=\s*"([^"]+)"', r'"([^"]+)"']:
        m = re.search(pat, args)
        if m:
            return m.group(1)
    return _clean_expression(args)[:180] or None
def _split_args(args: str) -> list[str]:
    out: list[str] = []
    cur: list[str] = []
    depth = 0
    in_string = False
    quote = ""
    esc = False
    for ch in args or "":
        if in_string:
            cur.append(ch)
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == quote:
                in_string = False
            continue
        if ch in {"'", '"'}:
            in_string = True
            quote = ch
            cur.append(ch)
            continue
        if ch in "([{<":
            depth += 1
            cur.append(ch)
            continue
        if ch in ")]}>":
            depth = max(0, depth - 1)
            cur.append(ch)
            continue
        if ch == "," and depth == 0:
            val = _clean_expression("".join(cur))
            if val:
                out.append(val)
            cur = []
            continue
        cur.append(ch)
    val = _clean_expression("".join(cur))
    if val:
        out.append(val)
    return out
def _source_parameter_from_expression(expr: str, caller_params: set[str], assignments: dict[str, dict[str, Any]]) -> tuple[str | None, str, str | None]:
    expr = _clean_expression(expr)
    if expr in caller_params:
        return expr, "same_object", None
    for param in sorted(caller_params):
        if re.search(rf"\b{re.escape(param)}\.(?:get|is)?[A-Z]", expr) or re.search(rf"\b{re.escape(param)}\.[A-Za-z_][A-Za-z0-9_]*", expr):
            return param, "field_extracted", None
        if _contains_symbol(expr, param):
            relation = "derived_object" if ("new " in expr or "." in expr or "(" in expr) else "same_object"
            return param, relation, None
    for var, info in assignments.items():
        if expr == var or _contains_symbol(expr, var):
            source_param = str(info.get("source_parameter") or "") or None
            if not source_param:
                continue
            if info.get("source_field"):
                return source_param, "field_extracted", var
            src_expr = _clean_expression(info.get("expression"))
            relation = str(info.get("relation_hint") or ("same_object" if src_expr == source_param else "derived_object"))
            if info.get("source_field"):
                relation = "field_extracted"
            if info.get("serialization_kind"):
                relation = "derived_object"
            return source_param, relation, var
    return None, "unknown", None
def _method_snippet(text: str, start: int, end: int, max_chars: int = 1800) -> str:
    snippet = text[start:end + 1]
    if len(snippet) > max_chars:
        return snippet[:max_chars] + "\n... method truncated ..."
    return snippet
def _receiver_storage_like(receiver: str) -> bool:
    low = (receiver or "").lower()
    if any(tok in low for tok in NOISE_RECEIVER_TOKENS):
        return False
    return any(tok in low for tok in STORAGE_RECEIVER_TOKENS)
def _write_kind_from_sql(sql: str) -> tuple[str, str]:
    first = (sql or "").strip().split(None, 1)[0].lower() if (sql or "").strip() else ""
    if first == "insert":
        return "write", "insert"
    if first == "update":
        return "write", "update"
    if first == "merge":
        return "write", "merge"
    if first == "delete":
        return "mutation", "delete"
    if first == "select":
        return "read", "select"
    return "unknown", "unknown"
def _table_from_sql(sql: str) -> str | None:
    patterns = [
        r"insert\s+into\s+([A-Za-z0-9_.]+)",
        r"update\s+([A-Za-z0-9_.]+)",
        r"merge\s+into\s+([A-Za-z0-9_.]+)",
        r"delete\s+from\s+([A-Za-z0-9_.]+)",
        r"from\s+([A-Za-z0-9_.]+)",
    ]
    for pat in patterns:
        m = re.search(pat, sql or "", re.IGNORECASE)
        if m:
            return m.group(1)
    return None
def _strip_java_modifiers(type_name: str | None) -> str:
    value = _clean_expression(type_name)
    while True:
        new = re.sub(r"^(?:public|private|protected|static|final|transient|volatile)\s+", "", value).strip()
        if new == value:
            return new
        value = new
def _simple_type_name(type_name: str | None) -> str:
    return _normalize_java_type(_strip_java_modifiers(type_name))
def _java_type_details(type_name: str | None) -> dict[str, str | None]:
    shape = java_type_shape(_strip_java_modifiers(type_name))
    return {
        "raw_type": shape.get("raw_type"),
        "type": shape.get("simple_type"),
        "container_kind": shape.get("container_kind"),
        "element_type": shape.get("element_type"),
        "map_key_type": shape.get("map_key_type"),
        "map_value_type": shape.get("map_value_type"),
    }

def _infer_var_raw_types(body: str, params: list[dict[str, str]]) -> dict[str, str]:
    types = {p.get("name", ""): _strip_java_modifiers(p.get("type")) for p in params if p.get("name")}
    method = _synthetic_method_for_body(body)
    if method:
        for assignment in method.assignments:
            if assignment.assignment_kind != "variable_declaration":
                continue
            raw = _strip_java_modifiers(assignment.declared_type)
            if raw == "var":
                creation = next((c for c in method.object_creations if c.start_byte >= assignment.start_byte and c.end_byte <= assignment.end_byte), None)
                raw = creation.type if creation else "unknown"
            if assignment.target and raw and raw != "unknown":
                types[assignment.target] = raw
    return types

def _infer_var_types(body: str, params: list[dict[str, str]]) -> dict[str, str]:
    return {name: _simple_type_name(raw) for name, raw in _infer_var_raw_types(body, params).items() if name}

def _split_type_list(value: str | None) -> list[str]:
    if not value:
        return []
    out: list[str] = []
    for part in re.split(r",", value):
        cleaned = _simple_type_name(part.strip())
        if cleaned and cleaned != "unknown":
            out.append(cleaned)
    return out
def _enhanced_assignment_map(body: str, params: set[str]) -> dict[str, dict[str, Any]]:
    # Compatibility wrapper for callers that only have raw body text. New Java
    # syntax-aware callers should use _enhanced_assignment_map_from_method_info.
    return _assignment_map(body, params)


def _enhanced_assignment_map_from_method_info(method_info: dict[str, Any] | None, params: set[str]) -> dict[str, dict[str, Any]]:
    assignments: dict[str, dict[str, Any]] = {}
    for binding in _tree_sitter_setter_bindings(method_info):
        target = binding.get("target_variable")
        source = binding.get("source_parameter")
        if not target or source not in params:
            continue
        assignments[str(target)] = {
            "source_parameter": source,
            "expression": _clean_expression(binding.get("expression")),
            "serialization_kind": None,
            "source_field": binding.get("source_field"),
            "derivation_kind": "setter_field_binding",
            "syntax_provider": "tree_sitter",
        }
    return assignments
def _binding_strength(relation: str, resolution_kind: str) -> float:
    base = 0.86 if relation == "same_object" else 0.74 if relation in {"derived_object", "field_extracted"} else 0.45
    if resolution_kind in {"spring_interface_dispatch", "spring_field_injection", "name_type_heuristic"}:
        base -= 0.08
    if resolution_kind == "unresolved":
        base = min(base, 0.35)
    return round(max(0.1, min(0.95, base)), 2)
def _relation_from_bindings(bindings: list[dict[str, Any]]) -> str:
    relations = [str(b.get("relation") or "unknown") for b in bindings if b.get("relation")]
    if not relations:
        return "unknown"
    if all(r == "same_object" for r in relations):
        return "same_object"
    if any(r == "unknown" for r in relations):
        return "unknown"
    if any(r == "field_extracted" for r in relations):
        return "field_extracted"
    return "derived_object"
def _relation_quality(relations: list[str]) -> str:
    if not relations:
        return "unresolved"
    if all(r == "same_object" for r in relations):
        return "confirmed"
    return "unresolved"
def _trace_status(origin: dict[str, Any] | None, relations: list[str], *, unknown_kind: str) -> str:
    if not origin:
        return unknown_kind
    if not origin.get("is_payload_origin", True):
        return "unresolved"
    if all(r == "same_object" for r in relations):
        return "confirmed"
    return "unresolved"
def _op_file_evidence(mi: dict[str, Any], extractor: str = "java_trace_builder") -> list[EvidenceRef]:
    return [EvidenceRef(
        file_path=str(mi["file"]),
        line_start=mi.get("line_start"),
        line_end=mi.get("line_end"),
        snippet=mi.get("snippet"),
        extractor=extractor,
    )]


__all__ = [name for name in globals() if name.startswith("_") or name.isupper()]
