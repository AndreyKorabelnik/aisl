from __future__ import annotations

import json
import re
from collections import defaultdict
from typing import Any, Iterable

_READ_ROLES = {"from", "join", "read", "source", "subquery"}
_TECHNICAL_TOKENS = {
    "tmp", "temp", "stg", "stage", "staging", "interim", "prestg", "aux", "work", "buffer",
}
_TARGET_BINDING_NAMES = {
    "main_table_name",
    "target_table_name",
    "main_table",
    "target_table",
    "tgt_table",
}


def _json(value: Any, default: Any) -> Any:
    if value in (None, ""):
        return default
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _text(value: Any) -> str:
    return str(value or "").strip()


def _logical_tail(value: Any) -> str:
    text = _text(value).lower().replace("`", "").replace('"', "")
    text = re.sub(r"\$\{[^{}]+\}|\$[A-Za-z_][A-Za-z0-9_.]*", "", text)
    text = text.rsplit(".", 1)[-1]
    return re.sub(r"[^a-z0-9_]+", "_", text).strip("_")


def _tokens(value: Any) -> set[str]:
    logical = _logical_tail(value)
    return {item for item in re.split(r"[_\W]+", logical) if item}


def _normalize_hints(values: Iterable[str] | str | None) -> list[str]:
    if values is None:
        return []
    raw = [values] if isinstance(values, str) else list(values)
    result = []
    for value in raw:
        normalized = _logical_tail(value)
        if normalized and normalized not in result:
            result.append(normalized)
    return result


def _match_strength(value: Any, hints: list[str]) -> tuple[int, str | None]:
    if not hints:
        return 0, None
    logical = _logical_tail(value)
    tokens = _tokens(value)
    best = (0, None)
    for hint in hints:
        hint_tokens = _tokens(hint)
        if logical == hint:
            candidate = (3, "exact_logical_name")
        elif logical.endswith("_" + hint) or hint.endswith("_" + logical):
            candidate = (2, "logical_suffix")
        elif hint_tokens and hint_tokens.issubset(tokens):
            candidate = (1, "token_match")
        else:
            continue
        if candidate[0] > best[0]:
            best = candidate
    return best


def _primary_business_match(candidate: str, hints: list[str]) -> tuple[int, str | None]:
    if not hints:
        return 0, None
    logical = _logical_tail(candidate)
    tokens = list(filter(None, logical.split("_")))
    for hint in hints:
        if logical == hint:
            return 3, "business_entity_exact"
        if logical.endswith("_" + hint):
            return 3, "business_entity_primary_suffix"
        if hint in tokens:
            return 1, "business_entity_token"
    return 0, None


def _technical_name(candidate: str) -> bool:
    return bool(_tokens(candidate) & _TECHNICAL_TOKENS)


def _rows(cursor: Any) -> list[dict[str, Any]]:
    columns = [item[0] for item in cursor.description]
    return [dict(zip(columns, raw)) for raw in cursor.fetchall()]


def _recommended_target_relation(
    *,
    logical_target_name: str,
    relation_candidates: Iterable[str],
    write_observations: Iterable[dict[str, Any]],
    read_observations: Iterable[dict[str, Any]],
) -> tuple[str | None, str, list[str]]:
    """Choose one physical target relation without hiding alternatives.

    The recommendation uses only already observed SQL evidence. A unique candidate
    is confirmed. With several candidates, observed writes outrank reads, concrete
    identities outrank unresolved templates, and remaining ties are resolved
    lexicographically so the next deterministic resolver can proceed.
    """
    candidates = sorted({_text(value) for value in relation_candidates if _text(value)})
    if not candidates:
        return None, "not_available", ["no_observed_target_relation"]
    if len(candidates) == 1:
        return candidates[0], "confirmed_unique", ["single_observed_target_relation"]

    write_counts: dict[str, int] = defaultdict(int)
    read_counts: dict[str, int] = defaultdict(int)
    for row in write_observations:
        value = _text(row.get("target_relation_name"))
        if value:
            write_counts[value] += 1
    for row in read_observations:
        value = _text(row.get("relation_name"))
        if value:
            read_counts[value] += 1

    logical_tail = _logical_tail(logical_target_name)

    def score(value: str) -> tuple[int, int, int, int]:
        concrete = int("${" not in value and not value.startswith("$"))
        return (
            write_counts.get(value, 0),
            int(_logical_tail(value) == logical_tail),
            concrete,
            read_counts.get(value, 0),
        )

    scored = [(score(value), value) for value in candidates]
    best_score = max(item[0] for item in scored)
    best = sorted(value for candidate_score, value in scored if candidate_score == best_score)
    recommended = best[0]
    reasons: list[str] = []
    if best_score[0]:
        reasons.append("most_observed_write_target")
    if best_score[1]:
        reasons.append("logical_target_name_match")
    if best_score[2]:
        reasons.append("concrete_relation_identity")
    if best_score[3]:
        reasons.append("observed_downstream_read_identity")
    if len(best) > 1:
        reasons.append("deterministic_lexical_tie_break")
        status = "probable_tie_break"
    else:
        status = "probable_ranked"
    return recommended, status, reasons


def find_sql_target_candidates(
    query: Any,
    *,
    repo_id: str | None = None,
    source_relation_hints: Iterable[str] | str | None = None,
    source_column_hints: Iterable[str] | str | None = None,
    business_entity_hints: Iterable[str] | str | None = None,
    max_results: int = 10,
) -> dict[str, Any]:
    """Rank likely logical SQL targets using already materialized evidence.

    The function does not ask an LLM to classify targets and does not mutate the
    artifact. Scores are only an explainable ordering of observed workflow, SQL and
    dependency signals; all candidates and reasons remain visible to the caller.
    """
    if max_results < 1 or max_results > 100:
        raise ValueError("max_results must be between 1 and 100")
    relation_hints = _normalize_hints(source_relation_hints)
    column_hints = _normalize_hints(source_column_hints)
    entity_hints = _normalize_hints(business_entity_hints)
    filters = {
        "repo_id": repo_id,
        "source_relation_hints": relation_hints,
        "source_column_hints": column_hints,
        "business_entity_hints": entity_hints,
        "max_results": max_results,
    }
    required = {
        "sql_workflow_binding",
        "sql_workflow_context_file",
        "sql_relation",
        "sql_write_target",
    }
    if not all(query._has_relation(name) for name in required):
        return {
            "kind": "knowledge-layer-sql-target-candidates",
            "schema_version": "sql-target-candidates/v1",
            "filters": filters,
            "not_available": True,
            "candidates": [],
            "candidate_count": 0,
            "diagnostics": ["required_sql_target_resolution_facts_not_available"],
        }

    repo_clause = "" if repo_id is None else " AND repo_id=?"
    repo_args: list[Any] = [] if repo_id is None else [repo_id]
    candidates: dict[tuple[str, str], dict[str, Any]] = {}

    def ensure(candidate_repo: str, logical_name: str) -> dict[str, Any]:
        normalized = _logical_tail(logical_name)
        key = (candidate_repo, normalized)
        if not normalized:
            raise ValueError("candidate logical name must not be empty")
        return candidates.setdefault(key, {
            "repo_id": candidate_repo,
            "logical_target_name": normalized,
            "target_relation_candidates": set(),
            "workflow_contexts": set(),
            "workflow_files": set(),
            "write_observations": [],
            "read_observations": [],
            "semantic_roles": set(),
            "source_relation_matches": [],
            "source_column_matches": [],
            "score": 0,
            "reasons": set(),
            "diagnostics": set(),
        })

    with query._connect() as con:
        binding_rows = _rows(con.execute(
            """SELECT repo_id, file, binding_name, scalar_value, value_expression,
                      resolution_status, evidence_json
               FROM sql_workflow_binding
               WHERE lower(binding_name) IN ({}) {} AND scalar_value IS NOT NULL
               ORDER BY repo_id, file, binding_name""".format(
                   ",".join("?" for _ in sorted(_TARGET_BINDING_NAMES)), repo_clause
               ),
            [*sorted(_TARGET_BINDING_NAMES), *repo_args],
        ))
        for row in binding_rows:
            value = _text(row.get("scalar_value") or row.get("value_expression"))
            if not value or "${" in value or value.startswith("$"):
                continue
            item = ensure(str(row["repo_id"]), value)
            item["workflow_contexts"].add(str(row["file"]))
            item["workflow_files"].add(str(row["file"]))
            if "declared_workflow_target" not in item["reasons"]:
                item["score"] += 20
                item["reasons"].add("declared_workflow_target")

        # Future/other repositories may bind a placeholder used as a write target.
        if query._has_relation("sql_placeholder_binding_resolution"):
            resolution_rows = _rows(con.execute(
                """SELECT repo_id, workflow_context_file, sql_file, resolved_value,
                          usage_roles_json, resolution_status, evidence_json
                   FROM sql_placeholder_binding_resolution
                   WHERE resolved_value IS NOT NULL {}""".format(repo_clause), repo_args,
            ))
            for row in resolution_rows:
                roles = set(_json(row.get("usage_roles_json"), []))
                if "target_relation" not in roles:
                    continue
                value = _text(row.get("resolved_value"))
                if not value or "${" in value or value.startswith("$"):
                    continue
                item = ensure(str(row["repo_id"]), value)
                item["workflow_contexts"].add(str(row["workflow_context_file"]))
                item["workflow_files"].add(str(row["sql_file"]))
                if "resolved_target_placeholder" not in item["reasons"]:
                    item["score"] += 35
                    item["reasons"].add("resolved_target_placeholder")

        write_rows = _rows(con.execute(
            """SELECT repo_id, file, line_start, operation_kind, target_relation_name,
                      target_logical_name, resolution_status, evidence_json
               FROM sql_write_target WHERE target_logical_name IS NOT NULL {}""".format(repo_clause),
            repo_args,
        ))
        for row in write_rows:
            item = ensure(str(row["repo_id"]), str(row["target_logical_name"]))
            relation = _text(row.get("target_relation_name"))
            if relation:
                item["target_relation_candidates"].add(relation)
            item["write_observations"].append({
                "file": row.get("file"), "line_start": row.get("line_start"),
                "operation_kind": row.get("operation_kind"),
                "target_relation_name": row.get("target_relation_name"),
                "resolution_status": row.get("resolution_status"),
            })
            if str(row.get("operation_kind") or "").lower() in {"insert", "merge", "update", "ctas", "create_table_as"}:
                if "observed_data_write" not in item["reasons"]:
                    item["score"] += 20
                    item["reasons"].add("observed_data_write")
            elif "observed_target_definition" not in item["reasons"]:
                item["score"] += 5
                item["reasons"].add("observed_target_definition")

        context_rows = _rows(con.execute(
            """SELECT repo_id, workflow_context_file, reachable_file, resolution_status
               FROM sql_workflow_context_file WHERE 1=1 {}""".format(repo_clause), repo_args,
        ))
        files_by_context: dict[tuple[str, str], set[str]] = defaultdict(set)
        for row in context_rows:
            files_by_context[(str(row["repo_id"]), str(row["workflow_context_file"]))].add(str(row["reachable_file"]))

        relation_rows = _rows(con.execute(
            """SELECT repo_id, file, line_start, relation_name, logical_name, usage_role,
                      definition_status, evidence_maturity_level
               FROM sql_relation WHERE 1=1 {}""".format(repo_clause), repo_args,
        ))
        relations_by_file: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for row in relation_rows:
            relations_by_file[(str(row["repo_id"]), str(row.get("file") or ""))].append(row)

        column_rows: list[dict[str, Any]] = []
        if column_hints and query._has_relation("sql_column_usage"):
            column_rows = _rows(con.execute(
                """SELECT repo_id, file, line_start, column_name, usage_role, relation_name,
                          resolution_status
                   FROM sql_column_usage WHERE 1=1 {}""".format(repo_clause), repo_args,
            ))
        columns_by_file: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for row in column_rows:
            columns_by_file[(str(row["repo_id"]), str(row.get("file") or ""))].append(row)

        # Add exact relation read observations and semantic roles before evaluating finality.
        for row in relation_rows:
            logical = _logical_tail(row.get("logical_name") or row.get("relation_name"))
            item = candidates.get((str(row["repo_id"]), logical))
            if item is None:
                continue
            if str(row.get("usage_role") or "").lower() in _READ_ROLES:
                item["read_observations"].append({
                    "file": row.get("file"), "line_start": row.get("line_start"),
                    "relation_name": row.get("relation_name"), "usage_role": row.get("usage_role"),
                })
                relation = _text(row.get("relation_name"))
                if relation:
                    item["target_relation_candidates"].add(relation)

        if query._has_relation("sql_relation_semantic_role"):
            role_rows = _rows(con.execute(
                """SELECT repo_id, logical_name, relation_identity, semantic_role,
                          classification_status, hidden_by_default
                   FROM sql_relation_semantic_role WHERE 1=1 {}""".format(repo_clause), repo_args,
            ))
            for row in role_rows:
                item = candidates.get((str(row["repo_id"]), _logical_tail(row.get("logical_name") or row.get("relation_identity"))))
                if item is None:
                    continue
                role = str(row.get("semantic_role") or "")
                item["semantic_roles"].add(role)
                item["target_relation_candidates"].add(str(row.get("relation_identity") or ""))
                if role == "output_target" and "semantic_output_target" not in item["reasons"]:
                    item["score"] += 15
                    item["reasons"].add("semantic_output_target")

        for item in candidates.values():
            candidate_files: set[str] = set(item["workflow_files"])
            for context in item["workflow_contexts"]:
                candidate_files.update(files_by_context.get((item["repo_id"], context), set()))

            best_relation_strength = 0
            relation_match_basis: set[str] = set()
            for file in sorted(candidate_files):
                for row in relations_by_file.get((item["repo_id"], file), []):
                    strength_name, basis_name = _match_strength(row.get("logical_name"), relation_hints)
                    strength_relation, basis_relation = _match_strength(row.get("relation_name"), relation_hints)
                    strength = max(strength_name, strength_relation)
                    basis = basis_name if strength_name >= strength_relation else basis_relation
                    if strength <= 0:
                        continue
                    best_relation_strength = max(best_relation_strength, strength)
                    if basis:
                        relation_match_basis.add(basis)
                    item["source_relation_matches"].append({
                        "file": file,
                        "line_start": row.get("line_start"),
                        "relation_name": row.get("relation_name"),
                        "logical_name": row.get("logical_name"),
                        "match_basis": basis,
                    })
            if best_relation_strength:
                item["score"] += {1: 12, 2: 22, 3: 32}[best_relation_strength]
                item["reasons"].add("source_relation_observed_in_workflow_context")
                item["reasons"].update(f"source_relation_{basis}" for basis in relation_match_basis)

            best_column_strength = 0
            for file in sorted(candidate_files):
                for row in columns_by_file.get((item["repo_id"], file), []):
                    strength, basis = _match_strength(row.get("column_name"), column_hints)
                    if strength <= 0:
                        continue
                    best_column_strength = max(best_column_strength, strength)
                    item["source_column_matches"].append({
                        "file": file, "line_start": row.get("line_start"),
                        "column_name": row.get("column_name"),
                        "relation_name": row.get("relation_name"),
                        "usage_role": row.get("usage_role"),
                        "match_basis": basis,
                    })
            if best_column_strength:
                item["score"] += {1: 5, 2: 10, 3: 15}[best_column_strength]
                item["reasons"].add("source_column_observed_in_workflow_context")

            outside_reads = [row for row in item["read_observations"] if str(row.get("file") or "") not in candidate_files]
            if outside_reads:
                item["score"] += 45
                item["reasons"].add("target_consumed_outside_own_workflow")

            business_strength, business_reason = _primary_business_match(item["logical_target_name"], entity_hints)
            if business_strength:
                item["score"] += {1: 8, 2: 15, 3: 22}[business_strength]
                if business_reason:
                    item["reasons"].add(business_reason)

            if _technical_name(item["logical_target_name"]):
                item["score"] -= 25
                item["reasons"].add("technical_or_intermediate_name_signal")

            if outside_reads or "output_target" in item["semantic_roles"]:
                item["target_kind"] = "published_or_terminal"
            elif _technical_name(item["logical_target_name"]):
                item["target_kind"] = "intermediate"
            else:
                item["target_kind"] = "workflow_target"

            if relation_hints and not item["source_relation_matches"]:
                item["diagnostics"].add("source_relation_hint_not_observed_in_candidate_context")
            if column_hints and not item["source_column_matches"]:
                item["diagnostics"].add("source_column_hint_not_observed_in_candidate_context")

    ordered = sorted(
        candidates.values(),
        key=lambda item: (-int(item["score"]), item["logical_target_name"], item["repo_id"]),
    )
    result_items: list[dict[str, Any]] = []
    for rank, item in enumerate(ordered[:max_results], 1):
        contexts = sorted(item["workflow_contexts"])
        files: set[str] = set(item["workflow_files"])
        # Do not return every reachable file; the contexts are enough for the next resolver.
        relation_candidates = sorted(x for x in item["target_relation_candidates"] if x)
        recommended_relation, recommendation_status, recommendation_reasons = _recommended_target_relation(
            logical_target_name=item["logical_target_name"],
            relation_candidates=relation_candidates,
            write_observations=item["write_observations"],
            read_observations=item["read_observations"],
        )
        result_items.append({
            "rank": rank,
            "repo_id": item["repo_id"],
            "logical_target_name": item["logical_target_name"],
            "recommended_target_relation": recommended_relation,
            "target_relation_recommendation_status": recommendation_status,
            "target_relation_recommendation_reasons": recommendation_reasons,
            "target_relation_candidates": relation_candidates,
            "target_kind": item["target_kind"],
            "score": int(item["score"]),
            "reasons": sorted(item["reasons"]),
            "workflow_contexts": contexts,
            "workflow_context_count": len(contexts),
            "write_observations": sorted(item["write_observations"], key=lambda row: (str(row.get("file")), int(row.get("line_start") or 0))),
            "read_observations": sorted(item["read_observations"], key=lambda row: (str(row.get("file")), int(row.get("line_start") or 0)))[:20],
            "source_relation_matches": sorted(item["source_relation_matches"], key=lambda row: (str(row.get("file")), int(row.get("line_start") or 0)))[:50],
            "source_column_matches": sorted(item["source_column_matches"], key=lambda row: (str(row.get("file")), int(row.get("line_start") or 0)))[:50],
            "semantic_roles": sorted(item["semantic_roles"]),
            "diagnostics": sorted(item["diagnostics"]),
        })
    return {
        "kind": "knowledge-layer-sql-target-candidates",
        "schema_version": "sql-target-candidates/v1",
        "filters": filters,
        "candidate_count": len(candidates),
        "returned_count": len(result_items),
        "candidates": result_items,
        "diagnostics": [],
    }
