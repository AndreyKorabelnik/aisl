from __future__ import annotations

"""Bounded on-demand traversal over the canonical direct value-flow graph.

The resolver reads only repository_value_node and repository_value_flow_edge. It never
persists transitive paths and does not depend on execution contexts or legacy technical
path projections.
"""

import json
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

ATTRIBUTE_PATH_SCHEMA_VERSION = "repository_attribute_path/v2"

_CONFIDENCE_RANK = {
    "unknown": 0,
    "probable": 1,
    "confirmed": 2,
}

_KNOWLEDGE_CLASS_RANK = {
    "candidate": 0,
    "derived": 1,
    "confirmed": 2,
}

_KNOWLEDGE_VIEW_RELATION = {
    "strict": "repository_value_flow_edge_strict",
    "working": "repository_value_flow_edge_working",
    "exploratory": "repository_value_flow_edge_exploratory",
}


@dataclass(frozen=True)
class _ResolvedEndpoint:
    status: str
    node: dict[str, Any] | None
    candidates: tuple[dict[str, Any], ...]


def _json_value(value: Any) -> Any:
    if isinstance(value, (dict, list, tuple, int, float, bool)) or value is None:
        return value
    text = str(value)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def _normalise_values(values: Sequence[str] | str | None) -> tuple[str, ...]:
    if values is None:
        return ()
    if isinstance(values, str):
        candidates = values.split(",")
    else:
        candidates = values
    result: list[str] = []
    for value in candidates:
        text = str(value or "").strip()
        if text and text not in result:
            result.append(text)
    return tuple(result)


def _validate_limit(name: str, value: int, *, minimum: int, maximum: int) -> int:
    number = int(value)
    if number < minimum or number > maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return number


def _compact_node(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "value_node_id": str(row.get("value_node_id") or ""),
        "repo_id": str(row.get("repo_id") or ""),
        "occurrence_id": str(row.get("occurrence_id") or ""),
        "node_kind": str(row.get("node_kind") or ""),
        "operation": row.get("operation"),
        "owner_ref": row.get("owner_ref"),
        "display_ref": str(row.get("display_ref") or ""),
        "type_ref": row.get("type_ref"),
        "wire_path": row.get("wire_path"),
        "source_path": row.get("source_path"),
        "provenance": _json_value(row.get("provenance_json")),
    }


def _compact_edge(row: Mapping[str, Any], nodes: Mapping[str, dict[str, Any]]) -> dict[str, Any]:
    source_id = str(row.get("source_value_node_id") or "")
    target_id = str(row.get("target_value_node_id") or "")
    return {
        "value_flow_edge_id": str(row.get("value_flow_edge_id") or ""),
        "source_repo_id": str(row.get("source_repo_id") or ""),
        "target_repo_id": str(row.get("target_repo_id") or ""),
        "source_value_node_id": source_id,
        "target_value_node_id": target_id,
        "flow_kind": str(row.get("flow_kind") or ""),
        "source_edge_kind": str(row.get("source_edge_kind") or ""),
        "transformation_kind": str(row.get("transformation_kind") or "unknown"),
        "naming_relation": str(row.get("naming_relation") or "unknown"),
        "value_preservation": str(row.get("value_preservation") or "unknown"),
        "confidence": str(row.get("confidence") or "unknown"),
        "knowledge_class": str(row.get("knowledge_class") or "candidate"),
        "derivation_id": row.get("derivation_id"),
        "derivation_kind": row.get("derivation_kind"),
        "derivation_source_count": int(row.get("derivation_source_count") or 0),
        "guards": _json_value(row.get("guards_json")),
        "provenance": _json_value(row.get("provenance_json")),
        "source": nodes[source_id],
        "target": nodes[target_id],
    }


def _resolve_endpoint(reference: str | None, nodes: Mapping[str, dict[str, Any]]) -> _ResolvedEndpoint:
    text = str(reference or "").strip()
    if not text:
        return _ResolvedEndpoint("not_supplied", None, ())
    if text in nodes:
        return _ResolvedEndpoint("resolved", nodes[text], ())
    matches = [
        node for node in nodes.values()
        if text in {
            str(node.get("occurrence_id") or ""),
            str(node.get("display_ref") or ""),
            str(node.get("owner_ref") or ""),
        }
    ]
    matches.sort(key=lambda node: (str(node.get("repo_id") or ""), str(node.get("display_ref") or ""), str(node.get("value_node_id") or "")))
    if len(matches) == 1:
        return _ResolvedEndpoint("resolved", matches[0], ())
    if matches:
        return _ResolvedEndpoint("ambiguous", None, tuple(matches))
    return _ResolvedEndpoint("not_found", None, ())


def _path_confidence(steps: Sequence[Mapping[str, Any]]) -> str:
    if not steps:
        return "confirmed"
    rank = min(_CONFIDENCE_RANK.get(str(step.get("confidence") or "unknown"), 0) for step in steps)
    for label, candidate_rank in _CONFIDENCE_RANK.items():
        if candidate_rank == rank:
            return label
    return "unknown"


def _path_knowledge_class(steps: Sequence[Mapping[str, Any]]) -> str:
    if not steps:
        return "confirmed"
    rank = min(_KNOWLEDGE_CLASS_RANK.get(str(step.get("knowledge_class") or "candidate"), 0) for step in steps)
    for label, candidate_rank in _KNOWLEDGE_CLASS_RANK.items():
        if candidate_rank == rank:
            return label
    return "candidate"


def _path_record(
    *,
    status: str,
    node_ids: Sequence[str],
    steps: Sequence[dict[str, Any]],
    nodes: Mapping[str, dict[str, Any]],
    gap: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    path_confidence = _path_confidence(steps)
    path_knowledge_class = _path_knowledge_class(steps)
    supporting_evidence: list[str] = []
    conflicting_evidence: list[str] = []
    limitations: list[str] = []
    candidate_step_count = 0
    derived_step_count = 0
    confirmed_step_count = 0
    probable_step_count = 0
    for step in steps:
        step_confidence = str(step.get("confidence") or "unknown")
        if step_confidence == "probable":
            probable_step_count += 1
        step_class = str(step.get("knowledge_class") or "candidate")
        if step_class == "confirmed":
            confirmed_step_count += 1
        elif step_class == "derived":
            derived_step_count += 1
        else:
            candidate_step_count += 1
        provenance = step.get("provenance")
        packet = provenance.get("evidence_packet") if isinstance(provenance, Mapping) else None
        if not isinstance(packet, Mapping):
            continue
        for target, key in (
            (supporting_evidence, "supporting_evidence"),
            (conflicting_evidence, "conflicting_evidence"),
            (limitations, "limitations"),
        ):
            for value in packet.get(key) or ():
                text = str(value or "").strip()
                if text and text not in target:
                    target.append(text)
    result: dict[str, Any] = {
        "status": status,
        "hop_count": len(steps),
        "confidence": path_confidence,
        "knowledge_class": path_knowledge_class,
        "start": nodes[node_ids[0]],
        "end": nodes[node_ids[-1]],
        "node_ids": list(node_ids),
        "steps": list(steps),
        "evidence_summary": {
            "confirmed_step_count": confirmed_step_count,
            "derived_step_count": derived_step_count,
            "candidate_step_count": candidate_step_count,
            "probable_step_count": probable_step_count,
            "supporting_evidence": supporting_evidence,
            "conflicting_evidence": conflicting_evidence,
            "limitations": limitations,
        },
    }
    if gap:
        result["gap"] = dict(gap)
    return result


def resolve_attribute_paths(
    query: Any,
    source: str,
    *,
    target: str | None = None,
    selected_repo_ids: Sequence[str] | str,
    max_hops: int = 20,
    max_paths: int = 20,
    max_branching: int = 20,
    allowed_edge_kinds: Sequence[str] | str | None = None,
    minimum_confidence: str = "probable",
    knowledge_view: str = "working",
) -> dict[str, Any]:
    """Resolve bounded attribute paths over selected repositories.

    ``source`` and ``target`` accept an exact value_node_id, occurrence_id, display_ref,
    or owner_ref. Non-unique references are returned as ambiguity rather than guessed.
    """

    repo_ids = _normalise_values(selected_repo_ids)
    if not repo_ids:
        raise ValueError("selected_repo_ids must contain at least one repository")
    max_hops = _validate_limit("max_hops", max_hops, minimum=1, maximum=100)
    max_paths = _validate_limit("max_paths", max_paths, minimum=1, maximum=500)
    max_branching = _validate_limit("max_branching", max_branching, minimum=1, maximum=500)
    confidence = str(minimum_confidence or "probable").strip().casefold()
    if confidence not in _CONFIDENCE_RANK:
        raise ValueError("minimum_confidence must be one of: unknown, probable, confirmed")
    knowledge_view = str(knowledge_view or "working").strip().casefold()
    if knowledge_view not in _KNOWLEDGE_VIEW_RELATION:
        raise ValueError("knowledge_view must be one of: strict, working, exploratory")
    edge_relation = _KNOWLEDGE_VIEW_RELATION[knowledge_view]
    allowed = set(_normalise_values(allowed_edge_kinds))

    base = {
        "schema_version": ATTRIBUTE_PATH_SCHEMA_VERSION,
        "kind": "knowledge-layer-attribute-paths",
        "source_ref": source,
        "target_ref": target,
        "selected_repo_ids": list(repo_ids),
        "constraints": {
            "max_hops": max_hops,
            "max_paths": max_paths,
            "max_branching": max_branching,
            "allowed_edge_kinds": sorted(allowed),
            "minimum_confidence": confidence,
            "knowledge_view": knowledge_view,
        },
    }

    if not query._has_relation("repository_value_node") or not query._has_relation(edge_relation):
        return {**base, "status": "unavailable", "paths": [], "gaps": [{"reason": "repository_value_flow_unavailable"}], "stats": {"node_count": 0, "edge_count": 0, "expanded_state_count": 0}}

    placeholders = ",".join("?" for _ in repo_ids)
    with query._connect() as connection:
        node_rows = query._rows(connection.execute(
            f"""SELECT value_node_id, repo_id, occurrence_id, node_kind, operation, owner_ref,
                       display_ref, type_ref, wire_path, source_path, provenance_json
                FROM repository_value_node
                WHERE repo_id IN ({placeholders})
                ORDER BY repo_id, display_ref, value_node_id""",
            list(repo_ids),
        ))
        nodes = {str(row["value_node_id"]): _compact_node(row) for row in node_rows}

        source_resolution = _resolve_endpoint(source, nodes)
        target_resolution = _resolve_endpoint(target, nodes)
        if source_resolution.status != "resolved":
            return {
                **base,
                "status": f"source_{source_resolution.status}",
                "source_candidates": list(source_resolution.candidates),
                "paths": [],
                "gaps": [{"reason": f"source_{source_resolution.status}", "reference": source}],
                "stats": {"node_count": len(nodes), "edge_count": 0, "expanded_state_count": 0},
            }
        if target is not None and target_resolution.status != "resolved":
            return {
                **base,
                "status": f"target_{target_resolution.status}",
                "source": source_resolution.node,
                "target_candidates": list(target_resolution.candidates),
                "paths": [],
                "gaps": [{"reason": f"target_{target_resolution.status}", "reference": target}],
                "stats": {"node_count": len(nodes), "edge_count": 0, "expanded_state_count": 0},
            }

        edge_rows = query._rows(connection.execute(
            f"""SELECT value_flow_edge_id, source_repo_id, target_repo_id,
                       source_value_node_id, target_value_node_id, flow_kind, source_edge_kind,
                       transformation_kind, naming_relation, value_preservation, confidence, knowledge_class,
                       derivation_id, derivation_kind, derivation_source_count, guards_json, provenance_json
                FROM {edge_relation}
                WHERE source_repo_id IN ({placeholders}) AND target_repo_id IN ({placeholders})
                ORDER BY source_repo_id, target_repo_id, source_value_node_id,
                         target_value_node_id, value_flow_edge_id""",
            [*repo_ids, *repo_ids],
        ))

    minimum_rank = _CONFIDENCE_RANK[confidence]
    adjacency: dict[str, list[dict[str, Any]]] = defaultdict(list)
    eligible_edge_count = 0
    for row in edge_rows:
        source_id = str(row.get("source_value_node_id") or "")
        target_id = str(row.get("target_value_node_id") or "")
        if source_id not in nodes or target_id not in nodes:
            continue
        edge_confidence = str(row.get("confidence") or "unknown").casefold()
        if _CONFIDENCE_RANK.get(edge_confidence, 0) < minimum_rank:
            continue
        flow_kind = str(row.get("flow_kind") or "")
        source_edge_kind = str(row.get("source_edge_kind") or "")
        if allowed and flow_kind not in allowed and source_edge_kind not in allowed:
            continue
        edge = _compact_edge(row, nodes)
        adjacency[source_id].append(edge)
        eligible_edge_count += 1
    for items in adjacency.values():
        items.sort(key=lambda edge: (
            str(edge.get("target_repo_id") or ""),
            str(edge.get("flow_kind") or ""),
            str(edge.get("target_value_node_id") or ""),
            str(edge.get("value_flow_edge_id") or ""),
        ))

    source_node = source_resolution.node
    assert source_node is not None
    source_id = str(source_node["value_node_id"])
    target_node = target_resolution.node
    target_id = str(target_node["value_node_id"]) if target_node else None

    if target_id == source_id:
        path = _path_record(status="complete", node_ids=[source_id], steps=[], nodes=nodes)
        return {**base, "status": "confirmed_complete", "source": source_node, "target": target_node, "paths": [path], "gaps": [], "branch_points": [], "stats": {"node_count": len(nodes), "edge_count": eligible_edge_count, "expanded_state_count": 0, "complete_path_count": 1, "partial_path_count": 0, "truncated": False}}

    complete_paths: list[dict[str, Any]] = []
    partial_paths: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    branch_points: list[dict[str, Any]] = []
    stack: list[tuple[str, list[str], list[dict[str, Any]]]] = [(source_id, [source_id], [])]
    expanded = 0
    truncated = False
    expansion_limit = max_paths * max_hops * max_branching

    def add_gap(reason: str, node_id: str, **details: Any) -> dict[str, Any]:
        gap = {"reason": reason, "node": nodes[node_id], **details}
        signature = json.dumps(gap, sort_keys=True, default=str)
        if all(json.dumps(existing, sort_keys=True, default=str) != signature for existing in gaps):
            gaps.append(gap)
        return gap

    while stack and len(complete_paths) + len(partial_paths) < max_paths:
        current, node_ids, steps = stack.pop()
        expanded += 1
        if expanded > expansion_limit:
            truncated = True
            gap = add_gap("expansion_limit_reached", current, expansion_limit=expansion_limit)
            partial_paths.append(_path_record(status="partial", node_ids=node_ids, steps=steps, nodes=nodes, gap=gap))
            break

        if target_id is not None and current == target_id:
            complete_paths.append(_path_record(status="complete", node_ids=node_ids, steps=steps, nodes=nodes))
            continue

        outgoing = adjacency.get(current, [])
        if len(steps) >= max_hops:
            gap = add_gap("max_hops_reached", current, outgoing_edge_count=len(outgoing))
            partial_paths.append(_path_record(status="partial", node_ids=node_ids, steps=steps, nodes=nodes, gap=gap))
            continue
        if not outgoing:
            gap = add_gap("no_observed_outgoing_value_flow", current)
            partial_paths.append(_path_record(status="partial", node_ids=node_ids, steps=steps, nodes=nodes, gap=gap))
            continue

        selected = outgoing[:max_branching]
        if len(outgoing) > 1:
            branch_points.append({
                "node": nodes[current],
                "outgoing_edge_count": len(outgoing),
                "selected_edge_count": len(selected),
                "truncated": len(outgoing) > len(selected),
            })
        if len(outgoing) > len(selected):
            add_gap("branching_limit_reached", current, outgoing_edge_count=len(outgoing), selected_edge_count=len(selected))
            truncated = True

        pushed = 0
        for edge in reversed(selected):
            next_id = str(edge["target_value_node_id"])
            if next_id in node_ids:
                add_gap("cycle_prevented", current, target=nodes[next_id], edge_id=edge["value_flow_edge_id"])
                continue
            stack.append((next_id, [*node_ids, next_id], [*steps, edge]))
            pushed += 1
        if pushed == 0:
            gap = add_gap("no_traversable_outgoing_value_flow", current)
            partial_paths.append(_path_record(status="partial", node_ids=node_ids, steps=steps, nodes=nodes, gap=gap))

    if stack:
        truncated = True
        add_gap("max_paths_reached", stack[-1][0], max_paths=max_paths)

    paths = [*complete_paths, *partial_paths]
    paths.sort(key=lambda path: (0 if path["status"] == "complete" else 1, int(path["hop_count"]), tuple(path["node_ids"])))
    if complete_paths:
        if len(complete_paths) > 1:
            status = "ambiguous"
        else:
            path_confidence = str(complete_paths[0].get("confidence") or "unknown")
            status = f"{path_confidence}_complete"
    elif partial_paths:
        status = "partial"
    else:
        status = "not_found"
        add_gap("no_path_found", source_id, target=target_node)

    return {
        **base,
        "status": status,
        "source": source_node,
        "target": target_node,
        "paths": paths[:max_paths],
        "gaps": gaps,
        "branch_points": branch_points,
        "stats": {
            "node_count": len(nodes),
            "edge_count": eligible_edge_count,
            "expanded_state_count": expanded,
            "complete_path_count": len(complete_paths),
            "partial_path_count": len(partial_paths),
            "truncated": truncated,
        },
    }
