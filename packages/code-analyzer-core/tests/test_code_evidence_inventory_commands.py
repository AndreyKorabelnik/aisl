from pathlib import Path

from code_analyzer_core.utils import write_json
from code_evidence.commands import (
    callable as callable_evidence,
    call_chain_diagnostic,
    data_source,
    facts_by_type,
    persistent_write,
    source_inspect,
    source_inspection_request,
    source_open,
    source_to_storage_lineage,
    storage_lineage_gap,
)
from evidence_access_test_utils import assert_evidence_tool_registered, evidence_tool_ids


def _analysis_out(tmp_path: Path) -> Path:
    out = tmp_path / "analysis-out"
    facts_dir = out / "facts" / "facts_by_type"
    facts_dir.mkdir(parents=True)
    (out / "compact").mkdir()
    write_json(facts_dir / "persistent_write.json", [
        {"fact_type": "persistent_write", "id": "persistent_write_000001", "storage_target": "dao", "operation_kind": "merge"}
    ])
    write_json(facts_dir / "source_to_storage_lineage.json", [
        {"fact_type": "source_to_storage_lineage", "id": "source_to_storage_lineage_000001", "source_payload": "Rq", "storage_target": "dao"}
    ])
    write_json(facts_dir / "storage_lineage_gap.json", [
        {"fact_type": "storage_lineage_gap", "id": "storage_lineage_gap_000001", "gap_kind": "field_mapping_not_resolved"}
    ])
    write_json(facts_dir / "data_source.json", [
        {"fact_type": "data_source", "id": "data_source_000001", "source_payload": "Rq"}
    ])
    write_json(facts_dir / "source_inspection_request.json", [
        {"fact_type": "source_inspection_request", "id": "source_inspection_request_000001", "reason": "field_mapping_not_resolved", "target_operation": "Svc.process"}
    ])
    write_json(facts_dir / "call_chain_diagnostic.json", [
        {"fact_type": "call_chain_diagnostic", "call_chain_diagnostic_id": "call_chain_diagnostic_000001", "target_operation": "Svc.process", "caller_status": "not_found"}
    ])
    return out


def test_persistence_inventory_commands_accept_no_filter(tmp_path: Path):
    out = _analysis_out(tmp_path)

    assert persistent_write(out, "")["hit_count"] == 1
    assert source_to_storage_lineage(out, "")["hit_count"] == 1
    assert storage_lineage_gap(out, "")["hit_count"] == 1
    assert data_source(out, "")["hit_count"] == 1
    assert source_inspection_request(out, "")["hit_count"] == 1
    assert call_chain_diagnostic(out, "")["hit_count"] == 1


def test_evidence_tool_catalog_allows_persistence_inventory_without_positional():
    for command_id in [
        "persistent_write",
        "source_to_storage_lineage",
        "storage_lineage_gap",
        "data_source",
        "source_inspection_request",
        "call_chain_diagnostic",
        "confirmed_evidence",
        "candidate_signal",
        "unresolved_gap",
        "declared_value_set",
        "declared_value_set_summary",
        "literal_data_write",
        "source_inspect",
        "source_open",
        "find_implementations",
    ]:
        assert_evidence_tool_registered(command_id)


def test_facts_by_type_accepts_hyphen_and_underscore(tmp_path: Path):
    out = _analysis_out(tmp_path)

    underscore = facts_by_type(out, "source_to_storage_lineage")
    hyphen = facts_by_type(out, "source-to-storage-lineage")

    assert underscore["returned"] == 1
    assert hyphen["returned"] == 1
    assert hyphen["fact_type"] == "source_to_storage_lineage"
    assert hyphen["requested_fact_type"] == "source-to-storage-lineage"


def test_evidence_tool_catalog_allows_facts_by_type():
    assert_evidence_tool_registered("facts_by_type")


def test_source_open_supports_iterative_follow_up(tmp_path: Path):
    repo = tmp_path / "repo"
    src = repo / "src" / "main" / "java"
    src.mkdir(parents=True)
    target = src / "Svc.java"
    target.write_text(
        "class Svc {\n"
        "  void process() {\n"
        "    Converter c = null;\n"
        "    c.convert(request);\n"
        "  }\n"
        "}\n",
        encoding="utf-8",
    )
    out = _analysis_out(tmp_path)
    write_json(out / "manifest.json", {"repo_path": str(repo)})

    opened = source_open(out, "src/main/java/Svc.java", line=4, context=1)

    assert opened["status"] == "opened"
    assert "c.convert(request)" in opened["snippet"]
    assert opened["policy"] == "read_only_targeted_source_inspection"
    assert "next_step_hint" in opened


def test_source_inspect_opens_symbol_method_bundle(tmp_path: Path):
    repo = tmp_path / "repo"
    src = repo / "src" / "main" / "java" / "example"
    src.mkdir(parents=True)
    target = src / "SpreadProfileServiceImpl.java"
    target.write_text(
        "class SpreadProfileServiceImpl {\n"
        "  public void process(SpreadProfileRq rq) {\n"
        "    UcpPhone_2Record rec = new UcpPhone_2Record();\n"
        "    rec.setPhoneNumber(rq.getPhoneNumber());\n"
        "    toAdd.add(rec);\n"
        "    ucpPhoneDao.merge(toAdd);\n"
        "  }\n"
        "}\n",
        encoding="utf-8",
    )
    out = _analysis_out(tmp_path)
    write_json(out / "manifest.json", {"repo_path": str(repo)})

    inspected = source_inspect(out, "SpreadProfileServiceImpl.process", context=2, max_chars=4000)

    assert inspected["kind"] == "source-inspect"
    assert inspected["policy"] == "read_only_targeted_source_inspection"
    assert inspected["symbol_candidates"]
    assert inspected["callable_snippets"]
    assert "ucpPhoneDao.merge(toAdd)" in inspected["callable_snippets"][0]["snippet"]


def test_callable_command_opens_exact_symbol_callable_fallback(tmp_path: Path):
    repo = tmp_path / "repo"
    src = repo / "src" / "main" / "java" / "example"
    src.mkdir(parents=True)
    target = src / "SpreadProfileServiceImpl.java"
    target.write_text(
        "class SpreadProfileServiceImpl {\n"
        "  public void process(SpreadProfileRq rq) {\n"
        "    UcpPhone_2Record rec = new UcpPhone_2Record();\n"
        "    rec.setUcpId(rq.getUcpId());\n"
        "    ucpPhoneDao.merge(toAdd);\n"
        "  }\n"
        "}\n",
        encoding="utf-8",
    )
    out = _analysis_out(tmp_path)
    write_json(out / "manifest.json", {"repo_path": str(repo)})

    opened = callable_evidence(out, "SpreadProfileServiceImpl", "process", max_chars=4000)

    assert opened["kind"] == "callable"
    assert opened["symbol"] == "SpreadProfileServiceImpl"
    assert opened["callable"] == "process"
    assert opened["matches"]
    assert "rec.setUcpId(rq.getUcpId())" in opened["matches"][0]["snippet"]


def test_evidence_tool_catalog_includes_registered_java_inventory_commands():
    expected = {
        "call_chain_diagnostic",
        "confirmed_evidence",
        "candidate_signal",
        "unresolved_gap",
        "declared_value_set",
        "declared_value_set_summary",
        "literal_data_write",
    }
    assert expected.issubset(evidence_tool_ids())


def test_java_manifest_capabilities_include_contract_registered_navigation_commands():
    from pathlib import Path
    text = Path("code_analyzer_core/pipeline.py").read_text(encoding="utf-8")
    for capability in [
        "call-chain-diagnostic",
        "confirmed-evidence",
        "candidate-signal",
        "unresolved-gap",
        "declared-value-set",
        "declared-value-set-summary",
        "literal-data-write",
        "reference-data-fact-base",
        "workspace-table-catalog",
        "workspace-table-attribute-catalog",
        "workspace-attribute-graph",
        "attribute-origin-candidates",
        "attribute-rename-chains",
        "attribute-journey-by-fp",
        "attribute-lineage-breaks",
        "workspace-er-model-candidates",
        "workspace-table-relationship-candidates",
        "workspace-key-candidates",
    ]:
        assert f'"{capability}"' in text
