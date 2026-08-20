from __future__ import annotations

import json
from pathlib import Path
from typing import Any

try:
    import duckdb
except ModuleNotFoundError:  # pragma: no cover
    duckdb = None


class ObservedStorageUsageUnavailableError(RuntimeError):
    pass


class ObservedStorageUsageReadService:
    REQUIRED_TABLES = {
        "observed_storage_access",
        "observed_storage_read",
        "observed_storage_write",
        "observed_storage_usage_gap",
    }

    def __init__(self, database_path: str | Path) -> None:
        if duckdb is None:
            raise ObservedStorageUsageUnavailableError("duckdb dependency is unavailable")
        self.database_path = Path(database_path).resolve()
        if not self.database_path.is_file():
            raise ObservedStorageUsageUnavailableError(
                f"observed-storage database is unavailable: {self.database_path}"
            )
        with self._connect() as connection:
            tables = {
                str(row[0])
                for row in connection.execute(
                    "SELECT table_name FROM information_schema.tables WHERE table_schema='main'"
                ).fetchall()
            }
        missing = sorted(self.REQUIRED_TABLES - tables)
        if missing:
            raise ObservedStorageUsageUnavailableError(
                "artifact does not contain observed-storage tables: " + ", ".join(missing)
            )

    def _connect(self):
        return duckdb.connect(str(self.database_path), read_only=True)

    @staticmethod
    def _json(value: Any, fallback: Any) -> Any:
        if value is None:
            return fallback
        if isinstance(value, (dict, list)):
            return value
        try:
            return json.loads(str(value))
        except (TypeError, ValueError, json.JSONDecodeError):
            return fallback

    @staticmethod
    def _where(
        *,
        repo_id: str | None,
        storage_kind: str | None,
        target_resolution_status: str | None,
        search: str | None,
        access_kind: str | None = None,
    ) -> tuple[str, list[Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if repo_id:
            clauses.append("repo_id = ?")
            params.append(repo_id)
        if storage_kind:
            clauses.append("storage_kind = ?")
            params.append(storage_kind)
        if target_resolution_status:
            clauses.append("target_resolution_status = ?")
            params.append(target_resolution_status)
        if access_kind:
            clauses.append("access_kind = ?")
            params.append(access_kind)
        if search:
            token = f"%{search.casefold()}%"
            clauses.append(
                "(lower(coalesce(storage_target_expression,'')) LIKE ? "
                "OR lower(coalesce(operation,'')) LIKE ? "
                "OR lower(coalesce(class_name,'')) LIKE ? "
                "OR lower(coalesce(method_name,'')) LIKE ?)"
            )
            params.extend([token, token, token, token])
        return (" WHERE " + " AND ".join(clauses)) if clauses else "", params

    def summary(self) -> dict[str, Any]:
        with self._connect() as connection:
            access_count = int(connection.execute("SELECT count(*) FROM observed_storage_access").fetchone()[0])
            read_count = int(connection.execute("SELECT count(*) FROM observed_storage_read").fetchone()[0])
            write_count = int(connection.execute("SELECT count(*) FROM observed_storage_write").fetchone()[0])
            gap_count = int(connection.execute("SELECT count(*) FROM observed_storage_usage_gap").fetchone()[0])
            by_kind = {
                str(row[0] or "unknown"): int(row[1])
                for row in connection.execute(
                    "SELECT coalesce(storage_kind,'unknown'), count(*) FROM observed_storage_access GROUP BY 1 ORDER BY 1"
                ).fetchall()
            }
            by_resolution = {
                str(row[0] or "unknown"): int(row[1])
                for row in connection.execute(
                    "SELECT coalesce(target_resolution_status,'unknown'), count(*) FROM observed_storage_access GROUP BY 1 ORDER BY 1"
                ).fetchall()
            }
        return {
            "access_count": access_count,
            "read_count": read_count,
            "write_count": write_count,
            "gap_count": gap_count,
            "by_storage_kind": by_kind,
            "by_resolution_status": by_resolution,
        }

    def list_accesses(
        self,
        *,
        repo_id: str | None,
        access_kind: str | None,
        storage_kind: str | None,
        target_resolution_status: str | None,
        search: str | None,
        offset: int,
        limit: int,
    ) -> dict[str, Any]:
        where, params = self._where(
            repo_id=repo_id,
            storage_kind=storage_kind,
            target_resolution_status=target_resolution_status,
            search=search,
            access_kind=access_kind,
        )
        select = """
            SELECT storage_access_id, repo_id, operation, operation_signature,
                   class_name, method_name, access_kind, operation_kind, write_kind,
                   mutation_kind, storage_kind, storage_target_expression,
                   target_resolution_level, target_resolution_status,
                   receiver_expression, receiver_declared_type, storage_method,
                   payload_expression, payload_role, writes_new_payload,
                   selected_fields_json, result_type, sql_preview, source_ref_json
            FROM observed_storage_access
        """
        with self._connect() as connection:
            total = int(connection.execute("SELECT count(*) FROM observed_storage_access" + where, params).fetchone()[0])
            rows = connection.execute(
                select + where + " ORDER BY repo_id, operation, storage_access_id LIMIT ? OFFSET ?",
                [*params, limit, offset],
            ).fetchall()
            columns = [item[0] for item in connection.description]
        items: list[dict[str, Any]] = []
        for row in rows:
            item = dict(zip(columns, row))
            item["selected_fields"] = self._json(item.pop("selected_fields_json"), [])
            item["source_ref"] = self._json(item.pop("source_ref_json"), {})
            items.append(item)
        return {"items": items, "total_count": total, "summary": self.summary()}

    def list_gaps(
        self,
        *,
        repo_id: str | None,
        gap_code: str | None,
        severity: str | None,
        search: str | None,
        offset: int,
        limit: int,
    ) -> dict[str, Any]:
        clauses: list[str] = []
        params: list[Any] = []
        if repo_id:
            clauses.append("s.repo_id = ?")
            params.append(repo_id)
        if gap_code:
            clauses.append("g.gap_code = ?")
            params.append(gap_code)
        if severity:
            clauses.append("g.severity = ?")
            params.append(severity)
        if search:
            token = f"%{search.casefold()}%"
            clauses.append("(lower(g.message) LIKE ? OR lower(g.owner_id) LIKE ? OR lower(g.gap_code) LIKE ?)")
            params.extend([token, token, token])
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        base = """
            FROM observed_storage_usage_gap g
            JOIN observed_storage_source s ON s.storage_usage_source_id=g.storage_usage_source_id
        """
        with self._connect() as connection:
            total = int(connection.execute("SELECT count(*) " + base + where, params).fetchone()[0])
            rows = connection.execute(
                """
                SELECT g.storage_usage_gap_id, s.repo_id, g.gap_code, g.severity,
                       g.owner_kind, g.owner_id, g.message, g.details_json,
                       g.source_refs_json
                """ + base + where +
                " ORDER BY s.repo_id, g.severity, g.gap_code, g.storage_usage_gap_id LIMIT ? OFFSET ?",
                [*params, limit, offset],
            ).fetchall()
            columns = [item[0] for item in connection.description]
        items: list[dict[str, Any]] = []
        for row in rows:
            item = dict(zip(columns, row))
            item["details"] = self._json(item.pop("details_json"), {})
            item["source_refs"] = self._json(item.pop("source_refs_json"), [])
            items.append(item)
        return {"items": items, "total_count": total, "summary": self.summary()}
