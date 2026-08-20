from __future__ import annotations

import json
import logging
from logging.handlers import RotatingFileHandler
from contextvars import ContextVar
from pathlib import Path
from typing import Any

from .security import environment_secret_values, redact_text
from .settings import RuntimeSettings

_REQUEST_ID: ContextVar[str | None] = ContextVar("knowledge_control_plane_request_id", default=None)
_SENSITIVE_PARTS = (
    "authorization",
    "credential",
    "password",
    "secret",
    "token",
    "private_key",
    "client_key",
)
_MAX_TEXT = 4000


def set_request_id(value: str | None):
    return _REQUEST_ID.set(value)


def reset_request_id(token) -> None:
    _REQUEST_ID.reset(token)


def get_request_id() -> str | None:
    return _REQUEST_ID.get()


def _truncate(value: str, limit: int = _MAX_TEXT) -> str:
    if len(value) <= limit:
        return value
    return value[:limit] + f"… <truncated {len(value) - limit} chars>"


def _safe_text(value: str, limit: int = _MAX_TEXT) -> str:
    return redact_text(_truncate(value, limit), secrets=environment_secret_values())


def sanitize_for_log(value: Any, *, key: str | None = None) -> Any:
    """Return a JSON-safe, bounded value without known secret fields."""
    if key and any(part in key.lower() for part in _SENSITIVE_PARTS):
        return "<redacted>"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, str):
        return _safe_text(value)
    if isinstance(value, dict):
        return {
            str(item_key): sanitize_for_log(item_value, key=str(item_key))
            for item_key, item_value in list(value.items())[:100]
        }
    if isinstance(value, (list, tuple, set)):
        return [sanitize_for_log(item) for item in list(value)[:100]]
    try:
        return sanitize_for_log(value.model_dump(mode="json"))
    except Exception:
        return _safe_text(repr(value), 1000)


def safe_reason(exc: BaseException) -> str:
    text = str(exc).strip() or exc.__class__.__name__
    return _safe_text(text)


class RequestContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id() or "-"
        return True


def configure_runtime_logging(settings: RuntimeSettings) -> Path:
    """Configure one rotating runtime file log without disturbing host handlers."""
    path = settings.runtime_log_path
    path.parent.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger("knowledge_control_plane")
    root.setLevel(getattr(logging, settings.runtime_log_level.upper(), logging.INFO))

    resolved = str(path.resolve())
    for handler in list(root.handlers):
        managed_path = getattr(handler, "_knowledge_control_plane_runtime_path", None)
        if managed_path == resolved:
            return path
        if managed_path is not None:
            root.removeHandler(handler)
            handler.close()

    handler = RotatingFileHandler(
        path,
        maxBytes=settings.runtime_log_max_bytes,
        backupCount=settings.runtime_log_backup_count,
        encoding="utf-8",
    )
    handler._knowledge_control_plane_runtime_path = resolved  # type: ignore[attr-defined]
    handler.addFilter(RequestContextFilter())
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s request_id=%(request_id)s "
            "logger=%(name)s %(message)s"
        )
    )
    root.addHandler(handler)
    return path



def append_job_run_log(settings: RuntimeSettings, job_id: str, entry: Any) -> Path:
    """Append one canonical job-log entry to the per-job human-readable mirror."""
    path = settings.job_run_log_path(job_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    stage = f"[{entry.stage}] " if getattr(entry, "stage", None) else ""
    stream = getattr(getattr(entry, "stream", None), "value", str(getattr(entry, "stream", "system")))
    level = getattr(getattr(entry, "level", None), "value", str(getattr(entry, "level", "info"))).upper()
    timestamp = entry.timestamp.isoformat() if getattr(entry, "timestamp", None) is not None else "-"
    message = sanitize_for_log(getattr(entry, "message", ""))
    line = f"{timestamp} {level:7s} stream={stream} {stage}{message}\n"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line)
    return path


def log_details(details: dict[str, Any] | None) -> str:
    return json.dumps(sanitize_for_log(details or {}), ensure_ascii=False, sort_keys=True)
