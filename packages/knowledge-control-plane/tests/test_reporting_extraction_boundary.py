from __future__ import annotations

from dataclasses import fields

from knowledge_control_plane.api.generic_v1.models import ArtifactKind, ConfigurationResponse, JobCreateRequest, ScenarioDefinition, ToolCommands
from knowledge_control_plane.runtime.pipeline import PipelinePlan
from knowledge_control_plane.runtime.settings import RuntimeSettings


def test_reporting_is_not_a_control_plane_runtime_contract() -> None:
    assert "default_report_output_root" not in RuntimeSettings.__dataclass_fields__
    assert "knowledge_reporting" not in ToolCommands.model_fields
    assert "llm" not in ConfigurationResponse.model_fields
    assert "build_report" not in JobCreateRequest.model_fields
    assert "report_profile" not in ScenarioDefinition.model_fields
    plan_fields = {item.name for item in fields(PipelinePlan)}
    assert not {"report_profile", "report_focus", "report_root"} & plan_fields
    assert "report_markdown" not in {item.value for item in ArtifactKind}
    assert "report_dataset" not in {item.value for item in ArtifactKind}
