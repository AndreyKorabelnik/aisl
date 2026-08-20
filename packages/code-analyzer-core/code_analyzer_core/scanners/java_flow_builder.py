from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from code_analyzer_core.models import Fact, EvidenceRef
from code_analyzer_core.scanners.java_syntax import (
    JAVA_SYNTAX_EXTRACTOR,
    parse_java_files,
    parse_java_text,
    JavaAssignment,
    JavaCall,
    JavaMethod,
    JavaObjectCreation,
    method_params_as_dicts,
    method_visibility as _ts_method_visibility,
)


SERIALIZATION_TOKENS = (
    "dtoToString", "toJson", "writeValueAsString", "convertValue", "String.valueOf", ".toString("
)

IDENTIFIER_TOKENS = (
    "cardNumber", "cardNumbers", "phoneNumber", "phoneNumbers", "ucpId", "clientId", "deviceId",
    "account", "accounts", "pan", "linkId", "requestId", "rqUid",
)

IDENTIFIER_TOKEN_LOWER = tuple(x.lower() for x in IDENTIFIER_TOKENS)


def _clean_expression(value: str | None) -> str:
    if not value:
        return ""
    out = re.sub(r"\s+", " ", value).strip()
    out = out.rstrip(";")
    if out.count("(") > out.count(")"):
        out += ")" * (out.count("(") - out.count(")"))
    out = out.rstrip(";")
    return out[:500]


def _parse_params(params: str) -> list[dict[str, str]]:
    # Compatibility helper: parse method parameters via Tree-sitter instead of
    # comma-splitting Java syntax by hand. Used by older mapper-signature helpers.
    try:
        parsed = parse_java_text(f"class __AnalyzerParams {{ void __m({params or ''}) {{}} }}")
        method = parsed.methods[0] if parsed.methods else None
        return method_params_as_dicts(method) if method else []
    except Exception:
        return []


def _parameter_names(params: list[dict[str, str]]) -> set[str]:
    return {p["name"] for p in params if p.get("name")}


def _contains_symbol(expr: str, symbol: str) -> bool:
    return bool(re.search(rf"(?<![A-Za-z0-9_]){re.escape(symbol)}(?![A-Za-z0-9_])", expr or ""))


def _serialization_kind(expr: str, source_param: str) -> str | None:
    low = expr.lower()
    if not _contains_symbol(expr, source_param):
        return None
    for token in SERIALIZATION_TOKENS:
        if token.lower() in low:
            return token
    return None


def _field_role(name: str | None) -> str:
    low = (name or "").lower()
    return "identifier" if any(tok in low for tok in IDENTIFIER_TOKEN_LOWER) else "field"


def _normalize_java_type(type_name: str | None) -> str:
    if not type_name:
        return "unknown"
    t = str(type_name).strip()
    t = re.sub(r"<.*>", "", t).strip()
    t = t.replace("[]", "")
    return t.split(".")[-1].strip() or "unknown"


def _extract_schema_fields(files: list[Path]) -> dict[str, list[dict[str, str]]]:
    """Extract lightweight class/record fields using Tree-sitter Java syntax.

    This relies on Tree-sitter structural facts and still keeps the
    existing product rule: only identifier-like fields are included here because
    this helper feeds identifier-focused source-to-sink evidence.
    """
    schemas: dict[str, list[dict[str, str]]] = {}
    parsed_files, _warnings = parse_java_files(files)
    for parsed in parsed_files:
        for cls in parsed.classes:
            fields = schemas.setdefault(cls.name, [])
            existing = {x["name"] for x in fields}
            for field in cls.fields:
                fname = field.name
                if fname in {"serialVersionUID"} or fname in existing:
                    continue
                if _field_role(fname) != "identifier":
                    continue
                fields.append({"name": fname, "type": field.type or "unknown", "role": "identifier"})
                existing.add(fname)
            if not fields:
                schemas.pop(cls.name, None)
    return schemas


def _getter_field(expr: str, param: str) -> str | None:
    # getCardNumber(), cardNumber(), object.cardNumber, object.cardNumber()
    patterns = [
        rf"\b{re.escape(param)}\.get([A-Z][A-Za-z0-9_]*)\s*\(",
        rf"\b{re.escape(param)}\.([A-Za-z_][A-Za-z0-9_]*)\s*\(",
        rf"\b{re.escape(param)}\.([A-Za-z_][A-Za-z0-9_]*)\b",
    ]
    for pat in patterns:
        m = re.search(pat, expr)
        if not m:
            continue
        raw = m.group(1)
        if raw in {"toString", "hashCode", "equals", "getClass"}:
            continue
        if "get([A-Z]" in pat and raw and raw[0].isupper():
            return raw[0].lower() + raw[1:]
        return raw
    return None


def _assignment_map_from_syntax(assignments_in: tuple[JavaAssignment, ...] | list[JavaAssignment], params: set[str]) -> dict[str, dict[str, Any]]:
    assignments: dict[str, dict[str, Any]] = {}
    # Preserve source order. Alias propagation is intentionally local to one method:
    #   var payload = request;
    #   var command = payload;
    #   service.save(command);
    # should still bind `command` back to the controller/listener payload parameter.
    for item in sorted(assignments_in or [], key=lambda x: (getattr(x, "start_byte", 0), getattr(x, "line_start", 0))):
        if item.assignment_kind not in {"variable_declaration", "assignment_expression"}:
            continue
        var = _clean_expression(item.target)
        # Avoid treating object.field = request as a new local payload alias. Setter/object
        # mappings are handled separately by field-lineage extraction.
        if not var or "." in var or "[" in var or "(" in var:
            continue
        expr = _clean_expression(item.expression)
        matched: dict[str, Any] | None = None
        parameter_candidates: list[tuple[int, int, str, str | None]] = []
        for param in sorted(params):
            if not _contains_symbol(expr, param):
                continue
            source_field = _getter_field(expr, param)
            if expr == param:
                rank = 0
            elif source_field:
                rank = 1
            else:
                rank = 2
            match = re.search(rf"\b{re.escape(param)}\b", expr)
            position = match.start() if match else len(expr)
            parameter_candidates.append((rank, position, param, source_field))
        if parameter_candidates:
            _, _, param, source_field = min(parameter_candidates)
            matched = {
                "source_parameter": param,
                "expression": expr,
                "serialization_kind": _serialization_kind(expr, param),
                "source_field": source_field,
                "alias_depth": 0,
                "alias_via": [],
                "relation_hint": "same_object" if expr == param else "derived_object",
            }
        if matched is None:
            for alias, info in list(assignments.items()):
                if expr == alias or _contains_symbol(expr, alias):
                    source = str(info.get("source_parameter") or "")
                    if not source:
                        continue
                    alias_field = _getter_field(expr, alias)
                    matched = {
                        "source_parameter": source,
                        "expression": expr,
                        "serialization_kind": info.get("serialization_kind") or _serialization_kind(expr, alias),
                        "source_field": alias_field or info.get("source_field"),
                        "alias_depth": int(info.get("alias_depth") or 0) + 1,
                        "alias_via": [*list(info.get("alias_via") or []), alias],
                        "relation_hint": "same_object" if expr == alias and str(info.get("relation_hint") or "same_object") == "same_object" else "derived_object",
                    }
                    break
        if matched is not None:
            assignments[var] = matched
    return assignments


def _synthetic_method_for_body(body: str) -> JavaMethod | None:
    source = body or "{}"
    if not source.lstrip().startswith("{"):
        source = "{" + source + "}"
    try:
        parsed = parse_java_text("class __AnalyzerBody { void __m() " + source + " }")
    except Exception:
        return None
    return parsed.methods[0] if parsed.methods else None


def _assignment_map(body: str, params: set[str]) -> dict[str, dict[str, Any]]:
    method = _synthetic_method_for_body(body)
    return _assignment_map_from_syntax(method.assignments if method else (), params)


def _dict_or_attr(item: Any, name: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(name, default)
    return getattr(item, name, default)


def _unwrap_response_entity_ok(expr: str) -> str:
    """Return ResponseEntity.ok(payload) payload using Tree-sitter call nodes.

    This keeps response unwrapping in the syntax layer instead of using return-text
    regexes. If parsing fails or the expression is not ResponseEntity.ok, the
    original expression is returned.
    """
    clean = _clean_expression(expr)
    if not clean:
        return ""
    method = _synthetic_method_for_body(f"{{ return {clean}; }}")
    if not method:
        return clean
    for call in method.calls:
        if call.receiver == "ResponseEntity" and call.method == "ok" and call.args:
            return _clean_expression(call.args[0])
    return clean


def _return_expressions_from_syntax(returns_in: tuple[Any, ...] | list[Any]) -> list[str]:
    out: list[str] = []
    for item in returns_in or []:
        expr = _clean_expression(_dict_or_attr(item, "expression", ""))
        if not expr:
            continue
        out.append(_unwrap_response_entity_ok(expr))
    return out


def _return_expressions_from_method_info(mi: dict[str, Any]) -> list[str]:
    return _return_expressions_from_syntax(mi.get("returns") or [])


def _source_param_for_payload(payload: str, params: set[str], assignments: dict[str, dict[str, Any]]) -> tuple[str | None, str, str | None]:
    payload = _clean_expression(payload)
    for param in sorted(params):
        if _contains_symbol(payload, param):
            return param, "direct_or_expression", _serialization_kind(payload, param)
    for var, info in assignments.items():
        if _contains_symbol(payload, var):
            return str(info.get("source_parameter")), f"via_local_variable:{var}", info.get("serialization_kind")
    return None, "unknown", None


def _fields_for_payload(
    *,
    payload: str,
    source_param: str,
    source_type: str,
    assignments: dict[str, dict[str, Any]],
    schema_fields: dict[str, list[dict[str, str]]],
) -> tuple[list[dict[str, Any]], str]:
    """Return candidate propagated fields and propagation mode.

    The payload may be either the source expression itself or a local variable that
    was assigned from that expression, for example:

        String payload = dtoToString(event);
        kafkaTemplate.send(topic, payload);

    In the latter case field propagation is a navigation signal unless an
    explicit field access is observed.
    """
    payload = _clean_expression(payload)
    fields_from_schema = schema_fields.get(_normalize_java_type(source_type), [])

    def schema_candidates(source: str) -> list[dict[str, Any]]:
        return [
            {"name": f["name"], "role": f.get("role") or _field_role(f["name"]), "source": source}
            for f in fields_from_schema
        ]

    explicit = _getter_field(payload, source_param)
    if explicit:
        return [{"name": explicit, "role": _field_role(explicit), "source": "getter_or_accessor"}], "explicit_field_access"

    for var, info in assignments.items():
        if not _contains_symbol(payload, var):
            continue
        if info.get("source_field"):
            field = str(info["source_field"])
            return [{"name": field, "role": _field_role(field), "source": f"assignment:{var}"}], "field_via_local_variable"
        expr = _clean_expression(info.get("expression"))
        if _contains_symbol(expr, source_param):
            explicit_from_assignment = _getter_field(expr, source_param)
            if explicit_from_assignment:
                return [
                    {
                        "name": explicit_from_assignment,
                        "role": _field_role(explicit_from_assignment),
                        "source": f"assignment:{var}",
                    }
                ], "field_via_local_variable"
            if fields_from_schema:
                return schema_candidates(f"schema_whole_object_via_assignment:{var}"), "whole_object_known_schema_fields_via_local_variable"

    # Whole-object payload or whole-object serialization. Use known identifier fields from schema.
    if _contains_symbol(payload, source_param) and fields_from_schema:
        return schema_candidates("schema_whole_object"), "whole_object_known_schema_fields"

    return [], "no_field_level_evidence"


def _looks_like_outbound_receiver(receiver: str | None, sink_kind: str, pattern_name: str) -> bool:
    receiver_low = (receiver or "").lower()
    if sink_kind in {"jms", "http_client", "rest_response"}:
        return True
    if pattern_name.startswith("producer_record"):
        return True
    if sink_kind == "spring_stream":
        return any(tok in receiver_low for tok in ["streambridge", "bridge"])
    if sink_kind == "kafka":
        return any(tok in receiver_low for tok in ["kafka", "template", "producer", "publisher"])
    return bool(receiver)


def _method_visibility(mods: str | None) -> str:
    m = (mods or "").strip()
    if "private" in m:
        return "private"
    if "protected" in m:
        return "protected"
    if "public" in m:
        return "public"
    return "package"


def _class_name_for_position(text: str, pos: int, default: str) -> str:
    """Compatibility helper for existing callers.

    Main Java scanning now obtains class ownership from Tree-sitter method nodes.
    This fallback is kept only for older helper code paths that still pass raw text.
    """
    return default


def _sink_matches_from_method(method: JavaMethod) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for call in method.calls:
        receiver = _clean_expression(call.receiver)
        args = [_clean_expression(a) for a in call.args]
        if call.method == "send" and len(args) >= 2:
            if _looks_like_outbound_receiver(receiver, "spring_stream", "stream_bridge_send"):
                matches.append({
                    "sink_kind": "spring_stream", "sink_pattern": "stream_bridge_send",
                    "receiver": receiver, "target": args[0], "payload": args[1],
                    "line_start": call.line_start, "snippet": call.text,
                })
            elif _looks_like_outbound_receiver(receiver, "kafka", "kafka_send_three_args" if len(args) >= 3 else "kafka_send_two_args"):
                matches.append({
                    "sink_kind": "kafka", "sink_pattern": "kafka_send_three_args" if len(args) >= 3 else "kafka_send_two_args",
                    "receiver": receiver, "target": args[0], "payload": args[2] if len(args) >= 3 else args[1],
                    "line_start": call.line_start, "snippet": call.text,
                })
        elif call.method == "convertAndSend" and len(args) >= 2:
            matches.append({
                "sink_kind": "jms", "sink_pattern": "jms_convert_and_send",
                "receiver": receiver, "target": args[0], "payload": args[1],
                "line_start": call.line_start, "snippet": call.text,
            })
        elif call.method == "postForObject" and len(args) >= 2:
            matches.append({
                "sink_kind": "http_client", "sink_pattern": "rest_template_post_for_object",
                "receiver": receiver, "target": args[0], "payload": args[1],
                "line_start": call.line_start, "snippet": call.text,
            })
        elif call.method == "bodyValue" and args:
            matches.append({
                "sink_kind": "http_client", "sink_pattern": "web_client_body_value",
                "receiver": receiver, "target": receiver, "payload": args[0],
                "line_start": call.line_start, "snippet": call.text,
            })
        elif receiver == "ResponseEntity" and call.method == "ok" and args:
            matches.append({
                "sink_kind": "rest_response", "sink_pattern": "response_entity_ok",
                "receiver": receiver, "target": "ResponseEntity.ok", "payload": args[0],
                "line_start": call.line_start, "snippet": call.text,
            })
    for creation in method.object_creations:
        if creation.type.split(".")[-1] == "ProducerRecord" and len(creation.args) >= 2:
            args = [_clean_expression(a) for a in creation.args]
            matches.append({
                "sink_kind": "kafka", "sink_pattern": "producer_record_three_args" if len(args) >= 3 else "producer_record_two_args",
                "receiver": "ProducerRecord", "target": args[0], "payload": args[2] if len(args) >= 3 else args[1],
                "line_start": creation.line_start, "snippet": creation.text,
            })
    return matches

def _sink_matches_from_method_info(mi: dict[str, Any]) -> list[dict[str, Any]]:
    class _MethodAdapter:
        calls = []
        object_creations = []
    method = _MethodAdapter()
    # The dataclass fields are accessed by attribute in _sink_matches_from_method;
    # adapt dictionaries without reintroducing regex-level syntax parsing.
    class _Obj:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)
    method.calls = [_Obj(**c) for c in (mi.get("method_calls") or [])]
    method.object_creations = [_Obj(**c) for c in (mi.get("object_creations") or [])]
    return _sink_matches_from_method(method)  # type: ignore[arg-type]



def build_java_data_flow_facts(files: list[Path]) -> tuple[list[Fact], dict[str, Any]]:
    """Build lightweight source-to-sink and field-level data-flow evidence.

    MVP scope:
    - method parameter -> outbound payload
    - method parameter -> serialization/helper -> outbound payload
    - identifier field propagation for explicit getter/accessor or known whole-object schema fields
    - supports Kafka send, ProducerRecord, StreamBridge/JMS/HTTP send, REST response
    """
    facts: list[Fact] = []
    flow_count = 0
    field_flow_count = 0
    schema_fields = _extract_schema_fields(files)
    status: dict[str, Any] = {
        "requested": True,
        "mode": "lightweight_method_parameter_and_field_to_outbound_sink",
        "files_scanned": 0,
        "methods_scanned": 0,
        "flows_extracted": 0,
        "field_flows_extracted": 0,
        "identifier_schema_count": len(schema_fields),
        "warnings": [],
    }

    parsed_files, parse_warnings = parse_java_files(files)
    status["warnings"].extend(parse_warnings)

    for parsed in parsed_files:
        p = parsed.file
        text = parsed.text
        status["files_scanned"] += 1
        for method in parsed.methods:
            class_name = method.class_name
            method_name = method.name
            params = method_params_as_dicts(method)
            if not params:
                continue
            status["methods_scanned"] += 1
            body = method.body or method.text
            method_start_line = method.line_start
            method_end_line = method.line_end
            param_names = _parameter_names(params)
            assignments = _assignment_map_from_syntax(method.assignments, param_names)
            operation = method.operation
            visibility = _ts_method_visibility(method)

            for sink in _sink_matches_from_method(method):
                    sink_kind = str(sink.get("sink_kind") or "unknown")
                    pattern_name = str(sink.get("sink_pattern") or "unknown")
                    receiver = _clean_expression(sink.get("receiver"))
                    payload = _clean_expression(sink.get("payload"))
                    target = _clean_expression(sink.get("target"))
                    if not payload:
                        continue
                    source_param, flow_mode, serialization_kind = _source_param_for_payload(payload, param_names, assignments)
                    if not source_param:
                        continue

                    param_info = next((x for x in params if x.get("name") == source_param), {})
                    source_type = param_info.get("type") or "unknown"
                    sink_line = int(sink.get("line_start") or method_start_line)
                    flow_count += 1
                    flow_id = f"flow_{flow_count:06d}"
                    method_snippet = method.text
                    if len(method_snippet) > 3500:
                        method_snippet = method_snippet[:3500] + "\n... method truncated ..."

                    steps: list[dict[str, Any]] = [
                        {
                            "kind": "method_parameter",
                            "operation": operation,
                            "parameter": source_param,
                            "parameter_type": source_type,
                        }
                    ]
                    if flow_mode.startswith("via_local_variable"):
                        var = flow_mode.split(":", 1)[1]
                        steps.append({
                            "kind": "assignment",
                            "variable": var,
                            "expression": assignments.get(var, {}).get("expression"),
                        })
                    if serialization_kind:
                        steps.append({
                            "kind": "serialization_or_simple_transform",
                            "method_or_pattern": serialization_kind,
                            "input_parameter": source_param,
                            "output_expression": payload,
                        })
                    steps.append({
                        "kind": "outbound_sink",
                        "sink_kind": sink_kind,
                        "sink_pattern": pattern_name,
                        "target_expression": target,
                        "payload_expression": payload,
                    })

                    flow_evidence = [EvidenceRef(
                        file_path=str(p),
                        line_start=method_start_line,
                        line_end=method_end_line,
                        snippet=method_snippet[:1600],
                        extractor=f"java_data_flow_builder:{JAVA_SYNTAX_EXTRACTOR}",
                    ), EvidenceRef(
                        file_path=str(p),
                        line_start=sink_line,
                        line_end=sink_line,
                        snippet=str(sink.get("snippet") or "")[:900],
                        extractor="java_data_flow_builder_sink",
                    )]

                    facts.append(Fact(
                        fact_type="source_to_sink_flow",
                        name=f"{operation}: {source_param} -> {sink_kind} payload",
                        properties={
                            "flow_id": flow_id,
                            "flow_type": "method_parameter_to_outbound_payload",
                            "operation": operation,
                            "class_name": class_name,
                            "method_name": method_name,
                            "method_visibility": visibility,
                            "source_kind": "method_parameter",
                            "source_parameter": source_param,
                            "source_type": source_type,
                            "sink_kind": sink_kind,
                            "sink_pattern": pattern_name,
                            "receiver_expression": receiver,
                            "target_expression": target,
                            "payload_expression": payload,
                            "flow_mode": flow_mode,
                            "serialization_kind": serialization_kind,
                            "steps": steps,
                            "evidence_maturity_dimensions": {
                                "source_boundary": "unresolved",
                                "field_mapping": "not_applicable",
                                "end_to_end_trace": "unresolved",
                            },
                            "evidence_maturity_level": "unresolved",
                            "missing_links": [
                                "caller or inbound channel may be outside current repository" if visibility in {"public", "protected", "package"} else "upstream caller not resolved"
                            ],
                        },
                        evidence=flow_evidence,
                    ))

                    field_candidates, field_mode = _fields_for_payload(
                        payload=payload,
                        source_param=source_param,
                        source_type=source_type,
                        assignments=assignments,
                        schema_fields=schema_fields,
                    )
                    for field in field_candidates:
                        field_name = str(field["name"])
                        role = str(field.get("role") or _field_role(field_name))
                        if role != "identifier":
                            continue
                        field_flow_count += 1
                        field_flow_id = f"field_flow_{field_flow_count:06d}"
                        trace_status = "confirmed" if field_mode in {"explicit_field_access", "field_via_local_variable"} else "unresolved"
                        path_steps = [
                            f"method parameter {source_param}",
                            f"{source_param}.{field_name}",
                        ]
                        if serialization_kind:
                            path_steps.append(f"{serialization_kind}({source_param})")
                        path_steps.append(f"{pattern_name} payload: {payload}")
                        facts.append(Fact(
                            fact_type="field_identifier_flow",
                            name=f"{operation}: {source_type}.{field_name} -> {sink_kind} payload",
                            properties={
                                "field_flow_id": field_flow_id,
                                "source_object": _normalize_java_type(source_type),
                                "source_parameter": source_param,
                                "source_field": field_name,
                                "source_role": role,
                                "field_mode": field_mode,
                                "sink_channel": sink_kind,
                                "sink_kind": sink_kind,
                                "sink_pattern": pattern_name,
                                "sink": target,
                                "sink_payload": payload,
                                "payload_expression": payload,
                                "target_expression": target,
                                "operation": operation,
                                "class_name": class_name,
                                "method_name": method_name,
                                "trace_status": trace_status,
                                "evidence_maturity_dimensions": {
                                    "field_mapping": trace_status,
                                    "source_boundary": "unresolved",
                                    "end_to_end_trace": "unresolved",
                                },
                                "evidence_maturity_level": trace_status if trace_status == "confirmed" else "unresolved",
                                "related_flow_id": flow_id,
                                "path": path_steps,
                                "candidate_signals": [] if trace_status == "confirmed" else [{
                                    "signal_type": "whole_object_field_navigation_signal",
                                    "target": payload,
                                    "basis": f"identifier-like field {field_name} is part of the source schema but no explicit field access was observed",
                                    "is_evidence": False,
                                    "allowed_use": "navigation_only",
                                    "requires_source_inspection": True,
                                    "recommended_action": "inspect serialization/helper that builds the outbound payload",
                                }],
                            },
                            evidence=flow_evidence,
                        ))

    status["flows_extracted"] = flow_count
    status["field_flows_extracted"] = field_flow_count
    return facts, status
