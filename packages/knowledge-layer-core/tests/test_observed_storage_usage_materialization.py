from copy import deepcopy
import hashlib
import json
from pathlib import Path

from knowledge_layer_core.materialization_runtime import materialize, registered_materialization_ids


def _fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _envelope(path: Path, repo_id: str = "repo") -> dict:
    artifact = {
        "contract_version": "core_evidence_artifact_contract/v1",
        "artifact_kind": "storage-usage-evidence",
        "schema_version": "storage-usage-evidence/v1",
        "producer": {"component": "code-analyzer-core", "analyzer_id": "java-storage-usage-analyzer", "analyzer_version": "test"},
        "source_snapshot": {"source_id": repo_id, "fingerprint": "fp", "scope": "java_storage_usage_sources", "file_count": 1, "revision": None},
        "foundation": {"used": False, "contract_version": None, "fingerprint": None, "sections": []},
        "parameters": {},
        "coverage": {"coverage_status": "complete", "storage_access_count": 2},
        "diagnostics": [],
        "provenance": {},
        "payload": {
            "storage_accesses": [
                {"storage_access_id":f"{repo_id}-a1","repo_id":repo_id,"operation":"S.load","access_kind":"read","operation_kind":"read","write_kind":"read","storage_kind":"repository_or_storage_api","storage_target_expression":"customerRepository","target_resolution_level":"read_method","target_resolution_status":"not_applicable","receiver_expression":"customerRepository","storage_method":"findById","writes_new_payload":False,"selected_fields":[],"selected_field_refs":[],"source_ref":{"repository_relative_path":"S.java","line_start":3,"line_end":3,"extractor":"test"}},
                {"storage_access_id":f"{repo_id}-a2","repo_id":repo_id,"operation":"S.save","access_kind":"write","operation_kind":"save","write_kind":"save","storage_kind":"repository_or_storage_api","storage_target_expression":"customerRepository","target_resolution_level":"known_storage_api_or_framework_method","target_resolution_status":"recognized_storage_method","receiver_expression":"customerRepository","storage_method":"save","payload_expression":"customer","payload_role":"saved_payload","writes_new_payload":True,"selected_fields":[],"selected_field_refs":[],"source_ref":{"repository_relative_path":"S.java","line_start":4,"line_end":4,"extractor":"test"}},
            ],
            "storage_reads": [{"storage_read_id":f"{repo_id}-r1","storage_access_id":f"{repo_id}-a1","repo_id":repo_id,"operation":"S.load","storage_target_expression":"customerRepository","storage_kind":"repository_or_storage_api","storage_method":"findById","selected_fields":[],"target_resolution_status":"not_applicable","source_ref":{"repository_relative_path":"S.java","line_start":3,"line_end":3,"extractor":"test"}}],
            "storage_writes": [{"storage_write_id":f"{repo_id}-w1","storage_access_id":f"{repo_id}-a2","repo_id":repo_id,"operation":"S.save","storage_target_expression":"customerRepository","storage_kind":"repository_or_storage_api","storage_method":"save","write_kind":"save","payload_expression":"customer","payload_role":"saved_payload","writes_new_payload":True,"target_resolution_status":"recognized_storage_method","source_ref":{"repository_relative_path":"S.java","line_start":4,"line_end":4,"extractor":"test"}}],
            "storage_usage_gaps": [],
        },
    }
    material={k:deepcopy(v) for k,v in artifact.items() if k not in {"content_fingerprint","artifact_id"}}
    artifact["content_fingerprint"]=_fingerprint(material); artifact["artifact_id"]="storage_"+artifact["content_fingerprint"][:24]
    path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(artifact),encoding="utf-8")
    return artifact


def test_observed_storage_usage_generic_materialization(tmp_path: Path) -> None:
    assert "observed-storage-usage" in registered_materialization_ids()
    path=tmp_path/"storage.json"; artifact=_envelope(path)
    request={"schema_version":"knowledge_materialization_request/v1","materialization_id":"observed-storage-usage","scope_id":"repo","inputs":{"evidence_artifacts":[{"artifact_id":artifact["artifact_id"],"artifact_kind":"storage-usage-evidence","schema_version":"storage-usage-evidence/v1","content_fingerprint":artifact["content_fingerprint"],"location":{"kind":"file","path":str(path)}}],"knowledge_artifacts":[]},"parameters":{}}
    result=materialize(request,tmp_path/"out")
    assert result["status"]=="completed"
    assert set(result["published_capabilities"])=={"common.observed-storage-usage","common.storage-read-write-inventory","common.storage-access-gaps"}
    assert result["output"]["counts"]["observed_storage_access"]==2


def test_observed_storage_usage_workspace_materializes_multiple_repository_artifacts(tmp_path: Path) -> None:
    first_path=tmp_path/"repo-a.json"; first=_envelope(first_path, "repo-a")
    second_path=tmp_path/"repo-b.json"; second=_envelope(second_path, "repo-b")
    evidence=[]
    for artifact,path in [(first,first_path),(second,second_path)]:
        evidence.append({"artifact_id":artifact["artifact_id"],"artifact_kind":"storage-usage-evidence","schema_version":"storage-usage-evidence/v1","content_fingerprint":artifact["content_fingerprint"],"location":{"kind":"file","path":str(path)}})
    request={"schema_version":"knowledge_materialization_request/v1","materialization_id":"observed-storage-usage","scope_id":"workspace-x","inputs":{"evidence_artifacts":evidence,"knowledge_artifacts":[]},"parameters":{}}
    result=materialize(request,tmp_path/"workspace-out")
    assert result["status"]=="completed"
    manifest=json.loads(Path(result["output"]["manifest_path"]).read_text(encoding="utf-8"))
    assert manifest["repository_ids"]==["repo-a","repo-b"]
    assert manifest["scope_type"]=="workspace"
    assert result["output"]["counts"]["observed_storage_source"]==2
    assert result["output"]["counts"]["observed_storage_access"]==4
