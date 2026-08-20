from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

from .contracts import ReportRequest
from .files import write_json
from .pipeline import build_report, prepare_report, write_prepared_report
from .profile import SUPPORTED_PROFILE_IDS, load_profile
from .renderer import FileRenderer, ModelRenderer, Renderer

SERVICE_SCHEMA = "aisl_reporting_service/v1"
RUN_SCHEMA = "aisl_report_service_run/v1"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _required(value: Any, name: str) -> str:
    result = str(value or "").strip()
    if not result:
        raise ValueError(f"{name} must not be empty")
    return result


def _default_audience(profile_id: str) -> str:
    report_type = profile_id.split("/", 1)[0]
    return "business" if report_type in {"system-description", "sql-source-inventory-report"} else "architecture"


@dataclass(frozen=True, slots=True)
class ReportingServiceConfig:
    api_url: str
    runs_root: Path
    response_file: Path | None = None
    llm_endpoint: str | None = None
    llm_model: str = "default"
    llm_timeout_sec: int = 600
    llm_cert_file: Path | None = None
    llm_key_file: Path | None = None
    llm_ca_file: Path | None = None
    llm_verify_tls: bool | None = None
    llm_http2: bool | None = None

    @property
    def renderer_kind(self) -> str | None:
        if self.response_file is not None:
            return "file"
        if str(self.llm_endpoint or os.getenv("LLM_BASE_URL") or "").strip():
            return "model"
        return None


class ReportService:
    def __init__(self, config: ReportingServiceConfig, *, api_transport: Any = None) -> None:
        self.config = config
        self.api_transport = api_transport
        self.config.runs_root.mkdir(parents=True, exist_ok=True)

    def health(self) -> dict[str, Any]:
        return {
            "schema_version": SERVICE_SCHEMA,
            "status": "ok",
            "knowledge_api_url": self.config.api_url,
            "renderer_kind": self.config.renderer_kind,
            "rendering_available": self.config.renderer_kind is not None,
        }

    def profiles(self) -> dict[str, Any]:
        return {"schema_version": SERVICE_SCHEMA, "items": list(SUPPORTED_PROFILE_IDS)}

    def _renderer(self) -> Renderer:
        if self.config.response_file is not None:
            return FileRenderer(self.config.response_file)
        if self.config.renderer_kind == "model":
            return ModelRenderer(
                endpoint=self.config.llm_endpoint,
                model=self.config.llm_model,
                timeout_sec=self.config.llm_timeout_sec,
                cert_file=self.config.llm_cert_file,
                key_file=self.config.llm_key_file,
                ca_file=self.config.llm_ca_file,
                verify_tls=self.config.llm_verify_tls,
                http2=self.config.llm_http2,
            )
        raise ValueError("rendering is not configured; use mode=prepare or configure a server-side renderer")

    def _request(self, payload: dict[str, Any]) -> tuple[ReportRequest, str]:
        profile_id = _required(payload.get("profile"), "profile")
        if profile_id not in SUPPORTED_PROFILE_IDS:
            raise ValueError(f"unsupported report profile: {profile_id}")
        load_profile(profile_id)  # validates package/resource availability
        report_type, version = profile_id.split("/", 1)
        system_id = _required(payload.get("system_id"), "system_id")
        # Service contract intentionally requires a concrete immutable revision.
        revision_id = _required(payload.get("revision_id"), "revision_id")
        mode = str(payload.get("mode") or "prepare").strip().lower()
        if mode not in {"prepare", "build"}:
            raise ValueError("mode must be prepare or build")
        audience = str(payload.get("audience") or _default_audience(profile_id))
        detail_level = str(payload.get("detail_level") or "standard")
        focus = tuple(str(v).strip() for v in (payload.get("focus") or []) if str(v).strip())
        request = ReportRequest(
            report_type=report_type,
            report_version=version,
            api_url=self.config.api_url,
            system_id=system_id,
            revision_id=revision_id,
            audience=audience,  # type: ignore[arg-type]
            detail_level=detail_level,  # type: ignore[arg-type]
            focus=focus,
            output_name="report.md",
            api_transport=self.api_transport,
        )
        return request, mode

    def create_run(self, payload: dict[str, Any]) -> dict[str, Any]:
        request, mode = self._request(payload)
        run_id = "report-" + uuid4().hex
        run_dir = self.config.runs_root / run_id
        run_dir.mkdir(parents=True, exist_ok=False)
        created_at = _now()
        service_manifest_path = run_dir / "service-run.json"
        try:
            if mode == "prepare":
                manifest = write_prepared_report(prepare_report(request), run_dir)
            else:
                manifest = build_report(request, run_dir, self._renderer(), heartbeat_sec=0)
            result = {
                "schema_version": RUN_SCHEMA,
                "run_id": run_id,
                "status": manifest.status,
                "mode": mode,
                "created_at": created_at,
                "source": {
                    "system_id": request.system_id,
                    "revision_id": manifest.request.revision_id,
                    "profile": request.profile_id,
                },
                "dataset_sha256": manifest.dataset_sha256,
                "report_sha256": manifest.report_sha256,
                "has_report": manifest.report_path is not None and manifest.report_path.is_file(),
                "warnings": list(manifest.warnings),
                "validation": dict(manifest.validation),
            }
        except Exception as exc:
            result = {
                "schema_version": RUN_SCHEMA,
                "run_id": run_id,
                "status": "failed",
                "mode": mode,
                "created_at": created_at,
                "source": {"system_id": request.system_id, "revision_id": request.revision_id, "profile": request.profile_id},
                "error": {"type": type(exc).__name__, "message": str(exc)},
                "has_report": False,
            }
            write_json(service_manifest_path, result)
            raise ReportRunFailed(result) from exc
        write_json(service_manifest_path, result)
        return result

    def _run_path(self, run_id: str) -> Path:
        rid = _required(run_id, "run_id")
        if not rid.startswith("report-") or any(c not in "0123456789abcdef" for c in rid.removeprefix("report-")):
            raise KeyError(run_id)
        path = self.config.runs_root / rid
        if not path.is_dir():
            raise KeyError(run_id)
        return path

    def get_run(self, run_id: str) -> dict[str, Any]:
        path = self._run_path(run_id) / "service-run.json"
        if not path.is_file():
            raise KeyError(run_id)
        return json.loads(path.read_text(encoding="utf-8"))

    def list_runs(self) -> dict[str, Any]:
        items = []
        for path in sorted(self.config.runs_root.glob("report-*/service-run.json"), reverse=True):
            try:
                items.append(json.loads(path.read_text(encoding="utf-8")))
            except Exception:
                continue
        return {"schema_version": SERVICE_SCHEMA, "items": items}

    def content(self, run_id: str, kind: str) -> tuple[str, str]:
        run_dir = self._run_path(run_id)
        if kind == "report":
            path, media = run_dir / "report.md", "text/markdown; charset=utf-8"
        elif kind == "dataset":
            path, media = run_dir / "report-dataset.json", "application/json; charset=utf-8"
        else:
            raise KeyError(kind)
        if not path.is_file():
            raise KeyError(f"{run_id}/{kind}")
        return path.read_text(encoding="utf-8"), media


class ReportRunFailed(RuntimeError):
    def __init__(self, result: dict[str, Any]) -> None:
        self.result = result
        super().__init__(str((result.get("error") or {}).get("message") or "report run failed"))


def make_handler(service: ReportService):
    class Handler(BaseHTTPRequestHandler):
        server_version = "aisl-reporting/0.4"

        def log_message(self, format: str, *args: Any) -> None:
            return

        def _json(self, status: int, payload: Any) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("content-type", "application/json; charset=utf-8")
            self.send_header("content-length", str(len(body)))
            self.end_headers(); self.wfile.write(body)

        def do_GET(self) -> None:
            path = urlsplit(self.path).path
            if path == "/healthz": return self._json(200, service.health())
            if path == "/api/reporting/v1/health": return self._json(200, service.health())
            if path == "/api/reporting/v1/profiles": return self._json(200, service.profiles())
            if path == "/api/reporting/v1/runs": return self._json(200, service.list_runs())
            parts = [p for p in path.split("/") if p]
            if len(parts) >= 5 and parts[:3] == ["api", "reporting", "v1"] and parts[3] == "runs":
                run_id = parts[4]
                try:
                    if len(parts) == 5: return self._json(200, service.get_run(run_id))
                    if len(parts) == 6 and parts[5] in {"content", "dataset"}:
                        kind = "report" if parts[5] == "content" else "dataset"
                        body, media = service.content(run_id, kind)
                        data = body.encode("utf-8"); self.send_response(200); self.send_header("content-type", media); self.send_header("content-length",str(len(data))); self.end_headers(); self.wfile.write(data); return
                except KeyError:
                    return self._json(404, {"error":"report_run_not_found","run_id":run_id})
            return self._json(404, {"error":"not_found","path":path})

        def do_POST(self) -> None:
            path = urlsplit(self.path).path
            if path != "/api/reporting/v1/runs": return self._json(404,{"error":"not_found","path":path})
            try:
                length=int(self.headers.get("content-length") or 0)
                payload=json.loads(self.rfile.read(length) or b"{}")
                if not isinstance(payload,dict): raise ValueError("request body must be a JSON object")
                return self._json(201, service.create_run(payload))
            except ReportRunFailed as exc:
                return self._json(422, exc.result)
            except (ValueError, TypeError) as exc:
                return self._json(400,{"error":"invalid_request","message":str(exc)})

    return Handler


def serve(config: ReportingServiceConfig, *, host: str = "127.0.0.1", port: int = 18280) -> None:
    service = ReportService(config)
    server = ThreadingHTTPServer((host, port), make_handler(service))
    print(f"AISL Reporting http://{host}:{port} -> {config.api_url}; runs={config.runs_root}")
    server.serve_forever()
