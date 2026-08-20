from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from .contracts import ReportRequest
from .files import read_json, write_json
from .pipeline import build_report, prepare_report, write_prepared_report
from .progress import ConsoleFileProgress
from .regression import compare_reports, write_comparison_markdown
from .renderer import FileRenderer, ModelRenderer

app = typer.Typer(no_args_is_help=True, help="Build evidence-grounded reports from published Knowledge API revisions.")
console = Console()


def _request(
    *,
    profile: str,
    audience: str | None,
    detail_level: str,
    focus: list[str],
    output_name: str,
    api_url: str | None = None,
    system_id: str | None = None,
    revision_id: str | None = None,
    instruction_files: list[Path] | None = None,
) -> ReportRequest:
    report_type, version = profile.split("/", 1)
    resolved_audience = audience or ("business" if report_type in {"system-description", "sql-source-inventory-report"} else "architecture")
    return ReportRequest(
        report_type=report_type,
        report_version=version,
        api_url=str(api_url or ""),
        system_id=str(system_id or ""),
        revision_id=revision_id,
        audience=resolved_audience,
        detail_level=detail_level,
        focus=tuple(focus),
        output_name=output_name,
        instruction_files=tuple(instruction_files or ()),
    )


@app.command("prepare")
def prepare_command(
    profile: str = typer.Option("system-description/v1"),
    output_dir: Path = typer.Option(...),
    api_url: str | None = typer.Option(None, help="Knowledge API base URL, for example http://127.0.0.1:8000."),
    system_id: str | None = typer.Option(None, help="Knowledge API system identifier."),
    revision_id: str | None = typer.Option(None, help="Specific revision; active revision is used when omitted."),
    audience: str | None = typer.Option(None, help="Audience mode. Defaults to business for system-description and architecture for other reports."),
    detail_level: str = typer.Option("standard"),
    focus: list[str] = typer.Option([]),
    output_name: str = typer.Option("report.md"),
    instruction_file: list[Path] = typer.Option([], "--instruction-file", exists=True, dir_okay=False, readable=True),
) -> None:
    request = _request(
        profile=profile, audience=audience, detail_level=detail_level, focus=focus,
        output_name=output_name, api_url=api_url, system_id=system_id, revision_id=revision_id,
        instruction_files=instruction_file,
    )
    manifest = write_prepared_report(prepare_report(request), output_dir)
    console.print(f"Prepared dataset: {manifest.dataset_path}")


@app.command("build")
def build_command(
    profile: str = typer.Option("system-description/v1"),
    output_dir: Path = typer.Option(...),
    api_url: str | None = typer.Option(None, help="Knowledge API base URL, for example http://127.0.0.1:8000."),
    system_id: str | None = typer.Option(None, help="Knowledge API system identifier."),
    revision_id: str | None = typer.Option(None, help="Specific revision; active revision is used when omitted."),
    audience: str | None = typer.Option(None, help="Audience mode. Defaults to business for system-description and architecture for other reports."),
    detail_level: str = typer.Option("standard"),
    focus: list[str] = typer.Option([]),
    output_name: str = typer.Option("report.md"),
    instruction_file: list[Path] = typer.Option([], "--instruction-file", exists=True, dir_okay=False, readable=True),
    response_file: Path | None = typer.Option(None, exists=True), endpoint: str | None = typer.Option(None),
    model: str = typer.Option("default"), timeout_sec: int = typer.Option(600),
    cert: Path | None = typer.Option(None, "--cert", exists=True, dir_okay=False, readable=True, help="Client certificate PEM for LLM mTLS. Env: LLM_CERT_FILE."),
    key: Path | None = typer.Option(None, "--key", exists=True, dir_okay=False, readable=True, help="Client private key PEM for LLM mTLS. Env: LLM_KEY_FILE."),
    ca: Path | None = typer.Option(None, "--ca", exists=True, dir_okay=False, readable=True, help="CA bundle used to verify the LLM endpoint. Env: LLM_CA_FILE."),
    insecure: bool = typer.Option(False, "--insecure", help="Disable TLS certificate verification for the LLM endpoint (curl -k equivalent)."),
    http2: bool = typer.Option(False, "--http2", help="Use HTTP/2 for the LLM endpoint."),
    heartbeat_sec: int = typer.Option(20, min=0, help="Print a heartbeat while dataset building or LLM rendering is still running; 0 disables heartbeats."),
    quiet: bool = typer.Option(False, "--quiet", help="Suppress terminal progress; report-run.log is still written."),
    debug: bool = typer.Option(False, "--debug", help="Re-raise failures with a full traceback."),
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    log_path = output_dir / "report-run.log"
    progress = ConsoleFileProgress(log_path, console=console, quiet=quiet)
    renderer = FileRenderer(response_file) if response_file else ModelRenderer(
        endpoint=endpoint, model=model, timeout_sec=timeout_sec, cert_file=cert, key_file=key, ca_file=ca,
        verify_tls=False if insecure else None, http2=True if http2 else None,
    )
    request = _request(
        profile=profile, audience=audience, detail_level=detail_level, focus=focus,
        output_name=output_name, api_url=api_url, system_id=system_id, revision_id=revision_id,
        instruction_files=instruction_file,
    )
    progress("INFO", f"Run log: {log_path}")
    progress("INFO", f"Profile: {request.profile_id}; audience={request.audience}; detail_level={request.detail_level}")
    try:
        manifest = build_report(request, output_dir, renderer, progress=progress, heartbeat_sec=heartbeat_sec, log_path=log_path)
    except Exception as exc:
        progress("ERROR", f"Report build failed: {type(exc).__name__}: {exc}")
        progress("INFO", f"Prepared or partial artifacts, when available, remain in {output_dir}")
        if debug:
            raise
        raise typer.Exit(1) from exc
    if manifest.warnings:
        console.print(f"[yellow]Report returned with warnings ({len(manifest.warnings)}).[/yellow]")
        console.print(f"Validation: {manifest.validation_path}")
    else:
        console.print("[green]Report build completed.[/green]")
    console.print(f"Report: {manifest.report_path}")
    console.print(f"Manifest: {output_dir / 'report-run-manifest.json'}")
    console.print(f"Log: {log_path}")


@app.command("compare")
def compare_command(old_report: Path = typer.Option(..., exists=True), new_report: Path = typer.Option(..., exists=True), dataset: Path = typer.Option(..., exists=True), expectations: Path | None = typer.Option(None, exists=True), output_dir: Path = typer.Option(...)) -> None:
    result = compare_reports(old_report=old_report.read_text(encoding="utf-8"), new_report=new_report.read_text(encoding="utf-8"), dataset=read_json(dataset), expectations_path=expectations)
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "comparison.json", result)
    (output_dir / "comparison.md").write_text(write_comparison_markdown(result), encoding="utf-8")
    if not result["passed"]:
        raise typer.Exit(2)
    console.print("Regression comparison passed")

@app.command("serve")
def serve_command(
    api_url: str = typer.Option(..., help="Knowledge API base URL."),
    runs_root: Path = typer.Option(..., help="Reporting-owned persistent ReportRun root."),
    host: str = typer.Option("127.0.0.1"),
    port: int = typer.Option(18280),
    response_file: Path | None = typer.Option(None, exists=True, dir_okay=False, readable=True, help="Server-side deterministic renderer fixture; useful for tests."),
    endpoint: str | None = typer.Option(None, help="Server-side OpenAI-compatible LLM endpoint."),
    model: str = typer.Option("default"),
    timeout_sec: int = typer.Option(600),
    cert: Path | None = typer.Option(None, "--cert", exists=True, dir_okay=False, readable=True, help="Server-side client certificate PEM for LLM mTLS."),
    key: Path | None = typer.Option(None, "--key", exists=True, dir_okay=False, readable=True, help="Server-side client private key PEM for LLM mTLS."),
    ca: Path | None = typer.Option(None, "--ca", exists=True, dir_okay=False, readable=True, help="Server-side CA bundle for the LLM endpoint."),
    insecure: bool = typer.Option(False, "--insecure", help="Disable TLS certificate verification for the server-side LLM endpoint."),
    http2: bool = typer.Option(False, "--http2", help="Use HTTP/2 for the server-side LLM endpoint."),
) -> None:
    from .service import ReportingServiceConfig, serve
    serve(
        ReportingServiceConfig(
            api_url=api_url, runs_root=runs_root, response_file=response_file, llm_endpoint=endpoint,
            llm_model=model, llm_timeout_sec=timeout_sec, llm_cert_file=cert, llm_key_file=key, llm_ca_file=ca,
            llm_verify_tls=False if insecure else None, llm_http2=True if http2 else None,
        ),
        host=host, port=port,
    )
