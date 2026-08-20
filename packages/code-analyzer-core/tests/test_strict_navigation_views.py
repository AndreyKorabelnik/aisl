from pathlib import Path
import json


from code_analyzer_core.models import AnalysisResult, EvidenceRef, Fact
from code_analyzer_core.navigation import build_navigation
from code_evidence.commands import confirmed_evidence, candidate_signal, unresolved_gap, source_inspection_request
from code_evidence import commands as evidence_tools
from code_analyzer_core.scanners.java_evidence_pipeline import _source_inspection_request_fact


LEGACY_PUBLIC_MARKERS = {
    "pro" + "bable",
    "par" + "tial",
    "confi" + "dence",
    "assess" + "ment",
    "persistent" + "_storage",
    "lineage" + "_assess" + "ment",
    "risk" + "_relevant",
    "risk" + "_relevance",
    "persistence" + "_evi" + "dence" + "_level",
    "persistence" + "_res" + "olution" + "_status",
}


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.strip() + "\n", encoding="utf-8")


def _base_result(tmp_path: Path) -> AnalysisResult:
    result = AnalysisResult(system_name="s", project_code="p", repo_path=str(tmp_path), stack=["java"], files_analyzed=1)
    result.facts.append(Fact(
        fact_type="storage_access",
        name="Storage call",
        properties={
            "storage_access_id": "storage_access_000001",
            "operation": "Service.process",
            "evidence_maturity_level": "unresolved",
            "evidence_maturity_dimensions": {"persistence_write": "unresolved", "physical_storage": "unresolved"},
            "candidate_signals": [{"signal_type": "custom_dao_persistence_boundary", "target": "repo.save", "basis": "dao-like receiver"}],
            "unresolved_gap_lifecycle": [{
                "dimension": "persistence_write",
                "gap_type": "persistence_write_unresolved",
                "decision_blocking": True,
                "actionability": "actionable",
                "source_inspection_required": True,
                "source_inspection_request_status": "emitted",
                "source_inspection_request_ids": ["source_inspection_request_000001"],
            }],
        },
        evidence=[EvidenceRef(file_path="src/Service.java", line_start=10, line_end=12, extractor="test")],
    ))
    result.facts.append(Fact(
        fact_type="source_inspection_request",
        name="Inspect Service.process",
        properties={
            "source_inspection_request_id": "source_inspection_request_000001",
            "reason": "persistence_write_not_confirmed",
            "target_operation": "Service.process",
            "target_symbol": "Service",
            "target_callable": "process",
            "suggested_evidence_tools": [{
                "purpose": "open_target_method",
                "evidence_tool": "callable",
                "arguments": {"symbol": "Service", "callable": "process"},
                "static_analysis_output_required": True,
                "execution_mode": "evidence_access_api",
            }],
            "related_evidence_refs": ["storage_access_000001"],
        },
    ))
    result.facts.append(Fact(
        fact_type="field_lineage",
        name="Confirmed mapping",
        properties={
            "field_lineage_id": "field_lineage_000001",
            "source_field": "a",
            "target_field": "b",
            "evidence_maturity_level": "confirmed",
            "evidence_maturity_dimensions": {"field_mapping": "confirmed"},
        },
    ))
    return result


def test_navigation_writes_strict_primary_views(tmp_path: Path):
    result = _base_result(tmp_path)

    nav = build_navigation(result, tmp_path / "analysis")
    assert nav["strict_evidence_contract"]["primary_views"] == ["confirmed_evidence", "candidate_signals", "unresolved_gaps", "source_inspection_requests"]
    assert (tmp_path / "analysis" / "compact" / "confirmed_evidence.json").exists()
    assert (tmp_path / "analysis" / "compact" / "candidate_signals.json").exists()
    assert (tmp_path / "analysis" / "compact" / "unresolved_gaps.json").exists()
    assert (tmp_path / "analysis" / "compact" / "source_inspection_requests.json").exists()

    ce = confirmed_evidence(tmp_path / "analysis", "field_lineage_000001")
    cs = candidate_signal(tmp_path / "analysis", "repo.save")
    ug = unresolved_gap(tmp_path / "analysis", "persistence_write")
    sir = source_inspection_request(tmp_path / "analysis", "Service.process")
    assert ce["hit_count"] == 1
    assert cs["hit_count"] == 1
    assert cs["hits"][0]["item"]["is_evidence"] is False
    assert ug["hit_count"] == 1
    assert sir["hit_count"] == 1


def test_strict_navigation_counts_and_gap_lifecycle_enums(tmp_path: Path):
    nav = build_navigation(_base_result(tmp_path), tmp_path / "analysis")
    counts = nav["counts"]
    assert counts["confirmed_evidence_count"] == 1
    assert counts["candidate_signal_count"] == 1
    assert counts["unresolved_gap_count"] == 1
    assert counts["source_inspection_request_count"] == 1
    assert counts["actionable_gap_count"] == 1
    assert counts["exhausted_gap_count"] == 0
    assert counts["gap_actionability_counts"] == {"actionable": 1}
    assert set(nav["strict_evidence_contract"]["maturity_levels"]) == {"confirmed", "unresolved", "not_applicable"}
    assert set(nav["strict_evidence_contract"]["gap_actionability_values"]) == {"actionable", "not_actionable", "exhausted", "not_relevant"}
    statuses = set(nav["strict_evidence_contract"]["source_inspection_request_status_values"])
    assert {"emitted", "required_but_not_emitted", "not_required"}.issubset(statuses)


def test_inventory_evidence_tools_work_without_positional_token(tmp_path: Path):
    build_navigation(_base_result(tmp_path), tmp_path / "analysis")
    for func in [confirmed_evidence, candidate_signal, unresolved_gap, source_inspection_request]:
        payload = func(tmp_path / "analysis")
        assert payload["hit_count"] >= 1


def test_generated_source_inspection_suggested_evidence_tools_are_executable(tmp_path: Path):
    repo = tmp_path / "repo"
    _write(repo / "src/main/java/com/acme/SpreadProfileServiceImpl.java", """
        package com.acme;
        public class SpreadProfileServiceImpl {
          private final UcpPhoneDao ucpPhoneDao = new UcpPhoneDaoImpl();
          public void process(SpreadProfileRq rq) { ucpPhoneDao.merge(rq); }
        }
        class SpreadProfileRq {}
        interface UcpPhoneDao { void merge(Object value); }
        class UcpPhoneDaoImpl implements UcpPhoneDao { public void merge(Object value) {} }
    """)
    analysis_out = tmp_path / "analysis"
    analysis_out.mkdir()
    (analysis_out / "manifest.json").write_text(json.dumps({"repo_path": str(repo)}), encoding="utf-8")
    fact = _source_inspection_request_fact(
        "source_inspection_request_000001",
        reason="field_mapping_unresolved",
        priority="high",
        target_operation="SpreadProfileServiceImpl.process",
        focus="Inspect mapping",
        related_evidence_refs=["source_to_storage_lineage_000001"],
        storage_access={"storage_method": "merge", "receiver_expression": "ucpPhoneDao", "table_or_repository": "ucpPhoneDao"},
        source_payload="SpreadProfileRq",
        saved_object="UcpPhone_2Record",
        tokens=["UcpPhoneDao", "ucpPhoneDao"],
    )
    commands = fact.properties["suggested_evidence_tools"]
    assert commands
    assert all(cmd.get("execution_mode") == "evidence_access_api" for cmd in commands)
    assert all("<relative-file-path>" not in json.dumps(cmd, ensure_ascii=False) for cmd in commands)
    assert all("<line>" not in json.dumps(cmd, ensure_ascii=False) for cmd in commands)

    for cmd in commands:
        evidence_tool = cmd["evidence_tool"]
        args = cmd.get("arguments") or {}
        if evidence_tool == "callable":
            result = evidence_tools.callable(analysis_out, args["symbol"], args["callable"])
        elif evidence_tool == "source-inspect":
            result = evidence_tools.source_inspect(analysis_out, args["token"], max_results=5)
        elif evidence_tool == "find-implementations":
            result = evidence_tools.find_implementations(analysis_out, args["token"])
        else:
            raise AssertionError(f"unsupported suggested evidence command: {evidence_tool}")
        assert result.get("kind")


def test_public_output_does_not_contain_removed_legacy_markers(tmp_path: Path):
    build_navigation(_base_result(tmp_path), tmp_path / "analysis")
    for path in (tmp_path / "analysis" / "compact").glob("*.json"):
        text = path.read_text(encoding="utf-8")
        for marker in LEGACY_PUBLIC_MARKERS:
            assert marker not in text, f"{marker} found in {path}"


def test_navigation_sorts_data_flow_dicts_without_type_error(tmp_path: Path):
    result = _base_result(tmp_path)
    result.facts.append(Fact(
        fact_type="source_to_sink_flow",
        name="B flow",
        properties={
            "flow_id": "flow_000002",
            "flow_type": "source_to_sink",
            "operation": "BService.send",
            "source_kind": "method_input",
            "source_parameter": "rq",
            "source_type": "Rq",
            "sink_kind": "http",
            "sink_pattern": "client.call",
            "payload_expression": "payload",
        },
    ))
    result.facts.append(Fact(
        fact_type="source_to_sink_flow",
        name="A flow",
        properties={
            "flow_id": "flow_000001",
            "flow_type": "source_to_sink",
            "operation": "AService.send",
            "source_kind": "method_input",
            "source_parameter": "rq",
            "source_type": "Rq",
            "sink_kind": "kafka",
            "sink_pattern": "producer.send",
            "payload_expression": "payload",
        },
    ))

    nav = build_navigation(result, tmp_path / "analysis")
    first_pass = json.loads((tmp_path / "analysis" / "compact" / "first_pass.json").read_text(encoding="utf-8"))
    assert [x["flow_id"] for x in first_pass["observed_data_flows"]] == ["flow_000001", "flow_000002"]
    assert nav["counts"]["data_flows"] == 2


def test_strict_evidence_views_is_reference_manifest_not_duplicate_payload(tmp_path: Path):
    from code_analyzer_core.models import AnalysisResult, Fact
    from code_analyzer_core.navigation import build_navigation
    import json

    result = _base_result(tmp_path)
    out = tmp_path / "analysis"
    build_navigation(result, out)
    manifest = json.loads((out / "compact" / "strict_evidence_views.json").read_text(encoding="utf-8"))
    assert manifest["format_version"] == "2.0"
    assert manifest["primary_views"]["confirmed_evidence"]["path"] == "confirmed_evidence.json"
    assert isinstance(manifest["primary_views"]["confirmed_evidence"]["count"], int)
    assert not isinstance(manifest["primary_views"]["confirmed_evidence"], list)
