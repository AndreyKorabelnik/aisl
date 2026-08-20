from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

import uvicorn

from knowledge_control_plane.api.generic_v1.models import JobStatus
from knowledge_control_plane.runtime.context import build_runtime_context
from knowledge_control_plane.runtime.errors import RuntimeApiError
from knowledge_control_plane.runtime.observability import configure_runtime_logging
from knowledge_control_plane.runtime.one_shot import (
    OneShotRunOptions,
    parse_knowledge_revision,
    parse_parameters,
    run_one_shot,
)
from knowledge_control_plane.runtime.repository_batch_run import (
    RepositoryBatchScenarioOptions,
    run_repository_batch_scenario,
)
from knowledge_control_plane.runtime.settings import RuntimeSettings


def _doctor(*, as_json: bool) -> int:
    context = build_runtime_context(RuntimeSettings.from_environment())
    report = context.diagnostics.system()
    if as_json:
        print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))
    else:
        print(f"knowledge-control-plane {report.application_version}: {report.overall_status.value}")
        for check in report.checks:
            marker = {"pass": "OK", "warning": "WARN", "fail": "FAIL"}[check.status.value]
            print(f"[{marker}] {check.check_id}: {check.summary}")
            if check.detail:
                print(f"       {check.detail}")
            if check.remediation:
                print(f"       remediation: {check.remediation}")
    return 1 if report.overall_status.value == "fail" else 0


def _run(args: argparse.Namespace) -> int:
    try:
        revisions = tuple(parse_knowledge_revision(value) for value in args.knowledge_revision)
        parameters = parse_parameters(args.parameter)
        settings = RuntimeSettings.from_environment()
        configure_runtime_logging(settings)
        context = build_runtime_context(settings)

        if getattr(args, "bitbucket_project_url", None):
            if args.repository:
                raise ValueError("--bitbucket-project-url and --repository are mutually exclusive")
            if getattr(args, "system_id", None):
                raise ValueError("--system-id is not used for repository batch execution; each repository keeps its own identity")
            if revisions:
                raise ValueError("--knowledge-revision is not accepted with --bitbucket-project-url")
            if args.physical_model:
                raise ValueError("--physical-model is not accepted with --bitbucket-project-url")
            if args.display_name:
                raise ValueError("--display-name is not accepted with --bitbucket-project-url")
            if parameters:
                raise ValueError("--parameter is not accepted with --bitbucket-project-url")
            result = run_repository_batch_scenario(
                context,
                RepositoryBatchScenarioOptions(
                    scenario_id=args.scenario,
                    bitbucket_project_url=getattr(args, "bitbucket_project_url", None),
                    output_path=args.output,
                    replace=args.replace,
                    force_rebuild=args.force_rebuild,
                    repository_limit=getattr(args, "repository_limit", None),
                    auth_mode=getattr(args, "auth_mode", "auto"),
                    ca_bundle=getattr(args, "ca_bundle", None),
                    insecure_skip_tls_verify=getattr(args, "insecure_skip_tls_verify", False),
                    timeout_seconds=getattr(args, "timeout_seconds", 60.0),
                    clone_retries=getattr(args, "clone_retries", 2),
                    clone_timeout_seconds=getattr(args, "clone_timeout_seconds", 300.0),
                    duckdb_memory_limit=getattr(args, "duckdb_memory_limit", "1GB"),
                    duckdb_threads=getattr(args, "duckdb_threads", 1),
                ),
            )
            if args.as_json:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                print(f"Status: {result.get('status')}")
                print(f"Scenario: {result.get('scenario_id')}")
                print(f"Profile: {result.get('knowledge_profile_id')}")
                print(
                    "Repositories: "
                    f"{result.get('repositories_completed', 0)}/{result.get('repository_count', 0)} completed"
                    + (f", {result.get('repositories_failed', 0)} failed" if result.get('repositories_failed') else "")
                )
                print(f"Output: {result.get('output')}")
            return 0 if result.get("status") == "completed" else 1

        if not args.system_id:
            raise ValueError("--system-id is required unless --bitbucket-project-url is used")
        options = OneShotRunOptions(
            scenario_id=args.scenario,
            system_id=args.system_id,
            repositories=tuple(args.repository),
            knowledge_revisions=revisions,
            physical_model_path=args.physical_model,
            display_name=args.display_name,
            parameters=parameters,
            output_path=args.output,
            replace=args.replace,
            force_rebuild=args.force_rebuild,
        )

        def emit_log(message: str) -> None:
            print(message, file=sys.stderr, flush=True)

        result = asyncio.run(run_one_shot(context, options, on_log=emit_log))
    except (RuntimeApiError, ValueError) as exc:
        if args.as_json:
            if isinstance(exc, RuntimeApiError):
                payload = {
                    "status": "error",
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                }
            else:
                payload = {"status": "error", "code": "invalid_arguments", "message": str(exc)}
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            if isinstance(exc, RuntimeApiError):
                print(f"ERROR [{exc.code}] {exc.message}", file=sys.stderr)
                if exc.details:
                    print(json.dumps(exc.details, ensure_ascii=False, indent=2), file=sys.stderr)
            else:
                print(f"ERROR {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("Cancelled by user", file=sys.stderr)
        return 130

    if args.as_json:
        print(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))
    else:
        print(f"Status: {result.status.value}")
        print(f"Job: {result.job_id}")
        print(f"System: {result.target.system_id}")
        if result.publication_bundle is not None:
            print(f"Bundle: {result.publication_bundle.path}")
            print(f"Bundle SHA-256: {result.publication_bundle.sha256}")
        if result.output.output_path:
            print(f"Output: {result.output.output_path}")
        if result.failure is not None:
            print(f"Failure: [{result.failure.code}] {result.failure.message}", file=sys.stderr)
    return 0 if result.status is JobStatus.SUCCEEDED else 1



def _refresh_check(args: argparse.Namespace) -> int:
    base_url = args.control_plane_url.rstrip("/")
    enqueue = "false" if args.no_enqueue else "true"
    if args.due:
        path = f"/api/v1/productions/refresh-check-due?enqueue={enqueue}"
    else:
        path = f"/api/v1/productions/{quote(args.production, safe='')}/refresh-check?enqueue={enqueue}"
    request = Request(
        f"{base_url}{path}",
        data=b"",
        method="POST",
        headers={"Accept": "application/json"},
    )
    try:
        with urlopen(request, timeout=args.timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        content = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(content)
        except Exception:
            payload = {"status": "error", "code": "control_plane_http_error", "message": content or str(exc)}
        print(json.dumps(payload, ensure_ascii=False, indent=2) if args.as_json else f"ERROR {payload.get('message', exc)}", file=sys.stderr)
        return 2
    except (URLError, TimeoutError, OSError, ValueError) as exc:
        payload = {
            "status": "error",
            "code": "control_plane_unavailable",
            "message": f"Knowledge Control Plane is unavailable: {exc}",
            "base_url": base_url,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2) if args.as_json else f"ERROR {payload['message']}", file=sys.stderr)
        return 2

    if args.as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    items = payload.get("items") if args.due else [payload]
    items = items or []
    if not items:
        print("No production registrations are due for a freshness check.")
        return 0
    for item in items:
        production = item.get("production") or {}
        print(
            f"{production.get('production_id')}: {production.get('freshness_status')}"
            + (f" -> job {item.get('enqueued_job_id')}" if item.get("enqueued_job_id") else "")
        )
    return 0

def main() -> None:
    parser = argparse.ArgumentParser(prog="knowledge-control-plane")
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve = subparsers.add_parser("serve", help="Start the generic orchestration backend")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--reload", action="store_true")

    doctor = subparsers.add_parser("doctor", help="Validate tools, paths, TLS and runtime health")
    doctor.add_argument("--json", action="store_true", dest="as_json")

    run = subparsers.add_parser(
        "run",
        help="Run one Analysis Scenario end-to-end from the terminal without starting knowledge-control-plane serve",
    )
    run.add_argument("--scenario", required=True, help="Analysis Scenario id")
    run.add_argument(
        "--system-id",
        help="AISL system id recorded in the publication bundle; omitted for --bitbucket-project-url batch execution",
    )
    run.add_argument(
        "--repository",
        action="append",
        default=[],
        help="Source repository path; repeat for source-backed workspace profiles",
    )
    run.add_argument(
        "--bitbucket-project-url",
        help="Bitbucket Data Center project URL; execute the selected repository-scoped scenario independently for every repository",
    )
    run.add_argument(
        "--repository-limit",
        type=int,
        help="Limit repositories selected from Bitbucket; useful for acceptance/smoke runs",
    )
    run.add_argument("--auth-mode", default="auto", choices=("auto", "token", "basic", "credential-helper", "ssh", "none"))
    run.add_argument("--ca-bundle", help="Custom CA bundle for Bitbucket TLS")
    run.add_argument("--insecure-skip-tls-verify", action="store_true")
    run.add_argument("--timeout-seconds", type=float, default=60.0, help="Bitbucket API timeout")
    run.add_argument("--clone-retries", type=int, default=2)
    run.add_argument("--clone-timeout-seconds", type=float, default=300.0)
    run.add_argument("--duckdb-memory-limit", default="1GB")
    run.add_argument("--duckdb-threads", type=int, default=1)
    run.add_argument(
        "--knowledge-revision",
        action="append",
        default=[],
        metavar="SYSTEM_ID:REVISION_ID",
        help="Published input revision for workspace-scoped profiles; repeat as needed",
    )
    run.add_argument("--physical-model", help="PowerDesigner PDM path when required by selected knowledge")
    run.add_argument("--display-name")
    run.add_argument("--parameter", action="append", default=[], metavar="NAME=VALUE")
    run.add_argument("--output", help="Explicit analysis output path")
    run.add_argument("--replace", action="store_true", help="Allow replacement of the explicit output path")
    run.add_argument("--force-rebuild", action="store_true", help="Disable reuse of unchanged analysis stages")
    run.add_argument("--json", action="store_true", dest="as_json", help="Print final JobDetails as JSON")

    refresh = subparsers.add_parser(
        "refresh-check",
        help="Ask a running Knowledge Control Plane to check registered production freshness",
    )
    selector = refresh.add_mutually_exclusive_group(required=True)
    selector.add_argument("--due", action="store_true", help="Check only enabled polling registrations whose interval is due")
    selector.add_argument("--production", help="Check one production registration by id")
    refresh.add_argument(
        "--control-plane-url",
        default=os.getenv("KNOWLEDGE_CONTROL_PLANE_URL", "http://127.0.0.1:8000"),
        help="Running Knowledge Control Plane base URL",
    )
    refresh.add_argument("--no-enqueue", action="store_true", help="Observe freshness without queuing a production job")
    refresh.add_argument("--timeout-seconds", type=float, default=60.0)
    refresh.add_argument("--json", action="store_true", dest="as_json")

    args = parser.parse_args()
    if args.command == "serve":
        uvicorn.run(
            "knowledge_control_plane.runtime.app:create_runtime_app",
            factory=True,
            host=args.host,
            port=args.port,
            reload=args.reload,
        )
        return
    if args.command == "doctor":
        raise SystemExit(_doctor(as_json=args.as_json))
    if args.command == "run":
        raise SystemExit(_run(args))
    if args.command == "refresh-check":
        raise SystemExit(_refresh_check(args))


if __name__ == "__main__":
    main()
