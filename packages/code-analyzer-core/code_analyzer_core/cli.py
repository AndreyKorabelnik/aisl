from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone
import ctypes
import faulthandler
import json
import os
import shutil
import signal
import sys
import typer
from rich.console import Console

from code_analyzer_core import __version__

app = typer.Typer(help="Machine-first analyzer with Tree-sitter Java, Python and SQL analysis outputs")
console = Console()


def _write_process_lifecycle_event(analysis_out: Path, event: str, **details) -> None:
    from code_analyzer_core.logging_utils import process_memory_metrics

    diagnostics = Path(analysis_out).expanduser().resolve() / "diagnostics"
    diagnostics.mkdir(parents=True, exist_ok=True)
    payload = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": event,
        "pid": os.getpid(),
        "runtime": process_memory_metrics(),
        "details": details,
    }
    with (diagnostics / "process_lifecycle.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()


def _trim_process_heap() -> dict[str, object]:
    """Return free libc heap pages without traversing Python object graphs."""
    try:
        libc = ctypes.CDLL(None)
        malloc_trim = getattr(libc, "malloc_trim")
        malloc_trim.argtypes = [ctypes.c_size_t]
        malloc_trim.restype = ctypes.c_int
        return {"supported": True, "trimmed": bool(malloc_trim(0))}
    except Exception as exc:
        return {"supported": False, "trimmed": False, "error": type(exc).__name__}


def _enable_stack_dump_signal(analysis_out: Path) -> None:
    if not hasattr(signal, "SIGUSR1"):
        return
    diagnostics = Path(analysis_out).expanduser().resolve() / "diagnostics"
    diagnostics.mkdir(parents=True, exist_ok=True)
    target = (diagnostics / "process_stack_dumps.log").open("a", encoding="utf-8")
    try:
        faulthandler.register(signal.SIGUSR1, file=target, all_threads=True, chain=False)
    except Exception:
        target.close()


def _clean_static_analysis_output(analysis_out: Path, *, source_path: Path | None = None) -> None:
    resolved = Path(analysis_out).expanduser().resolve()
    if str(resolved) in {"/", ""}:
        raise typer.BadParameter(f"REFUSE_TO_CLEAN_UNSAFE_OUTPUT_DIR: {resolved}")
    if source_path is not None:
        src = Path(source_path).expanduser().resolve()
        if resolved == src:
            raise typer.BadParameter("--static-analysis-output must not be the source repository/spec directory")
        try:
            src.relative_to(resolved)
            raise typer.BadParameter("--static-analysis-output must not be a parent of the source repository/spec directory")
        except ValueError:
            pass
    if resolved.exists():
        if not resolved.is_dir():
            raise typer.BadParameter(f"--static-analysis-output exists and is not a directory: {resolved}")
        shutil.rmtree(resolved)
    resolved.mkdir(parents=True, exist_ok=True)


@app.callback()
def main():
    pass


@app.command()
def version():
    console.print(__version__)


@app.command("analysis-catalog")
def analysis_catalog_command(
    profiles_root: Path = typer.Option(..., "--profiles-root", exists=True, file_okay=False, dir_okay=True, readable=True, help="Directory containing Core analysis profile YAML files."),
    output: Path = typer.Option(..., "--output", help="Target JSON file for core_analysis_catalog/v1."),
    fragments_root: Path | None = typer.Option(None, "--fragments-root", exists=True, file_okay=False, dir_okay=True, readable=True, help="Optional profile-fragment directory; defaults to sibling analysis-profile-fragments."),
):
    """Export the official read-only catalog of Core profiles and current runtime behavior."""
    from code_analyzer_core.analysis_catalog import build_core_analysis_catalog, write_core_analysis_catalog

    try:
        catalog = build_core_analysis_catalog(
            profiles_root=profiles_root,
            fragments_root=fragments_root,
        )
        target = write_core_analysis_catalog(output, catalog)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        console.print(f"[red]Core analysis catalog failed:[/red] {exc}")
        raise typer.Exit(1)

    console.print(json.dumps({
        "schema_version": catalog.get("schema_version"),
        "core_version": catalog.get("core_version"),
        "profile_count": (catalog.get("summary") or {}).get("profile_count"),
        "fragment_count": (catalog.get("summary") or {}).get("fragment_count"),
        "stage_definition_count": (catalog.get("summary") or {}).get("stage_definition_count"),
        "catalog_fingerprint": catalog.get("catalog_fingerprint"),
        "output": str(target),
    }, ensure_ascii=False, sort_keys=True))


@app.command("target-contracts")
def target_contracts_command(
    core_catalog: Path = typer.Option(..., "--core-catalog", exists=True, file_okay=True, dir_okay=False, readable=True, help="Official core_analysis_catalog/v1 JSON file."),
    output: Path = typer.Option(..., "--output", help="Target JSON file for core_target_analysis_contracts/v1."),
    markdown: Path | None = typer.Option(None, "--markdown", help="Optional human-readable Markdown summary."),
):
    """Export Core-owned target contracts without changing analysis execution."""
    from code_analyzer_core.target_contracts import (
        build_core_target_analysis_contracts,
        write_core_target_analysis_contracts,
        write_core_target_analysis_contracts_markdown,
    )

    try:
        source = json.loads(core_catalog.read_text(encoding="utf-8"))
        payload = build_core_target_analysis_contracts(source)
        target = write_core_target_analysis_contracts(output, payload)
        markdown_target = (
            write_core_target_analysis_contracts_markdown(markdown, payload)
            if markdown is not None
            else None
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        console.print(f"[red]Core target contracts failed:[/red] {exc}")
        raise typer.Exit(1)

    typer.echo(json.dumps({
        "schema_version": payload.get("schema_version"),
        "core_version": payload.get("core_version"),
        "foundation_violation_count": (payload.get("summary") or {}).get("foundation_violation_count"),
        "observed_internal_stage_dependency_count": (payload.get("summary") or {}).get("observed_internal_stage_dependency_count"),
        "knowledge_materialization_inside_core_count": (payload.get("summary") or {}).get("knowledge_materialization_inside_core_count"),
        "contracts_fingerprint": payload.get("contracts_fingerprint"),
        "output": str(target),
        "markdown": str(markdown_target) if markdown_target is not None else None,
    }, ensure_ascii=False, sort_keys=True))



@app.command("evidence-contracts")
def evidence_contracts_command(
    core_catalog: Path = typer.Option(..., "--core-catalog", exists=True, file_okay=True, dir_okay=False, readable=True, help="Official core_analysis_catalog/v1 JSON file."),
    core_target_contracts: Path = typer.Option(..., "--core-target-contracts", exists=True, file_okay=True, dir_okay=False, readable=True, help="Official core_target_analysis_contracts/v1 JSON file."),
    output: Path = typer.Option(..., "--output", help="Target JSON file for core_evidence_contract_catalog/v1."),
    markdown: Path | None = typer.Option(None, "--markdown", help="Optional human-readable Markdown summary."),
):
    """Export the generic Core-owned typed evidence contract catalog."""
    from code_analyzer_core.evidence_contracts import (
        build_core_evidence_contract_catalog,
        write_core_evidence_contract_catalog,
        write_core_evidence_contract_catalog_markdown,
    )

    try:
        catalog = json.loads(core_catalog.read_text(encoding="utf-8"))
        target_contracts = json.loads(core_target_contracts.read_text(encoding="utf-8"))
        payload = build_core_evidence_contract_catalog(catalog, target_contracts)
        target = write_core_evidence_contract_catalog(output, payload)
        markdown_target = (
            write_core_evidence_contract_catalog_markdown(markdown, payload)
            if markdown is not None
            else None
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        console.print(f"[red]Core evidence contracts failed:[/red] {exc}")
        raise typer.Exit(1)

    typer.echo(json.dumps({
        "schema_version": payload.get("schema_version"),
        "core_version": payload.get("core_version"),
        "contract_count": (payload.get("summary") or {}).get("contract_count"),
        "runtime_published_count": (payload.get("summary") or {}).get("runtime_published_count"),
        "catalog_fingerprint": payload.get("catalog_fingerprint"),
        "output": str(target),
        "markdown": str(markdown_target) if markdown_target is not None else None,
    }, ensure_ascii=False, sort_keys=True))


@app.command("evidence-execute")
def evidence_execute_command(
    repository: Path = typer.Option(..., "--repository", exists=True, file_okay=False, dir_okay=True, readable=True),
    request: Path = typer.Option(..., "--request", exists=True, file_okay=True, dir_okay=False, readable=True),
    output: Path = typer.Option(..., "--output", file_okay=False),
    repo_id: str | None = typer.Option(None, "--repo-id"),
    replace: bool = typer.Option(False, "--replace/--no-replace"),
):
    """Execute a contract-driven set of registered Core evidence analyzers."""
    from code_analyzer_core.evidence_runtime import execute_evidence_request

    try:
        if output.exists():
            if not replace:
                raise ValueError(f"output already exists: {output}; pass --replace")
            _clean_static_analysis_output(output, source_path=repository)
        else:
            output.mkdir(parents=True, exist_ok=True)
        payload = json.loads(request.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Core evidence execution request must be a JSON object")
        result = execute_evidence_request(
            repository=repository,
            request=payload,
            output=output,
            repo_id=repo_id,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        console.print(f"[red]Core evidence execution failed:[/red] {exc}")
        raise typer.Exit(1)

    console.print(json.dumps({
        "schema_version": result.get("schema_version"),
        "execution_id": result.get("execution_id"),
        "status": result.get("status"),
        "analyzer_execution_count": len(result.get("analyzer_executions") or []),
        "evidence_artifact_count": len(result.get("evidence_artifacts") or []),
        "result_fingerprint": result.get("result_fingerprint"),
        "output": str(output.resolve()),
    }, ensure_ascii=False, sort_keys=True))


@app.command()
def doctor():
    """Check runtime prerequisites for the fast evidence-oriented core."""
    checks: list[tuple[str, bool, str]] = []
    git_path = shutil.which("git")
    checks.append(("python_runtime", True, "ok"))
    checks.append(("git_optional_for_analyze_git_change", git_path is not None, git_path or "not found"))
    try:
        from code_analyzer_core.scanners.java_syntax import (
            JAVA_SYNTAX_PROVIDER,
            tree_sitter_available,
        )

        ok_ts, ts_detail = tree_sitter_available()
        checks.append(("java_syntax_provider", ok_ts, f"{JAVA_SYNTAX_PROVIDER}: {ts_detail}"))
    except ModuleNotFoundError as exc:
        checks.append(("java_syntax_provider", False, f"missing optional runtime dependency: {exc.name}"))
    checks.append(("heavy_java_ast_tools", True, "Spoon removed from fast core; Java/Maven are not mandatory"))
    checks.append(("semgrep", True, "Semgrep removed from fast core; executable is not required"))

    for name, ok, detail in checks:
        if ok:
            console.print(f"[green]✓[/green] {name}: {detail}")
        else:
            console.print(f"[yellow]⚠[/yellow] {name}: {detail}")

    console.print("\n[bold green]Fast core preflight passed.[/bold green]")


@app.command("build-java-foundation")
def build_java_foundation_command(
    repo_path: Path = typer.Argument(..., exists=True, file_okay=False, dir_okay=True),
    foundation_out: Path = typer.Option(..., "--foundation-output", help="Directory for the reusable foundation artifact"),
    foundation_fragment: Path = typer.Option(..., "--foundation-fragment", exists=True, file_okay=True, dir_okay=False, readable=True),
    repo_id: str | None = typer.Option(None, "--repo-id"),
    project_code: str = typer.Option("UNKNOWN", "--project-code"),
    system_name: str = typer.Option("unknown-system", "--system-name"),
    verbose: bool = typer.Option(False, "--verbose"),
    clean_output: bool = typer.Option(True, "--clean-output/--no-clean-output"),
):
    """Build one reusable deterministic repository analysis foundation artifact."""
    if clean_output:
        _clean_static_analysis_output(foundation_out, source_path=repo_path)
    _enable_stack_dump_signal(foundation_out)
    _write_process_lifecycle_event(foundation_out, "foundation_process_started", fragment=str(foundation_fragment))
    from code_analyzer_core.java_analysis import build_java_foundation

    result = build_java_foundation(
        repo_path=repo_path,
        foundation_out=foundation_out,
        foundation_fragment=foundation_fragment,
        repo_id=repo_id,
        project_code=project_code,
        system_name=system_name,
        verbose=verbose,
    )
    heap_trim = _trim_process_heap()
    _write_process_lifecycle_event(foundation_out, "foundation_process_exit", returncode=0, counts=result.get("counts"), heap_trim=heap_trim)
    console.print(f"[bold green]Java foundation done.[/bold green] repo_id={result.get('repo_id')} facts={(result.get('counts') or {}).get('facts')}")
    console.print(f"Foundation output: {foundation_out.resolve()}")
    try:
        console.file.flush()
    except Exception:
        pass
    os.execv(sys.executable, [sys.executable, "-c", "import os; os._exit(0)"])


@app.command("analyze-java")
def analyze_java(
    repo_path: Path = typer.Argument(..., exists=True, file_okay=False, dir_okay=True),
    analysis_out: Path = typer.Option(..., "--static-analysis-output", help="Directory for repository static-analysis-output"),
    repo_id: str | None = typer.Option(None, "--repo-id", help="Stable repository id inside the analysis output"),
    project_code: str = typer.Option("UNKNOWN", "--project-code"),
    system_name: str = typer.Option("unknown-system", "--system-name"),
    run_id: str | None = typer.Option(None, "--run-id", help="Optional run id; defaults to UTC timestamp"),
    max_packages: int = typer.Option(80, "--max-packages", help="Max navigation items per type."),
    max_fields_per_schema: int = typer.Option(16, "--max-fields-per-schema"),
    analysis_profile: Path = typer.Option(..., "--analysis-profile", exists=True, file_okay=True, dir_okay=False, readable=True, help="Required path to analysis profile YAML."),
    foundation_input: Path | None = typer.Option(None, "--foundation-input", exists=True, file_okay=False, dir_okay=True, readable=True, help="Optional reusable repository analysis foundation artifact."),
    verbose: bool = typer.Option(False, "--verbose"),
    clean_output: bool = typer.Option(True, "--clean-output/--no-clean-output", help="Clean --static-analysis-output before writing new static artifacts."),
):
    """Analyze one Java/Spring repository and add it to an analysis output."""
    if clean_output:
        _clean_static_analysis_output(analysis_out, source_path=repo_path)
    _enable_stack_dump_signal(analysis_out)
    _write_process_lifecycle_event(analysis_out, "process_started", profile=str(analysis_profile))
    from code_analyzer_core.java_analysis import run_java_analysis

    result = run_java_analysis(
        repo_path=repo_path,
        analysis_out=analysis_out,
        repo_id=repo_id,
        project_code=project_code,
        system_name=system_name,
        run_id=run_id,
        max_packages=max_packages,
        max_fields_per_schema=max_fields_per_schema,
        analysis_profile=analysis_profile,
        foundation_input=foundation_input,
        verbose=verbose,
    )
    repo_summary = dict(result.get("repo") or {})
    counts = repo_summary.get("counts") or {}
    analysis_output_path = result.get("analysis_out")
    _write_process_lifecycle_event(
        analysis_out,
        "analysis_returned",
        repo_id=repo_summary.get("repo_id"),
        counts=counts,
    )
    # Drop large workspace summary/catalog objects before the immediate one-shot
    # process exit. Do not run a full cyclic GC here: the process exits via
    # os._exit(0), so collecting millions of transient syntax objects adds
    # latency without providing cleanup value. Library callers still use the
    # explicit syntax lifecycle inside run_java_analysis().
    del result
    heap_trim = _trim_process_heap()
    _write_process_lifecycle_event(
        analysis_out,
        "cleanup_completed",
        strategy="immediate_exit_without_full_gc_with_malloc_trim",
        heap_trim=heap_trim,
    )
    console.print(f"[bold green]Java analysis done.[/bold green] repo_id={repo_summary.get('repo_id')} profile={analysis_profile} interfaces={counts.get('interfaces')} schemas={counts.get('schemas')} facts={counts.get('facts')}")
    console.print(f"Static analysis output: {analysis_output_path}")
    console.print(f"Static analysis output: {analysis_out.resolve()}")
    try:
        console.file.flush()
    except Exception:
        pass
    _write_process_lifecycle_event(analysis_out, "process_exit", returncode=0)
    # This Typer command is a one-shot CLI entrypoint. Use immediate process exit
    # after successful artifact publication to avoid long CPython shutdown on very
    # large transient analysis objects in real-app runs. Library callers use
    # run_java_analysis() directly and are not affected.
    os.execv(sys.executable, [sys.executable, "-c", "import os; os._exit(0)"])



@app.command("analyze-spec")
def analyze_spec(
    spec_artifacts: Path = typer.Argument(..., exists=True, file_okay=False, dir_okay=True, help="Directory containing data-evidence.yaml and SDD/OpenSpec artifacts"),
    analysis_out: Path = typer.Option(..., "--static-analysis-output", help="Directory for repository static-analysis-output"),
    repo_id: str | None = typer.Option(None, "--repo-id", help="Stable repository/system id inside the analysis output"),
    project_code: str = typer.Option("UNKNOWN", "--project-code"),
    system_name: str = typer.Option("unknown-system", "--system-name"),
    run_id: str | None = typer.Option(None, "--run-id", help="Optional run id; defaults to UTC timestamp"),
    analysis_profile: Path | None = typer.Option(None, "--analysis-profile", exists=True, file_okay=True, dir_okay=False, readable=True, help="Optional spec static analysis profile YAML; defaults to bundled spec-evidence-workspace"),
    verbose: bool = typer.Option(False, "--verbose"),
    clean_output: bool = typer.Option(True, "--clean-output/--no-clean-output", help="Clean --static-analysis-output before writing new static artifacts."),
):
    """Analyze SDD/OpenSpec artifacts into the ordinary analysis-output contract.

    This is a deterministic static analysis mode for specification artifacts. It
    does not call an LLM and does not create external_context. The resulting
    workspace is intentionally Java-compatible so evidence-llm run-pipeline can
    use the ordinary evidence tools API and existing LLM profiles.
    """
    try:
        if clean_output:
            _clean_static_analysis_output(analysis_out, source_path=spec_artifacts)
        from code_analyzer_core.spec_analysis import run_spec_analysis

        result = run_spec_analysis(
            spec_artifacts=spec_artifacts,
            analysis_out=analysis_out,
            repo_id=repo_id,
            project_code=project_code,
            system_name=system_name,
            run_id=run_id,
            analysis_profile=analysis_profile,
            verbose=verbose,
        )
    except Exception as exc:
        console.print(f"[red]Spec analysis failed:[/red] {exc}")
        raise typer.Exit(1)
    counts = result["repo"].get("counts") or {}
    console.print(
        f"[bold green]Spec analysis done.[/bold green] "
        f"repo_id={result['repo']['repo_id']} source_type=spec_artifacts "
        f"interfaces={counts.get('interfaces')} schemas={counts.get('schemas')} transformations={counts.get('transformations')} gaps={counts.get('gaps')}"
    )
    console.print(f"Static analysis output: {result['analysis_out']}")
    console.print(f"Static analysis output: {analysis_out.resolve()}")


@app.command("analyze-python")
def analyze_python(
    repo_path: Path = typer.Argument(..., exists=True, file_okay=False, dir_okay=True),
    analysis_out: Path = typer.Option(..., "--static-analysis-output", help="Directory for repository static-analysis-output"),
    repo_id: str | None = typer.Option(None, "--repo-id", help="Stable repository id inside the analysis output"),
    project_code: str = typer.Option("UNKNOWN", "--project-code"),
    system_name: str = typer.Option("unknown-system", "--system-name"),
    run_id: str | None = typer.Option(None, "--run-id", help="Optional run id; defaults to UTC timestamp"),
    max_packages: int = typer.Option(80, "--max-packages", help="Max navigation items per type."),
    max_fields_per_schema: int = typer.Option(16, "--max-fields-per-schema"),
    verbose: bool = typer.Option(False, "--verbose"),
    clean_output: bool = typer.Option(True, "--clean-output/--no-clean-output", help="Clean --static-analysis-output before writing new static artifacts."),
):
    """Analyze one Python repository and add it to an analysis output."""
    if clean_output:
        _clean_static_analysis_output(analysis_out, source_path=repo_path)
    from code_analyzer_core.python_analysis import run_python_repository_analysis

    result = run_python_repository_analysis(
        repo_path=repo_path,
        analysis_out=analysis_out,
        repo_id=repo_id,
        project_code=project_code,
        system_name=system_name,
        run_id=run_id,
        max_packages=max_packages,
        max_fields_per_schema=max_fields_per_schema,
        verbose=verbose,
    )
    counts = result["repo"].get("counts") or {}
    console.print(f"[bold green]Python analysis done.[/bold green] repo_id={result['repo']['repo_id']} interfaces={counts.get('interfaces')} schemas={counts.get('schemas')} facts={counts.get('facts')}")
    console.print(f"Static analysis output: {result['analysis_out']}")
    console.print(f"Static analysis output: {analysis_out.resolve()}")



@app.command("analyze-physical-model")
def analyze_physical_model(
    model_path: Path = typer.Argument(..., exists=True, file_okay=True, dir_okay=False, readable=True),
    artifact_out: Path = typer.Option(..., "--artifact-output", help="Directory for the physical-model/v1 artifact"),
    source_id: str | None = typer.Option(None, "--source-id", help="Stable auxiliary physical-model source id"),
    clean_output: bool = typer.Option(True, "--clean-output/--no-clean-output"),
):
    """Extract deterministic facts from a PowerDesigner PDM model."""
    if clean_output:
        _clean_static_analysis_output(artifact_out, source_path=model_path)
    from code_analyzer_core.physical_model import build_physical_model_artifact

    result = build_physical_model_artifact(
        model_path=model_path,
        output_dir=artifact_out,
        source_id=source_id,
    )
    console.print(
        f"[bold green]Physical model analysis done.[/bold green] "
        f"tables={result.counts.get('physical_model_table')} "
        f"columns={result.counts.get('physical_model_column')} "
        f"keys={result.counts.get('physical_model_key')} "
        f"relationships={result.counts.get('physical_model_relationship')}"
    )
    console.print(f"Physical model artifact: {result.output_dir}")


@app.command("analyze-git-change")
def analyze_git_change(
    repo_path: Path = typer.Argument(..., exists=True, file_okay=False, dir_okay=True),
    analysis_out: Path = typer.Option(..., "--static-analysis-output", help="Directory for repository static-analysis-output"),
    from_ref: str | None = typer.Option(None, "--from", help="Base git ref/commit. For branch analysis merge-base(from,to) is used when applicable."),
    to_ref: str | None = typer.Option(None, "--to", help="Target git ref/commit"),
    commit: str | None = typer.Option(None, "--commit", help="Analyze one commit as parent(commit) -> commit"),
    repo_id: str | None = typer.Option(None, "--repo-id", help="Stable repository id inside the analysis output"),
    project_code: str = typer.Option("UNKNOWN", "--project-code"),
    system_name: str = typer.Option("unknown-system", "--system-name"),
    max_packages: int = typer.Option(80, "--max-packages", help="Max navigation items per type for before/after static analysis."),
    max_fields_per_schema: int = typer.Option(16, "--max-fields-per-schema"),
    analysis_profile: Path = typer.Option(..., "--analysis-profile", exists=True, file_okay=True, dir_okay=False, readable=True, help="Analysis profile YAML used for BEFORE and AFTER snapshots."),
    change_id: str | None = typer.Option(None, "--change-id", help="Neutral change/MR id for traceability only."),
    change_type: str | None = typer.Option(None, "--change-type", help="commit|range|mr|branch_diff|unknown."),
    source_branch: str | None = typer.Option(None, "--source-branch", help="Source branch name for traceability only."),
    target_branch: str | None = typer.Option(None, "--target-branch", help="Target branch name for traceability only."),
    reviewers: str | None = typer.Option(None, "--reviewers", help="Comma-separated reviewer names/logins/emails for traceability only; no network lookup is performed."),
    verbose: bool = typer.Option(False, "--verbose"),
    clean_output: bool = typer.Option(True, "--clean-output/--no-clean-output", help="Clean --static-analysis-output before writing new static artifacts."),
):
    """Analyze a git change range and build before/after data-impact evidence.

    This command assesses the change between two repository states. It does not
    evaluate an author or engineer. Author/committer fields are metadata only.
    """
    try:
        if clean_output:
            _clean_static_analysis_output(analysis_out, source_path=repo_path)
        from code_analyzer_core.git_change_analyzer import run_git_change_analysis

        result = run_git_change_analysis(
            repo_path=repo_path,
            analysis_out=analysis_out,
            from_ref=from_ref,
            to_ref=to_ref,
            commit=commit,
            repo_id=repo_id,
            project_code=project_code,
            system_name=system_name,
            analysis_profile=analysis_profile,
            change_id=change_id,
            change_type=change_type,
            source_branch=source_branch,
            target_branch=target_branch,
            reviewers=reviewers,
            max_packages=max_packages,
            max_fields_per_schema=max_fields_per_schema,
            verbose=verbose,
        )
    except Exception as exc:
        console.print(f"[red]Git change analysis failed:[/red] {exc}")
        raise typer.Exit(1)
    counts = result.get("counts") or {}
    console.print(
        f"[bold green]Git change analysis done.[/bold green] "
        f"changed_files={counts.get('changed_files')} lineage_delta={counts.get('lineage_delta')} "
        f"transformation_delta={counts.get('transformation_delta')} table_delta={counts.get('table_delta')}"
    )
    console.print(f"Static analysis output: {Path(result['analysis_out']).resolve()}")
    console.print(f"Git change evidence: {Path(result['git_change_evidence']).resolve()}")


@app.command("analyze-git")
def analyze_git(
    repo_path: Path = typer.Argument(..., exists=True, file_okay=False, dir_okay=True),
    analysis_out: Path = typer.Option(..., "--static-analysis-output", help="Directory for repository static-analysis-output"),
    from_ref: str | None = typer.Option(None, "--from"),
    to_ref: str | None = typer.Option(None, "--to"),
    commit: str | None = typer.Option(None, "--commit"),
    repo_id: str | None = typer.Option(None, "--repo-id"),
    project_code: str = typer.Option("UNKNOWN", "--project-code"),
    system_name: str = typer.Option("unknown-system", "--system-name"),
    max_packages: int = typer.Option(80, "--max-packages"),
    max_fields_per_schema: int = typer.Option(16, "--max-fields-per-schema"),
    analysis_profile: Path = typer.Option(..., "--analysis-profile", exists=True, file_okay=True, dir_okay=False, readable=True),
    change_id: str | None = typer.Option(None, "--change-id"),
    change_type: str | None = typer.Option(None, "--change-type"),
    source_branch: str | None = typer.Option(None, "--source-branch"),
    target_branch: str | None = typer.Option(None, "--target-branch"),
    reviewers: str | None = typer.Option(None, "--reviewers"),
    verbose: bool = typer.Option(False, "--verbose"),
    clean_output: bool = typer.Option(True, "--clean-output/--no-clean-output", help="Clean --static-analysis-output before writing new static artifacts."),
):
    """Alias for analyze-git-change."""
    try:
        if clean_output:
            _clean_static_analysis_output(analysis_out, source_path=repo_path)
        from code_analyzer_core.git_change_analyzer import run_git_change_analysis

        result = run_git_change_analysis(
            repo_path=repo_path,
            analysis_out=analysis_out,
            from_ref=from_ref,
            to_ref=to_ref,
            commit=commit,
            repo_id=repo_id,
            project_code=project_code,
            system_name=system_name,
            analysis_profile=analysis_profile,
            change_id=change_id,
            change_type=change_type,
            source_branch=source_branch,
            target_branch=target_branch,
            reviewers=reviewers,
            max_packages=max_packages,
            max_fields_per_schema=max_fields_per_schema,
            verbose=verbose,
        )
    except Exception as exc:
        console.print(f"[red]Git change analysis failed:[/red] {exc}")
        raise typer.Exit(1)
    counts = result.get("counts") or {}
    console.print(f"[bold green]Git change analysis done.[/bold green] counts={counts}")
    console.print(f"Static analysis output: {Path(result['analysis_out']).resolve()}")

if __name__ == "__main__":
    app()
