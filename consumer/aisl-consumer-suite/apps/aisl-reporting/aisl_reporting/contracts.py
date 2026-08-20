from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Mapping

REPORT_REQUEST_SCHEMA = "aisl_report_request/v1"
REPORT_DATASET_SCHEMA = "report_dataset/v1"
REPORT_RUN_SCHEMA = "aisl_report_run/v1"
Audience = Literal["business", "architecture", "engineering"]
DetailLevel = Literal["executive", "standard", "detailed"]
OutputFormat = Literal["markdown"]


def _required(value: Any, name: str) -> str:
    result = str(value or "").strip()
    if not result:
        raise ValueError(f"{name} must not be empty")
    return result


@dataclass(frozen=True, slots=True)
class ReportRequest:
    report_type: str
    report_version: str
    api_url: str
    system_id: str
    revision_id: str | None = None
    audience: Audience = "architecture"
    detail_level: DetailLevel = "standard"
    focus: tuple[str, ...] = ()
    include_evidence: bool = True
    output_format: OutputFormat = "markdown"
    output_name: str = "report.md"
    instruction_files: tuple[Path, ...] = ()
    knowledge_source: Any = field(default=None, repr=False, compare=False)
    api_transport: Any = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "report_type", _required(self.report_type, "report_type"))
        object.__setattr__(self, "report_version", _required(self.report_version, "report_version"))
        object.__setattr__(self, "api_url", _required(self.api_url, "api_url"))
        object.__setattr__(self, "system_id", _required(self.system_id, "system_id"))
        object.__setattr__(self, "focus", tuple(str(v).strip() for v in self.focus if str(v).strip()))
        object.__setattr__(self, "output_name", _required(self.output_name, "output_name"))
        instruction_files = tuple(Path(value) for value in self.instruction_files)
        for instruction_file in instruction_files:
            if not instruction_file.is_file():
                raise ValueError(f"instruction file does not exist: {instruction_file}")
        object.__setattr__(self, "instruction_files", instruction_files)
        if self.audience not in {"business", "architecture", "engineering"}:
            raise ValueError(f"unsupported audience: {self.audience}")
        if self.detail_level not in {"executive", "standard", "detailed"}:
            raise ValueError(f"unsupported detail_level: {self.detail_level}")
        if self.output_format != "markdown":
            raise ValueError("only markdown output is supported")
        if Path(self.output_name).is_absolute() or ".." in Path(self.output_name).parts:
            raise ValueError("output_name must be a safe relative path")

    @property
    def profile_id(self) -> str:
        return f"{self.report_type}/{self.report_version}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": REPORT_REQUEST_SCHEMA,
            "report_type": self.report_type,
            "report_version": self.report_version,
            "profile_id": self.profile_id,
            "knowledge_api": {
                "api_url": self.api_url,
                "system_id": self.system_id,
                "revision_id": self.revision_id,
            },
            "audience": self.audience,
            "detail_level": self.detail_level,
            "focus": list(self.focus),
            "include_evidence": self.include_evidence,
            "output_format": self.output_format,
            "output_name": self.output_name,
            "instruction_files": [str(path) for path in self.instruction_files],
        }

    def to_dataset_dict(self) -> dict[str, Any]:
        result = self.to_dict()
        result["instruction_files"] = [path.name for path in self.instruction_files]
        if self.knowledge_source is not None:
            result["knowledge_api"] = {
                "api_url": self.api_url,
                "system_id": self.system_id,
                "revision_id": self.knowledge_source.revision_id,
            }
        return result


@dataclass(frozen=True, slots=True)
class PreparedReport:
    request: ReportRequest
    dataset: Mapping[str, Any]
    renderer_prompt: str
    profile_dir: Path


@dataclass(frozen=True, slots=True)
class ReportRunManifest:
    request: ReportRequest
    dataset_path: Path
    prompt_path: Path
    report_path: Path | None
    dataset_sha256: str
    prompt_sha256: str
    report_sha256: str | None
    validation: Mapping[str, Any] = field(default_factory=dict)
    status: str = "prepared"
    warnings: tuple[str, ...] = ()
    validation_path: Path | None = None
    log_path: Path | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": REPORT_RUN_SCHEMA,
            "status": self.status,
            "request": self.request.to_dict(),
            "dataset_path": str(self.dataset_path),
            "prompt_path": str(self.prompt_path),
            "report_path": str(self.report_path) if self.report_path else None,
            "validation_path": str(self.validation_path) if self.validation_path else None,
            "log_path": str(self.log_path) if self.log_path else None,
            "dataset_sha256": self.dataset_sha256,
            "prompt_sha256": self.prompt_sha256,
            "report_sha256": self.report_sha256,
            "validation": dict(self.validation),
            "warnings": list(self.warnings),
        }
