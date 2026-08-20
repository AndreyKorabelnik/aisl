from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
import re

from knowledge_control_plane.api.generic_v1.models import JobKind, JobOutputOptions

from .configuration import ConfigurationService
from .errors import UnsafePath

UI_OUTPUT_MARKER = ".knowledge-control-plane-output.json"
RUNNER_OUTPUT_MARKER = ".static-analysis-runner-output.json"
RUN_INFO_FILE = "RUN_INFO.json"


def _safe_segment(value: str) -> str:
    segment = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip(".-")
    return segment or "unknown"


def _short_job_id(job_id: str) -> str:
    token = job_id[4:] if job_id.startswith("job-") else job_id
    return f"job-{_safe_segment(token)[:8]}"


def _run_stamp(created_at: datetime | None) -> str:
    if created_at is None:
        return "preview"
    value = created_at if created_at.tzinfo is not None else created_at.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


class OutputSafety:
    def __init__(self, configuration: ConfigurationService) -> None:
        self.configuration = configuration

    def resolve(
        self,
        *,
        job_id: str,
        kind: JobKind,
        options: JobOutputOptions,
        protected_paths: list[Path],
        system_id: str,
        scenario_id: str,
        created_at: datetime | None = None,
    ) -> Path:
        return self._resolve(
            job_id=job_id,
            kind=kind,
            options=options,
            protected_paths=protected_paths,
            system_id=system_id,
            scenario_id=scenario_id,
            created_at=created_at,
            create_parent=True,
        )

    def preview(
        self,
        *,
        job_id: str,
        kind: JobKind,
        options: JobOutputOptions,
        protected_paths: list[Path],
        system_id: str,
        scenario_id: str,
        created_at: datetime | None = None,
    ) -> Path:
        return self._resolve(
            job_id=job_id,
            kind=kind,
            options=options,
            protected_paths=protected_paths,
            system_id=system_id,
            scenario_id=scenario_id,
            created_at=created_at,
            create_parent=False,
        )

    def _resolve(
        self,
        *,
        job_id: str,
        kind: JobKind,
        options: JobOutputOptions,
        protected_paths: list[Path],
        system_id: str,
        scenario_id: str,
        created_at: datetime | None,
        create_parent: bool,
    ) -> Path:
        if options.output_path:
            output = Path(options.output_path).expanduser().resolve()
        else:
            output = (
                self.configuration.path_value("analysis_output_root")
                / _safe_segment(system_id)
                / _safe_segment(scenario_id)
                / f"{_run_stamp(created_at)}__{_short_job_id(job_id)}"
            ).resolve()

        allowed_roots = self.configuration.allowed_output_roots()
        if not allowed_roots:
            raise UnsafePath(str(output), "no allowed output roots are configured")
        if not any(_is_relative_to(output, root) and output != root for root in allowed_roots):
            raise UnsafePath(str(output), "path must be a dedicated child of an allowed output root")

        dangerous = {
            Path("/").resolve(),
            Path.home().resolve(),
            Path.cwd().resolve(),
        }
        dangerous.update(Path.cwd().resolve().parents)
        if output in dangerous:
            raise UnsafePath(str(output), "path is a protected filesystem or project location")

        runtime_root = self.configuration.path_value("runtime_root")
        for protected in [runtime_root, *protected_paths]:
            resolved = protected.expanduser().resolve()
            if output == resolved or _is_relative_to(resolved, output) or _is_relative_to(output, resolved):
                raise UnsafePath(str(output), f"path overlaps protected input: {resolved}")

        if output.exists():
            if not output.is_dir():
                raise UnsafePath(str(output), "existing output is not a directory")
            entries = list(output.iterdir())
            if entries and not options.replace:
                raise UnsafePath(str(output), "output exists and is not empty; set replace=true")
            if entries and options.replace and not self.is_owned(output):
                raise UnsafePath(
                    str(output),
                    f"replacement requires {UI_OUTPUT_MARKER} or {RUNNER_OUTPUT_MARKER}",
                )
        if create_parent:
            output.parent.mkdir(parents=True, exist_ok=True)
        return output

    def write_run_info(
        self,
        output: Path,
        *,
        job_id: str,
        system_id: str,
        scenario_id: str,
        display_name: str | None,
        created_at: datetime,
        started_at: datetime | None,
        finished_at: datetime | None,
        status: str,
    ) -> Path:
        target = output / RUN_INFO_FILE
        target.write_text(
            json.dumps(
                {
                    "schema_version": "knowledge_control_plane_run_info/v1",
                    "job_id": job_id,
                    "display_name": display_name,
                    "system_id": system_id,
                    "scenario_id": scenario_id,
                    "created_at": created_at.isoformat(),
                    "started_at": started_at.isoformat() if started_at else None,
                    "finished_at": finished_at.isoformat() if finished_at else None,
                    "status": status,
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        return target

    def is_owned(self, output: Path) -> bool:
        return (output / UI_OUTPUT_MARKER).is_file() or (output / RUNNER_OUTPUT_MARKER).is_file()

    def mark_owned(self, output: Path, *, job_id: str, kind: JobKind) -> None:
        if not output.exists() or not output.is_dir():
            return
        marker = output / UI_OUTPUT_MARKER
        marker.write_text(
            json.dumps(
                {
                    "schema_version": "knowledge_control_plane_output/v1",
                    "job_id": job_id,
                    "job_kind": kind.value,
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
