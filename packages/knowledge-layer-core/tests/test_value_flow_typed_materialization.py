from __future__ import annotations

import hashlib
import json
from pathlib import Path

import duckdb

from knowledge_layer_core.materialization_runtime import materialize
from prepared_knowledge_runtime.query import KnowledgeLayerQuery


def _evidence(root: Path) -> dict:
    evidence_root = root / "evidence"
    payload = evidence_root / "value-flow-payload"
    (payload / "catalog").mkdir(parents=True)
    (payload / "compact").mkdir(parents=True)
    occurrences = [
        {"occurrence_id":"source","occurrence_kind":"local_field","field_path":"request.customerId","relative_file":"src/main/java/Mapper.java"},
        {"occurrence_id":"target","occurrence_kind":"setter_target","field_path":"target.customerId","relative_file":"src/main/java/Mapper.java"},
    ]
    edges = [{"edge_id":"edge-1","source_occurrence_id":"source","target_occurrence_id":"target","edge_kind":"assignment","relative_file":"src/main/java/Mapper.java"}]
    files = [
        (payload / "catalog/field_occurrences.json", "catalog/field_occurrences.json", occurrences, None),
        (payload / "catalog/field_flow_edges.json", "catalog/field_flow_edges.json", edges, None),
        (payload / "compact/system_interface_catalog.json", "system_interface_catalog.json", {"all_interfaces":[]}, "all_interfaces"),
    ]
    descriptors=[]
    for path,name,value,section in files:
        path.write_text(json.dumps(value), encoding="utf-8")
        descriptors.append({"artifact_name":name,"relative_path":path.relative_to(evidence_root).as_posix(),"sha256":hashlib.sha256(path.read_bytes()).hexdigest(),"bytes":path.stat().st_size,"section":section})
    envelope = evidence_root / "value-flow-evidence.json"
    content={
        "contract_version":"core_evidence_artifact_contract/v1",
        "artifact_id":"value-flow-demo",
        "artifact_kind":"value-flow-evidence",
        "schema_version":"value-flow-evidence/v1",
        "content_fingerprint":"value-flow-fingerprint",
        "source_snapshot":{"source_id":"demo","fingerprint":"source-fingerprint"},
        "coverage":{"coverage_status":"complete"},
        "diagnostics":[],
        "provenance":{},
        "payload":{"repository_identity":{"repo_id":"demo"},"artifacts":descriptors},
    }
    envelope.write_text(json.dumps(content), encoding="utf-8")
    return {"artifact_id":content["artifact_id"],"artifact_kind":content["artifact_kind"],"schema_version":content["schema_version"],"content_fingerprint":content["content_fingerprint"],"location":{"kind":"file","path":str(envelope)}}


def test_repository_value_flow_materializes_from_typed_evidence(tmp_path: Path) -> None:
    output=tmp_path / "knowledge"
    result=materialize({
        "schema_version":"knowledge_materialization_request/v1",
        "materialization_id":"repository-value-flow",
        "scope_id":"workspace",
        "inputs":{"evidence_artifacts":[_evidence(tmp_path)],"knowledge_artifacts":[]},
        "parameters":{},
    }, output)
    assert result["status"] == "completed"
    assert result["published_capabilities"] == ["workspace.attribute-path-resolver","workspace.repository-value-flow"]
    con=duckdb.connect(str(output / "knowledge-layer.duckdb"), read_only=True)
    try:
        assert con.execute("select count(*) from repository_value_node").fetchone()[0] == 2
        assert con.execute("select count(*) from repository_value_flow_edge").fetchone()[0] == 1
        assert con.execute("select count(*) from information_schema.columns where lower(column_name) in ('task_id','profile_id','suite_id')").fetchone()[0] == 0
    finally:
        con.close()
    query=KnowledgeLayerQuery(output / "knowledge-layer.duckdb")
    resolved=query.resolve_attribute_paths("request.customerId", target="target.customerId", selected_repo_ids=["demo"])
    assert resolved["status"] == "confirmed_complete"
    assert resolved["stats"]["complete_path_count"] == 1
