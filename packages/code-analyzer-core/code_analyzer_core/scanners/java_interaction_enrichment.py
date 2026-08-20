from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from code_analyzer_core.models import Direction, EvidenceRef, Fact, InterfaceInfo, InterfaceKind, SchemaInfo
from code_analyzer_core.scanners.java_syntax import (
    JAVA_SYNTAX_EXTRACTOR,
    JavaAnnotation,
    JavaClass,
    JavaMethod,
    JavaSyntaxFile,
    parse_java_files,
)

_HTTP_METHOD_ANNOTATIONS = {
    "Get": "GET", "Post": "POST", "Put": "PUT", "Delete": "DELETE", "Patch": "PATCH",
    "GET": "GET", "POST": "POST", "PUT": "PUT", "DELETE": "DELETE", "PATCH": "PATCH",
}
_SPRING_MAPPING_ANNOTATIONS = {
    "GetMapping": "GET", "PostMapping": "POST", "PutMapping": "PUT",
    "DeleteMapping": "DELETE", "PatchMapping": "PATCH", "RequestMapping": None,
}
_RAW_HTTP_REQUEST_TYPES = {"AggregatedHttpRequest", "HttpRequest", "Request", "ServletRequest", "ServerRequest"}
_SIMPLE_TYPES = {
    "String", "Boolean", "boolean", "Integer", "int", "Long", "long", "Double", "double",
    "Float", "float", "Short", "short", "Byte", "byte", "Character", "char", "void", "unknown", "var",
}


def _ann(annotations: Iterable[JavaAnnotation], names: set[str]) -> JavaAnnotation | None:
    return next((a for a in annotations if a.name in names), None)


def _strip_string(value: str | None) -> str | None:
    if value is None:
        return None
    raw = str(value).strip()
    if not re.fullmatch(r'"(?:[^"\\]|\\.)*"', raw, re.DOTALL):
        return None
    try:
        return json.loads(raw)
    except Exception:
        return raw[1:-1]


def _clean_type(value: str | None) -> str:
    text = re.sub(r"\s+", " ", str(value or "unknown").strip())
    text = re.sub(r"^(?:public|private|protected|static|final|abstract)\s+", "", text)
    wrappers = ("ResponseEntity", "HttpEntity", "Optional", "CompletableFuture")
    changed = True
    while changed:
        changed = False
        for wrapper in wrappers:
            m = re.fullmatch(rf"{wrapper}\s*<\s*(.+)\s*>", text)
            if m:
                text = m.group(1).strip()
                changed = True
    return text.split(".")[-1] if "." in text and "<" not in text else text


def _stable_unique(values: Iterable[Any]) -> list[Any]:
    out: list[Any] = []
    seen: set[str] = set()
    for value in values:
        marker = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
        if marker in seen:
            continue
        seen.add(marker)
        out.append(value)
    return out


def _source_set(path: Path) -> str:
    normalized = str(path).replace("\\", "/")
    return "test" if "/src/test/" in normalized else "main"


def _join_paths(base: str | None, method: str | None) -> str | None:
    if not base and not method:
        return None
    if not base:
        return method
    if not method:
        return base
    return "/" + "/".join(x.strip("/") for x in (str(base), str(method)) if x.strip("/"))


def _value_property(annotation: JavaAnnotation | None) -> dict[str, Any] | None:
    if annotation is None:
        return None
    raw = annotation.string_arg() or annotation.string_arg("value")
    if not raw:
        return None
    m = re.fullmatch(r"\$\{([^}:]+)(?::([^}]*))?\}", raw.strip())
    if not m:
        return {"raw_expression": raw, "property_key": None, "default_value": None}
    return {"raw_expression": raw, "property_key": m.group(1), "default_value": m.group(2)}


def _config_index(config_facts: list[Fact]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for fact in config_facts:
        if fact.fact_type != "config_property":
            continue
        value = (fact.properties or {}).get("value")
        entry = {
            "value": value,
            "evidence": [e.model_dump(mode="json") for e in fact.evidence],
        }
        marker = json.dumps(entry, ensure_ascii=False, sort_keys=True, default=str)
        if all(json.dumps(x, ensure_ascii=False, sort_keys=True, default=str) != marker for x in out[fact.name]):
            out[fact.name].append(entry)
    return dict(out)


def _constant_index(parsed_files: list[JavaSyntaxFile]) -> dict[str, dict[str, Any]]:
    """Resolve source-observed Java String constants, including concatenations.

    Qualified symbols are always published. A simple-name alias is published only
    when it is unambiguous, with production sources preferred over tests. Constant
    expressions are resolved by a small fixed-point pass; no code is executed.
    """
    resolved: dict[str, dict[str, Any]] = {}
    pending: list[dict[str, Any]] = []
    simple_candidates: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for parsed in parsed_files:
        for cls in parsed.classes:
            for field in cls.fields:
                m = re.search(r"=\s*(.+?)\s*;\s*$", field.raw, re.DOTALL)
                if not m:
                    continue
                expression = m.group(1).strip()
                item = {
                    "expression": expression,
                    "symbol": f"{cls.name}.{field.name}",
                    "simple_name": field.name,
                    "class_name": cls.name,
                    "source_set": _source_set(parsed.file),
                    "evidence": EvidenceRef(
                        file_path=str(parsed.file), line_start=field.line_start, line_end=field.line_end,
                        snippet=field.raw[:600], extractor=JAVA_SYNTAX_EXTRACTOR,
                    ),
                }
                pending.append(item)

    def resolve_const(expression: str, class_name: str) -> tuple[str | None, str | None]:
        literal = _strip_string(expression)
        if literal is not None:
            return literal, "class_string_constant_initializer"
        parts = _split_concat(expression)
        if len(parts) <= 1:
            candidates = [expression, f"{class_name}.{expression}"]
            simple = expression.split(".")[-1]
            candidates.append(simple)
            for candidate in candidates:
                found = resolved.get(candidate)
                if found is not None:
                    return str(found["value"]), "resolved_constant_reference"
            return None, None
        values: list[str] = []
        for part in parts:
            value, _ = resolve_const(part, class_name)
            if value is None:
                return None, None
            values.append(value)
        return "".join(values), "resolved_constant_concatenation"

    remaining = list(pending)
    for _ in range(max(2, len(remaining) + 1)):
        progressed = False
        next_remaining: list[dict[str, Any]] = []
        for item in remaining:
            value, basis = resolve_const(str(item["expression"]), str(item["class_name"]))
            if value is None:
                next_remaining.append(item)
                continue
            record = {
                "value": value,
                "symbol": item["symbol"],
                "basis": basis,
                "expression": item["expression"],
                "source_set": item["source_set"],
                "evidence": item["evidence"],
            }
            resolved[item["symbol"]] = record
            simple_candidates[item["simple_name"]].append(record)
            progressed = True
        remaining = next_remaining
        if not progressed:
            break

    for simple, candidates in simple_candidates.items():
        production = [x for x in candidates if x.get("source_set") == "main"]
        selected = production if production else candidates
        unique_values = {str(x.get("value")) for x in selected}
        if len(selected) == 1 or len(unique_values) == 1:
            resolved[simple] = selected[0]
    return resolved


def _split_concat(expression: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    quoted = False
    escaped = False
    depth = 0
    for ch in expression:
        if escaped:
            current.append(ch)
            escaped = False
            continue
        if ch == "\\" and quoted:
            current.append(ch)
            escaped = True
            continue
        if ch == '"':
            quoted = not quoted
            current.append(ch)
            continue
        if not quoted:
            if ch in "([{":
                depth += 1
            elif ch in ")]}" and depth:
                depth -= 1
            elif ch == "+" and depth == 0:
                parts.append("".join(current).strip())
                current = []
                continue
        current.append(ch)
    if current:
        parts.append("".join(current).strip())
    return parts


def _resolve_expression(
    expression: str | None,
    *,
    constants: dict[str, dict[str, Any]],
    value_bindings: dict[str, dict[str, Any]],
    config_values: dict[str, list[dict[str, Any]]],
    context_class: str | None = None,
) -> dict[str, Any]:
    raw = str(expression or "").strip()
    if not raw:
        return {"expression": raw, "values": [], "basis": "unresolved"}
    literal = _strip_string(raw)
    if literal is not None:
        return {"expression": raw, "values": [literal], "basis": "string_literal"}
    simple = raw.split(".")[-1]
    # A local @Value binding is stronger than a same-named constant elsewhere
    # in the repository (especially test fixtures).
    if raw in value_bindings or simple in value_bindings:
        binding = value_bindings.get(raw) or value_bindings.get(simple) or {}
        key = binding.get("property_key")
        observed = config_values.get(str(key), []) if key else []
        values = _stable_unique(x.get("value") for x in observed if x.get("value") is not None)
        if not values and binding.get("default_value") is not None:
            values = [binding.get("default_value")]
        return {
            "expression": raw,
            "values": values,
            "basis": "spring_value_property_binding" if key else "spring_value_expression",
            "property_key": key,
            "default_value": binding.get("default_value"),
            "config_evidence": [e for x in observed for e in (x.get("evidence") or [])],
        }
    constant_keys = [raw]
    if context_class and "." not in raw:
        constant_keys.insert(0, f"{context_class}.{raw}")
    if simple not in constant_keys:
        constant_keys.append(simple)
    for key_candidate in constant_keys:
        if key_candidate in constants:
            item = constants[key_candidate]
            return {"expression": raw, "values": [item["value"]], "basis": item["basis"], "symbol": item["symbol"]}
    concat = _split_concat(raw)
    if len(concat) > 1:
        resolved_parts = [
            _resolve_expression(x, constants=constants, value_bindings=value_bindings, config_values=config_values, context_class=context_class)
            for x in concat
        ]
        if all(x.get("values") for x in resolved_parts):
            values = [""]
            for item in resolved_parts:
                values = [str(prefix) + str(suffix) for prefix in values for suffix in item.get("values") or []]
            return {"expression": raw, "values": values[:64], "basis": "resolved_string_concatenation", "parts": resolved_parts}
    return {"expression": raw, "values": [], "basis": "unresolved"}


def _class_value_bindings(parsed: JavaSyntaxFile, cls: JavaClass) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for field in cls.fields:
        info = _value_property(_ann(field.annotations, {"Value"}))
        if info:
            out[field.name] = {**info, "target": field.name, "target_kind": "field", "file": str(parsed.file), "line": field.line_start}
    for method in cls.methods:
        if method.name != cls.name:
            continue
        param_info: dict[str, dict[str, Any]] = {}
        for param in method.params:
            info = _value_property(_ann(param.annotations, {"Value"}))
            if info:
                param_info[param.name] = info
        for assignment in method.assignments:
            target = assignment.target.removeprefix("this.")
            source = assignment.expression.strip()
            if source in param_info:
                out[target] = {**param_info[source], "target": target, "target_kind": "constructor_assigned_field", "file": str(parsed.file), "line": assignment.line_start}
    return out


def _class_qualifier_bindings(cls: JavaClass) -> dict[str, str]:
    out: dict[str, str] = {}
    for method in cls.methods:
        if method.name != cls.name:
            continue
        qualifier_by_param: dict[str, str] = {}
        for param in method.params:
            ann = _ann(param.annotations, {"Qualifier"})
            if ann:
                value = ann.string_arg() or ann.string_arg("value")
                if value:
                    qualifier_by_param[param.name] = value
        for assignment in method.assignments:
            target = assignment.target.removeprefix("this.")
            source = assignment.expression.strip()
            if source in qualifier_by_param:
                out[target] = qualifier_by_param[source]
    return out


def _local_type_map(method: JavaMethod, cls: JavaClass) -> dict[str, str]:
    out = {p.name: _clean_type(p.type) for p in method.params}
    out.update({f.name: _clean_type(f.type) for f in cls.fields})
    for assignment in method.assignments:
        if assignment.declared_type:
            out[assignment.target.removeprefix("this.")] = _clean_type(assignment.declared_type)
    return out


def _request_type_from_http_entity(method: JavaMethod, request_expr: str | None, type_map: dict[str, str]) -> str:
    if not request_expr:
        return "unknown"
    simple = str(request_expr).strip()
    direct = type_map.get(simple)
    if direct and not direct.startswith("HttpEntity"):
        return direct
    for assignment in method.assignments:
        if assignment.target == simple:
            expr = assignment.expression
            m = re.search(r"new\s+HttpEntity(?:<[^>]+>)?\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)", expr)
            if m:
                return type_map.get(m.group(1), "unknown")
            for param in method.params:
                if re.search(rf"\b{re.escape(param.name)}\b", expr):
                    return _clean_type(param.type)
    return direct or "unknown"


def _http_response_type(call_method: str, call_args: tuple[str, ...], method: JavaMethod) -> str:
    """Read the declared response contract from the framework call signature."""
    response_index = 3 if call_method == "exchange" else 2 if call_method in {"postForObject", "getForObject"} else None
    if response_index is None or response_index >= len(call_args):
        return "unknown"
    value = call_args[response_index].strip()
    m = re.match(r"([A-Za-z0-9_.$]+)\s*\.\s*class$", value)
    if m:
        return _clean_type(m.group(1))
    local_types = {
        assignment.target.removeprefix("this."): _clean_type(assignment.declared_type)
        for assignment in method.assignments
        if assignment.declared_type
    }
    declared = local_types.get(value)
    if declared and declared != "unknown":
        generic = re.search(r"<\s*([A-Za-z0-9_.$]+)\s*>", declared)
        return _clean_type(generic.group(1) if generic else declared)
    # Anonymous ParameterizedTypeReference<Foo>() {} and similar expressions.
    generic = re.search(r"(?:ParameterizedTypeReference|TypeReference)\s*<\s*([A-Za-z0-9_.$]+)\s*>", value)
    if generic:
        return _clean_type(generic.group(1))
    return "unknown"


def _build_rest_template_bean_bindings(
    parsed_files: list[JavaSyntaxFile],
    *,
    value_bindings_by_class: dict[str, dict[str, dict[str, Any]]],
    constants: dict[str, dict[str, Any]],
    config_values: dict[str, list[dict[str, Any]]],
) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for parsed in parsed_files:
        for cls in parsed.classes:
            class_values = value_bindings_by_class.get(cls.name, {})
            for method in cls.methods:
                if _ann(method.annotations, {"Bean"}) is None or _clean_type(method.return_type) != "RestTemplate":
                    continue
                candidates: list[str] = []
                for ret in method.returns:
                    candidates.extend(_split_concat(ret.expression))
                    candidates.extend(re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", ret.expression))
                for call in method.calls:
                    if call.method in {"rootUri", "baseUrl", "clientRestTemplate", "prepareRestTemplateBuilder"}:
                        candidates.extend(call.args)
                resolved: list[dict[str, Any]] = []
                for candidate in candidates:
                    item = _resolve_expression(candidate, constants=constants, value_bindings=class_values, config_values=config_values, context_class=cls.name)
                    if item.get("property_key") or item.get("values"):
                        resolved.append(item)
                # URL properties are preferred over timeouts and integer connection settings.
                resolved.sort(key=lambda x: (0 if "url" in str(x.get("property_key") or "").lower() else 1, str(x.get("property_key") or "")))
                if resolved:
                    best = resolved[0]
                    out[method.name].append({
                        "bean_name": method.name,
                        "base_url_property_key": best.get("property_key"),
                        "base_url_values": best.get("values") or [],
                        "base_url_expression": best.get("expression"),
                        "binding_basis": "spring_bean_return_call_argument_and_value_binding",
                        "source_file": str(parsed.file),
                        "line_start": method.line_start,
                    })
    return dict(out)


def _helper_templates(parsed_files: list[JavaSyntaxFile]) -> list[dict[str, Any]]:
    templates: list[dict[str, Any]] = []
    for parsed in parsed_files:
        for cls in parsed.classes:
            for method in cls.methods:
                param_index = {p.name: idx for idx, p in enumerate(method.params)}
                param_types = {p.name: _clean_type(p.type) for p in method.params}
                for call in method.calls:
                    receiver = (call.receiver or "").strip()
                    if param_types.get(receiver) != "RestTemplate" or call.method not in {"exchange", "postForObject", "getForObject"}:
                        continue
                    if not call.args:
                        continue
                    path_expr = call.args[0].strip()
                    path_idx = param_index.get(path_expr)
                    receiver_idx = param_index.get(receiver)
                    if path_idx is None or receiver_idx is None:
                        continue
                    http_method = "POST" if call.method == "postForObject" else "GET" if call.method == "getForObject" else None
                    request_expr = call.args[1] if call.method == "postForObject" and len(call.args) > 1 else call.args[2] if call.method == "exchange" and len(call.args) > 2 else None
                    if call.method == "exchange" and len(call.args) > 1:
                        mm = re.search(r"(?:HttpMethod\.)?([A-Z]+)", call.args[1])
                        http_method = mm.group(1) if mm else None
                    request_param_idx = None
                    if request_expr:
                        if request_expr in param_index:
                            request_param_idx = param_index[request_expr]
                        else:
                            for assignment in method.assignments:
                                if assignment.target == request_expr:
                                    for pname, pidx in param_index.items():
                                        if re.search(rf"\b{re.escape(pname)}\b", assignment.expression):
                                            request_param_idx = pidx
                                            break
                    templates.append({
                        "helper_operation": method.operation,
                        "helper_method": method.name,
                        "parameter_count": len(method.params),
                        "receiver_param_index": receiver_idx,
                        "path_param_index": path_idx,
                        "request_param_index": request_param_idx,
                        "http_method": http_method,
                        "response_payload_type": _clean_type(method.return_type),
                        "call_pattern": call.method,
                        "source_file": str(parsed.file),
                        "line_start": call.line_start,
                        "line_end": call.line_end,
                        "snippet": call.text[:1200],
                    })
    return templates


def _deserialize_types(method: JavaMethod) -> list[str]:
    out: list[str] = []
    for call in method.calls:
        if call.method not in {"deserialize", "readValue", "convertValue"}:
            continue
        for arg in call.args:
            m = re.match(r"([A-Za-z0-9_.$]+)\.class$", arg.strip())
            if m:
                typ = _clean_type(m.group(1))
                if typ not in out:
                    out.append(typ)
    return out


def _response_assignment_types(method: JavaMethod) -> list[str]:
    out: list[str] = []
    for assignment in method.assignments:
        typ = _clean_type(assignment.declared_type)
        if typ not in {"unknown", "var"} and typ not in _SIMPLE_TYPES and "Request" not in typ:
            if typ not in out:
                out.append(typ)
    return out



def _serialized_payload_types(method: JavaMethod, cls: JavaClass) -> list[str]:
    """Return DTO types explicitly passed to local JSON serialization calls."""
    types = _local_type_map(method, cls)
    out: list[str] = []
    for call in method.calls:
        if call.method not in {"serialize", "writeValueAsString", "toJson"} or not call.args:
            continue
        expression = call.args[0].strip()
        typ = types.get(expression)
        if not typ:
            created = re.match(r"new\s+([A-Za-z0-9_.$]+)", expression)
            typ = _clean_type(created.group(1)) if created else None
        typ = _clean_type(typ)
        if typ not in _SIMPLE_TYPES and typ not in {"unknown", "HttpResponse"} and typ not in out:
            out.append(typ)
    return out


def _registration_facts(
    parsed_files: list[JavaSyntaxFile],
    constants: dict[str, dict[str, Any]],
    value_bindings_by_class: dict[str, dict[str, dict[str, Any]]],
    config_values: dict[str, list[dict[str, Any]]],
) -> tuple[list[dict[str, Any]], list[Fact]]:
    registrations: list[dict[str, Any]] = []
    facts: list[Fact] = []
    for parsed in parsed_files:
        for cls in parsed.classes:
            for method in cls.methods:
                types = _local_type_map(method, cls)
                for call in method.calls:
                    if call.method != "annotatedService" or len(call.args) < 2:
                        continue
                    base_expr, service_symbol = call.args[0].strip(), call.args[1].strip()
                    base = _resolve_expression(base_expr, constants=constants, value_bindings=value_bindings_by_class.get(cls.name, {}), config_values=config_values, context_class=cls.name)
                    service_type = types.get(service_symbol, "unknown")
                    item = {
                        "registration_operation": method.operation,
                        "base_path_expression": base_expr,
                        "base_path_values": base.get("values") or [],
                        "base_path_resolution_basis": base.get("basis"),
                        "service_symbol": service_symbol,
                        "service_type": service_type,
                        "source_file": str(parsed.file),
                        "line_start": call.line_start,
                    }
                    registrations.append(item)
                    facts.append(Fact(
                        fact_type="http_service_registration",
                        name=f"{service_type}@{base_expr}",
                        properties={**item, "evidence_maturity_level": "confirmed", "syntax_provider": "tree_sitter"},
                        evidence=[EvidenceRef(file_path=str(parsed.file), line_start=call.line_start, line_end=call.line_end, snippet=call.text[:1000], extractor=JAVA_SYNTAX_EXTRACTOR)],
                    ))
    return registrations, facts


def _implementation_index(parsed_files: list[JavaSyntaxFile]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = defaultdict(list)
    for parsed in parsed_files:
        for cls in parsed.classes:
            for iface in cls.implements:
                if cls.name not in out[iface]:
                    out[iface].append(cls.name)
    return dict(out)


def _method_http_annotation(method: JavaMethod, constants: dict[str, dict[str, Any]], context_class: str | None = None) -> tuple[str | None, dict[str, Any] | None]:
    # Armeria uses @Post("/path"); JAX-RS uses @POST together with @Path("/path").
    for ann in method.annotations:
        if ann.name not in _HTTP_METHOD_ANNOTATIONS:
            continue
        http_method = _HTTP_METHOD_ANNOTATIONS[ann.name]
        expression = (ann.arguments or "").strip()
        annotation_name = ann.name
        if not expression:
            path_ann = _ann(method.annotations, {"Path"})
            if path_ann is None:
                continue
            expression = (path_ann.arguments or "").strip()
            annotation_name = path_ann.name
        first = next(iter([x.strip() for x in expression.split(",") if x.strip()]), "")
        resolved = _resolve_expression(first, constants=constants, value_bindings={}, config_values={}, context_class=context_class) if first else {"values": [], "basis": "unresolved"}
        return http_method, {"annotation": annotation_name, "expression": first, **resolved}
    return None, None


def _append_unique_interface(existing: list[InterfaceInfo], candidate: InterfaceInfo) -> bool:
    role = (candidate.properties or {}).get("boundary_role")
    marker = (candidate.operation, candidate.path, candidate.method, candidate.direction.value, role)
    candidate_locs = {(e.file_path, e.line_start) for e in candidate.evidence}
    for item in existing:
        item_role = (item.properties or {}).get("boundary_role")
        item_marker = (item.operation, item.path, item.method, item.direction.value, item_role)
        item_locs = {(e.file_path, e.line_start) for e in item.evidence}
        same_source_call = bool(candidate_locs & item_locs) and candidate.operation == item.operation and candidate.direction == item.direction and role == item_role
        if item_marker == marker or same_source_call:
            # Merge richer factual properties and evidence without changing semantic classification.
            merged = dict(item.properties or {})
            merged.update({k: v for k, v in (candidate.properties or {}).items() if v not in (None, [], {}, "")})
            item.properties = merged
            known = {(e.file_path, e.line_start, e.line_end, e.extractor) for e in item.evidence}
            item.evidence.extend(e for e in candidate.evidence if (e.file_path, e.line_start, e.line_end, e.extractor) not in known)
            if candidate.path and ((not item.path) or item.path == (item.properties or {}).get("endpoint_expression")):
                item.path = candidate.path
            if item.schema_ref in {None, "unknown", "method_parameters"} and candidate.schema_ref not in {None, "unknown"}:
                item.schema_ref = candidate.schema_ref
            return False
    existing.append(candidate)
    return True



def _local_callers_by_operation(
    parsed_files: list[JavaSyntaxFile],
    implementation_index: dict[str, list[str]],
) -> dict[str, list[str]]:
    """Build neutral one-hop caller links from resolved local receiver types."""
    methods_by_class_and_name: dict[tuple[str, str], list[str]] = defaultdict(list)
    for parsed in parsed_files:
        for cls in parsed.classes:
            for method in cls.methods:
                methods_by_class_and_name[(cls.name, method.name)].append(method.operation)

    callers: dict[str, set[str]] = defaultdict(set)
    for parsed in parsed_files:
        for cls in parsed.classes:
            for method in cls.methods:
                types = _local_type_map(method, cls)
                for call in method.calls:
                    receiver = (call.receiver or "").strip()
                    target_classes: list[str] = []
                    if receiver:
                        receiver_type = _clean_type(types.get(receiver))
                        if receiver_type and receiver_type != "unknown":
                            target_classes.append(receiver_type)
                            target_classes.extend(implementation_index.get(receiver_type, []))
                    else:
                        target_classes.append(cls.name)
                    for target_class in dict.fromkeys(target_classes):
                        for target_operation in methods_by_class_and_name.get((target_class, call.method), []):
                            if target_operation != method.operation:
                                callers[target_operation].add(method.operation)
    return {operation: sorted(values) for operation, values in callers.items()}


def _local_call_chain_candidates(
    operation: str,
    callers_by_operation: dict[str, list[str]],
    *,
    max_depth: int = 3,
    max_records: int = 64,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen_edges: set[tuple[str, str]] = set()
    frontier: list[tuple[str, int]] = [(operation, 0)]
    while frontier and len(out) < max_records:
        called_operation, depth = frontier.pop(0)
        if depth >= max_depth:
            continue
        for caller in callers_by_operation.get(called_operation, []):
            edge = (caller, called_operation)
            if edge in seen_edges:
                continue
            seen_edges.add(edge)
            out.append({
                "caller_operation": caller,
                "called_operation": called_operation,
                "distance_to_boundary": depth + 1,
                "basis": "local_receiver_type_and_method_call",
            })
            frontier.append((caller, depth + 1))
            if len(out) >= max_records:
                break
    return out


def _builder_setters_by_type(parsed_files: list[JavaSyntaxFile]) -> dict[str, list[str]]:
    """Collect source-observed Lombok-style builder setter names by declared type."""
    out: dict[str, set[str]] = defaultdict(set)
    ignored = {"builder", "build", "stream", "map", "toList", "getBody"}
    for parsed in parsed_files:
        for cls in parsed.classes:
            for method in cls.methods:
                for assignment in method.assignments:
                    declared = _clean_type(assignment.declared_type)
                    if declared in {"unknown", "var"}:
                        continue
                    expression = assignment.expression or ""
                    if not re.search(rf"\b{re.escape(declared)}\s*\.\s*builder\s*\(", expression):
                        continue
                    for setter in re.findall(r"\.\s*([A-Za-z_][A-Za-z0-9_]*)\s*\(", expression):
                        if setter not in ignored and not setter.startswith(("get", "is")):
                            out[declared].add(setter)
    return {name: sorted(values) for name, values in out.items()}

def _maven_dependency_facts(files: list[Path]) -> list[Fact]:
    facts: list[Fact] = []
    for path in files:
        if path.name != "pom.xml":
            continue
        try:
            root = ET.parse(path).getroot()
        except Exception:
            continue
        ns = ""
        if root.tag.startswith("{"):
            ns = root.tag.split("}", 1)[0] + "}"
        props: dict[str, str] = {}
        props_node = root.find(f"{ns}properties")
        if props_node is not None:
            for child in list(props_node):
                props[child.tag.split("}")[-1]] = (child.text or "").strip()
        def resolve(value: str | None) -> str | None:
            text = (value or "").strip()
            m = re.fullmatch(r"\$\{([^}]+)\}", text)
            return props.get(m.group(1), text) if m else text or None
        for dep in root.findall(f".//{ns}dependencies/{ns}dependency"):
            group = resolve(dep.findtext(f"{ns}groupId"))
            artifact = resolve(dep.findtext(f"{ns}artifactId"))
            version = resolve(dep.findtext(f"{ns}version"))
            scope = resolve(dep.findtext(f"{ns}scope")) or "compile"
            if not artifact:
                continue
            coordinate = f"{group or 'unknown'}:{artifact}" + (f":{version}" if version else "")
            facts.append(Fact(
                fact_type="external_dependency",
                name=coordinate,
                properties={
                    "dependency_kind": "maven_artifact",
                    "group_id": group,
                    "artifact_id": artifact,
                    "version": version,
                    "scope": scope,
                    "coordinate": coordinate,
                    "source_set": "main",
                    "is_test_source": scope == "test",
                    "evidence_maturity_level": "confirmed",
                },
                evidence=[EvidenceRef(file_path=str(path), extractor="maven_pom")],
            ))
    return facts


def scan_maven_dependencies(files: list[Path]) -> tuple[list[Fact], dict[str, Any]]:
    """Publish source-observed Maven dependency declarations without topology inference."""
    facts = _maven_dependency_facts(files)
    return facts, {
        "requested": True,
        "status": "success",
        "dependencies_extracted": len(facts),
        "pom_files_scanned": len([path for path in files if path.name == "pom.xml"]),
        "policy": "declared Maven coordinates only; no provider-repository resolution or dependency role inference",
    }


def scan_java_system_interaction_evidence(
    files: list[Path],
    *,
    config_facts: list[Fact],
    schemas: list[SchemaInfo],
    interfaces: list[InterfaceInfo],
) -> tuple[list[Fact], list[InterfaceInfo], list[str], dict[str, Any]]:
    """Enrich local system-boundary evidence without cross-repository matching.

    The stage only composes source-observed Java/configuration facts. It never
    identifies a target system, assigns an interaction status, or evaluates
    business meaning.
    """
    parsed_files, warnings = parse_java_files(files)
    parsed_files = list(parsed_files)
    config_values = _config_index(config_facts)
    constants = _constant_index(parsed_files)
    value_bindings_by_class: dict[str, dict[str, dict[str, Any]]] = {}
    qualifier_bindings_by_class: dict[str, dict[str, str]] = {}
    class_by_name: dict[str, tuple[JavaSyntaxFile, JavaClass]] = {}
    for parsed in parsed_files:
        for cls in parsed.classes:
            class_by_name[cls.name] = (parsed, cls)
            value_bindings_by_class[cls.name] = _class_value_bindings(parsed, cls)
            qualifier_bindings_by_class[cls.name] = _class_qualifier_bindings(cls)

    bean_bindings = _build_rest_template_bean_bindings(
        parsed_files,
        value_bindings_by_class=value_bindings_by_class,
        constants=constants,
        config_values=config_values,
    )
    helper_templates = _helper_templates(parsed_files)
    registrations, registration_fact_items = _registration_facts(
        parsed_files, constants, value_bindings_by_class, config_values
    )
    implementation_index = _implementation_index(parsed_files)
    callers_by_operation = _local_callers_by_operation(parsed_files, implementation_index)
    builder_setters_by_type = _builder_setters_by_type(parsed_files)

    facts: list[Fact] = []
    facts.extend(registration_fact_items)
    facts.extend(_maven_dependency_facts(files))
    produced_interfaces: list[InterfaceInfo] = []

    # Publish explicit configuration bindings as neutral source facts.
    for class_name, bindings in sorted(value_bindings_by_class.items()):
        for symbol, binding in sorted(bindings.items()):
            key = binding.get("property_key")
            observed = config_values.get(str(key), []) if key else []
            facts.append(Fact(
                fact_type="configuration_value_binding",
                name=f"{class_name}.{symbol}",
                properties={
                    "class": class_name,
                    "symbol": symbol,
                    "property_key": key,
                    "default_value": binding.get("default_value"),
                    "observed_values": [x.get("value") for x in observed],
                    "target_kind": binding.get("target_kind"),
                    "binding_basis": "spring_value_annotation",
                    "evidence_maturity_level": "confirmed",
                },
                evidence=[EvidenceRef(file_path=str(binding.get("file")), line_start=binding.get("line"), extractor=JAVA_SYNTAX_EXTRACTOR)],
            ))

    # Enrich direct RestTemplate calls already found by java_structural_scan.
    for parsed in parsed_files:
        for cls in parsed.classes:
            values = value_bindings_by_class.get(cls.name, {})
            qualifiers = qualifier_bindings_by_class.get(cls.name, {})
            for method in cls.methods:
                types = _local_type_map(method, cls)
                for call in method.calls:
                    receiver = (call.receiver or "").strip()
                    if call.method not in {"exchange", "postForObject", "getForObject"} or types.get(receiver) != "RestTemplate" or not call.args:
                        continue
                    # Calls through a RestTemplate method parameter are helper templates.
                    # They become concrete boundaries only after composition with a caller.
                    if any(param.name == receiver and _clean_type(param.type) == "RestTemplate" for param in method.params):
                        continue
                    path_info = _resolve_expression(call.args[0], constants=constants, value_bindings=values, config_values=config_values, context_class=cls.name)
                    bean_name = qualifiers.get(receiver) or receiver
                    bean_candidates = bean_bindings.get(bean_name, [])
                    base_keys = _stable_unique(x.get("base_url_property_key") for x in bean_candidates if x.get("base_url_property_key"))
                    base_values = _stable_unique(v for x in bean_candidates for v in (x.get("base_url_values") or []))
                    path_values = _stable_unique(path_info.get("values") or [])
                    url_variants = _stable_unique(str(base).rstrip("/") + "/" + str(path).lstrip("/") for base in base_values for path in path_values)
                    http_method = "POST" if call.method == "postForObject" else "GET" if call.method == "getForObject" else None
                    request_expr = call.args[1] if call.method == "postForObject" and len(call.args) > 1 else call.args[2] if call.method == "exchange" and len(call.args) > 2 else None
                    if call.method == "exchange" and len(call.args) > 1:
                        mm = re.search(r"(?:HttpMethod\.)?([A-Z]+)", call.args[1])
                        http_method = mm.group(1) if mm else None
                    request_type = _request_type_from_http_entity(method, request_expr, types)
                    response_type = _http_response_type(call.method, call.args, method)
                    props = {
                        "boundary_role": "http_outbound",
                        "composition_basis": "direct_rest_template_call_with_source_configuration_bindings",
                        "client_receiver": receiver,
                        "client_receiver_type": "RestTemplate",
                        "client_bean_name": bean_name,
                        "client_call_pattern": call.method,
                        "endpoint_expression": call.args[0],
                        "endpoint_path_property_key": path_info.get("property_key"),
                        "endpoint_path": path_values[0] if len(path_values) == 1 else None,
                        "endpoint_path_observed_values": path_values,
                        "endpoint_path_variants": path_values,
                        "endpoint_path_resolution_basis": path_info.get("basis"),
                        "base_url_property_key": base_keys[0] if len(base_keys) == 1 else None,
                        "base_url_property_keys": base_keys,
                        "base_url_observed_values": base_values,
                        "base_url_resolution_status": "resolved_single_bean_configuration_property" if len(base_keys) == 1 else "ambiguous_multiple_bean_configuration_properties" if len(base_keys) > 1 else "unresolved",
                        "endpoint_url_variants": url_variants,
                        "request_payload_expression": request_expr,
                        "request_payload_type": request_type,
                        "response_payload_type": response_type,
                        "scenario_operation": method.operation,
                        "local_caller_operations": callers_by_operation.get(method.operation, []),
                        "local_call_chain_candidates": _local_call_chain_candidates(method.operation, callers_by_operation),
                        "request_observed_builder_setters": builder_setters_by_type.get(request_type, []),
                        "source_set": _source_set(parsed.file),
                        "is_test_source": _source_set(parsed.file) == "test",
                        "syntax_provider": "tree_sitter",
                    }
                    candidate = InterfaceInfo(
                        name=str(path_values[0] if path_values else call.args[0])[:160],
                        direction=Direction.OUTBOUND,
                        kind=InterfaceKind.REST,
                        schema_ref=response_type,
                        operation=method.operation,
                        path=str(path_values[0] if len(path_values) == 1 else call.args[0]),
                        method=http_method,
                        evidence=[EvidenceRef(file_path=str(parsed.file), line_start=call.line_start, line_end=call.line_end, snippet=call.text[:1200], extractor="java_http_interaction_enrichment")],
                        properties=props,
                    )
                    _append_unique_interface(interfaces, candidate)
                    facts.append(Fact(
                        fact_type="http_outbound_binding",
                        name=f"{method.operation}:{call.args[0]}",
                        properties={**props, "http_method": http_method, "evidence_maturity_level": "confirmed"},
                        evidence=candidate.evidence,
                    ))

    # Compose helper method templates with concrete call sites.
    templates_by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for template in helper_templates:
        templates_by_name[template["helper_method"]].append(template)
        facts.append(Fact(
            fact_type="http_outbound_helper_template",
            name=template["helper_operation"],
            properties={**template, "evidence_maturity_level": "confirmed"},
            evidence=[EvidenceRef(file_path=template["source_file"], line_start=template["line_start"], line_end=template["line_end"], snippet=template["snippet"], extractor="java_http_interaction_enrichment")],
        ))
    for parsed in parsed_files:
        for cls in parsed.classes:
            values = value_bindings_by_class.get(cls.name, {})
            qualifiers = qualifier_bindings_by_class.get(cls.name, {})
            for method in cls.methods:
                types = _local_type_map(method, cls)
                for call in method.calls:
                    for template in templates_by_name.get(call.method, []):
                        if len(call.args) != template["parameter_count"]:
                            continue
                        path_expr = call.args[template["path_param_index"]]
                        rest_expr = call.args[template["receiver_param_index"]]
                        req_idx = template.get("request_param_index")
                        request_expr = call.args[req_idx] if isinstance(req_idx, int) and req_idx < len(call.args) else None
                        path_info = _resolve_expression(path_expr, constants=constants, value_bindings=values, config_values=config_values, context_class=cls.name)
                        bean_name = qualifiers.get(rest_expr) or rest_expr
                        bean_candidates = bean_bindings.get(bean_name, [])
                        base_keys = _stable_unique(x.get("base_url_property_key") for x in bean_candidates if x.get("base_url_property_key"))
                        base_values = _stable_unique(v for x in bean_candidates for v in (x.get("base_url_values") or []))
                        path_values = _stable_unique(path_info.get("values") or [])
                        url_variants = _stable_unique(str(base).rstrip("/") + "/" + str(path).lstrip("/") for base in base_values for path in path_values)
                        request_type = types.get(str(request_expr), "unknown") if request_expr else "unknown"
                        response_type = template.get("response_payload_type") or "unknown"
                        props = {
                            "boundary_role": "http_outbound",
                            "composition_basis": "helper_method_template_and_concrete_call_site",
                            "helper_operation": template["helper_operation"],
                            "scenario_operation": method.operation,
                            "client_receiver": rest_expr,
                            "client_receiver_type": "RestTemplate",
                            "client_bean_name": bean_name,
                            "client_call_pattern": template.get("call_pattern"),
                            "endpoint_expression": path_expr,
                            "endpoint_path_property_key": path_info.get("property_key"),
                            "endpoint_path": path_values[0] if len(path_values) == 1 else None,
                            "endpoint_path_observed_values": path_values,
                            "endpoint_path_variants": path_values,
                            "endpoint_path_resolution_basis": path_info.get("basis"),
                            "base_url_property_key": base_keys[0] if len(base_keys) == 1 else None,
                            "base_url_property_keys": base_keys,
                            "base_url_observed_values": base_values,
                            "base_url_resolution_status": "resolved_single_bean_configuration_property" if len(base_keys) == 1 else "ambiguous_multiple_bean_configuration_properties" if len(base_keys) > 1 else "unresolved",
                            "endpoint_url_variants": url_variants,
                            "request_payload_expression": request_expr,
                            "request_payload_type": request_type,
                            "response_payload_type": response_type,
                            "local_caller_operations": callers_by_operation.get(method.operation, []),
                            "local_call_chain_candidates": _local_call_chain_candidates(method.operation, callers_by_operation),
                            "request_observed_builder_setters": builder_setters_by_type.get(request_type, []),
                            "source_set": _source_set(parsed.file),
                            "is_test_source": _source_set(parsed.file) == "test",
                            "syntax_provider": "tree_sitter",
                        }
                        evidence = [
                            EvidenceRef(file_path=str(parsed.file), line_start=call.line_start, line_end=call.line_end, snippet=call.text[:1200], extractor="java_http_interaction_enrichment_call_site"),
                            EvidenceRef(file_path=template["source_file"], line_start=template["line_start"], line_end=template["line_end"], snippet=template["snippet"], extractor="java_http_interaction_enrichment_helper"),
                        ]
                        candidate = InterfaceInfo(
                            name=str(path_values[0] if path_values else path_expr)[:160],
                            direction=Direction.OUTBOUND,
                            kind=InterfaceKind.REST,
                            schema_ref=str(response_type),
                            operation=method.operation,
                            path=str(path_values[0] if len(path_values) == 1 else path_expr),
                            method=template.get("http_method"),
                            evidence=evidence,
                            properties=props,
                        )
                        if _append_unique_interface(interfaces, candidate):
                            produced_interfaces.append(candidate)
                        facts.append(Fact(
                            fact_type="http_outbound_call_composed",
                            name=f"{method.operation}:{path_expr}",
                            properties={**props, "http_method": template.get("http_method"), "evidence_maturity_level": "confirmed"},
                            evidence=evidence,
                        ))

    # Armeria/JAX-RS endpoints and programmatic base-path registrations.
    for parsed in parsed_files:
        for cls in parsed.classes:
            source_set = _source_set(parsed.file)
            for method in cls.methods:
                http_method, path_info = _method_http_annotation(method, constants, cls.name)
                if not http_method or not path_info:
                    continue
                method_paths = path_info.get("values") or ([path_info.get("expression")] if path_info.get("expression") else [])
                matching_bases: list[dict[str, Any]] = []
                for registration in registrations:
                    stype = registration.get("service_type")
                    implementations = implementation_index.get(str(stype), [])
                    if cls.name == stype or cls.name in implementations or stype in cls.implements:
                        matching_bases.append(registration)
                base_paths = [v for r in matching_bases for v in (r.get("base_path_values") or [])]
                full_paths = []
                if base_paths:
                    full_paths = [_join_paths(base, method_path) for base in base_paths for method_path in method_paths]
                else:
                    full_paths = method_paths
                full_paths = [x for x in full_paths if x]
                request_candidates = [
                    _clean_type(p.type) for p in method.params
                    if _clean_type(p.type) not in _RAW_HTTP_REQUEST_TYPES and _clean_type(p.type) not in _SIMPLE_TYPES
                ]
                if not request_candidates:
                    request_candidates = _deserialize_types(method)
                request_type = request_candidates[0] if request_candidates else "unknown"
                serialized_response_candidates = _serialized_payload_types(method, cls)
                assignment_response_candidates = _response_assignment_types(method)
                response_candidates = list(dict.fromkeys(serialized_response_candidates or assignment_response_candidates))
                return_type = _clean_type(method.return_type)
                response_type = response_candidates[0] if len(response_candidates) == 1 else return_type
                for full_path in full_paths or [None]:
                    common_props = {
                        "framework": "armeria_or_jaxrs",
                        "annotation": path_info.get("annotation"),
                        "method_path_expression": path_info.get("expression"),
                        "method_path_variants": method_paths,
                        "method_path_resolution_basis": path_info.get("basis"),
                        "registration_base_path_variants": base_paths,
                        "registration_records": matching_bases,
                        "full_path_variants": full_paths,
                        "full_path_basis": "programmatic_service_registration_and_method_annotation" if base_paths else "method_annotation",
                        "request_payload_type": request_type,
                        "response_payload_type": response_type,
                        "response_payload_candidates": response_candidates,
                        "response_payload_candidate_basis": "json_serialization_and_local_declared_types" if serialized_response_candidates else "local_declared_types",
                        "scenario_operation": method.operation,
                        "local_caller_operations": callers_by_operation.get(method.operation, []),
                        "local_call_chain_candidates": _local_call_chain_candidates(method.operation, callers_by_operation),
                        "request_observed_builder_setters": builder_setters_by_type.get(request_type, []),
                        "source_set": source_set,
                        "is_test_source": source_set == "test",
                        "syntax_provider": "tree_sitter",
                    }
                    ev = [EvidenceRef(file_path=str(parsed.file), line_start=method.line_start, line_end=method.line_end, snippet=method.text[:1600], extractor="java_http_interaction_enrichment")]
                    if request_type != "unknown":
                        request_candidate = InterfaceInfo(
                            name=f"{http_method} {full_path or path_info.get('expression')} request",
                            direction=Direction.INBOUND,
                            kind=InterfaceKind.REST,
                            schema_ref=request_type,
                            operation=method.operation,
                            path=full_path,
                            method=http_method,
                            evidence=ev,
                            properties={**common_props, "boundary_role": "rest_request"},
                        )
                        if _append_unique_interface(interfaces, request_candidate):
                            produced_interfaces.append(request_candidate)
                    response_candidate = InterfaceInfo(
                        name=f"{http_method} {full_path or path_info.get('expression')} response",
                        direction=Direction.OUTBOUND,
                        kind=InterfaceKind.REST,
                        schema_ref=response_type,
                        operation=method.operation,
                        path=full_path,
                        method=http_method,
                        evidence=ev,
                        properties={**common_props, "boundary_role": "rest_response"},
                    )
                    if _append_unique_interface(interfaces, response_candidate):
                        produced_interfaces.append(response_candidate)
                    facts.append(Fact(
                        fact_type="http_inbound_endpoint_registration",
                        name=f"{method.operation}:{full_path or path_info.get('expression')}",
                        properties={
                            **common_props,
                            "http_method": http_method,
                            "full_path": full_path,
                            "evidence_maturity_level": "confirmed",
                        },
                        evidence=ev,
                    ))

    coverage = {
        "requested": True,
        "configuration_value_bindings": sum(1 for f in facts if f.fact_type == "configuration_value_binding"),
        "http_outbound_bindings": sum(1 for f in facts if f.fact_type == "http_outbound_binding"),
        "http_outbound_helper_templates": len(helper_templates),
        "http_outbound_composed_calls": sum(1 for f in facts if f.fact_type == "http_outbound_call_composed"),
        "http_service_registrations": len(registrations),
        "http_inbound_endpoint_registrations": sum(1 for f in facts if f.fact_type == "http_inbound_endpoint_registration"),
        "maven_dependencies": sum(1 for f in facts if f.fact_type == "external_dependency" and (f.properties or {}).get("dependency_kind") == "maven_artifact"),
        "boundaries_with_local_callers": sum(1 for item in interfaces if (item.properties or {}).get("local_caller_operations")),
        "interfaces_added": len(produced_interfaces),
        "policy": "local source-observed boundary composition only; no cross-repository matching or target-system identification",
    }
    return facts, produced_interfaces, list(warnings), coverage
