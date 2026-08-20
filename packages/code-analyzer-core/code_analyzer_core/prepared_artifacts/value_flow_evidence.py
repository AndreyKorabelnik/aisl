from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import Any, Iterable, Mapping

from code_analyzer_core import __version__ as CORE_VERSION
from code_analyzer_core.pipeline import run_analysis

CONTRACT_VERSION = "core_evidence_artifact_contract/v1"
ARTIFACT_KIND = "value-flow-evidence"
SCHEMA_VERSION = "value-flow-evidence/v1"
ANALYZER_ID = "value-flow-analyzer"
RELATIVE_PATH = "evidence/value-flow-evidence.json"


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _relative(repository: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(repository.resolve()).as_posix()
    except Exception:
        return path.as_posix().lstrip("/") or "unknown"


def _source_snapshot(repository: Path, files: Iterable[Path], repo_id: str) -> dict[str, Any]:
    entries=[]
    for path in sorted((Path(item) for item in files), key=lambda item: _relative(repository,item)):
        try: payload=path.read_bytes()
        except OSError: continue
        entries.append({"repository_relative_path":_relative(repository,path),"sha256":hashlib.sha256(payload).hexdigest(),"byte_size":len(payload)})
    material={"source_id":repo_id,"scope":"value_flow_sources","files":entries}
    return {"source_id":repo_id,"revision":None,"fingerprint":_fingerprint(material),"scope":"value_flow_sources","file_count":len(entries)}


def _profile() -> dict[str, Any]:
    return {
        "profile_id":"internal-value-flow-evidence-v1",
        "profile_version":1,
        "name":"Typed direct value-flow evidence",
        "workspace_types":["java"],
        "capabilities":["lineage.data-flow","lineage.field-flow","lineage.traceability"],
        "pipeline":{"stages":[
            {"id":"scan_files"},{"id":"config_scan"},{"id":"maven_dependency_scan"},{"id":"gradle_dependency_scan"},
            {"id":"openapi_scan"},{"id":"java_structural_scan"},{"id":"java_source_observation_build","options":{"framework_interpreters":[]}},
            {"id":"java_system_interaction_enrichment"},{"id":"java_data_flow_build"},{"id":"java_field_flow_build"},{"id":"java_traceability_build"},
        ],"final_stages":[{"id":"core_output"},{"id":"normalize_facts"},{"id":"compact_package"}]},
    }


def _descriptor(root: Path, path: Path, *, artifact_name: str, section: str|None=None) -> dict[str, Any]:
    rel=path.resolve().relative_to(root.resolve()).as_posix()
    return {"artifact_name":artifact_name,"relative_path":rel,"sha256":hashlib.sha256(path.read_bytes()).hexdigest(),"bytes":path.stat().st_size,"section":section}


def _count(path: Path, section: str|None=None) -> int:
    if not path.is_file(): return 0
    raw=json.loads(path.read_text(encoding="utf-8"))
    if section and isinstance(raw,Mapping): raw=raw.get(section) or []
    return len(raw) if isinstance(raw,list) else 0


def _finalize(artifact: dict[str,Any]) -> dict[str,Any]:
    material={k:deepcopy(v) for k,v in artifact.items() if k not in {"content_fingerprint","artifact_id"}}
    artifact["content_fingerprint"]=_fingerprint(material)
    artifact["artifact_id"]=f"value_flow_{artifact['content_fingerprint'][:24]}"
    return artifact


def build_value_flow_evidence(*, repository:Path, files:list[Path], repo_id:str, output_root:Path, parameters:Mapping[str,Any]) -> dict[str,Any]:
    if parameters:
        raise ValueError("value-flow-evidence/v1 does not accept runtime parameters")
    repository=repository.expanduser().resolve(); output_root=output_root.expanduser().resolve()
    snapshot=_source_snapshot(repository,files,repo_id)
    payload_root=output_root/'evidence'/'value-flow-payload'; marker=payload_root/'value-flow-payload-manifest.json'
    expected={"schema_version":"value_flow_payload_manifest/v1","core_version":CORE_VERSION,"repo_id":repo_id,"source_fingerprint":snapshot["fingerprint"],"profile_id":"internal-value-flow-evidence-v1"}
    if marker.is_file():
        current=json.loads(marker.read_text(encoding='utf-8'))
        if {k:current.get(k) for k in expected} != expected: raise ValueError("existing value-flow payload does not match the current evidence request")
    else:
        if payload_root.exists(): shutil.rmtree(payload_root)
        result=run_analysis(repository,payload_root,project_code=repo_id,system_name=repo_id,repo_id=repo_id,analysis_profile=_profile())
    specs=[
        (payload_root/'catalog'/'field_occurrences.json','catalog/field_occurrences.json',None),
        (payload_root/'catalog'/'field_flow_edges.json','catalog/field_flow_edges.json',None),
        (payload_root/'compact'/'system_interface_catalog.json','system_interface_catalog.json','all_interfaces'),
    ]
    diagnostics=[]; artifacts=[]
    for path,name,section in specs:
        if path.is_file(): artifacts.append(_descriptor(output_root/'evidence',path,artifact_name=name,section=section))
        else: diagnostics.append({"code":"value_flow_payload_missing","severity":"warning","message":f"{name} was not produced","source_refs":[]})
    counts={name:_count(path,section) for path,name,section in specs}
    envelope={
        "contract_version":CONTRACT_VERSION,"artifact_kind":ARTIFACT_KIND,"schema_version":SCHEMA_VERSION,
        "producer":{"component":"code-analyzer-core","analyzer_id":ANALYZER_ID,"analyzer_version":CORE_VERSION},
        "source_snapshot":snapshot,"foundation":{"used":False,"contract_version":None,"fingerprint":None,"sections":[]},"parameters":{},
        "coverage":{"coverage_status":"partial" if diagnostics else "complete","source_file_count":len(files),"field_occurrence_count":counts['catalog/field_occurrences.json'],"field_flow_edge_count":counts['catalog/field_flow_edges.json'],"interface_count":counts['system_interface_catalog.json']},
        "diagnostics":diagnostics,
        "payload":{"repository_identity":{"repo_id":repo_id},"artifacts":artifacts},
    }
    return _finalize(envelope)
