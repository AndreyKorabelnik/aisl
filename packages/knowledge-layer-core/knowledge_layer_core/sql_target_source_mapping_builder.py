from __future__ import annotations

from collections import defaultdict
import json, os, re, uuid
from pathlib import Path
from typing import Any, Mapping

from prepared_knowledge_runtime.contracts import KnowledgeLayerManifest
from prepared_knowledge_runtime.database import connect_database, initialize_schema
from prepared_knowledge_runtime.io import write_manifest
from .logical_physical_mapping_ingestion import resolve_knowledge_layer_input
from .metrics import canonical_json, utc_now
from prepared_knowledge_runtime.normalization import stable_id
from .publication import publish_directory_atomic, remove_path
from .sql_producer_observations import (
    derive_sql_producer_observations,
    build_sql_producer_traversal,
    _scoped_parameter_environments,
    _match_sql_file_template,
)
from .sql_target_source_mapping_schema import SQL_TARGET_SOURCE_MAPPING_DATABASE, SQL_TARGET_SOURCE_MAPPING_DDL, SQL_TARGET_SOURCE_MAPPING_SCHEMA_VERSION, SQL_TARGET_SOURCE_MAPPING_TABLES
from .sql_value_source_semantics import StorageKeySemanticIndex, is_parent_key_identity_extraction
from .version import __version__



_PLACEHOLDER_PATTERN = re.compile(
    r"\$\{\s*\$?(?P<braced>[^{}]+?)\s*\}|"
    r"\{\{\s*(?P<jinja>[^{}]+?)\s*\}\}|"
    r"%\((?P<py>[^)]+)\)s|"
    r"(?<![A-Za-z0-9$])\$(?P<bare>[A-Za-z_][A-Za-z0-9_.]*)"
)

def _placeholder_tokens(text: str) -> list[str]:
    return [
        str(m.group("braced") or m.group("jinja") or m.group("py") or m.group("bare") or "")
        .strip().lstrip("$")
        for m in _PLACEHOLDER_PATTERN.finditer(str(text or ""))
    ]

def _replace_placeholder(text: str, name: str, value: str) -> str:
    escaped=re.escape(name)
    return re.sub(
        r"\$\{\s*\$?"+escaped+r"\s*\}|"
        r"\{\{\s*"+escaped+r"\s*\}\}|"
        r"%\("+escaped+r"\)s|"
        r"(?<![A-Za-z0-9$])\$"+escaped+r"\b",
        lambda _m:value, str(text or "")
    )

class _PlaceholderResolutionIndex:
    """Resolve source relation placeholders from exact observed workflow scope evidence.

    Existing ``sql_placeholder_binding_resolution`` rows are preferred. In addition,
    structurally paired ``name/prior_value`` records are correlated to one SQL file only
    when the same scoped parameter environment contains an exact repository-local SQL
    file reference. Nested placeholders are substituted recursively while unresolved
    environment values remain visible; repository-global values are used only when
    unique and otherwise contribute ambiguity diagnostics.
    """
    def __init__(self, sc: Any, repo_id: str) -> None:
        self._exact: dict[tuple[str,str,str],list[dict[str,Any]]]=defaultdict(list)
        self._global: dict[str,list[dict[str,Any]]]=defaultdict(list)
        try:
            rows=sc.execute(
                "SELECT workflow_context_file,sql_file,placeholder,resolved_value,resolution_status,resolution_reasons_json,sql_workflow_binding_id,evidence_json "
                "FROM sql_placeholder_binding_resolution WHERE repo_id=? ORDER BY workflow_context_file,sql_file,placeholder,sql_placeholder_binding_resolution_id",
                [repo_id],
            ).fetchall()
        except Exception:
            rows=[]
        for wf,sql_file,name,value,status,reasons,binding_id,evidence in rows:
            record={
                'workflow_context_file':str(wf),'sql_file':str(sql_file),'placeholder':str(name),
                'resolved_value':str(value or ''),'resolution_status':str(status or ''),
                'resolution_reasons':_json(reasons,[]),'workflow_binding_id':str(binding_id or ''),
                'evidence':_json(evidence,[]),'resolution_basis':'sql_placeholder_binding_resolution',
            }
            self._exact[(str(wf),str(sql_file),str(name))].append(record)
            self._global[str(name)].append(record)

        # Generic scoped parameter records (for example ``name=app.sbs.table.name``
        # plus ``prior_value=policyaccruals``) are already observed SQL knowledge.
        # Correlate them to a SQL file only through a file-valued parameter in the
        # *same* scope; sibling workflow scopes are never merged.
        try:
            known_sql_files=sorted({
                str(row[0]) for row in sc.execute(
                    "SELECT DISTINCT file FROM sql_statement WHERE repo_id=? AND file IS NOT NULL ORDER BY file",
                    [repo_id],
                ).fetchall() if row[0]
            })
            environments=_scoped_parameter_environments(sc,repo_id=repo_id)
        except Exception:
            known_sql_files=[]; environments=[]
        # Resolved workflow file references let us preserve the same exact CTL
        # parameter scope even when the scope points to a pipeline config rather
        # than directly to one SQL file. The chain is fully observed:
        # scoped parameter binding -> referenced config -> config filePath -> SQL.
        try:
            reference_rows=sc.execute(
                "SELECT source_file,source_fact_id,resolved_target_file,resolved_target_kind,resolution_status,evidence_json "
                "FROM sql_workflow_file_reference WHERE repo_id=? AND resolution_status='resolved' "
                "AND resolved_target_file IS NOT NULL ORDER BY source_file,source_fact_id,resolved_target_file",
                [repo_id],
            ).fetchall()
        except Exception:
            reference_rows=[]
        references_by_fact: dict[tuple[str,str],list[dict[str,Any]]]=defaultdict(list)
        references_by_source: dict[str,list[dict[str,Any]]]=defaultdict(list)
        for source_file,source_fact_id,target_file,target_kind,_status,evidence in reference_rows:
            item={
                'source_file':str(source_file or ''),'source_fact_id':str(source_fact_id or ''),
                'target_file':str(target_file or ''),'target_kind':str(target_kind or ''),
                'evidence':_json(evidence,[]),
            }
            references_by_fact[(item['source_file'],item['source_fact_id'])].append(item)
            references_by_source[item['source_file']].append(item)

        for env in environments:
            workflow_file=str(env.get('file') or '')
            target_basis: dict[str,str]={}
            # Direct exact SQL references observed in the scoped parameter values.
            for values in (env.get('values') or {}).values():
                for raw in values:
                    value=str(raw or '')
                    if not re.search(r"\.(?:sql|hql|q)(?:$|[?#])",value,re.IGNORECASE):
                        continue
                    matches=_match_sql_file_template(value,known_sql_files,workflow_file)
                    if len(matches)==1:
                        target_basis[str(matches[0])]='exact_scoped_parameter_environment_plus_repository_sql_file_reference'

            # Exact observed config-chain references. Correlate the CTL scope to
            # its config by the binding fact id, then reuse only SQL files that
            # the resolved config itself references.
            for parameter_record in env.get('records') or []:
                value=str(parameter_record.get('value') or '')
                if not re.search(r"\.(?:json|ya?ml|conf|properties)(?:$|[?#])",value,re.IGNORECASE):
                    continue
                fact_ids=[
                    str(parameter_record.get('value_binding_id') or ''),
                    str(parameter_record.get('name_binding_id') or ''),
                ]
                config_refs=[]
                for fact_id in fact_ids:
                    if fact_id:
                        config_refs.extend(references_by_fact.get((workflow_file,fact_id),()))
                config_files=sorted({
                    str(item.get('target_file') or '') for item in config_refs
                    if str(item.get('target_file') or '') and re.search(r"\.(?:json|ya?ml|conf|properties)$",str(item.get('target_file') or ''),re.IGNORECASE)
                })
                for config_file in config_files:
                    for child in references_by_source.get(config_file,()):
                        sql_file=str(child.get('target_file') or '')
                        if sql_file in known_sql_files and re.search(r"\.(?:sql|hql|q)$",sql_file,re.IGNORECASE):
                            target_basis.setdefault(sql_file,'exact_scoped_parameter_environment_via_resolved_config_sql_reference')

            if not target_basis:
                continue
            records_by_name={str(item.get('name') or ''):item for item in env.get('records') or [] if item.get('name')}
            for sql_file,basis in sorted(target_basis.items()):
                for name,values in sorted((env.get('values') or {}).items()):
                    unique_values=sorted({str(item) for item in values if str(item)})
                    if len(unique_values)!=1:
                        continue
                    value=unique_values[0]
                    source=records_by_name.get(str(name)) or {}
                    record={
                        'workflow_context_file':workflow_file,'sql_file':sql_file,'placeholder':str(name),
                        'resolved_value':value,
                        'resolution_status':'resolved' if not _placeholder_tokens(value) else 'partial',
                        'resolution_reasons':([] if not _placeholder_tokens(value) else ['scoped_parameter_value_has_unresolved_placeholders']),
                        'workflow_binding_id':str(source.get('value_binding_id') or source.get('name_binding_id') or ''),
                        'evidence':list(source.get('evidence') or []),
                        'resolution_basis':basis,
                        'scope_path':str(env.get('scope_path') or ''),
                    }
                    self._exact[(workflow_file,sql_file,str(name))].append(record)
                    self._global[str(name)].append(record)

        # Direct workflow/config bindings can resolve a nested placeholder only if
        # the repository observes one unique value for that name. Multiple stand-
        # specific values remain ambiguous and are never selected.
        try:
            direct_rows=sc.execute(
                "SELECT file,binding_path,binding_name,scalar_value,value_expression,evidence_json "
                "FROM sql_workflow_binding WHERE repo_id=? ORDER BY file,binding_path",
                [repo_id],
            ).fetchall()
        except Exception:
            direct_rows=[]
        for file,path,name,scalar,expression,evidence in direct_rows:
            pname=str(name or '').strip().lstrip('$')
            value=str(scalar if scalar is not None else expression or '').strip()
            if not pname or not value:
                continue
            self._global[pname].append({
                'workflow_context_file':str(file or ''),'sql_file':'','placeholder':pname,
                'resolved_value':value,'resolution_status':'resolved' if not _placeholder_tokens(value) else 'partial',
                'resolution_reasons':[],'workflow_binding_id':'','evidence':_json(evidence,[]),
                'resolution_basis':'repository_observed_binding_value','binding_path':str(path or ''),
            })

    @staticmethod
    def _usable_exact_values(candidates: list[dict[str,Any]]) -> list[str]:
        values=set()
        for item in candidates:
            value=str(item.get('resolved_value') or '')
            if not value:
                continue
            basis=str(item.get('resolution_basis') or '')
            status=str(item.get('resolution_status') or '')
            if basis in {'exact_scoped_parameter_environment_plus_repository_sql_file_reference','exact_scoped_parameter_environment_via_resolved_config_sql_reference'}:
                if status in {'resolved','partial','probable'}:
                    values.add(value)
                continue
            if status=='resolved' and not _placeholder_tokens(value):
                values.add(value)
        return sorted(values)

    def resolve_relation(self, relation_name: str, *, workflow_context: str, sql_file: str, max_depth: int=8) -> tuple[str,str,list[dict[str,Any]]]:
        observed=str(relation_name or '')
        current=observed
        diagnostics=[]
        for _ in range(max_depth):
            names=_placeholder_tokens(current)
            if not names:
                break
            changed=False
            for name in names:
                exact=self._exact.get((str(workflow_context or ''),str(sql_file or ''),name),[])
                candidates=list(exact)
                candidate_bases=sorted({str(item.get('resolution_basis') or '') for item in candidates if str(item.get('resolution_basis') or '')})
                basis=candidate_bases[0] if len(candidate_bases)==1 else 'exact_workflow_sql_scope'
                values=self._usable_exact_values(candidates)
                if len(values)==1:
                    value=values[0]
                    current=_replace_placeholder(current,name,value)
                    diagnostics.append({
                        'placeholder':name,'status':'resolved' if not _placeholder_tokens(value) else 'partial',
                        'resolved_value':value,'resolution_basis':basis,
                        'evidence':[item for item in candidates if str(item.get('resolved_value') or '')==value],
                    })
                    changed=True
                    break
                diagnostic_candidates=candidates if candidates else list(self._global.get(name,[]))
                diagnostic_values=sorted({str(item.get('resolved_value') or '') for item in diagnostic_candidates if str(item.get('resolved_value') or '')})
                candidate_statuses={str(item.get('resolution_status') or '') for item in diagnostic_candidates}
                diagnostic_status=(
                    'ambiguous' if len(diagnostic_values)>1 else
                    'partial' if candidates and bool(candidate_statuses & {'partial','probable'}) else
                    'unresolved'
                )
                diagnostics.append({
                    'placeholder':name,
                    'status':diagnostic_status,
                    'observed_value':current,'candidate_values':diagnostic_values,'candidates':diagnostic_candidates,
                    'resolution_basis':basis if candidates else ('repository_observed_binding_candidates' if diagnostic_candidates else 'no_observed_binding'),
                })
            if not changed:
                break
        remaining=_placeholder_tokens(current)
        status='resolved' if not remaining else 'partial'
        return current,status,diagnostics

def _json(value: Any, default: Any) -> Any:
    if value in (None, ""): return default
    if isinstance(value, (list,dict)): return value
    try: return json.loads(str(value))
    except Exception: return default


def _has_terminal_field_identity(relation_name: Any, column_name: Any) -> bool:
    """A product S2T field origin is resolved only with both relation and column identity."""
    return bool(str(relation_name or '').strip() and str(column_name or '').strip())


def _classify_terminal_source_identity(
    relation_name: Any, column_name: Any, *, placeholder_status: str = "resolved"
) -> tuple[str, str, str]:
    """Classify terminal identity without promoting unresolved placeholders to facts.

    A non-empty relation string such as ``schema.${table}`` is still useful
    evidence, but it is not a resolved physical relation identity until the
    observed workflow bindings resolve the placeholder.
    """
    if not _has_terminal_field_identity(relation_name, column_name):
        return "unresolved", "candidate", "terminal_source_field_identity_unresolved"
    if str(placeholder_status or "") != "resolved":
        return "partial", "candidate", "source_relation_placeholder_unresolved"
    return "resolved", "derived", "terminal_physical_relation_without_observed_local_producer"


def _mapping_branch_metadata(origin: Mapping[str, Any], traversal: Any, *, target_logical_name: str = "") -> dict[str, Any]:
    # Keep mapping-side fallback aligned with sql_workflow_target_lineage. Local
    # lineage evidence is preferred when available; this helper serves additional
    # materialization/workflow-copy seeds that do not have a local lineage row.
    relation_path = [dict(item) for item in origin.get('relation_path') or () if isinstance(item, dict)]
    target_key = str(target_logical_name or '').strip().casefold().rsplit('.', 1)[-1]
    search_from = 0
    if target_key:
        for index, item in enumerate(relation_path):
            kind = str(item.get('relation_kind') or '').strip().lower()
            name = str(item.get('relation_name') or '').strip().casefold().rsplit('.', 1)[-1]
            if kind in {'cte','derived','set','subquery'} and name == target_key:
                search_from = index + 1
                break
    physical_candidates = [
        item for item in relation_path[search_from:]
        if str(item.get('relation_kind') or '') in {'physical','physical_template'} and str(item.get('scope_id') or '')
    ]
    # A physical staging/history relation with the same logical basename as the
    # published target is part of target maintenance, not a source branch anchor.
    # Prefer the next observed physical relation when one exists; fall back to the
    # same-name relation only when it is the only available branch evidence.
    non_target_candidates = [
        item for item in physical_candidates
        if not target_key or str(item.get('relation_name') or '').strip().casefold().rsplit('.', 1)[-1] != target_key
    ]
    first_physical = (non_target_candidates or physical_candidates or [None])[0]
    if first_physical is None:
        fallback_candidates = [
            item for item in relation_path
            if str(item.get('relation_kind') or '') in {'physical','physical_template'} and str(item.get('scope_id') or '')
        ]
        non_target_fallback = [
            item for item in fallback_candidates
            if not target_key or str(item.get('relation_name') or '').strip().casefold().rsplit('.', 1)[-1] != target_key
        ]
        first_physical = (non_target_fallback or fallback_candidates or [None])[0]
    if first_physical is None:
        return {
            'source_branch':None,'source_branch_scope_id':None,'source_branch_ordinal':None,
            'branch_relation_name':None,'driver_relation_name':None,'driver_relation_status':'unresolved',
            'driver_relation_basis':'branch_driver_not_aggregated','driver_relation_candidates':[],
            'source_relation_role':'unknown','source_relation_role_basis':'branch_scope_not_observed_in_relation_path',
            'relation_path':relation_path,
        }
    scope_id=str(first_physical.get('scope_id') or '')
    candidate_ids=[
        str(item) for item in traversal.relations_by_scope.get(scope_id,())
        if str((traversal.relations.get(str(item)) or {}).get('usage_role') or '').strip().lower()=='from'
    ]
    driver_id=candidate_ids[0] if len(candidate_ids)==1 else None
    driver=traversal.relations.get(driver_id) if driver_id else None
    driver_name=str((driver or {}).get('name') or '') or None
    ordinal=int(first_physical.get('scope_ordinal') or 0) or None
    def safe_label(value: Any) -> str | None:
        text=str(value or '').strip()
        if not text or '${' in text or '{{' in text or '%(' in text: return None
        return text.rsplit('.',1)[-1] or None
    branch=safe_label(driver_name) or safe_label(first_physical.get('relation_name')) or (f'branch_{ordinal}' if ordinal else scope_id)
    try: anchor_index=relation_path.index(first_physical)
    except ValueError: anchor_index=0
    join_steps=[item for item in relation_path[anchor_index:] if str(item.get('usage_role') or '').strip().lower()=='join']
    first_role=str(first_physical.get('usage_role') or '').strip().lower()
    first_relation_id=str(first_physical.get('relation_id') or '')
    if join_steps:
        role='enrichment'; basis='observed_join_boundary_on_value_path_after_target_branch_anchor'
    elif driver_id and first_relation_id==driver_id:
        role='driver_path'; basis='unique_from_relation_in_target_branch_scope_and_no_join_boundary_on_value_path'
    elif first_role=='from':
        role='driver_candidate'; basis='value_path_enters_target_branch_via_from_relation_but_driver_is_not_unique' if len(candidate_ids)!=1 else 'value_path_enters_target_branch_via_from_relation'
    elif first_role=='join':
        role='enrichment'; basis='value_path_enters_target_branch_via_observed_join_relation'
    else:
        role='unknown'; basis='target_branch_relation_usage_role_not_decisive'
    return {
        'source_branch':branch,'source_branch_scope_id':scope_id,'source_branch_ordinal':ordinal,
        'branch_relation_name':driver_name,'driver_relation_name':None,'driver_relation_status':'unresolved',
        'driver_relation_basis':'branch_driver_not_aggregated','driver_relation_candidates':[],
        'driver_candidate_relation_ids':candidate_ids,'source_relation_role':role,'source_relation_role_basis':basis,'relation_path':relation_path,
    }


def _preferred_branch_metadata(evidence: Mapping[str, Any], origin: Mapping[str, Any], traversal: Any, *, target_logical_name: str) -> dict[str, Any]:
    observed = evidence.get('branch') if isinstance(evidence, Mapping) else None
    if isinstance(observed, Mapping) and str(observed.get('source_branch_scope_id') or ''):
        result = dict(observed)
        target_key = str(target_logical_name or '').strip().casefold().rsplit('.', 1)[-1]
        observed_branch_relation = str(result.get('branch_relation_name') or result.get('driver_relation_name') or '')
        observed_branch_key = observed_branch_relation.strip().casefold().rsplit('.', 1)[-1]
        # A staging/history relation with the same basename as the published target
        # is target-maintenance context, not the source branch. Recompute from the
        # current observed relation path so a deeper branch anchor can be used.
        if target_key and observed_branch_key == target_key:
            return _mapping_branch_metadata(origin, traversal, target_logical_name=target_logical_name)
        # A21 branch evidence used ``driver_relation_name`` for the immediate
        # relation that drives the target UNION/query branch.  A22 makes that
        # distinction explicit: branch_relation_name is observed branch structure,
        # while driver_relation_name is a derived terminal source relation computed
        # across all mappings in the branch.
        if not result.get('branch_relation_name') and result.get('driver_relation_name'):
            result['branch_relation_name'] = result.get('driver_relation_name')
        result['driver_relation_name'] = None
        result['driver_relation_status'] = 'unresolved'
        result['driver_relation_basis'] = 'branch_driver_not_aggregated'
        result['driver_relation_candidates'] = []
        return result
    return _mapping_branch_metadata(origin, traversal, target_logical_name=target_logical_name)


def _resolve_branch_driver_metadata(raw_records: list[dict[str, Any]]) -> dict[tuple[Any, ...], dict[str, Any]]:
    """Derive one terminal driver relation per observed target branch when possible.

    Branch membership and relation roles are already derived from observed SQL scope
    and JOIN facts.  The driver itself is selected only when all terminal mappings
    classified as ``driver_path`` in that branch point to one relation identity.
    Multiple identities remain explicit ambiguity; no ranking or name heuristic is
    used.
    """
    groups: dict[tuple[Any, ...], dict[str, Any]] = {}
    for record in raw_records:
        key = (
            str(record.get('repo_id') or ''), str(record.get('workflow') or ''),
            str(record.get('target') or ''), str(record.get('source_branch_scope_id') or ''),
            int(record.get('source_branch_ordinal') or 0), str(record.get('source_branch') or ''),
            str(record.get('branch_relation_name') or ''),
        )
        slot = groups.setdefault(key, {'candidates': {}, 'all_records': []})
        slot['all_records'].append(record)
        if str(record.get('source_relation_role') or '') != 'driver_path':
            continue
        relation = str(record.get('source_relation_name') or '').strip()
        if not relation:
            continue
        statuses = slot['candidates'].setdefault(relation, set())
        statuses.add(str(record.get('mapping_status') or ''))

    resolved: dict[tuple[Any, ...], dict[str, Any]] = {}
    for key, slot in groups.items():
        candidates = sorted(slot['candidates'])
        if len(candidates) == 1:
            relation = candidates[0]
            statuses = slot['candidates'][relation]
            status = 'resolved' if 'resolved' in statuses else 'partial'
            basis = (
                'unique_terminal_relation_on_driver_path_within_observed_branch'
                if status == 'resolved' else
                'unique_terminal_relation_on_driver_path_within_observed_branch_placeholder_partial'
            )
        elif len(candidates) > 1:
            relation = None
            status = 'ambiguous'
            basis = 'multiple_terminal_relations_on_driver_paths_within_observed_branch'
        else:
            relation = None
            status = 'unresolved'
            basis = 'no_terminal_relation_on_driver_path_within_observed_branch'
        meta = {
            'driver_relation_name': relation,
            'driver_relation_status': status,
            'driver_relation_basis': basis,
            'driver_relation_candidates': candidates,
        }
        resolved[key] = meta
        for record in slot['all_records']:
            record.update(meta)
    return resolved


def _counts(c: Any) -> dict[str,int]:
    return {t:int(c.execute(f'SELECT count(*) FROM "{t}"').fetchone()[0]) for t in SQL_TARGET_SOURCE_MAPPING_TABLES}


def _build_diagnostics(counts: Mapping[str, int]) -> list[dict[str, Any]]:
    """Publish visible diagnostics for useful-but-empty mapping outcomes."""
    observed = int(counts.get('sql_observed_relation_materialization') or 0)
    mappings = int(counts.get('sql_target_source_mapping') or 0)
    gaps = int(counts.get('sql_target_source_mapping_gap') or 0)
    if observed > 0 and mappings == 0:
        return [{
            'code': 'sql_target_source_mapping_empty_with_observed_materializations',
            'severity': 'warning',
            'message': 'Observed SQL relation materializations exist, but no target-to-source column mappings were produced.',
            'basis': 'observed_relation_materializations_without_target_column_mapping_seed',
            'counts': {
                'sql_observed_relation_materialization': observed,
                'sql_target_source_mapping': mappings,
                'sql_target_source_mapping_gap': gaps,
            },
        }]
    return []


def _insert_source(c: Any, *, scope_id: str, role: str, source: Any) -> None:
    item=source.input_item
    c.execute("INSERT INTO sql_target_source_mapping_source VALUES (?,?,?,?,?,?,?,?)",[
        stable_id('sql_target_source_mapping_source',scope_id,role,item.get('artifact_id')),
        scope_id,role,str(item.get('artifact_id') or ''),str(item.get('model_kind') or ''),str(item.get('schema_version') or ''),
        str(item.get('content_fingerprint') or ''),str(source.output_path),
    ])


def _usage_payloads(sc: Any, repo_id: str) -> dict[str,dict[str,Any]]:
    out={}
    for uid,payload in sc.execute("SELECT sql_column_usage_id,payload_json FROM sql_column_usage WHERE repo_id=? ORDER BY sql_column_usage_id",[repo_id]).fetchall():
        out[str(uid)]=_json(payload,{})
    return out


def _materialize_value_sources(
    c: Any, *, sc: Any, repo_id: str, raw_records: list[dict[str,Any]], semantic_index: StorageKeySemanticIndex|None,
    model_storage_artifact_id: str|None, projections: Mapping[str,Mapping[str,Any]],
    placeholder_index: _PlaceholderResolutionIndex,
) -> tuple[int,int,dict[str,int]]:
    """Publish deduplicated product value origins without rewriting raw SQL paths."""
    payloads=_usage_payloads(sc,repo_id)
    by_group: dict[tuple[str,str,str,str,str,int,str,str],list[dict[str,Any]]]=defaultdict(list)
    for r in raw_records:
        by_group[(
            r['repo_id'],r['workflow'],r['target'],r['target_col'],
            str(r.get('source_branch_scope_id') or ''),int(r.get('source_branch_ordinal') or 0),
            str(r.get('source_branch') or ''),str(r.get('branch_relation_name') or ''),
        )].append(r)

    value_acc: dict[tuple[Any,...],dict[str,Any]]={}
    semantic_gap_count=0
    stats=defaultdict(int)
    semantic_gap_insert_rows: list[list[Any]]=[]
    value_insert_rows: list[list[Any]]=[]

    def insert_rows_batched(table: str, rows: list[list[Any]], *, column_count: int, batch_size: int = 200) -> None:
        for offset in range(0, len(rows), batch_size):
            batch=rows[offset:offset + batch_size]
            placeholders='(' + ','.join('?' for _ in range(column_count)) + ')'
            sql_text=f"INSERT OR IGNORE INTO {table} VALUES " + ','.join(placeholders for _ in batch)
            c.execute(sql_text,[value for row in batch for value in row])

    def add_value(group: tuple[Any,...], source: dict[str,Any], *, kind: str, status: str, basis: str, raw_id: str, evidence: dict[str,Any]) -> None:
        rel=str(source.get('source_relation_name') or ''); col=str(source.get('source_column') or '')
        relation_role=str(source.get('source_relation_role') or 'unknown')
        relation_role_basis=str(source.get('source_relation_role_basis') or 'branch_role_unresolved')
        key=(*group,rel,col,relation_role,relation_role_basis)
        slot=value_acc.get(key)
        if slot is None:
            slot={
                'group':group,'source':source,'kinds':set(),'statuses':set(),'bases':set(),'raw_ids':set(),'evidence':[]
            }; value_acc[key]=slot
        slot['kinds'].add(kind); slot['statuses'].add(status); slot['bases'].add(basis); slot['raw_ids'].add(raw_id)
        if evidence and evidence not in slot['evidence']: slot['evidence'].append(evidence)

    def add_semantic_gap(r: dict[str,Any], *, kind: str, basis: str, evidence: dict[str,Any]) -> None:
        nonlocal semantic_gap_count
        gid=stable_id('sql_target_source_mapping_gap',r['repo_id'],r['workflow'],r['target'],r['target_col'],r['mapping_id'],kind)
        semantic_gap_insert_rows.append([
            gid,r['repo_id'],r['workflow'],r['target'],r['target_col'],r.get('root_projection_id'),r.get('local_lineage_id'),kind,
            'semantic_value_origin_incomplete',basis,canonical_json(evidence),
        ])
        semantic_gap_count+=1

    for group, records in sorted(by_group.items()):
        # Exact storage identity is computed once per raw source.  It is deliberately
        # independent of schema placeholder resolution.
        alias_info: dict[str,tuple[str|None,str,str]]={}
        extraction_candidate: dict[str,bool]={}
        for r in records:
            uid=str(r.get('source_usage_id') or '')
            direct_path=payloads.get(uid,{}).get('projection_expression_path')
            typed_paths=[]
            if direct_path: typed_paths.append(direct_path)
            for pid in r.get('producer_projection_ids') or ():
                projection=projections.get(str(pid)) or {}
                for source_uid in projection.get('source_usages') or ():
                    path=payloads.get(str(source_uid),{}).get('projection_expression_path')
                    if path: typed_paths.append(path)
            extraction_candidate[r['mapping_id']]=any(is_parent_key_identity_extraction(path) for path in typed_paths)
            r['semantic_expression_paths']=[path for path in typed_paths if is_parent_key_identity_extraction(path)]
            if semantic_index is not None:
                alias_info[r['mapping_id']]=semantic_index.resolve_relation_alias(str(r.get('source_relation_name') or ''))
            else:
                alias_info[r['mapping_id']]=(None,'unknown','semantic_context_not_available')

        # Candidate parent rows are themselves raw SQL origins in the same target
        # lineage.  This avoids guessing a Java getter -> SQL column correspondence.
        parent_rows: dict[tuple[str,str],list[dict[str,Any]]]=defaultdict(list)
        if semantic_index is not None:
            for r in records:
                alias,repr_kind,_=alias_info[r['mapping_id']]
                if alias and not extraction_candidate[r['mapping_id']]:
                    parent_rows[(alias,repr_kind)].append(r)

        for r in records:
            raw_id=r['mapping_id']; uid=str(r.get('source_usage_id') or '')
            path=(r.get('semantic_expression_paths') or [payloads.get(uid,{}).get('projection_expression_path')])[0]
            if not extraction_candidate[raw_id]:
                add_value(group,r,kind='direct_terminal_source',status='resolved',basis='raw_terminal_sql_origin',raw_id=raw_id,evidence={})
                stats['direct_raw_origins']+=1
                continue

            # Structured parent-key extraction is known, but without model-storage
            # semantics it must remain syntactic rather than be promoted to a value origin.
            if semantic_index is None:
                add_value(group,r,kind='syntactic_origin_only',status='semantic_context_unavailable',basis='structured_parent_key_extraction_without_model_storage',raw_id=raw_id,evidence={'projection_expression_path':path})
                add_semantic_gap(r,kind='model_storage_semantics_unavailable',basis='structured_parent_key_extraction_requires_storage_key_semantics',evidence={'source_relation_name':r.get('source_relation_name'),'source_column':r.get('source_column'),'projection_expression_path':path})
                stats['semantic_context_missing']+=1
                continue

            child_alias,representation,alias_basis=alias_info[raw_id]
            if not child_alias:
                add_value(group,r,kind='syntactic_origin_only',status='semantic_unresolved',basis=alias_basis,raw_id=raw_id,evidence={'projection_expression_path':path})
                add_semantic_gap(r,kind=alias_basis,basis='exact_storage_identity_required_for_parent_key_semantics',evidence={'source_relation_name':r.get('source_relation_name'),'source_column':r.get('source_column'),'projection_expression_path':path})
                stats['storage_alias_unresolved']+=1
                continue

            ancestor_paths=semantic_index.ancestor_paths(child_alias,str(r.get('source_column') or ''))
            if not ancestor_paths:
                reason='parent_key_link_not_found'
                add_value(group,r,kind='syntactic_origin_only',status='semantic_unresolved',basis=reason,raw_id=raw_id,evidence={'child_storage_alias':child_alias,'projection_expression_path':path})
                add_semantic_gap(r,kind=reason,basis='observed_parent_key_link_required_for_semantic_collapse',evidence={'child_storage_alias':child_alias,'source_column':r.get('source_column'),'projection_expression_path':path})
                stats['parent_link_unresolved']+=1
                continue

            # `split(key, '.')[0]` selects the root key component.  Consider all
            # evidence-backed ancestors and accept a collapse only when they expose
            # exactly one direct SQL value identity in this target/representation.
            identities: dict[tuple[str,str],list[dict[str,Any]]]=defaultdict(list)
            supporting_paths=[]
            for ap in ancestor_paths:
                candidates=parent_rows.get((str(ap['ancestor_alias']),representation),[])
                if candidates: supporting_paths.append(ap)
                for p in candidates:
                    identities[(str(p.get('source_relation_name') or ''),str(p.get('source_column') or ''))].append(p)
            if len(identities)!=1:
                reason='parent_value_origin_not_found' if not identities else 'parent_value_origin_ambiguous'
                aliases=sorted({str(x['ancestor_alias']) for x in ancestor_paths})
                add_value(group,r,kind='syntactic_origin_only',status='semantic_unresolved',basis=reason,raw_id=raw_id,evidence={'child_storage_alias':child_alias,'candidate_parent_storage_aliases':aliases,'representation':representation,'projection_expression_path':path,'candidate_parent_origins':sorted([list(x) for x in identities])})
                add_semantic_gap(r,kind=reason,basis='unique_direct_ancestor_origin_required_in_same_target_lineage_and_representation',evidence={'child_storage_alias':child_alias,'candidate_parent_storage_aliases':aliases,'representation':representation,'candidate_parent_origins':sorted([list(x) for x in identities]),'model_storage_evidence_ids':sorted({i for ap in ancestor_paths for i in ap['evidence_ids']})})
                stats[reason]+=1
                continue

            parent_identity,parent_dupes=next(iter(identities.items()))
            parent=sorted(parent_dupes,key=lambda x:x['mapping_id'])[0]
            chosen_paths=[ap for ap in supporting_paths if any(str(x.get('source_relation_name') or '')==parent_identity[0] and str(x.get('source_column') or '')==parent_identity[1] for x in parent_rows.get((str(ap['ancestor_alias']),representation),[]))]
            evidence={
                'child_storage_alias':child_alias,'parent_storage_aliases':[str(ap['ancestor_alias']) for ap in chosen_paths],'representation':representation,
                'storage_identity_basis':alias_basis,'parent_key_link_basis':'+'.join(sorted({str(ap['basis']) for ap in chosen_paths})),'model_storage_evidence_ids':sorted({i for ap in chosen_paths for i in ap['evidence_ids']}),
                'projection_expression_path':path,'collapsed_raw_source':{'relation_name':r.get('source_relation_name'),'column':r.get('source_column')},
            }
            add_value(group,parent,kind='parent_key_semantic_collapse',status='resolved',basis='structured_parent_key_extraction_plus_observed_storage_parent_key_lineage_plus_direct_parent_sql_origin',raw_id=raw_id,evidence=evidence)
            # Also attach all duplicate direct parent raw paths to the same value row.
            for p in parent_dupes:
                add_value(group,p,kind='direct_terminal_source',status='resolved',basis='raw_terminal_sql_origin',raw_id=p['mapping_id'],evidence={})
            stats['parent_key_collapsed']+=1

    value_rows=0
    for key,slot in sorted(value_acc.items()):
        repo,wf,target,target_col,branch_scope_id,branch_ordinal,source_branch,branch_relation_name,rel,col,relation_role,relation_role_basis=key; src=slot['source']
        kinds=slot['kinds']
        if 'parent_key_semantic_collapse' in kinds and 'direct_terminal_source' in kinds:
            norm='direct_terminal_with_parent_key_equivalents'
        elif 'parent_key_semantic_collapse' in kinds:
            norm='parent_key_semantic_collapse'
        elif 'direct_terminal_source' in kinds:
            norm='direct_terminal_source'
        else:
            norm='syntactic_origin_only'
        statuses=slot['statuses']; status='resolved' if statuses=={'resolved'} else ('semantic_unresolved' if 'semantic_unresolved' in statuses else 'semantic_context_unavailable')
        display_rel,placeholder_status,placeholder_evidence=placeholder_index.resolve_relation(
            rel, workflow_context=str(src.get('terminal_workflow_context') or wf), sql_file=str(src.get('source_file') or '')
        )
        if placeholder_status!='resolved':
            if status=='resolved': status='partial'
            unresolved=[item for item in placeholder_evidence if item.get('status')!='resolved']
            if unresolved:
                gid=stable_id('sql_target_source_mapping_gap',repo,wf,target,target_col,'source_relation_placeholder_unresolved',rel,col,canonical_json(unresolved))
                semantic_gap_insert_rows.append([
                    gid,repo,wf,target,target_col,src.get('root_projection_id'),src.get('local_lineage_id'),
                    'source_relation_placeholder_unresolved','source_identity_incomplete','observed_workflow_placeholder_binding_resolution',
                    canonical_json({'source_relation_name':rel,'source_column':col,'source_sql_file':src.get('source_file'),'terminal_workflow_context':src.get('terminal_workflow_context') or wf,'placeholder_resolution':unresolved}),
                ])
                semantic_gap_count+=1; stats['source_relation_placeholder_unresolved']+=1
        vid=stable_id(
            'sql_target_value_source_mapping',repo,wf,target,target_col,
            branch_scope_id,branch_ordinal,source_branch,branch_relation_name,
            display_rel,col,relation_role,relation_role_basis,
        )
        semantic_evidence=list(slot['evidence'])
        if placeholder_evidence: semantic_evidence.append({'source_relation_placeholder_resolution':placeholder_evidence})
        value_insert_rows.append([
            vid,repo,wf,target,target_col,
            source_branch or None,branch_scope_id or None,branch_ordinal or None,branch_relation_name or None,
            src.get('driver_relation_name') or None,str(src.get('driver_relation_status') or 'unresolved'),
            str(src.get('driver_relation_basis') or 'branch_driver_unresolved'),canonical_json(src.get('driver_relation_candidates') or []),
            relation_role,relation_role_basis,
            src.get('source_usage_id'),src.get('source_relation_id'),display_rel or None,col or None,src.get('source_file'),
            (semantic_index.resolve_relation_alias(rel)[1] if semantic_index is not None and rel else None),norm,status,
            'derived' if norm!='direct_terminal_source' else str(src.get('knowledge_class') or 'derived'),
            '+'.join(sorted(slot['bases'])),canonical_json(sorted(slot['raw_ids'])),canonical_json(semantic_evidence),
            canonical_json({'sql_raw_mapping_preserved':True,'observed_source_relation_name':rel,'model_storage_artifact_id':model_storage_artifact_id,'normalization_kinds':sorted(kinds),'placeholder_resolution_status':placeholder_status,'branch':{'source_branch':source_branch or None,'source_branch_scope_id':branch_scope_id or None,'source_branch_ordinal':branch_ordinal or None,'branch_relation_name':branch_relation_name or None,'driver_relation_name':src.get('driver_relation_name') or None,'driver_relation_status':src.get('driver_relation_status') or 'unresolved','driver_relation_basis':src.get('driver_relation_basis') or 'branch_driver_unresolved','driver_relation_candidates':src.get('driver_relation_candidates') or [],'source_relation_role':relation_role,'source_relation_role_basis':relation_role_basis}}),
        ]); value_rows+=1
    insert_rows_batched('sql_target_value_source_mapping',value_insert_rows,column_count=28,batch_size=150)
    insert_rows_batched('sql_target_source_mapping_gap',semantic_gap_insert_rows,column_count=11,batch_size=300)
    return value_rows,semantic_gap_count,{k:int(v) for k,v in sorted(stats.items())}



def _local_lineage_origins(
    traversal: Any, *, workflow: str, usage_id: str | None, relation_id: str | None, column: str | None,
) -> list[dict[str, Any]]:
    """Continue a canonical local lineage row from its strongest observed terminal.

    Parser-backed rows normally carry terminal_column_usage_id. Synthetic rows
    produced from an observed final materialization may instead carry the exact
    terminal relation+column but no usage row. Both are observed evidence. Missing
    both remains unresolved; no relation or column is guessed.
    """
    if usage_id:
        return traversal.usage_origins(workflow, usage_id)
    if relation_id and column:
        return traversal.relation_column_origins(workflow, relation_id, column)
    return []


def _observed_materialization_projection_seeds(
    observations: Any, traversal: Any, existing_seed_keys: set[tuple[str, str, str, str]] | None = None,
) -> list[dict[str, Any]]:
    """Build exact target-column seeds from observed query materializations.

    A materialization is eligible only when producer observation already carries an
    exact query_id and output table.  The function never infers a target from file
    names or relation-name similarity.  Wildcard projections are intentionally not
    expanded here because doing so would require a separate output-column contract.
    """
    existing = existing_seed_keys or set()
    seeds: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set(existing)
    for materialization in observations.materializations:
        if str(materialization.get("resolution_status") or "") not in {"matched", "resolved"}:
            continue
        if str(materialization.get("kind") or "") not in {"script_call", "sql_write"}:
            continue
        # Additional target seeds are intentionally narrower than producer edges.
        # Workflow-published targets are already represented by
        # sql_workflow_target_column_lineage.  Ordinary script/sql-write outputs
        # remain available to SqlProducerColumnTraversal as intermediate producer
        # materializations, but must not become independent S2T targets.
        #
        # A finite literal-loop correlation is different: Core/KLC observed an
        # exact query-file -> output-table pairing that has no separate workflow
        # target contract (e.g. generic dictionary loops).  That exact observed
        # pairing is strong enough to seed a target without name heuristics.
        mapping_basis = str(materialization.get("mapping_basis") or "")
        if "observed_literal_loop_candidate_correlation" not in mapping_basis:
            continue
        workflow = str(materialization.get("workflow") or "")
        target = str(materialization.get("table") or "").strip()
        query_id = str(materialization.get("query_id") or "").strip()
        if not workflow or not target or not query_id:
            continue
        roots = tuple(traversal.root_scopes_by_query.get(query_id, ()))
        if not roots:
            continue
        for scope_id in roots:
            for projection_id in traversal.projections_by_scope.get(str(scope_id), ()):
                projection = traversal.projections.get(str(projection_id)) or {}
                if projection.get("wildcard"):
                    continue
                target_column = str(projection.get("output") or "").strip()
                if not target_column:
                    continue
                key = (workflow, target.lower(), target_column.lower(), str(projection_id))
                if key in seen:
                    continue
                seen.add(key)
                seed_id = stable_id(
                    "sql_observed_materialization_target_seed",
                    str(materialization.get("id") or ""),
                    str(projection_id),
                )
                seeds.append({
                    "local_lineage_id": seed_id,
                    "workflow": workflow,
                    "target": target,
                    "target_col": target_column,
                    "root_projection_id": str(projection_id),
                    "root_expression": projection.get("expression"),
                    "materialization_id": str(materialization.get("id") or ""),
                    "materialization": materialization,
                    "projection": projection,
                })
    return seeds


def _observed_workflow_copy_target_seeds(
    observations: Any, traversal: Any, existing_seed_keys: set[tuple[str, str, str, str]] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Seed published S2T targets from exact observed workflow-copy contracts.

    ``s2tTableList`` is stronger than an ordinary SQL write: it explicitly declares
    source relation -> published target relation.  Columns are accepted only when
    the existing observed producer index exposes a complete source output contract.
    """
    existing = existing_seed_keys or set()
    seen: set[tuple[str, str, str, str]] = set(existing)
    seeds: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    for materialization in observations.materializations:
        if str(materialization.get('kind') or '') != 'workflow_copy':
            continue
        if str(materialization.get('resolution_status') or '') not in {'matched', 'resolved'}:
            continue
        basis = str(materialization.get('mapping_basis') or '')
        if basis not in {
            'observed_workflow_s2t_table_list',
            'observed_scoped_parameter_environment_plus_referenced_s2t_table_list',
        }:
            continue
        workflow = str(materialization.get('workflow') or '')
        target = str(materialization.get('table') or '').strip()
        if not workflow or not target:
            continue
        contract, contract_basis = traversal.materializations.output_contract(materialization)
        branch_diagnostics = (
            traversal.materializations.output_contract_diagnostics(materialization)
            if hasattr(traversal.materializations, 'output_contract_diagnostics')
            else ()
        )
        for diagnostic in branch_diagnostics:
            gaps.append({
                'workflow': workflow,
                'target': target,
                'materialization': materialization,
                'gap_kind': str(diagnostic.get('gap_kind') or 'workflow_copy_source_branch_incomplete'),
                'mapping_basis': str(diagnostic.get('resolution_basis') or contract_basis),
                'source_branch': dict(diagnostic),
            })
        if contract is None:
            gaps.append({
                'workflow': workflow, 'target': target, 'materialization': materialization,
                'gap_kind': 'workflow_copy_output_contract_unresolved',
                'mapping_basis': contract_basis,
            })
            continue
        for target_column in sorted(contract):
            key = (workflow, target.lower(), str(target_column).lower(), '')
            if key in seen:
                continue
            seen.add(key)
            seed_id = stable_id(
                'sql_observed_workflow_copy_target_seed',
                str(materialization.get('id') or ''),
                str(target_column),
            )
            seeds.append({
                'local_lineage_id': seed_id, 'workflow': workflow, 'target': target,
                'target_col': str(target_column), 'root_projection_id': '', 'root_expression': None,
                'materialization_id': str(materialization.get('id') or ''),
                'materialization': materialization, 'contract_basis': contract_basis,
            })
    return seeds, gaps


def build_sql_target_source_mapping_knowledge_layer(
    sql_item: Mapping[str,Any], output: str|Path, *, scope_id: str,
    model_storage_item: Mapping[str,Any]|None=None,
    replace: bool=True, duckdb_memory_limit: str="1GB", duckdb_threads: int=1,
) -> dict[str,Any]:
    sql=resolve_knowledge_layer_input(sql_item,model_kind="sql-observed-data-usage",schema_version="knowledge_layer_sql/v2",source_materialization_id="sql-analysis")
    model_storage=None
    if model_storage_item is not None:
        model_storage=resolve_knowledge_layer_input(model_storage_item,model_kind="model-storage-semantics",schema_version="model-storage-semantics/v1",source_materialization_id="model-storage-semantics")
    out=Path(output).expanduser().resolve(); out.parent.mkdir(parents=True,exist_ok=True)
    if (out.exists() or out.is_symlink()) and not replace: raise FileExistsError(out)
    staging=out.with_name(f".{out.name}.building-{os.getpid()}-{uuid.uuid4().hex[:12]}"); remove_path(staging); staging.mkdir(parents=True)
    started=utc_now(); build_id=stable_id('sql_target_source_mapping_build',scope_id,sql.input_item.get('content_fingerprint'),model_storage.input_item.get('content_fingerprint') if model_storage else None,__version__)
    c=sc=msc=None
    try:
        c=connect_database(staging/SQL_TARGET_SOURCE_MAPPING_DATABASE,memory_limit=duckdb_memory_limit,threads=duckdb_threads,preserve_insertion_order=False); initialize_schema(c,SQL_TARGET_SOURCE_MAPPING_DDL)
        # The whole knowledge layer is assembled in an unpublished staging directory.
        # Keep row materialization in one DuckDB transaction: thousands of mapping
        # and diagnostic rows are otherwise autocommitted individually, which is
        # pure write overhead and does not add durability before atomic publication.
        c.execute('BEGIN TRANSACTION')
        c.execute("INSERT INTO sql_target_source_mapping_build VALUES (?,?,?,?,?,?,NULL,?,?)",[build_id,scope_id,__version__,SQL_TARGET_SOURCE_MAPPING_SCHEMA_VERSION,'building',started,canonical_json({}),canonical_json({})])
        _insert_source(c,scope_id=scope_id,role='sql',source=sql)
        if model_storage is not None: _insert_source(c,scope_id=scope_id,role='model_storage',source=model_storage)
        sc=connect_database(sql.database_path,read_only=True)
        repo_rows=sc.execute("SELECT repo_id FROM sql_analysis_repository ORDER BY repo_id").fetchall()
        if len(repo_rows)!=1: raise ValueError(f"sql-target-source-mapping requires one repository SQL artifact; found={len(repo_rows)}")
        repo_id=str(repo_rows[0][0])
        placeholder_index=_PlaceholderResolutionIndex(sc,repo_id)
        observations=derive_sql_producer_observations(sc,repo_id=repo_id,sql_artifact_id=str(sql.input_item.get('artifact_id') or ''))
        for d in observations.dependencies:
            c.execute("INSERT INTO sql_observed_workflow_dependency VALUES (?,?,?,?,?,?,?,?,?,?)",[d['id'],d['producer_workflow'],d['consumer_workflow'],d['entity_identity'],d['producer_expression'],d['consumer_expression'],d['resolution_status'],d['knowledge_class'],d['mapping_basis'],canonical_json(d['provenance'])])
        for m in observations.materializations:
            c.execute("INSERT INTO sql_observed_relation_materialization VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",[m['id'],m['workflow'],m['kind'],m['source_file'],m['source_fact_id'],m.get('source_symbol'),m.get('query_file') or None,m.get('query_id') or None,m.get('source_table') or None,m['table'],m['resolution_status'],m['knowledge_class'],m['mapping_basis'],canonical_json({**m.get('provenance',{}),'source_scope_ids':m.get('source_scopes') or []})])
        traversal, usages, relations=build_sql_producer_traversal(sc,repo_id=repo_id,observations=observations)
        local_rows=sc.execute(
            "SELECT sql_workflow_target_column_lineage_id,workflow_context_file,workflow_target_logical_name,target_column,root_projection_id,root_expression,"
            "terminal_column_usage_id,terminal_relation_id,terminal_relation_name,terminal_relation_kind,terminal_column,transformation_path_json,evidence_json "
            "FROM sql_workflow_target_column_lineage WHERE repo_id=? ORDER BY workflow_context_file,target_column,sql_workflow_target_column_lineage_id",[repo_id]
        ).fetchall()
        mapping_rows=gap_rows=0; raw_records=[]; raw_seen=set()
        existing_seed_keys: set[tuple[str,str,str,str]] = set()
        mapping_insert_rows: list[list[Any]] = []
        gap_insert_rows: list[list[Any]] = []
        def insert_rows_batched(table: str, rows: list[list[Any]], *, column_count: int, batch_size: int = 200) -> None:
            # DuckDB's Python executemany still crosses the Python/SQL boundary for
            # each row.  Build bounded multi-row VALUES statements instead.  The
            # values remain bound parameters, so this is only a publication
            # optimization and cannot alter SQL/provenance semantics.
            for offset in range(0, len(rows), batch_size):
                batch = rows[offset:offset + batch_size]
                placeholders = '(' + ','.join('?' for _ in range(column_count)) + ')'
                sql_text = f"INSERT OR IGNORE INTO {table} VALUES " + ','.join(placeholders for _ in batch)
                parameters = [value for row in batch for value in row]
                c.execute(sql_text, parameters)

        def flush_pending_rows() -> None:
            if mapping_insert_rows:
                insert_rows_batched('sql_target_source_mapping', mapping_insert_rows, column_count=38)
                mapping_insert_rows.clear()
            if gap_insert_rows:
                insert_rows_batched('sql_target_source_mapping_gap', gap_insert_rows, column_count=11, batch_size=400)
                gap_insert_rows.clear()

        def emit_seed(
            *, local_id: str, wf: str, target: str, target_col: str, root_pid: str,
            root_expr: Any, usage_id: str | None, im_rel_id: str | None,
            im_rel_name: str | None, im_rel_kind: str | None, im_col: str | None,
            local_trans: Any, evidence: Mapping[str,Any], origins: list[dict[str,Any]],
        ) -> None:
            nonlocal mapping_rows, gap_rows
            if not origins:
                gid=stable_id('sql_target_source_mapping_gap',repo_id,wf,target,target_col,local_id,'ultimate_source_unresolved')
                gap_insert_rows.append([
                    gid,repo_id,wf,target,target_col,root_pid,local_id,'ultimate_source_unresolved',
                    'ultimate_source_mapping_incomplete','recursive_observed_relation_producer_lineage',
                    canonical_json({'immediate_relation_id':im_rel_id,'immediate_relation_name':im_rel_name,'immediate_column':im_col,'local_evidence':dict(evidence)}),
                ]); gap_rows+=1
                return
            # A source usage/relation/column occurrence is one observed source fact.
            # Recursive traversal may reach that exact occurrence through many
            # equivalent projection/materialization paths; publishing one S2T row per
            # path multiplies noise without adding a new source identity. Aggregate
            # those paths into provenance while retaining separate rows whenever the
            # observed source occurrence or producer-resolution status differs.
            unique: dict[tuple[Any, ...], dict[str, Any]] = {}
            for origin in origins:
                branch_meta=_preferred_branch_metadata(evidence,origin,traversal,target_logical_name=target)
                key=(
                    branch_meta.get('source_branch_scope_id'),branch_meta.get('source_branch_ordinal'),
                    origin.get('usage_id'), origin.get('relation_id'), str(origin.get('column') or '').lower(),
                    str(origin.get('terminal_workflow_context') or ''),
                    str(origin.get('producer_resolution_status') or ''),
                    str(origin.get('producer_resolution_basis') or ''),
                )
                path_evidence={
                    'projection_path': list(origin.get('projection_path') or []),
                    'materialization_path': list(origin.get('materialization_path') or []),
                    'workflow_dependency_path': list(origin.get('workflow_dependency_path') or []),
                    'producer_resolution_path': list(origin.get('producer_resolution_path') or []),
                    'relation_path': list(origin.get('relation_path') or []),
                    'branch': branch_meta,
                }
                slot=unique.get(key)
                if slot is None:
                    representative=dict(origin)
                    representative['_equivalent_path_evidence']=[path_evidence]
                    unique[key]=representative
                    continue
                slot['_equivalent_path_evidence'].append(path_evidence)
                current_cost=(
                    len(slot.get('materialization_path') or []) +
                    len(slot.get('workflow_dependency_path') or []) +
                    len(slot.get('projection_path') or [])
                )
                candidate_cost=(
                    len(origin.get('materialization_path') or []) +
                    len(origin.get('workflow_dependency_path') or []) +
                    len(origin.get('projection_path') or [])
                )
                if candidate_cost < current_cost:
                    paths=slot['_equivalent_path_evidence']
                    representative=dict(origin)
                    representative['_equivalent_path_evidence']=paths
                    unique[key]=representative
            for origin in unique.values():
                src_rel=relations.get(str(origin.get('relation_id') or '')) or {}; src_usage=usages.get(str(origin.get('usage_id') or '')) or {}
                producer_projection_ids=[str(x).split(':',1)[1] for x in origin.get('projection_path') or () if str(x).startswith('projection:')]
                producer_trans=[]
                for pid in producer_projection_ids:
                    projection=traversal.projections.get(pid)
                    if projection: producer_trans.append({'projection_id':pid,'file':projection.get('file'),'output_name':projection.get('output') or None,'expression':projection.get('expression'),'expression_kind':projection.get('expression_kind'),'resolution_status':projection.get('resolution_status')})
                mats=list(origin.get('materialization_path') or []); deps=list(origin.get('workflow_dependency_path') or [])
                terminal_role=str(origin.get('terminal_semantic_role') or '')
                terminal_classification=str(origin.get('terminal_classification_status') or '')
                producer_resolution_path=list(origin.get('producer_resolution_path') or [])
                producer_resolution_status=str(origin.get('producer_resolution_status') or '')
                producer_resolution_basis=str(origin.get('producer_resolution_basis') or '')
                producer_resolution_candidates=list(origin.get('producer_resolution_candidates') or [])
                equivalent_paths=list(origin.get('_equivalent_path_evidence') or [])
                equivalent_projection_ids=sorted({str(item) for path in equivalent_paths for item in path.get('projection_path') or []})
                equivalent_materialization_ids=sorted({str(item) for path in equivalent_paths for item in path.get('materialization_path') or []})
                equivalent_dependency_ids=sorted({str(item) for path in equivalent_paths for item in path.get('workflow_dependency_path') or []})
                equivalent_producer_resolution_paths=[]
                seen_resolution_paths=set()
                for path in equivalent_paths:
                    value=list(path.get('producer_resolution_path') or [])
                    marker=canonical_json(value)
                    if marker not in seen_resolution_paths:
                        seen_resolution_paths.add(marker); equivalent_producer_resolution_paths.append(value)
                intermediate_frontier=terminal_role in {'internal_intermediate','external_or_shared_intermediate'}
                observed_source_relation_name=str(src_rel.get('name') or '') or None
                source_column=str(origin.get('column') or src_usage.get('column') or '') or None
                display_relation, placeholder_status, placeholder_evidence = placeholder_index.resolve_relation(
                    observed_source_relation_name or '',
                    workflow_context=str(origin.get('terminal_workflow_context') or wf),
                    sql_file=str(origin.get('source_file') or src_usage.get('file') or src_rel.get('file') or ''),
                )
                source_relation_name=str(display_relation or observed_source_relation_name or '') or None
                terminal_field_identity_resolved=_has_terminal_field_identity(source_relation_name,source_column)
                branch_meta=_preferred_branch_metadata(evidence,origin,traversal,target_logical_name=target)
                if intermediate_frontier:
                    if producer_resolution_status == 'ambiguous':
                        basis='intermediate_relation_observed_producer_ambiguous'
                    elif producer_resolution_basis == 'observed_exact_table_producer_column_lineage_unresolved':
                        basis='intermediate_relation_observed_producer_column_lineage_unresolved'
                    else:
                        basis='intermediate_relation_without_observed_producer'
                    resolution_status='unresolved'; knowledge_class='candidate'
                else:
                    resolution_status, knowledge_class, identity_basis = _classify_terminal_source_identity(
                        source_relation_name, source_column, placeholder_status=placeholder_status
                    )
                    if resolution_status == 'resolved' and mats:
                        if producer_resolution_path:
                            resolution_status='partial'; knowledge_class='derived'
                            basis='recursive_observed_relation_producer_lineage_via_repository_unique_exact_producer'
                        else:
                            basis='recursive_observed_relation_producer_lineage'
                    else:
                        basis=identity_basis
                mid=stable_id(
                    'sql_target_source_mapping',repo_id,wf,target,target_col,local_id,
                    origin.get('usage_id'),origin.get('relation_id'),str(origin.get('column') or '').lower(),
                    str(origin.get('terminal_workflow_context') or ''),
                    branch_meta.get('source_branch_scope_id'),branch_meta.get('source_branch_ordinal'),
                    producer_resolution_status,producer_resolution_basis,
                )
                rec={'mapping_id':mid,'repo_id':repo_id,'workflow':wf,'target':target,'target_col':target_col,'root_projection_id':root_pid,'local_lineage_id':local_id,'source_usage_id':str(origin.get('usage_id')) if origin.get('usage_id') else None,'source_relation_id':str(origin.get('relation_id')) if origin.get('relation_id') else None,'source_relation_name':source_relation_name,'observed_source_relation_name':observed_source_relation_name,'source_column':source_column,'source_file':str(origin.get('source_file') or src_usage.get('file') or src_rel.get('file') or '') or None,'mapping_status':resolution_status,'knowledge_class':knowledge_class,'producer_projection_ids':producer_projection_ids,'terminal_workflow_context':str(origin.get('terminal_workflow_context') or wf),**branch_meta}
                mapping_insert_rows.append([
                    mid,repo_id,wf,target,target_col,
                    branch_meta.get('source_branch'),branch_meta.get('source_branch_scope_id'),branch_meta.get('source_branch_ordinal'),
                    branch_meta.get('branch_relation_name'),None,'unresolved','branch_driver_not_aggregated',canonical_json([]),
                    branch_meta.get('source_relation_role') or 'unknown',branch_meta.get('source_relation_role_basis') or 'branch_role_unresolved',
                    root_pid,root_expr,local_id,usage_id,im_rel_id,im_rel_name,im_col,
                    rec['source_usage_id'],rec['source_relation_id'],rec['source_relation_name'],str(src_rel.get('kind') or '') or None,rec['source_column'],rec['source_file'],str(src_usage.get('usage_role') or '') or None,
                    len(mats),resolution_status,knowledge_class,basis,canonical_json(local_trans),canonical_json(producer_trans),canonical_json(mats),canonical_json(deps),canonical_json({'sql_artifact_id':sql.input_item.get('artifact_id'),'local_lineage_id':local_id,'local_terminal_relation_kind':im_rel_kind,'terminal_semantic_role':terminal_role or None,'terminal_classification_status':terminal_classification or None,'terminal_classification_basis':origin.get('terminal_classification_basis'),'producer_resolution_path':producer_resolution_path,'producer_resolution_status':producer_resolution_status or None,'producer_resolution_basis':producer_resolution_basis or None,'producer_resolution_candidates':producer_resolution_candidates,
                    'equivalent_observed_path_count':len(equivalent_paths),
                    'equivalent_projection_ids':equivalent_projection_ids,
                    'equivalent_materialization_ids':equivalent_materialization_ids,
                    'equivalent_workflow_dependency_ids':equivalent_dependency_ids,
                    'equivalent_producer_resolution_paths':equivalent_producer_resolution_paths,
                    'representative_path':{'projection_path':list(origin.get('projection_path') or []),'materialization_path':mats,'workflow_dependency_path':deps},
                    'observed_source_relation_name':observed_source_relation_name,
                    'resolved_source_relation_name':source_relation_name,
                    'source_relation_placeholder_status':placeholder_status,'source_relation_placeholder_evidence':placeholder_evidence,
                    'branch':branch_meta,'local_evidence':dict(evidence)})
                ]); mapping_rows+=1
                if intermediate_frontier:
                    if producer_resolution_status == 'ambiguous':
                        gap_kind='intermediate_producer_ambiguous'
                        gap_basis='multiple_repository_exact_table_producers_without_observed_workflow_path'
                    elif producer_resolution_basis == 'observed_exact_table_producer_column_lineage_unresolved':
                        gap_kind='intermediate_producer_column_lineage_unresolved'
                        gap_basis='observed_exact_table_producer_column_lineage_unresolved'
                    else:
                        gap_kind='intermediate_producer_unresolved'
                        gap_basis='semantic_intermediate_frontier_requires_observed_producer'
                    gid=stable_id('sql_target_source_mapping_gap',repo_id,wf,target,target_col,local_id,mid,gap_kind)
                    gap_insert_rows.append([
                        gid,repo_id,wf,target,target_col,root_pid,local_id,gap_kind,'ultimate_source_mapping_incomplete',gap_basis,
                        canonical_json({'source_mapping_id':mid,'relation_name':rec['source_relation_name'],'source_column':rec['source_column'],'semantic_role':terminal_role,'classification_status':terminal_classification,'classification_basis':origin.get('terminal_classification_basis'),'producer_resolution_status':producer_resolution_status or None,'producer_resolution_basis':producer_resolution_basis or None,'producer_resolution_candidates':producer_resolution_candidates})
                    ]); gap_rows+=1
                    continue
                if not terminal_field_identity_resolved:
                    gid=stable_id('sql_target_source_mapping_gap',repo_id,wf,target,target_col,local_id,mid,'ultimate_source_identity_unresolved')
                    gap_insert_rows.append([
                        gid,repo_id,wf,target,target_col,root_pid,local_id,'ultimate_source_identity_unresolved','ultimate_source_mapping_incomplete','terminal_source_requires_relation_and_column_identity',
                        canonical_json({'source_mapping_id':mid,'immediate_relation_name':im_rel_name,'immediate_column':im_col,'terminal_relation_id':origin.get('relation_id'),'terminal_column':origin.get('column') or src_usage.get('column'),'local_evidence':dict(evidence)}),
                    ]); gap_rows+=1
                    continue
                if mid not in raw_seen: raw_seen.add(mid); raw_records.append(rec)

        for local_row_index, row in enumerate(local_rows, start=1):
            local_id,wf,target,target_col,root_pid,root_expr,usage_id,im_rel_id,im_rel_name,im_rel_kind,im_col,local_trans_json,evidence_json=row
            existing_seed_keys.add((str(wf),str(target).lower(),str(target_col or '').lower(),str(root_pid or '')))
            origins=_local_lineage_origins(
                traversal, workflow=str(wf),
                usage_id=str(usage_id) if usage_id else None,
                relation_id=str(im_rel_id) if im_rel_id else None,
                column=str(im_col) if im_col else None,
            )
            emit_seed(
                local_id=str(local_id),wf=str(wf),target=str(target),target_col=str(target_col or ''),root_pid=str(root_pid or ''),root_expr=root_expr,
                usage_id=str(usage_id) if usage_id else None,im_rel_id=str(im_rel_id) if im_rel_id else None,im_rel_name=str(im_rel_name) if im_rel_name else None,
                im_rel_kind=str(im_rel_kind) if im_rel_kind else None,im_col=str(im_col) if im_col else None,
                local_trans=_json(local_trans_json,[]),evidence=_json(evidence_json,{}),origins=origins,
            )
            # Bound DuckDB transaction state while retaining coarse-grained batch
            # commits. The directory is unpublished until the whole build succeeds.
            if local_row_index % 100 == 0:
                flush_pending_rows()
                c.execute('COMMIT')
                c.execute('BEGIN TRANSACTION')

        materialization_seeds=_observed_materialization_projection_seeds(observations,traversal,existing_seed_keys)
        for seed in materialization_seeds:
            materialization=seed['materialization']; projection=seed['projection']
            materialization_id=str(seed['materialization_id'])
            origins=traversal.projection_origins(
                str(seed['workflow']),projection,materialization_path=(materialization_id,),
            )
            evidence={
                'seed_kind':'observed_relation_materialization_projection',
                'materialization_id':materialization_id,
                'materialization_kind':materialization.get('kind'),
                'materialization_source_file':materialization.get('source_file'),
                'materialization_query_file':materialization.get('query_file'),
                'materialization_query_id':materialization.get('query_id'),
                'materialization_mapping_basis':materialization.get('mapping_basis'),
                'materialization_provenance':materialization.get('provenance') or {},
                'projection_id':projection.get('id'),
                'projection_resolution_status':projection.get('resolution_status'),
            }
            emit_seed(
                local_id=str(seed['local_lineage_id']),wf=str(seed['workflow']),target=str(seed['target']),target_col=str(seed['target_col']),
                root_pid=str(seed['root_projection_id']),root_expr=seed.get('root_expression'),usage_id=None,im_rel_id=None,im_rel_name=None,im_rel_kind=None,im_col=None,
                local_trans=[{'projection_id':projection.get('id'),'expression':projection.get('expression'),'expression_kind':projection.get('expression_kind'),'resolution_status':projection.get('resolution_status')}],
                evidence=evidence,origins=origins,
            )
        workflow_copy_seeds, workflow_copy_seed_gaps = _observed_workflow_copy_target_seeds(
            observations, traversal, existing_seed_keys
        )
        for seed in workflow_copy_seeds:
            materialization=seed['materialization']
            evidence={
                'seed_kind':'observed_workflow_copy_publication',
                'materialization_id':seed['materialization_id'],
                'materialization_kind':materialization.get('kind'),
                'materialization_source_file':materialization.get('source_file'),
                'materialization_mapping_basis':materialization.get('mapping_basis'),
                'materialization_provenance':materialization.get('provenance') or {},
                'output_contract_basis':seed.get('contract_basis'),
            }
            emit_seed(
                local_id=str(seed['local_lineage_id']),wf=str(seed['workflow']),target=str(seed['target']),
                target_col=str(seed['target_col']),root_pid='',root_expr=None,usage_id=None,im_rel_id=None,
                im_rel_name=None,im_rel_kind=None,im_col=None,
                local_trans=[{'kind':'observed_workflow_copy_identity','materialization_id':seed['materialization_id']}],
                evidence=evidence,origins=traversal.materialized_table_column_origins(
                    str(seed['workflow']), str(seed['target']), str(seed['target_col'])
                ),
            )
        for gap in workflow_copy_seed_gaps:
            materialization=gap['materialization']
            gid=stable_id(
                'sql_target_source_mapping_gap',repo_id,gap['workflow'],gap['target'],
                gap['materialization'].get('id'),gap['gap_kind']
            )
            gap_insert_rows.append(
                [gid,repo_id,str(gap['workflow']),str(gap['target']),None,None,None,str(gap['gap_kind']),
                 'target_column_set_unresolved',str(gap['mapping_basis']),
                 canonical_json({'materialization_id':materialization.get('id'),'source_table':materialization.get('source_table'),
                                 'target_table':materialization.get('table'),'provenance':materialization.get('provenance') or {},
                                 'source_branch':gap.get('source_branch')})]
            ); gap_rows+=1

        # Preserve local target gaps as product gaps too.
        for row in sc.execute("SELECT workflow_context_file,workflow_target_logical_name,target_column,projection_id,gap_kind,impact,mapping_basis,evidence_json FROM sql_workflow_target_lineage_gap WHERE repo_id=? ORDER BY sql_workflow_target_lineage_gap_id",[repo_id]).fetchall():
            gid=stable_id('sql_target_source_mapping_gap',repo_id,*[str(x or '') for x in row[:7]])
            gap_insert_rows.append([gid,repo_id,str(row[0]),str(row[1]),str(row[2]) if row[2] else None,str(row[3]) if row[3] else None,None,str(row[4]),str(row[5]),str(row[6]),canonical_json(_json(row[7],{}))]); gap_rows+=1

        flush_pending_rows()

        # Resolve the business-useful driver relation at branch level only after
        # all terminal raw mappings are known.  This intentionally does not rank
        # candidates: one observed driver-path relation => derived driver; more
        # than one => explicit ambiguity; none => unresolved.
        branch_driver_metadata = _resolve_branch_driver_metadata(raw_records)
        for key, driver_meta in branch_driver_metadata.items():
            branch_repo,branch_workflow,branch_target,branch_scope,branch_ordinal,source_branch,branch_relation = key
            c.execute(
                "UPDATE sql_target_source_mapping SET driver_relation_name=?,driver_relation_status=?,driver_relation_basis=?,driver_relation_candidates_json=? "
                "WHERE repo_id=? AND workflow_context_file=? AND workflow_target_logical_name=? "
                "AND coalesce(source_branch_scope_id,'')=? AND coalesce(source_branch_ordinal,0)=? "
                "AND coalesce(source_branch,'')=? AND coalesce(branch_relation_name,'')=?",
                [
                    driver_meta.get('driver_relation_name'),driver_meta.get('driver_relation_status'),
                    driver_meta.get('driver_relation_basis'),canonical_json(driver_meta.get('driver_relation_candidates') or []),
                    branch_repo,branch_workflow,branch_target,branch_scope,branch_ordinal,source_branch,branch_relation,
                ],
            )

        # Persist the producer/raw-lineage phase before semantic normalization.
        # The staging directory is still unpublished and removed on any later
        # failure, so publication remains atomic while DuckDB can release the
        # transaction state before the next write-heavy phase.
        c.execute('COMMIT')
        c.execute('BEGIN TRANSACTION')
        semantic_index=None
        if model_storage is not None:
            msc=connect_database(model_storage.database_path,read_only=True); semantic_index=StorageKeySemanticIndex(msc)
        value_rows,semantic_gaps,semantic_stats=_materialize_value_sources(c,sc=sc,repo_id=repo_id,raw_records=raw_records,semantic_index=semantic_index,model_storage_artifact_id=str(model_storage.input_item.get('artifact_id')) if model_storage else None,projections=traversal.projections,placeholder_index=placeholder_index)
        gap_rows+=semantic_gaps
        counts=_counts(c); build_diagnostics=_build_diagnostics(counts); checks={'producer_materialization_count':len(observations.materializations),'workflow_dependency_count':len(observations.dependencies),'local_lineage_seed_count':len(local_rows),'observed_materialization_projection_seed_count':len(materialization_seeds),'workflow_copy_target_seed_count':len(workflow_copy_seeds),'workflow_copy_target_seed_gap_count':len(workflow_copy_seed_gaps),'raw_target_source_mapping_count':int(counts['sql_target_source_mapping']),'value_source_mapping_count':value_rows,'gap_count':int(counts['sql_target_source_mapping_gap']),'semantic_normalization_available':model_storage is not None,'semantic_normalization_stats':semantic_stats,'branch_driver_group_count':len(branch_driver_metadata),'branch_driver_resolved_count':sum(1 for item in branch_driver_metadata.values() if item.get('driver_relation_status') in {'resolved','partial'}),'branch_driver_ambiguous_count':sum(1 for item in branch_driver_metadata.values() if item.get('driver_relation_status')=='ambiguous'),'branch_driver_unresolved_count':sum(1 for item in branch_driver_metadata.values() if item.get('driver_relation_status')=='unresolved'),'name_heuristics_used':False,'semantic_role_required_for_traversal':False,'gold_data_used':False}
        completed=utc_now(); c.execute("UPDATE sql_target_source_mapping_build SET completed_at=?,build_status='complete',counts_json=?,checks_json=? WHERE build_id=?",[completed,canonical_json(counts),canonical_json(checks),build_id]); c.execute('COMMIT'); c.execute('CHECKPOINT'); c.close(); c=None; sc.close(); sc=None
        if msc is not None: msc.close(); msc=None
        manifest=KnowledgeLayerManifest(scope_id=scope_id,repository_ids=(repo_id,),modes=('sql',),producer_version=__version__,build_id=build_id,build_status='complete',counts=counts,materialized_marts=('sql-observed-relation-materialization','sql-observed-workflow-dependency','sql-target-source-mapping','sql-target-value-source-mapping'),capabilities=('common.sql-target-source-mapping','common.sql-target-value-source-mapping','common.sql-relation-materialization','common.sql-workflow-dependency'),artifacts={'database':SQL_TARGET_SOURCE_MAPPING_DATABASE,'manifest':'knowledge-layer-manifest.json'},source_evidence=(),validation_status='complete',validation=checks,metadata={'model_schema_version':SQL_TARGET_SOURCE_MAPPING_SCHEMA_VERSION,'started_at':started,'completed_at':completed,'source_sql_artifact_id':sql.input_item.get('artifact_id'),'source_model_storage_artifact_id':model_storage.input_item.get('artifact_id') if model_storage else None,'diagnostics':build_diagnostics})
        write_manifest(staging/'knowledge-layer-manifest.json',manifest); publish_directory_atomic(staging,out,replace=replace,existing_label='knowledge-layer output'); return manifest.to_dict()
    except Exception:
        if msc is not None: msc.close()
        if sc is not None: sc.close()
        if c is not None: c.close()
        remove_path(staging); raise
