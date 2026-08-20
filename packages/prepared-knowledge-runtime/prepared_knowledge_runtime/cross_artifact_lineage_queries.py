from __future__ import annotations

import json
from pathlib import Path
from typing import Any

try:
    import duckdb
except Exception:  # pragma: no cover
    duckdb = None


class DataModelLineageUnavailableError(RuntimeError):
    pass


class DataModelLineageReadService:
    """Thin read-only projection over canonical cross-artifact S2T knowledge.

    The adapter never traverses SQL, resolves producers, classifies value/control
    operands, or resolves placeholders. Those semantics must already be present in
    cross-artifact-data-model-mapping/v6.
    """

    SCHEMA_VERSION = "cross-artifact-data-model-mapping/v6"
    REQUIRED_TABLES = {
        "cross_artifact_mapping_build",
        "cross_artifact_workflow_projection_physical_mapping",
        "cross_artifact_value_origin_physical_lineage",
        "cross_artifact_mapping_gap",
    }
    _PRIMARY_ORIGIN_KINDS = {"logical_field", "object_presence", "sql_column"}
    _DEPENDENCY_ORIGIN_KINDS = {"storage_identity", "reference_key"}

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser().resolve()
        if duckdb is None:
            raise DataModelLineageUnavailableError("duckdb is required to query cross-artifact data-model lineage")
        if not self.path.is_file():
            raise DataModelLineageUnavailableError(f"cross-artifact data-model database is unavailable: {self.path}")
        with self._connect() as con:
            tables = {
                str(row[0])
                for row in con.execute(
                    "SELECT table_name FROM information_schema.tables WHERE table_schema='main'"
                ).fetchall()
            }
            missing = sorted(self.REQUIRED_TABLES - tables)
            if missing:
                raise DataModelLineageUnavailableError(
                    f"artifact is not {self.SCHEMA_VERSION}; missing tables: {missing}"
                )
            build = self._one(con, "SELECT * FROM cross_artifact_mapping_build LIMIT 1")
            if not build or str(build.get("schema_version") or "") != self.SCHEMA_VERSION:
                raise DataModelLineageUnavailableError(
                    f"artifact does not declare {self.SCHEMA_VERSION}"
                )
            if str(build.get("build_status") or "") != "complete":
                raise DataModelLineageUnavailableError("cross-artifact data-model mapping build is incomplete")

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

    @staticmethod
    def _json(value: Any, default: Any) -> Any:
        if value is None:
            return default
        if isinstance(value, (dict, list)):
            return value
        try:
            return json.loads(str(value))
        except (TypeError, ValueError, json.JSONDecodeError):
            return default

    def _resolve_target_table_code(self, con: Any, target_relation: str) -> str | None:
        requested = target_relation.strip()
        if not requested:
            return None
        rows = con.execute(
            "SELECT DISTINCT target_table_code FROM cross_artifact_workflow_projection_physical_mapping "
            "WHERE lower(target_table_code)=lower(?) ORDER BY target_table_code",
            [requested],
        ).fetchall()
        if rows:
            return str(rows[0][0])
        # API addressing convenience only: cross-artifact/PDM identity is the table code,
        # while callers may provide the already-known SQL-qualified target relation.
        leaf = requested.rsplit(".", 1)[-1]
        rows = con.execute(
            "SELECT DISTINCT target_table_code FROM cross_artifact_workflow_projection_physical_mapping "
            "WHERE lower(target_table_code)=lower(?) ORDER BY target_table_code",
            [leaf],
        ).fetchall()
        return str(rows[0][0]) if len(rows) == 1 else None

    @staticmethod
    def _display_source_column(row: dict[str, Any]) -> str:
        kind = str(row.get("origin_kind") or "")
        if kind == "logical_field" and row.get("logical_field_name"):
            return str(row["logical_field_name"])
        if kind in {"storage_identity", "reference_key", "object_presence"} and row.get("storage_key_field"):
            return str(row["storage_key_field"])
        return str(row.get("source_sql_column_name") or "")

    def _source_ref(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "relation": str(row.get("source_sql_relation_name") or ""),
            "column": self._display_source_column(row),
            "status": str(row.get("source_resolution_status") or "partial"),
        }

    @staticmethod
    def _dedupe_refs(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen: set[tuple[str, ...]] = set()
        result: list[dict[str, Any]] = []
        for row in rows:
            key = (
                str(row.get("relation") or "").casefold(),
                str(row.get("column") or "").casefold(),
                str(row.get("status") or ""),
            )
            if key in seen:
                continue
            seen.add(key)
            result.append(row)
        return sorted(
            result,
            key=lambda item: (
                str(item.get("relation") or "").casefold(),
                str(item.get("column") or "").casefold(),
                str(item.get("status") or ""),
            ),
        )

    def list_target_source_mapping(
        self,
        *,
        target_relation: str,
        target_column: str | None,
        include_gaps: bool,
        max_gaps: int,
        offset: int,
        limit: int,
    ) -> dict[str, Any]:
        with self._connect() as con:
            target_table_code = self._resolve_target_table_code(con, target_relation)
            filters = {
                "target_relation": target_relation,
                "target_table_code": target_table_code,
                "target_column": target_column,
            }
            if target_table_code is None:
                return {
                    "schema_version": "target-source-mapping/v1",
                    "filters": filters,
                    "target_relation": target_relation,
                    "target_table_code": None,
                    "mappings": [],
                    "total_count": 0,
                    "gaps": [],
                    "gap_count": 0,
                    "gaps_truncated": False,
                    "summary": {
                        "target_column_count": 0,
                        "source_count": 0,
                        "dependency_count": 0,
                        "complete_count": 0,
                        "partial_count": 0,
                        "no_source_count": 0,
                        "unresolved_placeholder_source_count": 0,
                    },
                }

            clauses = ["lower(target_table_code)=lower(?)"]
            params: list[Any] = [target_table_code]
            if target_column is not None:
                clauses.append("lower(physical_column_code)=lower(?)")
                params.append(target_column)
            where = " AND ".join(clauses)
            target_rows = self._rows(
                con,
                f"""SELECT workflow_context_file,target_table_code,physical_model_table_id,
                           physical_model_column_id,physical_column_code,transform_sql_file,
                           transform_query_id,projection_id,projection_expression,mapping_status,
                           knowledge_class,mapping_basis
                    FROM cross_artifact_workflow_projection_physical_mapping
                    WHERE {where}
                    ORDER BY lower(physical_column_code),physical_column_code,projection_id""",
                params,
            )
            grouped_targets: dict[str, list[dict[str, Any]]] = {}
            for row in target_rows:
                grouped_targets.setdefault(str(row["physical_column_code"]), []).append(row)
            ordered_columns = sorted(grouped_targets, key=lambda value: (value.casefold(), value))
            total = len(ordered_columns)
            selected_columns = ordered_columns[offset : offset + limit]

            origins_by_column: dict[str, list[dict[str, Any]]] = {column: [] for column in selected_columns}
            if selected_columns:
                placeholders = ",".join("?" for _ in selected_columns)
                origin_rows = self._rows(
                    con,
                    f"""SELECT * FROM cross_artifact_value_origin_physical_lineage
                        WHERE lower(target_table_code)=lower(?)
                          AND lower(physical_column_code) IN ({placeholders})
                        ORDER BY lower(physical_column_code),physical_column_code,
                                 lower(source_sql_relation_name),source_sql_relation_name,
                                 lower(source_sql_column_name),source_sql_column_name,origin_kind,lineage_id""",
                    [target_table_code, *[column.casefold() for column in selected_columns]],
                )
                for row in origin_rows:
                    origins_by_column.setdefault(str(row["physical_column_code"]), []).append(row)

            mappings: list[dict[str, Any]] = []
            all_source_refs: list[dict[str, Any]] = []
            all_dependency_refs: list[dict[str, Any]] = []
            status_counts = {"complete": 0, "partial": 0, "no_source": 0}
            for column in selected_columns:
                projections = grouped_targets[column]
                origins = origins_by_column.get(column, [])
                primary_rows = [row for row in origins if str(row.get("origin_kind") or "") in self._PRIMARY_ORIGIN_KINDS]
                dependency_rows = [row for row in origins if str(row.get("origin_kind") or "") in self._DEPENDENCY_ORIGIN_KINDS]
                # Unknown future semantic kinds are not silently discarded: expose them as dependencies.
                dependency_rows.extend(
                    row for row in origins
                    if str(row.get("origin_kind") or "") not in self._PRIMARY_ORIGIN_KINDS | self._DEPENDENCY_ORIGIN_KINDS
                )
                sources = self._dedupe_refs([self._source_ref(row) for row in primary_rows])
                dependencies = self._dedupe_refs([self._source_ref(row) for row in dependency_rows])
                if not sources:
                    mapping_status = "no_source"
                elif any(str(source.get("status")) != "confirmed" for source in sources):
                    mapping_status = "partial"
                else:
                    mapping_status = "complete"
                status_counts[mapping_status] += 1
                mappings.append({
                    "target_column": column,
                    "sources": sources,
                    "mapping_status": mapping_status,
                    "source_count": len(sources),
                    "dependency_count": len(dependencies),
                })
                all_source_refs.extend(sources)
                all_dependency_refs.extend(dependencies)

            gaps: list[dict[str, Any]] = []
            gap_count = 0
            if include_gaps and selected_columns:
                projection_ids = sorted({str(row["projection_id"]) for column in selected_columns for row in grouped_targets[column]})
                placeholders = ",".join("?" for _ in projection_ids)
                if projection_ids:
                    gap_count = int(con.execute(
                        f"SELECT count(*) FROM cross_artifact_mapping_gap WHERE owner_kind='target_projection' AND owner_id IN ({placeholders})",
                        projection_ids,
                    ).fetchone()[0])
                    gaps = self._rows(
                        con,
                        f"""SELECT gap_id,gap_kind,severity,owner_id,message,details_json
                            FROM cross_artifact_mapping_gap
                            WHERE owner_kind='target_projection' AND owner_id IN ({placeholders})
                            ORDER BY severity,gap_kind,gap_id LIMIT ?""",
                        [*projection_ids, max_gaps],
                    )
                    for gap in gaps:
                        gap["details"] = self._json(gap.pop("details_json"), {})

            unique_sources = self._dedupe_refs(all_source_refs)
            unique_dependencies = self._dedupe_refs(all_dependency_refs)
            return {
                "schema_version": "target-source-mapping/v1",
                "filters": filters,
                "target_relation": target_relation,
                "target_table_code": target_table_code,
                "mappings": mappings,
                "total_count": total,
                "gaps": gaps,
                "gap_count": gap_count,
                "gaps_truncated": gap_count > len(gaps),
                "summary": {
                    "target_column_count": total,
                    "source_count": len(unique_sources),
                    "dependency_count": len(unique_dependencies),
                    "complete_count": status_counts["complete"],
                    "partial_count": status_counts["partial"],
                    "no_source_count": status_counts["no_source"],
                    "unresolved_placeholder_source_count": sum(
                        1 for row in unique_sources if row.get("status") == "unresolved_placeholder"
                    ),
                },
            }

    def list_lineage(
        self,
        *,
        logical_type: str | None,
        logical_field: str | None,
        target_table: str | None,
        target_column: str | None,
        knowledge_class: str | None,
        search: str | None,
        offset: int,
        limit: int,
    ) -> dict[str, Any]:
        clauses: list[str] = []
        params: list[Any] = []
        filters = {
            "logical_type": logical_type,
            "logical_field": logical_field,
            "target_table": target_table,
            "target_column": target_column,
            "knowledge_class": knowledge_class,
            "search": search,
        }
        exact_filters = [
            ("logical_fully_qualified_name", logical_type),
            ("logical_field_name", logical_field),
            ("target_table_code", target_table),
            ("physical_column_code", target_column),
            ("knowledge_class", knowledge_class),
        ]
        for column, value in exact_filters:
            if value is not None:
                clauses.append(f"lower({column}) = lower(?)")
                params.append(value)
        if search:
            token = f"%{search}%"
            clauses.append("(" + " OR ".join([
                "coalesce(logical_fully_qualified_name,'') ILIKE ?",
                "coalesce(logical_field_name,'') ILIKE ?",
                "origin_identity ILIKE ?",
                "coalesce(source_sql_relation_id,'') ILIKE ?",
                "source_sql_column_name ILIKE ?",
                "target_table_code ILIKE ?",
                "physical_column_code ILIKE ?",
                "coalesce(target_projection_expression,'') ILIKE ?",
            ]) + ")")
            params.extend([token] * 8)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as con:
            total = int(con.execute(
                f"SELECT count(*) FROM cross_artifact_value_origin_physical_lineage{where}", params
            ).fetchone()[0])
            rows = self._rows(
                con,
                f"""SELECT * FROM cross_artifact_value_origin_physical_lineage{where}
                    ORDER BY lower(target_table_code),target_table_code,
                             lower(physical_column_code),physical_column_code,
                             origin_kind,lower(origin_identity),origin_identity,lineage_id
                    LIMIT ? OFFSET ?""",
                [*params, limit, offset],
            )
            summary_row = self._one(
                con,
                f"""SELECT count(*) AS path_count,
                           count(DISTINCT origin_identity) AS origin_count,
                           count(DISTINCT target_table_code) AS target_table_count,
                           count(DISTINCT target_table_code || '#' || physical_column_code) AS target_column_count,
                           count(DISTINCT source_sql_file) AS source_sql_file_count,
                           count(DISTINCT transform_sql_file) AS transform_sql_file_count
                    FROM cross_artifact_value_origin_physical_lineage{where}""",
                params,
            ) or {}
            kind_rows = con.execute(
                f"SELECT origin_kind,count(*) FROM cross_artifact_value_origin_physical_lineage{where} GROUP BY origin_kind ORDER BY origin_kind",
                params,
            ).fetchall()
            knowledge_class_rows = con.execute(
                f"SELECT knowledge_class,count(*) FROM cross_artifact_value_origin_physical_lineage{where} GROUP BY knowledge_class ORDER BY knowledge_class",
                params,
            ).fetchall()
        items: list[dict[str, Any]] = []
        role_counts: dict[str, int] = {}
        for row in rows:
            for json_field, output_field, default in (
                ("origin_semantics_json", "origin_semantics", {}),
                ("projection_path_json", "projection_path", []),
                ("materialization_path_json", "materialization_path", []),
                ("workflow_dependency_path_json", "workflow_dependency_path", []),
                ("provenance_json", "provenance", {}),
            ):
                row[output_field] = self._json(row.pop(json_field), default)
            role = str((row.get("origin_semantics") or {}).get("lineage_role") or "value")
            role_counts[role] = role_counts.get(role, 0) + 1
            items.append(row)
        summary = dict(summary_row)
        summary["by_origin_kind"] = {str(key): int(value) for key, value in kind_rows}
        summary["by_knowledge_class"] = {str(key): int(value) for key, value in knowledge_class_rows}
        summary["by_lineage_role"] = role_counts
        return {
            "schema_version": "data-model-lineage-query/v2",
            "filters": filters,
            "items": items,
            "total_count": total,
            "summary": summary,
        }
