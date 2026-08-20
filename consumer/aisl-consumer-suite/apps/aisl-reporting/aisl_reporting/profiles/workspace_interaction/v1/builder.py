from __future__ import annotations

from collections import Counter, defaultdict
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterable, Mapping

from ....contracts import REPORT_DATASET_SCHEMA, ReportRequest
from ....files import canonical_json, sha256_text


_DETAIL_LIMITS = {
    "executive": {"fields": 12, "interactions": 20},
    "standard": {"fields": 40, "interactions": 60},
    "detailed": {"fields": 120, "interactions": 200},
}


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _stable_values(values: Iterable[Any]) -> list[str]:
    return sorted({str(value).strip() for value in values if str(value or "").strip()})


def _portable_path(value: Any) -> str:
    raw = str(value or "").strip().replace("\\", "/")
    if not raw:
        return ""
    path = Path(raw)
    if not path.is_absolute():
        return raw.lstrip("./")
    parts = list(path.parts)
    for marker in ("src", "resources", "config", "workflow"):
        if marker in parts:
            return "/".join(parts[parts.index(marker) :])
    return path.name


def _portableize(value: Any, *, key: str = "") -> Any:
    if isinstance(value, Mapping):
        return {str(k): _portableize(v, key=str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [_portableize(item, key=key) for item in value]
    if isinstance(value, tuple):
        return [_portableize(item, key=key) for item in value]
    if isinstance(value, str) and key.casefold() in {
        "file", "path", "source_path", "relative_file", "repository_path", "source_repository_path",
    }:
        return _portable_path(value)
    return value


def _evidence_id(repo_id: str, path: str, line_start: int | None, line_end: int | None, extractor: str) -> str:
    payload = f"{repo_id}|{path}|{line_start or ''}|{line_end or ''}|{extractor}"
    return "evidence_" + sha256(payload.encode("utf-8")).hexdigest()[:20]


def _as_int(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _add_evidence(
    index: dict[str, dict[str, Any]],
    *,
    repo_id: str,
    path: str,
    line_start: Any = None,
    line_end: Any = None,
    extractor: str = "knowledge-api",
    owner_id: str | None = None,
) -> str | None:
    portable = _portable_path(path)
    if not repo_id or not portable:
        return None
    start = _as_int(line_start)
    end = _as_int(line_end) or start
    evidence_id = _evidence_id(repo_id, portable, start, end, extractor)
    index.setdefault(
        evidence_id,
        {
            "evidence_id": evidence_id,
            "repo_id": repo_id,
            "path": portable,
            "line_start": start,
            "line_end": end,
            "extractor": extractor,
            "maturity": "observed",
            "owner_id": owner_id,
        },
    )
    return evidence_id


def _evidence_refs(
    value: Any,
    *,
    default_repo_id: str,
    owner_id: str | None,
    index: dict[str, dict[str, Any]],
) -> list[str]:
    """Extract only explicit source references already published in Prepared Knowledge."""
    result: set[str] = set()

    def walk(node: Any, repo_id: str) -> None:
        if isinstance(node, Mapping):
            current_repo = str(node.get("repo_id") or node.get("source_repo_id") or repo_id or "").strip()
            path = str(node.get("relative_file") or node.get("source_path") or node.get("file") or node.get("path") or "").strip()
            if path:
                evidence_id = _add_evidence(
                    index,
                    repo_id=current_repo,
                    path=path,
                    line_start=node.get("line_start") or node.get("start_line") or node.get("line"),
                    line_end=node.get("line_end") or node.get("end_line"),
                    extractor=str(node.get("extractor") or "prepared-knowledge"),
                    owner_id=owner_id,
                )
                if evidence_id:
                    result.add(evidence_id)
            for nested in node.values():
                if isinstance(nested, (Mapping, list, tuple)):
                    walk(nested, current_repo)
        elif isinstance(node, (list, tuple)):
            for item in node:
                walk(item, repo_id)

    walk(value, default_repo_id)
    return sorted(result)


def _observed_repository_interaction_summaries(
    repo_ids: Iterable[str],
    boundaries: Iterable[Mapping[str, Any]],
    boundary_interactions: Iterable[Mapping[str, Any]],
    diagnostics: Iterable[Mapping[str, Any]],
    published_coverage: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    coverage_by_repo = {str(item.get("repo_id") or ""): dict(item) for item in published_coverage}
    boundary_rows = [dict(item) for item in boundaries]
    interaction_rows = [dict(item) for item in boundary_interactions]
    diagnostic_rows = [dict(item) for item in diagnostics]
    metadata_by_repo: dict[str, dict[str, Any]] = {}
    for item in boundary_rows:
        repo_id = str(item.get("repo_id") or "")
        if repo_id:
            metadata_by_repo.setdefault(repo_id, {"system_id": item.get("system_id"), "project_id": item.get("project_id")})
    ordered_repo_ids = _stable_values([*repo_ids, *metadata_by_repo, *coverage_by_repo])
    result: list[dict[str, Any]] = []
    for repo_id in ordered_repo_ids:
        own_boundaries = [item for item in boundary_rows if str(item.get("repo_id") or "") == repo_id]
        inbound = sum(1 for item in own_boundaries if str(item.get("direction") or "").casefold() == "inbound")
        outbound = sum(1 for item in own_boundaries if str(item.get("direction") or "").casefold() == "outbound")
        matched = [item for item in interaction_rows if str(item.get("source_repo_id") or "") == repo_id]
        own_diagnostics = [item for item in diagnostic_rows if str(item.get("source_repo_id") or "") == repo_id]
        ambiguous = sum(1 for item in own_diagnostics if str(item.get("match_status") or "").casefold() == "ambiguous")
        unresolved = sum(1 for item in own_diagnostics if str(item.get("match_status") or "").casefold() == "unresolved")
        confirmed = sum(1 for item in matched if str(item.get("confidence") or "").casefold() == "confirmed")
        probable = sum(1 for item in matched if str(item.get("confidence") or "").casefold() == "probable")
        disposed = len(matched) + ambiguous + unresolved
        technical_disposition = "not_applicable" if outbound == 0 else ("complete" if disposed >= outbound else "partial")
        published = coverage_by_repo.get(repo_id, {})
        metadata = metadata_by_repo.get(repo_id, {})
        result.append({
            "repo_id": repo_id,
            "system_id": published.get("system_id") or metadata.get("system_id"),
            "project_id": published.get("project_id") or metadata.get("project_id"),
            "inbound_boundary_count": inbound,
            "outbound_boundary_count": outbound,
            "matched_outbound_count": len(matched),
            "confirmed_outbound_count": confirmed,
            "probable_outbound_count": probable,
            "ambiguous_outbound_count": ambiguous,
            "unresolved_outbound_count": unresolved,
            "technical_matching_disposition_status": technical_disposition,
            "analysis_status": published.get("analysis_status"),
            "coverage_status": published.get("coverage_status"),
            "matching_coverage_status": published.get("matching_coverage_status"),
            "coverage_basis": (
                "published_interaction_coverage_plus_observed_boundary_inventory"
                if published else "observed_boundary_inventory_without_interaction_coverage_mart"
            ),
        })
    return result


def _role_candidates(coverage: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in coverage:
        inbound = int(item.get("inbound_boundary_count") or 0)
        outbound = int(item.get("outbound_boundary_count") or 0)
        if inbound and outbound:
            role, explanation = "integration_hub_candidate", "Наблюдаются входящие и исходящие границы; это допускает роль интеграционного узла, но не устанавливает бизнес-владение."
        elif outbound:
            role, explanation = "interaction_initiator_candidate", "Наблюдаются исходящие границы; репозиторий технически инициирует вызовы в проанализированном контуре."
        elif inbound:
            role, explanation = "interaction_provider_candidate", "Наблюдаются входящие границы; репозиторий предоставляет операции в проанализированном контуре."
        else:
            role, explanation = "role_not_observed", "Интерфейсных границ текущий профиль не наблюдает; это не доказывает отсутствие интеграций."
        result.append({
            "repo_id": item.get("repo_id"), "system_id": item.get("system_id"), "project_id": item.get("project_id"),
            "observed_inbound_boundary_count": inbound, "observed_outbound_boundary_count": outbound,
            "matched_outbound_count": int(item.get("matched_outbound_count") or 0),
            "confirmed_outbound_count": int(item.get("confirmed_outbound_count") or 0),
            "probable_outbound_count": int(item.get("probable_outbound_count") or 0),
            "unresolved_outbound_count": int(item.get("unresolved_outbound_count") or 0),
            "role_candidate": role, "interpretation_status": "candidate", "explanation": explanation,
            "coverage_status": item.get("coverage_status"),
        })
    return result


def _normalized_boundary_paths(boundary: Mapping[str, Any]) -> list[str]:
    value = boundary.get("normalized_paths_json")
    if isinstance(value, list):
        return _stable_values(value)
    payload = _mapping(boundary.get("payload_json"))
    for key in ("normalized_paths", "full_path_variants", "endpoint_path_variants"):
        candidate = payload.get(key)
        if isinstance(candidate, list) and candidate:
            return _stable_values(candidate)
    return []


def _unmatched_inbound_operations(
    boundaries: Iterable[Mapping[str, Any]], boundary_interactions: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    matched_keys: set[tuple[str, str, str, str]] = set()
    for interaction in boundary_interactions:
        repo_id = str(interaction.get("target_repo_id") or "").strip()
        protocol = str(interaction.get("protocol") or "").strip().casefold()
        method = str(interaction.get("http_method") or "").strip().upper()
        path = str(interaction.get("target_ingress_endpoint") or "").strip()
        if repo_id and protocol and path:
            matched_keys.add((repo_id, protocol, method, path))
    grouped: dict[tuple[str, str, str, tuple[str, ...]], dict[str, Any]] = {}
    for boundary in boundaries:
        if str(boundary.get("direction") or "").casefold() != "inbound":
            continue
        repo_id = str(boundary.get("repo_id") or "").strip()
        protocol = str(boundary.get("protocol") or "").strip().casefold()
        method = str(boundary.get("http_method") or "").strip().upper()
        paths = _normalized_boundary_paths(boundary)
        if not repo_id or not protocol or (paths and any((repo_id, protocol, method, path) in matched_keys for path in paths)):
            continue
        key = (repo_id, protocol, method, tuple(paths))
        item = grouped.setdefault(key, {
            "repo_id": repo_id, "protocol": protocol, "http_method": method or None, "normalized_paths": paths,
            "interface_ids": [], "operations": [], "status": "unmatched_inbound",
            "basis": "observed inbound operation signature is not the target of any matched boundary interaction in the workspace",
        })
        if boundary.get("interface_id"):
            item["interface_ids"].append(str(boundary["interface_id"]))
        if boundary.get("operation"):
            item["operations"].append(str(boundary["operation"]))
    result: list[dict[str, Any]] = []
    for item in grouped.values():
        item["interface_ids"] = _stable_values(item["interface_ids"])
        item["operations"] = _stable_values(item["operations"])
        result.append(item)
    return sorted(result, key=lambda item: (str(item.get("repo_id") or ""), str(item.get("protocol") or ""), str(item.get("http_method") or ""), tuple(item.get("normalized_paths") or [])))


def _response_contract_observation(interaction: Mapping[str, Any]) -> dict[str, Any]:
    payload = _mapping(interaction.get("payload_json"))
    source = _mapping(payload.get("outbound_interface"))
    target = _mapping(payload.get("target_ingress_interface"))
    def size(obj: Mapping[str, Any], key: str) -> int:
        value = obj.get(key)
        return len(value) if isinstance(value, list) else 0
    return {
        "source_response_signature_count": size(source, "response_contract_signature"),
        "source_response_candidate_count": size(source, "response_contract_candidates"),
        "target_response_signature_count": size(target, "response_contract_signature"),
        "target_response_candidate_count": size(target, "response_contract_candidates"),
    }


def _grounded_owner_questions(
    boundary_interactions: Iterable[Mapping[str, Any]],
    diagnostics: Iterable[Mapping[str, Any]],
    unmatched_inbound: Iterable[Mapping[str, Any]],
    *,
    confidence_counts: Mapping[str, int],
) -> list[dict[str, Any]]:
    questions: list[dict[str, Any]] = []
    def add(question_id: str, question: str, basis: str) -> None:
        if len(questions) < 15 and not any(item["question"] == question for item in questions):
            questions.append({"question_id": question_id, "question": question, "basis": basis})
    add("Q-BUSINESS-ROLE", "Какое бизнесовое назначение и владение данными закреплено за системами этого workspace?", "Статический анализ показывает технические роли в обмене, но не назначает business owner или source of truth.")
    probable = [item for item in boundary_interactions if str(item.get("confidence") or "") == "probable"]
    for index, item in enumerate(sorted(probable, key=lambda row: (str(row.get("target_repo_id") or ""), str(row.get("target_ingress_endpoint") or "")))[:4], start=1):
        source, target = str(item.get("source_repo_id") or "?"), str(item.get("target_repo_id") or "?")
        method = str(item.get("http_method") or "").strip()
        path = str(item.get("target_ingress_endpoint") or item.get("outbound_endpoint") or "?")
        add(f"Q-PROBABLE-{index}", f"Какой runtime URL/service binding подтверждает маршрут `{method} {path}` из `{source}` в `{target}`?", f"Framework нашёл technical match с confidence=probable; confirmed={confidence_counts.get('confirmed', 0)}, probable={confidence_counts.get('probable', 0)}.")
    unresolved = [item for item in diagnostics if str(item.get("match_status") or "") in {"unresolved", "ambiguous"}]
    for index, item in enumerate(unresolved[:3], start=1):
        paths = [str(value) for value in (item.get("outbound_paths_json") or []) if str(value).strip()]
        path_text = ", ".join(f"`{value}`" for value in paths[:3]) or "без разрешённого path"
        operation = str(item.get("outbound_operation") or item.get("outbound_interface_id") or "unknown operation")
        add(f"Q-UNMATCHED-OUT-{index}", f"Какая внешняя система должна принимать outbound `{operation}` ({path_text})?", f"Операция имеет match_status={item.get('match_status') or 'unresolved'} и не образует межрепозиторный interaction.")
    for index, item in enumerate(list(unmatched_inbound)[:2], start=1):
        paths = ", ".join(f"`{value}`" for value in (item.get("normalized_paths") or [])[:3]) or "без path"
        add(f"Q-UNMATCHED-IN-{index}", f"Какие клиенты workspace или внешние системы вызывают inbound {paths} в `{item.get('repo_id')}`?", "Inbound operation наблюдается, но ни один matched boundary interaction текущего workspace на неё не указывает.")
    for index, item in enumerate(boundary_interactions, start=1):
        observation = _response_contract_observation(item)
        source_known = observation["source_response_signature_count"] or observation["source_response_candidate_count"]
        target_known = observation["target_response_signature_count"] or observation["target_response_candidate_count"]
        if source_known and target_known:
            continue
        source, target = str(item.get("source_repo_id") or "?"), str(item.get("target_repo_id") or "?")
        method = str(item.get("http_method") or "").strip()
        path = str(item.get("target_ingress_endpoint") or item.get("outbound_endpoint") or "?")
        add(f"Q-RESPONSE-{index}", f"Какой фактический response contract связывает `{target}` и `{source}` для `{method} {path}`?", "Bilateral response-field correspondence не установлен текущим interaction knowledge.")
    add("Q-ATTRIBUTE-IDENTITY", "Какие одноимённые поля в request/response contracts действительно являются одним бизнес-атрибутом, а какие лишь технически совпадают по wire path?", "Framework публикует technical correspondence, но semantic identity остаётся отдельной интерпретацией.")
    return questions[:15]


def build_dataset(request: ReportRequest) -> dict[str, Any]:
    source = request.knowledge_source
    if source is None:
        raise ValueError("workspace-interaction/v1 requires a resolved Knowledge API revision")

    system_interactions = source.list_system_interactions(max_results=5000)
    boundary_interactions = source.list_system_boundary_interactions(max_results=5000)
    boundaries = source.list_repository_interaction_boundaries(max_results=20_000)
    execution_contexts = source.list_system_interaction_execution_contexts(max_results=5000)
    field_contracts = source.list_system_interaction_field_contracts(max_results=20_000)
    diagnostics = source.list_system_interaction_diagnostics(max_results=10_000)
    coverage_items = source.list_repository_interaction_coverage(max_results=5000)

    repo_ids = _stable_values([
        *(item.get("repo_id") for item in boundaries),
        *(item.get("repo_id") for item in coverage_items),
        *(item.get("source_repo_id") for item in boundary_interactions),
        *(item.get("target_repo_id") for item in boundary_interactions),
    ])
    if len(repo_ids) < 2:
        raise ValueError("workspace-interaction/v1 requires at least two repositories")
    scope_ids = _stable_values([
        *(item.get("scope_id") for item in system_interactions),
        *(item.get("scope_id") for item in boundary_interactions),
        *(item.get("scope_id") for item in boundaries),
        *(item.get("scope_id") for item in coverage_items),
    ])
    if len(scope_ids) > 1:
        raise ValueError(f"workspace-interaction/v1 received multiple scope_ids: {scope_ids}")
    scope_id = scope_ids[0] if scope_ids else str(request.system_id or "workspace")

    summaries = _observed_repository_interaction_summaries(repo_ids, boundaries, boundary_interactions, diagnostics, coverage_items)
    contracts_by_boundary: dict[str, list[dict[str, Any]]] = defaultdict(list)
    contexts_by_boundary: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in field_contracts:
        contracts_by_boundary[str(item.get("boundary_interaction_id") or "")].append(item)
    for item in execution_contexts:
        contexts_by_boundary[str(item.get("boundary_interaction_id") or "")].append(item)
    for values in contracts_by_boundary.values():
        values.sort(key=lambda item: (str(item.get("wire_path") or ""), str(item.get("field_contract_id") or "")))

    evidence_index: dict[str, dict[str, Any]] = {}
    limits = _DETAIL_LIMITS[request.detail_level]
    selected_interactions = boundary_interactions[: limits["interactions"]]
    business_interactions: list[dict[str, Any]] = []
    top_level_fields: Counter[str] = Counter()
    for interaction in selected_interactions:
        boundary_id = str(interaction.get("boundary_interaction_id") or "")
        contracts = contracts_by_boundary.get(boundary_id, [])
        selected_contracts: list[dict[str, Any]] = []
        interaction_evidence = set(_evidence_refs(
            {"payload": interaction.get("payload_json"), "provenance": interaction.get("provenance_json")},
            default_repo_id=str(interaction.get("source_repo_id") or ""), owner_id=boundary_id, index=evidence_index,
        ))
        for contract in contracts[: limits["fields"]]:
            wire_path = str(contract.get("wire_path") or "")
            if wire_path:
                top_level_fields[wire_path.split(".", 1)[0]] += 1
            field_evidence = _evidence_refs(
                {"payload": contract.get("payload_json"), "provenance": contract.get("provenance_json")},
                default_repo_id=str(contract.get("source_repo_id") or ""), owner_id=str(contract.get("field_contract_id") or ""), index=evidence_index,
            )
            interaction_evidence.update(field_evidence)
            selected_contracts.append({
                "field_contract_id": contract.get("field_contract_id"), "wire_path": contract.get("wire_path"),
                "source_field_path": contract.get("outbound_field_path"), "target_field_path": contract.get("target_field_path"),
                "source_payload_type": contract.get("outbound_payload_type"), "target_payload_type": contract.get("target_payload_type"),
                "source_field_type": contract.get("outbound_field_type"), "target_field_type": contract.get("target_field_type"),
                "match_kind": contract.get("match_kind"), "match_status": contract.get("match_status"),
                "type_compatibility": contract.get("type_compatibility"), "evidence_ids": field_evidence,
            })
        contexts = contexts_by_boundary.get(boundary_id, [])
        for context in contexts:
            interaction_evidence.update(_evidence_refs(
                {"payload": context.get("payload_json"), "provenance": context.get("provenance_json")},
                default_repo_id=str(context.get("source_repo_id") or ""), owner_id=str(context.get("execution_context_id") or ""), index=evidence_index,
            ))
        basis = _mapping(interaction.get("match_basis_json"))
        contract_basis = _mapping(basis.get("contract"))
        limitations: list[str] = []
        if str(interaction.get("confidence") or "") != "confirmed": limitations.append("interaction_not_confirmed")
        if str(interaction.get("local_execution_status") or "") != "confirmed": limitations.append("local_execution_context_not_confirmed")
        if not contracts: limitations.append("field_contracts_not_materialized")
        elif any(str(item.get("match_status") or "") != "confirmed" for item in contracts): limitations.append("field_contracts_include_probable_candidates")
        business_interactions.append({
            "boundary_interaction_id": boundary_id, "interaction_id": interaction.get("interaction_id"),
            "source_repo_id": interaction.get("source_repo_id"), "source_operation": interaction.get("outbound_operation"),
            "source_payload_type": contract_basis.get("outbound_request_payload_type"),
            "target_repo_id": interaction.get("target_repo_id"), "target_operation": interaction.get("target_ingress_operation"),
            "target_payload_type": contract_basis.get("inbound_request_payload_type"),
            "protocol": interaction.get("protocol"), "http_method": interaction.get("http_method"),
            "source_endpoint": interaction.get("outbound_endpoint"), "target_endpoint": interaction.get("target_ingress_endpoint"),
            "match_status": interaction.get("match_status"), "confidence": interaction.get("confidence"),
            "local_execution_status": interaction.get("local_execution_status"), "match_basis": basis,
            "field_contracts": selected_contracts, "field_contract_count": len(contracts),
            "data_groups": _stable_values(str(item.get("wire_path") or "").split(".", 1)[0] for item in contracts),
            "execution_contexts": [{
                "execution_context_id": item.get("execution_context_id"), "trigger_kind": item.get("trigger_kind"),
                "source_ingress_operation": item.get("source_ingress_operation"), "source_ingress_endpoint": item.get("source_ingress_endpoint"),
                "path_status": item.get("path_status"), "call_chain_length": item.get("call_chain_length"),
            } for item in contexts],
            "limitations": limitations, "evidence_ids": sorted(interaction_evidence),
        })

    confidence_counts = Counter(str(item.get("confidence") or "unknown") for item in boundary_interactions)
    protocol_counts = Counter(str(item.get("protocol") or "unknown") for item in boundary_interactions)
    diagnostic_counts = Counter(str(item.get("match_status") or "unknown") for item in diagnostics)
    boundary_direction_counts = Counter(str(item.get("direction") or "unknown") for item in boundaries)
    unmatched_outbound = [item for item in diagnostics if str(item.get("match_status") or "") in {"unresolved", "ambiguous"}]
    unmatched_inbound = _unmatched_inbound_operations(boundaries, boundary_interactions)
    questions = _grounded_owner_questions(boundary_interactions, unmatched_outbound, unmatched_inbound, confidence_counts=confidence_counts)

    coverage_summary = {
        "repository_count": len(repo_ids),
        "analysis_status_counts": dict(sorted(Counter(str(item.get("analysis_status") or "unknown") for item in coverage_items).items())),
        "coverage_status_counts": dict(sorted(Counter(str(item.get("coverage_status") or "unknown") for item in coverage_items).items())),
        "matching_coverage_status_counts": dict(sorted(Counter(str(item.get("matching_coverage_status") or "unknown") for item in coverage_items).items())),
        "inbound_boundary_count": sum(int(item.get("inbound_boundary_count") or 0) for item in summaries),
        "outbound_boundary_count": sum(int(item.get("outbound_boundary_count") or 0) for item in summaries),
        "matched_outbound_count": sum(int(item.get("matched_outbound_count") or 0) for item in summaries),
        "confirmed_outbound_count": sum(int(item.get("confirmed_outbound_count") or 0) for item in summaries),
        "probable_outbound_count": sum(int(item.get("probable_outbound_count") or 0) for item in summaries),
        "ambiguous_outbound_count": sum(int(item.get("ambiguous_outbound_count") or 0) for item in summaries),
        "unresolved_outbound_count": sum(int(item.get("unresolved_outbound_count") or 0) for item in summaries),
        "boundary_interaction_count": len(boundary_interactions), "field_contract_count": len(field_contracts),
        "execution_context_count": len(execution_contexts), "diagnostic_status_counts": dict(sorted(diagnostic_counts.items())),
        "published_interaction_coverage_available": bool(coverage_items),
        "count_basis": "counts are derived from canonical interaction boundaries, boundary interactions, field contracts, execution contexts and diagnostics exposed by Knowledge API",
    }

    architecture_facts = [
        {"fact_id": "ARCH-PROTOCOLS", "fact": "Наблюдаемые межсистемные взаимодействия сгруппированы по протоколам.", "values": dict(sorted(protocol_counts.items())), "interpretation_status": "observed"},
        {"fact_id": "ARCH-CONFIDENCE", "fact": "Уровни уверенности boundary interactions сохраняются без повышения статуса.", "values": dict(sorted(confidence_counts.items())), "interpretation_status": "observed"},
        {"fact_id": "ARCH-EXECUTION-CONTEXT", "fact": "Execution context является дополнительным контекстом и не является условием существования boundary interaction.", "values": {"boundary_interaction_count": len(boundary_interactions), "execution_context_count": len(execution_contexts)}, "interpretation_status": "observed"},
    ]

    sections = {
        "workspace_overview": {"scope_id": scope_id, "repository_ids": repo_ids, "repositories": summaries, "capabilities": list(source.capabilities)},
        "repository_roles": {"items": _role_candidates(summaries), "policy": "Roles are technical interpretation candidates derived from observed boundaries; business ownership is not inferred."},
        "business_interactions": {"items": business_interactions, "total_count": len(boundary_interactions), "confidence_counts": dict(sorted(confidence_counts.items())), "protocol_counts": dict(sorted(protocol_counts.items())), "selection_truncated": len(boundary_interactions) > len(business_interactions)},
        "data_exchange": {"top_level_field_groups": [{"field_group": name, "field_contract_count": count} for name, count in sorted(top_level_fields.items(), key=lambda item: (-item[1], item[0]))], "field_contract_count": len(field_contracts), "policy": "Field contracts are technical correspondence evidence; semantic identity and business ownership require explicit confirmation."},
        "architecture_observations": {"items": architecture_facts},
        "diagrams": {
            "nodes": [{"node_id": item.get("repo_id"), "label": item.get("system_id") or item.get("repo_id"), "kind": "repository"} for item in summaries],
            "interaction_edges": [{
                "edge_id": item.get("boundary_interaction_id"), "from": item.get("source_repo_id"), "to": item.get("target_repo_id"),
                "protocol": item.get("protocol"), "operation": f"{item.get('http_method') or ''} {item.get('target_ingress_endpoint') or item.get('outbound_endpoint') or ''}".strip(),
                "source_operation": item.get("outbound_operation"), "target_operation": item.get("target_ingress_operation"),
                "confidence": item.get("confidence"), "match_status": item.get("match_status"),
                "field_contract_count": len(contracts_by_boundary.get(str(item.get("boundary_interaction_id") or ""), [])),
            } for item in boundary_interactions],
        },
        "coverage_and_limitations": {
            "summary": coverage_summary, "repositories": summaries, "published_interaction_coverage": coverage_items,
            "unmatched_or_ambiguous_outbound_operations": unmatched_outbound[:200], "unmatched_inbound_operations": unmatched_inbound[:200],
            "boundary_direction_counts": dict(sorted(boundary_direction_counts.items())),
            "rules": ["not_observed does not mean absent in the source system", "probable must not be rewritten as confirmed", "an unresolved execution context does not invalidate an independently matched boundary interaction", "counts are diagnostic occurrences, not accuracy percentages"],
        },
        "owner_questions": questions,
        "technical_appendix": {"system_interactions": system_interactions},
    }
    dataset: dict[str, Any] = {
        "schema_version": REPORT_DATASET_SCHEMA, "profile_id": request.profile_id, "request": request.to_dataset_dict(),
        "scope": {"kind": "workspace", "id": scope_id, "repository_ids": repo_ids}, "coverage": coverage_summary,
        "sections": sections, "evidence_index": evidence_index if request.include_evidence else {},
        "interpretation_policy": {
            "business_first": "Start with the contour, technical roles, operations and data groups.",
            "boundary_interaction": "Use source outbound to target inbound as the canonical interaction fact; execution context is optional context.",
            "confidence": "Preserve confirmed/probable/ambiguous/unresolved exactly.",
            "attribute_identity": "Same wire path or name is technical correspondence, not automatic semantic identity or origin proof.",
            "repository_role": "Observed technical role may be described; business ownership remains an interpretation or owner question.",
            "absence": "Missing or not_observed evidence is not proof of absence in the source system.",
            "parked_scope": "Direct value-flow graph and attribute-path resolution are not part of this active report profile.",
        },
    }
    dataset = _portableize(dataset)
    dataset["dataset_fingerprint"] = sha256_text(canonical_json(dataset))
    return dataset
