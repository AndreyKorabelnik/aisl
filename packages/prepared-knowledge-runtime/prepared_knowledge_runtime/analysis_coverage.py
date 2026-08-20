from __future__ import annotations

from collections import Counter
from typing import Any

ANALYSIS_COVERAGE_SCHEMA_VERSION = "analysis_coverage/v1"


def _count(connection: Any, relation: str, where: str = "1=1") -> int:
    return int(connection.execute(f"SELECT count(*) FROM {relation} WHERE {where}").fetchone()[0])


def _classify_limitation(category: object, kind: object) -> str:
    marker = f"{category or ''} {kind or ''}".casefold().replace("-", "_")
    if "unsupported" in marker or "not_supported" in marker:
        return "unsupported"
    if "conflict" in marker or "ambiguous" in marker:
        return "conflicting"
    if "not_observed" in marker:
        return "not_observed"
    return "unresolved"


def build_analysis_coverage(query: Any, *, max_limitations: int = 100) -> dict[str, Any]:
    """Build a deterministic coverage/limitations projection from existing KLC facts.

    Counts are diagnostic occurrences, not accuracy percentages and not unique business
    elements. An empty gap catalog means only that no known gaps were materialized.
    """

    with query._connect() as connection:  # KnowledgeLayerQuery owns the connection policy.
        has = query._has_relation
        repository_count = _count(connection, "workspace_repository") if has("workspace_repository") else 0
        observed_fact_count = _count(connection, "source_observation") if has("source_observation") else 0
        relationship_count = _count(connection, "model_relationship_observation") if has("model_relationship_observation") else 0
        relationship_candidate_count = _count(connection, "model_relationship_candidate") if has("model_relationship_candidate") else 0
        physical_relationship_observation_count = (
            _count(connection, "table_relationship_observation") if has("table_relationship_observation") else 0
        )

        storage_relationship_ids: set[str] = set()
        for relation in ("model_relationship_storage_reference", "model_relationship_storage_key_derivation"):
            if not has(relation):
                continue
            storage_relationship_ids.update(
                str(row[0])
                for row in connection.execute(
                    f"SELECT DISTINCT relationship_id FROM {relation} WHERE relationship_id IS NOT NULL"
                ).fetchall()
                if row and row[0]
            )

        limitations: list[dict[str, Any]] = []
        limitation_status_counts: Counter[str] = Counter()
        gap_count = 0
        if has("workspace_missing_fact"):
            rows = connection.execute(
                """
                SELECT coalesce(repo_id, 'unknown') AS repo_id,
                       coalesce(category, 'unknown') AS category,
                       coalesce(missing_fact_kind, 'unknown') AS missing_fact_kind,
                       required_for_operation,
                       count(*) AS occurrence_count
                FROM workspace_missing_fact
                GROUP BY repo_id, category, missing_fact_kind, required_for_operation
                ORDER BY occurrence_count DESC, repo_id, category, missing_fact_kind, required_for_operation
                """
            ).fetchall()
            gap_count = sum(int(row[4] or 0) for row in rows)
            for repo_id, category, missing_kind, operation, count in rows:
                status = _classify_limitation(category, missing_kind)
                limitation_status_counts[status] += int(count or 0)
                limitations.append(
                    {
                        "source": "workspace_missing_fact",
                        "status": status,
                        "repo_id": str(repo_id),
                        "category": str(category),
                        "kind": str(missing_kind),
                        "required_for_operation": str(operation) if operation else None,
                        "count": int(count or 0),
                    }
                )

        if relationship_candidate_count:
            limitation_status_counts["unresolved"] += relationship_candidate_count
            limitations.append(
                {
                    "source": "model_relationship_candidate",
                    "status": "unresolved",
                    "repo_id": None,
                    "category": "data_model",
                    "kind": "relationship_target_not_resolved",
                    "required_for_operation": "relationship_materialization",
                    "count": relationship_candidate_count,
                }
            )

        requires_interpretation_count = len(storage_relationship_ids)
        if requires_interpretation_count:
            limitations.append(
                {
                    "source": "canonical_relationship_storage",
                    "status": "requires_interpretation",
                    "repo_id": None,
                    "category": "physical_storage",
                    "kind": "physical_encoding_requires_downstream_interpretation",
                    "required_for_operation": "physical_join_generation",
                    "count": requires_interpretation_count,
                }
            )
            limitation_status_counts["requires_interpretation"] += requires_interpretation_count

        known_limitation_count = sum(limitation_status_counts.values())
        status = "partial" if known_limitation_count else "observed_no_known_gaps"
        limitations.sort(
            key=lambda item: (
                -int(item["count"]),
                str(item["status"]),
                str(item.get("repo_id") or ""),
                str(item["category"]),
                str(item["kind"]),
            )
        )
        truncated = len(limitations) > max_limitations

        return {
            "schema_version": ANALYSIS_COVERAGE_SCHEMA_VERSION,
            "status": status,
            "statement": (
                "Coverage describes observed facts and known limitations; absence of evidence does not prove absence in source systems."
            ),
            "count_basis": "diagnostic_occurrences_not_unique_business_elements",
            "summary": {
                "repository_count": repository_count,
                "observed_fact_count": observed_fact_count,
                "known_gap_count": gap_count,
                "unresolved_count": int(limitation_status_counts["unresolved"]),
                "conflicting_count": int(limitation_status_counts["conflicting"]),
                "unsupported_count": int(limitation_status_counts["unsupported"]),
                "not_observed_count": int(limitation_status_counts["not_observed"]),
                "requires_interpretation_count": requires_interpretation_count,
                "physical_join_observation_count": physical_relationship_observation_count,
            },
            "domains": {
                "source_facts": {
                    "status": "observed" if observed_fact_count else "not_observed",
                    "observed_fact_count": observed_fact_count,
                },
                "data_model": {
                    "status": "partial" if relationship_candidate_count else ("observed" if relationship_count else "not_observed"),
                    "relationship_count": relationship_count,
                    "unresolved_relationship_candidate_count": relationship_candidate_count,
                },
                "physical_storage": {
                    "status": "requires_interpretation" if requires_interpretation_count else (
                        "observed" if physical_relationship_observation_count else "not_observed"
                    ),
                    "storage_evidence_relationship_count": requires_interpretation_count,
                    "requires_interpretation_count": requires_interpretation_count,
                    "physical_join_observation_count": physical_relationship_observation_count,
                },
                "analysis_gaps": {
                    "status": "observed" if gap_count else "not_observed",
                    "known_gap_count": gap_count,
                    "status_counts": dict(sorted(limitation_status_counts.items())),
                },
            },
            "limitations": limitations[:max_limitations],
            "limitations_total_groups": len(limitations),
            "limitations_truncated": truncated,
        }
