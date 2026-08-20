from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from knowledge_control_plane.api.generic_v1.models import (
    ArtifactKind,
    ArtifactSummary,
    JobDetails,
    JobEvent,
    JobEventType,
    JobLogEntry,
    JobStatus,
    LogLevel,
    LogStream,
    KnowledgeProfileDefinition,
    ProductionRegistration,
    RepositorySummary,
    WorkspaceSummary,
)


def utc_now() -> datetime:
    return datetime.now(UTC)


class RuntimeStore:
    """Small durable SQLite store for orchestration metadata.

    SQLite stores only orchestration state, event cursors and artifact metadata.
    """

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._schema_lock = threading.RLock()
        self._initialize()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path, timeout=30, check_same_thread=False)
        try:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA synchronous = NORMAL")
            with connection:
                yield connection
        finally:
            connection.close()

    def quick_check(self) -> str:
        with self._connect() as connection:
            row = connection.execute("PRAGMA quick_check").fetchone()
        return str(row[0]) if row is not None else "no result"

    def _initialize(self) -> None:
        with self._schema_lock, self._connect() as connection:
            existing = {
                str(row[0])
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
                ).fetchall()
            }
            if existing and "runtime_metadata" not in existing:
                raise RuntimeError(
                    "legacy Knowledge Control Plane runtime database is not supported; start with a new runtime database"
                )
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS runtime_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS configuration (
                    id INTEGER PRIMARY KEY CHECK (id = 1), revision INTEGER NOT NULL,
                    payload_json TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS repositories (
                    repository_id TEXT PRIMARY KEY, payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS workspaces (
                    workspace_id TEXT PRIMARY KEY, revision INTEGER NOT NULL,
                    payload_json TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS knowledge_profiles (
                    profile_id TEXT PRIMARY KEY, payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS knowledge_profiles_updated_idx
                    ON knowledge_profiles(updated_at DESC, profile_id);
                CREATE TABLE IF NOT EXISTS productions (
                    production_id TEXT PRIMARY KEY, revision INTEGER NOT NULL,
                    payload_json TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS productions_updated_idx
                    ON productions(updated_at DESC, production_id);
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY, status TEXT NOT NULL, kind TEXT NOT NULL,
                    idempotency_key TEXT UNIQUE, request_json TEXT NOT NULL, details_json TEXT NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS jobs_status_created_idx ON jobs(status, created_at DESC);
                CREATE TABLE IF NOT EXISTS job_logs (
                    job_id TEXT NOT NULL REFERENCES jobs(job_id) ON DELETE CASCADE,
                    sequence INTEGER NOT NULL, timestamp TEXT NOT NULL, level TEXT NOT NULL,
                    stream TEXT NOT NULL, stage TEXT, message TEXT NOT NULL, PRIMARY KEY(job_id, sequence)
                );
                CREATE TABLE IF NOT EXISTS job_events (
                    job_id TEXT NOT NULL REFERENCES jobs(job_id) ON DELETE CASCADE,
                    sequence INTEGER NOT NULL, timestamp TEXT NOT NULL, event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL, PRIMARY KEY(job_id, sequence)
                );
                CREATE TABLE IF NOT EXISTS artifacts (
                    artifact_id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES jobs(job_id) ON DELETE CASCADE,
                    kind TEXT NOT NULL, name TEXT NOT NULL, media_type TEXT NOT NULL, absolute_path TEXT NOT NULL,
                    relative_path TEXT, size_bytes INTEGER NOT NULL, created_at TEXT NOT NULL,
                    content_available INTEGER NOT NULL, downloadable INTEGER NOT NULL, sha256 TEXT,
                    UNIQUE(job_id, absolute_path)
                );
                CREATE INDEX IF NOT EXISTS artifacts_job_idx ON artifacts(job_id, created_at);
                """
            )
            row = connection.execute(
                "SELECT value FROM runtime_metadata WHERE key = 'schema_version'"
            ).fetchone()
            if row is None:
                connection.execute(
                    "INSERT INTO runtime_metadata(key, value) VALUES('schema_version', '3')"
                )
            elif str(row[0]) != "3":
                raise RuntimeError(
                    f"unsupported Knowledge Control Plane runtime schema version: {row[0]}"
                )

    # Configuration -----------------------------------------------------
    def load_configuration(self) -> tuple[int, dict[str, Any]] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT revision, payload_json FROM configuration WHERE id = 1"
            ).fetchone()
        if row is None:
            return None
        return int(row["revision"]), json.loads(row["payload_json"])

    def save_configuration(self, revision: int, payload: dict[str, Any]) -> None:
        now = utc_now().isoformat()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO configuration(id, revision, payload_json, updated_at)
                VALUES(1, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    revision = excluded.revision,
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at
                """,
                (revision, json.dumps(payload, ensure_ascii=False, sort_keys=True), now),
            )

    # Repositories ------------------------------------------------------
    def upsert_repository(self, repository: RepositorySummary) -> None:
        now = utc_now().isoformat()
        payload = repository.model_dump_json()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO repositories(repository_id, payload_json, created_at, updated_at)
                VALUES(?, ?, ?, ?)
                ON CONFLICT(repository_id) DO UPDATE SET
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at
                """,
                (repository.repository_id, payload, now, now),
            )

    def list_repositories(self) -> list[RepositorySummary]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload_json FROM repositories ORDER BY updated_at DESC, repository_id"
            ).fetchall()
        return [RepositorySummary.model_validate_json(row["payload_json"]) for row in rows]

    def get_repository(self, repository_id: str) -> RepositorySummary | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM repositories WHERE repository_id = ?",
                (repository_id,),
            ).fetchone()
        return None if row is None else RepositorySummary.model_validate_json(row["payload_json"])

    # Workspaces --------------------------------------------------------
    def insert_workspace(self, workspace: WorkspaceSummary) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO workspaces(workspace_id, revision, payload_json, created_at, updated_at)
                VALUES(?, ?, ?, ?, ?)
                """,
                (
                    workspace.workspace_id,
                    workspace.revision,
                    workspace.model_dump_json(),
                    workspace.created_at.isoformat(),
                    workspace.updated_at.isoformat(),
                ),
            )

    def update_workspace(self, workspace: WorkspaceSummary) -> None:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE workspaces
                SET revision = ?, payload_json = ?, updated_at = ?
                WHERE workspace_id = ?
                """,
                (
                    workspace.revision,
                    workspace.model_dump_json(),
                    workspace.updated_at.isoformat(),
                    workspace.workspace_id,
                ),
            )
            if cursor.rowcount != 1:
                raise KeyError(workspace.workspace_id)

    def list_workspaces(self) -> list[WorkspaceSummary]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload_json FROM workspaces ORDER BY updated_at DESC, workspace_id"
            ).fetchall()
        return [WorkspaceSummary.model_validate_json(row["payload_json"]) for row in rows]

    def get_workspace(self, workspace_id: str) -> WorkspaceSummary | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM workspaces WHERE workspace_id = ?",
                (workspace_id,),
            ).fetchone()
        return None if row is None else WorkspaceSummary.model_validate_json(row["payload_json"])

    def delete_workspace(self, workspace_id: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM workspaces WHERE workspace_id = ?", (workspace_id,)
            )
        return cursor.rowcount == 1

    # Knowledge profiles ------------------------------------------------
    def upsert_knowledge_profile(self, profile: KnowledgeProfileDefinition) -> None:
        now = utc_now().isoformat()
        created = (profile.created_at or utc_now()).isoformat()
        updated = (profile.updated_at or utc_now()).isoformat()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO knowledge_profiles(profile_id, payload_json, created_at, updated_at)
                VALUES(?, ?, ?, ?)
                ON CONFLICT(profile_id) DO UPDATE SET
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at
                """,
                (profile.profile_id, profile.model_dump_json(), created, updated or now),
            )

    def list_knowledge_profiles(self) -> list[KnowledgeProfileDefinition]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload_json FROM knowledge_profiles ORDER BY updated_at DESC, profile_id"
            ).fetchall()
        return [KnowledgeProfileDefinition.model_validate_json(row["payload_json"]) for row in rows]

    def get_knowledge_profile(self, profile_id: str) -> KnowledgeProfileDefinition | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM knowledge_profiles WHERE profile_id = ?",
                (profile_id,),
            ).fetchone()
        return None if row is None else KnowledgeProfileDefinition.model_validate_json(row["payload_json"])

    def delete_knowledge_profile(self, profile_id: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM knowledge_profiles WHERE profile_id = ?", (profile_id,)
            )
        return cursor.rowcount == 1

    # Knowledge production registrations -------------------------------
    def insert_production(self, production: ProductionRegistration) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO productions(production_id, revision, payload_json, created_at, updated_at)
                VALUES(?, ?, ?, ?, ?)
                """,
                (
                    production.production_id,
                    production.revision,
                    production.model_dump_json(),
                    production.created_at.isoformat(),
                    production.updated_at.isoformat(),
                ),
            )

    def update_production(self, production: ProductionRegistration) -> None:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE productions SET revision = ?, payload_json = ?, updated_at = ?
                WHERE production_id = ?
                """,
                (
                    production.revision,
                    production.model_dump_json(),
                    production.updated_at.isoformat(),
                    production.production_id,
                ),
            )
            if cursor.rowcount != 1:
                raise KeyError(production.production_id)

    def get_production(self, production_id: str) -> ProductionRegistration | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM productions WHERE production_id = ?",
                (production_id,),
            ).fetchone()
        return None if row is None else ProductionRegistration.model_validate_json(row["payload_json"])

    def list_productions(self) -> list[ProductionRegistration]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload_json FROM productions ORDER BY updated_at DESC, production_id"
            ).fetchall()
        return [ProductionRegistration.model_validate_json(row["payload_json"]) for row in rows]

    def delete_production(self, production_id: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM productions WHERE production_id = ?", (production_id,)
            )
        return cursor.rowcount == 1

    # Jobs --------------------------------------------------------------
    def insert_job(
        self,
        job: JobDetails,
        *,
        request_json: str,
        idempotency_key: str | None,
    ) -> None:
        now = utc_now().isoformat()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO jobs(
                    job_id, status, kind, idempotency_key, request_json,
                    details_json, created_at, updated_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job.job_id,
                    job.status.value,
                    job.kind.value,
                    idempotency_key,
                    request_json,
                    job.model_dump_json(),
                    job.created_at.isoformat(),
                    now,
                ),
            )

    def update_job(self, job: JobDetails) -> None:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE jobs SET status = ?, details_json = ?, updated_at = ?
                WHERE job_id = ?
                """,
                (job.status.value, job.model_dump_json(), utc_now().isoformat(), job.job_id),
            )
            if cursor.rowcount != 1:
                raise KeyError(job.job_id)

    def get_job(self, job_id: str) -> JobDetails | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT details_json FROM jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
        return None if row is None else JobDetails.model_validate_json(row["details_json"])

    def get_job_request_json(self, job_id: str) -> str | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT request_json FROM jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
        return None if row is None else str(row["request_json"])

    def get_job_by_idempotency_key(self, key: str) -> JobDetails | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT details_json FROM jobs WHERE idempotency_key = ?", (key,)
            ).fetchone()
        return None if row is None else JobDetails.model_validate_json(row["details_json"])

    def list_jobs(self) -> list[JobDetails]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT details_json FROM jobs ORDER BY created_at DESC, job_id"
            ).fetchall()
        return [JobDetails.model_validate_json(row["details_json"]) for row in rows]

    def recover_incomplete_jobs(self) -> tuple[list[str], list[str]]:
        """Return queued runs to resume and in-flight runs to mark interrupted.

        Recovery is intentionally status-based and has no knowledge-family or legacy-pipeline semantics.
        """
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT job_id, status FROM jobs WHERE status IN (?, ?, ?) ORDER BY created_at, job_id",
                (JobStatus.QUEUED.value, JobStatus.PREPARING.value, JobStatus.RUNNING.value),
            ).fetchall()
        queued = [str(row["job_id"]) for row in rows if row["status"] == JobStatus.QUEUED.value]
        interrupted = [
            str(row["job_id"])
            for row in rows
            if row["status"] in {JobStatus.PREPARING.value, JobStatus.RUNNING.value}
        ]
        return queued, interrupted

    def delete_job(self, job_id: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute("DELETE FROM jobs WHERE job_id = ?", (job_id,))
        return cursor.rowcount == 1

    # Logs and events ---------------------------------------------------
    def append_log(
        self,
        job_id: str,
        *,
        level: LogLevel,
        stream: LogStream,
        message: str,
        stage: str | None,
    ) -> JobLogEntry:
        now = utc_now()
        with self._connect() as connection:
            sequence = int(
                connection.execute(
                    "SELECT COALESCE(MAX(sequence), 0) + 1 FROM job_logs WHERE job_id = ?",
                    (job_id,),
                ).fetchone()[0]
            )
            connection.execute(
                """
                INSERT INTO job_logs(job_id, sequence, timestamp, level, stream, stage, message)
                VALUES(?, ?, ?, ?, ?, ?, ?)
                """,
                (job_id, sequence, now.isoformat(), level.value, stream.value, stage, message),
            )
        return JobLogEntry(
            sequence=sequence,
            timestamp=now,
            level=level,
            stream=stream,
            stage=stage,
            message=message,
        )

    def list_logs(self, job_id: str, *, cursor: int, limit: int) -> list[JobLogEntry]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT sequence, timestamp, level, stream, stage, message
                FROM job_logs WHERE job_id = ? AND sequence >= ?
                ORDER BY sequence LIMIT ?
                """,
                (job_id, cursor, limit),
            ).fetchall()
        return [
            JobLogEntry(
                sequence=int(row["sequence"]),
                timestamp=datetime.fromisoformat(row["timestamp"]),
                level=LogLevel(row["level"]),
                stream=LogStream(row["stream"]),
                stage=row["stage"],
                message=row["message"],
            )
            for row in rows
        ]

    def list_logs_filtered(
        self,
        job_id: str,
        *,
        cursor: int,
        limit: int,
        level: LogLevel | None = None,
        stream: LogStream | None = None,
        stage: str | None = None,
        search: str | None = None,
    ) -> tuple[list[JobLogEntry], bool]:
        clauses = ["job_id = ?", "sequence >= ?"]
        parameters: list[Any] = [job_id, cursor]
        if level is not None:
            clauses.append("level = ?")
            parameters.append(level.value)
        if stream is not None:
            clauses.append("stream = ?")
            parameters.append(stream.value)
        if stage is not None:
            clauses.append("stage = ?")
            parameters.append(stage)
        if search:
            clauses.append("LOWER(message) LIKE ?")
            parameters.append(f"%{search.casefold()}%")
        parameters.append(limit + 1)
        query = f"""
            SELECT sequence, timestamp, level, stream, stage, message
            FROM job_logs
            WHERE {' AND '.join(clauses)}
            ORDER BY sequence
            LIMIT ?
        """
        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        has_more = len(rows) > limit
        rows = rows[:limit]
        entries = [
            JobLogEntry(
                sequence=int(row["sequence"]),
                timestamp=datetime.fromisoformat(row["timestamp"]),
                level=LogLevel(row["level"]),
                stream=LogStream(row["stream"]),
                stage=row["stage"],
                message=row["message"],
            )
            for row in rows
        ]
        return entries, has_more

    def append_event(
        self,
        job_id: str,
        *,
        event_type: JobEventType,
        payload: dict[str, Any],
    ) -> JobEvent:
        now = utc_now()
        with self._connect() as connection:
            sequence = int(
                connection.execute(
                    "SELECT COALESCE(MAX(sequence), 0) + 1 FROM job_events WHERE job_id = ?",
                    (job_id,),
                ).fetchone()[0]
            )
            connection.execute(
                """
                INSERT INTO job_events(job_id, sequence, timestamp, event_type, payload_json)
                VALUES(?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    sequence,
                    now.isoformat(),
                    event_type.value,
                    json.dumps(payload, ensure_ascii=False, sort_keys=True),
                ),
            )
        return JobEvent(
            sequence=sequence,
            timestamp=now,
            event_type=event_type,
            job_id=job_id,
            payload=payload,
        )

    def list_events(self, job_id: str, *, after: int, limit: int = 1000) -> list[JobEvent]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT sequence, timestamp, event_type, payload_json
                FROM job_events WHERE job_id = ? AND sequence > ?
                ORDER BY sequence LIMIT ?
                """,
                (job_id, after, limit),
            ).fetchall()
        return [
            JobEvent(
                sequence=int(row["sequence"]),
                timestamp=datetime.fromisoformat(row["timestamp"]),
                event_type=JobEventType(row["event_type"]),
                job_id=job_id,
                payload=json.loads(row["payload_json"]),
            )
            for row in rows
        ]

    # Artifacts ---------------------------------------------------------
    def upsert_artifact(self, summary: ArtifactSummary, absolute_path: Path) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO artifacts(
                    artifact_id, job_id, kind, name, media_type, absolute_path,
                    relative_path, size_bytes, created_at, content_available,
                    downloadable, sha256
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_id, absolute_path) DO UPDATE SET
                    artifact_id = excluded.artifact_id,
                    kind = excluded.kind,
                    name = excluded.name,
                    media_type = excluded.media_type,
                    relative_path = excluded.relative_path,
                    size_bytes = excluded.size_bytes,
                    content_available = excluded.content_available,
                    downloadable = excluded.downloadable,
                    sha256 = excluded.sha256
                """,
                (
                    summary.artifact_id,
                    summary.job_id,
                    summary.kind.value,
                    summary.name,
                    summary.media_type,
                    str(absolute_path),
                    summary.relative_path,
                    summary.size_bytes,
                    summary.created_at.isoformat(),
                    int(summary.content_available),
                    int(summary.downloadable),
                    summary.sha256,
                ),
            )

    def _artifact_from_row(self, row: sqlite3.Row) -> ArtifactSummary:
        return ArtifactSummary(
            artifact_id=row["artifact_id"],
            job_id=row["job_id"],
            kind=ArtifactKind(row["kind"]),
            name=row["name"],
            media_type=row["media_type"],
            size_bytes=int(row["size_bytes"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            relative_path=row["relative_path"],
            content_available=bool(row["content_available"]),
            downloadable=bool(row["downloadable"]),
            sha256=row["sha256"],
        )

    def list_artifacts(self, job_id: str) -> list[ArtifactSummary]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM artifacts WHERE job_id = ? ORDER BY created_at, artifact_id",
                (job_id,),
            ).fetchall()
        return [self._artifact_from_row(row) for row in rows]

    def get_artifact(self, artifact_id: str) -> tuple[ArtifactSummary, Path] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM artifacts WHERE artifact_id = ?", (artifact_id,)
            ).fetchone()
        if row is None:
            return None
        return self._artifact_from_row(row), Path(row["absolute_path"])

