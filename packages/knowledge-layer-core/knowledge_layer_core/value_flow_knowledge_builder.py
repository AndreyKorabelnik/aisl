from __future__ import annotations
import hashlib, json, os, uuid
from pathlib import Path
from typing import Any, Mapping, Sequence
from prepared_knowledge_runtime.contracts import KnowledgeLayerManifest
from .bulk import bulk_insert
from prepared_knowledge_runtime.database import connect_database, initialize_schema
from prepared_knowledge_runtime.io import write_json
from .metrics import canonical_json, utc_now
from prepared_knowledge_runtime.normalization import stable_id
from .publication import publish_directory_atomic, remove_path
from .value_flow import materialize_repository_value_flow
from .value_flow_knowledge_schema import VALUE_FLOW_KNOWLEDGE_DATABASE, VALUE_FLOW_KNOWLEDGE_DDL, VALUE_FLOW_KNOWLEDGE_SCHEMA_VERSION
from .version import __version__

def _read(path:Path):
    value=json.loads(path.read_text(encoding='utf-8'))
    return value

def _safe(envelope_path:Path, relative:str)->Path:
    candidate=Path(str(relative or ''))
    if not relative or candidate.is_absolute(): raise ValueError('value-flow payload path must be envelope-relative')
    root=envelope_path.parent.resolve(); resolved=(root/candidate).resolve()
    try: resolved.relative_to(root)
    except ValueError as exc: raise ValueError('value-flow payload path escapes envelope root') from exc
    return resolved

def _source(item:Mapping[str,Any]):
    path=Path(str((item.get('location') or {}).get('path') or '')).expanduser().resolve(); env=_read(path)
    if (env.get('artifact_kind'),env.get('schema_version')) != ('value-flow-evidence','value-flow-evidence/v1'):
        raise ValueError('unexpected value-flow evidence identity')
    return path,env

def build_repository_value_flow_knowledge_layer(evidence_items:Sequence[Mapping[str,Any]], output:str|Path, *, scope_id:str, replace:bool=True, duckdb_memory_limit:str='1GB', duckdb_threads:int=1)->dict[str,Any]:
    if not evidence_items: raise ValueError('repository-value-flow requires value-flow-evidence')
    sources=[_source(i) for i in evidence_items]
    repo_ids=[str((e.get('source_snapshot') or {}).get('source_id') or '').strip() for _,e in sources]
    if any(not r for r in repo_ids) or len(set(repo_ids))!=len(repo_ids): raise ValueError('value-flow evidence must have unique repository IDs')
    out=Path(output).expanduser().resolve(); staging=out.with_name(f'.{out.name}.building-{os.getpid()}-{uuid.uuid4().hex[:12]}')
    remove_path(staging); staging.mkdir(parents=True)
    fp=hashlib.sha256(canonical_json([{'repo_id':r,'artifact_id':e.get('artifact_id'),'content_fingerprint':e.get('content_fingerprint')} for r,(_,e) in sorted(zip(repo_ids,sources))]).encode()).hexdigest()
    build_id=stable_id('value_flow_knowledge_build',scope_id,fp,__version__); started=utc_now(); con=None
    transaction_started=False
    try:
        con=connect_database(staging/VALUE_FLOW_KNOWLEDGE_DATABASE,memory_limit=duckdb_memory_limit,threads=duckdb_threads,preserve_insertion_order=False)
        initialize_schema(con,VALUE_FLOW_KNOWLEDGE_DDL)
        con.execute('BEGIN TRANSACTION'); transaction_started=True
        con.execute("INSERT INTO value_flow_knowledge_build VALUES (?,?,?,?,?,?,?,'building',?,?)",[build_id,scope_id,__version__,VALUE_FLOW_KNOWLEDGE_SCHEMA_VERSION,'value-flow-evidence/v1',started,None,canonical_json({}),canonical_json({})])
        record_count=0
        for repo_id,(path,env) in sorted(zip(repo_ids,sources)):
            con.execute('INSERT INTO value_flow_evidence_source VALUES (?,?,?,?,?)',[scope_id,repo_id,env.get('artifact_id'),env.get('content_fingerprint'),canonical_json(env.get('payload') or {})])
            for descriptor in ((env.get('payload') or {}).get('artifacts') or []):
                if not isinstance(descriptor,Mapping): continue
                artifact_name=str(descriptor.get('artifact_name') or ''); raw=_read(_safe(path,str(descriptor.get('relative_path') or '')))
                section=str(descriptor.get('section') or '')
                if section and isinstance(raw,Mapping): raw=raw.get(section) or []
                if not isinstance(raw,list): raise ValueError(f'value-flow payload section must be a list: {artifact_name}')
                rows=[]
                for ordinal,item in enumerate(raw,1):
                    if not isinstance(item,Mapping): continue
                    local=str(item.get('occurrence_id') or item.get('edge_id') or item.get('interface_id') or '').strip() or None
                    payload_json=canonical_json(item)
                    rid=stable_id('value_flow_evidence_record',scope_id,repo_id,artifact_name,local or '',ordinal,hashlib.sha256(payload_json.encode()).hexdigest())
                    rows.append((rid,scope_id,repo_id,artifact_name,local,ordinal,payload_json))
                bulk_insert(con,'INSERT INTO value_flow_evidence_record VALUES',rows)
                record_count+=len(rows)
        counts={'value_flow_evidence_source':len(repo_ids),'value_flow_evidence_record':record_count,**materialize_repository_value_flow(con,scope_id=scope_id)}
        checks={'typed_evidence_only':True,'direct_edges_only':True}
        completed=utc_now(); con.execute("UPDATE value_flow_knowledge_build SET completed_at=?, build_status='complete', counts_json=?, checks_json=? WHERE build_id=?",[completed,canonical_json(counts),canonical_json(checks),build_id]); con.execute('COMMIT'); transaction_started=False; con.execute('CHECKPOINT'); con.close(); con=None
        manifest=KnowledgeLayerManifest(scope_id=scope_id,repository_ids=tuple(sorted(repo_ids)),modes=('repository-value-flow',),producer_version=__version__,build_id=build_id,build_status='complete',counts=counts,materialized_marts=('workspace-repository-value-flow',),capabilities=('workspace.repository-value-flow','workspace.attribute-path-resolver'),artifacts={'database':VALUE_FLOW_KNOWLEDGE_DATABASE,'manifest':'knowledge-layer-manifest.json'},source_evidence=tuple({'artifact_id':e.get('artifact_id'),'artifact_kind':e.get('artifact_kind'),'schema_version':e.get('schema_version'),'content_fingerprint':e.get('content_fingerprint'),'artifact_path':str(p)} for p,e in sources),validation_status='complete',validation=checks,metadata={'value_flow_schema_version':VALUE_FLOW_KNOWLEDGE_SCHEMA_VERSION,'produced_model':'repository_value_flow/v6','coverage':{'coverage_status':'complete'},'started_at':started,'completed_at':completed})
        write_json(staging/'knowledge-layer-manifest.json',manifest.to_dict()); publish_directory_atomic(staging,out,replace=replace,existing_label='knowledge-layer output'); return manifest.to_dict()
    except Exception:
        if con is not None:
            if transaction_started:
                try: con.execute('ROLLBACK')
                except Exception: pass
            con.close()
        remove_path(staging); raise
