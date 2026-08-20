from __future__ import annotations

import json
from pathlib import Path
from typing import Any

try:
    import duckdb
except Exception:  # pragma: no cover
    duckdb = None


class EffectiveDataModelUnavailableError(RuntimeError):
    pass


class DataObjectNotFoundError(KeyError):
    pass


class RelationshipNotFoundError(KeyError):
    pass


class EffectiveDataModelReadService:
    """Schema-owned read projection over effective-data-model/v1.

    KLC owns the DuckDB schema and all interpretation of materialized effective-model
    rows. Consumers receive stable semantic dictionaries and do not know mart names or
    columns.
    """

    REQUIRED_TABLES = {
        "effective_data_model_build",
        "effective_data_model_entity",
        "effective_data_model_field",
        "effective_data_model_key",
        "effective_data_model_relationship",
        "effective_data_model_gap",
        "effective_data_model_coverage",
    }

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser().resolve()
        if duckdb is None:
            raise EffectiveDataModelUnavailableError("duckdb is required to query effective-data-model/v1")
        if not self.path.is_file():
            raise EffectiveDataModelUnavailableError(f"effective data model database is unavailable: {self.path}")
        with self._connect() as con:
            tables = {
                str(row[0])
                for row in con.execute(
                    "SELECT table_name FROM information_schema.tables WHERE table_schema='main'"
                ).fetchall()
            }
            missing = sorted(self.REQUIRED_TABLES - tables)
            if missing:
                raise EffectiveDataModelUnavailableError(
                    "artifact does not contain effective-data-model/v1 tables: " + ", ".join(missing)
                )
            build = self._one(con, "SELECT * FROM effective_data_model_build LIMIT 1")
            if not build or str(build.get("schema_version") or "") != "effective-data-model/v1":
                raise EffectiveDataModelUnavailableError("artifact does not declare effective-data-model/v1")
            if str(build.get("build_status") or "") != "complete":
                raise EffectiveDataModelUnavailableError("effective-data-model/v1 build is incomplete")

    def _connect(self):
        return duckdb.connect(str(self.path), read_only=True)

    @staticmethod
    def _rows(con: Any, sql: str, params: list[Any] | tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        cursor = con.execute(sql, params)
        names = [str(item[0]) for item in cursor.description]
        return [dict(zip(names, row, strict=True)) for row in cursor.fetchall()]

    @classmethod
    def _one(cls, con: Any, sql: str, params: list[Any] | tuple[Any, ...] = ()) -> dict[str, Any] | None:
        rows = cls._rows(con, sql, params)
        return rows[0] if rows else None

    def field_catalog(self, system_id: str) -> dict[str, Any]:
        with self._connect() as con:
            entities = self._rows(
                con,
                """SELECT effective_entity_id, logical_name, logical_fully_qualified_name,
                          physical_table_name, physical_table_code, mapping_status
                   FROM effective_data_model_entity
                   ORDER BY logical_fully_qualified_name, effective_entity_id""",
            )
            fields = self._rows(
                con,
                """SELECT effective_entity_id, logical_field_name
                   FROM effective_data_model_field
                   ORDER BY effective_entity_id, inherited_depth, logical_field_name, effective_field_id""",
            )
        by_entity: dict[str, list[dict[str, Any]]] = {}
        for row in fields:
            by_entity.setdefault(str(row["effective_entity_id"]), []).append(
                {"field_name": str(row["logical_field_name"]), "description": None}
            )
        return {
            "system_id": system_id,
            "tables": [
                {
                    "table_id": str(row["effective_entity_id"]),
                    "table_name": str(row["logical_name"]),
                    "description": _entity_description(row),
                    "fields": by_entity.get(str(row["effective_entity_id"]), []),
                }
                for row in entities
            ],
        }

    def relationship_counts(self) -> dict[str, int]:
        with self._connect() as con:
            rows = self._rows(
                con,
                """SELECT source_effective_entity_id, count(*) AS relationship_count
                   FROM effective_data_model_relationship
                   GROUP BY source_effective_entity_id""",
            )
        return {str(row["source_effective_entity_id"]): int(row["relationship_count"]) for row in rows}

    def table_detail(self, system_id: str, table_id: str) -> dict[str, Any]:
        with self._connect() as con:
            entity = self._one(con, "SELECT * FROM effective_data_model_entity WHERE effective_entity_id=?", [table_id])
            if entity is None:
                raise DataObjectNotFoundError(table_id)
            fields = self._rows(
                con,
                """SELECT * FROM effective_data_model_field
                   WHERE effective_entity_id=?
                   ORDER BY inherited_depth, logical_field_name, effective_field_id""",
                [table_id],
            )
            keys = self._rows(
                con,
                """SELECT * FROM effective_data_model_key
                   WHERE effective_entity_id=?
                   ORDER BY key_kind, effective_key_id""",
                [table_id],
            )
            relationships = self._rows(
                con,
                """SELECT * FROM effective_data_model_relationship
                   WHERE source_effective_entity_id=?
                   ORDER BY logical_field_id, effective_relationship_id""",
                [table_id],
            )
            all_entities = self._rows(con, "SELECT * FROM effective_data_model_entity")
            build = self._one(con, "SELECT * FROM effective_data_model_build LIMIT 1") or {}
        entities_by_id = {str(item["effective_entity_id"]): item for item in all_entities}
        field_name_by_id = {str(item["logical_field_id"]): str(item["logical_field_name"]) for item in fields}
        relationship_by_field = {str(item["logical_field_id"]): item for item in relationships}
        return {
            "system_id": system_id,
            "workspace_id": str(build.get("scope_id") or "") or None,
            "build_id": str(build.get("build_id") or "") or None,
            "generated_at": _iso(build.get("completed_at")),
            "object": {
                "id": str(entity["effective_entity_id"]),
                "name": str(entity["logical_name"]),
                "kind": "effective_entity",
                "display_name": str(entity.get("physical_table_name") or "") or None,
                "description": _entity_description(entity),
            },
            "fields": [
                {
                    "name": str(item["logical_field_name"]),
                    "type": str(item.get("normalized_type_expression") or item.get("declared_type_expression") or "unknown"),
                    "target_object": (
                        str(relationship_by_field[str(item["logical_field_id"])]["target_effective_entity_id"])
                        if str(item["logical_field_id"]) in relationship_by_field else None
                    ),
                    "display_name": None,
                    "description": _field_description(item),
                    "nullable": None if item.get("physical_mandatory") is None else not bool(item.get("physical_mandatory")),
                    "inherited": bool(item.get("is_inherited")),
                    "storage_observation_count": 0,
                    "storage_observations": [],
                    "storage_observations_truncated": False,
                }
                for item in fields
            ],
            "keys": [
                {
                    "kind": str(item.get("key_kind") or "unknown"),
                    "fields": [field_name_by_id[str(item["logical_field_id"])]]
                    if str(item.get("logical_field_id") or "") in field_name_by_id else [],
                    "version_field": None,
                    "collocation_field": None,
                }
                for item in keys
            ],
            "relationships": [self._relationship_summary(item, entities_by_id, field_name_by_id) for item in relationships],
            "embedded_objects": [],
            "relationship_candidate_count": sum(1 for item in relationships if item.get("mapping_status") != "matched"),
            "indexes": [],
            "constraints": [],
            "partitioning": [],
            "triggers": [],
        }

    def relationship_detail(self, table_id: str, relationship_id: str) -> dict[str, Any]:
        with self._connect() as con:
            source = self._one(con, "SELECT * FROM effective_data_model_entity WHERE effective_entity_id=?", [table_id])
            if source is None:
                raise DataObjectNotFoundError(table_id)
            relationship = self._one(
                con,
                """SELECT * FROM effective_data_model_relationship
                   WHERE source_effective_entity_id=? AND effective_relationship_id=?""",
                [table_id, relationship_id],
            )
            if relationship is None:
                raise RelationshipNotFoundError(relationship_id)
            target = self._one(
                con,
                "SELECT * FROM effective_data_model_entity WHERE effective_entity_id=?",
                [relationship["target_effective_entity_id"]],
            )
            field = self._one(
                con,
                """SELECT * FROM effective_data_model_field
                   WHERE effective_entity_id=? AND logical_field_id=? LIMIT 1""",
                [table_id, relationship["logical_field_id"]],
            ) or {}
        matched = str(relationship.get("mapping_status") or "") == "matched"
        source_field = str(field.get("logical_field_name") or relationship.get("logical_field_id") or "unknown")
        source_physical = str(relationship.get("source_physical_column_id") or "")
        target_physical = str(relationship.get("target_physical_column_id") or "")
        return {
            "relationship_id": str(relationship["effective_relationship_id"]),
            "kind": str(relationship.get("relationship_kind") or "declared_relationship"),
            "source": {"field": source_field, "inherited": bool(field.get("is_inherited")), "cardinality": "unknown"},
            "target": {
                "object": {
                    "id": str(target["effective_entity_id"]),
                    "name": str(target["logical_name"]),
                    "kind": "effective_entity",
                    "display_name": str(target.get("physical_table_name") or "") or None,
                    "description": _entity_description(target),
                },
                "aliases": [],
                "logical_identity": {
                    "status": "declared_target", "fields": [], "version_fields": [], "collocation_fields": [],
                    "classification_basis": "effective_data_model_relationship",
                },
                "storage_key": {
                    "status": "physical_relationship_matched" if matched else "not_resolved",
                    "fields": [target_physical] if target_physical else [], "expressions": [], "evidence": [],
                },
            },
            "reference": {
                "assignment_operations": [], "value_origins": [],
                "encoding_inputs": {
                    "type_component": {"source": "target_alias", "values": []},
                    "key_component": {"source": "target_storage_key", "fields": [target_physical] if target_physical else []},
                },
                "physical_encoding": {"status": "confirmed" if matched and relationship.get("physical_model_relationship_id") else "not_confirmed"},
            },
            "join": {
                "method": "physical_model_relationship" if relationship.get("physical_model_relationship_id") else "not_materialized",
                "source": {"field": source_field, "kind": "logical_field", "fields": [source_physical] if source_physical else [], "expression": None, "expressions": [], "composed_expression": None},
                "target": {"field": None, "kind": "physical_column_id", "fields": [target_physical] if target_physical else [], "expression": None, "expressions": [], "composed_expression": None},
                "requires_encoding_interpretation": False,
                "physical_join_confirmed": bool(matched and relationship.get("physical_model_relationship_id")),
                "match_basis": str(relationship.get("mapping_basis") or "") or None,
                "parent_key_passed": None,
                "collection_membership_semantics": None,
            },
            "polymorphic_targets": [],
            "provenance": _json_object(relationship.get("provenance_json")),
        }

    @staticmethod
    def _relationship_summary(
        relationship: dict[str, Any],
        entities_by_id: dict[str, dict[str, Any]],
        field_name_by_id: dict[str, str],
    ) -> dict[str, Any]:
        target = entities_by_id[str(relationship["target_effective_entity_id"])]
        matched = str(relationship.get("mapping_status") or "") == "matched"
        source_physical = str(relationship.get("source_physical_column_id") or "")
        target_physical = str(relationship.get("target_physical_column_id") or "")
        return {
            "relationship_id": str(relationship["effective_relationship_id"]),
            "kind": str(relationship.get("relationship_kind") or "declared_relationship"),
            "source_field": field_name_by_id.get(str(relationship.get("logical_field_id") or ""), "unknown"),
            "cardinality": "unknown",
            "target": {
                "object": {"id": str(target["effective_entity_id"]), "name": str(target["logical_name"]), "kind": "effective_entity"},
                "aliases": None,
            },
            "join": {
                "method": "physical_model_relationship" if relationship.get("physical_model_relationship_id") else "not_materialized",
                "source_fields": [source_physical] if source_physical else [],
                "target_fields": [target_physical] if target_physical else None,
                "target_kind": "physical_column_id" if target_physical else None,
                "source_expressions": None, "target_expressions": None,
                "requires_encoding_interpretation": False,
                "physical_join_confirmed": bool(matched and relationship.get("physical_model_relationship_id")),
                "match_basis": str(relationship.get("mapping_basis") or "") or None,
                "parent_key_passed": None,
                "collection_membership_semantics": None,
            },
            "polymorphic_targets": None,
        }

    def analysis_coverage(self, _system_id: str) -> dict[str, Any]:
        with self._connect() as con:
            metrics = {
                str(row["metric_name"]): int(row["metric_value"])
                for row in self._rows(con, "SELECT metric_name, metric_value FROM effective_data_model_coverage")
            }
            gap_rows = self._rows(con, "SELECT gap_kind, severity, count(*) AS count FROM effective_data_model_gap GROUP BY gap_kind, severity")
            repository_count = int(self._one(con, "SELECT count(DISTINCT repo_id) AS value FROM effective_data_model_entity")["value"])
            unresolved = int(self._one(con, """SELECT count(*) AS value FROM effective_data_model_entity
                       WHERE mapping_status NOT IN ('matched','not_applicable')""")["value"]) + int(
                self._one(con, """SELECT count(*) AS value FROM effective_data_model_field
                       WHERE mapping_status NOT IN ('matched','not_applicable')""")["value"]
            )
        known_gaps = sum(int(row["count"]) for row in gap_rows)
        unsupported = sum(int(row["count"]) for row in gap_rows if str(row["gap_kind"]).startswith("unsupported"))
        conflicting = sum(int(row["count"]) for row in gap_rows if "conflict" in str(row["gap_kind"]))
        observed = metrics.get("logical_entities", 0) + metrics.get("logical_fields", 0) + metrics.get("logical_relationships", 0) + metrics.get("matched_keys", 0)
        limitations = [
            {"source": "effective-data-model/v1", "status": "known_gap", "category": "materialized_gap", "kind": str(row["gap_kind"]), "count": int(row["count"])}
            for row in gap_rows
        ]
        status = "complete" if known_gaps == 0 and unresolved == 0 else "partial"
        return {
            "status": status,
            "statement": "Coverage is derived from effective-data-model/v1 materialized facts and explicit gaps.",
            "count_basis": "materialized_effective_model_rows",
            "summary": {
                "repository_count": repository_count, "observed_fact_count": observed, "known_gap_count": known_gaps,
                "unresolved_count": unresolved, "conflicting_count": conflicting, "unsupported_count": unsupported,
                "not_observed_count": 0, "requires_interpretation_count": unresolved,
                "physical_join_observation_count": metrics.get("matched_relationships", 0),
            },
            "domains": {
                "source_facts": {"status": "available", "observed_fact_count": observed},
                "data_model": {
                    "status": status, "relationship_count": metrics.get("logical_relationships", 0),
                    "unresolved_relationship_candidate_count": max(0, metrics.get("logical_relationships", 0) - metrics.get("matched_relationships", 0)),
                },
                "physical_storage": {
                    "status": "available" if metrics.get("physical_tables", 0) else "not_available",
                    "storage_evidence_relationship_count": metrics.get("matched_relationships", 0),
                    "requires_interpretation_count": unresolved,
                    "physical_join_observation_count": metrics.get("matched_relationships", 0),
                },
                "analysis_gaps": {
                    "status": "complete" if known_gaps == 0 else "partial",
                    "known_gap_count": known_gaps,
                    "status_counts": _count_by(gap_rows, "severity"),
                },
            },
            "limitations": limitations,
            "limitations_total_groups": len(limitations),
            "limitations_truncated": False,
        }


def _entity_description(row: dict[str, Any]) -> str | None:
    physical = str(row.get("physical_table_code") or row.get("physical_table_name") or "").strip()
    status = str(row.get("mapping_status") or "").strip()
    if physical:
        return f"Effective entity; physical table {physical}; mapping status {status}."
    return f"Effective entity; mapping status {status}." if status else "Effective entity."


def _field_description(row: dict[str, Any]) -> str | None:
    physical = str(row.get("physical_column_code") or row.get("physical_column_name") or "").strip()
    status = str(row.get("mapping_status") or "").strip()
    if physical:
        return f"Physical column {physical}; mapping status {status}."
    return f"Mapping status {status}." if status else None


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return dict(parsed) if isinstance(parsed, dict) else {}
    return {}


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    method = getattr(value, "isoformat", None)
    return str(method()) if callable(method) else str(value)


def _count_by(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    result: dict[str, int] = {}
    for row in rows:
        value = str(row.get(key) or "unknown")
        result[value] = result.get(value, 0) + int(row.get("count") or 0)
    return result
