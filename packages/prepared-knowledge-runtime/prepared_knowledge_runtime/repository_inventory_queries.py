from __future__ import annotations

from typing import Any


class RepositoryInventoryUnavailableError(RuntimeError):
    pass


def _require(query) -> None:
    required = {
        "repository_inventory_build",
        "repository_inventory_source",
        "repository_inventory_identity",
        "repository_inventory_file",
        "repository_inventory_extension",
        "repository_inventory_technology",
        "repository_inventory_interface",
        "repository_inventory_structural_family",
        "repository_inventory_candidate",
        "repository_inventory_completeness",
        "repository_inventory_coverage_gap",
        "repository_inventory_source_occurrence",
        "repository_inventory_object_occurrence",
        "repository_inventory_diagnostic",
    }
    missing = sorted(required - set(query.relation_names()))
    if missing:
        raise RepositoryInventoryUnavailableError(
            f"repository inventory is unavailable; missing relations: {missing}"
        )


def repository_inventory_summary(query) -> dict[str, Any]:
    _require(query)
    with query._connect() as con:
        identity_rows = query._rows(con.execute(
            "SELECT scope_id, repo_id, repository_id, repository_name, source_kind, repository_url, default_branch, source_metadata_json "
            "FROM repository_inventory_identity ORDER BY repo_id LIMIT 1"
        ))
        identity = identity_rows[0] if identity_rows else {}
        build_rows = query._rows(con.execute(
            "SELECT schema_version, evaluation_phase, evaluation_basis_json, build_status FROM repository_inventory_build ORDER BY started_at DESC LIMIT 1"
        ))
        build = build_rows[0] if build_rows else {}
        file_count = int(con.execute("SELECT count(*) FROM repository_inventory_file").fetchone()[0])
        extension_count = int(con.execute("SELECT count(*) FROM repository_inventory_extension").fetchone()[0])
        technology_count = int(con.execute("SELECT count(*) FROM repository_inventory_technology").fetchone()[0])
        interface_rows = con.execute("SELECT direction, count(*) FROM repository_inventory_interface GROUP BY direction ORDER BY direction").fetchall()
        interface_counts = {str(direction): int(count) for direction, count in interface_rows}
        discovery_rows = con.execute("SELECT discovery_kind, count(*) FROM repository_inventory_candidate GROUP BY discovery_kind ORDER BY discovery_kind").fetchall()
        discovery_counts = {str(kind): int(count) for kind, count in discovery_rows}
        outside_frontier_count = int(con.execute("SELECT count(*) FROM repository_inventory_file WHERE analyzer_frontier_status='outside_analyzer_frontier'").fetchone()[0])
        diagnostic_count = int(con.execute("SELECT count(*) FROM repository_inventory_diagnostic").fetchone()[0])
        gap_count = int(con.execute("SELECT count(*) FROM repository_inventory_coverage_gap").fetchone()[0])
        source_occurrence_count = int(con.execute("SELECT count(*) FROM repository_inventory_source_occurrence").fetchone()[0])
        source_occurrence_link_count = int(con.execute("SELECT count(*) FROM repository_inventory_object_occurrence").fetchone()[0])
        structural_family_count = int(con.execute("SELECT count(*) FROM repository_inventory_structural_family").fetchone()[0])
        source_rows = query._rows(con.execute(
            "SELECT artifact_kind, schema_version, coverage_json, diagnostics_json FROM repository_inventory_source ORDER BY artifact_kind, schema_version"
        ))
    return {
        "schema_version": "repository-inventory-query/v5",
        "inventory_schema_version": build.get("schema_version"),
        "evaluation_phase": build.get("evaluation_phase"),
        "evaluation_basis": build.get("evaluation_basis_json") or {},
        "identity": identity,
        "counts": {
            "files": file_count, "extension_families": extension_count, "technologies": technology_count,
            "inbound_interfaces": interface_counts.get("inbound", 0), "outbound_interfaces": interface_counts.get("outbound", 0),
            "structural_families": structural_family_count,
            "discovery_candidates": sum(discovery_counts.values()), "unknown_primitives": discovery_counts.get("unknown_primitive", 0),
            "coverage_gaps": gap_count, "source_occurrences": source_occurrence_count, "source_occurrence_links": source_occurrence_link_count,
            "outside_analyzer_frontier_files": outside_frontier_count, "diagnostics": diagnostic_count,
        },
        "discovery_counts": discovery_counts, "source_evidence": source_rows,
    }



def repository_inventory_coverage(query) -> dict[str, Any]:
    _require(query)
    with query._connect() as con:
        phase_row = con.execute("SELECT evaluation_phase FROM repository_inventory_build ORDER BY started_at DESC LIMIT 1").fetchone()
        frontier_rows = con.execute("SELECT analyzer_frontier_status, count(*) FROM repository_inventory_file GROUP BY analyzer_frontier_status ORDER BY analyzer_frontier_status").fetchall()
        completeness = query._rows(con.execute(
            "SELECT subject_kind, subject_id, status, evidence_evaluation_status, basis_json, diagnostics_json FROM repository_inventory_completeness ORDER BY subject_kind, subject_id"
        ))
        gap_kind_rows = con.execute("SELECT gap_kind, count(*) FROM repository_inventory_coverage_gap GROUP BY gap_kind ORDER BY gap_kind").fetchall()
        discovery_gap_rows = con.execute("SELECT discovery_kind, count(*) FROM repository_inventory_coverage_gap GROUP BY discovery_kind ORDER BY discovery_kind").fetchall()
        source_rows = query._rows(con.execute(
            "SELECT artifact_kind, schema_version, coverage_json, diagnostics_json FROM repository_inventory_source ORDER BY artifact_kind, schema_version"
        ))
    return {
        "schema_version": "repository-inventory-coverage-query/v5",
        "evaluation_phase": str(phase_row[0]) if phase_row else None,
        "analyzer_frontier": {str(status): int(count) for status, count in frontier_rows},
        "completeness": completeness,
        "gap_counts": {str(kind): int(count) for kind, count in gap_kind_rows},
        "discovery_gap_counts": {str(kind): int(count) for kind, count in discovery_gap_rows},
        "source_evidence": source_rows,
    }


def list_repository_inventory_technologies(query, *, category: str | None = None, token: str = "", max_results: int = 100, page_token: str = "") -> dict[str, Any]:
    _require(query)
    clauses = ["1=1"]
    args: list[Any] = []
    if category:
        clauses.append("category=?")
        args.append(category)
    if token:
        clauses.append("lower(category || ' ' || technology || ' ' || status || ' ' || confidence) LIKE ?")
        args.append(f"%{token.casefold()}%")
    where = " AND ".join(clauses)
    filters = {"category": category, "token": token}
    return query._paged_select(
        kind="repository-inventory-technologies", query_id="repository_inventory_technologies",
        select_sql=f"SELECT technology_id, scope_id, repo_id, category, technology, status, confidence, basis_json FROM repository_inventory_technology WHERE {where} ORDER BY category, technology, technology_id",
        count_sql=f"SELECT count(*) FROM repository_inventory_technology WHERE {where}",
        args=args, filters=filters, max_results=max_results, page_token=page_token,
    )


def list_repository_inventory_interfaces(query, *, direction: str | None = None, protocol: str | None = None, peer_resolution_status: str | None = None, token: str = "", max_results: int = 100, page_token: str = "") -> dict[str, Any]:
    _require(query)
    clauses = ["1=1"]
    args: list[Any] = []
    if direction:
        clauses.append("direction=?")
        args.append(direction)
    if protocol:
        clauses.append("protocol=?")
        args.append(protocol)
    if peer_resolution_status:
        clauses.append("peer_resolution_status=?")
        args.append(peer_resolution_status)
    if token:
        clauses.append("lower(coalesce(operation,'') || ' ' || coalesce(endpoint_or_topic,'') || ' ' || coalesce(peer_system,'') || ' ' || coalesce(protocol,'')) LIKE ?")
        args.append(f"%{token.casefold()}%")
    where = " AND ".join(clauses)
    filters = {"direction": direction, "protocol": protocol, "peer_resolution_status": peer_resolution_status, "token": token}
    return query._paged_select(
        kind="repository-inventory-interfaces", query_id="repository_inventory_interfaces",
        select_sql=f"SELECT interface_id, scope_id, repo_id, direction, boundary_kind, protocol, operation, endpoint_or_topic, http_method, peer_system, peer_resolution_status, evidence_status, source_artifact_id, basis_json FROM repository_inventory_interface WHERE {where} ORDER BY direction, protocol, endpoint_or_topic, operation, interface_id",
        count_sql=f"SELECT count(*) FROM repository_inventory_interface WHERE {where}",
        args=args, filters=filters, max_results=max_results, page_token=page_token,
    )


def list_repository_inventory_structural_families(query, *, family_kind: str | None = None, discovery_kind: str | None = None, token: str = "", max_results: int = 100, page_token: str = "") -> dict[str, Any]:
    _require(query)
    clauses = ["1=1"]
    args: list[Any] = []
    if family_kind:
        clauses.append("family_kind=?")
        args.append(family_kind)
    if discovery_kind:
        clauses.append("discovery_kind=?")
        args.append(discovery_kind)
    if token:
        clauses.append("lower(family_kind || ' ' || family_label || ' ' || discovery_kind) LIKE ?")
        args.append(f"%{token.casefold()}%")
    where = " AND ".join(clauses)
    filters = {"family_kind": family_kind, "discovery_kind": discovery_kind, "token": token}
    return query._paged_select(
        kind="repository-inventory-structural-families", query_id="repository_inventory_structural_families",
        select_sql=f"SELECT family_id, scope_id, repo_id, family_kind, family_label, source_artifact_kind, source_schema_version, occurrence_count, structural_salience_score, discovery_kind, discovery_basis_json, observed_metrics_json, evidence_refs_json FROM repository_inventory_structural_family WHERE {where} ORDER BY structural_salience_score DESC, family_kind, family_label, family_id",
        count_sql=f"SELECT count(*) FROM repository_inventory_structural_family WHERE {where}",
        args=args, filters=filters, max_results=max_results, page_token=page_token,
    )


def list_repository_inventory_discovery(query, *, discovery_kind: str | None = None, min_salience_score: float = 0.0, max_results: int = 100, page_token: str = "") -> dict[str, Any]:
    _require(query)
    clauses = ["structural_salience_score>=?"]
    args: list[Any] = [float(min_salience_score)]
    if discovery_kind:
        clauses.append("discovery_kind=?")
        args.append(discovery_kind)
    where = " AND ".join(clauses)
    filters = {"discovery_kind": discovery_kind, "min_salience_score": float(min_salience_score)}
    return query._paged_select(
        kind="repository-inventory-discovery", query_id="repository_inventory_discovery",
        select_sql=f"SELECT candidate_id, scope_id, repo_id, family_id, family_kind, structural_salience_score, discovery_kind, basis_json FROM repository_inventory_candidate WHERE {where} ORDER BY structural_salience_score DESC, discovery_kind, family_kind, family_id, candidate_id",
        count_sql=f"SELECT count(*) FROM repository_inventory_candidate WHERE {where}",
        args=args, filters=filters, max_results=max_results, page_token=page_token,
    )


def list_repository_inventory_coverage_gaps(query, *, gap_kind: str | None = None, discovery_kind: str | None = None, relevance_status: str | None = None, max_results: int = 100, page_token: str = "") -> dict[str, Any]:
    _require(query)
    clauses = ["1=1"]
    args: list[Any] = []
    if gap_kind:
        clauses.append("gap_kind=?"); args.append(gap_kind)
    if discovery_kind:
        clauses.append("discovery_kind=?"); args.append(discovery_kind)
    if relevance_status:
        clauses.append("relevance_status=?"); args.append(relevance_status)
    where = " AND ".join(clauses)
    filters = {"gap_kind": gap_kind, "discovery_kind": discovery_kind, "relevance_status": relevance_status}
    return query._paged_select(
        kind="repository-inventory-coverage-gaps", query_id="repository_inventory_coverage_gaps",
        select_sql=f"SELECT gap_occurrence_id, scope_id, repo_id, gap_kind, subject_kind, subject_id, discovery_kind, coverage_status, relevance_status, family_id, source_artifact_id, localization_scope_kind, localization_status, evidence_refs_json, diagnostics_json, basis_json FROM repository_inventory_coverage_gap WHERE {where} ORDER BY gap_kind, discovery_kind, subject_kind, subject_id, gap_occurrence_id",
        count_sql=f"SELECT count(*) FROM repository_inventory_coverage_gap WHERE {where}",
        args=args, filters=filters, max_results=max_results, page_token=page_token,
    )



def list_repository_inventory_source_occurrences(
    query, *, object_kind: str | None = None, object_id: str | None = None,
    repository_relative_path: str | None = None, localization_kind: str | None = None,
    max_results: int = 100, page_token: str = "",
) -> dict[str, Any]:
    _require(query)
    clauses = ["1=1"]
    args: list[Any] = []
    if repository_relative_path:
        clauses.append("o.repository_relative_path=?"); args.append(repository_relative_path)
    if localization_kind:
        clauses.append("o.localization_kind=?"); args.append(localization_kind)
    if object_kind:
        clauses.append("EXISTS (SELECT 1 FROM repository_inventory_object_occurrence l WHERE l.occurrence_id=o.occurrence_id AND l.object_kind=?)")
        args.append(object_kind)
    if object_id:
        clauses.append("EXISTS (SELECT 1 FROM repository_inventory_object_occurrence l WHERE l.occurrence_id=o.occurrence_id AND l.object_id=?)")
        args.append(object_id)
    where = " AND ".join(clauses)
    filters = {
        "object_kind": object_kind, "object_id": object_id,
        "repository_relative_path": repository_relative_path, "localization_kind": localization_kind,
    }
    return query._paged_select(
        kind="repository-inventory-source-occurrences", query_id="repository_inventory_source_occurrences",
        select_sql=f"SELECT o.occurrence_id, o.scope_id, o.repo_id, o.repository_relative_path, o.localization_kind, o.line_start, o.line_end, o.content_sha256, o.provenance_json FROM repository_inventory_source_occurrence o WHERE {where} ORDER BY o.repository_relative_path, coalesce(o.line_start,0), coalesce(o.line_end,0), o.occurrence_id",
        count_sql=f"SELECT count(*) FROM repository_inventory_source_occurrence o WHERE {where}",
        args=args, filters=filters, max_results=max_results, page_token=page_token,
    )


def get_repository_inventory_source_occurrence(query, occurrence_id: str) -> dict[str, Any] | None:
    _require(query)
    with query._connect() as con:
        rows = query._rows(con.execute(
            "SELECT occurrence_id, scope_id, repo_id, repository_relative_path, localization_kind, line_start, line_end, content_sha256, provenance_json "
            "FROM repository_inventory_source_occurrence WHERE occurrence_id=?", [occurrence_id]
        ))
        if not rows:
            return None
        links = query._rows(con.execute(
            "SELECT link_id, object_kind, object_id, linkage_role, basis_json "
            "FROM repository_inventory_object_occurrence WHERE occurrence_id=? "
            "ORDER BY object_kind, object_id, linkage_role, link_id", [occurrence_id]
        ))
    return {
        "schema_version": "repository-source-occurrence-query/v1",
        "occurrence": rows[0],
        "object_links": links,
    }

def list_repository_inventory_diagnostics(query, *, severity: str | None = None, code: str | None = None, token: str = "", max_results: int = 100, page_token: str = "") -> dict[str, Any]:
    _require(query)
    clauses = ["1=1"]
    args: list[Any] = []
    if severity:
        clauses.append("severity=?")
        args.append(severity)
    if code:
        clauses.append("code=?")
        args.append(code)
    if token:
        clauses.append("lower(code || ' ' || message) LIKE ?")
        args.append(f"%{token.casefold()}%")
    where = " AND ".join(clauses)
    filters = {"severity": severity, "code": code, "token": token}
    return query._paged_select(
        kind="repository-inventory-diagnostics", query_id="repository_inventory_diagnostics",
        select_sql=f"SELECT diagnostic_id, scope_id, repo_id, code, severity, message, basis_json FROM repository_inventory_diagnostic WHERE {where} ORDER BY severity, code, diagnostic_id",
        count_sql=f"SELECT count(*) FROM repository_inventory_diagnostic WHERE {where}",
        args=args, filters=filters, max_results=max_results, page_token=page_token,
    )


def _repository_occurrence_ids_by_object(con, object_kind: str) -> dict[str, list[str]]:
    rows = con.execute(
        "SELECT object_id, occurrence_id FROM repository_inventory_object_occurrence "
        "WHERE object_kind=? ORDER BY object_id, occurrence_id", [object_kind]
    ).fetchall()
    result: dict[str, list[str]] = {}
    for object_id, occurrence_id in rows:
        bucket = result.setdefault(str(object_id), [])
        value = str(occurrence_id)
        if value not in bucket:
            bucket.append(value)
    return result


def repository_inventory_portfolio_snapshot(query) -> dict[str, Any]:
    """Return one compact, immutable repository projection for portfolio consumers.

    This is a read-only projection of canonical repository_inventory_* relations.
    It does not classify new concepts, resolve peers, or infer system membership.
    """
    _require(query)
    with query._connect() as con:
        identity_rows = query._rows(con.execute(
            "SELECT scope_id, repo_id, repository_id, repository_name, source_kind, "
            "repository_url, default_branch, source_metadata_json "
            "FROM repository_inventory_identity ORDER BY repo_id LIMIT 1"
        ))
        identity = identity_rows[0] if identity_rows else {}
        extensions = {
            str(ext): int(count)
            for ext, count in con.execute(
                "SELECT extension, file_count FROM repository_inventory_extension ORDER BY extension"
            ).fetchall()
        }
        technologies = query._rows(con.execute(
            "SELECT category, technology, status, confidence, basis_json "
            "FROM repository_inventory_technology ORDER BY category, technology, technology_id"
        ))
        candidate_occurrences = _repository_occurrence_ids_by_object(con, "discovery_candidate")
        discovery_candidates = query._rows(con.execute(
            "SELECT candidate_id, family_id, family_kind, structural_salience_score, discovery_kind, basis_json "
            "FROM repository_inventory_candidate ORDER BY discovery_kind, structural_salience_score DESC, candidate_id"
        ))
        for item in discovery_candidates:
            item["source_occurrence_ids"] = list(candidate_occurrences.get(str(item.get("candidate_id") or ""), ()))
        gap_occurrences = _repository_occurrence_ids_by_object(con, "coverage_gap")
        coverage_gaps = query._rows(con.execute(
            "SELECT gap_occurrence_id, gap_kind, subject_kind, subject_id, discovery_kind, coverage_status, relevance_status, "
            "localization_scope_kind, localization_status FROM repository_inventory_coverage_gap "
            "ORDER BY gap_kind, discovery_kind, subject_kind, subject_id, gap_occurrence_id"
        ))
        for item in coverage_gaps:
            item["source_occurrence_ids"] = list(gap_occurrences.get(str(item.get("gap_occurrence_id") or ""), ()))
        interfaces = query._rows(con.execute(
            "SELECT interface_id, direction, boundary_kind, protocol, operation, endpoint_or_topic, "
            "http_method, peer_system, peer_resolution_status, evidence_status, source_artifact_id, basis_json "
            "FROM repository_inventory_interface ORDER BY direction, protocol, endpoint_or_topic, operation, interface_id"
        ))
        phase_row = con.execute("SELECT evaluation_phase FROM repository_inventory_build ORDER BY started_at DESC LIMIT 1").fetchone()
        counts = {
            "files": int(con.execute("SELECT count(*) FROM repository_inventory_file").fetchone()[0]),
            "discovery_candidates": int(con.execute("SELECT count(*) FROM repository_inventory_candidate").fetchone()[0]),
            "unknown_primitives": int(con.execute("SELECT count(*) FROM repository_inventory_candidate WHERE discovery_kind='unknown_primitive'").fetchone()[0]),
            "coverage_gaps": int(con.execute("SELECT count(*) FROM repository_inventory_coverage_gap").fetchone()[0]),
            "source_occurrences": int(con.execute("SELECT count(*) FROM repository_inventory_source_occurrence").fetchone()[0]),
            "source_occurrence_links": int(con.execute("SELECT count(*) FROM repository_inventory_object_occurrence").fetchone()[0]),
            "outside_analyzer_frontier_files": int(con.execute(
                "SELECT count(*) FROM repository_inventory_file WHERE analyzer_frontier_status='outside_analyzer_frontier'"
            ).fetchone()[0]),
            "diagnostics": int(con.execute("SELECT count(*) FROM repository_inventory_diagnostic").fetchone()[0]),
        }
    return {
        "schema_version": "repository-inventory-portfolio-snapshot/v5",
        "identity": identity,
        "evaluation_phase": str(phase_row[0]) if phase_row else None,
        "extensions": extensions,
        "technologies": technologies,
        "discovery_candidates": discovery_candidates,
        "coverage_gaps": coverage_gaps,
        "interfaces": interfaces,
        "counts": counts,
    }
