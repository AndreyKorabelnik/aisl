from __future__ import annotations

import re
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Mapping

import yaml

from ....contracts import REPORT_DATASET_SCHEMA, ReportRequest
from ....files import canonical_json, sha256_text

_TOKEN_SPLIT = re.compile(r"[^A-Za-zА-Яа-я0-9]+")
_CAMEL_BOUNDARY = re.compile(r"(?<=[a-zа-я0-9])(?=[A-ZА-Я])")
_STOP_TOKENS = {
    "abstract", "adapter", "api", "app", "application", "async", "base", "batch", "bean",
    "between", "by", "channel", "client", "common", "config", "configuration", "consume",
    "consumer", "controller", "create", "data", "default", "delete", "dto", "enable",
    "event", "external", "factory", "find", "get", "handler", "http", "impl",
    "implementation", "inbound", "info", "internal", "java", "job", "kafka", "list",
    "local", "manager", "message", "messages", "method", "model", "name", "object",
    "operation", "outbound", "parameters", "placeholder", "post", "process", "processor",
    "producer", "provider", "publish", "publisher", "receive", "received", "receiver",
    "request", "response", "rest", "root", "save", "schema", "send", "sender", "server",
    "service", "set", "spring", "state", "string", "table", "tables", "task", "topic",
    "unknown", "update", "v1", "v2",
    # Generic Russian structural words can appear in database comments and must not
    # become business capability or data-domain labels.
    "данные", "имя", "история", "объект", "операция", "поле", "связь", "таблица",
}

_VOWELS = frozenset("aeiouyаеёиоуыэюя")


def _canonical_token(token: str) -> str:
    """Normalize simple English plurals without introducing a language-specific stemmer."""
    if len(token) > 5 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 4 and token.endswith("s") and not token.endswith(("ss", "us", "is")):
        return token[:-1]
    return token


def _is_semantic_token(token: str) -> bool:
    """Reject short identifier-like acronyms from business grouping.

    Product/system abbreviations are valid evidence, but an acronym alone is not a
    stable business capability label. It remains available in the underlying catalog.
    """
    return len(token) >= 3 and any(char in _VOWELS for char in token)

@lru_cache(maxsize=1)
def _audience_policies() -> dict[str, dict[str, Any]]:
    payload = yaml.safe_load(Path(__file__).with_name("audience-policy.yaml").read_text(encoding="utf-8")) or {}
    required = {"business", "architecture", "engineering"}
    missing = sorted(required - set(payload))
    if missing:
        raise ValueError(f"system-description audience policy is incomplete: {missing}")
    return {str(key): dict(value or {}) for key, value in payload.items()}


def _merge_evidence(results: Iterable[Mapping[str, Any]], referenced_ids: set[str]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for result in results:
        for ref in result.get("evidence") or ():
            if not isinstance(ref, Mapping):
                continue
            evidence_id = str(ref.get("evidence_id") or "")
            if evidence_id and evidence_id in referenced_ids:
                index[evidence_id] = dict(ref)
    return index


def _referenced_evidence_ids(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "evidence_ids" and isinstance(item, list):
                found.update(str(v) for v in item if str(v))
            else:
                found.update(_referenced_evidence_ids(item))
    elif isinstance(value, list):
        for item in value:
            found.update(_referenced_evidence_ids(item))
    return found


def _focus_match(item: Mapping[str, Any], terms: tuple[str, ...]) -> bool:
    if not terms:
        return True
    text = canonical_json(item).lower()
    return any(term.lower() in text for term in terms)


def _tokens(*values: Any) -> tuple[str, ...]:
    found: list[str] = []
    for value in values:
        if isinstance(value, (list, tuple, set)):
            found.extend(_tokens(*value))
            continue
        text = _CAMEL_BOUNDARY.sub(" ", str(value or ""))
        for raw in _TOKEN_SPLIT.split(text):
            token = _canonical_token(raw.casefold().strip())
            if len(token) < 3 or token.isdigit() or token in _STOP_TOKENS:
                continue
            if token not in found:
                found.append(token)
    return tuple(found)


def _evidence_lookup(results: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for result in results:
        for ref in result.get("evidence") or ():
            if not isinstance(ref, Mapping):
                continue
            evidence_id = str(ref.get("evidence_id") or "")
            if evidence_id:
                lookup[evidence_id] = dict(ref)
    return lookup


def _display_ref(ref: Mapping[str, Any]) -> str:
    path = str(ref.get("path") or "")
    start = ref.get("line_start")
    end = ref.get("line_end")
    if start is None:
        return path
    if end is None or end == start:
        return f"{path}:{start}"
    return f"{path}:{start}–{end}"


def _with_provenance(item: Mapping[str, Any], lookup: Mapping[str, Mapping[str, Any]], *, max_refs: int = 3) -> dict[str, Any]:
    result = dict(item)
    refs: list[dict[str, Any]] = []
    for evidence_id in result.get("evidence_ids") or ():
        ref = lookup.get(str(evidence_id))
        if not ref:
            continue
        refs.append({
            "evidence_id": evidence_id,
            "repo_id": ref.get("repo_id"),
            "path": ref.get("path"),
            "line_start": ref.get("line_start"),
            "line_end": ref.get("line_end"),
            "display": _display_ref(ref),
        })
        if len(refs) >= max_refs:
            break
    result["provenance"] = refs
    return result


def _compact_boundary_catalog_item(item: Mapping[str, Any]) -> dict[str, Any]:
    """Keep the complete boundary catalog useful without duplicating evidence payloads.

    Exact provenance is retained in the bounded interface map and representative
    journeys. The full catalog is used for grouping and coverage only.
    """
    keys = (
        "interface_id", "direction", "boundary_kind", "protocol", "operation",
        "http_method", "endpoint_or_topic", "payload_schema", "request_payload_type",
        "response_payload_type", "resolution_status", "evidence_level", "attribute_count",
    )
    return {key: item.get(key) for key in keys if item.get(key) is not None}


def _compact_provenance_item(
    item: Mapping[str, Any],
    lookup: Mapping[str, Mapping[str, Any]],
    *,
    keys: tuple[str, ...],
    max_refs: int = 1,
) -> dict[str, Any]:
    selected = {key: item.get(key) for key in keys if item.get(key) is not None}
    evidence_ids = [str(value) for value in item.get("evidence_ids") or () if str(value)][:max_refs]
    if evidence_ids:
        selected["evidence_ids"] = evidence_ids
    return _with_provenance(selected, lookup, max_refs=max_refs)


def _compact_data_object(item: Mapping[str, Any], lookup: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    keys = (
        "object_id", "repo_id", "module_name", "name", "schema", "qualified_name",
        "description", "object_kind", "source_type", "column_count", "key_count",
        "relationship_count", "observed_relationship_count", "evidence_level",
    )
    return _compact_provenance_item(item, lookup, keys=keys, max_refs=1)


def _compact_table_relationship(item: Mapping[str, Any], lookup: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    keys = (
        "relationship_id", "repo_id", "left_table", "right_table", "relation_kind",
        "join_type", "column_pair_count", "column_pairs", "matched_declared_keys", "source_kind",
    )
    return _compact_provenance_item(item, lookup, keys=keys, max_refs=1)


def _select_declared_dependencies(items: list[dict[str, Any]], limit: int = 40) -> tuple[list[dict[str, Any]], int]:
    aggregated: dict[str, dict[str, Any]] = {}
    priority = {"runtimeOnly": 5, "implementation": 4, "api": 4, "compile": 3, "compileOnly": 2, "annotationProcessor": 1}
    for item in items:
        coordinate = str(item.get("coordinate") or "")
        if not coordinate:
            continue
        current = aggregated.get(coordinate)
        if current is None:
            current = dict(item)
            current["module_paths"] = []
            current["configurations"] = []
            current["evidence_ids"] = []
            aggregated[coordinate] = current
        module = item.get("module_path")
        configuration = item.get("configuration")
        if module and module not in current["module_paths"]:
            current["module_paths"].append(module)
        if configuration and configuration not in current["configurations"]:
            current["configurations"].append(configuration)
        current["evidence_ids"].extend(item.get("evidence_ids") or [])
    selected = list(aggregated.values())
    for item in selected:
        item["module_paths"] = sorted(item["module_paths"])
        item["configurations"] = sorted(item["configurations"])
        item["evidence_ids"] = sorted(set(item["evidence_ids"]))[:3]
        item["selection_score"] = max((priority.get(value, 0) for value in item["configurations"]), default=0)
        item.pop("module_path", None)
        item.pop("configuration", None)
    selected.sort(key=lambda item: (-int(item["selection_score"]), str(item.get("group_id")), str(item.get("artifact_id")), str(item.get("coordinate"))))
    return selected[:limit], len(selected)


def _relationship_is_explicit(item: Mapping[str, Any]) -> bool:
    marker = " ".join(str(item.get(key) or "") for key in ("relation_kind", "source_kind")).casefold()
    return "foreign" in marker or marker.strip() in {"fk", "foreign_key"} or bool(item.get("matched_declared_keys"))


def _deduplicate_json_values(values: Iterable[Any]) -> list[Any]:
    """Deduplicate arbitrary JSON-like values while preserving deterministic output.

    ReportingQueryService may return declared-key matches as either scalar IDs or
    structured dictionaries. Dictionaries and nested lists are not hashable, so a
    plain ``set(values)`` is invalid for real knowledge-layer datasets. Canonical
    JSON provides a stable content key for all supported shapes.
    """

    selected: dict[str, Any] = {}
    for value in values:
        selected.setdefault(canonical_json(value), value)
    return [selected[key] for key in sorted(selected)]


def _deduplicate_relationships(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected: dict[tuple[Any, ...], dict[str, Any]] = {}
    for item in items:
        pair_key = tuple((p.get("left_column"), p.get("operator"), p.get("right_column")) for p in item.get("column_pairs") or [])
        key = (item.get("left_table"), item.get("right_table"), item.get("join_type"), pair_key)
        current = selected.get(key)
        if current is None:
            current = dict(item)
            current["matched_declared_keys"] = _deduplicate_json_values(current.get("matched_declared_keys") or [])
            selected[key] = current
        else:
            current["evidence_ids"] = sorted(set((current.get("evidence_ids") or []) + (item.get("evidence_ids") or [])))[:3]
            current["matched_declared_keys"] = _deduplicate_json_values(
                (current.get("matched_declared_keys") or []) + (item.get("matched_declared_keys") or [])
            )
    values = list(selected.values())
    values.sort(key=lambda item: (not _relationship_is_explicit(item), -len(item.get("matched_declared_keys") or []), -int(item.get("column_pair_count") or 0), str(item.get("left_table")), str(item.get("right_table"))))
    return values


def _select_report_relationships(
    explicit_relationships: list[dict[str, Any]],
    observed_relationships: list[dict[str, Any]],
    detail_level: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    observed_limit = {"executive": 8, "standard": 20, "detailed": 40}[detail_level]
    explicit_limit = (
        len(explicit_relationships)
        if len(explicit_relationships) <= 30
        else {"executive": 12, "standard": 30, "detailed": 60}[detail_level]
    )
    selected_explicit = explicit_relationships[:explicit_limit]
    selected_observed = observed_relationships[:observed_limit]
    return selected_explicit, selected_observed, {
        "explicit_relationship_selection_limit": explicit_limit,
        "observed_join_selection_limit": observed_limit,
        "all_explicit_relationships_selected": len(selected_explicit) == len(explicit_relationships),
        "explicit_relationship_selection_policy": (
            "all_explicit_relationships_when_count_at_most_30/v1"
            if len(explicit_relationships) <= 30
            else "ranked_explicit_relationships_with_detail_level_budget/v1"
        ),
    }


def _rank_data_objects(items: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    values = [dict(item) for item in items]
    values.sort(key=lambda item: (-int(item.get("selection_score") or 0), str(item.get("qualified_name") or item.get("name"))))
    return values[:limit]


def _module_role_hint(item: Mapping[str, Any]) -> dict[str, Any]:
    """Attach a conservative role hint derived only from the module path/name.

    The role remains an interpretation candidate. It is intentionally generic and
    does not contain AT900-specific module names.
    """

    result = dict(item)
    marker = " ".join(
        str(item.get(key) or "") for key in ("module_name", "module_path", "build_file")
    ).casefold()
    if not str(item.get("module_path") or "").strip() or marker.strip() in {".", "root"}:
        role = "агрегация сборки и общие настройки проекта"
    elif any(token in marker for token in ("-api", "_api", "/api", "contracts", "contract")):
        role = "API-контракты, DTO и спецификации интерфейсов"
    elif any(token in marker for token in ("-db", "_db", "/db", "database", "persistence", "liquibase", "jooq")):
        role = "схема данных, миграции и слой доступа к хранилищу"
    elif any(token in marker for token in ("-app", "_app", "/app", "application", "runtime", "boot")):
        role = "runtime-приложение и прикладная логика"
    elif any(token in marker for token in ("test", "fixture", "mock")):
        role = "тестовая или вспомогательная часть проекта"
    else:
        role = "роль требует интерпретации по содержимому модуля"
    result["role_hint"] = role
    result["role_status"] = "interpreted_from_module_identifier"
    return result


def _semantic_clusters(
    interfaces: list[dict[str, Any]],
    integrations: list[dict[str, Any]],
    data_objects: list[dict[str, Any]],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    """Build conservative capability candidates from source-diverse evidence.

    A functional capability must be supported by an observed interface. Database-only
    lexical frequency is not sufficient. Data objects may strengthen an interface-backed
    candidate, but schema prefixes, transport vocabulary and identifier-like acronyms
    never create a capability by themselves.
    """

    token_stats: dict[str, Counter[str]] = defaultdict(Counter)
    tokenized_interfaces: list[tuple[dict[str, Any], tuple[str, ...], str]] = []
    for item, source in [(item, "inbound") for item in interfaces] + [(item, "outbound") for item in integrations]:
        item_tokens = tuple(
            token for token in _tokens(
                item.get("operation"),
                item.get("endpoint_or_topic"),
                item.get("payload_schema"),
                item.get("request_payload_type"),
                item.get("response_payload_type"),
            )
            if _is_semantic_token(token)
        )
        tokenized_interfaces.append((item, item_tokens, source))
        for token in item_tokens:
            token_stats[token][source] += 1

    tokenized_data: list[tuple[dict[str, Any], tuple[str, ...]]] = []
    for item in data_objects:
        # The simple object name is intentionally preferred to the qualified name:
        # a schema prefix is infrastructure identity, not a business data domain.
        source_name = item.get("name") or str(item.get("qualified_name") or "").rsplit(".", 1)[-1]
        item_tokens = tuple(token for token in _tokens(source_name) if _is_semantic_token(token))
        tokenized_data.append((item, item_tokens))
        for token in item_tokens:
            token_stats[token]["data"] += 1

    ranked: list[tuple[str, int]] = []
    for token, counts in token_stats.items():
        interface_count = counts["inbound"] + counts["outbound"]
        if interface_count == 0:
            continue
        source_diversity = sum(bool(counts[source]) for source in ("inbound", "outbound", "data"))
        score = interface_count * 4 + min(counts["data"], 8) + source_diversity * 3
        ranked.append((token, score))
    ranked.sort(key=lambda pair: (-pair[1], pair[0]))

    candidates: list[tuple[str, int]] = []
    for token, score in ranked:
        if score < 7:
            continue
        if any(token in existing or existing in token for existing, _ in candidates):
            continue
        candidates.append((token, score))
        if len(candidates) >= limit:
            break

    clusters: list[dict[str, Any]] = []
    for token, score in candidates:
        inbound_examples: list[dict[str, Any]] = []
        outbound_examples: list[dict[str, Any]] = []
        table_examples: list[str] = []
        evidence_ids: set[str] = set()
        for item, item_tokens, source in tokenized_interfaces:
            if token not in item_tokens:
                continue
            example = {
                "interface_id": item.get("interface_id"),
                "operation": item.get("operation"),
                "channel": item.get("boundary_kind"),
                "endpoint_or_topic": item.get("endpoint_or_topic"),
                "payload": item.get("payload_schema") or item.get("request_payload_type"),
                "evidence_ids": list(item.get("evidence_ids") or ())[:2],
            }
            evidence_ids.update(example["evidence_ids"])
            target = inbound_examples if source == "inbound" else outbound_examples
            if len(target) < 5:
                target.append(example)
        for item, item_tokens in tokenized_data:
            if token in item_tokens and len(table_examples) < 8:
                table_examples.append(str(item.get("qualified_name") or item.get("name")))
        clusters.append({
            "cluster_id": f"capability:{token}",
            "label_hint": token,
            "status": "interpreted_candidate",
            "inbound_examples": inbound_examples,
            "outbound_examples": outbound_examples,
            "data_examples": table_examples,
            "evidence_ids": sorted(evidence_ids),
            "selection_score": score,
            "selection_basis": "interface_backed_source_diversity",
        })
    return clusters


def _data_groups(data_objects: list[dict[str, Any]], *, limit: int = 10) -> list[dict[str, Any]]:
    """Create overlapping lexical data-domain candidates from simple object names.

    Qualified schema prefixes and free-form descriptions are excluded because they
    frequently describe infrastructure rather than the business subject of a table.
    Objects may belong to several candidate domains (for example, card + history).
    """

    frequencies: Counter[str] = Counter()
    tokenized: list[tuple[dict[str, Any], tuple[str, ...]]] = []
    for item in data_objects:
        source_name = item.get("name") or str(item.get("qualified_name") or "").rsplit(".", 1)[-1]
        item_tokens = tuple(token for token in _tokens(source_name) if _is_semantic_token(token))
        tokenized.append((item, item_tokens))
        frequencies.update(item_tokens)

    candidates: list[str] = []
    for token, count in frequencies.most_common():
        if count < 2:
            continue
        if any(token in existing or existing in token for existing in candidates):
            continue
        candidates.append(token)
        if len(candidates) >= limit:
            break

    groups: list[dict[str, Any]] = []
    grouped_ids: set[str] = set()
    for token in candidates:
        objects = []
        for item, item_tokens in tokenized:
            if token not in item_tokens:
                continue
            object_id = str(item.get("object_id") or item.get("qualified_name"))
            grouped_ids.add(object_id)
            objects.append(str(item.get("qualified_name") or item.get("name")))
        if objects:
            groups.append({
                "group_hint": token,
                "object_count": len(objects),
                "objects": objects[:15],
                "status": "lexical_candidate",
                "overlap_policy": "allowed",
                "selection_basis": "simple_object_name",
            })
    ungrouped = [
        str(item.get("qualified_name") or item.get("name"))
        for item, _ in tokenized
        if str(item.get("object_id") or item.get("qualified_name")) not in grouped_ids
    ]
    if ungrouped:
        groups.append({
            "group_hint": "other",
            "object_count": len(ungrouped),
            "objects": ungrouped[:20],
            "status": "ungrouped",
        })
    return groups


def _interface_score(item: Mapping[str, Any]) -> int:
    score = 0
    if item.get("evidence_ids"):
        score += 5
    if item.get("endpoint_or_topic"):
        score += 4
    if item.get("payload_schema") or item.get("request_payload_type"):
        score += 3
    if item.get("response_payload_type"):
        score += 2
    if item.get("resolution_status") == "resolved":
        score += 2
    if item.get("boundary_kind") == "rest_request":
        score += 1
    return score


def _select_interface_map(inbound: list[dict[str, Any]], outbound: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    candidates = [dict(item) for item in inbound + outbound]
    candidates.sort(key=lambda item: (-_interface_score(item), str(item.get("boundary_kind")), str(item.get("endpoint_or_topic")), str(item.get("operation"))))
    selected: list[dict[str, Any]] = []
    kind_counts: Counter[str] = Counter()
    seen: set[tuple[Any, ...]] = set()
    for item in candidates:
        key = (item.get("direction"), item.get("boundary_kind"), item.get("endpoint_or_topic"), item.get("operation"))
        if key in seen:
            continue
        kind = str(item.get("boundary_kind") or "unknown")
        if kind_counts[kind] >= max(2, limit // 3):
            continue
        seen.add(key)
        kind_counts[kind] += 1
        selected.append(item)
        if len(selected) >= limit:
            break
    if len(selected) < limit:
        for item in candidates:
            key = (item.get("direction"), item.get("boundary_kind"), item.get("endpoint_or_topic"), item.get("operation"))
            if key in seen:
                continue
            seen.add(key)
            selected.append(item)
            if len(selected) >= limit:
                break
    return selected


def _scenario_examples(
    journeys: list[dict[str, Any]],
    inbound: list[dict[str, Any]],
    outbound: list[dict[str, Any]],
    data_objects: list[dict[str, Any]],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    interface_by_operation = {str(item.get("operation")): item for item in inbound + outbound if item.get("operation")}
    table_by_name: dict[str, dict[str, Any]] = {}
    for item in data_objects:
        for key in (item.get("name"), item.get("qualified_name")):
            if key:
                table_by_name[str(key).casefold()] = item

    examples: list[dict[str, Any]] = []
    used_operations: set[str] = set()
    for journey in journeys:
        result = dict(journey)
        evidence_ids: set[str] = set()
        operation = str(journey.get("operation") or "")
        matched = interface_by_operation.get(operation)
        if matched:
            evidence_ids.update(matched.get("evidence_ids") or ())
            result["boundary"] = {
                "interface_id": matched.get("interface_id"),
                "channel": matched.get("boundary_kind"),
                "endpoint_or_topic": matched.get("endpoint_or_topic"),
                "payload": matched.get("payload_schema") or matched.get("request_payload_type"),
            }
        for touch in journey.get("storage_touches") or ():
            text = canonical_json(touch).casefold()
            for name, table in table_by_name.items():
                if name and name in text:
                    evidence_ids.update(table.get("evidence_ids") or ())
        result["evidence_ids"] = sorted(evidence_ids)
        result["status"] = "observed_partial_journey" if not journey.get("is_complete") else "observed_journey"
        examples.append(result)
        if operation:
            used_operations.add(operation)
        if len(examples) >= limit:
            return examples

    # Guarantee useful scenario material even when scenario reconstruction is unresolved:
    # boundary-only examples are explicitly marked and never presented as end-to-end flows.
    boundary_candidates = sorted(inbound, key=lambda item: (-_interface_score(item), str(item.get("operation"))))
    for item in boundary_candidates:
        operation = str(item.get("operation") or "")
        if operation in used_operations:
            continue
        examples.append({
            "journey_id": f"boundary:{item.get('interface_id')}",
            "operation": operation,
            "status": "observed_boundary_only",
            "boundary": {
                "interface_id": item.get("interface_id"),
                "channel": item.get("boundary_kind"),
                "endpoint_or_topic": item.get("endpoint_or_topic"),
                "payload": item.get("payload_schema") or item.get("request_payload_type"),
                "response_payload": item.get("response_payload_type"),
            },
            "entrypoints": [], "external_calls": [], "storage_touches": [], "is_complete": False,
            "evidence_ids": list(item.get("evidence_ids") or ())[:3],
        })
        used_operations.add(operation)
        if len(examples) >= limit:
            return examples
    for item in sorted(outbound, key=lambda item: (-_interface_score(item), str(item.get("operation")))):
        operation = str(item.get("operation") or "")
        if operation in used_operations:
            continue
        examples.append({
            "journey_id": f"outbound:{item.get('interface_id')}",
            "operation": operation,
            "status": "observed_outbound_boundary_only",
            "boundary": {
                "interface_id": item.get("interface_id"),
                "channel": item.get("boundary_kind"),
                "endpoint_or_topic": item.get("endpoint_or_topic"),
                "payload": item.get("request_payload_type") or item.get("payload_schema"),
                "response_payload": item.get("response_payload_type"),
            },
            "entrypoints": [], "external_calls": [item.get("endpoint_or_topic")], "storage_touches": [], "is_complete": False,
            "evidence_ids": list(item.get("evidence_ids") or ())[:3],
        })
        if len(examples) >= limit:
            break
    return examples


def _count_value(counts: Mapping[str, Any], *names: str) -> int:
    normalized = {str(key).casefold(): value for key, value in counts.items()}
    for name in names:
        value = normalized.get(name.casefold())
        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                continue
    return 0


def _storage_inventory(counts: Mapping[str, Any], table_count: int, relationship_count: int) -> dict[str, Any]:
    return {
        "table_count": table_count or _count_value(counts, "db_schema_table", "table", "tables"),
        "column_count": _count_value(counts, "db_schema_column", "column", "columns"),
        "key_count": _count_value(counts, "db_schema_key", "key", "keys"),
        "explicit_foreign_key_count": _count_value(counts, "db_schema_foreign_key", "foreign_key", "foreign_keys"),
        "relationship_observation_count": relationship_count,
        "index_count": _count_value(counts, "db_schema_index", "index", "indexes"),
        "partitioning_observation_count": _count_value(counts, "db_schema_partition", "partition", "partitioning_observation"),
        "sequence_count": _count_value(counts, "db_schema_sequence", "sequence", "sequences"),
        "trigger_count": _count_value(counts, "db_schema_trigger", "trigger", "triggers"),
        "raw_knowledge_layer_counts": dict(counts),
    }


def _technical_references(sections: Mapping[str, Any], lookup: Mapping[str, Mapping[str, Any]], *, limit: int = 20) -> list[dict[str, Any]]:
    ids = sorted(_referenced_evidence_ids(sections))
    refs: list[dict[str, Any]] = []
    seen_locations: set[tuple[Any, ...]] = set()
    for evidence_id in ids:
        ref = lookup.get(evidence_id)
        if not ref:
            continue
        key = (ref.get("repo_id"), ref.get("path"), ref.get("line_start"), ref.get("line_end"))
        if key in seen_locations:
            continue
        seen_locations.add(key)
        refs.append({
            "evidence_id": evidence_id,
            "repo_id": ref.get("repo_id"),
            "path": ref.get("path"),
            "line_start": ref.get("line_start"),
            "line_end": ref.get("line_end"),
            "display": _display_ref(ref),
            "maturity": ref.get("maturity"),
        })
        if len(refs) >= limit:
            break
    return refs


def _owner_questions(overview: Mapping[str, Any], gaps: Mapping[str, Any], journeys: Mapping[str, Any], integrations: Mapping[str, Any], data_inventory: Mapping[str, Any]) -> list[dict[str, Any]]:
    questions: list[dict[str, Any]] = []
    gap_count = int((gaps.get("summary") or {}).get("gap_count") or 0)
    if gap_count:
        questions.append({"question_id": "Q-GAPS", "question": "Какие из зафиксированных пробелов критичны для бизнес-описания и должны быть закрыты дополнительными источниками?", "basis": f"Knowledge Layer содержит {gap_count} gaps."})
    incomplete = sum(1 for item in journeys.get("items") or () if not item.get("is_complete"))
    if incomplete:
        questions.append({"question_id": "Q-FLOWS", "question": "Какие наблюдаемые точки входа образуют ключевые сквозные бизнес-сценарии?", "basis": f"Среди выбранных journeys {incomplete} не имеют подтверждённого продолжения до хранения или внешнего вызова."})
    if integrations.get("items"):
        questions.append({"question_id": "Q-INTEGRATIONS", "question": "Какие конфигурационные адреса и топики являются production-контрактами, а какие относятся только к тестовым или резервным контурам?", "basis": "Статический анализ подтверждает вызовы и конфигурационные ключи, но не runtime-топологию."})
    if int(data_inventory.get("table_count") or 0):
        questions.append({"question_id": "Q-SOURCE-OF-TRUTH", "question": "Какие локальные таблицы являются operational source of truth, а какие — кэшем, проекцией, аудитом или миграционным наследием?", "basis": "Наличие локального хранения само по себе не устанавливает бизнес-владение данными."})
    questions.append({"question_id": "Q-PURPOSE", "question": "Подтверждает ли владелец сформулированное по коду назначение системы и какие функции являются ключевыми с точки зрения бизнеса?", "basis": "Назначение системы является интерпретацией технических фактов."})
    return questions


def build_dataset(request: ReportRequest) -> dict[str, Any]:
    source = request.knowledge_source
    if source is None:
        raise ValueError("system-description/v1 requires a resolved Knowledge API revision")
    overview = source.query_system_description("get_scope_overview")
    composition = source.query_system_description("get_repository_composition", max_results=500)
    technologies = source.query_system_description("get_technologies", max_results=1500)
    inbound = source.query_system_description(
        "list_interfaces",
        filters={"direction": "inbound", "boundary_kinds": ["rest_request", "kafka_consume"]},
        max_results=1500,
    )
    integrations = source.query_system_description("list_integrations", max_results=1500)
    events = source.query_system_description("list_events", max_results=1500)
    # Full compact catalogs are needed for functional and data grouping. Only selected
    # objects retain evidence in the final dataset.
    data_objects = source.query_system_description(
        "list_data_objects", filters={"representative": False}, max_results=1000
    )
    relationships = source.query_system_description("list_relationships", max_results=1500)
    gaps = source.query_system_description("get_gap_summary", max_results=50)
    coverage_result = source.query_system_description("get_analysis_coverage", max_results=50)
    journeys = source.query_system_description(
        "get_representative_journeys",
        max_results={"executive": 6, "standard": 12, "detailed": 20}[request.detail_level],
    )
    results = [overview, composition, technologies, inbound, integrations, events, data_objects, relationships, gaps, coverage_result, journeys]
    evidence_lookup = _evidence_lookup(results)

    inbound_items = [dict(item) for item in (inbound.get("items") or []) if _focus_match(item, request.focus)]
    integration_items = [dict(item) for item in (integrations.get("items") or []) if _focus_match(item, request.focus)]
    all_data_items = [dict(item) for item in (data_objects.get("items") or [])]
    focused_data_items = [item for item in all_data_items if _focus_match(item, request.focus)]
    if request.focus and not inbound_items and not integration_items and not focused_data_items:
        inbound_items = [dict(item) for item in (inbound.get("items") or [])]
        integration_items = [dict(item) for item in (integrations.get("items") or [])]
        focused_data_items = all_data_items
        focus_status = "no_exact_match_fallback_to_profile_dataset"
    else:
        focus_status = "applied" if request.focus else "not_requested"

    overview_item = dict((overview.get("items") or [])[0])
    scope_id = str(overview_item.get("scope_id") or request.system_id or "unknown")
    scope_kind = str(overview_item.get("scope_type") or overview_item.get("scope_kind") or "repository")
    repository_ids = [str(value) for value in overview_item.get("repository_ids") or () if str(value)]
    counts = dict(overview_item.get("counts") or {})
    modules = [
        _module_role_hint(item)
        for item in list(((composition.get("items") or [])[0] if (composition.get("items") or []) else {}).get("modules") or [])
    ]
    repositories = list(((composition.get("items") or [])[0] if (composition.get("items") or []) else {}).get("repositories") or [])
    if not repository_ids:
        repository_ids = [str(item.get("repo_id") or "") for item in repositories if str(item.get("repo_id") or "")]
    scope = {"kind": scope_kind, "id": scope_id, "repository_ids": repository_ids}
    technology_items = [dict(item) for item in (technologies.get("items") or [])]
    plugins = [item for item in technology_items if item.get("kind") == "build_plugin"]
    dependencies, declared_dependency_total = _select_declared_dependencies(
        [item for item in technology_items if item.get("kind") == "declared_dependency"],
        limit={"executive": 12, "standard": 16, "detailed": 30}[request.detail_level],
    )

    representative_limit = {"executive": 12, "standard": 25, "detailed": 45}[request.detail_level]
    representative_objects = _rank_data_objects(focused_data_items, representative_limit)
    all_relationships = _deduplicate_relationships([dict(item) for item in (relationships.get("items") or [])])
    explicit_relationships = [item for item in all_relationships if _relationship_is_explicit(item)]
    observed_relationships = [item for item in all_relationships if not _relationship_is_explicit(item)]
    selected_explicit, selected_observed, relationship_selection = _select_report_relationships(
        explicit_relationships, observed_relationships, request.detail_level
    )
    selected_relationships = selected_explicit + selected_observed

    boundary_catalog_inbound = [_compact_boundary_catalog_item(item) for item in inbound_items]
    boundary_catalog_outbound = [_compact_boundary_catalog_item(item) for item in integration_items]
    boundary_keys = (
        "interface_id", "repo_id", "direction", "boundary_kind", "protocol", "operation",
        "http_method", "endpoint_or_topic", "payload_schema", "request_payload_type",
        "response_payload_type", "resolution_status", "evidence_level", "attribute_count",
    )
    representative_with_provenance = [_compact_data_object(item, evidence_lookup) for item in representative_objects]
    relationship_with_provenance = [_compact_table_relationship(item, evidence_lookup) for item in selected_relationships]

    interface_map_limit = {"executive": 10, "standard": 20, "detailed": 40}[request.detail_level]
    interface_map = [
        _compact_provenance_item(item, evidence_lookup, keys=boundary_keys, max_refs=1)
        for item in _select_interface_map(inbound_items, integration_items, limit=interface_map_limit)
    ]
    scenario_limit = {"executive": 4, "standard": 8, "detailed": 12}[request.detail_level]
    scenario_examples = [
        _with_provenance(item, evidence_lookup, max_refs=1)
        for item in _scenario_examples(
            [dict(item) for item in (journeys.get("items") or [])], inbound_items, integration_items, representative_objects, limit=scenario_limit
        )
    ]
    capability_clusters = _semantic_clusters(inbound_items, integration_items, all_data_items, limit=8 if request.detail_level != "executive" else 5)

    boundary_counts = Counter(str(item.get("boundary_kind") or "unknown") for item in inbound_items + integration_items)
    repository_ids = repository_ids
    module_nodes = [
        {"node_id": f"repo:{repo_id}", "label": repo_id, "kind": "repository"}
        for repo_id in repository_ids
    ] + [
        {"node_id": f"module:{item.get('repo_id')}:{item.get('module_path')}", "label": item.get("module_name") or item.get("module_path"), "kind": "module", "repo_id": item.get("repo_id")}
        for item in modules
    ]
    module_edges = [
        {"from": f"repo:{item.get('repo_id')}", "to": f"module:{item.get('repo_id')}:{item.get('module_path')}", "kind": "contains"}
        for item in modules
    ]
    system_boundary_nodes = [{"node_id": "scope", "label": scope_id, "kind": "analyzed_scope"}]
    system_boundary_edges: list[dict[str, Any]] = []
    boundary_specs = [
        ("rest_request", "rest_clients", "REST-клиенты", "inbound"),
        ("kafka_consume", "kafka_in", "Kafka-входы", "inbound"),
        ("http_outbound", "http_out", "Внешние HTTP-сервисы", "outbound"),
        ("kafka_publish", "kafka_out", "Kafka-публикации", "outbound"),
    ]
    for kind, node_id, label, direction in boundary_specs:
        count = int(boundary_counts.get(kind) or 0)
        if not count:
            continue
        system_boundary_nodes.append({"node_id": node_id, "label": label, "kind": kind, "count": count})
        system_boundary_edges.append({"from": node_id if direction == "inbound" else "scope", "to": "scope" if direction == "inbound" else node_id, "kind": kind, "count": count})
    storage_table_count = int(((data_objects.get("summary") or {}) or {}).get("table_count") or 0)
    if storage_table_count:
        system_boundary_nodes.append({"node_id": "storage", "label": "Локальное реляционное хранение", "kind": "storage", "count": storage_table_count})
        system_boundary_edges.append({"from": "scope", "to": "storage", "kind": "local_storage", "count": storage_table_count})

    data_edges = []
    for item in selected_relationships:
        if not item.get("left_table") or not item.get("right_table"):
            continue
        pairs = [
            f"{pair.get('left_column')} {pair.get('operator') or '='} {pair.get('right_column')}"
            for pair in item.get("column_pairs") or ()
            if pair.get("left_column") or pair.get("right_column")
        ]
        data_edges.append({
            "from": item.get("left_table"), "to": item.get("right_table"),
            "kind": "explicit_foreign_key" if _relationship_is_explicit(item) else "observed_join",
            "join_type": item.get("join_type"), "column_pairs": pairs,
            "relationship_id": item.get("relationship_id"), "evidence_ids": list(item.get("evidence_ids") or ())[:2],
        })

    storage_inventory = _storage_inventory(counts, storage_table_count, int(((relationships.get("summary") or {}) or {}).get("relationship_count") or 0))
    compact_catalog = [
        {
            "object_id": item.get("object_id"), "name": item.get("name"), "schema": item.get("schema"),
            "qualified_name": item.get("qualified_name"), "column_count": item.get("column_count"),
            "key_count": item.get("key_count"), "relationship_count": item.get("relationship_count"),
        }
        for item in all_data_items
    ]

    sections: dict[str, Any] = {
        "scope_overview": overview_item,
        "project_structure": {"repositories": repositories, "modules": modules},
        "functional_capabilities": {
            "status": "interpreted_candidates_from_identifiers",
            "clusters": capability_clusters,
            "instruction": "Renderer assigns readable Russian labels, but marks capabilities as interpretation grounded in examples.",
        },
        "system_boundaries": {
            "counts": dict(sorted(boundary_counts.items())),
            "inbound_items": boundary_catalog_inbound,
            "outbound_items": boundary_catalog_outbound,
            "catalog_evidence_policy": "full_catalog_without_duplicated_provenance; exact evidence is retained in interface_map and journeys",
            "runtime_topology_confirmed": False,
            "production_bindings_confirmed": False,
        },
        "technologies": {
            "plugins": plugins, "declared_dependencies": dependencies,
            "declared_dependency_total": declared_dependency_total,
            "selection_policy": "coordinate-dedup-runtime-priority/v1",
            "runtime_use_note": "Declared dependencies are not proof of runtime use.",
        },
        "events": {
            "event_count": len((events.get("items") or [])),
            "consumer_count": sum(1 for item in (events.get("items") or []) if item.get("boundary_kind") == "kafka_consume"),
            "publisher_count": sum(1 for item in (events.get("items") or []) if item.get("boundary_kind") == "kafka_publish"),
            "catalog_locations": ["sections.system_boundaries.inbound_items", "sections.system_boundaries.outbound_items"],
        },
        "interface_map": {"items": interface_map, "selection_policy": "diverse-channel-evidence-rich/v2"},
        "data_and_storage": {
            "inventory": storage_inventory,
            "data_groups": _data_groups(all_data_items),
            "representative_objects": representative_with_provenance,
            "compact_object_catalog": compact_catalog,
            "explicit_relationships": [
                item for item, raw in zip(relationship_with_provenance, selected_relationships)
                if _relationship_is_explicit(raw)
            ],
            "observed_joins": [
                item for item, raw in zip(relationship_with_provenance, selected_relationships)
                if not _relationship_is_explicit(raw)
            ],
            "relationship_catalog_total": len(all_relationships),
            "explicit_relationship_catalog_total": len(explicit_relationships),
            "observed_join_catalog_total": len(observed_relationships),
            "selected_explicit_relationship_count": len(selected_explicit),
            "selected_observed_join_count": len(selected_observed),
            **relationship_selection,
            "selection_policy": "full-compact-object-catalog-plus-bounded-ranked-evidence/v3",
        },
        "journeys": {
            "scenario_count": int(((journeys.get("summary") or {}) or {}).get("scenario_count") or 0),
            "items": scenario_examples,
            "selection_policy": "observed-journeys-then-evidence-backed-boundaries/v2",
            "status_note": "Boundary-only examples are not end-to-end runtime flows.",
        },
        "gaps": {"summary": dict((gaps.get("summary") or {})), "items": [dict(item) for item in (gaps.get("items") or [])]},
        "diagrams": {
            "module_structure": {"nodes": module_nodes, "edges": module_edges},
            "system_boundary": {"nodes": system_boundary_nodes, "edges": system_boundary_edges},
            "architecture": {"nodes": module_nodes, "edges": module_edges},
            "data_relationships": {"edges": data_edges},
        },
    }
    sections["owner_questions"] = _owner_questions(
        overview, gaps, {"items": scenario_examples}, integrations, storage_inventory
    )
    sections["technical_appendix"] = {
        "source_references": _technical_references(sections, evidence_lookup),
        "exact_identifier_examples": {
            "interfaces": [item.get("interface_id") for item in interface_map if item.get("interface_id")],
            "journeys": [item.get("journey_id") for item in scenario_examples if item.get("journey_id")],
            "relationships": [item.get("relationship_id") for item in selected_relationships if item.get("relationship_id")][:30],
        },
        "scope_limit": f"Описание относится к анализируемому scope {scope_id}; полнота относительно всей информационной системы не подтверждается автоматически.",
    }

    referenced_evidence_ids = _referenced_evidence_ids(sections)
    evidence_payload = _merge_evidence(results, referenced_evidence_ids) if request.include_evidence else {}
    dataset: dict[str, Any] = {
        "schema_version": REPORT_DATASET_SCHEMA,
        "profile_id": request.profile_id,
        "request": request.to_dataset_dict(),
        "scope": scope,
        "audience_policy": _audience_policies()[request.audience],
        "report_blueprint": {
            "required_sections": (
                (["О системе"] if request.audience == "business" else [])
                + [
                    "Краткий вывод", "Границы и окружение", "Основные сценарии", "Использование данных и хранилищ",
                    "Карта интерфейсов", "Архитектурные и бизнес-выводы",
                    "Приложение A. Полнота анализа и ограничения доказательности",
                    "Приложение B. Неоднозначности и вопросы для уточнения",
                    "Приложение C. Технические доказательства и provenance",
                ]
            ),
            "business_opening_requirement": (
                "Start with a plain-language # О системе section without evidence IDs, implementation identifiers or detailed gap counts."
                if request.audience == "business" else None
            ),
            "scenario_requirement": "Describe every selected evidence-backed scenario and state the confirmed boundary of each chain.",
            "diagram_requirement": "Render one system-boundary flowchart and one ER/data relationship diagram when corresponding dataset sections are non-empty.",
            "interface_map_requirement": "Include a compact direction/channel/operation/payload/provenance table.",
            "technical_appendix_requirement": "Include exact IDs and file:line source references without dumping raw catalogs.",
        },
        "coverage": {
            "analysis_coverage": dict((coverage_result.get("items") or [])[0]) if (coverage_result.get("items") or []) else {},
            "knowledge_layer_counts": counts,
            "repository_count": len(repository_ids),
            "module_count": len(modules),
            "inbound_interface_count": len(inbound_items),
            "outbound_integration_count": len(integration_items),
            "event_count": len((events.get("items") or [])),
            "table_count": storage_table_count,
            "relationship_count": int(((relationships.get("summary") or {}) or {}).get("relationship_count") or 0),
            "explicit_relationship_count": len(explicit_relationships),
            "selected_explicit_relationship_count": len(selected_explicit),
            "selected_observed_join_count": len(selected_observed),
            "scenario_count": int(((journeys.get("summary") or {}) or {}).get("scenario_count") or 0),
            "gap_count": int(((gaps.get("summary") or {}) or {}).get("gap_count") or 0),
            "focus_status": focus_status,
        },
        "sections": sections,
        "evidence_index": evidence_payload,
        "interpretation_policy": {
            "facts": "May be stated directly when represented in the dataset.",
            "functional_capabilities": "Capability labels are interpretations inferred from identifiers and must be presented as such.",
            "declared_dependencies": "Must not be described as confirmed runtime use.",
            "business_purpose": "Must be marked as interpretation inferred from technical facts.",
            "unresolved_journeys": "Must not be presented as complete end-to-end business processes.",
            "configuration_bindings": "An unresolved property binding is not the same as an absent endpoint or topic.",
            "missing_runtime_facts": ["owners", "SLA", "runtime volumes", "production topology", "actual production endpoints"],
        },
    }
    dataset["dataset_fingerprint"] = sha256_text(canonical_json(dataset))
    return dataset
