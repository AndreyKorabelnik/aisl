from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Iterable

def aggregate_system_inventory(
    system: dict[str, Any], repository_records: list[dict[str, Any]]
) -> dict[str, Any]:
    technologies: dict[tuple[str, str], dict[str, Any]] = {}
    protocols = Counter()
    source_kinds = Counter()
    inbound_count = 0
    outbound_count = 0
    unresolved_peer_count = 0
    sql_files = 0
    file_count = 0
    discovery_candidate_count = 0
    unknown_primitive_count = 0
    coverage_gap_count = 0
    outside_frontier_count = 0
    diagnostics_count = 0
    source_occurrence_count = 0
    source_occurrence_link_count = 0
    evaluation_phases = Counter()
    repositories: list[dict[str, Any]] = []
    interfaces: list[dict[str, Any]] = []
    discovery_candidates: list[dict[str, Any]] = []
    coverage_gaps: list[dict[str, Any]] = []

    for record in repository_records:
        snapshot = record["snapshot"]
        identity = dict(snapshot.get("identity") or {})
        repo_id = str(identity.get("repo_id") or record.get("repo_id") or "")
        source_kind = str(identity.get("source_kind") or "")
        if source_kind:
            source_kinds[source_kind] += 1
        evaluation_phase = str(snapshot.get("evaluation_phase") or "")
        if evaluation_phase:
            evaluation_phases[evaluation_phase] += 1
        repositories.append({
            "repo_id": repo_id,
            "repository_id": identity.get("repository_id"),
            "repository_name": identity.get("repository_name"),
            "source_kind": identity.get("source_kind"),
            "repository_url": identity.get("repository_url"),
            "default_branch": identity.get("default_branch"),
            "evaluation_phase": evaluation_phase or None,
            "revision_id": record.get("revision_id"),
            "revision_ordinal": record.get("revision_ordinal"),
            "revision_state": record.get("revision_state"),
            "revision_created_at": (record.get("revision_created_at").isoformat() if hasattr(record.get("revision_created_at"), "isoformat") else record.get("revision_created_at")),
        })
        extensions = dict(snapshot.get("extensions") or {})
        sql_files += int(extensions.get(".sql") or 0)
        counts = dict(snapshot.get("counts") or {})
        file_count += int(counts.get("files") or 0)
        discovery_candidate_count += int(counts.get("discovery_candidates") or 0)
        unknown_primitive_count += int(counts.get("unknown_primitives") or 0)
        coverage_gap_count += int(counts.get("coverage_gaps") or 0)
        outside_frontier_count += int(counts.get("outside_analyzer_frontier_files") or 0)
        diagnostics_count += int(counts.get("diagnostics") or 0)
        source_occurrence_count += int(counts.get("source_occurrences") or 0)
        source_occurrence_link_count += int(counts.get("source_occurrence_links") or 0)

        for item in snapshot.get("discovery_candidates") or ():
            row = dict(item)
            row.update({"repo_id": repo_id, "revision_id": record.get("revision_id")})
            discovery_candidates.append(row)

        for item in snapshot.get("coverage_gaps") or ():
            row = dict(item)
            row.update({"repo_id": repo_id, "revision_id": record.get("revision_id")})
            coverage_gaps.append(row)

        for item in snapshot.get("technologies") or ():
            row = dict(item)
            key = (str(row.get("category") or ""), str(row.get("technology") or ""))
            if key not in technologies:
                technologies[key] = {
                    "category": key[0], "technology": key[1],
                    "repository_ids": [], "status": row.get("status"), "confidence": row.get("confidence"),
                }
            technologies[key]["repository_ids"].append(repo_id)

        for item in snapshot.get("interfaces") or ():
            row = dict(item)
            row.update({"repo_id": repo_id, "revision_id": record.get("revision_id")})
            direction = str(row.get("direction") or "")
            if direction == "inbound": inbound_count += 1
            if direction == "outbound": outbound_count += 1
            protocol = str(row.get("protocol") or "")
            if protocol: protocols[protocol] += 1
            if str(row.get("peer_resolution_status") or "") != "resolved": unresolved_peer_count += 1
            interfaces.append(row)

    repositories.sort(key=lambda row: (str(row.get("repo_id") or ""), str(row.get("revision_id") or "")))
    technology_items = sorted(technologies.values(), key=lambda row: (row["category"], row["technology"]))
    for row in technology_items:
        row["repository_ids"] = sorted(set(row["repository_ids"]))
    discovery_candidates.sort(key=lambda row: (str(row.get("discovery_kind") or ""), -float(row.get("structural_salience_score") or 0.0), str(row.get("repo_id") or ""), str(row.get("candidate_id") or "")))
    coverage_gaps.sort(key=lambda row: (str(row.get("gap_kind") or ""), str(row.get("repo_id") or ""), str(row.get("gap_occurrence_id") or "")))

    return {
        "system_id": system["system_id"],
        "display_name": system["display_name"],
        "description": system.get("description"),
        "active_revision_id": system.get("active_revision_id"),
        "repository_membership_basis": "latest_published_repository_inventory_per_repo_id",
        "repositories": repositories,
        "repository_count": len(repositories),
        "repository_urls": sorted({str(row["repository_url"]) for row in repositories if row.get("repository_url")}),
        "source_kinds": dict(sorted(source_kinds.items())),
        "technologies": technology_items,
        "counts": {
            "files": file_count,
            "sql_files": sql_files,
            "inbound_interfaces": inbound_count,
            "outbound_interfaces": outbound_count,
            "unresolved_peers": unresolved_peer_count,
            "discovery_candidates": discovery_candidate_count,
            "unknown_primitives": unknown_primitive_count,
            "coverage_gaps": coverage_gap_count,
            "outside_analyzer_frontier_files": outside_frontier_count,
            "diagnostics": diagnostics_count,
            "source_occurrences": source_occurrence_count,
            "source_occurrence_links": source_occurrence_link_count,
            "preflight_repositories": int(evaluation_phases.get("preflight", 0)),
            "post_analysis_repositories": int(evaluation_phases.get("post_analysis", 0)),
        },
        "protocols": dict(sorted(protocols.items())),
        "discovery_candidates": discovery_candidates,
        "coverage_gaps": coverage_gaps,
        "interfaces": interfaces,
    }


def matches_portfolio_filters(
    item: dict[str, Any], *, search: str | None = None, technology: str | None = None,
    protocol: str | None = None, has_sql: bool | None = None,
    has_unresolved_peers: bool | None = None, source_kind: str | None = None,
) -> bool:
    if search:
        token = search.casefold()
        haystack = " ".join([
            str(item.get("system_id") or ""), str(item.get("display_name") or ""),
            str(item.get("description") or ""), " ".join(item.get("repository_urls") or ()),
            " ".join(str(row.get("repository_name") or "") for row in item.get("repositories") or ()),
        ]).casefold()
        if token not in haystack:
            return False
    if technology:
        needle = technology.casefold()
        if not any(needle in str(row.get("technology") or "").casefold() for row in item.get("technologies") or ()):
            return False
    if protocol and protocol not in (item.get("protocols") or {}):
        return False
    if has_sql is not None and (int((item.get("counts") or {}).get("sql_files") or 0) > 0) != has_sql:
        return False
    if has_unresolved_peers is not None and (int((item.get("counts") or {}).get("unresolved_peers") or 0) > 0) != has_unresolved_peers:
        return False
    if source_kind and source_kind not in (item.get("source_kinds") or {}):
        return False
    return True


def build_facets(items: list[dict[str, Any]]) -> dict[str, Any]:
    technologies = Counter()
    protocols = Counter()
    source_kinds = Counter()
    for item in items:
        for row in item.get("technologies") or ():
            technologies[f"{row.get('category') or ''}:{row.get('technology') or ''}"] += 1
        for protocol in (item.get("protocols") or {}):
            protocols[str(protocol)] += 1
        for source_kind in (item.get("source_kinds") or {}):
            source_kinds[str(source_kind)] += 1
    return {
        "technologies": dict(sorted(technologies.items())),
        "protocols": dict(sorted(protocols.items())),
        "source_kinds": dict(sorted(source_kinds.items())),
    }


def build_interaction_graph(items: list[dict[str, Any]]) -> dict[str, Any]:
    system_ids = {str(item.get("system_id") or "") for item in items}
    observations: list[dict[str, Any]] = []
    for item in items:
        system_id = str(item.get("system_id") or "")
        for interface in item.get("interfaces") or ():
            direction = str(interface.get("direction") or "")
            peer = interface.get("peer_system")
            if direction == "outbound":
                source_system, target_system = system_id, peer
            elif direction == "inbound":
                source_system, target_system = peer, system_id
            else:
                source_system, target_system = None, None
            observations.append({
                "observation_id": f"{system_id}:{interface.get('repo_id') or ''}:{interface.get('interface_id') or ''}",
                "observed_in_system_id": system_id,
                "repo_id": interface.get("repo_id"),
                "revision_id": interface.get("revision_id"),
                "direction": direction,
                "source_system": source_system,
                "target_system": target_system,
                "peer_system": peer,
                "peer_resolution_status": interface.get("peer_resolution_status"),
                "target_in_portfolio": bool(target_system and str(target_system) in system_ids),
                "source_in_portfolio": bool(source_system and str(source_system) in system_ids),
                "protocol": interface.get("protocol"),
                "boundary_kind": interface.get("boundary_kind"),
                "operation": interface.get("operation"),
                "endpoint_or_topic": interface.get("endpoint_or_topic"),
                "http_method": interface.get("http_method"),
                "evidence_status": interface.get("evidence_status"),
                "source_artifact_id": interface.get("source_artifact_id"),
            })
    observations.sort(key=lambda row: (str(row.get("observed_in_system_id") or ""), str(row.get("repo_id") or ""), str(row.get("observation_id") or "")))
    return {
        "nodes": [{"system_id": item["system_id"], "display_name": item["display_name"], "repository_count": item["repository_count"]} for item in sorted(items, key=lambda row: row["system_id"])],
        "observations": observations,
        "resolved_observation_count": sum(1 for row in observations if row.get("peer_resolution_status") == "resolved"),
        "unresolved_observation_count": sum(1 for row in observations if row.get("peer_resolution_status") != "resolved"),
    }
