from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class KnowledgeStore:
    """SQLite persistence for canonical systems and immutable revisions."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=30.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode = WAL;
                CREATE TABLE IF NOT EXISTS systems (
                    system_id TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    description TEXT,
                    metadata_json TEXT NOT NULL,
                    active_revision_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS revisions (
                    revision_id TEXT PRIMARY KEY,
                    system_id TEXT NOT NULL REFERENCES systems(system_id) ON DELETE CASCADE,
                    base_revision_id TEXT,
                    ordinal INTEGER NOT NULL,
                    state TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    execution_json TEXT NOT NULL,
                    execution_result_json TEXT NOT NULL,
                    knowledge_artifacts_json TEXT NOT NULL,
                    capabilities_json TEXT NOT NULL,
                    labels_json TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    UNIQUE(system_id, ordinal)
                );
                CREATE INDEX IF NOT EXISTS revisions_system_idx
                    ON revisions(system_id, ordinal DESC);
                """
            )
            revision_columns = {
                str(row[1]) for row in connection.execute("PRAGMA table_info(revisions)").fetchall()
            }
            required = {
                "base_revision_id", "execution_json", "execution_result_json",
                "knowledge_artifacts_json", "capabilities_json"
            }
            if not required.issubset(revision_columns):
                raise RuntimeError(
                    "Knowledge API catalog schema is incompatible; create a new 0.30.11+ catalog"
                )

    def create_system(
        self,
        *,
        system_id: str,
        display_name: str,
        description: str | None,
        metadata: dict[str, Any],
        created_at: datetime,
    ) -> bool:
        timestamp = created_at.isoformat()
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO systems(
                        system_id, display_name, description, metadata_json,
                        active_revision_id, created_at, updated_at
                    ) VALUES(?, ?, ?, ?, NULL, ?, ?)
                    """,
                    (
                        system_id,
                        display_name,
                        description,
                        _dump(metadata),
                        timestamp,
                        timestamp,
                    ),
                )
        except sqlite3.IntegrityError:
            return False
        return True

    def list_systems(self, *, search: str | None = None) -> list[dict[str, Any]]:
        sql = """
            SELECT s.*, COUNT(r.revision_id) AS revision_count
            FROM systems s
            LEFT JOIN revisions r ON r.system_id = s.system_id
        """
        params: tuple[Any, ...] = ()
        if search:
            sql += " WHERE lower(s.system_id) LIKE ? OR lower(s.display_name) LIKE ? OR lower(COALESCE(s.description, '')) LIKE ?"
            token = f"%{search.casefold()}%"
            params = (token, token, token)
        sql += " GROUP BY s.system_id ORDER BY s.updated_at DESC, s.system_id"
        with self._connect() as connection:
            rows = connection.execute(sql, params).fetchall()
        return [self._system_row(row) for row in rows]

    def get_system(self, system_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT s.*, COUNT(r.revision_id) AS revision_count
                FROM systems s
                LEFT JOIN revisions r ON r.system_id = s.system_id
                WHERE s.system_id = ?
                GROUP BY s.system_id
                """,
                (system_id,),
            ).fetchone()
        return None if row is None else self._system_row(row)

    def update_system(
        self,
        system_id: str,
        *,
        display_name_set: bool,
        display_name: str | None,
        description_set: bool,
        description: str | None,
        metadata_patch: dict[str, Any],
        updated_at: datetime,
    ) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT display_name, description, metadata_json FROM systems WHERE system_id = ?",
                (system_id,),
            ).fetchone()
            if row is None:
                return False
            metadata = _load(row["metadata_json"], {})
            for key, value in metadata_patch.items():
                if value is None:
                    metadata.pop(key, None)
                else:
                    metadata[key] = value
            next_display_name = display_name if display_name_set else row["display_name"]
            next_description = description if description_set else row["description"]
            connection.execute(
                """
                UPDATE systems
                SET display_name = ?, description = ?, metadata_json = ?, updated_at = ?
                WHERE system_id = ?
                """,
                (next_display_name, next_description, _dump(metadata), updated_at.isoformat(), system_id),
            )
        return True

    def delete_system(self, system_id: str) -> int | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS revision_count FROM revisions WHERE system_id = ?",
                (system_id,),
            ).fetchone()
            exists = connection.execute(
                "SELECT 1 FROM systems WHERE system_id = ?",
                (system_id,),
            ).fetchone()
            if exists is None:
                return None
            revision_count = int(row["revision_count"]) if row is not None else 0
            connection.execute("DELETE FROM systems WHERE system_id = ?", (system_id,))
        return revision_count

    def next_ordinal(self, system_id: str) -> int:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COALESCE(MAX(ordinal), 0) + 1 FROM revisions WHERE system_id = ?",
                (system_id,),
            ).fetchone()
        return int(row[0])

    def publish_revision(
        self,
        *,
        revision_id: str,
        system_id: str,
        ordinal: int,
        base_revision_id: str | None,
        execution: dict[str, Any],
        execution_result: dict[str, Any],
        knowledge_artifacts: list[dict[str, Any]],
        capabilities: list[str],
        labels: list[str],
        metadata: dict[str, Any],
        activate: bool,
        created_at: datetime,
    ) -> dict[str, Any]:
        existing = self.get_revision(system_id, revision_id)
        if existing is not None:
            return existing

        timestamp = created_at.isoformat()
        with self._connect() as connection:
            system = connection.execute(
                "SELECT active_revision_id FROM systems WHERE system_id = ?", (system_id,)
            ).fetchone()
            if system is None:
                raise KeyError(system_id)

            state = "active" if activate else "inactive"
            if activate:
                connection.execute(
                    "UPDATE revisions SET state = 'superseded' WHERE system_id = ? AND state = 'active'",
                    (system_id,),
                )
            connection.execute(
                """
                INSERT INTO revisions(
                    revision_id, system_id, base_revision_id, ordinal, state, created_at,
                    execution_json, execution_result_json, knowledge_artifacts_json,
                    capabilities_json, labels_json, metadata_json
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    revision_id,
                    system_id,
                    base_revision_id,
                    ordinal,
                    state,
                    timestamp,
                    _dump(execution),
                    _dump(execution_result),
                    _dump(knowledge_artifacts),
                    _dump(capabilities),
                    _dump(labels),
                    _dump(metadata),
                ),
            )
            active_revision_id = revision_id if activate else system["active_revision_id"]
            connection.execute(
                "UPDATE systems SET active_revision_id = ?, updated_at = ? WHERE system_id = ?",
                (active_revision_id, timestamp, system_id),
            )
        result = self.get_revision(system_id, revision_id)
        assert result is not None
        return result

    def activate_revision(self, system_id: str, revision_id: str, *, activated_at: datetime) -> None:
        timestamp = activated_at.isoformat()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT revision_id FROM revisions WHERE system_id = ? AND revision_id = ?",
                (system_id, revision_id),
            ).fetchone()
            if row is None:
                raise KeyError(revision_id)
            connection.execute(
                "UPDATE revisions SET state = 'superseded' WHERE system_id = ? AND state = 'active'",
                (system_id,),
            )
            connection.execute(
                "UPDATE revisions SET state = 'active' WHERE revision_id = ?",
                (revision_id,),
            )
            connection.execute(
                "UPDATE systems SET active_revision_id = ?, updated_at = ? WHERE system_id = ?",
                (revision_id, timestamp, system_id),
            )

    def list_revisions(self, system_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM revisions WHERE system_id = ? ORDER BY ordinal DESC",
                (system_id,),
            ).fetchall()
        return [self._revision_row(row) for row in rows]

    def list_all_revisions(self) -> list[dict[str, Any]]:
        """Return every retained immutable revision in the AISL Catalog."""
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM revisions ORDER BY system_id, ordinal"
            ).fetchall()
        return [self._revision_row(row) for row in rows]

    def get_revision(self, system_id: str, revision_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM revisions WHERE system_id = ? AND revision_id = ?",
                (system_id, revision_id),
            ).fetchone()
        return None if row is None else self._revision_row(row)

    def active_revision(self, system_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT r.* FROM systems s
                JOIN revisions r ON r.revision_id = s.active_revision_id
                WHERE s.system_id = ?
                """,
                (system_id,),
            ).fetchone()
        return None if row is None else self._revision_row(row)

    @staticmethod
    def _system_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "system_id": str(row["system_id"]),
            "display_name": str(row["display_name"]),
            "description": row["description"],
            "metadata": _load(row["metadata_json"], {}),
            "active_revision_id": row["active_revision_id"],
            "revision_count": int(row["revision_count"]),
            "created_at": datetime.fromisoformat(str(row["created_at"])),
            "updated_at": datetime.fromisoformat(str(row["updated_at"])),
        }

    @staticmethod
    def _revision_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "revision_id": str(row["revision_id"]),
            "system_id": str(row["system_id"]),
            "base_revision_id": None if row["base_revision_id"] is None else str(row["base_revision_id"]),
            "ordinal": int(row["ordinal"]),
            "state": str(row["state"]),
            "created_at": datetime.fromisoformat(str(row["created_at"])),
            "execution": _load(row["execution_json"], {}),
            "execution_result": _load(row["execution_result_json"], {}),
            "knowledge_artifacts": _load(row["knowledge_artifacts_json"], []),
            "capabilities": _load(row["capabilities_json"], []),
            "labels": _load(row["labels_json"], []),
            "metadata": _load(row["metadata_json"], {}),
        }


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _load(value: str, default: Any) -> Any:
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default
