from __future__ import annotations

import json
import re
from collections import defaultdict
from typing import Any

from prepared_knowledge_runtime.normalization import stable_id

_EXTERNAL_KINDS = {"physical", "physical_template"}
_STRUCTURAL_INTERNAL_KINDS = {"cte", "derived", "temporary"}
_TECHNICAL_SEGMENT = re.compile(
    r"(^|[._$])(tmp|temp|stg|stage|staging|interim|work|wrk|buffer|bkp|backup|aux)([._$]|$)",
    re.IGNORECASE,
)
_DROP_TABLE = re.compile(r"\bdrop\s+table\s+(?:if\s+exists\s+)?([^\s;]+)", re.IGNORECASE)


def normalize_relation_identity(value: Any) -> str:
    text = str(value or "").strip().replace("`", "").replace('"', "")
    return re.sub(r"\s+", "", text).lower()


def relation_namespace(value: Any) -> str:
    normalized = normalize_relation_identity(value)
    return normalized.rsplit(".", 1)[0] if "." in normalized else ""


def _load_json(value: Any, default: Any) -> Any:
    if value in (None, ""):
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _drop_targets(connection: Any) -> set[str]:
    targets: set[str] = set()
    rows = connection.execute(
        "SELECT payload_json FROM sql_statement WHERE statement_type='drop'"
    ).fetchall()
    for (payload_raw,) in rows:
        payload = _load_json(payload_raw, {})
        evidence = payload.get("evidence") or []
        snippet = ""
        if evidence and isinstance(evidence[0], dict):
            snippet = str(evidence[0].get("snippet") or "")
        match = _DROP_TABLE.search(snippet)
        if match:
            targets.add(normalize_relation_identity(match.group(1)))
    return targets


def _representative_evidence(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, int | None]] = set()
    for row in rows:
        file = str(row.get("file") or "").strip()
        line = row.get("line_start")
        if not file:
            continue
        key = (file, int(line) if line is not None else None)
        if key in seen:
            continue
        seen.add(key)
        item: dict[str, Any] = {"file": file}
        if line is not None:
            item["line_start"] = int(line)
        result.append(item)
        if len(result) >= 5:
            break
    return result


def materialize_sql_relation_semantic_roles(connection: Any, *, repo_id: str) -> dict[str, Any]:
    """Classify logical SQL relations without deleting technical facts.

    Naming markers are never sufficient by themselves. A physical relation is hidden by
    default only when lifecycle evidence proves local ownership, or when a technical name
    is combined with a repository-owned namespace and an observed dependency into another
    local target. Uncertain read-only staging sources remain visible.
    """
    connection.execute("DELETE FROM sql_relation_semantic_role WHERE repo_id=?", [repo_id])

    relation_columns = [item[0] for item in connection.execute(
        "SELECT * FROM sql_relation WHERE 1=0"
    ).description]
    relation_rows = [dict(zip(relation_columns, row)) for row in connection.execute(
        "SELECT * FROM sql_relation WHERE repo_id=? ORDER BY relation_kind, coalesce(nullif(template_name,''), relation_name), sql_relation_id",
        [repo_id],
    ).fetchall()]

    write_columns = [item[0] for item in connection.execute(
        "SELECT * FROM sql_write_target WHERE 1=0"
    ).description]
    write_rows = [dict(zip(write_columns, row)) for row in connection.execute(
        "SELECT * FROM sql_write_target WHERE repo_id=? ORDER BY target_relation_name, sql_write_target_id",
        [repo_id],
    ).fetchall()]

    dependency_columns = [item[0] for item in connection.execute(
        "SELECT * FROM sql_object_dependency WHERE 1=0"
    ).description]
    dependency_rows = [dict(zip(dependency_columns, row)) for row in connection.execute(
        "SELECT * FROM sql_object_dependency WHERE repo_id=? ORDER BY source_relation_name, target_relation_name, sql_object_dependency_id",
        [repo_id],
    ).fetchall()]

    writes_by_identity: dict[str, list[dict[str, Any]]] = defaultdict(list)
    owned_namespaces: set[str] = set()
    for row in write_rows:
        identity = normalize_relation_identity(row.get("target_relation_name"))
        if not identity:
            continue
        writes_by_identity[identity].append(row)
        namespace = relation_namespace(identity)
        if namespace:
            owned_namespaces.add(namespace)

    dependencies_by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in dependency_rows:
        identity = normalize_relation_identity(row.get("source_relation_name"))
        if identity:
            dependencies_by_source[identity].append(row)

    dropped_identities = _drop_targets(connection)
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in relation_rows:
        relation_kind = str(row.get("relation_kind") or "unknown")
        relation_identity = str(row.get("template_name") or row.get("relation_name") or "").strip()
        grouped[(relation_kind, relation_identity)].append(row)

    role_counts: dict[str, int] = defaultdict(int)
    status_counts: dict[str, int] = defaultdict(int)
    hidden_count = 0
    insert_rows: list[list[Any]] = []

    for (relation_kind, relation_identity), rows in sorted(grouped.items()):
        normalized_identity = normalize_relation_identity(relation_identity)
        exact_writes = writes_by_identity.get(normalized_identity, [])
        downstream = dependencies_by_source.get(normalized_identity, [])
        namespace = relation_namespace(relation_identity)
        owned_namespace = bool(namespace and namespace in owned_namespaces)
        technical_name_signal = bool(_TECHNICAL_SEGMENT.search(relation_identity))
        dropped = normalized_identity in dropped_identities
        reasons: list[str] = []

        if relation_kind in _STRUCTURAL_INTERNAL_KINDS:
            semantic_role = "internal_intermediate"
            classification_status = "confirmed"
            reasons.append("structural_intermediate_relation")
        elif relation_kind not in _EXTERNAL_KINDS or not normalized_identity:
            semantic_role = "unknown"
            classification_status = "unresolved"
            reasons.append("unsupported_or_missing_relation_identity")
        elif exact_writes and (downstream or dropped):
            semantic_role = "internal_intermediate"
            classification_status = "confirmed"
            reasons.append("written_inside_repository")
            if downstream:
                reasons.append("read_to_build_another_local_target")
            if dropped:
                reasons.append("dropped_inside_repository")
        elif exact_writes:
            semantic_role = "output_target"
            classification_status = "confirmed"
            reasons.append("written_inside_repository")
            reasons.append("no_downstream_local_target_observed")
        elif technical_name_signal and owned_namespace and downstream:
            semantic_role = "internal_intermediate"
            classification_status = "probable"
            reasons.extend((
                "technical_name_signal",
                "repository_owned_namespace",
                "read_to_build_another_local_target",
            ))
        elif technical_name_signal and owned_namespace:
            semantic_role = "external_or_shared_intermediate"
            classification_status = "probable"
            reasons.extend(("technical_name_signal", "repository_owned_namespace"))
        else:
            semantic_role = "external_source"
            classification_status = "confirmed"
            reasons.append("read_without_local_write_evidence")
            if technical_name_signal:
                reasons.append("technical_name_without_repository_ownership")

        hidden_by_default = semantic_role in {
            "internal_intermediate",
            "external_or_shared_intermediate",
            "output_target",
        }
        role_counts[semantic_role] += 1
        status_counts[classification_status] += 1
        hidden_count += int(hidden_by_default)

        evidence_rows = [*rows, *exact_writes, *downstream]
        insert_rows.append([
            stable_id("sql_relation_semantic_role", repo_id, relation_kind, normalized_identity),
            repo_id,
            relation_kind,
            relation_identity,
            normalized_identity,
            next((str(row.get("template_name")) for row in rows if row.get("template_name")), None),
            next((str(row.get("logical_name")) for row in rows if row.get("logical_name")), None),
            semantic_role,
            classification_status,
            hidden_by_default,
            json.dumps(reasons, ensure_ascii=False, sort_keys=True),
            len(rows),
            len(exact_writes),
            len({normalize_relation_identity(row.get("target_relation_name")) for row in downstream if row.get("target_relation_name")}),
            owned_namespace,
            technical_name_signal,
            dropped,
            json.dumps(_representative_evidence(evidence_rows), ensure_ascii=False, sort_keys=True),
        ])

    if insert_rows:
        connection.executemany(
            """INSERT INTO sql_relation_semantic_role VALUES (
               ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )""",
            insert_rows,
        )
    return {
        "total_relations": len(insert_rows),
        "hidden_by_default": hidden_count,
        "visible_by_default": len(insert_rows) - hidden_count,
        "by_role": dict(sorted(role_counts.items())),
        "by_status": dict(sorted(status_counts.items())),
    }
