from __future__ import annotations

import hashlib
import threading
from importlib.resources import files
from dataclasses import replace
from pathlib import Path
from time import perf_counter
from typing import Any, Callable, TypeVar

import yaml

from .contracts import PreparedReport, ReportRequest, ReportRunManifest
from .deterministic_er import apply_deterministic_er_section
from .er_correction import ER_CORRECTION_PROMPT, correction_dataset, merge_er_section
from .files import canonical_json, sha256_text, write_json
from .profile import load_profile
from aisl_sdk import AislClient
from .knowledge_api import KnowledgeApiSourceError, resolve_revision, select_artifact
from .progress import ProgressCallback
from .renderer import Renderer, renderer_messages
from .mermaid import normalize_mermaid_markdown
from .validation import validate_dataset, validate_markdown_report

_T = TypeVar("_T")


def _required_headings(contract: dict[str, Any], request: ReportRequest) -> list[str]:
    audience_headings = contract.get("audience_required_headings") or {}
    headings = [str(value) for value in (audience_headings.get(request.audience) or [])]
    headings.extend(str(value) for value in (contract.get("required_headings") or []))
    return list(dict.fromkeys(headings))


def _emit(progress: ProgressCallback | None, level: str, message: str) -> None:
    if progress is not None:
        progress(level, message)


def _has_warning(validation: dict[str, Any], code: str) -> bool:
    return any(str(item.get("code") or "") == code for item in (validation.get("warnings") or ()))


def _append_warning(validation: dict[str, Any], *, code: str, message: str, details: dict[str, Any]) -> None:
    warnings = list(validation.get("warnings") or ())
    warnings.append({"code": code, "message": message, "details": details})
    validation["warnings"] = warnings
    validation["conforms"] = False


def _run_stage(
    name: str,
    operation: Callable[[], _T],
    *,
    progress: ProgressCallback | None,
    heartbeat_sec: int,
) -> _T:
    started = perf_counter()
    _emit(progress, "INFO", f"{name}: started")
    stop = threading.Event()
    heartbeat: threading.Thread | None = None

    if progress is not None and heartbeat_sec > 0:
        def beat() -> None:
            while not stop.wait(heartbeat_sec):
                elapsed = perf_counter() - started
                _emit(progress, "INFO", f"{name}: still running ({elapsed:.1f}s elapsed)")

        heartbeat = threading.Thread(target=beat, name="aisl-reporting-heartbeat", daemon=True)
        heartbeat.start()

    try:
        result = operation()
    except Exception as exc:
        elapsed = perf_counter() - started
        _emit(progress, "ERROR", f"{name}: failed after {elapsed:.1f}s: {type(exc).__name__}: {exc}")
        raise
    finally:
        stop.set()
        if heartbeat is not None:
            heartbeat.join(timeout=1.0)

    elapsed = perf_counter() - started
    _emit(progress, "SUCCESS", f"{name}: completed in {elapsed:.1f}s")
    return result




def _renderer_prompt_with_common_policy(
    base_prompt: str,
    contract: dict[str, Any],
    request: ReportRequest,
) -> str:
    policy = (
        files("aisl_reporting.profiles.common.v1")
        .joinpath("editorial-policy.md")
        .read_text(encoding="utf-8")
        .strip()
    )
    if not policy:
        raise ValueError("common reporting policy must not be empty")
    headings = _required_headings(contract, request)
    if not headings:
        raise ValueError(f"profile {request.profile_id} must define required headings")
    structure = "\n".join(f"{index}. `{heading}`" for index, heading in enumerate(headings, start=1))
    return (
        policy
        + "\n\n# Обязательная структура текущего профиля\n\n"
        + "Сформируй разделы верхнего уровня в следующем порядке и используй заголовки дословно:\n\n"
        + structure
        + "\n\n# Профильные правила\n\n"
        + base_prompt.strip()
        + "\n"
    )


def _renderer_prompt_with_explicit_instructions(base_prompt: str, request: ReportRequest) -> str:
    sections: list[str] = []
    for path in request.instruction_files:
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            raise ValueError(f"instruction file must not be empty: {path}")
        sections.append(f"## {path.name}\n{text}")
    if not sections:
        return base_prompt
    return (
        base_prompt.rstrip()
        + "\n\n# Явные дополнительные инструкции пользователя/профиля\n"
        + "Применяй следующий блок только как явно предоставленное правило. "
          "Он не является фактом Knowledge Layer и не должен менять evidence/provenance.\n\n"
        + "\n\n".join(sections)
        + "\n"
    )

def prepare_report(
    request: ReportRequest,
    *,
    progress: ProgressCallback | None = None,
    heartbeat_sec: int = 20,
) -> PreparedReport:
    _emit(progress, "INFO", f"Loading profile {request.profile_id}")
    profile = load_profile(request.profile_id)
    resolved_request = request
    knowledge_client: AislClient | None = None
    requirement = profile.knowledge_requirement
    if requirement is None:
        raise KnowledgeApiSourceError(
            f"profile {profile.profile_id} does not declare its required knowledge"
        )
    knowledge_client = AislClient(
        str(request.api_url),
        transport=request.api_transport,
    )
    revision = resolve_revision(knowledge_client, str(request.system_id), request.revision_id)
    selected = select_artifact(revision, requirement)
    source = revision.with_selected(selected)
    resolved_request = replace(
        request,
        revision_id=revision.revision_id,
        knowledge_source=source,
    )
    _emit(
        progress,
        "INFO",
        "Input: kind=knowledge_api_revision, "
        f"system={source.system_id}, revision={source.revision_id}, "
        f"model={selected.get('model_kind')}, artifact={selected.get('artifact_id')}",
    )

    try:
        dataset = _run_stage(
            "Building deterministic report dataset",
            lambda: profile.builder(resolved_request),
            progress=progress,
            heartbeat_sec=heartbeat_sec,
        )
    finally:
        if knowledge_client is not None:
            knowledge_client.close()
    if resolved_request.knowledge_source is not None:
        request_payload = dict(dataset.get("request") or resolved_request.to_dataset_dict())
        request_payload["knowledge_source"] = resolved_request.knowledge_source.to_dict()
        dataset["request"] = request_payload
        fingerprint_material = {key: value for key, value in dataset.items() if key != "dataset_fingerprint"}
        dataset["dataset_fingerprint"] = sha256_text(canonical_json(fingerprint_material))
    contract = yaml.safe_load(profile.text("report-contract.yaml")) or {}
    rules = yaml.safe_load(profile.text("quality-rules.yaml")) or {}
    max_bytes = int(rules.get("max_dataset_bytes") or 200_000)
    validation = _run_stage(
        "Validating report dataset",
        lambda: validate_dataset(
            dataset,
            profile.resource_dir.joinpath("report-dataset.schema.json"),
            max_bytes=max_bytes,
        ),
        progress=progress,
        heartbeat_sec=heartbeat_sec,
    )
    dataset["validation"] = validation
    _emit(
        progress,
        "INFO",
        f"Dataset ready: {validation['dataset_bytes']} bytes, {validation['evidence_count']} evidence refs",
    )
    return PreparedReport(
        request=resolved_request,
        dataset=dataset,
        renderer_prompt=_renderer_prompt_with_explicit_instructions(
            _renderer_prompt_with_common_policy(profile.text("renderer-prompt.md"), contract, request),
            request,
        ),
        profile_dir=profile.path_hint(),
    )


def write_prepared_report(
    prepared: PreparedReport,
    output_dir: Path,
    *,
    progress: ProgressCallback | None = None,
    log_path: Path | None = None,
) -> ReportRunManifest:
    output_dir.mkdir(parents=True, exist_ok=True)
    dataset_path = output_dir / "report-dataset.json"
    prompt_path = output_dir / "renderer-prompt.md"
    messages_path = output_dir / "renderer-messages.json"
    write_json(dataset_path, prepared.dataset)
    prompt_path.write_text(prepared.renderer_prompt.rstrip() + "\n", encoding="utf-8")
    write_json(messages_path, renderer_messages(prepared.renderer_prompt, prepared.dataset))
    manifest = ReportRunManifest(
        request=prepared.request,
        dataset_path=dataset_path,
        prompt_path=prompt_path,
        report_path=None,
        dataset_sha256=sha256_text(canonical_json(prepared.dataset)),
        prompt_sha256=sha256_text(prepared.renderer_prompt),
        report_sha256=None,
        validation={"dataset": prepared.dataset.get("validation") or {}},
        status="prepared",
        log_path=log_path,
    )
    write_json(output_dir / "report-run-manifest.json", manifest.to_dict())
    _emit(progress, "INFO", f"Prepared artifacts written to {output_dir}")
    return manifest


def build_report(
    request: ReportRequest,
    output_dir: Path,
    renderer: Renderer,
    *,
    progress: ProgressCallback | None = None,
    heartbeat_sec: int = 20,
    log_path: Path | None = None,
) -> ReportRunManifest:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    _emit(progress, "INFO", f"Report build started: profile={request.profile_id}")

    prepared = prepare_report(request, progress=progress, heartbeat_sec=heartbeat_sec)
    initial = write_prepared_report(prepared, output_dir, progress=progress, log_path=log_path)

    renderer_description = getattr(renderer, "description", renderer.__class__.__name__)
    _emit(progress, "INFO", f"Renderer: {renderer_description}")
    report = _run_stage(
        "Rendering report",
        lambda: renderer.render(prompt=prepared.renderer_prompt, dataset=prepared.dataset),
        progress=progress,
        heartbeat_sec=heartbeat_sec,
    )
    if not report.strip():
        raise ValueError("renderer returned an empty report")

    report, deterministic_er = apply_deterministic_er_section(report, prepared.dataset)
    if deterministic_er.get("applied"):
        _emit(progress, "SUCCESS", "Replaced the model-authored ER section with deterministic Mermaid from report dataset")

    report, mermaid_normalization = normalize_mermaid_markdown(report)
    if mermaid_normalization.changed_block_count:
        _emit(
            progress,
            "INFO",
            "Normalized Mermaid syntax in "
            f"{mermaid_normalization.changed_block_count}/{mermaid_normalization.block_count} block(s)",
        )

    # Preserve the model output before quality validation. A structural warning must
    # never destroy an otherwise useful report.
    report_path = output_dir / request.output_name
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")
    _emit(progress, "SUCCESS", f"Rendered report saved: {report_path} ({len(report.encode('utf-8'))} bytes)")

    profile = load_profile(request.profile_id)
    contract = yaml.safe_load(profile.text("report-contract.yaml")) or {}
    required_headings = _required_headings(contract, request)
    validation = _run_stage(
        "Validating rendered report",
        lambda: validate_markdown_report(
            report,
            prepared.dataset,
            required_headings,
        ),
        progress=progress,
        heartbeat_sec=heartbeat_sec,
    )
    validation["mermaid_normalization"] = mermaid_normalization.to_dict()
    validation["deterministic_er"] = deterministic_er

    correction_status: dict[str, Any] = {
        "required": _has_warning(validation, "missing_required_er_diagram"),
        "supported": bool(getattr(renderer, "supports_correction", False)),
        "attempted": False,
        "applied": False,
        "status": "not_required",
    }
    if correction_status["required"]:
        required_layers = [str(value) for value in validation.get("required_er_diagram_layers") or ()]
        if correction_status["supported"]:
            correction_status.update({"attempted": True, "status": "running", "required_layers": required_layers})
            correction_path = output_dir / "report-er-correction.md"
            candidate_path = output_dir / "report-er-correction-candidate.md"
            try:
                correction = _run_stage(
                    "Correcting missing ER diagrams",
                    lambda: renderer.render(
                        prompt=ER_CORRECTION_PROMPT,
                        dataset=correction_dataset(prepared.dataset, required_layers),
                    ),
                    progress=progress,
                    heartbeat_sec=heartbeat_sec,
                )
                if not correction.strip():
                    raise ValueError("renderer returned an empty ER correction")
                correction, correction_normalization = normalize_mermaid_markdown(correction)
                correction_path.write_text(correction, encoding="utf-8")
                candidate = merge_er_section(report, correction)
                candidate, candidate_normalization = normalize_mermaid_markdown(candidate)
                candidate_path.write_text(candidate, encoding="utf-8")
                candidate_validation = _run_stage(
                    "Validating ER correction candidate",
                    lambda: validate_markdown_report(candidate, prepared.dataset, required_headings),
                    progress=progress,
                    heartbeat_sec=heartbeat_sec,
                )
                candidate_validation["mermaid_normalization"] = candidate_normalization.to_dict()
                if _has_warning(candidate_validation, "missing_required_er_diagram"):
                    correction_status.update({
                        "status": "rejected",
                        "reason": "candidate_still_missing_required_er_diagram",
                        "correction_path": str(correction_path),
                        "candidate_path": str(candidate_path),
                        "correction_mermaid_normalization": correction_normalization.to_dict(),
                    })
                    _append_warning(
                        validation,
                        code="er_diagram_correction_rejected",
                        message="automatic ER correction was rejected because required ER diagrams are still missing",
                        details={"required_layers": required_layers, "candidate_path": str(candidate_path)},
                    )
                else:
                    backup_path = output_dir / f"{report_path.stem}.before-er-correction{report_path.suffix}"
                    backup_path.write_text(report, encoding="utf-8")
                    report = candidate
                    report_path.write_text(report, encoding="utf-8")
                    validation = candidate_validation
                    correction_status.update({
                        "applied": True,
                        "status": "applied",
                        "backup_path": str(backup_path),
                        "correction_path": str(correction_path),
                        "candidate_path": str(candidate_path),
                        "correction_mermaid_normalization": correction_normalization.to_dict(),
                    })
                    _emit(progress, "SUCCESS", f"ER correction applied; original report preserved at {backup_path}")
            except Exception as exc:
                correction_status.update({
                    "status": "failed",
                    "exception_type": type(exc).__name__,
                    "message": str(exc)[:500],
                })
                _append_warning(
                    validation,
                    code="er_diagram_correction_failed",
                    message=f"automatic ER correction failed: {type(exc).__name__}: {exc}",
                    details={"required_layers": required_layers, "exception_type": type(exc).__name__},
                )
                _emit(progress, "WARNING", "ER correction failed; the original rendered report remains unchanged")
        else:
            correction_status.update({
                "status": "not_supported",
                "required_layers": required_layers,
            })
            _emit(progress, "WARNING", "Renderer does not support an automatic ER correction pass")

    validation["er_correction"] = correction_status
    validation_path = output_dir / "report-validation.json"
    write_json(validation_path, validation)

    warning_messages = tuple(item["message"] for item in validation.get("warnings") or ())
    all_messages = warning_messages
    for message in warning_messages:
        _emit(progress, "WARNING", message)

    status = "completed_with_warnings" if warning_messages else "completed"

    final = ReportRunManifest(
        request=prepared.request,
        dataset_path=initial.dataset_path,
        prompt_path=initial.prompt_path,
        report_path=report_path,
        dataset_sha256=initial.dataset_sha256,
        prompt_sha256=initial.prompt_sha256,
        report_sha256=hashlib.sha256(report.encode("utf-8")).hexdigest(),
        validation={"dataset": prepared.dataset.get("validation"), "report": validation},
        status=status,
        warnings=all_messages,
        validation_path=validation_path,
        log_path=log_path,
    )
    manifest_path = output_dir / "report-run-manifest.json"
    write_json(manifest_path, final.to_dict())
    _emit(progress, "INFO", f"Run manifest updated: {manifest_path}")

    if all_messages:
        _emit(progress, "WARNING", f"Report returned with {len(all_messages)} validation issue(s); see {validation_path}")
    else:
        _emit(progress, "SUCCESS", "Report validation passed")
    return final
