from __future__ import annotations

import importlib.util
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RuntimeSettings:
    runtime_root: Path
    database_path: Path
    jobs_root: Path
    default_analysis_output_root: Path
    max_concurrent_jobs: int = 1
    event_poll_interval_seconds: float = 0.15
    shutdown_grace_seconds: float = 5.0
    knowledge_api_base_url: str = "http://127.0.0.1:8080/api/knowledge/v1"
    knowledge_api_timeout_seconds: float = 30.0
    knowledge_api_proxy_enabled: bool = True
    runtime_log_path: Path | None = None
    runtime_log_level: str = "INFO"
    runtime_log_max_bytes: int = 10 * 1024 * 1024
    runtime_log_backup_count: int = 5
    one_shot_heartbeat_seconds: float = 30.0

    def __post_init__(self) -> None:
        if self.runtime_log_path is None:
            object.__setattr__(self, "runtime_log_path", self.runtime_root / "logs" / "knowledge-control-plane.log")

    @classmethod
    def from_environment(cls, *, base_dir: Path | None = None) -> "RuntimeSettings":
        base = (base_dir or Path.cwd()).expanduser().resolve()
        runtime_root = Path(os.getenv("KNOWLEDGE_CONTROL_PLANE_RUNTIME_ROOT", str(base / "runtime" / "control-plane"))).expanduser().resolve()
        analysis_root = Path(
            os.getenv("KNOWLEDGE_CONTROL_PLANE_ANALYSIS_OUTPUT_ROOT", str(base / "outputs" / "static-analysis"))
        ).expanduser().resolve()
        max_jobs = max(1, int(os.getenv("KNOWLEDGE_CONTROL_PLANE_MAX_CONCURRENT_JOBS", "1")))
        knowledge_api_base_url = os.getenv(
            "KNOWLEDGE_API_BASE_URL", "http://127.0.0.1:8080/api/knowledge/v1"
        ).rstrip("/")
        knowledge_api_timeout_seconds = max(
            1.0, float(os.getenv("KNOWLEDGE_API_TIMEOUT_SECONDS", "30"))
        )
        knowledge_api_proxy_enabled = os.getenv(
            "KNOWLEDGE_API_PROXY_ENABLED", "1"
        ).strip().lower() not in {"0", "false", "no", "off"}
        runtime_log_path = Path(
            os.getenv("KNOWLEDGE_CONTROL_PLANE_LOG_FILE", str(runtime_root / "logs" / "knowledge-control-plane.log"))
        ).expanduser().resolve()
        runtime_log_level = os.getenv("KNOWLEDGE_CONTROL_PLANE_LOG_LEVEL", "INFO").strip().upper() or "INFO"
        runtime_log_max_bytes = max(1_048_576, int(os.getenv("KNOWLEDGE_CONTROL_PLANE_LOG_MAX_BYTES", str(10 * 1024 * 1024))))
        runtime_log_backup_count = max(1, int(os.getenv("KNOWLEDGE_CONTROL_PLANE_LOG_BACKUP_COUNT", "5")))
        one_shot_heartbeat_seconds = max(1.0, float(os.getenv("KNOWLEDGE_CONTROL_PLANE_HEARTBEAT_SECONDS", "30")))
        return cls(
            runtime_root=runtime_root,
            database_path=runtime_root / "knowledge-control-plane.sqlite3",
            jobs_root=runtime_root / "jobs",
            default_analysis_output_root=analysis_root,
            max_concurrent_jobs=max_jobs,
            knowledge_api_base_url=knowledge_api_base_url,
            knowledge_api_timeout_seconds=knowledge_api_timeout_seconds,
            knowledge_api_proxy_enabled=knowledge_api_proxy_enabled,
            runtime_log_path=runtime_log_path,
            runtime_log_level=runtime_log_level,
            runtime_log_max_bytes=runtime_log_max_bytes,
            runtime_log_backup_count=runtime_log_backup_count,
            one_shot_heartbeat_seconds=one_shot_heartbeat_seconds,
        )

    @property
    def producer_artifact_root(self) -> Path:
        return self.runtime_root / "producer-artifacts"

    def job_run_log_path(self, job_id: str) -> Path:
        return self.runtime_root / "logs" / "jobs" / job_id / "run.log"

    def ensure_directories(self) -> None:
        for path in (
            self.runtime_root,
            self.jobs_root,
            self.producer_artifact_root,
            self.default_analysis_output_root,
            self.runtime_log_path.parent,
        ):
            path.mkdir(parents=True, exist_ok=True)
