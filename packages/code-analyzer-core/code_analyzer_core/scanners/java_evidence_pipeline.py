from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from code_analyzer_core.models import EvidenceRef, Fact
from code_analyzer_core.evidence_contract import maturity_props as _maturity_props, candidate_signal as _candidate_signal

def _storage_resolution_level_for_access(access: dict[str, Any]) -> str:
    return str(access.get("storage_resolution_level") or "unresolved")



def _candidate_signals_for_access(access: dict[str, Any]) -> list[dict[str, Any]]:
    level = _storage_resolution_level_for_access(access)
    target = ".".join(x for x in [str(access.get("receiver_expression") or access.get("table_or_repository") or ""), str(access.get("storage_method") or "")] if x).strip(".")
    if access.get("access_kind") not in {"write", "mutation"}:
        return []
    if level == "custom_dao_boundary":
        return [_candidate_signal(
            signal_type="custom_dao_persistence_boundary",
            target=target or None,
            basis="DAO/repository-like receiver with domain mutating method; implementation/mapper not resolved by analyzer",
            recommended_action="find DAO implementation, mapper XML, SQL resource, or inspect targeted source before treating as persistent storage evidence",
            related_evidence_refs=[str(access.get("storage_access_id") or "")],
        )]
    if level == "known_storage_api_or_framework_method":
        return [_candidate_signal(
            signal_type="known_storage_api_boundary",
            target=target or None,
            basis="known storage-like method observed; exact physical storage/field mapping may still be unresolved",
            recommended_action="inspect call target or SQL/mapper details if physical storage or field mapping is decision-blocking",
            related_evidence_refs=[str(access.get("storage_access_id") or "")],
        )]
    return []


def _persistence_maturity_for_access(access: dict[str, Any]) -> str:
    if access.get("access_kind") != "write" or access.get("writes_new_payload") is False:
        return "not_applicable"
    level = _storage_resolution_level_for_access(access)
    if level in {"confirmed_sql", "resolved_mapper_sql", "resolved_dao_implementation", "confirmed_bytecode_storage_api"}:
        return "confirmed"
    return "unresolved"


def _physical_storage_maturity_for_access(access: dict[str, Any]) -> str:
    if access.get("access_kind") != "write" or access.get("writes_new_payload") is False:
        return "not_applicable"
    target = str(access.get("table_or_repository") or "")
    receiver = str(access.get("receiver_expression") or "")
    level = _storage_resolution_level_for_access(access)
    if level == "confirmed_sql" and target and target != receiver:
        return "confirmed"
    if level in {"resolved_mapper_sql", "resolved_dao_implementation", "confirmed_bytecode_storage_api"}:
        return "confirmed"
    return "unresolved"


def _source_boundary_maturity(source_kind: str | None) -> str:
    kind = str(source_kind or "unknown")
    if kind in {"rest_ingress", "kafka_consumed", "external_service_response", "file_input", "message_queue"}:
        return "confirmed"
    if kind in {"storage_read", "cache_read", "computed", "constant"}:
        return "not_applicable"
    return "unresolved"


def _field_mapping_maturity(*, lineage_level: str | None, source_field: str | None, saved_object_field: str | None, storage_field: str | None, missing_links: list[str] | None) -> str:
    missing = set(missing_links or [])
    if "field_mapping_not_resolved" in missing or "source_field_not_resolved" in missing or "storage_field_not_resolved" in missing:
        return "unresolved"
    if lineage_level == "field" and source_field and (saved_object_field or storage_field):
        return "confirmed"
    return "unresolved"


def _end_to_end_trace_maturity(source_kind: str | None, source_operation: str | None, storage_operation: str | None) -> str:
    kind = str(source_kind or "unknown")
    if kind in {"storage_read", "cache_read", "computed", "constant"}:
        return "not_applicable"
    if kind in {"rest_ingress", "kafka_consumed", "external_service_response"} and source_operation and storage_operation:
        return "confirmed"
    return "unresolved"


def _field_mapping_gap_diagnostic(*, storage_access: dict[str, Any], saved_object: str | None, saved_object_field: str | None, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = str(storage_access.get("payload_expression") or "")
    method = str(storage_access.get("storage_method") or "")
    extra = extra or {}
    if extra.get("mapper_expression") or re.search(r"\.convert\s*\(|\.map\s*\(", payload):
        blocker = "mapper_or_converter_result_not_resolved"
        hints = ["resolve converter implementation", "extract field mappings inside converter/map method"]
    elif re.search(r"^[A-Za-z_][A-Za-z0-9_]*$", payload):
        blocker = "saved_payload_variable_assignment_not_resolved"
        hints = ["track assignments to saved payload variable", "look for setter/builder/constructor/copyProperties before storage call"]
    elif "new " in payload:
        blocker = "inline_constructor_or_builder_not_resolved"
        hints = ["parse constructor arguments or builder chain used as DAO argument"]
    elif method.lower() in {"save", "saveall", "merge", "persist", "insert", "update"}:
        blocker = "known_storage_api_payload_mapping_not_resolved"
        hints = ["resolve saved argument expression to local object or collection element"]
    else:
        blocker = "unsupported_or_dynamic_mapping_pattern"
        hints = ["manual check or targeted analyzer extension required only if pattern is frequent"]
    return {
        "lineage_blocker": blocker,
        "lineage_diagnostic": {
            "blocker": blocker,
            "saved_object": saved_object or "unknown",
            "saved_object_field": saved_object_field,
            "payload_expression": payload or None,
            "storage_method": method or None,
            "hints": hints,
            "policy": "diagnostic_only_do_not_upgrade_to_risk",
        },
    }


def _op_symbol_and_callable(operation: str | None) -> tuple[str | None, str | None]:
    value = str(operation or "").strip()
    if not value:
        return None, None
    parts = value.split(".")
    if len(parts) >= 2:
        return parts[-2], parts[-1]
    return value, None


def _source_inspection_request_fact(
    request_id: str,
    *,
    reason: str,
    priority: str,
    target_operation: str | None,
    focus: str,
    related_evidence_refs: list[str] | None = None,
    storage_access: dict[str, Any] | None = None,
    source_payload: str | None = None,
    saved_object: str | None = None,
    saved_field: str | None = None,
    trigger_blockers: list[str] | None = None,
    evidence: list[EvidenceRef] | None = None,
    expected_observations: list[str] | None = None,
    tokens: list[str] | None = None,
) -> Fact:
    """Describe a controlled read-only source inspection step for the LLM.

    This is intentionally not another analyzer resolver.  It is a handoff point:
    when static evidence is not mature enough, the prompt can request a narrow source slice via the evidence access API instead of searching the repository blindly.
    """
    access = storage_access or {}
    symbol, callable_name = _op_symbol_and_callable(target_operation)
    method = str(access.get("storage_method") or "") or None
    receiver = str(access.get("receiver_expression") or access.get("table_or_repository") or "") or None
    token_items = []
    for item in [source_payload, saved_object, saved_field, receiver, method, *(tokens or [])]:
        value = str(item or "").strip()
        if value and value not in token_items:
            token_items.append(value)
    suggested_evidence_tools: list[dict[str, Any]] = []

    def _suggested_tool(
        *,
        purpose: str,
        evidence_tool: str,
        positional_args: list[str] | None = None,
        options: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        args = [str(x) for x in (positional_args or []) if str(x).strip()]
        opts = {str(k): str(v) for k, v in (options or {}).items() if str(v).strip()}
        return {
            "purpose": purpose,
            "evidence_tool": evidence_tool,
            "arguments": {**({"token": args[0]} if args else {}), **opts},
            "static_analysis_output_required": True,
            "execution_mode": "evidence_access_api",
        }

    if symbol and callable_name:
        suggested_evidence_tools.append(_suggested_tool(
            purpose="open_target_method",
            evidence_tool="callable",
            options={"symbol": symbol, "callable": callable_name},
        ))
    for token in token_items[:6]:
        suggested_evidence_tools.append(_suggested_tool(
            purpose="targeted_source_search",
            evidence_tool="source-inspect",
            positional_args=[token],
        ))
    implementation_target = next((x for x in token_items if x[:1].isupper() and any(t in x.lower() for t in ("dao", "repository", "repo"))), None)
    if not implementation_target and receiver and receiver[:1].isupper():
        implementation_target = receiver
    if implementation_target and method:
        suggested_evidence_tools.append(_suggested_tool(
            purpose="find_possible_dao_implementation",
            evidence_tool="find-implementations",
            positional_args=[f"{implementation_target}.{method}"],
        ))
    iterative_follow_up_policy = {
        "enabled": True,
        "principle": "If a targeted source inspection reveals that the answer moved to another concrete converter/helper/DAO/mapper/file/line, request one more targeted inspection for that concrete target instead of finalizing the gap immediately.",
        "allowed_follow_up_tools": [
            "source_inspect with token=<ClassOrSymbol.methodOrToken>",
            "source_open with file_path=<relative-file-path>, line=<line>",
            "find_implementations with token=<InterfaceOrType.method>",
            "search with token=<exact-token>",
        ],
        "stop_rules": [
            "stop when the gap is confirmed/resolved",
            "stop when the inspected snippet proves the mapping/source/DAO evidence is not visible in this repository",
            "stop when the next target is not concrete enough and only broad repository scanning would remain",
        ],
    }
    props = {
        "source_inspection_request_id": request_id,
        "request_type": "targeted_source_inspection",
        "status": "pending_llm_source_inspection",
        "reason": reason,
        "priority": priority,
        "target_operation": target_operation,
        "target_symbol": symbol,
        "target_callable": callable_name,
        "focus": focus,
        "source_payload": source_payload,
        "saved_object": saved_object,
        "saved_field": saved_field,
        "storage_target": access.get("table_or_repository"),
        "storage_method": access.get("storage_method"),
        "payload_expression": access.get("payload_expression"),
        "receiver_expression": access.get("receiver_expression"),
        "related_evidence_refs": [x for x in (related_evidence_refs or []) if x],
        "trigger_blockers": trigger_blockers or [],
        "expected_observations": expected_observations or [],
        "search_tokens": token_items[:10],
        "suggested_evidence_tools": suggested_evidence_tools,
        "inspection_policy": "read_only_targeted_code_check_do_not_scan_whole_repo_blindly",
        "iterative_follow_up_policy": iterative_follow_up_policy,
        "llm_evidence_rule": "If source inspection resolves a gap, cite it as llm_source_inspection evidence distinct from analyzer-confirmed evidence. If inspection points to another concrete symbol/file/line, request a follow-up targeted inspection before finalizing unresolved gaps.",
    }
    return Fact(
        fact_type="source_inspection_request",
        name=f"inspect source for {reason}: {target_operation or 'unknown'}",
        properties={k: v for k, v in props.items() if v is not None},
        evidence=evidence or [],
    )


def _inspection_key(reason: str, operation: str | None, access: dict[str, Any] | None = None, saved_object: str | None = None) -> tuple[str, str, str, str, str]:
    access = access or {}
    return (
        reason,
        str(operation or ""),
        str(access.get("receiver_expression") or access.get("table_or_repository") or ""),
        str(access.get("storage_method") or ""),
        str(saved_object or ""),
    )


def _fact_stable_ids(fact: Fact) -> list[str]:
    props = fact.properties or {}
    keys = [
        "persistent_write_id",
        "read_from_storage_id",
        "access_boundary_id",
        "storage_to_access_lineage_id",
        "stored_field_to_response_field_mapping_id",
        "source_to_storage_lineage_id",
        "storage_lineage_gap_id",
        "storage_access_id",
        "data_source_id",
        "source_inspection_request_id",
    ]
    out: list[str] = []
    for key in keys:
        value = props.get(key)
        if isinstance(value, str) and value.strip() and value not in out:
            out.append(value)
    return out


def _attach_source_inspection_links(facts: list[Fact]) -> None:
    """Link actionable unresolved gaps to emitted source_inspection_request facts.

    Gap lifecycle and source inspection requests are produced by different passes.
    This final enrichment makes the contract explicit for LLM prompts: if a gap is
    decision-blocking and actionable, the lifecycle says which request(s) were
    emitted to resolve it.
    """
    request_by_related: dict[str, list[str]] = defaultdict(list)
    all_request_ids: list[str] = []
    for fact in facts:
        if fact.fact_type != "source_inspection_request":
            continue
        props = fact.properties or {}
        rid = str(props.get("source_inspection_request_id") or "")
        if not rid:
            continue
        all_request_ids.append(rid)
        for ref in props.get("related_evidence_refs") or []:
            if isinstance(ref, str) and ref.strip():
                request_by_related[ref.strip()].append(rid)

    for fact in facts:
        props = fact.properties or {}
        lifecycle = props.get("unresolved_gap_lifecycle")
        if not isinstance(lifecycle, list) or not lifecycle:
            continue
        fact_ids = _fact_stable_ids(fact)
        linked: list[str] = []
        for fid in fact_ids:
            for rid in request_by_related.get(fid, []):
                if rid not in linked:
                    linked.append(rid)
        any_required = False
        for item in lifecycle:
            if not isinstance(item, dict):
                continue
            if not item.get("source_inspection_required"):
                continue
            any_required = True
            item["source_inspection_request_ids"] = linked
            item["source_inspection_request_status"] = "emitted" if linked else "required_but_not_emitted"
            if linked:
                item["reason"] = "decision-blocking unresolved gap has emitted targeted source inspection request(s)"
        props["source_inspection_request_ids"] = linked
        props["source_inspection_required"] = any_required
        props["source_inspection_request_status"] = "emitted" if linked else ("required_but_not_emitted" if any_required else "not_required")
