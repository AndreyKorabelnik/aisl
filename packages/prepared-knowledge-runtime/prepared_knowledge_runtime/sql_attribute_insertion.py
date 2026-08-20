from __future__ import annotations

import json
from collections import defaultdict
from pathlib import PurePosixPath
from typing import Any, Iterable

from .sql_target_resolution import (
    _READ_ROLES,
    _logical_tail,
    _match_strength,
    _normalize_hints,
    _technical_name,
    find_sql_target_candidates,
)


def _json(value: Any, default: Any) -> Any:
    if value in (None, ""):
        return default
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _rows(cursor: Any) -> list[dict[str, Any]]:
    columns = [item[0] for item in cursor.description]
    return [dict(zip(columns, raw)) for raw in cursor.fetchall()]


def _path_parts(value: Any) -> tuple[str, ...]:
    text = str(value or "").strip().replace("\\", "/").lstrip("/")
    return tuple(part.lower() for part in PurePosixPath(text).parts if part)


def _target_directory_basis(file: str, logical_target: str) -> tuple[int, str | None]:
    parts = _path_parts(file)
    target = _logical_tail(logical_target)
    if not target or target not in parts:
        return 0, None
    index = parts.index(target)
    previous = parts[index - 1] if index > 0 else ""
    if previous == "dml":
        return 3, "exact_primary_target_directory"
    if previous in {"dml_inc", "dml_arc"}:
        return 2, "exact_target_branch_directory"
    return 1, "exact_target_directory_segment"


def _target_workflow_files(connection: Any, repo_id: str, contexts: Iterable[str]) -> set[str]:
    values = sorted({str(item) for item in contexts if str(item).strip()})
    if not values:
        return set()
    placeholders = ",".join("?" for _ in values)
    rows = connection.execute(
        f"""SELECT DISTINCT reachable_file
              FROM sql_workflow_context_file
             WHERE repo_id=? AND workflow_context_file IN ({placeholders})""",
        [repo_id, *values],
    ).fetchall()
    return {str(row[0]) for row in rows if row and row[0]}


def _workflow_targets(connection: Any, repo_id: str, contexts: Iterable[str]) -> dict[str, list[str]]:
    roots = sorted({str(item) for item in contexts if str(item).strip()})
    if not roots:
        return {}
    placeholders = ",".join("?" for _ in roots)
    rows = connection.execute(
        f"""SELECT file, scalar_value
              FROM sql_workflow_binding
             WHERE repo_id=? AND file IN ({placeholders})
               AND lower(binding_name)='main_table_name'
               AND scalar_value IS NOT NULL
             ORDER BY file, scalar_value""",
        [repo_id, *roots],
    ).fetchall()
    result: dict[str, list[str]] = defaultdict(list)
    for file, value in rows:
        logical = _logical_tail(value)
        if logical and logical not in result[str(file)]:
            result[str(file)].append(logical)
    return dict(result)


def resolve_sql_attribute_insertion_context(
    query: Any,
    *,
    target_relation: str,
    repo_id: str | None = None,
    source_relation_hints: Iterable[str] | str | None = None,
    source_column_hints: Iterable[str] | str | None = None,
    max_results: int = 10,
) -> dict[str, Any]:
    """Return explainable SQL scopes where a new source attribute can be introduced.

    This is a read-only ranking over already materialized SQL facts. It does not edit
    source files, invent a dependency edge, or require an exact end-to-end relation path
    before returning a useful SQL candidate.
    """
    logical_target = _logical_tail(target_relation)
    if not logical_target:
        raise ValueError("target_relation must not be empty")
    if max_results < 1 or max_results > 100:
        raise ValueError("max_results must be between 1 and 100")
    relation_hints = _normalize_hints(source_relation_hints)
    column_hints = _normalize_hints(source_column_hints)
    if not relation_hints:
        raise ValueError("source_relation_hints must contain at least one value")
    filters = {
        "repo_id": repo_id,
        "target_relation": logical_target,
        "source_relation_hints": relation_hints,
        "source_column_hints": column_hints,
        "max_results": max_results,
    }
    required = {
        "sql_relation",
        "sql_column_usage",
        "sql_statement",
        "sql_workflow_context_file",
        "sql_workflow_binding",
    }
    if not all(query._has_relation(name) for name in required):
        return {
            "kind": "knowledge-layer-sql-attribute-insertion-context",
            "schema_version": "sql-attribute-insertion-context/v1",
            "filters": filters,
            "not_available": True,
            "target": None,
            "recommended_insertion": None,
            "insertion_candidates": [],
            "diagnostics": ["required_sql_insertion_context_facts_not_available"],
        }

    target_result = find_sql_target_candidates(
        query,
        repo_id=repo_id,
        source_relation_hints=relation_hints,
        source_column_hints=column_hints,
        business_entity_hints=[logical_target],
        max_results=100,
    )
    target_candidate = next(
        (
            item
            for item in target_result.get("candidates") or []
            if _logical_tail(item.get("logical_target_name")) == logical_target
        ),
        None,
    )
    diagnostics: list[str] = []
    if target_candidate is None:
        diagnostics.append("target_not_present_in_ranked_write_candidates")

    repo_clause = "" if repo_id is None else " AND repo_id=?"
    repo_args: list[Any] = [] if repo_id is None else [repo_id]
    candidates: dict[tuple[str, str, str, str], dict[str, Any]] = {}

    with query._connect() as con:
        target_repo = str((target_candidate or {}).get("repo_id") or repo_id or "")
        target_contexts = list((target_candidate or {}).get("workflow_contexts") or [])
        target_files = _target_workflow_files(con, target_repo, target_contexts) if target_repo else set()

        relation_rows = _rows(con.execute(
            """SELECT sql_relation_id, repo_id, query_id, scope_id, file, line_start,
                      relation_kind, relation_name, template_name, logical_name, alias,
                      usage_role, definition_status, evidence_maturity_level, evidence_json
                 FROM sql_relation
                WHERE 1=1 {} AND lower(coalesce(usage_role,'')) IN ({})
                ORDER BY repo_id, file, query_id, scope_id, line_start, sql_relation_id""".format(
                    repo_clause, ",".join("?" for _ in sorted(_READ_ROLES))
                ),
            [*repo_args, *sorted(_READ_ROLES)],
        ))
        for row in relation_rows:
            strength_name, basis_name = _match_strength(row.get("logical_name"), relation_hints)
            strength_relation, basis_relation = _match_strength(row.get("relation_name"), relation_hints)
            strength = max(strength_name, strength_relation)
            if strength <= 0:
                continue
            basis = basis_name if strength_name >= strength_relation else basis_relation
            key = (
                str(row.get("repo_id") or ""),
                str(row.get("file") or ""),
                str(row.get("query_id") or ""),
                str(row.get("scope_id") or ""),
            )
            item = candidates.setdefault(key, {
                "repo_id": key[0],
                "file": key[1],
                "query_id": key[2],
                "scope_id": key[3],
                "relation_matches": [],
                "column_matches": [],
                "matched_relation_hints": set(),
                "matched_column_hints": set(),
                "score": 0,
                "reasons": set(),
                "diagnostics": set(),
            })
            matched_hint = max(
                relation_hints,
                key=lambda hint: _match_strength(row.get("logical_name") or row.get("relation_name"), [hint])[0],
            )
            item["matched_relation_hints"].add(matched_hint)
            item["relation_matches"].append({
                "sql_relation_id": row.get("sql_relation_id"),
                "relation_name": row.get("relation_name"),
                "logical_name": row.get("logical_name"),
                "relation_kind": row.get("relation_kind"),
                "alias": row.get("alias"),
                "usage_role": row.get("usage_role"),
                "line_start": row.get("line_start"),
                "match_basis": basis,
                "match_strength": strength,
                "evidence_maturity_level": row.get("evidence_maturity_level"),
                "evidence": _json(row.get("evidence_json"), []),
            })

        if column_hints and candidates:
            column_rows = _rows(con.execute(
                """SELECT sql_column_usage_id, repo_id, query_id, scope_id, file, line_start,
                          column_name, usage_role, table_or_alias, relation_id, relation_name,
                          resolution_status, resolution_basis, evidence_maturity_level, evidence_json
                     FROM sql_column_usage WHERE 1=1 {}
                    ORDER BY repo_id, file, query_id, scope_id, line_start, sql_column_usage_id""".format(repo_clause),
                repo_args,
            ))
            for row in column_rows:
                key = (
                    str(row.get("repo_id") or ""),
                    str(row.get("file") or ""),
                    str(row.get("query_id") or ""),
                    str(row.get("scope_id") or ""),
                )
                item = candidates.get(key)
                if item is None:
                    continue
                strength, basis = _match_strength(row.get("column_name"), column_hints)
                if strength <= 0:
                    continue
                matched_hint = max(
                    column_hints,
                    key=lambda hint: _match_strength(row.get("column_name"), [hint])[0],
                )
                item["matched_column_hints"].add(matched_hint)
                item["column_matches"].append({
                    "sql_column_usage_id": row.get("sql_column_usage_id"),
                    "column_name": row.get("column_name"),
                    "usage_role": row.get("usage_role"),
                    "table_or_alias": row.get("table_or_alias"),
                    "relation_name": row.get("relation_name"),
                    "line_start": row.get("line_start"),
                    "resolution_status": row.get("resolution_status"),
                    "resolution_basis": row.get("resolution_basis"),
                    "match_basis": basis,
                    "match_strength": strength,
                    "evidence_maturity_level": row.get("evidence_maturity_level"),
                    "evidence": _json(row.get("evidence_json"), []),
                })

        context_rows = _rows(con.execute(
            """SELECT repo_id, workflow_context_file, reachable_file, context_hop_count,
                      resolution_status, resolution_reasons_json
                 FROM sql_workflow_context_file WHERE 1=1 {}
                ORDER BY repo_id, workflow_context_file, context_hop_count, reachable_file""".format(repo_clause),
            repo_args,
        ))
        contexts_by_file: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for row in context_rows:
            contexts_by_file[(str(row.get("repo_id") or ""), str(row.get("reachable_file") or ""))].append(row)
        all_source_contexts = {
            str(row.get("workflow_context_file") or "")
            for item in candidates.values()
            for row in contexts_by_file.get((item["repo_id"], item["file"]), [])
        }
        source_targets_by_context = _workflow_targets(con, target_repo or str(repo_id or ""), all_source_contexts)

        def scoped_rows(table: str, columns: str, item: dict[str, Any], *, scope: bool = True, limit: int = 200) -> list[dict[str, Any]]:
            clauses = ["repo_id=?", "file=?", "query_id=?"]
            args: list[Any] = [item["repo_id"], item["file"], item["query_id"]]
            if scope and item["scope_id"]:
                clauses.append("scope_id=?")
                args.append(item["scope_id"])
            return _rows(con.execute(
                f"SELECT {columns} FROM {table} WHERE {' AND '.join(clauses)} ORDER BY line_start LIMIT ?",
                [*args, limit],
            ))

        for item in candidates.values():
            relation_strength = max((int(row["match_strength"]) for row in item["relation_matches"]), default=0)
            item["score"] += {1: 12, 2: 22, 3: 32}.get(relation_strength, 0)
            item["score"] += 8 * max(0, len(item["matched_relation_hints"]) - 1)
            item["reasons"].add("source_relation_observed_in_scope")
            direct_source_matches = [
                row for row in item["relation_matches"]
                if str(row.get("relation_kind") or "") == "physical_template"
                and not _technical_name(row.get("logical_name") or row.get("relation_name"))
            ]
            technical_matches = [
                row for row in item["relation_matches"]
                if _technical_name(row.get("logical_name") or row.get("relation_name"))
            ]
            if direct_source_matches:
                item["score"] += 45
                item["reasons"].add("direct_physical_source_relation")
            elif technical_matches and len(technical_matches) == len(item["relation_matches"]):
                item["score"] -= 35
                item["reasons"].add("matched_only_technical_intermediate_relation")
            if item["column_matches"]:
                column_strength = max(int(row["match_strength"]) for row in item["column_matches"])
                item["score"] += {1: 5, 2: 10, 3: 15}.get(column_strength, 0)
                item["score"] += 4 * max(0, len(item["matched_column_hints"]) - 1)
                item["reasons"].add("source_column_observed_in_scope")

            in_target_context = item["file"] in target_files
            if in_target_context:
                item["score"] += 45
                item["reasons"].add("reachable_from_target_workflow")

            directory_strength, directory_reason = _target_directory_basis(item["file"], logical_target)
            if directory_strength:
                item["score"] += {1: 8, 2: 20, 3: 35}[directory_strength]
                if directory_reason:
                    item["reasons"].add(directory_reason)

            source_context_rows = contexts_by_file.get((item["repo_id"], item["file"]), [])
            item["source_workflow_contexts"] = sorted({str(row["workflow_context_file"]) for row in source_context_rows})
            item["source_workflow_targets"] = sorted({
                target
                for context in item["source_workflow_contexts"]
                for target in source_targets_by_context.get(context, [])
            })
            if logical_target in item["source_workflow_targets"]:
                item["score"] += 20
                item["reasons"].add("source_scope_workflow_targets_selected_relation")

            item["statements"] = scoped_rows(
                "sql_statement",
                "sql_statement_id, file, line_start, line_end, operation, statement_type, target_relation_name, unit_kind, evidence_maturity_level, evidence_json",
                item,
                scope=False,
                limit=20,
            ) if query._has_relation("sql_statement") else []
            item["scope_relations"] = scoped_rows(
                "sql_relation",
                "sql_relation_id, file, line_start, relation_kind, relation_name, template_name, logical_name, alias, usage_role, definition_status, evidence_maturity_level, evidence_json",
                item,
                limit=100,
            )
            item["joins"] = scoped_rows(
                "sql_join_edge",
                "sql_join_edge_id, file, line_start, join_ordinal, join_type, condition_kind, predicate, right_relation_name, column_pairs_json, resolution_status, physical_join_confirmed, evidence_maturity_level, evidence_json",
                item,
                limit=100,
            ) if query._has_relation("sql_join_edge") else []
            item["projections"] = scoped_rows(
                "sql_projection",
                "sql_projection_id, file, line_start, projection_ordinal, output_name, expression, expression_kind, resolution_status, resolution_basis, evidence_maturity_level, evidence_json",
                item,
                limit=200,
            ) if query._has_relation("sql_projection") else []
            item["write_observations"] = scoped_rows(
                "sql_write_target",
                "sql_write_target_id, file, line_start, operation_kind, target_relation_name, target_logical_name, resolution_status, field_mapping_status, evidence_maturity_level, evidence_json",
                item,
                scope=False,
                limit=50,
            ) if query._has_relation("sql_write_target") else []
            if item["write_observations"]:
                item["score"] += 10
                item["reasons"].add("scope_file_contains_write_observation")

            if in_target_context:
                item["propagation_status"] = "resolved"
                item["propagation_basis"] = "same_target_workflow_context"
            elif directory_strength:
                item["propagation_status"] = "probable"
                item["propagation_basis"] = directory_reason
            else:
                item["propagation_status"] = "partial"
                item["propagation_basis"] = "source_scope_observed_without_exact_target_context_path"
                item["diagnostics"].add("exact_propagation_path_to_target_not_observed")

        target_sql_files = sorted(
            file for file in target_files
            if file.lower().endswith(".sql") and PurePosixPath(file).name.lower() == f"{logical_target}.sql"
        )
        if not target_sql_files:
            target_sql_files = sorted(file for file in target_files if file.lower().endswith(".sql"))

    ordered = sorted(
        candidates.values(),
        key=lambda item: (
            -int(item["score"]),
            -len(item["matched_relation_hints"]),
            -len(item["matched_column_hints"]),
            item["file"],
            item["scope_id"],
        ),
    )
    result_items: list[dict[str, Any]] = []
    for rank, item in enumerate(ordered[:max_results], 1):
        result_items.append({
            "rank": rank,
            "repo_id": item["repo_id"],
            "file": item["file"],
            "query_id": item["query_id"],
            "scope_id": item["scope_id"],
            "score": int(item["score"]),
            "reasons": sorted(item["reasons"]),
            "matched_relation_hints": sorted(item["matched_relation_hints"]),
            "matched_column_hints": sorted(item["matched_column_hints"]),
            "relation_matches": sorted(item["relation_matches"], key=lambda row: (int(row.get("line_start") or 0), str(row.get("relation_name") or ""))),
            "column_matches": sorted(item["column_matches"], key=lambda row: (int(row.get("line_start") or 0), str(row.get("column_name") or ""))),
            "source_workflow_contexts": item["source_workflow_contexts"],
            "source_workflow_targets": item["source_workflow_targets"],
            "propagation_status": item["propagation_status"],
            "propagation_basis": item["propagation_basis"],
            "statements": item["statements"],
            "scope_relations": item["scope_relations"],
            "joins": item["joins"],
            "projections": item["projections"],
            "write_observations": item["write_observations"],
            "diagnostics": sorted(item["diagnostics"]),
        })

    recommended = result_items[0] if result_items else None
    if not result_items:
        diagnostics.append("no_sql_scope_observes_requested_source_relation")
    if recommended and recommended["propagation_status"] != "resolved":
        diagnostics.append("recommended_scope_has_no_exact_end_to_end_target_dependency_path")

    return {
        "kind": "knowledge-layer-sql-attribute-insertion-context",
        "schema_version": "sql-attribute-insertion-context/v1",
        "filters": filters,
        "target": {
            "logical_target_name": logical_target,
            "candidate": target_candidate,
            "workflow_contexts": list((target_candidate or {}).get("workflow_contexts") or []),
            "target_sql_files": target_sql_files,
        },
        "recommended_insertion": recommended,
        "insertion_candidates": result_items,
        "candidate_count": len(candidates),
        "returned_count": len(result_items),
        "diagnostics": sorted(dict.fromkeys(diagnostics)),
    }
