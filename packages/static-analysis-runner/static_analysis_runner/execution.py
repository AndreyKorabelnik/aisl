from __future__ import annotations

import json
import os
import shlex
import codecs
import selectors
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping, Sequence


@dataclass(frozen=True)
class ProcessResult:
    command: tuple[str, ...]
    returncode: int
    log_path: Path
    pid: int | None = None
    started_at: str | None = None
    completed_at: str | None = None
    elapsed_seconds: float | None = None
    max_rss_kb: int | None = None
    runtime_diagnostics_path: Path | None = None
    stack_dump_requests: int = 0
    timed_out: bool = False


def command_parts(value: str) -> list[str]:
    parts = shlex.split(value)
    if not parts:
        raise ValueError("tool command must not be empty")
    return parts



def require_tool_command(value: str) -> tuple[str, ...]:
    """Validate the executable token of a configured tool command without touching outputs."""
    parts = tuple(command_parts(value))
    executable = parts[0]
    if "/" in executable:
        candidate = Path(executable).expanduser()
        if not candidate.is_file() or not os.access(candidate, os.X_OK):
            raise RuntimeError(
                f"tool executable not found or not executable: {executable!r}; command={display_command(parts)}"
            )
    elif shutil.which(executable) is None:
        raise RuntimeError(f"tool executable not found: {executable!r}; command={display_command(parts)}")
    return parts

def display_command(command: Sequence[str]) -> str:
    return shlex.join([str(item) for item in command])


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _process_rss_kb(pid: int) -> int | None:
    try:
        status = Path(f"/proc/{pid}/status").read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None
    for line in status.splitlines():
        if line.startswith("VmRSS:"):
            try:
                return int(line.split()[1])
            except (IndexError, ValueError):
                return None
    return None


def _read_progress(progress_path: Path | None) -> tuple[tuple[object, ...] | None, dict | None]:
    if progress_path is None or not progress_path.is_file():
        return None, None
    try:
        payload = json.loads(progress_path.read_text(encoding="utf-8"))
        stat = progress_path.stat()
    except Exception:
        return None, None
    latest = payload.get("latest_event") if isinstance(payload, dict) else None
    signature = (
        stat.st_mtime_ns,
        payload.get("events_count") if isinstance(payload, dict) else None,
        payload.get("phase") if isinstance(payload, dict) else None,
        payload.get("status") if isinstance(payload, dict) else None,
    )
    summary = {
        "updated_at": payload.get("updated_at"),
        "events_count": payload.get("events_count"),
        "phase": payload.get("phase"),
        "status": payload.get("status"),
        "latest_event_code": latest.get("event_code") if isinstance(latest, dict) else None,
    }
    return signature, summary


def _append_runtime_event(path: Path | None, payload: dict) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()


def run_process(
    command: Sequence[str],
    *,
    log_path: str | Path,
    cwd: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    echo: Callable[[str], None] | None = None,
    progress_path: str | Path | None = None,
    runtime_diagnostics_path: str | Path | None = None,
    stall_warning_seconds: float | None = None,
    stack_dump_seconds: float | None = None,
    heartbeat_interval_seconds: float = 5.0,
    timeout_seconds: float | None = None,
) -> ProcessResult:
    """Run and monitor a subprocess without owning its stdout pipe.

    Child output is written directly to the log file. The parent only polls the
    process and progress artifact, which avoids pipe/selector shutdown races on
    large one-shot core processes.
    """
    normalized = tuple(str(item) for item in command)
    target = Path(log_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    progress_target = Path(progress_path) if progress_path is not None else None
    runtime_target = Path(runtime_diagnostics_path) if runtime_diagnostics_path is not None else None
    merged_env = os.environ.copy()
    merged_env.setdefault("PYTHONUNBUFFERED", "1")
    merged_env.setdefault("PYTHONFAULTHANDLER", "1")
    if env:
        merged_env.update({str(key): str(value) for key, value in env.items()})
    started_at = _now_utc()
    started = time.monotonic()
    log_offset = 0

    with target.open("w", encoding="utf-8") as output_handle:
        try:
            process = subprocess.Popen(
                normalized,
                cwd=str(cwd) if cwd else None,
                env=merged_env,
                stdout=output_handle,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                start_new_session=True,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(
                f"tool executable not found: {normalized[0]!r}; command={display_command(normalized)}"
            ) from exc

        _append_runtime_event(runtime_target, {
            "ts": started_at,
            "event": "process_started",
            "pid": process.pid,
            "command": list(normalized),
        })
        max_rss_kb = 0
        last_signature: tuple[object, ...] | None = None
        last_progress_at = started
        last_output_mtime_ns = 0
        last_heartbeat = 0.0
        warning_signature: tuple[object, ...] | None = None
        dump_signature: tuple[object, ...] | None = None
        stack_dump_requests = 0
        timed_out = False
        terminate_requested_at: float | None = None
        heartbeat_interval_seconds = max(0.5, float(heartbeat_interval_seconds))

        while True:
            now = time.monotonic()
            rss_kb = _process_rss_kb(process.pid)
            if rss_kb is not None:
                max_rss_kb = max(max_rss_kb, rss_kb)
            signature, progress_summary = _read_progress(progress_target)
            if signature is not None and signature != last_signature:
                last_signature = signature
                last_progress_at = now
                warning_signature = None
                dump_signature = None
            try:
                stat = target.stat()
                if stat.st_mtime_ns != last_output_mtime_ns:
                    last_output_mtime_ns = stat.st_mtime_ns
                    last_progress_at = now
                    warning_signature = None
                    dump_signature = None
                if echo and stat.st_size > log_offset:
                    with target.open("r", encoding="utf-8", errors="replace") as reader:
                        reader.seek(log_offset)
                        text = reader.read()
                        log_offset = reader.tell()
                    for line in text.splitlines():
                        echo(line)
            except OSError:
                pass

            idle_seconds = max(0.0, now - last_progress_at)
            if now - last_heartbeat >= heartbeat_interval_seconds:
                _append_runtime_event(runtime_target, {
                    "ts": _now_utc(),
                    "event": "heartbeat",
                    "pid": process.pid,
                    "elapsed_seconds": round(now - started, 3),
                    "idle_seconds": round(idle_seconds, 3),
                    "rss_kb": rss_kb,
                    "max_rss_kb": max_rss_kb or None,
                    "progress": progress_summary,
                })
                last_heartbeat = now

            effective_signature = last_signature or ("no-progress-file",)
            if stall_warning_seconds and idle_seconds >= stall_warning_seconds and warning_signature != effective_signature:
                _append_runtime_event(runtime_target, {
                    "ts": _now_utc(), "event": "stall_warning", "pid": process.pid,
                    "elapsed_seconds": round(now - started, 3), "idle_seconds": round(idle_seconds, 3),
                    "rss_kb": rss_kb, "progress": progress_summary,
                })
                warning_signature = effective_signature
            if stack_dump_seconds and idle_seconds >= stack_dump_seconds and dump_signature != effective_signature and hasattr(signal, "SIGUSR1"):
                try:
                    os.killpg(process.pid, signal.SIGUSR1)
                    stack_dump_requests += 1
                    _append_runtime_event(runtime_target, {
                        "ts": _now_utc(), "event": "stack_dump_requested", "pid": process.pid,
                        "signal": "SIGUSR1", "elapsed_seconds": round(now - started, 3),
                        "idle_seconds": round(idle_seconds, 3), "progress": progress_summary,
                    })
                except ProcessLookupError:
                    pass
                dump_signature = effective_signature

            if timeout_seconds and now - started >= timeout_seconds and not timed_out:
                timed_out = True
                terminate_requested_at = now
                if hasattr(signal, "SIGUSR1"):
                    try:
                        os.killpg(process.pid, signal.SIGUSR1)
                        stack_dump_requests += 1
                    except ProcessLookupError:
                        pass
                _append_runtime_event(runtime_target, {
                    "ts": _now_utc(), "event": "process_timeout", "pid": process.pid,
                    "elapsed_seconds": round(now - started, 3), "timeout_seconds": timeout_seconds,
                    "progress": progress_summary,
                })
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            if timed_out and terminate_requested_at is not None and now - terminate_requested_at >= 5.0 and process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass

            returncode = process.poll()
            if returncode is not None:
                break
            time.sleep(min(0.5, heartbeat_interval_seconds))

        returncode = process.wait()

    if echo:
        try:
            with target.open("r", encoding="utf-8", errors="replace") as reader:
                reader.seek(log_offset)
                for line in reader.read().splitlines():
                    echo(line)
        except OSError:
            pass
    completed_at = _now_utc()
    elapsed_seconds = round(time.monotonic() - started, 3)
    _append_runtime_event(runtime_target, {
        "ts": completed_at,
        "event": "process_completed",
        "pid": process.pid,
        "returncode": returncode,
        "elapsed_seconds": elapsed_seconds,
        "max_rss_kb": max_rss_kb or None,
        "stack_dump_requests": stack_dump_requests,
        "timed_out": timed_out,
    })
    return ProcessResult(
        command=normalized,
        returncode=returncode,
        log_path=target,
        pid=process.pid,
        started_at=started_at,
        completed_at=completed_at,
        elapsed_seconds=elapsed_seconds,
        max_rss_kb=max_rss_kb or None,
        runtime_diagnostics_path=runtime_target,
        stack_dump_requests=stack_dump_requests,
        timed_out=timed_out,
    )


def python_module_command(module: str) -> str:
    return f"{shlex.quote(sys.executable)} -m {shlex.quote(module)}"
