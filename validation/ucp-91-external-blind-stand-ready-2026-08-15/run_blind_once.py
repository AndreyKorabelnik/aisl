#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

EXPECTED_REVISION = "rev-828b3d5897d6bf2f09d6b0c4"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def safe_endpoint(value: str) -> str:
    try:
        parts = urlsplit(value)
        host = parts.hostname or ""
        if parts.port:
            host += f":{parts.port}"
        return urlunsplit((parts.scheme, host, parts.path, "", ""))
    except Exception:
        return "configured"


def wait_tcp(host: str, port: int, process: subprocess.Popen[str], timeout: float) -> None:
    deadline = time.monotonic() + timeout
    last_error = ""
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Knowledge API exited before readiness with code {process.returncode}")
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return
        except OSError as exc:
            last_error = str(exc)
            time.sleep(0.2)
    raise RuntimeError(f"Knowledge API did not become reachable on {host}:{port}: {last_error}")


def run_capture(args: list[str], *, cwd: Path, env: dict[str, str], stdout_path: Path, stderr_path: Path) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(args, cwd=cwd, env=env, text=True, capture_output=True)
    stdout_path.write_text(proc.stdout or "", encoding="utf-8")
    stderr_path.write_text(proc.stderr or "", encoding="utf-8")
    if proc.returncode != 0:
        raise RuntimeError(f"command failed ({proc.returncode}): {' '.join(args)}; see {stderr_path}")
    return proc


def main() -> int:
    parser = argparse.ArgumentParser(
        description="One-shot Gold-isolated UCP 91 blind run: publish -> serve -> external LLM agent -> freeze -> bundle."
    )
    parser.add_argument("--endpoint", default=os.getenv("LLM_BASE_URL") or os.getenv("LLM_ENDPOINT"))
    parser.add_argument("--model", default=os.getenv("LLM_MODEL") or os.getenv("LLM_DEFAULT_MODEL"))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18081)
    parser.add_argument("--batch-size", type=int, default=10)
    parser.add_argument("--max-turns", type=int, default=30)
    parser.add_argument("--llm-timeout", type=int, default=300)
    parser.add_argument("--tool-timeout", type=int, default=60)
    parser.add_argument("--api-ready-timeout", type=float, default=30.0)
    parser.add_argument("--run-dir", type=Path)
    args = parser.parse_args()

    if not args.endpoint:
        raise SystemExit("LLM endpoint is required: --endpoint, LLM_BASE_URL or LLM_ENDPOINT")
    if not args.model:
        raise SystemExit("LLM model is required: --model, LLM_MODEL or LLM_DEFAULT_MODEL")
    if bool(os.getenv("LLM_CERT_FILE")) ^ bool(os.getenv("LLM_KEY_FILE")):
        raise SystemExit("Both LLM_CERT_FILE and LLM_KEY_FILE are required for mTLS")
    for env_name in ("LLM_CERT_FILE", "LLM_KEY_FILE", "LLM_CA_FILE"):
        value = os.getenv(env_name)
        if value and not Path(value).expanduser().is_file():
            raise SystemExit(f"{env_name} does not point to a readable file")

    root = Path(__file__).resolve().parents[1]
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = (args.run_dir or (root / "runs" / f"blind-{timestamp}")).expanduser().resolve()
    run_dir.mkdir(parents=True, exist_ok=False)
    traces = run_dir / "agent-traces"
    traces.mkdir(parents=True)
    result = run_dir / "agent-result.json"
    freeze_receipt = run_dir / "agent-result.freeze.json"
    api_log = run_dir / "knowledge-api.log"
    env = os.environ.copy()
    started = time.monotonic()
    stage_seconds: dict[str, float] = {}
    api_proc: subprocess.Popen[str] | None = None

    metadata: dict[str, object] = {
        "schema_version": "ucp-91-external-blind-run/v1",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "gold_available_to_run": False,
        "llm": {
            "endpoint": safe_endpoint(args.endpoint),
            "model": args.model,
            "api_key_configured": bool(os.getenv("LLM_API_KEY")),
            "mtls_configured": bool(os.getenv("LLM_CERT_FILE") and os.getenv("LLM_KEY_FILE")),
            "custom_ca_configured": bool(os.getenv("LLM_CA_FILE")),
        },
        "parameters": {
            "batch_size": args.batch_size,
            "max_turns": args.max_turns,
            "llm_timeout": args.llm_timeout,
            "tool_timeout": args.tool_timeout,
        },
    }

    try:
        t0 = time.monotonic()
        pub = run_capture(
            [sys.executable, "scripts/publish_revision.py", "--reset"],
            cwd=root,
            env=env,
            stdout_path=run_dir / "publication.stdout.json",
            stderr_path=run_dir / "publication.stderr.log",
        )
        stage_seconds["publication"] = round(time.monotonic() - t0, 3)
        publication = json.loads(pub.stdout)
        revision = str(publication.get("revision_id") or "")
        if revision != EXPECTED_REVISION:
            raise RuntimeError(f"unexpected published revision: {revision!r}")
        metadata["system_id"] = publication.get("system_id")
        metadata["revision_id"] = revision

        api_fh = api_log.open("w", encoding="utf-8")
        api_proc = subprocess.Popen(
            [sys.executable, "scripts/serve_api.py", "--host", args.host, "--port", str(args.port)],
            cwd=root,
            env=env,
            stdout=api_fh,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        t0 = time.monotonic()
        wait_tcp(args.host, args.port, api_proc, args.api_ready_timeout)
        stage_seconds["api_start"] = round(time.monotonic() - t0, 3)

        api_base = f"http://{args.host}:{args.port}"
        t0 = time.monotonic()
        run_capture(
            [
                sys.executable,
                "scripts/run_openai_compatible_agent.py",
                "--endpoint", args.endpoint,
                "--model", args.model,
                "--api-base", api_base,
                "--batch-size", str(args.batch_size),
                "--max-turns", str(args.max_turns),
                "--llm-timeout", str(args.llm_timeout),
                "--tool-timeout", str(args.tool_timeout),
                "--output", str(result),
                "--trace-dir", str(traces),
            ],
            cwd=root,
            env=env,
            stdout_path=run_dir / "agent.stdout.log",
            stderr_path=run_dir / "agent.stderr.log",
        )
        stage_seconds["agent"] = round(time.monotonic() - t0, 3)

        t0 = time.monotonic()
        freeze = run_capture(
            [sys.executable, "scripts/freeze_result.py", str(result), "--receipt", str(freeze_receipt)],
            cwd=root,
            env=env,
            stdout_path=run_dir / "freeze.stdout.json",
            stderr_path=run_dir / "freeze.stderr.log",
        )
        stage_seconds["freeze"] = round(time.monotonic() - t0, 3)
        receipt = json.loads(freeze.stdout)
        metadata["result_sha256"] = receipt.get("result_sha256")
        metadata["status_counts"] = receipt.get("status_counts")
        metadata["result_count"] = receipt.get("result_count")
        metadata["gold_accessed_by_validator"] = receipt.get("gold_accessed_by_validator")
        metadata["stage_seconds"] = stage_seconds
        metadata["completed_at"] = datetime.now(timezone.utc).isoformat()
        metadata["total_seconds"] = round(time.monotonic() - started, 3)
        metadata["status"] = "frozen"
        metadata_path = run_dir / "run-metadata.json"
        metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        result_sha = str(receipt["result_sha256"])
        bundle = run_dir.parent / f"ucp-91-frozen-result-{result_sha[:12]}.zip"
        if bundle.exists():
            bundle.unlink()
        include = [
            result,
            freeze_receipt,
            metadata_path,
            run_dir / "publication.stdout.json",
            run_dir / "publication.stderr.log",
            run_dir / "agent.stdout.log",
            run_dir / "agent.stderr.log",
            run_dir / "freeze.stdout.json",
            run_dir / "freeze.stderr.log",
            api_log,
        ] + sorted(traces.glob("*.json"))
        with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
            for path in include:
                if path.exists():
                    zf.write(path, arcname=path.relative_to(run_dir))
        bundle_sha = sha256(bundle)
        (run_dir / "frozen-bundle.sha256").write_text(f"{bundle_sha}  {bundle.name}\n", encoding="utf-8")
        print(json.dumps({
            "status": "frozen",
            "system_id": metadata.get("system_id"),
            "revision_id": revision,
            "result": str(result),
            "result_sha256": result_sha,
            "freeze_receipt": str(freeze_receipt),
            "bundle": str(bundle),
            "bundle_sha256": bundle_sha,
            "stage_seconds": stage_seconds,
            "total_seconds": metadata["total_seconds"],
        }, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        metadata["status"] = "failed"
        metadata["error"] = str(exc)
        metadata["stage_seconds"] = stage_seconds
        metadata["failed_at"] = datetime.now(timezone.utc).isoformat()
        metadata["total_seconds"] = round(time.monotonic() - started, 3)
        (run_dir / "run-metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        raise
    finally:
        if api_proc is not None and api_proc.poll() is None:
            try:
                os.killpg(api_proc.pid, signal.SIGTERM)
                api_proc.wait(timeout=10)
            except Exception:
                try:
                    os.killpg(api_proc.pid, signal.SIGKILL)
                except Exception:
                    pass


if __name__ == "__main__":
    raise SystemExit(main())
