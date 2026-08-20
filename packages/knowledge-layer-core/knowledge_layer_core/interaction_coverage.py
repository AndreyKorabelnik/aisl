from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from .bulk import bulk_insert
from .metrics import canonical_json
from prepared_knowledge_runtime.normalization import stable_id


INTERACTION_COVERAGE_SCHEMA_VERSION = "repository_interaction_coverage/v1"


def _payload(raw: Any) -> dict[str, Any]:
    if isinstance(raw, str):
        value = json.loads(raw)
    else:
        value = raw or {}
    return value if isinstance(value, dict) else {}


def materialize_repository_interaction_coverage(connection: Any, *, scope_id: str) -> dict[str, int]:
    """Publish per-repository topology analysis and outbound matching coverage."""
    connection.execute("DELETE FROM repository_interaction_coverage WHERE scope_id=?", [scope_id])

    node_rows = connection.execute(
        """SELECT repo_id, system_id, project_id, payload_json
           FROM interaction_repository_identity
           WHERE scope_id=?
           ORDER BY repo_id""",
        [scope_id],
    ).fetchall()
    nodes: dict[str, dict[str, Any]] = {}
    for repo_id, system_id, project_id, payload_raw in node_rows:
        identity = _payload(payload_raw)
        nodes[str(repo_id)] = {
            "system_id": system_id or identity.get("system_id"),
            "project_id": project_id or identity.get("project_id"),
            "analysis_status": "completed",
        }

    boundary_counts: dict[str, dict[str, int]] = defaultdict(lambda: {"inbound": 0, "outbound": 0})
    for repo_id, direction, count in connection.execute(
        """SELECT repo_id, direction, count(*)
           FROM repository_interaction_boundary
           WHERE scope_id=?
           GROUP BY repo_id, direction""",
        [scope_id],
    ).fetchall():
        boundary_counts[str(repo_id)][str(direction)] = int(count)

    diagnostic_counts: dict[str, dict[str, int]] = defaultdict(
        lambda: {
            "matched": 0,
            "confirmed": 0,
            "probable": 0,
            "ambiguous": 0,
            "unresolved": 0,
        }
    )
    for repo_id, match_status, confidence, count in connection.execute(
        """SELECT source_repo_id, match_status, confidence, count(*)
           FROM system_interaction_match_diagnostic
           WHERE scope_id=?
           GROUP BY source_repo_id, match_status, confidence""",
        [scope_id],
    ).fetchall():
        stats = diagnostic_counts[str(repo_id)]
        status = str(match_status or "unresolved")
        stats[status] = stats.get(status, 0) + int(count)
        if status == "matched" and confidence in {"confirmed", "probable"}:
            stats[str(confidence)] += int(count)

    rows: list[tuple[Any, ...]] = []
    for repo_id in sorted(nodes):
        node = nodes[repo_id]
        boundaries = boundary_counts[repo_id]
        diagnostics = diagnostic_counts[repo_id]
        outbound_count = int(boundaries["outbound"])
        matched_count = int(diagnostics["matched"])
        ambiguous_count = int(diagnostics["ambiguous"])
        unresolved_count = int(diagnostics["unresolved"])
        if outbound_count == 0:
            matching_status = "not_applicable"
        elif matched_count == outbound_count and ambiguous_count == 0 and unresolved_count == 0:
            matching_status = "complete"
        else:
            matching_status = "partial"
        coverage_status = (
            "complete"
            if node["analysis_status"] == "completed" and matching_status in {"complete", "not_applicable"}
            else "partial"
        )
        coverage_id = stable_id("repository_interaction_coverage", scope_id, repo_id)
        payload = {
            "schema_version": INTERACTION_COVERAGE_SCHEMA_VERSION,
            "coverage_id": coverage_id,
            "scope_id": scope_id,
            "repo_id": repo_id,
            "system_id": node["system_id"],
            "project_id": node["project_id"],
            "analysis_status": node["analysis_status"],
            "boundary_counts": dict(boundaries),
            "outbound_match_counts": dict(diagnostics),
            "matching_coverage_status": matching_status,
            "coverage_status": coverage_status,
        }
        rows.append(
            (
                coverage_id,
                scope_id,
                repo_id,
                node["system_id"],
                node["project_id"],
                node["analysis_status"],
                int(boundaries["inbound"]),
                outbound_count,
                matched_count,
                int(diagnostics["confirmed"]),
                int(diagnostics["probable"]),
                ambiguous_count,
                unresolved_count,
                matching_status,
                coverage_status,
                canonical_json(payload),
            )
        )

    bulk_insert(connection, "INSERT INTO repository_interaction_coverage VALUES", rows)
    return {"repository_interaction_coverage": len(rows)}
