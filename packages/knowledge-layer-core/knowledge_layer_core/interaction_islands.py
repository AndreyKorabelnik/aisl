from __future__ import annotations

import json
from collections import defaultdict, deque
from typing import Any, Iterable

from .bulk import bulk_insert
from .metrics import canonical_json
from prepared_knowledge_runtime.normalization import stable_id


INTERACTION_ISLAND_SCHEMA_VERSION = "repository_interaction_island/v2"


def _allowed_confidences(mode: str) -> frozenset[str]:
    if mode == "strict":
        return frozenset({"confirmed"})
    if mode == "extended":
        return frozenset({"confirmed", "probable"})
    raise ValueError(f"unsupported island mode: {mode!r}")


def _components(nodes: Iterable[str], undirected: dict[str, set[str]]) -> list[tuple[str, ...]]:
    remaining = set(nodes)
    components: list[tuple[str, ...]] = []
    while remaining:
        root = min(remaining)
        queue = deque([root])
        component: set[str] = set()
        while queue:
            node = queue.popleft()
            if node in component:
                continue
            component.add(node)
            remaining.discard(node)
            for neighbour in sorted(undirected.get(node, ())):
                if neighbour not in component:
                    queue.append(neighbour)
        components.append(tuple(sorted(component)))
    return sorted(components, key=lambda values: (values[0], len(values), values))


def _matching_status(values: Iterable[str]) -> str:
    statuses = set(values)
    if "partial" in statuses:
        return "partial"
    if "complete" in statuses:
        return "complete"
    return "not_applicable"


def materialize_repository_interaction_islands(connection: Any, *, scope_id: str) -> dict[str, int]:
    """Materialize strict and extended weakly connected repository components."""
    connection.execute("DELETE FROM repository_interaction_island_member WHERE scope_id=?", [scope_id])
    connection.execute("DELETE FROM repository_interaction_island WHERE scope_id=?", [scope_id])

    coverage_rows = connection.execute(
        """SELECT repo_id, system_id, project_id, analysis_status,
                  inbound_boundary_count, outbound_boundary_count,
                  matched_outbound_count, confirmed_outbound_count,
                  probable_outbound_count, ambiguous_outbound_count,
                  unresolved_outbound_count, matching_coverage_status,
                  coverage_status
           FROM repository_interaction_coverage
           WHERE scope_id=?
           ORDER BY repo_id""",
        [scope_id],
    ).fetchall()
    nodes: dict[str, dict[str, Any]] = {}
    for row in coverage_rows:
        repo = str(row[0])
        nodes[repo] = {
            "repo_id": repo,
            "system_id": row[1],
            "project_id": row[2],
            "analysis_status": str(row[3]),
            "inbound_boundary_count": int(row[4]),
            "outbound_boundary_count": int(row[5]),
            "matched_outbound_count": int(row[6]),
            "confirmed_outbound_count": int(row[7]),
            "probable_outbound_count": int(row[8]),
            "ambiguous_outbound_count": int(row[9]),
            "unresolved_outbound_count": int(row[10]),
            "matching_coverage_status": str(row[11]),
            "coverage_status": str(row[12]),
        }

    edge_rows = connection.execute(
        """SELECT interaction_id, source_repo_id, target_repo_id, protocol,
                  operation_count, confidence
           FROM system_interaction
           WHERE scope_id=? AND match_status='matched'
           ORDER BY interaction_id""",
        [scope_id],
    ).fetchall()

    island_rows: list[tuple[Any, ...]] = []
    member_rows: list[tuple[Any, ...]] = []
    for mode in ("strict", "extended"):
        allowed = _allowed_confidences(mode)
        selected_edges = [row for row in edge_rows if str(row[5]) in allowed]
        undirected: dict[str, set[str]] = defaultdict(set)
        inbound_degree: dict[str, int] = defaultdict(int)
        outbound_degree: dict[str, int] = defaultdict(int)
        for _edge_id, source_repo_id, target_repo_id, _protocol, _operation_count, _confidence in selected_edges:
            source = str(source_repo_id)
            target = str(target_repo_id)
            if source not in nodes or target not in nodes:
                continue
            undirected[source].add(target)
            undirected[target].add(source)
            outbound_degree[source] += 1
            inbound_degree[target] += 1

        for members in _components(nodes, undirected):
            member_set = set(members)
            component_edges = [
                row
                for row in selected_edges
                if str(row[1]) in member_set and str(row[2]) in member_set
            ]
            protocols = sorted({str(row[3]) for row in component_edges})
            confirmed_count = sum(1 for row in component_edges if str(row[5]) == "confirmed")
            probable_count = sum(1 for row in component_edges if str(row[5]) == "probable")
            project_ids = {
                str(nodes[repo].get("project_id"))
                for repo in members
                if nodes[repo].get("project_id") is not None
            }
            completed_node_count = sum(1 for repo in members if nodes[repo]["analysis_status"] == "completed")
            incomplete_node_count = len(members) - completed_node_count
            analysis_coverage_status = "complete" if incomplete_node_count == 0 else "partial"
            matching_coverage_status = _matching_status(
                nodes[repo]["matching_coverage_status"] for repo in members
            )
            coverage_status = (
                "complete"
                if analysis_coverage_status == "complete" and matching_coverage_status in {"complete", "not_applicable"}
                else "partial"
            )
            aggregate_keys = (
                "inbound_boundary_count",
                "outbound_boundary_count",
                "matched_outbound_count",
                "confirmed_outbound_count",
                "probable_outbound_count",
                "ambiguous_outbound_count",
                "unresolved_outbound_count",
            )
            aggregate = {
                key: sum(int(nodes[repo][key]) for repo in members)
                for key in aggregate_keys
            }
            island_id = stable_id("repository_interaction_island", scope_id, mode, *members)
            island_payload = {
                "schema_version": INTERACTION_ISLAND_SCHEMA_VERSION,
                "island_id": island_id,
                "scope_id": scope_id,
                "mode": mode,
                "members": list(members),
                "edge_ids": [str(row[0]) for row in component_edges],
                "protocols": protocols,
                "completed_node_count": completed_node_count,
                "incomplete_node_count": incomplete_node_count,
                "boundary_counts": {
                    "inbound": aggregate["inbound_boundary_count"],
                    "outbound": aggregate["outbound_boundary_count"],
                },
                "outbound_match_counts": {
                    "matched": aggregate["matched_outbound_count"],
                    "confirmed": aggregate["confirmed_outbound_count"],
                    "probable": aggregate["probable_outbound_count"],
                    "ambiguous": aggregate["ambiguous_outbound_count"],
                    "unresolved": aggregate["unresolved_outbound_count"],
                },
                "analysis_coverage_status": analysis_coverage_status,
                "matching_coverage_status": matching_coverage_status,
                "coverage_status": coverage_status,
            }
            island_rows.append(
                (
                    island_id,
                    scope_id,
                    mode,
                    len(members),
                    len(component_edges),
                    len(project_ids),
                    canonical_json(protocols),
                    confirmed_count,
                    probable_count,
                    completed_node_count,
                    incomplete_node_count,
                    aggregate["inbound_boundary_count"],
                    aggregate["outbound_boundary_count"],
                    aggregate["matched_outbound_count"],
                    aggregate["confirmed_outbound_count"],
                    aggregate["probable_outbound_count"],
                    aggregate["ambiguous_outbound_count"],
                    aggregate["unresolved_outbound_count"],
                    analysis_coverage_status,
                    matching_coverage_status,
                    coverage_status,
                    canonical_json(island_payload),
                )
            )
            for repo in members:
                inbound = inbound_degree.get(repo, 0)
                outbound = outbound_degree.get(repo, 0)
                member_id = stable_id("repository_interaction_island_member", island_id, repo)
                member_payload = {
                    "schema_version": INTERACTION_ISLAND_SCHEMA_VERSION,
                    "island_id": island_id,
                    "mode": mode,
                    "node_id": repo,
                    "repo_id": repo,
                    "system_id": nodes[repo].get("system_id"),
                    "project_id": nodes[repo].get("project_id"),
                    "inbound_degree": inbound,
                    "outbound_degree": outbound,
                    "total_degree": inbound + outbound,
                    "analysis_status": nodes[repo]["analysis_status"],
                    "coverage_status": nodes[repo]["coverage_status"],
                    "matching_coverage_status": nodes[repo]["matching_coverage_status"],
                    "isolated": not component_edges,
                }
                member_rows.append(
                    (
                        member_id,
                        island_id,
                        scope_id,
                        mode,
                        repo,
                        repo,
                        nodes[repo].get("system_id"),
                        nodes[repo].get("project_id"),
                        inbound,
                        outbound,
                        inbound + outbound,
                        nodes[repo]["analysis_status"],
                        canonical_json(member_payload),
                    )
                )

    bulk_insert(connection, "INSERT INTO repository_interaction_island VALUES", island_rows)
    bulk_insert(connection, "INSERT INTO repository_interaction_island_member VALUES", member_rows)
    return {
        "repository_interaction_island": len(island_rows),
        "repository_interaction_island_member": len(member_rows),
    }
