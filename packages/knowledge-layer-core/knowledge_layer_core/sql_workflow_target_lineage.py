from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import PurePosixPath
from typing import Any

from .metrics import canonical_json
from .progress import emit_progress, timed_phase
from .sql_producer_observations import derive_sql_producer_observations, build_sql_producer_traversal
from prepared_knowledge_runtime.normalization import stable_id


_TERMINAL_RELATION_KINDS = {
    "physical",
    "physical_template",
    "dynamic",
    "unresolved",
    "target",
    "temp",
}
_COMPOSITE_RELATION_KINDS = {"cte", "derived", "set", "subquery"}


def _json_value(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(str(value))
    except Exception:
        return default


def _structural_key(value: Any) -> Any:
    """Return a deterministic hashable key without serializing JSON.

    This is used only for in-memory de-duplication of already observed lineage
    branches. Published JSON and stable identifiers keep their canonical encoding.
    """
    if isinstance(value, dict):
        return tuple((str(key), _structural_key(item)) for key, item in sorted(value.items(), key=lambda pair: str(pair[0])))
    if isinstance(value, (list, tuple)):
        return tuple(_structural_key(item) for item in value)
    if isinstance(value, set):
        return tuple(sorted((_structural_key(item) for item in value), key=repr))
    return value




def _normalized_expression(value: Any) -> str:
    return " ".join(str(value or "").split()).casefold()


def _effective_transformation_key(transformations: list[dict[str, Any]]) -> tuple[Any, ...]:
    """Return the useful transformation identity, excluding passthrough path mechanics.

    Projection ids and alias-only/direct-column hops are provenance, not a distinct
    target-to-source calculation.  Explicit expressions and config column mappings
    remain part of identity so materially different calculations are never merged.
    """
    effective: list[Any] = []
    for item in transformations or []:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or "")
        expression_kind = str(item.get("expression_kind") or "")
        expression = _normalized_expression(item.get("expression"))
        if kind == "observed_config_column_mapping":
            effective.append((
                kind,
                str(item.get("target_column") or "").casefold(),
                str(item.get("source_column") or "").casefold(),
            ))
            continue
        if expression_kind == "direct_column":
            continue
        if expression == "*" or expression.endswith(".*"):
            continue
        if expression or expression_kind:
            effective.append((expression_kind, expression))
    return tuple(effective)


def _branch_anchor_step(terminal: dict[str, Any], target_logical_name: str = "") -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    relation_path = [dict(item) for item in terminal.get("relation_path") or () if isinstance(item, dict)]
    target_key = str(target_logical_name or "").strip().casefold()
    target_key = target_key.rsplit(".", 1)[-1]
    search_from = 0
    if target_key:
        for index, item in enumerate(relation_path):
            kind = str(item.get("relation_kind") or "").strip().lower()
            name = str(item.get("relation_name") or "").strip().casefold().rsplit(".", 1)[-1]
            if kind in {"cte", "derived", "set", "subquery"} and name == target_key:
                search_from = index + 1
                break
    physical_candidates = [
        item for item in relation_path[search_from:]
        if str(item.get("relation_kind") or "") in {"physical", "physical_template"} and str(item.get("scope_id") or "")
    ]
    non_target_candidates = [
        item for item in physical_candidates
        if not target_key or str(item.get("relation_name") or "").strip().casefold().rsplit(".", 1)[-1] != target_key
    ]
    if non_target_candidates or physical_candidates:
        return (non_target_candidates or physical_candidates)[0], relation_path
    fallback_candidates = [
        item for item in relation_path
        if str(item.get("relation_kind") or "") in {"physical", "physical_template"} and str(item.get("scope_id") or "")
    ]
    non_target_fallback = [
        item for item in fallback_candidates
        if not target_key or str(item.get("relation_name") or "").strip().casefold().rsplit(".", 1)[-1] != target_key
    ]
    if non_target_fallback or fallback_candidates:
        return (non_target_fallback or fallback_candidates)[0], relation_path
    return None, relation_path


def _branch_identity_from_terminal(terminal: dict[str, Any], target_logical_name: str = "") -> tuple[str, str, int]:
    anchor, _relation_path = _branch_anchor_step(terminal, target_logical_name)
    if anchor is None:
        return "", "", 0
    return str(anchor.get("query_id") or ""), str(anchor.get("scope_id") or ""), int(anchor.get("scope_ordinal") or 0)


def _safe_branch_label(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text or "${" in text or "{{" in text or "%(" in text:
        return None
    return text.rsplit(".", 1)[-1] or None


def _branch_metadata(terminal: dict[str, Any], traversal: Any, target_logical_name: str = "") -> dict[str, Any]:
    first_physical, relation_path = _branch_anchor_step(terminal, target_logical_name)
    if first_physical is None:
        return {
            "source_branch": None,
            "source_branch_scope_id": None,
            "source_branch_ordinal": None,
            "branch_relation_id": None,
            "branch_relation_name": None,
            "source_relation_role": "unknown",
            "source_relation_role_basis": "branch_scope_not_observed_in_relation_path",
            "relation_path": relation_path,
        }
    scope_id = str(first_physical.get("scope_id") or "")
    candidate_ids = [
        str(item) for item in traversal.relations_by_scope.get(scope_id, ())
        if str((traversal.relations.get(str(item)) or {}).get("usage_role") or "").strip().lower() == "from"
    ]
    driver_id = candidate_ids[0] if len(candidate_ids) == 1 else None
    driver = traversal.relations.get(driver_id) if driver_id else None
    driver_name = str((driver or {}).get("name") or "") or None
    ordinal = int(first_physical.get("scope_ordinal") or 0) or None
    branch = _safe_branch_label(driver_name) or _safe_branch_label(first_physical.get("relation_name")) or (f"branch_{ordinal}" if ordinal else scope_id)

    # A terminal source is an enrichment when its value reaches the target branch
    # through any observed JOIN boundary after the branch anchor.  This remains a
    # strongly-supported derived role: the JOIN facts are observed, while the
    # business label "enrichment" is interpretation over that path.
    try:
        anchor_index = relation_path.index(first_physical)
    except ValueError:
        anchor_index = 0
    path_after_anchor = relation_path[anchor_index:]
    join_steps = [item for item in path_after_anchor if str(item.get("usage_role") or "").strip().lower() == "join"]
    first_role = str(first_physical.get("usage_role") or "").strip().lower()
    first_relation_id = str(first_physical.get("relation_id") or "")
    if join_steps:
        relation_role = "enrichment"
        role_basis = "observed_join_boundary_on_value_path_after_target_branch_anchor"
    elif driver_id and first_relation_id == driver_id:
        relation_role = "driver_path"
        role_basis = "unique_from_relation_in_target_branch_scope_and_no_join_boundary_on_value_path"
    elif first_role == "from":
        relation_role = "driver_candidate"
        role_basis = (
            "value_path_enters_target_branch_via_from_relation_but_driver_is_not_unique"
            if len(candidate_ids) != 1 else
            "value_path_enters_target_branch_via_from_relation"
        )
    elif first_role == "join":
        relation_role = "enrichment"
        role_basis = "value_path_enters_target_branch_via_observed_join_relation"
    else:
        relation_role = "unknown"
        role_basis = "target_branch_relation_usage_role_not_decisive"
    return {
        "source_branch": branch,
        "source_branch_scope_id": scope_id,
        "source_branch_ordinal": ordinal,
        "branch_relation_id": driver_id,
        "branch_relation_name": driver_name,
        "driver_candidate_relation_ids": candidate_ids,
        "source_relation_role": relation_role,
        "source_relation_role_basis": role_basis,
        "relation_path": relation_path,
    }



def _explicit_null_projection(expression: Any) -> bool:
    text = " ".join(str(expression or "").strip().lower().split())
    if not text:
        return False
    return bool(
        re.match(r"^null(?:\s+as\s+.+)?$", text)
        or re.match(r"^cast\s*\(\s*null\s+as\s+[^)]+\)(?:\s+as\s+.+)?$", text)
    )


def _join_branch_selector_index(connection: Any, *, repo_id: str) -> dict[tuple[str, str], list[dict[str, Any]]]:
    """Index observed equality join-key columns by branch scope and relation.

    The index is evidence-only.  It does not infer branch names or producer choice.
    A selector is useful downstream only when exactly one equality-key column is
    observed for the joined relation in that SELECT scope.
    """
    indexed: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    rows = connection.execute(
        "SELECT sql_join_edge_id,scope_id,column_pairs_json FROM sql_join_edge "
        "WHERE repo_id=? ORDER BY scope_id,join_ordinal,sql_join_edge_id",
        [repo_id],
    ).fetchall()
    for join_edge_id, scope_id, pairs_json in rows:
        for pair in _json_value(pairs_json, []):
            if not isinstance(pair, dict):
                continue
            operator = str(pair.get("operator") or "").strip()
            role = str(pair.get("predicate_role") or "").strip().lower()
            status = str(pair.get("resolution_status") or "").strip().lower()
            if operator != "=" or role != "equality_key" or status not in {"confirmed", "resolved"}:
                continue
            for side in ("left", "right"):
                relation_id = str(pair.get(f"{side}_relation_id") or "")
                column = str(pair.get(f"{side}_column") or "").strip()
                if relation_id and column:
                    indexed[(str(scope_id or ""), relation_id)].append({
                        "join_edge_id": str(join_edge_id or ""),
                        "column": column,
                        "predicate": str(pair.get("predicate") or ""),
                    })
    return indexed


def _filter_terminals_by_join_branch_selector(
    terminals: list[dict[str, Any]],
    *,
    traversal: Any,
    selector_index: dict[tuple[str, str], list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """Filter impossible inner UNION branches using an observed outer JOIN key.

    Example pattern (generic): an outer branch joins an intermediate union-backed
    table by ``c.source_a_sid``.  If the inner union has one branch where
    ``source_a_sid`` is populated and sibling branches explicitly project NULL for
    that column, only the populated branch is compatible with the observed JOIN.

    No filtering happens when the selector, set container, or branch projection is
    ambiguous/unobserved.
    """
    projection_state_cache: dict[tuple[str, str], str] = {}

    def projection_state(scope_id: str, column: str) -> str:
        key = (scope_id, column.strip().lower())
        if key in projection_state_cache:
            return projection_state_cache[key]
        matches = [
            traversal.projections[pid]
            for pid in traversal.projections_by_scope.get(scope_id, ())
            if str(traversal.projections[pid].get("output") or "").strip().lower() == key[1]
            and not traversal.projections[pid].get("wildcard")
        ]
        if not matches:
            state = "unknown"
        elif all(_explicit_null_projection(item.get("expression")) for item in matches):
            state = "explicit_null"
        elif any(not _explicit_null_projection(item.get("expression")) for item in matches):
            state = "populated"
        else:
            state = "unknown"
        projection_state_cache[key] = state
        return state

    result: list[dict[str, Any]] = []
    for terminal in terminals:
        path = [dict(item) for item in terminal.get("relation_path") or () if isinstance(item, dict)]
        decision: tuple[str, dict[str, Any]] | None = None
        for index, step in enumerate(path):
            if str(step.get("usage_role") or "").strip().lower() != "join":
                continue
            scope_id = str(step.get("scope_id") or "")
            relation_id = str(step.get("relation_id") or "")
            selectors = selector_index.get((scope_id, relation_id), ())
            selector_columns = sorted({str(item.get("column") or "").strip() for item in selectors if item.get("column")})
            if len(selector_columns) != 1:
                continue
            selector_column = selector_columns[0]

            # Find the first later observed relation that fans out into multiple
            # source scopes.  The next path step belonging to one of those scopes
            # identifies the concrete branch actually traversed.
            for container_index in range(index + 1, len(path)):
                container_id = str(path[container_index].get("relation_id") or "")
                container = traversal.relations.get(container_id) or {}
                source_scopes = {str(item) for item in container.get("source_scopes") or () if item}
                if len(source_scopes) <= 1:
                    continue
                selected_scope = ""
                for branch_step in path[container_index + 1 :]:
                    candidate_scope = str(branch_step.get("scope_id") or "")
                    if candidate_scope in source_scopes:
                        selected_scope = candidate_scope
                        break
                if not selected_scope:
                    break
                state = projection_state(selected_scope, selector_column)
                if state in {"populated", "explicit_null"}:
                    selector_meta = {
                        "selector_column": selector_column,
                        "outer_scope_id": scope_id,
                        "joined_relation_id": relation_id,
                        "join_edge_ids": sorted({str(item.get("join_edge_id") or "") for item in selectors if item.get("join_edge_id")}),
                        "set_container_relation_id": container_id,
                        "selected_branch_scope_id": selected_scope,
                        "branch_projection_state": state,
                        "basis": "observed_join_key_plus_inner_set_branch_selector_projection",
                    }
                    decision = (state, selector_meta)
                break
            if decision is not None:
                break

        if decision is None:
            result.append(terminal)
            continue
        state, selector_meta = decision
        if state == "explicit_null":
            continue
        copied = dict(terminal)
        copied["join_branch_selector"] = selector_meta
        result.append(copied)
    return result

def _aggregate_equivalent_terminals(terminals: list[dict[str, Any]], *, target_logical_name: str = "") -> list[dict[str, Any]]:
    """Collapse technical routes to useful terminal source+calculation facts.

    Identity is the observed terminal relation field plus its effective transformation
    (non-passthrough expressions/config mappings) and resolution state.  A column-usage
    id and the full projection chain are provenance occurrences, not separate useful
    S2T facts.  Keep a deterministic representative path and aggregate the observed
    ids/counts needed to inspect the evidence.
    """
    unique: dict[tuple[Any, ...], dict[str, Any]] = {}
    for terminal in terminals:
        transformations = list(terminal.get("transformations") or [])
        branch_identity = _branch_identity_from_terminal(terminal, target_logical_name)
        key = (
            branch_identity,
            terminal.get("terminal_source_kind"),
            terminal.get("terminal_relation_id"),
            terminal.get("terminal_relation_name"),
            terminal.get("terminal_relation_kind"),
            str(terminal.get("terminal_column") or "").casefold(),
            _effective_transformation_key(transformations),
            terminal.get("recursive_resolution_status"),
            terminal.get("physical_origin_status"),
            terminal.get("lineage_status"),
        )
        materialization_path = [str(item) for item in terminal.get("materialization_path") or ()]
        dependency_path = [str(item) for item in terminal.get("workflow_dependency_path") or ()]
        usage_id = str(terminal.get("terminal_column_usage_id") or "")
        projection_ids = {
            str(item.get("projection_id"))
            for item in transformations
            if isinstance(item, dict) and item.get("projection_id")
        }
        candidate_path = {
            "materialization_path": materialization_path,
            "workflow_dependency_path": dependency_path,
        }
        candidate_rank = (
            len(materialization_path) + len(dependency_path) + len(transformations),
            canonical_json(candidate_path),
            usage_id,
            canonical_json(transformations),
        )

        slot = unique.get(key)
        if slot is None:
            slot = dict(terminal)
            slot["_equivalent_observed_path_count"] = 1
            slot["_equivalent_column_usage_ids"] = {usage_id} if usage_id else set()
            slot["_equivalent_projection_ids"] = set(projection_ids)
            slot["_equivalent_materialization_ids"] = set(materialization_path)
            slot["_equivalent_workflow_dependency_ids"] = set(dependency_path)
            slot["_representative_path_rank"] = candidate_rank
            unique[key] = slot
            continue

        slot["_equivalent_observed_path_count"] = int(slot.get("_equivalent_observed_path_count") or 1) + 1
        if usage_id:
            slot.setdefault("_equivalent_column_usage_ids", set()).add(usage_id)
        slot.setdefault("_equivalent_projection_ids", set()).update(projection_ids)
        slot.setdefault("_equivalent_materialization_ids", set()).update(materialization_path)
        slot.setdefault("_equivalent_workflow_dependency_ids", set()).update(dependency_path)
        if candidate_rank < slot.get("_representative_path_rank", candidate_rank):
            preserved = {
                key_name: slot.get(key_name)
                for key_name in (
                    "_equivalent_observed_path_count",
                    "_equivalent_column_usage_ids",
                    "_equivalent_projection_ids",
                    "_equivalent_materialization_ids",
                    "_equivalent_workflow_dependency_ids",
                )
            }
            replacement = dict(terminal)
            replacement.update(preserved)
            replacement["_representative_path_rank"] = candidate_rank
            unique[key] = replacement

    result: list[dict[str, Any]] = []
    for slot in unique.values():
        slot.pop("_representative_path_rank", None)
        result.append(slot)
    return result


def _is_main_target_script_template(template: str) -> bool:
    """Return true only when the invoked SQL basename is parameterized by main_table_name.

    The workflow itself is the evidence: e.g. `${main_table_name}.sql`. A directory
    that merely contains `main_table_name` (such as `.../main_table_name/prep_src.sql`)
    is not considered the final target transform.
    """
    name = PurePosixPath(str(template or "").replace("\\", "/")).name.casefold()
    return "main_table_name" in name and name.endswith(".sql")


def materialize_sql_workflow_target_lineage(connection: Any, *, repo_id: str) -> dict[str, Any]:
    """Materialize workflow-resolved target columns over already observed SQL projections.

    This composes only facts already present in the SQL knowledge artifact:
    workflow `main_table_name`, resolved script-invocation reachability, root SELECT
    projections, CTE/derived scope links and column usages. It never derives a physical
    target relation name here; that exact relation identity remains the responsibility of
    the existing target resolver at query time.
    """
    connection.execute("DELETE FROM sql_workflow_target_column_lineage WHERE repo_id=?", [repo_id])
    connection.execute("DELETE FROM sql_workflow_target_lineage_gap WHERE repo_id=?", [repo_id])

    reference_by_id: dict[str, dict[str, Any]] = {}
    for row in connection.execute(
        "SELECT sql_workflow_file_reference_id, source_kind, target_path_template, "
        "resolved_target_file, resolution_status, resolution_basis, evidence_json "
        "FROM sql_workflow_file_reference WHERE repo_id=?",
        [repo_id],
    ).fetchall():
        reference_by_id[str(row[0])] = {
            "source_kind": str(row[1] or ""),
            "template": str(row[2] or ""),
            "resolved_file": row[3],
            "resolution_status": str(row[4] or ""),
            "resolution_basis": str(row[5] or ""),
            "evidence": _json_value(row[6], []),
        }

    main_table_by_workflow: dict[str, list[str]] = defaultdict(list)
    workflow_binding_evidence: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in connection.execute(
        "SELECT file, scalar_value, value_expression, resolution_status, evidence_json "
        "FROM sql_workflow_binding WHERE repo_id=? AND lower(binding_name)='main_table_name' ORDER BY file, line_start",
        [repo_id],
    ).fetchall():
        workflow_file = str(row[0] or "")
        value = str(row[1] if row[1] is not None else row[2] or "").strip()
        if not workflow_file or not value or "$" in value:
            continue
        main_table_by_workflow[workflow_file].append(value)
        workflow_binding_evidence[(workflow_file, value)].extend(
            item for item in _json_value(row[4], []) if isinstance(item, dict)
        )
    for workflow_file in list(main_table_by_workflow):
        main_table_by_workflow[workflow_file] = sorted(dict.fromkeys(main_table_by_workflow[workflow_file]))

    # Reuse the canonical observed-producer traversal used by the generic SQL
    # target/source materialization.  Workflow target lineage must not maintain a
    # second, weaker CTE/wildcard resolver: the same observed SQL facts and
    # producer index define value origins everywhere.
    with timed_phase("workflow-target-lineage derive producer observations"):
        producer_observations = derive_sql_producer_observations(connection, repo_id=repo_id)
    observation_dependencies = getattr(producer_observations, "dependencies", ())
    emit_progress(
        f"workflow-target-lineage producer observations materializations={len(producer_observations.materializations)} "
        f"workflow_dependencies={len(observation_dependencies)}"
    )
    with timed_phase("workflow-target-lineage build producer traversal"):
        producer_traversal, producer_usages, producer_relations = build_sql_producer_traversal(
            connection, repo_id=repo_id, observations=producer_observations
        )
    join_branch_selector_index = _join_branch_selector_index(connection, repo_id=repo_id)

    materialization_by_id = {
        str(item.get("id") or ""): dict(item)
        for item in producer_observations.materializations
        if item.get("id")
    }

    usage_evidence: dict[str, list[dict[str, Any]]] = {}
    usage_maturity: dict[str, str] = {}
    for row in connection.execute(
        "SELECT sql_column_usage_id, evidence_maturity_level, evidence_json "
        "FROM sql_column_usage WHERE repo_id=?",
        [repo_id],
    ).fetchall():
        usage_id = str(row[0])
        usage_maturity[usage_id] = str(row[1] or "")
        usage_evidence[usage_id] = [
            item for item in _json_value(row[2], []) if isinstance(item, dict)
        ]

    def projection_transformations(origin: dict[str, Any], root_projection_id: str) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for marker in origin.get("projection_path") or ():
            marker_text = str(marker or "")
            if not marker_text.startswith("projection:"):
                continue
            projection_id = marker_text.split(":", 1)[1]
            if not projection_id or projection_id == root_projection_id:
                continue
            projection = producer_traversal.projections.get(projection_id)
            if not projection:
                continue
            out.append({
                "projection_id": projection_id,
                "output_name": projection.get("output") or None,
                "expression": projection.get("expression"),
                "expression_kind": projection.get("expression_kind"),
                "resolution_status": projection.get("resolution_status"),
            })
        return out

    def materialization_transformations(
        materialization_path: list[str] | tuple[str, ...], *, target_column: str
    ) -> list[dict[str, Any]]:
        """Describe only explicit observed column transforms on a producer path.

        Workflow copies are identity propagation and therefore are represented in the
        branch path, not as a fabricated expression. Config transforms may carry an
        observed target->source column map; preserve that map as a transformation.
        """
        out: list[dict[str, Any]] = []
        current_column = str(target_column or "").strip().lower()
        for materialization_id in materialization_path:
            producer = materialization_by_id.get(str(materialization_id))
            if not producer or str(producer.get("kind") or "") != "config_transform":
                continue
            mappings = (producer.get("provenance") or {}).get("column_mappings") or {}
            normalized_mappings = {
                str(key).strip().lower(): str(value).strip()
                for key, value in mappings.items()
                if key and value
            }
            source_column = normalized_mappings.get(current_column)
            if not source_column:
                continue
            out.append({
                "kind": "observed_config_column_mapping",
                "materialization_id": str(materialization_id),
                "target_column": current_column,
                "source_column": source_column,
                "mapping_basis": producer.get("mapping_basis"),
            })
            current_column = source_column.lower()
        return out

    def origin_terminal(
        origin: dict[str, Any], *, root_projection_id: str, root_target_column: str
    ) -> dict[str, Any] | None:
        usage_id = str(origin.get("usage_id") or origin.get("frontier_usage_id") or "")
        usage = producer_usages.get(usage_id) if usage_id else None
        relation_id = str(origin.get("relation_id") or (usage or {}).get("relation_id") or "")
        relation = producer_relations.get(relation_id) if relation_id else None
        relation_kind = str((relation or {}).get("kind") or (usage or {}).get("relation_kind") or "")
        relation_name = str((relation or {}).get("name") or (usage or {}).get("relation_name") or "")
        column = str(origin.get("column") or origin.get("frontier_column") or (usage or {}).get("column") or "")

        # A value usage with no relation (literal/parameter/unresolved expression)
        # remains a visible partial frontier.  Never invent a physical relation.
        source_kind = "column_usage"
        if not relation_id:
            source_kind = str((usage or {}).get("relation_kind") or "") or "unresolved_usage"
        physical_status = "confirmed" if relation_kind in {"physical", "physical_template"} else "unresolved"
        usage_resolution = str((usage or {}).get("resolution_status") or "")
        resolution_status = "resolved" if relation_name and usage_resolution == "resolved" else "partial"
        if relation_id and not usage_id:
            # A physical frontier reached through a wildcard can legitimately have
            # no concrete usage row for the propagated column. The observed relation
            # identity plus the single-relation wildcard contract is still grounded.
            resolution_status = "resolved" if relation_name else "partial"
            source_kind = "propagated_relation_column"
        transformations = [
            *materialization_transformations(
                origin.get("materialization_path") or (), target_column=root_target_column
            ),
            *projection_transformations(origin, root_projection_id),
        ]
        recursion_depth = len(transformations) + len(origin.get("materialization_path") or ())
        return {
            "terminal_source_kind": source_kind,
            "terminal_column_usage_id": usage_id or None,
            "terminal_column": column or None,
            "terminal_relation_id": relation_id or None,
            "terminal_relation_name": relation_name or None,
            "terminal_relation_kind": relation_kind or None,
            "recursion_depth": recursion_depth,
            "recursive_resolution_status": resolution_status,
            "physical_origin_status": physical_status,
            "lineage_status": "confirmed" if resolution_status == "resolved" and physical_status == "confirmed" else "partial",
            "transformations": transformations,
            "materialization_path": [str(item) for item in origin.get("materialization_path") or ()],
            "workflow_dependency_path": [str(item) for item in origin.get("workflow_dependency_path") or ()],
            "relation_path": [dict(item) for item in origin.get("relation_path") or () if isinstance(item, dict)],
            "evidence_maturity_level": usage_maturity.get(usage_id) or "derived",
            "evidence": usage_evidence.get(usage_id, []),
        }

    transform_count = 0
    target_column_count = 0
    lineage_path_count = 0
    gap_count = 0
    seen_transform_keys: set[tuple[str, str, str]] = set()
    script_seeded_workflow_targets: set[tuple[str, str]] = set()

    contexts = connection.execute(
        "SELECT workflow_context_file, reachable_file, context_reference_ids_json, context_hop_count, "
        "resolution_reasons_json FROM sql_workflow_context_file "
        "WHERE repo_id=? AND reachable_file_kind='sql' AND resolution_status='resolved' "
        "ORDER BY workflow_context_file, context_hop_count, reachable_file",
        [repo_id],
    ).fetchall()
    emit_progress(f"workflow-target-lineage resolved sql contexts={len(contexts)}")
    script_phase_started = __import__("time").monotonic()
    emit_progress("workflow-target-lineage script-seeded traversal started")
    for workflow_file_raw, reachable_file_raw, reference_ids_json, hop_count, context_reasons_json in contexts:
        workflow_file = str(workflow_file_raw or "")
        reachable_file = str(reachable_file_raw or "")
        targets = main_table_by_workflow.get(workflow_file, ())
        if len(targets) != 1:
            continue
        target_logical_name = targets[0]
        reference_ids = [str(item) for item in _json_value(reference_ids_json, []) if item]
        if not reference_ids:
            continue
        final_reference_id = reference_ids[-1]
        reference = reference_by_id.get(final_reference_id)
        if not reference or reference.get("source_kind") != "script_invocation":
            continue
        if not _is_main_target_script_template(str(reference.get("template") or "")):
            continue

        transform_key = (workflow_file, target_logical_name, reachable_file)
        if transform_key in seen_transform_keys:
            continue
        seen_transform_keys.add(transform_key)
        script_seeded_workflow_targets.add((workflow_file, target_logical_name.strip().lower()))
        transform_count += 1

        statement_rows = connection.execute(
            "SELECT query_id, line_start, statement_type FROM sql_statement "
            "WHERE repo_id=? AND file=? ORDER BY line_start, query_id",
            [repo_id, reachable_file],
        ).fetchall()
        for query_id_raw, query_line_start, statement_type in statement_rows:
            query_id = str(query_id_raw or "")
            root_scopes = [str(row[0]) for row in connection.execute(
                "SELECT sql_select_scope_id FROM sql_select_scope "
                "WHERE repo_id=? AND query_id=? AND parent_scope_id IS NULL ORDER BY scope_ordinal",
                [repo_id, query_id],
            ).fetchall()]
            if not root_scopes:
                continue
            for root_scope in root_scopes:
                root_projections = connection.execute(
                    "SELECT sql_projection_id, output_name, expression, expression_kind, "
                    "source_column_usage_ids_json, resolution_status, evidence_maturity_level, evidence_json "
                    "FROM sql_projection WHERE repo_id=? AND scope_id=? AND output_name IS NOT NULL "
                    "AND is_wildcard=false ORDER BY projection_ordinal",
                    [repo_id, root_scope],
                ).fetchall()
                for projection_row in root_projections:
                    projection_id = str(projection_row[0])
                    target_column = str(projection_row[1] or "").strip()
                    if not target_column:
                        continue
                    target_column_count += 1
                    root_projection = producer_traversal.projections.get(projection_id)
                    origins = producer_traversal.projection_origins(
                        workflow_file, root_projection
                    ) if root_projection else []
                    terminals = [
                        terminal
                        for origin in origins
                        if (terminal := origin_terminal(
                                origin, root_projection_id=projection_id, root_target_column=target_column
                            )) is not None
                    ]
                    terminals = _filter_terminals_by_join_branch_selector(
                        terminals, traversal=producer_traversal, selector_index=join_branch_selector_index
                    )
                    # Deterministic de-duplication of the same terminal reached through equivalent branches.
                    unique_terminals: dict[tuple[Any, ...], dict[str, Any]] = {}
                    for terminal in terminals:
                        key = (
                            terminal.get("terminal_relation_id"),
                            terminal.get("terminal_relation_name"),
                            terminal.get("terminal_column"),
                            _structural_key(terminal.get("transformations") or []),
                        )
                        unique_terminals.setdefault(key, terminal)
                    terminals = list(unique_terminals.values())

                    base_evidence = [
                        *workflow_binding_evidence.get((workflow_file, target_logical_name), ()),
                        *[item for item in reference.get("evidence") or () if isinstance(item, dict)],
                        *[item for item in _json_value(projection_row[7], []) if isinstance(item, dict)],
                    ]
                    mapping_basis = (
                        "resolved_workflow_main_table_binding_plus_contextual_script_invocation_"
                        "plus_root_projection_plus_canonical_observed_producer_column_traversal"
                    )
                    if not terminals:
                        gap_id = stable_id(
                            "sql_workflow_target_lineage_gap",
                            repo_id,
                            workflow_file,
                            target_logical_name,
                            query_id,
                            projection_id,
                        )
                        connection.execute(
                            "INSERT OR IGNORE INTO sql_workflow_target_lineage_gap VALUES "
                            "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                            [
                                gap_id,
                                repo_id,
                                workflow_file,
                                target_logical_name,
                                final_reference_id,
                                query_id,
                                reachable_file,
                                query_line_start,
                                target_column,
                                projection_id,
                                projection_row[5],
                                "workflow_target_projection_source_unresolved",
                                "target_column_source_lineage_incomplete",
                                mapping_basis,
                                "derived",
                                canonical_json({
                                    "workflow_context_hop_count": int(hop_count or 0),
                                    "workflow_context_reasons": _json_value(context_reasons_json, []),
                                    "statement_type": statement_type,
                                    "evidence": base_evidence,
                                }),
                            ],
                        )
                        gap_count += 1
                        continue

                    for terminal in terminals:
                        lineage_id = stable_id(
                            "sql_workflow_target_column_lineage",
                            repo_id,
                            workflow_file,
                            target_logical_name,
                            query_id,
                            projection_id,
                            terminal.get("terminal_relation_id"),
                            terminal.get("terminal_relation_name"),
                            terminal.get("terminal_column"),
                            canonical_json(terminal.get("transformations") or []),
                        )
                        branch_path = [{
                            "kind": "workflow_target",
                            "workflow_context_file": workflow_file,
                            "target_logical_name": target_logical_name,
                            "transform_reference_id": final_reference_id,
                            "transform_file": reachable_file,
                        }]
                        branch_path.extend(
                            {"kind": "observed_relation_materialization", "materialization_id": item}
                            for item in terminal.get("materialization_path") or ()
                        )
                        branch_path.extend(
                            {"kind": "observed_workflow_dependency", "workflow_dependency_id": item}
                            for item in terminal.get("workflow_dependency_path") or ()
                        )
                        connection.execute(
                            "INSERT OR IGNORE INTO sql_workflow_target_column_lineage VALUES "
                            "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                            [
                                lineage_id,
                                repo_id,
                                workflow_file,
                                target_logical_name,
                                final_reference_id,
                                query_id,
                                reachable_file,
                                query_line_start,
                                target_column,
                                projection_id,
                                projection_row[2],
                                projection_row[3],
                                terminal.get("terminal_source_kind") or "column_usage",
                                terminal.get("terminal_column_usage_id"),
                                terminal.get("terminal_column"),
                                terminal.get("terminal_relation_id"),
                                terminal.get("terminal_relation_name"),
                                terminal.get("terminal_relation_kind"),
                                int(terminal.get("recursion_depth") or 0),
                                canonical_json(branch_path),
                                canonical_json(terminal.get("transformations") or []),
                                terminal.get("recursive_resolution_status") or "partial",
                                terminal.get("physical_origin_status") or "unresolved",
                                terminal.get("lineage_status") or "partial",
                                "derived",
                                mapping_basis,
                                canonical_json({
                                    "workflow_context_hop_count": int(hop_count or 0),
                                    "workflow_context_reasons": _json_value(context_reasons_json, []),
                                    "statement_type": statement_type,
                                    "projection_resolution_status": projection_row[5],
                                    "evidence": [*base_evidence, *terminal.get("evidence", [])],
                                }),
                            ],
                        )
                        lineage_path_count += 1

    emit_progress(
        f"workflow-target-lineage script-seeded traversal completed; "
        f"duration={__import__('time').monotonic() - script_phase_started:.1f}s; "
        f"transforms={transform_count}; target_columns={target_column_count}; lineage_paths={lineage_path_count}; gaps={gap_count}"
    )

    # Some workflows publish their final target through an observed materialization
    # (for example an s2tTableList copy or a referenced config transform) rather than
    # through a final `${main_table_name}.sql` invocation. Reuse the same producer
    # index as a second target anchor. Never infer output columns from naming: all
    # direct producers must expose the same complete observed output contract.
    materialization_target_pairs: set[tuple[str, str]] = {
        (workflow_file, targets[0])
        for workflow_file, targets in main_table_by_workflow.items()
        if len(targets) == 1
    }
    # Any resolved observed workflow-copy contract is itself a publication target
    # anchor.  The producer-observation layer already owns the evidence rules that
    # establish a copy (direct s2tTableList or a scoped parameter environment plus
    # a referenced s2tTableList).  Do not couple target-lineage consumption to one
    # producer mapping_basis string: doing so discards equally observed copy facts.
    # No target is inferred from filenames or name similarity here.
    for producer in producer_observations.materializations:
        if str(producer.get("kind") or "") != "workflow_copy":
            continue
        if str(producer.get("resolution_status") or "") not in {"matched", "resolved"}:
            continue
        workflow_file = str(producer.get("workflow") or "").strip()
        target_logical_name = str(producer.get("table") or "").strip()
        if not workflow_file or not target_logical_name:
            continue
        materialization_target_pairs.add((workflow_file, target_logical_name))
        provenance = producer.get("provenance") or {}
        anchor_evidence: list[dict[str, Any]] = []
        anchor_evidence.extend(
            item for item in provenance.get("binding_evidence") or () if isinstance(item, dict)
        )
        anchor_evidence.extend(
            item for item in provenance.get("template_evidence") or () if isinstance(item, dict)
        )
        for record in provenance.get("parameter_records") or ():
            if not isinstance(record, dict):
                continue
            anchor_evidence.extend(
                item for item in record.get("evidence") or () if isinstance(item, dict)
            )
        workflow_binding_evidence[(workflow_file, target_logical_name)].extend(anchor_evidence)

    materialization_phase_started = __import__("time").monotonic()
    emit_progress(
        f"workflow-target-lineage materialization-seeded traversal started; target_pairs={len(materialization_target_pairs)}"
    )
    materialization_lineage_rows: list[list[Any]] = []
    for target_ordinal, (workflow_file, target_logical_name) in enumerate(sorted(materialization_target_pairs), start=1):
        target_started = __import__("time").monotonic()
        target_lineage_before = lineage_path_count
        target_gap_before = gap_count
        target_key = (workflow_file, target_logical_name.strip().lower())
        emit_progress(
            f"workflow-target-lineage target {target_ordinal}/{len(materialization_target_pairs)} "
            f"started; table={target_logical_name}; workflow={workflow_file}"
        )
        if target_key in script_seeded_workflow_targets:
            continue

        producer_pairs = [
            (producer, dependency_path)
            for producer, dependency_path in producer_traversal.materializations.producers(
                workflow_file, target_logical_name
            )
            if str(producer.get("workflow") or "") == workflow_file and not dependency_path
        ]
        if not producer_pairs:
            continue

        contracts: list[tuple[dict[str, Any], set[str], str]] = []
        incomplete: list[dict[str, Any]] = []
        for producer, _dependency_path in producer_pairs:
            contract, contract_basis = producer_traversal.materializations.output_contract(producer)
            if contract is None and str(producer.get("kind") or "") in {"workflow_copy", "config_transform"}:
                # Final-target useful-knowledge fallback only. If a direct observed
                # copy/transform points at a source relation with at least one
                # complete observed producer contract, and every complete contract
                # agrees, preserve that column set as partial. Incomplete sibling
                # producer branches remain diagnostics; this does not change the
                # global producer traversal contract semantics.
                source_table = str(producer.get("source_table") or "").strip().lower()
                source_contracts: list[set[str]] = []
                source_incomplete: list[dict[str, Any]] = []
                if source_table:
                    for source_producer, _source_dependency_path in producer_traversal.materializations.producers(
                        str(producer.get("workflow") or workflow_file), source_table
                    ):
                        source_contract, source_basis = producer_traversal.materializations.output_contract(source_producer)
                        if source_contract is None:
                            source_incomplete.append({
                                "materialization_id": source_producer.get("id"),
                                "kind": source_producer.get("kind"),
                                "source_file": source_producer.get("source_file"),
                                "contract_basis": source_basis,
                            })
                        else:
                            source_contracts.append(set(source_contract))
                if source_contracts and all(item == source_contracts[0] for item in source_contracts[1:]):
                    contract = set(source_contracts[0])
                    contract_basis = f"{producer.get('kind')}_partial_consistent_source_contract_at_final_target"
                    incomplete.append({
                        "materialization_id": producer.get("id"),
                        "kind": producer.get("kind"),
                        "source_file": producer.get("source_file"),
                        "contract_basis": contract_basis,
                        "partial_contract_used": True,
                        "incomplete_source_producers": source_incomplete,
                    })
            if contract is None:
                incomplete.append({
                    "materialization_id": producer.get("id"),
                    "kind": producer.get("kind"),
                    "source_file": producer.get("source_file"),
                    "contract_basis": contract_basis,
                })
                continue
            contracts.append((producer, set(contract), contract_basis))

        anchor = producer_pairs[0][0]
        anchor_id = str(anchor.get("id") or anchor.get("source_fact_id") or "")
        anchor_file = str(anchor.get("source_file") or "") or None
        fatal_incomplete = [item for item in incomplete if not item.get("partial_contract_used")]
        if not contracts:
            gap_id = stable_id(
                "sql_workflow_target_lineage_gap", repo_id, workflow_file,
                target_logical_name, "materialization_contract_incomplete"
            )
            connection.execute(
                "INSERT OR IGNORE INTO sql_workflow_target_lineage_gap VALUES "
                "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    gap_id, repo_id, workflow_file, target_logical_name, anchor_id,
                    None, anchor_file, None, None, None, None,
                    "workflow_target_materialization_output_contract_incomplete",
                    "target_column_set_unresolved",
                    "observed_final_materialization_has_no_complete_output_contract",
                    "derived",
                    canonical_json({
                        "direct_materializations": fatal_incomplete or incomplete,
                        "evidence": workflow_binding_evidence.get(
                            (workflow_file, target_logical_name), []
                        ),
                    }),
                ],
            )
            gap_count += 1
            continue

        first_contract = contracts[0][1]
        if any(contract != first_contract for _producer, contract, _basis in contracts[1:]):
            gap_id = stable_id(
                "sql_workflow_target_lineage_gap", repo_id, workflow_file,
                target_logical_name, "materialization_contract_ambiguous"
            )
            connection.execute(
                "INSERT OR IGNORE INTO sql_workflow_target_lineage_gap VALUES "
                "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    gap_id, repo_id, workflow_file, target_logical_name, anchor_id,
                    None, anchor_file, None, None, None, None,
                    "workflow_target_materialization_output_contract_ambiguous",
                    "target_column_set_ambiguous",
                    "observed_final_materializations_have_different_output_contracts",
                    "derived",
                    canonical_json({
                        "direct_materializations": [
                            {
                                "materialization_id": producer.get("id"),
                                "kind": producer.get("kind"),
                                "source_file": producer.get("source_file"),
                                "output_columns": sorted(contract),
                                "contract_basis": basis,
                            }
                            for producer, contract, basis in contracts
                        ],
                        "evidence": workflow_binding_evidence.get(
                            (workflow_file, target_logical_name), []
                        ),
                    }),
                ],
            )
            gap_count += 1
            continue

        transform_count += 1
        direct_materialization_ids = [str(producer.get("id") or "") for producer, _, _ in contracts]
        producer_evidence: list[dict[str, Any]] = []
        for producer, _contract, _basis in contracts:
            provenance = producer.get("provenance") or {}
            producer_evidence.extend(
                item for item in provenance.get("binding_evidence") or () if isinstance(item, dict)
            )

        partial_contract = bool(incomplete) or any("partial_consistent" in basis for _producer, _contract, basis in contracts)
        if fatal_incomplete:
            gap_id = stable_id(
                "sql_workflow_target_lineage_gap", repo_id, workflow_file,
                target_logical_name, "materialization_branch_incomplete"
            )
            connection.execute(
                "INSERT OR IGNORE INTO sql_workflow_target_lineage_gap VALUES "
                "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    gap_id, repo_id, workflow_file, target_logical_name, anchor_id,
                    None, anchor_file, None, None, None, None,
                    "workflow_target_materialization_branch_incomplete",
                    "target_column_set_partial",
                    "consistent_complete_direct_producer_contract_with_incomplete_sibling_branches",
                    "derived",
                    canonical_json({
                        "incomplete_direct_materializations": fatal_incomplete,
                        "complete_direct_materializations": [
                            {
                                "materialization_id": producer.get("id"),
                                "kind": producer.get("kind"),
                                "source_file": producer.get("source_file"),
                                "output_columns": sorted(contract),
                                "contract_basis": basis,
                            }
                            for producer, contract, basis in contracts
                        ],
                        "evidence": workflow_binding_evidence.get((workflow_file, target_logical_name), []),
                    }),
                ],
            )
            gap_count += 1
        mapping_basis = (
            "resolved_workflow_main_table_binding_plus_observed_final_materialization_"
            + (
                "plus_partial_consistent_output_contract_plus_canonical_observed_producer_column_traversal"
                if partial_contract
                else "plus_complete_consistent_output_contract_plus_canonical_observed_producer_column_traversal"
            )
        )
        emit_progress(
            f"workflow-target-lineage target {target_ordinal}/{len(materialization_target_pairs)} "
            f"contract resolved; table={target_logical_name}; columns={len(first_contract)}; "
            f"direct_producers={len(producer_pairs)}; usable_contracts={len(contracts)}; "
            f"incomplete_branches={len(incomplete)}"
        )
        for target_column in sorted(first_contract):
            target_column_count += 1
            column_started = __import__("time").monotonic()
            origins = producer_traversal.materialized_table_column_origins(
                workflow_file, target_logical_name, target_column
            )
            column_elapsed = __import__("time").monotonic() - column_started
            if column_elapsed >= 1.0:
                emit_progress(
                    f"workflow-target-lineage slow column; table={target_logical_name}; "
                    f"column={target_column}; duration={column_elapsed:.1f}s; origins={len(origins)}"
                )
            terminals = [
                terminal
                for origin in origins
                if (terminal := origin_terminal(
                    origin, root_projection_id="", root_target_column=target_column
                )) is not None
            ]
            raw_terminal_count = len(terminals)
            terminals = _filter_terminals_by_join_branch_selector(
                terminals, traversal=producer_traversal, selector_index=join_branch_selector_index
            )
            terminals = _aggregate_equivalent_terminals(terminals, target_logical_name=target_logical_name)
            if raw_terminal_count != len(terminals):
                emit_progress(
                    f"workflow-target-lineage path aggregation; table={target_logical_name}; "
                    f"column={target_column}; raw_paths={raw_terminal_count}; "
                    f"terminal_facts={len(terminals)}"
                )

            if not terminals:
                gap_id = stable_id(
                    "sql_workflow_target_lineage_gap", repo_id, workflow_file,
                    target_logical_name, target_column, "materialization_source_unresolved"
                )
                connection.execute(
                    "INSERT OR IGNORE INTO sql_workflow_target_lineage_gap VALUES "
                    "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [
                        gap_id, repo_id, workflow_file, target_logical_name, anchor_id,
                        None, anchor_file, None, target_column, None, None,
                        "workflow_target_materialization_source_unresolved",
                        "target_column_source_lineage_incomplete", mapping_basis, "derived",
                        canonical_json({
                            "direct_materialization_ids": direct_materialization_ids,
                            "output_contract_basis": [basis for _p, _c, basis in contracts],
                            "evidence": [
                                *workflow_binding_evidence.get((workflow_file, target_logical_name), ()),
                                *producer_evidence,
                            ],
                        }),
                    ],
                )
                gap_count += 1
                continue

            for terminal in terminals:
                path = [str(item) for item in terminal.get("materialization_path") or ()]
                dependency_path = [str(item) for item in terminal.get("workflow_dependency_path") or ()]
                equivalent_path_count = int(terminal.get("_equivalent_observed_path_count") or 1)
                equivalent_usage_ids = sorted(
                    str(item) for item in terminal.get("_equivalent_column_usage_ids") or () if item
                )
                equivalent_projection_ids = sorted(
                    str(item) for item in terminal.get("_equivalent_projection_ids") or () if item
                )
                equivalent_materialization_ids = sorted(
                    str(item) for item in terminal.get("_equivalent_materialization_ids") or path
                )
                equivalent_dependency_ids = sorted(
                    str(item) for item in terminal.get("_equivalent_workflow_dependency_ids") or dependency_path
                )
                terminal_anchor_id = path[0] if path else anchor_id
                terminal_anchor = materialization_by_id.get(terminal_anchor_id) or anchor
                branch_metadata = _branch_metadata(terminal, producer_traversal, target_logical_name)
                if terminal.get("join_branch_selector"):
                    branch_metadata["join_branch_selector"] = terminal.get("join_branch_selector")
                lineage_id = stable_id(
                    "sql_workflow_target_column_lineage", repo_id, workflow_file,
                    target_logical_name, target_column,
                    branch_metadata.get("source_branch_scope_id"),
                    branch_metadata.get("source_branch_ordinal"),
                    terminal.get("terminal_source_kind"),
                    terminal.get("terminal_relation_id"),
                    terminal.get("terminal_relation_name"),
                    terminal.get("terminal_column"),
                    canonical_json(_effective_transformation_key(list(terminal.get("transformations") or []))),
                    terminal.get("recursive_resolution_status"),
                    terminal.get("physical_origin_status"),
                    terminal.get("lineage_status"),
                )
                branch_path = [{
                    "kind": "workflow_target_materialization",
                    "workflow_context_file": workflow_file,
                    "target_logical_name": target_logical_name,
                    "materialization_id": terminal_anchor_id,
                    "materialization_kind": terminal_anchor.get("kind"),
                    "source_file": terminal_anchor.get("source_file"),
                }]
                branch_path.extend(
                    {"kind": "observed_relation_materialization", "materialization_id": item}
                    for item in path
                )
                branch_path.extend(
                    {"kind": "observed_workflow_dependency", "workflow_dependency_id": item}
                    for item in dependency_path
                )
                materialization_lineage_rows.append([
                    lineage_id, repo_id, workflow_file, target_logical_name, terminal_anchor_id,
                    None, str(terminal_anchor.get("source_file") or "") or None, None,
                    target_column, None, None, None,
                    terminal.get("terminal_source_kind") or "column_usage",
                    terminal.get("terminal_column_usage_id"), terminal.get("terminal_column"),
                    terminal.get("terminal_relation_id"), terminal.get("terminal_relation_name"),
                    terminal.get("terminal_relation_kind"), int(terminal.get("recursion_depth") or 0),
                    canonical_json(branch_path), canonical_json(terminal.get("transformations") or []),
                    ("partial" if partial_contract else (terminal.get("recursive_resolution_status") or "partial")),
                    terminal.get("physical_origin_status") or "unresolved",
                    ("partial" if partial_contract else (terminal.get("lineage_status") or "partial")), "derived", mapping_basis,
                    canonical_json({
                        "target_anchor_kind": "observed_relation_materialization",
                        "branch": branch_metadata,
                        "direct_materialization_ids": direct_materialization_ids,
                        "output_contract_basis": [basis for _p, _c, basis in contracts],
                        "equivalent_observed_path_count": equivalent_path_count,
                        "equivalent_column_usage_ids": equivalent_usage_ids,
                        "equivalent_projection_ids": equivalent_projection_ids,
                        "equivalent_materialization_ids": equivalent_materialization_ids,
                        "equivalent_workflow_dependency_ids": equivalent_dependency_ids,
                        "representative_path": {
                            "materialization_path": path,
                            "workflow_dependency_path": dependency_path,
                        },
                        "path_aggregation_basis": "same_terminal_relation_field_plus_effective_transformation_identity",
                        "evidence": [
                            *workflow_binding_evidence.get((workflow_file, target_logical_name), ()),
                            *producer_evidence, *terminal.get("evidence", []),
                        ],
                    }),
                ])
                lineage_path_count += 1

        emit_progress(
            f"workflow-target-lineage target {target_ordinal}/{len(materialization_target_pairs)} completed; "
            f"table={target_logical_name}; duration={__import__('time').monotonic() - target_started:.1f}s; "
            f"new_lineage_paths={lineage_path_count - target_lineage_before}; "
            f"new_gaps={gap_count - target_gap_before}"
        )

    if materialization_lineage_rows:
        row_placeholders = "(" + ", ".join(["?"] * 27) + ")"
        batch_size = 200
        for start in range(0, len(materialization_lineage_rows), batch_size):
            batch = materialization_lineage_rows[start : start + batch_size]
            connection.execute(
                "INSERT OR IGNORE INTO sql_workflow_target_column_lineage VALUES "
                + ", ".join([row_placeholders] * len(batch)),
                [value for row in batch for value in row],
            )

    emit_progress(
        f"workflow-target-lineage materialization-seeded traversal completed; "
        f"duration={__import__('time').monotonic() - materialization_phase_started:.1f}s; "
        f"batch_rows={len(materialization_lineage_rows)}; total_lineage_paths={lineage_path_count}; gaps={gap_count}"
    )

    return {
        "workflow_transform_count": transform_count,
        "target_projection_count": target_column_count,
        "lineage_path_count": lineage_path_count,
        "gap_count": gap_count,
    }
