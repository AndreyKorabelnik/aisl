from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer

from . import __version__
from .evidence_executor import execute_core_evidence_plan
from .knowledge_materialization_executor import execute_knowledge_materialization_plan
from .knowledge_execution import execute_knowledge_execution_plan
from .knowledge_execution_planning import (
    artifacts_from_repository_run_manifest,
    build_knowledge_input_inventory,
    compile_knowledge_execution_plan,
    inspect_repository_source,
    knowledge_from_materialization_result,
)
from .execution_result_contracts import (
    build_analysis_execution_result_catalog,
    load_json_object as load_execution_contract_json,
    write_analysis_execution_result_catalog,
    write_analysis_execution_result_markdown,
)
from .knowledge_planning import (
    build_knowledge_catalog,
    load_json_object as load_knowledge_json,
    load_knowledge_product_catalog,
    load_profile as load_knowledge_profile,
    render_knowledge_catalog_markdown,
    render_knowledge_resolution_markdown,
    resolve_knowledge_profile,
    write_json as write_knowledge_json,
    write_markdown as write_knowledge_markdown,
)
from .data_model_discovery import run_data_model_discovery
from .repository_acquisition import discover_bitbucket_project_repositories
from .repository_batch import run_repository_batch
from .io_utils import read_json as read_runtime_json, write_json as write_runtime_json
from .input_preparation import prepare_knowledge_input_inventory

app = typer.Typer(
    name="static-analysis-runner",
    help="Typed evidence execution and deterministic knowledge materialization runtime.",
    no_args_is_help=True,
)


def _progress(message: str) -> None:
    typer.echo(message, err=True)



@app.command("version")
def version() -> None:
    typer.echo(__version__)


@app.command("execution-result-contract")
def execution_result_contract(
    core_target_contracts: Path = typer.Option(..., "--core-target-contracts", exists=True, dir_okay=False),
    klc_materialization_contracts: Path = typer.Option(..., "--klc-materialization-contracts", exists=True, dir_okay=False),
    output: Path = typer.Option(..., "--output", dir_okay=False),
    markdown: Optional[Path] = typer.Option(None, "--markdown", dir_okay=False),
) -> None:
    """Build the read-only Runner-owned analysis execution result contract."""
    try:
        core_payload = load_execution_contract_json(core_target_contracts, label="Core target contracts")
        klc_payload = load_execution_contract_json(klc_materialization_contracts, label="KLC materialization contracts")
        payload = build_analysis_execution_result_catalog(core_payload, klc_payload)
        target = write_analysis_execution_result_catalog(output, payload)
        markdown_target = (
            write_analysis_execution_result_markdown(markdown, payload)
            if markdown is not None
            else None
        )
    except Exception as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(json.dumps({
        "schema_version": payload["schema_version"],
        "catalog_fingerprint": payload["catalog_fingerprint"],
        "knowledge_product_catalog_fingerprint": (payload.get("source") or {}).get("knowledge_product_catalog_fingerprint"),
        "knowledge_product_catalog_source": (payload.get("source") or {}).get("knowledge_product_catalog_source"),
        "output": str(target),
        "markdown": str(markdown_target) if markdown_target is not None else None,
        "current_manifest_variant_count": (payload.get("summary") or {}).get("current_manifest_variant_count"),
        "fully_compliant_manifest_count": (payload.get("summary") or {}).get("fully_compliant_manifest_count"),
        "task_semantic_coupled_variant_count": (payload.get("summary") or {}).get("task_semantic_coupled_variant_count"),
        "current_klc_task_semantic_route_count": (payload.get("summary") or {}).get("current_klc_task_semantic_route_count"),
        "next_step": next(
            (
                item.get("step")
                for item in ((payload.get("planning_conclusions") or {}).get("revised_sequence") or [])
                if item.get("status") == "next"
            ),
            None,
        ),
    }, ensure_ascii=False, indent=2, sort_keys=True))


@app.command("knowledge-catalog")
def knowledge_catalog(
    klc_materialization_contracts: Path = typer.Option(..., "--klc-materialization-contracts", exists=True, dir_okay=False),
    core_target_contracts: Path = typer.Option(..., "--core-target-contracts", exists=True, dir_okay=False),
    core_evidence_contracts: Path = typer.Option(..., "--core-evidence-contracts", exists=True, dir_okay=False),
    execution_result_contracts: Path = typer.Option(..., "--execution-result-contracts", exists=True, dir_okay=False),
    knowledge_product_catalog: Optional[Path] = typer.Option(
        None, "--knowledge-product-catalog", exists=True, dir_okay=False,
        help="Optional declarative knowledge_product_catalog/v1 JSON. Uses the packaged default when omitted.",
    ),
    output: Path = typer.Option(..., "--output", dir_okay=False),
    markdown: Optional[Path] = typer.Option(None, "--markdown", dir_okay=False),
) -> None:
    """Build the read-only user-facing catalog of KLC knowledge and source lineage."""
    try:
        klc = load_knowledge_json(klc_materialization_contracts, label="KLC materialization contracts")
        core = load_knowledge_json(core_target_contracts, label="Core target contracts")
        core_evidence = load_knowledge_json(core_evidence_contracts, label="Core evidence contracts")
        execution = load_knowledge_json(execution_result_contracts, label="Runner execution result contracts")
        product_catalog = (
            load_knowledge_product_catalog(knowledge_product_catalog)
            if knowledge_product_catalog is not None
            else None
        )
        payload = build_knowledge_catalog(
            klc, core, core_evidence, execution,
            product_catalog=product_catalog,
            product_catalog_source="external" if knowledge_product_catalog is not None else None,
        )
        target = write_knowledge_json(output, payload)
        markdown_target = (
            write_knowledge_markdown(markdown, render_knowledge_catalog_markdown(payload))
            if markdown is not None
            else None
        )
    except Exception as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(json.dumps({
        "schema_version": payload["schema_version"],
        "catalog_fingerprint": payload["catalog_fingerprint"],
        "knowledge_product_catalog_fingerprint": (payload.get("source") or {}).get("knowledge_product_catalog_fingerprint"),
        "knowledge_product_catalog_source": (payload.get("source") or {}).get("knowledge_product_catalog_source"),
        "output": str(target),
        "markdown": str(markdown_target) if markdown_target is not None else None,
        "knowledge_type_count": (payload.get("summary") or {}).get("knowledge_type_count"),
        "profile_v2_selectable_count": (payload.get("summary") or {}).get("profile_v2_selectable_count"),
        "runtime_status_counts": (payload.get("summary") or {}).get("runtime_status_counts"),
        "next_step": payload.get("next_step"),
    }, ensure_ascii=False, indent=2, sort_keys=True))


@app.command("knowledge-profile-resolve")
def knowledge_profile_resolve(
    catalog_path: Path = typer.Option(..., "--knowledge-catalog", exists=True, dir_okay=False),
    profile_path: Path = typer.Option(..., "--profile", exists=True, dir_okay=False),
    output: Path = typer.Option(..., "--output", dir_okay=False),
    markdown: Optional[Path] = typer.Option(None, "--markdown", dir_okay=False),
) -> None:
    """Resolve a user knowledge profile into a read-only KLC/Core source plan."""
    try:
        catalog = load_knowledge_json(catalog_path, label="knowledge catalog")
        profile = load_knowledge_profile(profile_path)
        payload = resolve_knowledge_profile(catalog, profile)
        target = write_knowledge_json(output, payload)
        markdown_target = (
            write_knowledge_markdown(markdown, render_knowledge_resolution_markdown(payload))
            if markdown is not None
            else None
        )
    except Exception as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(json.dumps({
        "schema_version": payload["schema_version"],
        "plan_fingerprint": payload["plan_fingerprint"],
        "output": str(target),
        "markdown": str(markdown_target) if markdown_target is not None else None,
        "profile_id": (payload.get("profile") or {}).get("profile_id"),
        "scope": (payload.get("profile") or {}).get("scope"),
        "requested_knowledge_count": (payload.get("status") or {}).get("requested_knowledge_count"),
        "resolved_knowledge_count": (payload.get("status") or {}).get("resolved_knowledge_count"),
        "implicit_required_dependency_count": (payload.get("status") or {}).get("implicit_required_dependency_count"),
        "overall_status": (payload.get("status") or {}).get("overall"),
        "execution_effect": payload.get("execution_effect"),
    }, ensure_ascii=False, indent=2, sort_keys=True))


@app.command("knowledge-input-prepare")
def knowledge_input_prepare(
    scope_kind: str = typer.Option(..., "--scope-kind"),
    scope_id: str = typer.Option(..., "--scope-id"),
    repositories: list[Path] = typer.Option([], "--repository", exists=True, file_okay=False),
    repository_metadata_json: list[str] = typer.Option([], "--repository-metadata-json"),
    physical_model: Path | None = typer.Option(None, "--physical-model", exists=True, dir_okay=False),
    published_revisions: list[Path] = typer.Option([], "--published-revision", exists=True, dir_okay=False),
    core_evidence_catalog: Path = typer.Option(..., "--core-evidence-catalog", exists=True, dir_okay=False),
    materialization_catalog: Path = typer.Option(..., "--materialization-catalog", exists=True, dir_okay=False),
    preparation_root: Path = typer.Option(..., "--preparation-root", file_okay=False),
    core_command: str = typer.Option("code-analyzer-core", "--core-command"),
    producer_cache_root: Path | None = typer.Option(None, "--producer-cache-root", file_okay=False),
    force_rebuild: bool = typer.Option(False, "--force-rebuild"),
    reuse_decision_output: Path | None = typer.Option(None, "--reuse-decision-output", dir_okay=False),
    output: Path = typer.Option(..., "--output", dir_okay=False),
) -> None:
    """Normalize raw execution context into knowledge_input_inventory/v1.

    This is the control-plane boundary: callers provide repositories, optional raw PDM,
    and immutable published-revision snapshots. Runner owns Core invocation and typed
    artifact normalization.
    """
    try:
        revisions = [(path, read_runtime_json(path)) for path in published_revisions]
        repository_metadata: dict[str, dict] = {}
        for raw in repository_metadata_json:
            value = json.loads(raw)
            if not isinstance(value, dict) or not str(value.get("source_id") or "").strip():
                raise ValueError("--repository-metadata-json must be a JSON object with source_id")
            source_id = str(value.pop("source_id")).strip()
            if source_id in repository_metadata:
                raise ValueError(f"duplicate repository metadata source_id: {source_id}")
            repository_metadata[source_id] = value
        payload = prepare_knowledge_input_inventory(
            scope_kind=scope_kind,
            scope_id=scope_id,
            repositories=repositories,
            core_evidence_catalog=read_runtime_json(core_evidence_catalog),
            materialization_catalog=read_runtime_json(materialization_catalog),
            preparation_root=preparation_root,
            physical_model_path=physical_model,
            published_revisions=revisions,
            core_command=core_command,
            producer_cache_root=producer_cache_root,
            force_rebuild=force_rebuild,
            reuse_decision_path=reuse_decision_output,
            progress=_progress,
            repository_metadata_by_source_id=repository_metadata,
        )
        write_runtime_json(output, payload)
    except Exception as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(json.dumps({
        "schema_version": payload["schema_version"],
        "inventory_fingerprint": payload["inventory_fingerprint"],
        "scope": payload["scope"],
        "summary": payload["summary"],
        "output": str(output),
    }, ensure_ascii=False, indent=2, sort_keys=True))


@app.command("knowledge-input-inventory")
def knowledge_input_inventory(
    scope_kind: str = typer.Option(..., "--scope-kind"),
    scope_id: str = typer.Option(..., "--scope-id"),
    repositories: list[Path] = typer.Option([], "--repository", exists=True, file_okay=False),
    repository_run_manifests: list[Path] = typer.Option([], "--repository-run-manifest", exists=True, dir_okay=False),
    typed_artifact_descriptors: list[Path] = typer.Option([], "--typed-artifact-descriptor", exists=True, dir_okay=False),
    materialization_results: list[Path] = typer.Option([], "--materialization-result", exists=True, dir_okay=False),
    knowledge_artifact_descriptors: list[Path] = typer.Option([], "--knowledge-artifact-descriptor", exists=True, dir_okay=False),
    core_evidence_catalog: Path = typer.Option(..., "--core-evidence-catalog", exists=True, dir_okay=False),
    materialization_catalog: Path = typer.Option(..., "--materialization-catalog", exists=True, dir_okay=False),
    output: Path = typer.Option(..., "--output", dir_okay=False),
) -> None:
    """Inspect actual run inputs and publish knowledge_input_inventory/v1."""
    try:
        source_snapshots = [inspect_repository_source(path) for path in repositories]
        typed_artifacts = [
            read_runtime_json(path) for path in typed_artifact_descriptors
        ]
        for manifest_path in repository_run_manifests:
            typed_artifacts.extend(artifacts_from_repository_run_manifest(manifest_path))
        knowledge_artifacts = [
            read_runtime_json(path) for path in knowledge_artifact_descriptors
        ]
        for result_path in materialization_results:
            knowledge_artifacts.extend(knowledge_from_materialization_result(result_path))
        payload = build_knowledge_input_inventory(
            scope_kind=scope_kind,
            scope_id=scope_id,
            source_snapshots=source_snapshots,
            core_evidence_catalog=read_runtime_json(core_evidence_catalog),
            materialization_catalog=read_runtime_json(materialization_catalog),
            typed_artifacts=typed_artifacts,
            knowledge_artifacts=knowledge_artifacts,
        )
        write_runtime_json(output, payload)
    except Exception as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(json.dumps({
        "schema_version": payload["schema_version"],
        "inventory_fingerprint": payload["inventory_fingerprint"],
        "scope": payload["scope"],
        "summary": payload["summary"],
        "output": str(output),
    }, ensure_ascii=False, indent=2, sort_keys=True))


@app.command("knowledge-execution-plan")
def knowledge_execution_plan(
    knowledge_catalog: Path = typer.Option(..., "--knowledge-catalog", exists=True, dir_okay=False),
    profile: Path = typer.Option(..., "--profile", exists=True, dir_okay=False),
    input_inventory: Path = typer.Option(..., "--input-inventory", exists=True, dir_okay=False),
    core_evidence_catalog: Path = typer.Option(..., "--core-evidence-catalog", exists=True, dir_okay=False),
    materialization_catalog: Path = typer.Option(..., "--materialization-catalog", exists=True, dir_okay=False),
    output: Path = typer.Option(..., "--output", dir_okay=False),
) -> None:
    """Compile Knowledge Profile and actual inputs into knowledge_execution_plan/v1."""
    try:
        payload = compile_knowledge_execution_plan(
            knowledge_catalog=read_runtime_json(knowledge_catalog),
            knowledge_profile=load_knowledge_profile(profile),
            input_inventory=read_runtime_json(input_inventory),
            core_evidence_catalog=read_runtime_json(core_evidence_catalog),
            materialization_catalog=read_runtime_json(materialization_catalog),
        )
        write_runtime_json(output, payload)
    except Exception as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(json.dumps({
        "schema_version": payload["schema_version"],
        "plan_fingerprint": payload["plan_fingerprint"],
        "scope": payload["scope"],
        "status": payload["status"],
        "execution_order": (payload.get("graph") or {}).get("execution_order"),
        "output": str(output),
    }, ensure_ascii=False, indent=2, sort_keys=True))


@app.command("knowledge-execute")
def knowledge_execute(
    execution_plan: Path = typer.Option(..., "--execution-plan", exists=True, dir_okay=False),
    core_evidence_catalog: Path = typer.Option(..., "--core-evidence-catalog", exists=True, dir_okay=False),
    materialization_catalog: Path = typer.Option(..., "--materialization-catalog", exists=True, dir_okay=False),
    output: Path = typer.Option(..., "--output", file_okay=False),
    core_command: str = typer.Option("code-analyzer-core", "--core-command"),
    replace: bool = typer.Option(False, "--replace/--no-replace"),
    duckdb_memory_limit: str = typer.Option("1GB", "--duckdb-memory-limit"),
    duckdb_threads: int = typer.Option(1, "--duckdb-threads", min=1),
    producer_cache_root: Path | None = typer.Option(None, "--producer-cache-root", file_okay=False),
    force_rebuild: bool = typer.Option(False, "--force-rebuild"),
) -> None:
    """Execute knowledge_execution_plan/v1 as the canonical product runtime."""
    try:
        payload = execute_knowledge_execution_plan(
            execution_plan=execution_plan,
            core_evidence_catalog=core_evidence_catalog,
            materialization_catalog=materialization_catalog,
            output=output,
            core_command=core_command,
            replace=replace,
            duckdb_memory_limit=duckdb_memory_limit,
            duckdb_threads=duckdb_threads,
            producer_cache_root=producer_cache_root,
            force_rebuild=force_rebuild,
            progress=_progress,
        )
    except Exception as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(json.dumps({
        "schema_version": payload["schema_version"],
        "status": payload["status"],
        "scope": payload["scope"],
        "execution_order": payload["execution_order"],
        "evidence_artifact_count": len(payload.get("evidence_artifacts") or []),
        "materialization_count": len(payload.get("materialization_executions") or []),
        "knowledge_artifact_count": len(payload.get("knowledge_artifacts") or []),
        "producer_reuse": payload.get("producer_reuse") or {},
        "published_capabilities": payload.get("published_capabilities") or [],
        "result_fingerprint": payload.get("result_fingerprint"),
        "output": str(output),
    }, ensure_ascii=False, indent=2, sort_keys=True))


@app.command("evidence-execute")
def evidence_execute(
    repository: Path = typer.Option(..., "--repository", exists=True, file_okay=False),
    resolution_plan: Path = typer.Option(..., "--resolution-plan", exists=True, dir_okay=False),
    core_evidence_catalog: Path = typer.Option(..., "--core-evidence-catalog", exists=True, dir_okay=False),
    output: Path = typer.Option(..., "--output", file_okay=False),
    core_command: str = typer.Option("code-analyzer-core", "--core-command"),
    repo_id: Optional[str] = typer.Option(None, "--repo-id"),
    replace: bool = typer.Option(False, "--replace/--no-replace"),
) -> None:
    """Low-level diagnostic Core evidence execution; not the product knowledge route."""
    try:
        payload = execute_core_evidence_plan(
            repository=repository,
            resolution_plan=resolution_plan,
            core_evidence_catalog=core_evidence_catalog,
            output=output,
            core_command=core_command,
            repo_id=repo_id,
            replace=replace,
            progress=_progress,
        )
    except Exception as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(json.dumps({
        "schema_version": payload["schema_version"],
        "status": payload["status"],
        "repo_id": (payload.get("repository") or {}).get("repo_id"),
        "analyzer_execution_count": len(payload.get("analyzer_executions") or []),
        "evidence_artifact_count": len(payload.get("evidence_artifacts") or []),
        "run_fingerprint": payload.get("run_fingerprint"),
        "output": str(output),
    }, ensure_ascii=False, indent=2, sort_keys=True))


@app.command("knowledge-materialize")
def knowledge_materialize(
    resolution_plan: Path = typer.Option(..., "--resolution-plan", exists=True, dir_okay=False),
    materialization_catalog: Path = typer.Option(..., "--materialization-catalog", exists=True, dir_okay=False),
    repository_run_manifests: list[Path] = typer.Option([], "--repository-run-manifest", exists=True, dir_okay=False),
    existing_results: list[Path] = typer.Option([], "--existing-materialization-result", exists=True, dir_okay=False),
    output: Path = typer.Option(..., "--output", file_okay=False),
    scope_id: Optional[str] = typer.Option(None, "--scope-id"),
    replace: bool = typer.Option(False, "--replace"),
    duckdb_memory_limit: str = typer.Option("1GB", "--duckdb-memory-limit"),
    duckdb_threads: int = typer.Option(1, "--duckdb-threads", min=1),
) -> None:
    """Low-level diagnostic KLC execution; the product route is knowledge-execute."""
    try:
        payload = execute_knowledge_materialization_plan(
            resolution_plan=resolution_plan,
            materialization_catalog=materialization_catalog,
            repository_run_manifests=repository_run_manifests,
            existing_materialization_results=existing_results,
            output=output,
            scope_id=scope_id,
            replace=replace,
            duckdb_memory_limit=duckdb_memory_limit,
            duckdb_threads=duckdb_threads,
        )
    except Exception as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(json.dumps({
        "schema_version": payload["schema_version"],
        "status": payload["status"],
        "scope_id": payload["scope_id"],
        "execution_order": payload["execution_order"],
        "materialization_count": len(payload["materialization_executions"]),
        "knowledge_artifact_count": len(payload["knowledge_artifacts"]),
        "published_capabilities": payload["published_capabilities"],
        "execution_fingerprint": payload["execution_fingerprint"],
        "output": str(output),
    }, ensure_ascii=False, indent=2, sort_keys=True))


@app.command("repository-batch-discover")
def repository_batch_discover(
    bitbucket_project_url: str = typer.Option(..., "--bitbucket-project-url"),
    output: Path = typer.Option(..., "--output", dir_okay=False),
    auth_mode: str = typer.Option("auto", "--auth-mode"),
    token_env: str = typer.Option("BITBUCKET_TOKEN", "--token-env"),
    username_env: str = typer.Option("BITBUCKET_USERNAME", "--username-env"),
    password_env: str = typer.Option("BITBUCKET_PASSWORD", "--password-env"),
    api_base_path: str = typer.Option("/rest/api/latest", "--api-base-path"),
    ca_bundle: Optional[Path] = typer.Option(None, "--ca-bundle", exists=True, dir_okay=False),
    insecure_skip_tls_verify: bool = typer.Option(False, "--insecure-skip-tls-verify"),
    timeout_seconds: float = typer.Option(60.0, "--timeout-seconds", min=1.0),
    page_size: int = typer.Option(100, "--page-size", min=1, max=1000),
    max_repositories: Optional[int] = typer.Option(
        None, "--repository-limit", "--max-repositories", min=1,
    ),
) -> None:
    """Discover Bitbucket repositories without cloning or analyzing them."""
    try:
        payload = discover_bitbucket_project_repositories(
            project_url=bitbucket_project_url,
            auth_mode=auth_mode,
            token_env=token_env,
            username_env=username_env,
            password_env=password_env,
            api_base_path=api_base_path,
            ca_bundle=ca_bundle,
            insecure_skip_tls_verify=insecure_skip_tls_verify,
            timeout_seconds=timeout_seconds,
            page_size=page_size,
            max_repositories=max_repositories,
        ).to_dict()
        write_runtime_json(output, payload)
    except Exception as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(json.dumps({
        "schema_version": payload["schema_version"],
        "repository_count": len(payload.get("repositories") or []),
        "repository_source_fingerprint": payload.get("portfolio_fingerprint"),
        "output": str(output),
    }, ensure_ascii=False, indent=2, sort_keys=True))


@app.command("repository-batch-run")
def repository_batch_run(
    output: Path = typer.Option(..., "--output", file_okay=False),
    work_dir: Path = typer.Option(..., "--work-dir", file_okay=False),
    knowledge_profile: Path = typer.Option(..., "--knowledge-profile", exists=True, dir_okay=False),
    knowledge_catalog: Path = typer.Option(..., "--knowledge-catalog", exists=True, dir_okay=False),
    core_evidence_catalog: Path = typer.Option(..., "--core-evidence-catalog", exists=True, dir_okay=False),
    materialization_catalog: Path = typer.Option(..., "--materialization-catalog", exists=True, dir_okay=False),
    bitbucket_project_url: Optional[str] = typer.Option(None, "--bitbucket-project-url"),
    repository_sources: Optional[Path] = typer.Option(
        None, "--repository-sources", exists=True, dir_okay=False,
        help="Offline/discovery input using the existing repository source manifest contract.",
    ),
    core_command: str = typer.Option("code-analyzer-core", "--core-command"),
    auth_mode: str = typer.Option("auto", "--auth-mode"),
    token_env: str = typer.Option("BITBUCKET_TOKEN", "--token-env"),
    username_env: str = typer.Option("BITBUCKET_USERNAME", "--username-env"),
    password_env: str = typer.Option("BITBUCKET_PASSWORD", "--password-env"),
    api_base_path: str = typer.Option("/rest/api/latest", "--api-base-path"),
    ca_bundle: Optional[Path] = typer.Option(None, "--ca-bundle", exists=True, dir_okay=False),
    insecure_skip_tls_verify: bool = typer.Option(False, "--insecure-skip-tls-verify"),
    timeout_seconds: float = typer.Option(60.0, "--timeout-seconds", min=1.0),
    page_size: int = typer.Option(100, "--page-size", min=1, max=1000),
    max_repositories: Optional[int] = typer.Option(
        None, "--repository-limit", "--max-repositories", min=1,
    ),
    clone_retries: int = typer.Option(2, "--clone-retries", min=0, max=10),
    clone_timeout_seconds: float = typer.Option(300.0, "--clone-timeout-seconds", min=1.0),
    producer_cache_root: Optional[Path] = typer.Option(None, "--producer-cache-root", file_okay=False),
    force_rebuild: bool = typer.Option(False, "--force-rebuild"),
    duckdb_memory_limit: str = typer.Option("1GB", "--duckdb-memory-limit"),
    duckdb_threads: int = typer.Option(1, "--duckdb-threads", min=1),
    replace: bool = typer.Option(False, "--replace/--no-replace"),
) -> None:
    """Run one repository-scoped Knowledge Profile independently for every repository."""
    try:
        result = run_repository_batch(
            output=output,
            work_dir=work_dir,
            knowledge_profile=knowledge_profile,
            knowledge_catalog=knowledge_catalog,
            core_evidence_catalog=core_evidence_catalog,
            materialization_catalog=materialization_catalog,
            bitbucket_project_url=bitbucket_project_url,
            repository_sources=repository_sources,
            core_command=core_command,
            auth_mode=auth_mode,
            token_env=token_env,
            username_env=username_env,
            password_env=password_env,
            api_base_path=api_base_path,
            ca_bundle=ca_bundle,
            insecure_skip_tls_verify=insecure_skip_tls_verify,
            timeout_seconds=timeout_seconds,
            page_size=page_size,
            max_repositories=max_repositories,
            clone_retries=clone_retries,
            clone_timeout_seconds=clone_timeout_seconds,
            producer_cache_root=producer_cache_root,
            force_rebuild=force_rebuild,
            duckdb_memory_limit=duckdb_memory_limit,
            duckdb_threads=duckdb_threads,
            replace=replace,
            progress=_progress,
        )
    except Exception as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(json.dumps(result.summary, ensure_ascii=False, indent=2, sort_keys=True))


@app.command("data-model-discovery")
def data_model_discovery(
    output: Path = typer.Option(..., "--output", file_okay=False),
    work_dir: Path = typer.Option(..., "--work-dir", file_okay=False),
    bitbucket_project_url: Optional[str] = typer.Option(None, "--bitbucket-project-url"),
    repository_sources: Optional[Path] = typer.Option(
        None, "--repository-sources", exists=True, dir_okay=False,
        help="Offline/test input using portfolio_repository_sources/v1.",
    ),
    core_command: str = typer.Option("code-analyzer-core", "--core-command"),
    auth_mode: str = typer.Option("auto", "--auth-mode"),
    token_env: str = typer.Option("BITBUCKET_TOKEN", "--token-env"),
    username_env: str = typer.Option("BITBUCKET_USERNAME", "--username-env"),
    password_env: str = typer.Option("BITBUCKET_PASSWORD", "--password-env"),
    api_base_path: str = typer.Option("/rest/api/latest", "--api-base-path"),
    ca_bundle: Optional[Path] = typer.Option(None, "--ca-bundle", exists=True, dir_okay=False),
    insecure_skip_tls_verify: bool = typer.Option(False, "--insecure-skip-tls-verify"),
    timeout_seconds: float = typer.Option(60.0, "--timeout-seconds", min=1.0),
    page_size: int = typer.Option(100, "--page-size", min=1, max=1000),
    max_repositories: Optional[int] = typer.Option(
        None, "--repository-limit", "--max-repositories", min=1,
        help="Analyze only the first N repositories returned by Bitbucket or listed in the source manifest.",
    ),
    clone_retries: int = typer.Option(2, "--clone-retries", min=0, max=10),
    clone_timeout_seconds: float = typer.Option(300.0, "--clone-timeout-seconds", min=1.0),
    replace: bool = typer.Option(False, "--replace/--no-replace"),
) -> None:
    """Scan a Bitbucket project and return ranked data-model repository candidates."""
    try:
        result = run_data_model_discovery(
            output=output, work_dir=work_dir,
            bitbucket_project_url=bitbucket_project_url, repository_sources=repository_sources,
            core_command=core_command, auth_mode=auth_mode,
            token_env=token_env, username_env=username_env, password_env=password_env,
            api_base_path=api_base_path, ca_bundle=ca_bundle,
            insecure_skip_tls_verify=insecure_skip_tls_verify, timeout_seconds=timeout_seconds,
            page_size=page_size, max_repositories=max_repositories, clone_retries=clone_retries,
            clone_timeout_seconds=clone_timeout_seconds,
            replace=replace, progress=_progress,
        )
    except Exception as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(json.dumps(result.summary, ensure_ascii=False, indent=2, sort_keys=True))


