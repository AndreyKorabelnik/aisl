from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import code_analyzer_core.prepared_artifacts.system_reference_evidence as subject
from code_analyzer_core.evidence_runtime import registered_evidence_analyzers


def _fake_run(counter: list[dict]):
    def run(repository: Path, output: Path, **kwargs):
        counter.append(dict(kwargs))
        compact = output / "compact"
        compact.mkdir(parents=True, exist_ok=True)
        (compact / "system_interface_catalog.json").write_text(
            json.dumps({"all_interfaces": [{"interface_id": "api-1", "protocol": "http"}]}), encoding="utf-8"
        )
        for name, payload in {
            "system_scenarios.json": [{"scenario_id": "scenario-1"}],
            "scenario_storage_summaries.json": [],
            "storage_usage_summaries.json": [],
            "external_dependencies.json": [{"dependency_id": "dep-1"}],
            "access_boundaries.json": [],
            "data_sources.json": [],
        }.items():
            (compact / name).write_text(json.dumps(payload), encoding="utf-8")
        detail = compact / "reference_data_fact_base"
        detail.mkdir()
        row = {"declared_value_set_id": "values-1", "name": "Status"}
        raw = json.dumps(row, ensure_ascii=False) + "\n"
        (detail / "declared_value_sets.jsonl").write_text(raw, encoding="utf-8")
        (compact / "reference_data_fact_base_manifest.json").write_text(
            json.dumps({
                "section_index": {
                    "declared_value_sets": {
                        "relative_path": "reference_data_fact_base/declared_value_sets.jsonl",
                        "records_count": 1,
                        "format": "jsonl",
                    }
                }
            }), encoding="utf-8"
        )
        return SimpleNamespace(coverage={"evidence_coverage": {"coverage_status": "complete"}})
    return run


def test_system_description_uses_dedicated_lightweight_pipeline(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    source = repo / "src/main/java/demo/Sample.java"
    source.parent.mkdir(parents=True)
    source.write_text("package demo; class Sample {}", encoding="utf-8")
    output = tmp_path / "out"
    calls: list[dict] = []
    monkeypatch.setattr(subject, "run_analysis", _fake_run(calls))

    system = subject.build_system_description_evidence(
        repository=repo, files=[source], repo_id="demo", output_root=output
    )
    reference = subject.build_reference_data_evidence(
        repository=repo, files=[source], repo_id="demo", output_root=output
    )

    assert len(calls) == 2
    system_profile = calls[0]["analysis_profile"]
    reference_profile = calls[1]["analysis_profile"]
    assert system_profile["profile_id"] == "internal-system-description-evidence-v1"
    system_stage_ids = [item["id"] for item in system_profile["pipeline"]["stages"]]
    assert "java_persistence_lineage_build" not in system_stage_ids
    assert "declared_value_scan" not in system_stage_ids
    assert "reference_data_fact_base" not in system_stage_ids
    assert system_profile["output_contract"]["policy"]["deep_persistence_not_requested"] is True
    assert "task_suite_profile_semantics" not in system_profile["output_contract"]["policy"]
    assert reference_profile["profile_id"] == "internal-reference-data-evidence-v1"
    assert system["artifact_kind"] == "system-description-evidence"
    assert system["schema_version"] == "system-description-evidence/v1"
    assert len(system["payload"]["artifacts"]) == 7
    assert reference["artifact_kind"] == "reference-data-evidence"
    assert reference["schema_version"] == "reference-data-evidence/v1"
    assert reference["coverage"]["record_count"] == 1
    assert "legacy_fallback" not in reference["provenance"]
    assert "dual_write" not in reference["provenance"]


def test_subject_analyzers_are_registered_by_typed_semantic_identity() -> None:
    identities = {(item.artifact_kind, item.schema_version) for item in registered_evidence_analyzers()}
    assert ("system-description-evidence", "system-description-evidence/v1") in identities
    assert ("reference-data-evidence", "reference-data-evidence/v1") in identities
