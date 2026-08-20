from __future__ import annotations

import functools
import hashlib
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


@dataclass(frozen=True)
class FdpViewDependencies:
    compact_or_facts: Callable[[Path, str, str], list[dict[str, Any]]]
    event_sources: Callable[..., list[dict[str, Any]]]
    mapping_items: Callable[..., list[dict[str, Any]]]
    data_flow_items: Callable[..., list[dict[str, Any]]]
    stored_data_access: Callable[..., dict[str, Any]]
    db_schema_items: Callable[[Path, str], list[dict[str, Any]]]
    item_id: Callable[[dict[str, Any]], str | None]
    item_matches_blob: Callable[[dict[str, Any], str], bool]
    locations_from_item: Callable[[dict[str, Any]], list[dict[str, Any]]]
    evidence_refs: Callable[[dict[str, Any]], list[str]]
    openspec_id: Callable[..., str]
    props: Callable[[dict[str, Any]], dict[str, Any]]
    status_from_evidence_level: Callable[..., str]
    read_json: Callable[..., Any]
    write_lazy: Callable[..., Any]


_CURRENT_DEPS: FdpViewDependencies | None = None


def _deps() -> FdpViewDependencies:
    if _CURRENT_DEPS is None:
        raise RuntimeError("FDP view dependencies are not configured")
    return _CURRENT_DEPS


class _FdpDepsContext:
    def __init__(self, deps: FdpViewDependencies):
        self.deps = deps
        self.previous: FdpViewDependencies | None = None

    def __enter__(self) -> None:
        global _CURRENT_DEPS
        self.previous = _CURRENT_DEPS
        _CURRENT_DEPS = self.deps

    def __exit__(self, exc_type, exc, tb) -> None:
        global _CURRENT_DEPS
        _CURRENT_DEPS = self.previous


def _compact_or_facts(analysis_out: Path, compact_name: str, fact_type: str) -> list[dict[str, Any]]:
    return _deps().compact_or_facts(analysis_out, compact_name, fact_type)


def _event_sources(analysis_out: Path, **kwargs: Any) -> list[dict[str, Any]]:
    return _deps().event_sources(analysis_out, **kwargs)


def _mapping_items(analysis_out: Path, **kwargs: Any) -> list[dict[str, Any]]:
    return _deps().mapping_items(analysis_out, **kwargs)


def _data_flow_items(analysis_out: Path, mappings: list[dict[str, Any]], **kwargs: Any) -> list[dict[str, Any]]:
    return _deps().data_flow_items(analysis_out, mappings, **kwargs)


def stored_data_access(analysis_out: Path, **kwargs: Any) -> dict[str, Any]:
    return _deps().stored_data_access(analysis_out, **kwargs)


def _db_schema_items(analysis_out: Path, name: str) -> list[dict[str, Any]]:
    return _deps().db_schema_items(analysis_out, name)


def _item_id(item: dict[str, Any]) -> str | None:
    if _CURRENT_DEPS is not None:
        return _deps().item_id(item)
    if not isinstance(item, dict):
        return None
    props = item.get("properties") if isinstance(item.get("properties"), dict) else item
    for key in (
        "source_to_storage_lineage_id", "storage_to_access_lineage_id", "stored_field_to_response_field_mapping_id",
        "persistent_write_id", "storage_access_id", "attribute_mapping_id", "attribute_derivation_id",
        "factory_method_mapping_id", "builder_field_mapping_id", "stream_collection_lineage_id",
        "jooq_batch_bind_mapping_id", "jooq_parameterized_sql_mapping_id", "mapstruct_mapper_signature_id",
        "id", "evidence_id",
    ):
        value = props.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _item_matches_blob(item: dict[str, Any], token: str) -> bool:
    return _deps().item_matches_blob(item, token)


def _locations_from_item(item: dict[str, Any]) -> list[dict[str, Any]]:
    if _CURRENT_DEPS is not None:
        return _deps().locations_from_item(item)
    props = _props(item) if isinstance(item, dict) else {}
    evs = (item.get("evidence") if isinstance(item, dict) else None) or props.get("evidence") or []
    out: list[dict[str, Any]] = []
    if isinstance(evs, list):
        for ev in evs:
            if not isinstance(ev, dict):
                continue
            out.append({k: ev.get(k) for k in ["file", "file_path", "line_start", "line_end", "extractor", "snippet"] if ev.get(k) is not None})
    return out


def _evidence_refs(item: dict[str, Any]) -> list[str]:
    return _deps().evidence_refs(item)


def _openspec_id(prefix: str, *parts: Any) -> str:
    return _deps().openspec_id(prefix, *parts)


def _props(item: dict[str, Any]) -> dict[str, Any]:
    if _CURRENT_DEPS is not None:
        return _deps().props(item)
    if isinstance(item, dict) and isinstance(item.get("properties"), dict):
        return item.get("properties") or {}
    return item if isinstance(item, dict) else {}


def _status_from_evidence_level(level: Any, *, default: str = "unresolved_static_analysis") -> str:
    return _deps().status_from_evidence_level(level, default=default)


def read_json(path: Path, default: Any = None) -> Any:
    return _deps().read_json(path, default)


def write_lazy(analysis_out: Path, kind: str, token: str, obj: dict[str, Any]) -> Any:
    return _deps().write_lazy(analysis_out, kind, token, obj)


_FDP_EXTERNAL_SOURCE_KINDS = {
    "rest", "http", "api", "rest_controller", "controller", "request_body",
    "kafka", "kafka_listener", "kafka_consumed", "message", "consumer",
}
_FDP_INTERNAL_SOURCE_HINTS = {
    "db", "database", "repository", "dao", "storage", "read_from_storage",
    "internal", "local", "generated", "constant", "default", "scheduler",
}
_FDP_RUNTIME_OBJECT_SUFFIXES = (
    "request", "req", "rq", "dto", "message", "event", "payload", "command", "body"
)
_FDP_PLACEHOLDER_TOKENS = {
    "", "unknown", "null", "none", "na", "n/a", "empty", "dao", "repository",
    "service", "test", "mock", "verify", "when", "doanswer", "never", "times",
}
_FDP_NOISY_FIELD_MARKERS = ("\n", "/**", "*/", "{", "}")
_FDP_TEST_MARKERS = (
    "/test/", "\\test\\", "src/test", "test/java", "test/resources", "mockito",
    "verify(", "verify_", "doanswer", "when(", ".when(", "times(", "never(",
    "junit", "assert", "mock", "stub",
)
_FDP_GENERATED_MARKERS = ("/generated/", "\\generated\\", "target/generated", "build/generated")
_FDP_NORM_RE = re.compile(r"[^a-z0-9]")


@functools.lru_cache(maxsize=200000)
def _fdp_norm_cached(value: str) -> str:
    return _FDP_NORM_RE.sub("", value.lower())


def _fdp_norm(value: Any) -> str:
    return _fdp_norm_cached(str(value or ""))


def _fdp_simple_name(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = text.split("<", 1)[0].split("[", 1)[0]
    text = text.rsplit(".", 1)[-1]
    return text


@functools.lru_cache(maxsize=1)
def _fdp_placeholder_norms() -> frozenset[str]:
    return frozenset(_fdp_norm(x) for x in _FDP_PLACEHOLDER_TOKENS)


def _fdp_is_placeholder(value: Any) -> bool:
    raw = str(value or "").strip()
    if not raw:
        return True
    return _fdp_norm(raw) in _fdp_placeholder_norms()


def _fdp_concrete_text(value: Any) -> str:
    text = str(value or "").strip()
    return "" if _fdp_is_placeholder(text) else text


def _fdp_tokens(*values: Any) -> set[str]:
    out: set[str] = set()
    for value in values:
        if value is None:
            continue
        if isinstance(value, (list, tuple, set)):
            for sub in value:
                out.update(_fdp_tokens(sub))
            continue
        raw = str(value).strip()
        if not raw or _fdp_is_placeholder(raw):
            continue
        for part in re.split(r"[\s,;:/|()]+", raw):
            if not part or _fdp_is_placeholder(part):
                continue
            placeholder_norms = _fdp_placeholder_norms()
            norm = _fdp_norm(part)
            if norm and norm not in placeholder_norms:
                out.add(norm)
            simple = _fdp_norm(_fdp_simple_name(part))
            if simple and simple not in placeholder_norms:
                out.add(simple)
    return {x for x in out if x}


def _fdp_source_scope(item: Any) -> str:
    if item is None:
        return "unknown"
    props = _props(item) if isinstance(item, dict) else {}
    explicit = str(props.get("source_scope") or props.get("scope") or props.get("code_scope") or "").lower()
    if explicit in {"production_code", "test_code", "generated_code", "unknown"}:
        return explicit
    texts: list[str] = []
    if isinstance(item, dict):
        texts.append(json.dumps(item, ensure_ascii=False, default=str).lower())
        for ev in _locations_from_item(item):
            texts.append(str(ev.get("file") or ev.get("file_path") or "").lower())
            texts.append(str(ev.get("snippet") or "").lower())
    else:
        texts.append(str(item).lower())
    blob = "\n".join(texts)
    if any(marker in blob for marker in _FDP_TEST_MARKERS):
        return "test_code"
    if any(marker in blob for marker in _FDP_GENERATED_MARKERS):
        return "generated_code"
    if blob:
        return "production_code"
    return "unknown"


def _fdp_scope_summary(scopes: list[str]) -> dict[str, Any]:
    counts = {"production_code": 0, "test_code": 0, "generated_code": 0, "unknown": 0}
    for scope in scopes:
        counts[scope if scope in counts else "unknown"] += 1
    dominant = max(counts, key=lambda k: counts[k]) if any(counts.values()) else "unknown"
    if counts["production_code"] > 0:
        dominant = "production_code"
    elif counts["test_code"] > 0 and counts["generated_code"] == 0:
        dominant = "test_code"
    return {
        "has_production_evidence": counts["production_code"] > 0,
        "has_test_evidence": counts["test_code"] > 0,
        "has_generated_evidence": counts["generated_code"] > 0,
        "has_unknown_scope_evidence": counts["unknown"] > 0,
        "dominant_scope": dominant,
        "counts": counts,
    }

def _fdp_is_inbound_event(event: dict[str, Any]) -> bool:
    direction = str(event.get("direction") or "").lower()
    kind = str(event.get("kind") or event.get("source_kind") or "").lower()
    blob = json.dumps(event, ensure_ascii=False, default=str).lower()
    if direction == "inbound" and kind in {"rest", "kafka"}:
        return True
    return direction == "inbound" and any(x in blob for x in ["controller", "requestmapping", "kafkalistener", "listener"])


def _fdp_event_ref(event: dict[str, Any], *, reason: str) -> dict[str, Any]:
    return {
        k: event.get(k)
        for k in [
            "event_source_id", "interface_id", "ingress_id", "operation_id", "kind", "source_kind",
            "direction", "operation", "class_name", "method_name", "endpoint_or_topic",
            "endpoint_path", "topic_name", "request_type", "payload_type", "payload_parameter", "evidence_level",
        ]
        if event.get(k) is not None
    } | {"match_reason": reason}


def _fdp_related_events(sp: dict[str, Any], event_sources: list[dict[str, Any]], *, max_results: int = 10) -> list[dict[str, Any]]:
    source_payload = _fdp_concrete_text(sp.get("source_payload") or sp.get("source_object"))
    operation = _fdp_concrete_text(sp.get("operation") or sp.get("terminal_operation_id") or sp.get("ingress_operation_id"))
    source_kind = _fdp_concrete_text(sp.get("origin_kind") or sp.get("source_kind") or "")
    source_tokens = _fdp_tokens(source_payload, operation)
    related: list[dict[str, Any]] = []
    seen: set[str] = set()
    for ev in event_sources:
        if _fdp_source_scope(ev) == "test_code":
            continue
        if not _fdp_is_inbound_event(ev):
            continue
        reasons: list[str] = []
        ev_payload = _fdp_concrete_text(ev.get("request_type") or ev.get("payload_type"))
        if source_payload and ev_payload and _fdp_norm(source_payload) == _fdp_norm(ev_payload):
            reasons.append("source_payload_matches_inbound_event_payload")
        ev_operation = _fdp_concrete_text(ev.get("operation") or "")
        if operation and ev_operation and str(operation) == str(ev_operation):
            reasons.append("operation_matches_inbound_event")
        elif operation and ev_operation and (_fdp_norm(operation) in _fdp_norm(ev_operation) or _fdp_norm(ev_operation) in _fdp_norm(operation)):
            reasons.append("operation_name_overlaps_inbound_event")
        # Do not use generic source kind alone (rest/kafka/controller) as a relation. It is evidence only
        # when coupled with a concrete operation/payload/object match.
        ev_tokens = _fdp_tokens(ev_payload, ev.get("operation"), ev.get("class_name"), ev.get("method_name"), ev.get("endpoint_or_topic"), ev.get("endpoint_path"), ev.get("topic_name"))
        shared = source_tokens.intersection(ev_tokens) if source_tokens and ev_tokens else set()
        if shared:
            reasons.append("source_tokens_overlap_inbound_event")
        if not reasons:
            continue
        ref_id = str(ev.get("event_source_id") or ev.get("interface_id") or ev.get("ingress_id") or ev.get("operation") or len(related))
        if ref_id in seen:
            continue
        seen.add(ref_id)
        related.append(_fdp_event_ref(ev, reason=", ".join(dict.fromkeys(reasons))))
        if len(related) >= max_results:
            break
    return related


def _fdp_op_class(value: Any) -> str | None:
    text = _fdp_concrete_text(value)
    if not text or "." not in text:
        return None
    return text.rsplit(".", 1)[0]


def _fdp_op_method(value: Any) -> str | None:
    text = _fdp_concrete_text(value)
    if not text:
        return None
    return text.rsplit(".", 1)[-1]


def _fdp_class_matches(candidate: Any, expected: Any) -> bool:
    cn = _fdp_norm(_fdp_simple_name(candidate))
    en = _fdp_norm(_fdp_simple_name(expected))
    if not cn or not en:
        return False
    return cn == en or cn.endswith(en) or en.endswith(cn)


def _fdp_operation_matches(candidate: Any, expected: Any) -> bool:
    cn = _fdp_norm(candidate)
    en = _fdp_norm(expected)
    if not cn or not en:
        return False
    return cn == en or cn.endswith(en) or en.endswith(cn)


def _fdp_event_matches_operation(ev: dict[str, Any], operation: Any) -> bool:
    ev_operation = _fdp_concrete_text(ev.get("operation") or ev.get("operation_id"))
    if ev_operation and _fdp_operation_matches(ev_operation, operation):
        return True
    ev_class = _fdp_concrete_text(ev.get("class_name")) or _fdp_op_class(ev_operation)
    ev_method = _fdp_concrete_text(ev.get("method_name")) or _fdp_op_method(ev_operation)
    op_class = _fdp_op_class(operation)
    op_method = _fdp_op_method(operation)
    return bool(ev_class and ev_method and op_class and op_method and _fdp_class_matches(ev_class, op_class) and _fdp_norm(ev_method) == _fdp_norm(op_method))


def _fdp_binding_matches_event_payload(binding: dict[str, Any], ev: dict[str, Any]) -> bool:
    ev_payload = _fdp_concrete_text(ev.get("payload_type") or ev.get("request_type"))
    ev_param = _fdp_concrete_text(ev.get("payload_parameter"))
    source_param = _fdp_concrete_text(binding.get("caller_source_parameter"))
    source_type = _fdp_concrete_text(binding.get("source_type"))
    caller_expr = _fdp_concrete_text(binding.get("caller_expression"))
    if ev_param and source_param and _fdp_norm(ev_param) == _fdp_norm(source_param):
        return True
    if ev_payload and source_type and _fdp_class_matches(ev_payload, source_type):
        return True
    if ev_param and caller_expr and _fdp_norm(ev_param) == _fdp_norm(caller_expr):
        return True
    return False


def _fdp_call_payload_continues(binding: dict[str, Any], previous_parameter: str | None, previous_type: str | None) -> bool:
    caller_source = _fdp_concrete_text(binding.get("caller_source_parameter"))
    caller_expr = _fdp_concrete_text(binding.get("caller_expression"))
    source_type = _fdp_concrete_text(binding.get("source_type"))
    if previous_parameter and (caller_source and _fdp_norm(caller_source) == _fdp_norm(previous_parameter)):
        return True
    if previous_parameter and (caller_expr and _fdp_norm(caller_expr) == _fdp_norm(previous_parameter)):
        return True
    if previous_type and source_type and _fdp_class_matches(previous_type, source_type):
        return True
    return False


def _fdp_evaluate_call_path_payload(ev: dict[str, Any], forward_edges: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]], bool]:
    """Evaluate best-effort payload propagation along a call path.

    This remains candidate evidence. A path is useful only when the first hop
    starts from the inbound operation and the payload parameter/type can be
    followed through subsequent caller->callee argument bindings.
    """
    chosen_bindings: list[dict[str, Any]] = []
    previous_parameter: str | None = None
    previous_type: str | None = None
    has_alias = False
    for idx, edge in enumerate(forward_edges):
        bindings = [b for b in _fdp_list(edge.get("argument_bindings")) if isinstance(b, dict)]
        if not bindings:
            return "candidate_call_path_payload_argument_unmatched", chosen_bindings, has_alias
        if idx == 0:
            candidates = [b for b in bindings if _fdp_binding_matches_event_payload(b, ev)]
        else:
            candidates = [b for b in bindings if _fdp_call_payload_continues(b, previous_parameter, previous_type)]
        if not candidates:
            return "candidate_call_path_payload_argument_unmatched", chosen_bindings, has_alias
        candidates = sorted(candidates, key=lambda b: (str(b.get("relation") or "") != "same_object", -float(b.get("binding_strength") or 0)))
        chosen = candidates[0]
        chosen_bindings.append(chosen)
        previous_parameter = _fdp_concrete_text(chosen.get("callee_parameter")) or previous_parameter
        previous_type = _fdp_concrete_text(chosen.get("target_type") or chosen.get("source_type")) or previous_type
        if chosen.get("via_local_variable") or chosen.get("alias_via") or int(chosen.get("alias_depth") or 0) > 0:
            has_alias = True
    return "candidate_payload_argument_match", chosen_bindings, has_alias


def _fdp_find_multi_hop_call_paths(
    operation: str,
    event_sources: list[dict[str, Any]],
    method_calls: list[dict[str, Any]],
    *,
    method_call_index: dict[str, Any] | None = None,
    max_depth: int = 4,
    max_paths: int = 20,
    max_edges_per_node: int = 50,
    max_visited_nodes: int = 500,
) -> list[dict[str, Any]]:
    if method_call_index is None:
        method_call_index = _fdp_build_method_call_index(method_calls or [], event_sources or [])
    inbound_events = method_call_index.get("inbound_events") or []
    found: list[dict[str, Any]] = []

    visited_states: set[tuple[str, int]] = set()

    def incoming_edges_for(target_operation: str) -> list[dict[str, Any]]:
        return _fdp_indexed_incoming_edges_for(target_operation, method_call_index, max_edges_per_node=max_edges_per_node)

    def dfs(target_operation: str, reverse_path: list[dict[str, Any]], seen_ops: set[str]) -> None:
        if len(found) >= max_paths or len(reverse_path) >= max_depth or len(visited_states) >= max_visited_nodes:
            return
        state = (target_operation, len(reverse_path))
        if state in visited_states:
            return
        visited_states.add(state)
        for edge in incoming_edges_for(target_operation):
            caller = str(edge.get("caller_operation") or "")
            if not caller or caller in seen_ops:
                continue
            new_reverse = [edge, *reverse_path]
            for ev in inbound_events:
                if not _fdp_event_matches_operation(ev, caller):
                    continue
                status, chosen_bindings, has_alias = _fdp_evaluate_call_path_payload(ev, new_reverse)
                # For multi-hop paths do not create origin evidence when the payload
                # cannot be followed. Class-only paths are still covered by Spring/template hints.
                if status != "candidate_payload_argument_match":
                    continue
                call_ids = _fdp_unique_strings([e.get("call_id") for e in new_reverse])
                found.append({
                    "event": ev,
                    "call_ids": call_ids,
                    "argument_propagation_status": status,
                    "has_payload_alias_propagation": has_alias,
                    "hops": [
                        {
                            "call_id": e.get("call_id"),
                            "caller_operation": e.get("caller_operation"),
                            "callee_operation": e.get("callee_operation"),
                            "resolution_kind": e.get("resolution_kind"),
                            "argument_binding": chosen_bindings[i] if i < len(chosen_bindings) else None,
                        }
                        for i, e in enumerate(new_reverse)
                    ],
                })
            dfs(caller, new_reverse, {caller, *seen_ops})

    dfs(operation, [], {operation})
    return found[:max_paths]


def _fdp_related_events_via_call_hints(
    sp: dict[str, Any],
    event_sources: list[dict[str, Any]],
    *,
    spring_dependencies: list[dict[str, Any]],
    template_dispatches: list[dict[str, Any]],
    method_calls: list[dict[str, Any]] | None = None,
    method_call_index: dict[str, Any] | None = None,
    max_results: int = 10,
) -> list[dict[str, Any]]:
    """Candidate ingress links through source-level call/template hints.

    These hints are intentionally navigation-only.  They can make the source
    side more explainable (controller/listener -> service/handler/DAO path), but
    they do not confirm field-level source-to-storage lineage or business risk.
    """
    operation = _fdp_concrete_text(sp.get("operation") or sp.get("storage_operation") or sp.get("source_operation"))
    op_class = _fdp_op_class(operation) or _fdp_concrete_text(sp.get("class_name"))
    if not operation and not op_class:
        return []
    related: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(ev: dict[str, Any], reason: str, hint_ref: Any = None, extra: dict[str, Any] | None = None) -> None:
        if len(related) >= max_results:
            return
        hint_refs = _fdp_unique_strings(_fdp_list(hint_ref))
        ref_id = str(ev.get("event_source_id") or ev.get("interface_id") or ev.get("ingress_id") or ev.get("operation") or len(related))
        key = f"{ref_id}:{reason}:{'|'.join(hint_refs)}"
        if key in seen:
            return
        seen.add(key)
        item = _fdp_event_ref(ev, reason=reason)
        item["match_basis"] = "candidate_call_graph_hint"
        item["hint_refs"] = hint_refs
        if extra:
            item.update({k: v for k, v in extra.items() if v not in (None, [], {})})
        related.append(item)

    # Prefer concrete method-call evidence when available. This connects
    # Controller/Listener payload arguments to downstream service/DAO operations
    # and is stronger than class-level Spring dependency hints, but still
    # candidate until field-level storage mapping is confirmed.
    if method_call_index is None:
        method_call_index = _fdp_build_method_call_index(method_calls or [], event_sources or [])
    inbound_events = method_call_index.get("inbound_events") or []
    for cp in _fdp_indexed_incoming_edges_for(operation, method_call_index, max_edges_per_node=50) if operation else []:
        callee = _fdp_concrete_text(cp.get("callee_operation_id") or cp.get("callee_method") or cp.get("callee_operation"))
        caller = _fdp_concrete_text(cp.get("caller_operation_id") or cp.get("caller_method") or cp.get("caller_operation"))
        if not (callee and caller and operation and _fdp_operation_matches(callee, operation)):
            continue
        bindings = [b for b in _fdp_list(cp.get("argument_bindings")) if isinstance(b, dict)]
        for ev in inbound_events:
            if not _fdp_event_matches_operation(ev, caller):
                continue
            matching_bindings = [b for b in bindings if _fdp_binding_matches_event_payload(b, ev)]
            if not matching_bindings and bindings:
                # Keep the call path as navigation evidence, but make the missing
                # payload argument match explicit.
                matching_bindings = []
            extra = {
                "call_path": {
                    "caller_operation": caller,
                    "callee_operation": callee,
                    "call_id": cp.get("call_id") or _item_id(cp),
                    "resolution_kind": cp.get("resolution_kind"),
                    "argument_bindings": matching_bindings[:5],
                    "argument_propagation_status": "candidate_payload_argument_match" if matching_bindings else "candidate_call_path_payload_argument_unmatched",
                }
            }
            add(ev, "candidate_call_path_via_argument_binding", str(cp.get("call_id") or _item_id(cp) or ""), extra=extra)

    # Multi-hop method-call path: Controller/Listener -> Facade -> Service/Handler -> write operation.
    # Requires argument propagation along every hop to avoid turning class reachability into source proof.
    if operation and method_calls:
        for path in _fdp_find_multi_hop_call_paths(operation, event_sources, method_calls, method_call_index=method_call_index, max_depth=4, max_paths=max_results):
            ev = path.get("event") or {}
            call_ids = _fdp_list(path.get("call_ids"))
            extra = {
                "call_path": {
                    "path_kind": "multi_hop_method_call_argument_path",
                    "caller_operation": (path.get("hops") or [{}])[0].get("caller_operation"),
                    "callee_operation": (path.get("hops") or [{}])[-1].get("callee_operation"),
                    "call_ids": call_ids,
                    "hop_count": len(path.get("hops") or []),
                    "hops": (path.get("hops") or [])[:6],
                    "argument_propagation_status": path.get("argument_propagation_status"),
                    "has_payload_alias_propagation": bool(path.get("has_payload_alias_propagation")),
                }
            }
            add(ev, "candidate_multi_hop_call_path_via_argument_binding", call_ids, extra=extra)

    for ev in event_sources:
        if _fdp_source_scope(ev) == "test_code" or not _fdp_is_inbound_event(ev):
            continue
        ev_operation = _fdp_concrete_text(ev.get("operation") or "")
        ev_class = _fdp_concrete_text(ev.get("class_name")) or _fdp_op_class(ev_operation)
        if not ev_operation and not ev_class:
            continue

        for dep in spring_dependencies:
            if _fdp_source_scope(dep) == "test_code":
                continue
            dp = _props(dep)
            source_class = dp.get("source_class")
            declared_type = dp.get("declared_type")
            impls = _fdp_list(dp.get("candidate_implementations"))
            dep_targets = _fdp_unique_strings([declared_type] + impls)
            if ev_class and source_class and _fdp_class_matches(ev_class, source_class) and any(_fdp_class_matches(op_class, target) for target in dep_targets):
                add(ev, "candidate_call_path_via_spring_component_dependency", str(dp.get("spring_component_dependency_id") or _item_id(dep) or ""))
                break

        for disp in template_dispatches:
            if _fdp_source_scope(disp) == "test_code":
                continue
            tp = _props(disp)
            override_op = _fdp_concrete_text(tp.get("override_operation"))
            templates = [_fdp_concrete_text(x) for x in _fdp_list(tp.get("candidate_template_operations"))]
            override_matches = bool(operation and override_op and (operation == override_op or _fdp_norm(operation) == _fdp_norm(override_op)))
            template_matches = bool(ev_operation and any(t and (ev_operation == t or _fdp_norm(ev_operation) == _fdp_norm(t)) for t in templates))
            if override_matches and template_matches:
                add(ev, "candidate_call_path_via_template_method_dispatch", str(tp.get("template_method_dispatch_id") or _item_id(disp) or ""))
                break
    return related



def _fdp_build_method_call_index(method_calls: list[dict[str, Any]], event_sources: list[dict[str, Any]]) -> dict[str, Any]:
    """Build reusable bounded call indexes for FDP case materialization.

    Full traceability runs can contain thousands of method_call facts.  FDP
    cases are grouped by write/storage boundary, but source interpretation is
    evaluated per case.  Rebuilding the method-call edge list and inbound-event
    filter for every case makes the derived view much slower than the analyzer
    run itself.  The index is a pure presentation optimization: it does not add
    new evidence or change confidence semantics.
    """
    edges: list[dict[str, Any]] = []
    incoming: dict[str, list[dict[str, Any]]] = {}
    for call in method_calls or []:
        if _fdp_source_scope(call) == "test_code":
            continue
        cp = _props(call)
        caller = _fdp_concrete_text(cp.get("caller_operation_id") or cp.get("caller_method"))
        callee = _fdp_concrete_text(cp.get("callee_operation_id") or cp.get("callee_method"))
        if not caller or not callee:
            continue
        edge = {
            **cp,
            "caller_operation": caller,
            "callee_operation": callee,
            "call_id": cp.get("call_id") or _item_id(call),
        }
        edges.append(edge)
        incoming.setdefault(callee, []).append(edge)
    inbound_events = [
        ev for ev in (event_sources or [])
        if _fdp_source_scope(ev) != "test_code" and _fdp_is_inbound_event(ev)
    ]
    return {
        "edges": edges,
        "incoming": incoming,
        "fallback_cache": {},
        "inbound_events": inbound_events,
        "edge_count": len(edges),
        "inbound_event_count": len(inbound_events),
    }


def _fdp_indexed_incoming_edges_for(
    target_operation: str,
    method_call_index: dict[str, Any] | None,
    *,
    max_edges_per_node: int = 50,
) -> list[dict[str, Any]]:
    if not method_call_index:
        return []
    incoming = method_call_index.get("incoming") or {}
    exact = incoming.get(target_operation) or []
    if exact:
        return exact[:max_edges_per_node]
    fallback_cache = method_call_index.setdefault("fallback_cache", {})
    if target_operation not in fallback_cache:
        matched: list[dict[str, Any]] = []
        for edge in method_call_index.get("edges") or []:
            if _fdp_operation_matches(edge.get("callee_operation"), target_operation):
                matched.append(edge)
                if len(matched) >= max_edges_per_node:
                    break
        fallback_cache[target_operation] = matched
    return fallback_cache[target_operation][:max_edges_per_node]

def _fdp_related_object_mappings(sp: dict[str, Any], mappings: list[dict[str, Any]], *, max_results: int = 20) -> list[dict[str, Any]]:
    source_payload = _fdp_concrete_text(sp.get("source_payload") or sp.get("source_object"))
    saved_object = _fdp_concrete_text(sp.get("saved_object") or sp.get("storage_target") or sp.get("storage_object"))
    if not source_payload and not saved_object:
        return []
    source_norm = _fdp_norm(source_payload)
    saved_norm = _fdp_norm(saved_object)
    related: list[dict[str, Any]] = []
    for m in mappings:
        if _fdp_source_scope(m) == "test_code":
            continue
        ms_raw = _fdp_concrete_text(m.get("source_object"))
        mt_raw = _fdp_concrete_text(m.get("target_object"))
        ms = _fdp_norm(ms_raw)
        mt = _fdp_norm(mt_raw)
        if not ms and not mt:
            continue
        reasons = []
        if source_norm and source_norm in {ms, mt}:
            reasons.append("source_payload_object_participates_in_mapping")
        if saved_norm and saved_norm in {ms, mt}:
            reasons.append("saved_object_or_storage_participates_in_mapping")
        if source_norm and saved_norm and ms == source_norm and mt == saved_norm:
            reasons.append("direct_source_object_to_saved_object_mapping")
        if not reasons:
            continue
        related.append({
            "mapping_id": m.get("mapping_id"),
            "source_object": m.get("source_object"),
            "target_object": m.get("target_object"),
            "mapping_type": m.get("mapping_type"),
            "evidence_level": m.get("evidence_level"),
            "match_reason": ", ".join(dict.fromkeys(reasons)),
        })
        if len(related) >= max_results:
            break
    return related

def _fdp_object_role(value: Any) -> str | None:
    simple = _fdp_simple_name(value)
    norm = _fdp_norm(simple)
    if not norm:
        return None
    if any(norm.endswith(suffix) for suffix in _FDP_RUNTIME_OBJECT_SUFFIXES):
        return "runtime_payload_object"
    if any(x in norm for x in ["entity", "record", "jooq", "table"]):
        return "persistence_object"
    return None


def _fdp_source_interpretation(
    sp: dict[str, Any],
    *,
    event_sources: list[dict[str, Any]],
    mappings: list[dict[str, Any]],
    spring_dependencies: list[dict[str, Any]] | None = None,
    template_dispatches: list[dict[str, Any]] | None = None,
    method_calls: list[dict[str, Any]] | None = None,
    method_call_index: dict[str, Any] | None = None,
) -> dict[str, Any]:
    source_payload_raw = sp.get("source_payload") or sp.get("source_object")
    saved_object_raw = sp.get("saved_object") or sp.get("storage_target") or sp.get("storage_object")
    source_payload = _fdp_concrete_text(source_payload_raw)
    saved_object = _fdp_concrete_text(saved_object_raw)
    source_kind = str(sp.get("origin_kind") or sp.get("source_kind") or "").lower()
    source_kind_concrete = _fdp_concrete_text(source_kind)
    lineage_status = str(sp.get("lineage_status") or sp.get("trace_status") or sp.get("evidence_level") or "").lower()
    related_events = _fdp_related_events(sp, event_sources)
    call_hint_events = _fdp_related_events_via_call_hints(
        sp,
        event_sources,
        spring_dependencies=spring_dependencies or [],
        template_dispatches=template_dispatches or [],
        method_calls=method_calls or [],
        method_call_index=method_call_index,
        max_results=max(0, 10 - len(related_events)),
    )
    if call_hint_events:
        existing_by_key = {str(x.get("event_source_id") or x.get("interface_id") or x.get("operation") or x.get("endpoint_or_topic") or x): x for x in related_events}
        for ev in call_hint_events:
            key = str(ev.get("event_source_id") or ev.get("interface_id") or ev.get("operation") or ev.get("endpoint_or_topic") or ev)
            if key in existing_by_key:
                existing = existing_by_key[key]
                existing["match_reason"] = ", ".join(dict.fromkeys(_fdp_list(existing.get("match_reason")) + _fdp_list(ev.get("match_reason"))))
                existing["hint_refs"] = _fdp_unique_strings(_fdp_list(existing.get("hint_refs")) + _fdp_list(ev.get("hint_refs")))
                existing["match_basis"] = "candidate_call_graph_hint" if ev.get("match_basis") else existing.get("match_basis")
                if ev.get("call_path") and not existing.get("call_path"):
                    existing["call_path"] = ev.get("call_path")
            else:
                related_events.append(ev)
                existing_by_key[key] = ev
    related_mappings = _fdp_related_object_mappings(sp, mappings)
    signals: list[str] = []
    not_proven: list[str] = []
    discarded: list[str] = []
    status = "unknown_origin"
    confidence = "low"

    if source_payload_raw and not source_payload:
        discarded.append("placeholder_source_payload_discarded")
        not_proven.append("source_payload_unknown")
    if saved_object_raw and not saved_object:
        discarded.append("placeholder_saved_object_or_storage_discarded")
    source_role = _fdp_object_role(source_payload)
    if source_payload:
        signals.append(f"source payload/object observed: {source_payload}")
        if source_role == "runtime_payload_object":
            signals.append("source object name looks like runtime request/message payload")
    if source_kind_concrete:
        signals.append(f"source kind observed: {source_kind_concrete}")
    if related_events:
        signals.append("related inbound REST/Kafka event source candidate found")
        if any((ev.get("call_path") or {}).get("argument_propagation_status") for ev in related_events):
            signals.append("candidate ingress payload argument propagation to downstream write operation found")
    if related_mappings:
        signals.append("object-level source/saved-object mapping candidate found")
    if saved_object:
        signals.append(f"saved object/storage target observed: {saved_object}")

    kind_tokens = _fdp_tokens(source_kind_concrete)
    external_kind = bool(kind_tokens.intersection(_FDP_EXTERNAL_SOURCE_KINDS)) or any(x in source_kind_concrete for x in ["rest", "kafka", "controller", "listener", "request", "message"])
    internal_kind = bool(kind_tokens.intersection(_FDP_INTERNAL_SOURCE_HINTS)) or any(x in source_kind_concrete for x in ["generated", "constant", "internal", "database", "repository", "dao"])
    concrete_ingress_link = bool(related_events and (source_payload or any("operation_" in str(ev.get("match_reason") or "") or "operation_matches" in str(ev.get("match_reason") or "") or "call_path" in str(ev.get("match_reason") or "") for ev in related_events)))

    if external_kind and concrete_ingress_link and "confirmed" in lineage_status:
        status = "confirmed_external_ingress"
    elif external_kind and concrete_ingress_link:
        status = "external_ingress_candidate"
    elif concrete_ingress_link:
        status = "external_ingress_candidate"
    elif source_role == "runtime_payload_object":
        status = "runtime_input_candidate"
    elif source_payload:
        status = "runtime_input_candidate"
    else:
        status = "unknown_origin"
    if internal_kind and not concrete_ingress_link and not external_kind:
        status = "internal_generated_or_local_candidate"

    if status in {"confirmed_external_ingress", "external_ingress_candidate", "runtime_input_candidate", "unknown_origin"}:
        not_proven.append("exact upstream business system is not identified by static analysis")
    if status != "confirmed_external_ingress":
        not_proven.append("complete source-to-persistence lineage is not confirmed")
    if related_mappings and not any(str(m.get("evidence_level") or "").lower() == "confirmed_by_analyzer" for m in related_mappings):
        not_proven.append("field-level source-to-storage mapping remains incomplete")
    elif not related_mappings:
        not_proven.append("object/field mapping between source payload and saved object is not fully materialized in this view")
    if discarded:
        not_proven.extend(discarded)

    return {
        "status": status,
        "business_source_decision": "not_made_by_analyzer",
        "interpretation_scope": "coarse_static_evidence_over_concrete_ingress_reachability_and_object_mapping; placeholder tokens are ignored; not a business ownership decision",
        "source_payload": source_payload_raw,
        "source_payload_concrete": source_payload or None,
        "saved_object_or_storage": saved_object_raw,
        "saved_object_or_storage_concrete": saved_object or None,
        "source_kind": sp.get("origin_kind") or sp.get("source_kind"),
        "lineage_status": sp.get("lineage_status") or sp.get("trace_status") or sp.get("evidence_level"),
        "signals": signals[:20],
        "discarded_signals": list(dict.fromkeys(discarded)),
        "related_inbound_event_sources": related_events,
        "related_object_mappings": related_mappings,
        "not_proven": list(dict.fromkeys(not_proven)),
    }

def _fdp_source_origin_summary(cases: list[dict[str, Any]]) -> dict[str, Any]:
    by_status: dict[str, int] = {}
    with_access_by_status: dict[str, int] = {}
    for case in cases:
        interp = case.get("source_interpretation") or {}
        status = str(interp.get("status") or "unknown_origin")
        by_status[status] = by_status.get(status, 0) + 1
        if ((case.get("external_access") or {}).get("status") == "observed_in_code"):
            with_access_by_status[status] = with_access_by_status.get(status, 0) + 1
    return {
        "total_cases": len(cases),
        "by_source_interpretation_status": by_status,
        "with_external_access_by_source_interpretation_status": with_access_by_status,
        "decision_policy": "Analyzer reports coarse source/origin interpretation only. It does not decide whether an ingress belongs to another business system.",
    }



def _fdp_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _fdp_unique_strings(values: list[Any]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def _fdp_storage_values(props: dict[str, Any]) -> list[str]:
    values: list[Any] = []
    for key in [
        "storage_target", "storage_object", "target_table", "qualified_table", "table_name",
        "saved_object", "storage_symbol", "source_storage_object", "read_type", "target_object",
    ]:
        for raw_value in _fdp_list(props.get(key)):
            if not _fdp_is_placeholder(raw_value):
                values.append(raw_value)
    return _fdp_unique_strings(values)


def _fdp_storage_matches(a: Any, b: Any) -> bool:
    an = _fdp_norm(a)
    bn = _fdp_norm(b)
    if not an or not bn:
        return False
    return an == bn or an.endswith(bn) or bn.endswith(an)


def _fdp_storage_candidate_matches(a: Any, b: Any) -> bool:
    if _fdp_storage_matches(a, b):
        return True
    at = _fdp_tokens(a)
    bt = _fdp_tokens(b)
    return bool(at and bt and at.intersection(bt))


def _fdp_match_persistent_writes(sp: dict[str, Any], writes: list[dict[str, Any]]) -> dict[str, Any]:
    direct_refs = _fdp_unique_strings([
        sp.get("persistent_write_id"), sp.get("write_evidence_ref"), sp.get("write_id"), sp.get("storage_write_ref"),
    ])
    confirmed: list[str] = []
    candidate: list[str] = []
    confirmed_reasons: dict[str, str] = {}
    candidate_reasons: dict[str, str] = {}
    src_storage_values = _fdp_storage_values(sp)
    src_refs = set(_evidence_refs(sp)) if isinstance(sp, dict) else set()

    write_by_id: dict[str, dict[str, Any]] = {}
    for w in writes:
        wid = _item_id(w)
        if wid:
            write_by_id[wid] = w

    for ref in direct_refs:
        if ref in write_by_id:
            confirmed.append(ref)
            confirmed_reasons[ref] = "direct persistent_write_id/write_evidence_ref from source_to_storage_lineage"
        elif ref:
            candidate.append(ref)
            candidate_reasons[ref] = "direct write reference present in lineage but write fact was not materialized in the current view"

    for w in writes:
        if _fdp_source_scope(w) == "test_code":
            continue
        wid = _item_id(w)
        if not wid or wid in confirmed or wid in candidate:
            continue
        wp = _props(w)
        w_refs = set(_evidence_refs(w))
        if src_refs and w_refs and src_refs.intersection(w_refs):
            confirmed.append(wid)
            confirmed_reasons[wid] = "evidence_refs overlap between source_to_storage_lineage and persistent_write"
            continue

        write_storage_values = _fdp_storage_values(wp)
        exact_storage = any(_fdp_storage_matches(sv, wv) for sv in src_storage_values for wv in write_storage_values)
        if exact_storage:
            # Table/storage-only matching is intentionally candidate, not confirmed: multiple writes can target
            # the same table and only a direct ref/provenance/source overlap can safely confirm the operation.
            candidate.append(wid)
            candidate_reasons[wid] = "storage target/object exact match only; treated as candidate because multiple writes may target the same storage"
            continue

        write_blob = json.dumps(wp, ensure_ascii=False, default=str).lower()
        text_values = [_fdp_concrete_text(v) for v in [sp.get("operation"), sp.get("terminal_operation_id"), sp.get("saved_object")]]
        if any(v and str(v).lower() in write_blob for v in text_values):
            candidate.append(wid)
            candidate_reasons[wid] = "operation/saved-object text overlaps persistent_write"
            continue
        if any(_fdp_storage_candidate_matches(sv, wv) for sv in src_storage_values for wv in write_storage_values):
            candidate.append(wid)
            candidate_reasons[wid] = "storage target/object token overlap between source_to_storage_lineage and persistent_write"

    confirmed = _fdp_unique_strings(confirmed)
    overlap = [x for x in _fdp_unique_strings(candidate) if x not in set(confirmed)]
    observations = [
        {"persistent_write_ref": ref, "observation_kind": "direct_reference_or_shared_evidence_ref", "basis": reason}
        for ref, reason in confirmed_reasons.items()
    ]
    observations.extend(
        {"persistent_write_ref": ref, "observation_kind": "identifier_or_text_overlap", "basis": reason}
        for ref, reason in candidate_reasons.items()
        if ref not in set(confirmed)
    )
    return {
        "persistent_write_refs": confirmed,
        "overlap_persistent_write_refs": overlap,
        "persistent_write_observations": observations,
        "persistent_write_fact_found": bool(confirmed or overlap),
    }


def _fdp_field_quality(value: Any) -> tuple[bool, str | None]:
    text = str(value or "").strip()
    if not text:
        return False, "empty_field_name"
    if _fdp_is_placeholder(text):
        return False, "placeholder_field_name"
    if any(marker in text for marker in _FDP_NOISY_FIELD_MARKERS):
        return False, "code_or_comment_fragment"
    if ";" in text or "(" in text or ")" in text:
        return False, "code_fragment_character"
    if len(text) < 2 or len(text) > 180:
        return False, "field_name_length_out_of_range"
    # Allow qualified identifiers, quoted identifiers and common DB column naming; reject obvious snippets.
    if not re.match(r'^[A-Za-z_][A-Za-z0-9_$]*(?:[.][A-Za-z_][A-Za-z0-9_$]*)*$', text):
        if not re.match(r'^[A-Za-z_][A-Za-z0-9_$]*(?:_[A-Za-z0-9_$]+)*$', text):
            return False, "not_identifier_like"
    return True, None


def _fdp_filter_field_attr(attr: dict[str, Any], *, role: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    out = dict(attr)
    rejected: list[dict[str, str]] = []
    for key in ["storage_attribute", "source_attribute", "response_attribute"]:
        value = out.get(key)
        if value is None:
            continue
        ok, reason = _fdp_field_quality(value)
        if not ok:
            rejected.append({"field_role": key, "value": str(value), "reason": reason or "invalid_field_name"})
            out[key] = None
    if rejected:
        if not out.get("storage_attribute") and not out.get("response_attribute"):
            return None, {"attribute_role": role, "rejected_fields": rejected, "evidence_refs": out.get("evidence_refs") or []}
        out["field_quality"] = "partially_noisy"
        out["rejected_fields"] = rejected
        if out.get("mapping_status") == "confirmed":
            out["mapping_status"] = "candidate"
    else:
        out["field_quality"] = "accepted"
    return out, None

def _fdp_field_values_from_any(value: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in _fdp_list(value):
        if item is None:
            continue
        if isinstance(item, dict):
            storage = item.get("storage_attribute") or item.get("storage_field") or item.get("target_attribute") or item.get("target_field") or item.get("column") or item.get("field") or item.get("name")
            source = item.get("source_attribute") or item.get("source_field")
            out.append({
                "storage_attribute": storage,
                "source_attribute": source,
                "source_object": item.get("source_object") or item.get("source_container"),
                "saved_object": item.get("saved_object") or item.get("target_object") or item.get("target_container"),
                "mapping_status": item.get("mapping_status") or item.get("evidence_level") or "candidate",
                "mapping_kind": item.get("mapping_kind") or item.get("mapping_type") or item.get("assignment_kind"),
                "evidence_policy": item.get("evidence_policy"),
                "lineage_hint_kind": item.get("lineage_hint_kind") or item.get("hint_kind"),
                "hint_refs": _fdp_unique_strings(_fdp_list(item.get("hint_refs"))),
                "evidence_refs": _fdp_unique_strings(_fdp_list(item.get("evidence_refs"))),
            })
        else:
            text = str(item).strip()
            if text:
                out.append({
                    "storage_attribute": text,
                    "source_attribute": None,
                    "source_object": None,
                    "saved_object": None,
                    "mapping_status": "target_field_observed_source_unresolved",
                    "evidence_refs": [],
                })
    return [x for x in out if x.get("storage_attribute")]


def _fdp_field_names_from_props(props: dict[str, Any]) -> list[Any]:
    values: list[Any] = []
    for key in [
        "saved_attributes", "source_to_saved_field_mappings", "write_target_fields", "storage_fields", "written_fields", "saved_fields", "target_columns", "target_fields",
        "field_mappings", "mapping_hints", "lineage_hints", "columns", "fields", "field_names", "db_columns", "assigned_fields", "record_setters",
    ]:
        raw = props.get(key)
        if not raw:
            continue
        values.extend(_fdp_list(raw))
    return values


def _fdp_attribute_key(attr: dict[str, Any]) -> tuple[str, str, str]:
    return (_fdp_norm(attr.get("storage_attribute")), _fdp_norm(attr.get("source_attribute")), _fdp_norm(attr.get("saved_object")))


def _fdp_mapping_status_from_level(level: Any, mapping_type: Any = None) -> str:
    raw = str(level or "").lower()
    mtype = str(mapping_type or "").lower()
    if "name" in mtype or "inferred" in raw or "name" in raw:
        return "inferred_from_names"
    if raw in {"confirmed", "confirmed_by_analyzer", "observed", "observed_in_code"} or "confirmed" in raw:
        return "confirmed"
    if raw in {"unresolved", "unknown", "insufficient"}:
        return "unresolved"
    return "candidate"


def _fdp_mark_saved_attribute(attr: dict[str, Any], *, source: str) -> dict[str, Any]:
    out = dict(attr)
    out.setdefault("field_evidence_status", source)
    out.setdefault("attribute_source", source)
    return out


def _fdp_enrich_persistence_attributes(
    sp: dict[str, Any],
    *,
    storage: Any,
    matched_write_refs: list[str],
    candidate_write_refs: list[str],
    writes_by_id: dict[str, dict[str, Any]],
    mappings: list[dict[str, Any]],
    db_columns: list[dict[str, Any]],
    max_results: int = 200,
) -> dict[str, list[dict[str, Any]]]:
    write_target_fields: list[dict[str, Any]] = []
    source_to_saved_mappings: list[dict[str, Any]] = []
    schema_only_attrs: list[dict[str, Any]] = []
    rejected_noisy_fields: list[dict[str, Any]] = []

    def add_attr(attr: dict[str, Any], *, source: str, role: str) -> None:
        attr = _fdp_mark_saved_attribute(attr, source=source)
        attr["attribute_role"] = role
        attr["source_mapping_available"] = bool(attr.get("source_attribute") and role == "source_to_saved_mapping")
        clean, rejected = _fdp_filter_field_attr(attr, role=role)
        if rejected:
            rejected_noisy_fields.append(rejected)
        if not clean:
            return
        if role == "source_to_saved_mapping" and not clean.get("source_attribute"):
            clean["attribute_role"] = "write_target_field"
            clean["source_mapping_available"] = False
            clean["mapping_status"] = "target_field_observed_source_unresolved"
            write_target_fields.append(clean)
        elif role == "source_to_saved_mapping":
            source_to_saved_mappings.append(clean)
        elif role == "schema_only":
            schema_only_attrs.append(clean)
        else:
            write_target_fields.append(clean)

    for attr in _fdp_field_values_from_any(_fdp_field_names_from_props(sp)):
        attr.setdefault("saved_object", sp.get("saved_object") or sp.get("storage_object") or storage)
        if not attr.get("evidence_refs"):
            attr["evidence_refs"] = _evidence_refs(sp)
        role = "source_to_saved_mapping" if attr.get("source_attribute") else "write_target_field"
        if not attr.get("source_attribute"):
            attr["mapping_status"] = "target_field_observed_source_unresolved"
        add_attr(attr, source="lineage_saved_field", role=role)

    for ref in matched_write_refs + candidate_write_refs:
        w = writes_by_id.get(ref)
        if not w or _fdp_source_scope(w) == "test_code":
            continue
        wp = _props(w)
        evidence_source = "persistent_write_target_field" if ref in matched_write_refs else "candidate_persistent_write_target_field"
        for field_attr in _fdp_field_values_from_any(_fdp_field_names_from_props(wp)):
            field_attr.setdefault("source_attribute", None)
            field_attr.setdefault("source_object", None)
            field_attr.setdefault("saved_object", wp.get("saved_object") or wp.get("storage_object") or wp.get("storage_target") or storage)
            if field_attr.get("source_attribute"):
                field_attr["mapping_status"] = _fdp_mapping_status_from_level(field_attr.get("mapping_status") or wp.get("evidence_level"))
                role = "source_to_saved_mapping"
            else:
                field_attr["mapping_status"] = "target_field_observed_source_unresolved"
                role = "write_target_field"
            field_attr["evidence_refs"] = _evidence_refs(w)
            add_attr(field_attr, source=evidence_source, role=role)

    storage_values = _fdp_storage_values(sp) + [storage]
    saved_obj_norm = _fdp_norm(_fdp_concrete_text(sp.get("saved_object") or sp.get("storage_object") or storage))
    for m in mappings:
        if _fdp_source_scope(m) == "test_code":
            continue
        source_object = m.get("source_object")
        target_object = m.get("target_object")
        target_attr = m.get("target_attribute")
        source_attr = m.get("source_attribute")
        if not target_attr:
            continue
        target_matches = False
        if saved_obj_norm and _fdp_norm(target_object) == saved_obj_norm:
            target_matches = True
        if any(_fdp_storage_candidate_matches(target_object, sv) for sv in storage_values if sv):
            target_matches = True
        if any(_fdp_storage_candidate_matches(target_attr, sv) for sv in storage_values if sv):
            target_matches = True
        if not target_matches:
            continue
        status = _fdp_mapping_status_from_level(m.get("evidence_level"), m.get("mapping_type"))
        role = "source_to_saved_mapping" if source_attr else "write_target_field"
        add_attr({
            "storage_attribute": target_attr,
            "source_attribute": source_attr,
            "source_object": source_object,
            "saved_object": target_object or storage,
            "mapping_status": status if source_attr else "target_field_observed_source_unresolved",
            "mapping_kind": m.get("mapping_type"),
            "evidence_policy": m.get("evidence_policy"),
            "evidence_refs": (m.get("provenance") or {}).get("evidence_refs") or _fdp_unique_strings([m.get("mapping_id")]),
        }, source="attribute_mapping", role=role)

    if not write_target_fields and not source_to_saved_mappings and storage:
        for col in db_columns:
            table = col.get("table_name") or col.get("qualified_table") or col.get("storage_target")
            if not any(_fdp_storage_matches(table, sv) for sv in storage_values if sv):
                continue
            name = col.get("column_name") or col.get("name") or col.get("db_column_name")
            if not name:
                continue
            attr = {
                "storage_attribute": f"{table}.{name}" if table else name,
                "source_attribute": None,
                "source_object": None,
                "saved_object": storage,
                "mapping_status": "schema_field_only_not_write_evidence",
                "evidence_refs": _fdp_unique_strings([col.get("db_schema_column_id"), col.get("evidence_id")]),
            }
            add_attr(attr, source="schema_only_fallback", role="schema_only")
            if len(schema_only_attrs) >= max_results:
                break

    def dedupe(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        deduped: list[dict[str, Any]] = []
        seen: dict[tuple[str, str, str], int] = {}
        for attr in items:
            if not attr.get("storage_attribute"):
                continue
            if attr.get("mapping_status") in {"confirmed_by_analyzer", "observed", "observed_in_code"}:
                attr["mapping_status"] = "confirmed" if attr.get("source_attribute") else "target_field_observed_source_unresolved"
            key = _fdp_attribute_key(attr)
            if key in seen:
                idx = seen[key]
                existing = deduped[idx]
                existing_refs = _fdp_unique_strings(_fdp_list(existing.get("evidence_refs")))
                attr_refs = _fdp_unique_strings(_fdp_list(attr.get("evidence_refs")))
                existing_has_stream = any("stream_collection_lineage_" in str(ref) for ref in existing_refs)
                attr_has_stream = any("stream_collection_lineage_" in str(ref) for ref in attr_refs)
                existing_confirmed = existing.get("mapping_status") == "confirmed"
                attr_confirmed = attr.get("mapping_status") == "confirmed"
                if (attr_has_stream and not existing_has_stream and not existing_confirmed) or (attr_confirmed and not existing_confirmed):
                    merged = dict(existing)
                    merged.update({k: v for k, v in attr.items() if v not in (None, [], {})})
                    merged["evidence_refs"] = _fdp_unique_strings(existing_refs + attr_refs)
                    merged["hint_refs"] = _fdp_unique_strings(_fdp_list(existing.get("hint_refs")) + _fdp_list(attr.get("hint_refs")))
                    deduped[idx] = {k: v for k, v in merged.items() if v not in (None, [], {})}
                continue
            seen[key] = len(deduped)
            attr["evidence_refs"] = _fdp_unique_strings(_fdp_list(attr.get("evidence_refs")))
            attr["hint_refs"] = _fdp_unique_strings(_fdp_list(attr.get("hint_refs")))
            attr = {k: v for k, v in attr.items() if v not in (None, [], {})}
            deduped.append(attr)
            if len(deduped) >= max_results:
                break
        return deduped

    write_target_fields = dedupe(write_target_fields)
    source_to_saved_mappings = dedupe(source_to_saved_mappings)
    schema_only_attrs = dedupe(schema_only_attrs)
    saved_attributes = write_target_fields + source_to_saved_mappings
    return {
        "saved_attributes": saved_attributes[:max_results],  # compatibility field: no schema-only fallback
        "write_target_fields": write_target_fields,
        "source_to_saved_field_mappings": source_to_saved_mappings,
        "schema_only_attributes": schema_only_attrs,
        "rejected_noisy_fields": rejected_noisy_fields[:max_results],
        "field_quality_summary": {
            "accepted_field_count": len(write_target_fields) + len(source_to_saved_mappings),
            "rejected_noisy_field_count": len(rejected_noisy_fields),
        },
    }

def _fdp_related_stored_response_mappings(
    storage: Any,
    related_access: list[dict[str, Any]],
    raw_mappings: list[dict[str, Any]],
    write_target_fields: list[dict[str, Any]],
    source_to_saved_mappings: list[dict[str, Any]],
    *,
    max_results: int = 200,
) -> dict[str, Any]:
    production_access = [x for x in related_access if _fdp_source_scope(x) != "test_code"]
    access_ids = {_item_id(x) for x in production_access if _item_id(x)}
    storage_values = _fdp_unique_strings([storage] + [(_props(x).get("source_storage_object") or _props(x).get("storage_object")) for x in production_access])
    saved_field_norms = {_fdp_norm(a.get("storage_attribute")) for a in write_target_fields + source_to_saved_mappings if a.get("storage_attribute")}
    mapping_refs: list[str] = []
    overlaps: list[dict[str, Any]] = []
    rejected_noisy_fields: list[dict[str, Any]] = []
    unresolved_reasons: list[str] = []
    overlap_bases: set[str] = set()
    field_statuses: set[str] = set()
    for raw in raw_mappings:
        if _fdp_source_scope(raw) == "test_code":
            continue
        mp = _props(raw)
        mid = str(mp.get("stored_field_to_response_field_mapping_id") or mp.get("mapping_id") or _item_id(raw) or "")
        lid = str(mp.get("storage_to_access_lineage_id") or mp.get("lineage_id") or mp.get("storage_to_access_lineage_ref") or "")
        storage_field = mp.get("storage_field") or mp.get("source_field") or mp.get("stored_field")
        response_field = mp.get("response_field") or mp.get("target_field") or mp.get("published_field")
        storage_obj = mp.get("storage_object") or mp.get("source_storage_object") or mp.get("source_container")
        if access_ids and lid and lid in access_ids:
            related = True
            relation_basis = "storage_to_access_lineage_ref"
        else:
            related = bool(any(_fdp_storage_candidate_matches(storage_obj, sv) for sv in storage_values if sv))
            relation_basis = "storage_object_match" if related else ""
            if not related and storage_field and saved_field_norms:
                sf = _fdp_norm(storage_field)
                related = any(sf and (sf == norm or sf.endswith(norm) or norm.endswith(sf)) for norm in saved_field_norms)
                relation_basis = "saved_field_match" if related else ""
        if not related:
            continue
        attr = {
            "storage_attribute": storage_field,
            "response_attribute": response_field,
            "mapping_status": _fdp_mapping_status_from_level(mp.get("evidence_level") or mp.get("evidence_maturity_level"), mp.get("mapping_type") or mp.get("mapping_kind")),
            "evidence_refs": _evidence_refs(raw),
        }
        clean, rejected = _fdp_filter_field_attr(attr, role="storage_to_access_mapping")
        if rejected:
            rejected_noisy_fields.append(rejected)
        if not clean or not clean.get("storage_attribute") or not clean.get("response_attribute"):
            continue
        if mid:
            mapping_refs.append(mid)
        status = clean["mapping_status"]
        if status == "confirmed":
            basis = "field_mapping_confirmed"
            field_status = "confirmed_field_mapping"
        elif status == "inferred_from_names":
            basis = "name_based_field_overlap"
            field_status = "inferred_from_names"
        else:
            basis = "field_mapping_candidate" if relation_basis != "saved_field_match" else "saved_field_name_overlap"
            field_status = "candidate_field_mapping"
        overlap_bases.add(basis)
        field_statuses.add(field_status)
        clean.update({
            "overlap_basis": basis,
            "field_evidence_status": field_status,
        })
        overlaps.append(clean)
        if len(overlaps) >= max_results:
            break
    if not production_access:
        unresolved_reasons.append("external_access_not_observed")
    if production_access and not overlaps:
        unresolved_reasons.append("storage_to_access_lineage_found_but_field_mapping_not_materialized")
        overlap_bases.add("access_lineage_only")
        field_statuses.add("no_field_mapping")

    source_mapping_status = "unresolved"
    source_mapping_refs: list[str] = []
    source_field_mappings: list[dict[str, Any]] = []
    if source_to_saved_mappings:
        source_field_mappings = source_to_saved_mappings[:max_results]
        source_mapping_refs = _fdp_unique_strings([ref for a in source_to_saved_mappings for ref in (a.get("evidence_refs") or [])])
        if any((a.get("mapping_status") == "confirmed") for a in source_to_saved_mappings):
            source_mapping_status = "confirmed"
        else:
            source_mapping_status = "candidate"

    storage_to_access_status = "unresolved"
    if overlaps:
        storage_to_access_status = "confirmed" if any(x.get("mapping_status") == "confirmed" for x in overlaps) else "candidate"
    elif production_access:
        storage_to_access_status = "candidate"

    if source_mapping_status == "confirmed" and storage_to_access_status == "confirmed":
        end_status = "confirmed"
        end_basis = "source_storage_access_field_chain"
    elif source_mapping_status in {"confirmed", "candidate"} and storage_to_access_status in {"confirmed", "candidate"}:
        end_status = "candidate"
        end_basis = "source_storage_access_field_chain"
    elif storage_to_access_status in {"confirmed", "candidate"}:
        end_status = "candidate" if overlaps else "unresolved"
        end_basis = "storage_access_only"
        unresolved_reasons.append("storage_to_access_only_no_source_chain")
    else:
        end_status = "unresolved"
        end_basis = "unresolved"

    legacy_status = "confirmed_overlap" if end_status == "confirmed" else ("candidate_overlap" if end_status == "candidate" else "unresolved")
    basis_priority = ["field_mapping_confirmed", "field_mapping_candidate", "name_based_field_overlap", "saved_field_name_overlap", "access_lineage_only", "no_access"]
    field_priority = ["confirmed_field_mapping", "candidate_field_mapping", "inferred_from_names", "no_field_mapping", "not_applicable"]
    if not overlap_bases:
        overlap_bases.add("no_access" if not production_access else "access_lineage_only")
    if not field_statuses:
        field_statuses.add("not_applicable" if not production_access else "no_field_mapping")
    overlap_basis = next((x for x in basis_priority if x in overlap_bases), sorted(overlap_bases)[0])
    field_evidence_status = next((x for x in field_priority if x in field_statuses), sorted(field_statuses)[0])
    return {
        "status": legacy_status,
        "overlap_basis": overlap_basis,
        "field_evidence_status": field_evidence_status,
        "mapping_refs": _fdp_unique_strings(mapping_refs),
        "stored_to_response_mapping_refs": _fdp_unique_strings(mapping_refs),
        "overlapping_attributes": overlaps,
        "source_to_storage": {
            "status": source_mapping_status,
            "mapping_refs": source_mapping_refs,
            "field_mappings": source_field_mappings,
        },
        "storage_to_access": {
            "status": storage_to_access_status,
            "mapping_refs": _fdp_unique_strings(mapping_refs),
            "field_mappings": overlaps,
        },
        "end_to_end_same_data": {
            "status": end_status,
            "basis": end_basis,
        },
        "gap_refs": [],
        "unresolved_reasons": list(dict.fromkeys(unresolved_reasons)),
        "rejected_noisy_fields": rejected_noisy_fields[:max_results],
    }

def _fdp_local_persistence_summary(cases: list[dict[str, Any]]) -> dict[str, Any]:
    by_observation_kind: dict[str, int] = {}
    out = {
        "total_cases": len(cases),
        "with_direct_persistent_write_refs": 0,
        "with_overlap_persistent_write_refs": 0,
        "with_saved_attributes": 0,
        "with_write_target_fields": 0,
        "with_source_to_saved_field_mappings": 0,
        "with_schema_only_attributes": 0,
        "with_only_target_fields_no_source_mapping": 0,
        "with_rejected_noisy_fields": 0,
        "by_persistent_write_observation_kind": by_observation_kind,
    }
    for case in cases:
        lp = case.get("local_persistence") or {}
        if lp.get("persistent_write_refs"):
            out["with_direct_persistent_write_refs"] += 1
        if lp.get("overlap_persistent_write_refs"):
            out["with_overlap_persistent_write_refs"] += 1
        for observation in lp.get("persistent_write_observations") or []:
            kind = str(observation.get("observation_kind") or "unknown")
            by_observation_kind[kind] = by_observation_kind.get(kind, 0) + 1
        if lp.get("saved_attributes"):
            out["with_saved_attributes"] += 1
        if lp.get("write_target_fields"):
            out["with_write_target_fields"] += 1
        if lp.get("source_to_saved_field_mappings"):
            out["with_source_to_saved_field_mappings"] += 1
        if lp.get("schema_only_attributes"):
            out["with_schema_only_attributes"] += 1
        if lp.get("write_target_fields") and not lp.get("source_to_saved_field_mappings"):
            out["with_only_target_fields_no_source_mapping"] += 1
        if lp.get("rejected_noisy_fields"):
            out["with_rejected_noisy_fields"] += 1
    return out

def _fdp_same_data_field_summary(cases: list[dict[str, Any]]) -> dict[str, Any]:
    by_status: dict[str, int] = {}
    by_basis: dict[str, int] = {}
    by_field_status: dict[str, int] = {}
    by_e2e: dict[str, int] = {}
    by_e2e_basis: dict[str, int] = {}
    out = {
        "total_cases": len(cases),
        "with_stored_to_response_mapping_refs": 0,
        "with_overlapping_attributes": 0,
        "with_source_to_storage_field_mappings": 0,
        "with_end_to_end_same_data_confirmed": 0,
        "with_end_to_end_same_data_candidate": 0,
        "by_same_data_link_status": by_status,
        "by_overlap_basis": by_basis,
        "by_field_evidence_status": by_field_status,
        "by_end_to_end_same_data_status": by_e2e,
        "by_end_to_end_same_data_basis": by_e2e_basis,
    }
    for case in cases:
        sdl = case.get("same_data_link") or {}
        status = str(sdl.get("status") or "unresolved")
        basis = str(sdl.get("overlap_basis") or "unknown")
        field_status = str(sdl.get("field_evidence_status") or "unknown")
        e2e = sdl.get("end_to_end_same_data") or {}
        e2e_status = str(e2e.get("status") or "unresolved")
        e2e_basis = str(e2e.get("basis") or "unresolved")
        by_status[status] = by_status.get(status, 0) + 1
        by_basis[basis] = by_basis.get(basis, 0) + 1
        by_field_status[field_status] = by_field_status.get(field_status, 0) + 1
        by_e2e[e2e_status] = by_e2e.get(e2e_status, 0) + 1
        by_e2e_basis[e2e_basis] = by_e2e_basis.get(e2e_basis, 0) + 1
        if sdl.get("stored_to_response_mapping_refs"):
            out["with_stored_to_response_mapping_refs"] += 1
        if sdl.get("overlapping_attributes"):
            out["with_overlapping_attributes"] += 1
        if (sdl.get("source_to_storage") or {}).get("field_mappings"):
            out["with_source_to_storage_field_mappings"] += 1
        if e2e_status == "confirmed":
            out["with_end_to_end_same_data_confirmed"] += 1
        if e2e_status == "candidate":
            out["with_end_to_end_same_data_candidate"] += 1
    return out

def _fdp_mapping_hint_family(mapping: dict[str, Any]) -> str:
    text = " ".join(str(mapping.get(k) or "") for k in ["mapping_kind", "evidence_policy", "attribute_source"]).lower()
    refs = " ".join(str(x) for x in _fdp_list(mapping.get("evidence_refs")) + _fdp_list(mapping.get("hint_refs"))).lower()
    blob = text + " " + refs
    if "stream_collection" in blob or "streamcollection" in blob:
        return "stream_collection"
    if "jooq_parameterized" in blob or "parameterized_sql" in blob:
        return "jooq_parameterized_sql"
    if "jooq_batch" in blob or "bind_order" in blob:
        return "jooq_bind_order"
    if "factory" in blob:
        return "factory"
    if "builder" in blob or "tobuilder" in blob:
        return "builder_to_builder"
    if "mapstruct" in blob or "mapper_signature" in blob:
        return "mapper_signature"
    return "other"


def _fdp_case_evidence_maturity(case: dict[str, Any]) -> dict[str, Any]:
    interp = case.get("source_interpretation") or {}
    lp = case.get("local_persistence") or {}
    sdl = case.get("same_data_link") or {}
    related_events = interp.get("related_inbound_event_sources") or []
    mappings = lp.get("source_to_saved_field_mappings") or []
    access = case.get("external_access") or {}
    object_mappings = interp.get("related_object_mappings") or []
    families_set = {fam for fam in (_fdp_mapping_hint_family(m) for m in mappings) if fam != "other"}
    if any("mapstruct" in str(m.get("mapping_type") or "").lower() or "mapper_signature" in str(m.get("mapping_type") or "").lower() for m in object_mappings):
        families_set.add("mapper_signature")
    families = sorted(families_set)
    call_paths = [ev.get("call_path") for ev in related_events if isinstance(ev.get("call_path"), dict)]
    call_statuses = sorted({str(cp.get("argument_propagation_status") or "unknown") for cp in call_paths})

    def status_for_mappings() -> str:
        if not mappings:
            return "unresolved"
        if any(m.get("mapping_status") == "confirmed" for m in mappings):
            return "confirmed"
        return "candidate"

    source_status = interp.get("status") or "unknown_origin"
    source_segment_status = status_for_mappings()
    storage_to_access_status = (sdl.get("storage_to_access") or {}).get("status") or "unresolved"
    end_status = (sdl.get("end_to_end_same_data") or {}).get("status") or "unresolved"

    return {
        "maturity_policy": "technical evidence maturity only; no business own/foreign or risk decision",
        "segments": {
            "ingress_to_write_operation": {
                "status": "candidate" if related_events else "unresolved",
                "basis": "method_call_argument_binding" if call_paths else ("call_graph_hint" if related_events else "none"),
                "call_argument_propagation_statuses": call_statuses,
                "evidence_refs": _fdp_unique_strings([ref for ev in related_events for ref in _fdp_list(ev.get("hint_refs"))]),
            },
            "source_to_mapped_object": {
                "status": source_segment_status if mappings else ("candidate" if object_mappings else "unresolved"),
                "hint_families": families,
                "field_mapping_count": len(mappings),
                "object_mapping_count": len(object_mappings),
            },
            "mapped_object_to_write": {
                "persistent_write_refs": lp.get("persistent_write_refs") or [],
                "overlap_persistent_write_refs": lp.get("overlap_persistent_write_refs") or [],
                "persistent_write_observations": lp.get("persistent_write_observations") or [],
                "persistent_write_fact_found": bool(lp.get("persistent_write_refs") or lp.get("overlap_persistent_write_refs")),
            },
            "source_to_storage_field_chain": {
                "status": (sdl.get("source_to_storage") or {}).get("status") or source_segment_status,
                "field_mapping_count": len((sdl.get("source_to_storage") or {}).get("field_mappings") or mappings),
                "hint_families": families,
            },
            "storage_to_access_field_chain": {
                "status": storage_to_access_status,
                "field_mapping_count": len((sdl.get("storage_to_access") or {}).get("field_mappings") or []),
            },
            "end_to_end_same_data": {
                "status": end_status,
                "basis": (sdl.get("end_to_end_same_data") or {}).get("basis"),
            },
        },
        "summary": {
            "source_origin_status": source_status,
            "has_call_argument_propagation": bool(call_paths),
            "has_multi_hop_call_argument_propagation": any(cp.get("path_kind") == "multi_hop_method_call_argument_path" for cp in call_paths),
            "has_payload_alias_propagation": any(cp.get("has_payload_alias_propagation") for cp in call_paths),
            "has_hint_based_field_mapping": bool(families),
            "has_external_access": access.get("status") == "observed_in_code",
            "end_to_end_status": end_status,
        },
    }


def _fdp_evidence_maturity_summary(cases: list[dict[str, Any]]) -> dict[str, Any]:
    by_end_status: dict[str, int] = {}
    by_hint_family: dict[str, int] = {}
    out = {
        "total_cases": len(cases),
        "with_method_call_argument_propagation": 0,
        "with_multi_hop_method_call_argument_propagation": 0,
        "with_payload_alias_propagation": 0,
        "with_candidate_hint_based_field_mapping": 0,
        "with_mapper_signature_object_bridge": 0,
        "by_end_to_end_status": by_end_status,
        "by_hint_family": by_hint_family,
    }
    for case in cases:
        maturity = case.get("evidence_maturity") or _fdp_case_evidence_maturity(case)
        summary = maturity.get("summary") or {}
        if summary.get("has_call_argument_propagation"):
            out["with_method_call_argument_propagation"] += 1
        call_paths = [ev.get("call_path") for ev in ((case.get("source_interpretation") or {}).get("related_inbound_event_sources") or []) if isinstance(ev.get("call_path"), dict)]
        if any(cp.get("path_kind") == "multi_hop_method_call_argument_path" for cp in call_paths):
            out["with_multi_hop_method_call_argument_propagation"] += 1
        if any(cp.get("has_payload_alias_propagation") for cp in call_paths):
            out["with_payload_alias_propagation"] += 1
        if summary.get("has_hint_based_field_mapping"):
            out["with_candidate_hint_based_field_mapping"] += 1
        end = str(summary.get("end_to_end_status") or "unresolved")
        by_end_status[end] = by_end_status.get(end, 0) + 1
        for seg in (maturity.get("segments") or {}).values():
            for family in seg.get("hint_families") or []:
                by_hint_family[family] = by_hint_family.get(family, 0) + 1
                if family == "mapper_signature":
                    out["with_mapper_signature_object_bridge"] += 1
    return out


def _fdp_chain_completeness_summary(cases: list[dict[str, Any]]) -> dict[str, Any]:
    out = {
        "total_cases": len(cases),
        "with_concrete_source_payload": 0,
        "with_production_ingress_link": 0,
        "with_confirmed_persistent_write": 0,
        "with_write_target_fields": 0,
        "with_source_to_saved_field_mappings": 0,
        "with_external_access": 0,
        "with_storage_to_access_field_mapping": 0,
        "with_end_to_end_same_data_confirmed": 0,
        "with_end_to_end_same_data_candidate": 0,
        "blocked_by_unknown_source": 0,
        "blocked_by_test_only_evidence": 0,
        "blocked_by_missing_source_to_storage_mapping": 0,
        "blocked_by_missing_storage_to_access_mapping": 0,
        "blocked_by_noisy_fields": 0,
    }
    for case in cases:
        interp = case.get("source_interpretation") or {}
        lp = case.get("local_persistence") or {}
        sdl = case.get("same_data_link") or {}
        scope = case.get("evidence_scope_summary") or {}
        if interp.get("source_payload_concrete"):
            out["with_concrete_source_payload"] += 1
        if interp.get("related_inbound_event_sources") and scope.get("has_production_evidence"):
            out["with_production_ingress_link"] += 1
        if lp.get("persistent_write_refs"):
            out["with_confirmed_persistent_write"] += 1
        if lp.get("write_target_fields"):
            out["with_write_target_fields"] += 1
        if lp.get("source_to_saved_field_mappings"):
            out["with_source_to_saved_field_mappings"] += 1
        if (case.get("external_access") or {}).get("status") == "observed_in_code":
            out["with_external_access"] += 1
        if (sdl.get("storage_to_access") or {}).get("field_mappings"):
            out["with_storage_to_access_field_mapping"] += 1
        e2e = sdl.get("end_to_end_same_data") or {}
        if e2e.get("status") == "confirmed":
            out["with_end_to_end_same_data_confirmed"] += 1
        if e2e.get("status") == "candidate":
            out["with_end_to_end_same_data_candidate"] += 1
        blockers = set((case.get("risk_eligibility") or {}).get("blocking_reasons") or [])
        chain = case.get("chain_breakdown") or {}
        for section in chain.values():
            blockers.update(section.get("blocking_reasons") or [])
        if "source_origin_unresolved" in blockers or "source_payload_unknown" in blockers:
            out["blocked_by_unknown_source"] += 1
        if (case.get("case_scope") == "test_only") or "no_production_evidence" in blockers or "test_only_persistence_evidence" in blockers:
            out["blocked_by_test_only_evidence"] += 1
        if "missing_source_to_saved_field_mapping" in blockers or "target_field_only_no_source_mapping" in blockers or "source_attribute_missing" in blockers:
            out["blocked_by_missing_source_to_storage_mapping"] += 1
        if "missing_storage_to_access_field_mapping" in blockers or "external_access_not_observed" in blockers:
            out["blocked_by_missing_storage_to_access_mapping"] += 1
        if lp.get("rejected_noisy_fields") or sdl.get("rejected_noisy_fields"):
            out["blocked_by_noisy_fields"] += 1
    return out

def _fdp_bool_filter(value: str | bool | None) -> bool | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    raw = str(value).strip().lower()
    if raw in {"true", "1", "yes", "y"}:
        return True
    if raw in {"false", "0", "no", "n"}:
        return False
    return None


def _fdp_csv_filter(value: str | None) -> set[str]:
    if not value:
        return set()
    return {x.strip() for x in str(value).split(",") if x.strip()}


def _fdp_filter_cases(
    cases: list[dict[str, Any]],
    *,
    external_access: str | None = None,
    source_interpretation: str | None = None,
    same_data_link: str | None = None,
    with_persistent_write_refs: str | bool | None = None,
    with_saved_attributes: str | bool | None = None,
    case_id: str | None = None,
) -> list[dict[str, Any]]:
    external_values = _fdp_csv_filter(external_access)
    source_values = _fdp_csv_filter(source_interpretation)
    same_values = _fdp_csv_filter(same_data_link)
    want_writes = _fdp_bool_filter(with_persistent_write_refs)
    want_attrs = _fdp_bool_filter(with_saved_attributes)
    out: list[dict[str, Any]] = []
    for case in cases:
        if case_id and str(case.get("id") or "") != str(case_id):
            continue
        if external_values and str((case.get("external_access") or {}).get("status") or "") not in external_values:
            continue
        if source_values and str((case.get("source_interpretation") or {}).get("status") or "") not in source_values:
            continue
        if same_values and str((case.get("same_data_link") or {}).get("status") or "") not in same_values:
            continue
        lp = case.get("local_persistence") or {}
        has_writes = bool(lp.get("persistent_write_refs") or lp.get("overlap_persistent_write_refs"))
        has_attrs = bool(lp.get("saved_attributes"))
        if want_writes is not None and has_writes != want_writes:
            continue
        if want_attrs is not None and has_attrs != want_attrs:
            continue
        out.append(case)
    return out


def _fdp_case_sort_key(case: dict[str, Any]) -> tuple[int, int, int, int, int, str]:
    access_priority = 0 if ((case.get("external_access") or {}).get("status") == "observed_in_code") else 1
    source_order = {
        "confirmed_external_ingress": 0,
        "external_ingress_candidate": 1,
        "runtime_input_candidate": 2,
        "unknown_origin": 3,
        "internal_generated_or_local_candidate": 4,
    }
    same_order = {"confirmed_overlap": 0, "candidate_overlap": 1, "unresolved": 2, "not_applicable": 3}
    lp = case.get("local_persistence") or {}
    sdl = case.get("same_data_link") or {}
    return (
        access_priority,
        source_order.get(str((case.get("source_interpretation") or {}).get("status") or "unknown_origin"), 9),
        same_order.get(str(sdl.get("status") or "unresolved"), 9),
        -len(lp.get("persistent_write_refs") or []),
        -len(lp.get("saved_attributes") or []),
        str(case.get("id") or ""),
    )

def _fdp_chain_breakdown(case: dict[str, Any]) -> dict[str, Any]:
    interp = case.get("source_interpretation") or {}
    lp = case.get("local_persistence") or {}
    access = case.get("external_access") or {}
    sdl = case.get("same_data_link") or {}
    source_status = interp.get("status") or "unknown_origin"
    source_to_storage_status = (sdl.get("source_to_storage") or {}).get("status") or "unresolved"
    persistence_status = "confirmed" if lp.get("persistent_write_refs") else ("candidate" if lp.get("overlap_persistent_write_refs") else "unresolved")
    storage_access_status = (sdl.get("storage_to_access") or {}).get("status") or ("candidate" if access.get("status") == "observed_in_code" else "unresolved")
    e2e = sdl.get("end_to_end_same_data") or {}
    blocking_source: list[str] = []
    blocking_s2s: list[str] = []
    blocking_persistence: list[str] = []
    blocking_access: list[str] = []
    blocking_e2e: list[str] = []
    if source_status in {"unknown_origin", "runtime_origin_unresolved"}:
        blocking_source.append("source_payload_unknown")
    if (interp.get("discarded_signals") or []):
        blocking_source.extend(interp.get("discarded_signals") or [])
    if not lp.get("source_to_saved_field_mappings"):
        blocking_s2s.append("target_field_only_no_source_mapping" if lp.get("write_target_fields") else "source_attribute_missing")
    if persistence_status == "unresolved":
        blocking_persistence.append("persistent_write_ref_not_found")
    elif persistence_status == "candidate":
        blocking_persistence.append("persistent_write_ref_candidate_only")
    scope_summary = case.get("evidence_scope_summary") or {}
    if scope_summary.get("dominant_scope") == "test_code" and not scope_summary.get("has_production_evidence"):
        blocking_persistence.append("test_only_persistence_evidence")
    if access.get("status") != "observed_in_code":
        blocking_access.append("external_access_not_observed")
    if storage_access_status == "candidate":
        blocking_access.append("storage_to_access_candidate_only")
    if (e2e.get("status") or "unresolved") != "confirmed":
        if e2e.get("basis") == "storage_access_only":
            blocking_e2e.append("storage_to_access_only_no_source_chain")
        else:
            blocking_e2e.append("end_to_end_same_data_not_confirmed")
    return {
        "source": {"status": source_status, "blocking_reasons": list(dict.fromkeys(blocking_source))},
        "source_to_storage": {"status": source_to_storage_status, "blocking_reasons": list(dict.fromkeys(blocking_s2s))},
        "persistence": {"status": persistence_status, "blocking_reasons": list(dict.fromkeys(blocking_persistence))},
        "storage_to_access": {"status": storage_access_status, "blocking_reasons": list(dict.fromkeys(blocking_access))},
        "end_to_end": {"status": e2e.get("status") or "unresolved", "blocking_reasons": list(dict.fromkeys(blocking_e2e))},
    }


def _fdp_risk_eligibility(case: dict[str, Any]) -> dict[str, Any]:
    interp = case.get("source_interpretation") or {}
    lp = case.get("local_persistence") or {}
    access = case.get("external_access") or {}
    sdl = case.get("same_data_link") or {}
    scope = case.get("evidence_scope_summary") or {}
    reasons: list[str] = []
    if interp.get("status") in {"unknown_origin", "runtime_origin_unresolved"}:
        reasons.append("source_origin_unresolved")
    if not scope.get("has_production_evidence", False):
        reasons.append("no_production_evidence")
    if not lp.get("persistent_write_refs"):
        reasons.append("direct_persistent_write_reference_not_observed")
    if not lp.get("source_to_saved_field_mappings"):
        reasons.append("missing_source_to_saved_field_mapping")
    if access.get("status") != "observed_in_code":
        reasons.append("external_access_not_observed")
    if (sdl.get("storage_to_access") or {}).get("status") not in {"confirmed", "candidate"}:
        reasons.append("missing_storage_to_access_field_mapping")
    if (sdl.get("end_to_end_same_data") or {}).get("status") not in {"confirmed", "candidate"}:
        reasons.append("end_to_end_same_data_not_established")
    eligible = not reasons
    priority = "probable_candidate" if eligible else ("investigation_candidate" if access.get("status") == "observed_in_code" else "incomplete_candidate")
    return {"risk_eligible": eligible, "risk_status": priority, "blocking_reasons": list(dict.fromkeys(reasons))}



def _fdp_is_local_collection_mutation_root(props: dict[str, Any], storage: str) -> bool:
    """Return True for local collection/map mutations that should not root FDP cases.

    source_to_storage_lineage may contain Java collection mutations such as
    linksToRemove.add(...) or cardsToRemove.put(...). They can be useful as
    local data-flow hints when they later feed a DAO/batch write, but by
    themselves they are not persistent storage boundaries and must not become
    foreign-data-persistence cases.
    """
    method = str(props.get("storage_method") or props.get("method") or "").strip().lower()
    if method not in {"add", "put", "remove", "removeall", "clear"}:
        return False
    level = str(props.get("storage_resolution_level") or props.get("resolution_level") or "").lower()
    storage_norm = _fdp_norm(storage)
    if not storage_norm:
        return False
    # Keep real storage-looking targets. This guard is intentionally conservative:
    # it only filters lower-camel local variables / known temporary collections,
    # not DAO/repository/table/cache targets.
    persistent_tokens = {"dao", "repository", "repo", "table", "jooq", "jdbc", "database", "cache", "topic", "queue"}
    if any(tok in storage_norm for tok in persistent_tokens):
        return False
    # storage_resolution_level can be coarse (for example custom_dao_boundary or
    # known_storage_api_or_framework_method) even for local collection mutations.
    # Trust concrete target naming more than the coarse level here; only hard
    # physical SQL/JDBC/jOOQ levels keep the root.
    if any(tok in level for tok in {"jooq", "jdbc", "database", "sql", "table"}):
        return False
    local_name = bool(storage and storage[:1].islower())
    temporary_collection_name = any(tok in storage_norm for tok in {"toremove", "toadd", "toinsert", "toupdate", "list", "map", "set", "items", "collection"})
    return local_name or temporary_collection_name

def _openspec_fdp_cases(analysis_out: Path, flows: list[dict[str, Any]], access_paths: list[dict[str, Any]], *, max_results: int = 10000) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    raw_s2s = _compact_or_facts(analysis_out, "source_to_storage_lineage", "source_to_storage_lineage")
    # FDP is a case view, not a field-lineage dump.  Real applications may now
    # emit many source_to_storage_lineage rows for one DAO/write, especially after
    # cross-DAO jOOQ field mapping.  Group by concrete write/storage boundary so
    # case materialization stays bounded while field mappings remain available in
    # local_persistence.source_to_saved_field_mappings.
    s2s: list[dict[str, Any]] = []
    seen_s2s_cases: set[tuple[str, str]] = set()
    for item in raw_s2s:
        props = _props(item)
        storage_key = _fdp_concrete_text(props.get("storage_target") or props.get("storage_object") or props.get("saved_object"))
        boundary_key = str(props.get("persistent_write_id") or props.get("storage_access_id") or _item_id(item) or "")
        key = (boundary_key, storage_key)
        if key in seen_s2s_cases:
            continue
        seen_s2s_cases.add(key)
        s2s.append(item)
    stoa = _compact_or_facts(analysis_out, "storage_to_access_lineage", "storage_to_access_lineage")
    event_sources = _event_sources(analysis_out, max_results=10000)
    mappings = _mapping_items(analysis_out, max_results=100000)
    writes = _compact_or_facts(analysis_out, "persistent_writes", "persistent_write")
    writes_by_id = {_item_id(w): w for w in writes if _item_id(w) and _fdp_source_scope(w) != "test_code"}
    db_columns = _db_schema_items(analysis_out, "db_schema_columns")
    stored_response_mappings = _compact_or_facts(analysis_out, "stored_field_to_response_field_mappings", "stored_field_to_response_field_mapping")
    spring_dependencies = _compact_or_facts(analysis_out, "spring_component_dependencies", "spring_component_dependency")
    template_dispatches = _compact_or_facts(analysis_out, "template_method_dispatches", "template_method_dispatch")
    method_calls = _compact_or_facts(analysis_out, "method_calls", "method_call")
    method_call_index = _fdp_build_method_call_index(method_calls, event_sources)

    for src in s2s:
        sp = _props(src)
        src_scope = _fdp_source_scope(src)
        # FDP cases are rooted in source-to-storage lineage. Test-only roots such
        # as Mockito verify(...).dao.write(...) must not be promoted into
        # production-looking cases merely because the same DAO/table is also read
        # by production code. Production related access can still be attached to
        # production roots below, but test roots are excluded from this case view.
        if src_scope == "test_code":
            continue
        storage = _fdp_concrete_text(sp.get("storage_target") or sp.get("storage_object") or sp.get("saved_object"))
        if not storage:
            continue
        if _fdp_is_local_collection_mutation_root(sp, storage):
            continue
        related_access = []
        for acc in stoa:
            if _fdp_source_scope(acc) == "test_code":
                continue
            ap = _props(acc)
            access_storage_values = _fdp_storage_values(ap)
            if any(_fdp_storage_candidate_matches(storage, av) for av in access_storage_values if av):
                related_access.append(acc)
        cid = _openspec_id("FDP", sp.get("source_to_storage_lineage_id") or _item_id(src), sp.get("operation"), sp.get("source_payload") or sp.get("source_object"), storage)
        source_interpretation = _fdp_source_interpretation(
            sp,
            event_sources=event_sources,
            mappings=mappings,
            spring_dependencies=spring_dependencies,
            template_dispatches=template_dispatches,
            method_calls=method_calls,
            method_call_index=method_call_index,
        )
        write_match = _fdp_match_persistent_writes(sp, writes)
        persistence_attrs = _fdp_enrich_persistence_attributes(
            sp,
            storage=storage,
            matched_write_refs=write_match["persistent_write_refs"],
            candidate_write_refs=write_match["overlap_persistent_write_refs"],
            writes_by_id=writes_by_id,
            mappings=mappings,
            db_columns=db_columns,
        )
        saved_attributes = persistence_attrs["saved_attributes"]
        write_target_fields = persistence_attrs["write_target_fields"]
        source_to_saved = persistence_attrs["source_to_saved_field_mappings"]
        schema_only_attributes = persistence_attrs["schema_only_attributes"]
        same_data_link = _fdp_related_stored_response_mappings(storage, related_access, stored_response_mappings, write_target_fields, source_to_saved)
        scopes = [src_scope] + [_fdp_source_scope(x) for x in related_access]
        scopes.extend(_fdp_source_scope(writes_by_id.get(ref)) for ref in write_match["persistent_write_refs"] + write_match["overlap_persistent_write_refs"] if writes_by_id.get(ref))
        scope_summary = _fdp_scope_summary(scopes)
        case_scope = "test_only" if scope_summary["dominant_scope"] == "test_code" and not scope_summary["has_production_evidence"] else scope_summary["dominant_scope"]
        evidence_refs = _evidence_refs(src) + [_item_id(x) for x in related_access if _item_id(x)]
        evidence_refs.extend(write_match["persistent_write_refs"])
        evidence_refs.extend(write_match["overlap_persistent_write_refs"])
        for attr in saved_attributes[:50]:
            evidence_refs.extend(attr.get("evidence_refs") or [])
        evidence_refs.extend(same_data_link.get("mapping_refs") or [])
        case = {
            "id": cid,
            "case_kind": "external_data_persistence_evidence_candidate",
            "risk_decision": "not_made_by_analyzer",
            "case_scope": case_scope,
            "evidence_scope_summary": scope_summary,
            "source_side": {
                "origin_kind": sp.get("origin_kind") or sp.get("source_kind") or "unknown",
                "source_payload": sp.get("source_payload") or sp.get("source_object"),
                "status": _status_from_evidence_level(sp.get("evidence_level") or sp.get("lineage_status"), default="unresolved_static_analysis"),
                "evidence_refs": _evidence_refs(src),
            },
            "source_interpretation": source_interpretation,
            "local_persistence": {
                "status": "observed_in_code" if storage else "unresolved_static_analysis",
                "storage_refs": [storage] if storage else [],
                "persistent_write_refs": write_match["persistent_write_refs"],
                "overlap_persistent_write_refs": write_match["overlap_persistent_write_refs"],
                "persistent_write_observations": write_match["persistent_write_observations"],
                "persistent_write_fact_found": write_match["persistent_write_fact_found"],
                "saved_attributes": saved_attributes[:80],
                "write_target_fields": write_target_fields[:80],
                "source_to_saved_field_mappings": source_to_saved[:80],
                "schema_only_attributes": schema_only_attributes[:40],
                "rejected_noisy_fields": persistence_attrs["rejected_noisy_fields"][:40],
                "materialization_limits": {
                    "saved_attributes_total": len(saved_attributes),
                    "write_target_fields_total": len(write_target_fields),
                    "source_to_saved_field_mappings_total": len(source_to_saved),
                    "schema_only_attributes_total": len(schema_only_attributes),
                    "saved_attributes_included": min(len(saved_attributes), 80),
                    "write_target_fields_included": min(len(write_target_fields), 80),
                    "source_to_saved_field_mappings_included": min(len(source_to_saved), 80),
                    "schema_only_attributes_included": min(len(schema_only_attributes), 40),
                },
                "field_quality_summary": persistence_attrs["field_quality_summary"],
            },
            "external_access": {
                "status": "observed_in_code" if related_access else "not_observed",
                "access_path_refs": [_item_id(x) for x in related_access if _item_id(x)],
                "response_attributes": [],
            },
            "same_data_link": same_data_link,
            "evidence_refs": _fdp_unique_strings(evidence_refs),
        }
        case["evidence_maturity"] = _fdp_case_evidence_maturity(case)
        case["risk_eligibility"] = _fdp_risk_eligibility(case)
        case["chain_breakdown"] = _fdp_chain_breakdown(case)
        cases.append(case)
        if len(cases) >= max_results:
            return cases
    return cases



def openspec_fdp_cases(analysis_out: Path, flows: list[dict[str, Any]], access_paths: list[dict[str, Any]], *, max_results: int = 10000, deps: FdpViewDependencies | None = None) -> list[dict[str, Any]]:
    if deps is not None:
        with _FdpDepsContext(deps):
            return _openspec_fdp_cases(analysis_out, flows, access_paths, max_results=max_results)
    return _openspec_fdp_cases(analysis_out, flows, access_paths, max_results=max_results)

def _fdp_lazy_cache_key(filters: dict[str, Any], max_results: int) -> str:
    payload = {k: v for k, v in filters.items() if v not in (None, "", [])}
    payload["max_results"] = max_results
    if not payload or payload == {"max_results": max_results}:
        return "all" if max_results == 1000 else f"all_max_{max_results}"
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
    parts: list[str] = []
    for key in ["case_id", "external_access", "source_interpretation", "same_data_link", "with_persistent_write_refs", "with_saved_attributes", "token"]:
        value = payload.get(key)
        if value not in (None, ""):
            parts.append(f"{key}_{value}")
    if not parts:
        parts.append(f"max_{max_results}")
    return f"filter_{'_'.join(parts)}_{digest}"

def foreign_data_persistence_cases(
    analysis_out: Path,
    token: str = "",
    max_results: int = 1000,
    *,
    external_access: str | None = None,
    source_interpretation: str | None = None,
    same_data_link: str | None = None,
    with_persistent_write_refs: str | bool | None = None,
    with_saved_attributes: str | bool | None = None,
    case_id: str | None = None,
    deps: FdpViewDependencies | None = None,
) -> dict[str, Any]:
    if deps is not None:
        with _FdpDepsContext(deps):
            return foreign_data_persistence_cases(
                analysis_out,
                token=token,
                max_results=max_results,
                external_access=external_access,
                source_interpretation=source_interpretation,
                same_data_link=same_data_link,
                with_persistent_write_refs=with_persistent_write_refs,
                with_saved_attributes=with_saved_attributes,
                case_id=case_id,
            )
    materialization_started = time.perf_counter()
    filters = {
        "token": token,
        "external_access": external_access,
        "source_interpretation": source_interpretation,
        "same_data_link": same_data_link,
        "with_persistent_write_refs": with_persistent_write_refs,
        "with_saved_attributes": with_saved_attributes,
        "case_id": case_id,
    }
    cache_key = _fdp_lazy_cache_key(filters, max_results)
    cache_path = analysis_out / "lazy" / "foreign-data-persistence-cases" / f"{re.sub(r'[^A-Za-z0-9_.-]+', '_', cache_key)[:160] or 'all'}.json"
    if cache_path.exists():
        cached = read_json(cache_path, None)
        if isinstance(cached, dict) and cached.get("kind") == "foreign-data-persistence-cases":
            cached = dict(cached)
            perf = dict(cached.get("materialization_performance") or {})
            perf["cache_hit"] = True
            perf["cache_key"] = cache_key
            perf["cache_read_seconds"] = round(time.perf_counter() - materialization_started, 4)
            cached["materialization_performance"] = perf
            return cached

    load_started = time.perf_counter()
    access_items = stored_data_access(analysis_out, token=token, max_results=100000).get("stored_data_access") or []
    mappings = _mapping_items(analysis_out, max_results=100000)
    flows = _data_flow_items(analysis_out, mappings, max_results=100000)
    load_seconds = time.perf_counter() - load_started
    case_started = time.perf_counter()
    all_cases = _openspec_fdp_cases(analysis_out, flows, access_items, max_results=100000)
    case_seconds = time.perf_counter() - case_started
    if token:
        all_cases = [x for x in all_cases if _item_matches_blob(x, token)]
    filtered_cases = _fdp_filter_cases(
        all_cases,
        external_access=external_access,
        source_interpretation=source_interpretation,
        same_data_link=same_data_link,
        with_persistent_write_refs=with_persistent_write_refs,
        with_saved_attributes=with_saved_attributes,
        case_id=case_id,
    )
    sorted_cases = sorted(filtered_cases, key=_fdp_case_sort_key)
    cases = sorted_cases[:max_results]
    by_same_data: dict[str, int] = {}
    by_access: dict[str, int] = {}
    by_source_interpretation: dict[str, int] = {}
    for case in filtered_cases:
        same = ((case.get("same_data_link") or {}).get("status") or "unknown")
        access = ((case.get("external_access") or {}).get("status") or "unknown")
        source_interp = ((case.get("source_interpretation") or {}).get("status") or "unknown_origin")
        by_same_data[same] = by_same_data.get(same, 0) + 1
        by_access[access] = by_access.get(access, 0) + 1
        by_source_interpretation[source_interp] = by_source_interpretation.get(source_interp, 0) + 1
    obj = {
        "kind": "foreign-data-persistence-cases",
        "analysis_out": str(analysis_out),
        "token": token,
        "filters": filters,
        "selection_policy": "deterministic FDP evidence candidates only: source_side + enriched local_persistence + external_access + enriched same_data_link + coarse source_interpretation; no risk/violation or business-source ownership decision is made",
        "ordering_policy": "default priority: external_access observed first, then source_interpretation priority, same_data_link strength, persistent write refs and saved attributes",
        "risk_decision": "not_made_by_analyzer",
        "scope_policy": "source_to_storage roots from test_code are excluded; test/mock verify writes are not promoted into production FDP cases through shared DAO/table access; local collection/map mutations such as add/put/remove are not used as FDP roots unless the target looks like a real persistent boundary",
        "total_count": len(all_cases),
        "matched_count": len(filtered_cases),
        "included_count": len(cases),
        "omitted_count": max(0, len(filtered_cases) - len(cases)),
        "by_same_data_link_status": by_same_data,
        "by_external_access_status": by_access,
        "by_source_interpretation_status": by_source_interpretation,
        "fdp_source_origin_summary": _fdp_source_origin_summary(filtered_cases),
        "local_persistence_summary": _fdp_local_persistence_summary(filtered_cases),
        "same_data_field_summary": _fdp_same_data_field_summary(filtered_cases),
        "fdp_chain_completeness_summary": _fdp_chain_completeness_summary(filtered_cases),
        "fdp_evidence_maturity_summary": _fdp_evidence_maturity_summary(filtered_cases),
        "materialization_performance": {
            "cache_hit": False,
            "cache_key": cache_key,
            "input_load_seconds": round(load_seconds, 4),
            "case_build_seconds": round(case_seconds, 4),
            "total_materialization_seconds": round(time.perf_counter() - materialization_started, 4),
            "loaded_access_items": len(access_items),
            "loaded_mapping_items": len(mappings),
            "loaded_flow_items": len(flows),
        },
        "cases": cases,
    }
    write_lazy(analysis_out, "foreign-data-persistence-cases", cache_key, obj)
    return obj


def foreign_data_persistence_case_detail(analysis_out: Path, case_id: str, token: str = "", *, deps: FdpViewDependencies | None = None) -> dict[str, Any]:
    view = foreign_data_persistence_cases(analysis_out, token=token, max_results=1, case_id=case_id, deps=deps)
    case = (view.get("cases") or [None])[0]
    return {
        "kind": "foreign-data-persistence-case-detail",
        "analysis_out": str(analysis_out),
        "case_id": case_id,
        "found": case is not None,
        "selection_policy": "single FDP case with enriched persistence/write refs, saved attributes and same-data field evidence where available",
        "case": case,
    }

