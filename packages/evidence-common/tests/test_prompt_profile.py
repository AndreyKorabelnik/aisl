from pathlib import Path
import json

import pytest

from evidence_common.prompt_profile import assemble_prompt_stage, PromptProfileError


def _write_profile(root: Path, *, include_schema: bool = True) -> Path:
    shared = root / "shared"
    profile = root / "profile"
    (profile / "schemas").mkdir(parents=True)
    shared.mkdir(parents=True)
    (shared / "language_policy.md").write_text("LANGUAGE", encoding="utf-8")
    (profile / "initial_business.md").write_text("BUSINESS", encoding="utf-8")
    (profile / "continuation_business.md").write_text("CONT", encoding="utf-8")
    (profile / "report.md").write_text("REPORT", encoding="utf-8")
    (profile / "profile.yaml").write_text(
        "profile_id: test-profile\n"
        "profile_version: 1.0.0\n"
        "prompt_assembly:\n"
        "  initial:\n"
        "    - ../shared/language_policy.md\n"
        "    - @generated/profile_schema_contract\n"
        "    - initial_business.md\n"
        "  continuation:\n"
        "    - ../shared/language_policy.md\n"
        "    - @generated/profile_schema_contract\n"
        "    - continuation_business.md\n"
        "  report:\n"
        "    - ../shared/language_policy.md\n"
        "    - report.md\n",
        encoding="utf-8",
    )
    if include_schema:
        schema = {
            "type": "object",
            "description": "Top result schema",
            "required": ["status", "findings", "agent_requests"],
            "additionalProperties": False,
            "properties": {
                "status": {"const": "ready_to_assess", "description": "Final status"},
                "findings": {"type": "array", "items": {"$ref": "#/$defs/finding"}},
                "agent_requests": {"type": "array", "maxItems": 0},
            },
            "$defs": {
                "finding": {
                    "type": "object",
                    "required": ["finding_type", "assessment", "confidence", "evidence_refs", "attributes"],
                    "additionalProperties": False,
                    "properties": {
                        "finding_type": {"type": "string", "enum": ["table_lineage", "lineage_gap"], "description": "Finding kind"},
                        "assessment": {"type": "string", "enum": ["confirmed", "insufficient_information"]},
                        "decision": {"type": "string", "enum": ["yes", "needs_more_evidence"]},
                        "severity": {"type": "string", "enum": ["medium", "unknown"]},
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                        "evidence_refs": {"type": "array", "items": {"type": "string"}},
                        "attributes": {
                            "type": "object",
                            "additionalProperties": True,
                            "properties": {
                                "source_table": {"type": "string", "description": "Source table"},
                                "target_table": {"type": "string"},
                                "transformation_types": {"type": "array", "items": {"type": "string", "enum": ["filter", "join"]}},
                            },
                        },
                    },
                }
            },
        }
        (profile / "schemas" / "structured_result.schema.json").write_text(json.dumps(schema), encoding="utf-8")
    return profile


def test_generated_profile_schema_contract_is_inserted(tmp_path: Path):
    profile = _write_profile(tmp_path)
    prompt, meta = assemble_prompt_stage(profile, "initial")
    assert "LANGUAGE" in prompt
    assert "# Generated profile schema contract" in prompt
    assert "profile_id: `test-profile`" in prompt
    assert "allowed finding_type values: table_lineage, lineage_gap" in prompt
    assert "required finding fields:" in prompt
    assert "finding_type" in prompt
    assert "source_table" in prompt
    assert "Source table" in prompt
    assert "confidence: type=number; range=0..1" in prompt
    assert "evidence_refs: required; type=array" in prompt
    assert "BUSINESS" in prompt
    assert any(f["declared_path"] == "@generated/profile_schema_contract" and f["generated"] for f in meta["fragments"])


def test_report_does_not_get_generated_contract_when_not_specified(tmp_path: Path):
    profile = _write_profile(tmp_path)
    prompt, meta = assemble_prompt_stage(profile, "report")
    assert "# Generated profile schema contract" not in prompt
    assert "REPORT" in prompt
    assert all(not f["generated"] for f in meta["fragments"])


def test_missing_schema_for_generated_fragment_fails(tmp_path: Path):
    profile = _write_profile(tmp_path, include_schema=False)
    with pytest.raises(PromptProfileError) as exc:
        assemble_prompt_stage(profile, "initial")
    message = str(exc.value)
    assert "profile_id: test-profile" in message
    assert "stage: initial" in message
    assert "@generated/profile_schema_contract" in message
    assert "structured_result.schema.json" in message

def test_analysis_profile_can_omit_report_stage(tmp_path: Path):
    profile = _write_profile(tmp_path)
    text = (profile / "profile.yaml").read_text(encoding="utf-8")
    text = text.split("  report:\n")[0]
    (profile / "profile.yaml").write_text(text, encoding="utf-8")
    prompt, meta = assemble_prompt_stage(profile, "initial")
    assert "BUSINESS" in prompt
    assert meta["stage"] == "initial"


def test_requested_missing_stage_fails_lazily(tmp_path: Path):
    profile = _write_profile(tmp_path)
    text = (profile / "profile.yaml").read_text(encoding="utf-8")
    text = text.split("  report:\n")[0]
    (profile / "profile.yaml").write_text(text, encoding="utf-8")
    with pytest.raises(PromptProfileError) as exc:
        assemble_prompt_stage(profile, "report")
    assert "missing prompt_assembly.report" in str(exc.value)
    assert "available stages" in str(exc.value)

from evidence_common.prompt_profile import (
    build_prompt_profile_index,
    discover_prompt_profile_dirs,
    list_prompt_profiles,
    resolve_prompt_profile_dir,
    validate_prompt_profile_fragment_paths,
)


def _write_minimal_profile(profile_dir: Path, profile_id: str, shared_rel: str = "../../shared/language_policy.md") -> Path:
    profile_dir.mkdir(parents=True, exist_ok=True)
    (profile_dir / "initial.md").write_text(f"INITIAL {profile_id}", encoding="utf-8")
    (profile_dir / "profile.yaml").write_text(
        f"profile_id: {profile_id}\n"
        "profile_version: 1.0.0\n"
        "prompt_assembly:\n"
        "  initial:\n"
        f"    - {shared_rel}\n"
        "    - initial.md\n",
        encoding="utf-8",
    )
    return profile_dir


def test_grouped_layout_recursive_discovery_excludes_shared(tmp_path: Path):
    root = tmp_path / "llm-prompts"
    (root / "shared").mkdir(parents=True)
    (root / "shared" / "language_policy.md").write_text("LANGUAGE", encoding="utf-8")
    # A defensive fixture: even if shared accidentally has profile.yaml, it must not be runnable.
    (root / "shared" / "profile.yaml").write_text("profile_id: shared-not-runnable\n", encoding="utf-8")
    _write_minimal_profile(root / "code" / "system-data-model-description", "system-data-model-description")
    _write_minimal_profile(root / "sdd" / "spec-data-model-description", "spec-data-model-description")
    _write_minimal_profile(root / "support" / "profile-router", "profile-router")

    dirs = discover_prompt_profile_dirs(root)
    assert {d.name for d in dirs} == {"system-data-model-description", "spec-data-model-description", "profile-router"}

    index = build_prompt_profile_index(root)
    assert set(index) == {"system-data-model-description", "spec-data-model-description", "profile-router"}
    assert index["system-data-model-description"].profile_group == "code"
    assert index["spec-data-model-description"].profile_group == "sdd"
    assert index["profile-router"].profile_group == "support"
    assert [entry.profile_id for entry in list_prompt_profiles(root)] == sorted(index)


def test_grouped_layout_fragments_resolve_relative_to_profile_dir(tmp_path: Path):
    root = tmp_path / "llm-prompts"
    (root / "shared").mkdir(parents=True)
    (root / "shared" / "language_policy.md").write_text("LANGUAGE", encoding="utf-8")
    profile = _write_minimal_profile(root / "code" / "system-data-model-description", "system-data-model-description")

    prompt, meta = assemble_prompt_stage(profile, "initial")
    assert "LANGUAGE" in prompt
    assert "INITIAL system-data-model-description" in prompt
    resolved_paths = {Path(f["resolved_path"]).name for f in meta["fragments"]}
    assert resolved_paths == {"language_policy.md", "initial.md"}

    validation = validate_prompt_profile_fragment_paths(profile)
    assert validation["profile_id"] == "system-data-model-description"
    assert "initial" in validation["stages"]


def test_duplicate_profile_id_in_grouped_layout_is_hard_error(tmp_path: Path):
    root = tmp_path / "llm-prompts"
    (root / "shared").mkdir(parents=True)
    (root / "shared" / "language_policy.md").write_text("LANGUAGE", encoding="utf-8")
    _write_minimal_profile(root / "code" / "duplicate", "duplicate-profile")
    _write_minimal_profile(root / "sdd" / "duplicate", "duplicate-profile")

    with pytest.raises(PromptProfileError) as exc:
        build_prompt_profile_index(root)
    message = str(exc.value)
    assert "Duplicate prompt profile_id" in message
    assert "duplicate-profile" in message
    assert "code" in message and "sdd" in message


def test_resolve_prompt_profile_dir_requires_explicit_existing_profile_path(tmp_path: Path):
    root = tmp_path / "llm-prompts"
    (root / "shared").mkdir(parents=True)
    (root / "shared" / "language_policy.md").write_text("LANGUAGE", encoding="utf-8")
    profile = _write_minimal_profile(root / "code" / "system-data-model-description", "system-data-model-description")

    assert resolve_prompt_profile_dir(profile) == profile.resolve()
    assert resolve_prompt_profile_dir(profile / "profile.yaml") == profile.resolve()

    # No legacy fallback from llm-prompts/<profile_id> to llm-prompts/code/<profile_id>.
    with pytest.raises(PromptProfileError):
        resolve_prompt_profile_dir(root / "system-data-model-description")


def test_generated_schema_contract_resolves_attribute_refs_and_conditional_requirements(tmp_path: Path):
    profile = _write_profile(tmp_path)
    schema_path = profile / "schemas" / "structured_result.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    schema["$defs"]["endpoint"] = {
        "type": "object",
        "additionalProperties": False,
        "required": ["repo_ids", "system_id"],
        "properties": {
            "repo_ids": {"type": "array", "items": {"type": "string"}},
            "system_id": {"type": ["string", "null"]},
        },
    }
    schema["$defs"]["interaction_attributes"] = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "workspace_systems": {"type": "array", "items": {"$ref": "#/$defs/endpoint"}},
            "boundary_counts": {"type": "object"},
            "human_validation_required": {"type": "boolean"},
        },
    }
    finding = schema["$defs"]["finding"]
    finding["properties"]["finding_type"]["enum"] = ["workspace_system_interaction_overview", "inter_system_data_exchange"]
    finding["properties"]["attributes"] = {"$ref": "#/$defs/interaction_attributes"}
    finding["allOf"] = [{
        "if": {"properties": {"finding_type": {"const": "workspace_system_interaction_overview"}}},
        "then": {"properties": {"attributes": {"allOf": [{"required": ["workspace_systems", "boundary_counts", "human_validation_required"]}]}}},
    }]
    schema_path.write_text(json.dumps(schema), encoding="utf-8")

    prompt, meta = assemble_prompt_stage(profile, "initial")
    assert "allowed profile-specific attributes: workspace_systems, boundary_counts, human_validation_required" in prompt
    assert "Conditional required attributes by finding_type" in prompt
    assert "`workspace_system_interaction_overview`: workspace_systems, boundary_counts, human_validation_required" in prompt
    assert "Nested object `endpoint`" in prompt
    assert "required fields: repo_ids, system_id" in prompt or "required fields: system_id, repo_ids" in prompt
    generated = next(item for item in meta["fragments"] if item["generated"])
    assert generated["declared_path"] == "@generated/profile_schema_contract"
