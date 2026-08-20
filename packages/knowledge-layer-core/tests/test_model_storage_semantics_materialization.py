from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path

import duckdb

from knowledge_layer_core.materialization_runtime import materialize, registered_materialization_ids


def _fp(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def _envelope(path: Path) -> dict:
    artifact = {
        "contract_version": "core_evidence_artifact_contract/v1",
        "artifact_kind": "model-storage-evidence",
        "schema_version": "model-storage-evidence/v1",
        "producer": {"component": "code-analyzer-core", "analyzer_id": "java-model-storage-analyzer", "analyzer_version": "test"},
        "source_snapshot": {"source_id": "repo", "fingerprint": "snapshot"},
        "foundation": {"used": True},
        "parameters": {},
        "coverage": {"coverage_status": "complete"},
        "diagnostics": [],
        "provenance": {"framework_interpreter": "tsa"},
        "payload": {
            "storage_records": [{"observation_id":"r1","observation_kind":"builder_storage_record","api_framework":"tsa_change_vector","properties":{"owner_fqcn":"demo.ParentConverter","owner_operation":"convert","storage_alias":"demo.Parent","storage_key_field":"key","storage_key_expression":"\"Parent_\" + parent.id()"},"source_refs":[]}],
            "storage_references": [{"observation_id":"ref1","observation_kind":"reference_value_from_target_storage_record","api_framework":"tsa_change_vector","properties":{"source_owner_fqcn":"demo.ParentConverter","source_operation":"convert","source_alias":"demo.Parent","source_field":"child","reference_operation":"referenceField","target_converter_operation":"convertChild","target_alias":"demo.Child","target_storage_key_field":"key","target_storage_key_expression":"parentKey + '.' + fieldName"},"source_refs":[]}],
            "storage_key_lineage": [{"observation_id":"lin1","observation_kind":"reference_collection_storage_key_lineage","api_framework":"tsa_change_vector","properties":{"source_owner_fqcn":"demo.ParentConverter","source_operation":"convert","source_alias":"demo.Parent","relationship_field":"children","reference_operation":"replaceReferenceCollection","target_alias":"demo.Child","source_key_expression":"\"Parent_\" + parent.id()","target_key_expression_template":"parentKey + '.children_' + child.id()","composed_target_key_expression":"\"Parent_\" + parent.id() + '.children_' + child.id()","source_key_passed_into_target_key":True},"source_refs":[]}],
            "reference_value_derivations": [],
        },
    }
    material={k:deepcopy(v) for k,v in artifact.items() if k not in {"content_fingerprint","artifact_id"}}
    artifact["content_fingerprint"]=_fp(material); artifact["artifact_id"]="model_storage_"+artifact["content_fingerprint"][:24]
    path.write_text(json.dumps(artifact),encoding="utf-8")
    return artifact


def test_model_storage_semantics_generic_materialization(tmp_path: Path) -> None:
    assert "model-storage-semantics" in registered_materialization_ids()
    path=tmp_path/"model-storage.json"; artifact=_envelope(path)
    request={"schema_version":"knowledge_materialization_request/v1","materialization_id":"model-storage-semantics","scope_id":"repo","inputs":{"evidence_artifacts":[{"artifact_id":artifact["artifact_id"],"artifact_kind":"model-storage-evidence","schema_version":"model-storage-evidence/v1","content_fingerprint":artifact["content_fingerprint"],"location":{"kind":"file","path":str(path)}}],"knowledge_artifacts":[]},"parameters":{}}
    result=materialize(request,tmp_path/"out")
    assert result["status"]=="completed"
    assert set(result["published_capabilities"])=={"common.model-storage-semantics","common.storage-identities","common.storage-reference-lineage"}
    db=duckdb.connect(str(tmp_path/"out/knowledge-layer.duckdb"),read_only=True)
    assert db.execute("select storage_alias, storage_key_expression from model_storage_record").fetchone()==('demo.Parent','"Parent_" + parent.id()')
    assert db.execute("select source_alias, source_field, target_alias from model_storage_reference").fetchone()==('demo.Parent','child','demo.Child')
    assert db.execute("select relationship_field, target_alias from model_storage_key_lineage").fetchone()==('children','demo.Child')
    db.close()
