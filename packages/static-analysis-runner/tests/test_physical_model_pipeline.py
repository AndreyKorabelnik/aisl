from __future__ import annotations

import hashlib
import json
from pathlib import Path

from typer.testing import CliRunner

from static_analysis_runner.cli import app
from static_analysis_runner.io_utils import write_json
from static_analysis_runner.knowledge_execution import execute_knowledge_execution_plan
from static_analysis_runner.knowledge_execution_planning import (
    build_knowledge_input_inventory,
    compile_knowledge_execution_plan,
)
from test_knowledge_execution_planning import _catalog_for, _runtime_klc
from test_knowledge_planning import _core_evidence_payload, _fingerprint, _profile

runner = CliRunner()


def _write_empty_physical_artifact(root: Path, source_id: str = "fixture-pdm") -> Path:
    facts = root / "facts"
    facts.mkdir(parents=True)
    fact_types = (
        ("physical_model_table", "physical_model_table_id"),
        ("physical_model_column", "physical_model_column_id"),
        ("physical_model_key", "physical_model_key_id"),
        ("physical_model_relationship", "physical_model_relationship_id"),
        ("physical_model_gap", "physical_model_gap_id"),
    )
    entries = []
    for fact_type, id_field in fact_types:
        path = facts / f"{fact_type}.jsonl"
        path.write_bytes(b"")
        entries.append({
            "fact_type": fact_type,
            "id_field": id_field,
            "path": f"facts/{fact_type}.jsonl",
            "record_count": 0,
            "size_bytes": 0,
            "sha256": hashlib.sha256(b"").hexdigest(),
        })
    source_sha = hashlib.sha256(b"fixture").hexdigest()
    (root / "metadata.json").write_text(json.dumps({
        "physical_model_source_id": source_id,
        "schema_version": "physical-model/v1",
        "core_version": "0.44.1",
        "source_file": "fixture.pdm",
        "source_sha256": source_sha,
        "model_object_id": None,
        "model_name": "Fixture",
        "model_code": "fixture",
        "powerdesigner_version": None,
        "powerdesigner_target": None,
    }), encoding="utf-8")
    manifest = {
        "schema_version": "physical-model/v1",
        "physical_model_source_id": source_id,
        "core_version": "0.44.1",
        "content_fingerprint": hashlib.sha256(b"").hexdigest(),
        "source": {"file": "fixture.pdm", "sha256": source_sha, "metadata_path": "metadata.json"},
        "counts": {name: 0 for name, _ in fact_types},
        "facts": entries,
        "coverage": {"status": "complete", "gap_count": 0},
    }
    path = root / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def test_physical_model_executes_only_through_typed_knowledge_route(tmp_path: Path) -> None:
    manifest = _write_empty_physical_artifact(tmp_path / "physical-model")
    core = _core_evidence_payload()
    klc = _runtime_klc("physical-model")
    klc["runtime_contract"].update({
        "generic_entrypoint": "knowledge_layer_core.materialization_runtime.materialize",
        "registered_materialization_ids": ["physical-model"],
    })
    physical_contract = next(
        item for item in klc["materializations"]
        if item["materialization_id"] == "physical-model"
    )
    physical_contract["outputs"]["models"] = ["knowledge_layer_physical_model/v1"]
    physical_contract["outputs"]["capabilities"] = ["common.physical-model.pdm"]
    klc["catalog_fingerprint"] = _fingerprint({
        key: value for key, value in klc.items() if key != "catalog_fingerprint"
    })
    knowledge_catalog = _catalog_for(core, klc)
    physical_knowledge = next(
        item for item in knowledge_catalog["knowledge_types"]
        if item["knowledge_id"] == "physical-data-model"
    )
    physical_knowledge["materialization"]["models"] = ["knowledge_layer_physical_model/v1"]
    physical_knowledge["materialization"]["capabilities"] = ["common.physical-model.pdm"]
    knowledge_catalog["catalog_fingerprint"] = _fingerprint({
        key: value for key, value in knowledge_catalog.items() if key != "catalog_fingerprint"
    })
    inventory = build_knowledge_input_inventory(
        scope_kind="repository",
        scope_id="client-profile",
        source_snapshots=[],
        core_evidence_catalog=core,
        materialization_catalog=klc,
        typed_artifacts=[{
            "artifact_id": "physical-model-input",
            "artifact_kind": "physical-model",
            "schema_version": "physical-model/v1",
            "status": "completed",
            "scope_id": "client-profile",
            "location": {"kind": "file", "path": str(manifest)},
        }],
    )
    plan = compile_knowledge_execution_plan(
        knowledge_catalog=knowledge_catalog,
        knowledge_profile=_profile("physical-data-model", scope="repository"),
        input_inventory=inventory,
        core_evidence_catalog=core,
        materialization_catalog=klc,
    )
    assert plan["status"]["overall"] == "ready"
    assert plan["graph"]["execution_order"] == ["materialization:physical-model"]

    plan_path = tmp_path / "plan.json"
    core_path = tmp_path / "core.json"
    klc_path = tmp_path / "klc.json"
    write_json(plan_path, plan)
    write_json(core_path, core)
    write_json(klc_path, klc)
    result = execute_knowledge_execution_plan(
        execution_plan=plan_path,
        core_evidence_catalog=core_path,
        materialization_catalog=klc_path,
        output=tmp_path / "knowledge-execution",
        core_command=str(tmp_path / "must-not-run"),
        replace=True,
    )
    assert result["status"] == "completed"
    assert result["analyzer_executions"] == []
    assert result["execution_order"] == ["materialization:physical-model"]
    assert "common.physical-model.pdm" in result["published_capabilities"]
    assert "task_suite_profile_semantics" not in result["semantic_policy"]
    assert "legacy_fallback" not in result["semantic_policy"]


def test_obsolete_physical_model_and_hidden_materialization_commands_are_removed() -> None:
    help_result = runner.invoke(app, ["--help"], env={"COLUMNS": "220"})
    assert help_result.exit_code == 0
    assert "physical-model" not in help_result.stdout
    assert "materialize-knowledge-layer" not in help_result.stdout

    physical = runner.invoke(app, ["physical-model", "--help"])
    assert physical.exit_code != 0
    hidden = runner.invoke(app, ["materialize-knowledge-layer", "--help"])
    assert hidden.exit_code != 0
