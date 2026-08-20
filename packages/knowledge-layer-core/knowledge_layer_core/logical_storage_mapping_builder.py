from __future__ import annotations

from collections import defaultdict, deque
from contextlib import suppress
import os
from pathlib import Path
from typing import Any, Mapping
import uuid

from prepared_knowledge_runtime.contracts import KnowledgeLayerManifest
from prepared_knowledge_runtime.database import connect_database, initialize_schema
from prepared_knowledge_runtime.io import write_manifest
from .logical_physical_mapping_ingestion import resolve_knowledge_layer_input
from .logical_storage_mapping_schema import LOGICAL_STORAGE_DATABASE, LOGICAL_STORAGE_DDL, LOGICAL_STORAGE_SCHEMA_VERSION, LOGICAL_STORAGE_TABLES
from .metrics import canonical_json, utc_now
from prepared_knowledge_runtime.normalization import stable_id
from .publication import publish_directory_atomic, remove_path
from .version import __version__
from .storage_join_correspondence import record_properties, structural_reference_key_correspondences


def _counts(connection: Any) -> dict[str, int]:
    return {t:int(connection.execute(f'SELECT count(*) FROM "{t}"').fetchone()[0]) for t in LOGICAL_STORAGE_TABLES}


def _code_inventory(code_db: Path) -> dict[str, Any]:
    c=connect_database(code_db, read_only=True)
    try:
        types={}
        by_fqcn=defaultdict(list)
        for r in c.execute("SELECT repo_id,type_occurrence_id,fully_qualified_name FROM code_declared_type").fetchall():
            row={"repo_id":str(r[0]),"type_occurrence_id":str(r[1]),"fqcn":str(r[2])}; types[row["type_occurrence_id"]]=row; by_fqcn[row["fqcn"]].append(row)
        fields={str(r[0]):str(r[1]) for r in c.execute("SELECT field_occurrence_id,name FROM code_declared_field").fetchall()}
        effective=defaultdict(list)
        for r in c.execute("SELECT effective_field_occurrence_id,effective_owner_type_occurrence_id,field_occurrence_id,field_name,is_inherited FROM code_declared_effective_field").fetchall():
            row={"effective_field_occurrence_id":str(r[0]),"owner":str(r[1]),"field_occurrence_id":str(r[2]),"field_name":str(r[3]),"is_inherited":bool(r[4])}; effective[(row["owner"],row["field_name"])].append(row)
        rels=defaultdict(list); relationships=[]
        for r in c.execute("SELECT relationship_occurrence_id,repo_id,source_type_occurrence_id,target_type_occurrence_id,field_occurrence_id FROM code_declared_relationship ORDER BY relationship_occurrence_id").fetchall():
            row={"relationship_occurrence_id":str(r[0]),"repo_id":str(r[1]),"source":str(r[2]),"target":str(r[3]),"field_occurrence_id":str(r[4])}; rels[(row["source"],row["field_occurrence_id"])].append(row); relationships.append(row)
        parents=defaultdict(set)
        for r in c.execute("SELECT subtype_occurrence_id,resolved_supertype_occurrence_id FROM code_declared_inheritance WHERE resolved_supertype_occurrence_id IS NOT NULL").fetchall():
            parents[str(r[0])].add(str(r[1]))
        return {"types":types,"by_fqcn":by_fqcn,"fields":fields,"effective":effective,"rels":rels,"relationships":relationships,"parents":parents}
    finally: c.close()


def _is_descendant(child: str, ancestor: str, parents: Mapping[str,set[str]]) -> bool:
    if child == ancestor: return False
    q=deque([child]); seen={child}
    while q:
        node=q.popleft()
        for parent in parents.get(node,set()):
            if parent==ancestor: return True
            if parent not in seen: seen.add(parent); q.append(parent)
    return False


def _gap(connection: Any, source_id: str, kind: str, owner_kind: str, owner_id: str, message: str, details: Mapping[str,Any]) -> None:
    connection.execute("INSERT INTO logical_storage_mapping_gap VALUES (?, ?, ?, ?, ?, ?, ?, ?)",[
        stable_id("logical_storage_gap",source_id,kind,owner_kind,owner_id),source_id,kind,"warning",owner_kind,owner_id,message,canonical_json(dict(details))])


def _unique_text(values: Any) -> list[str]:
    result=[]
    for value in values:
        text=str(value or "").strip()
        if text and text not in result: result.append(text)
    return result


def _join_semantic_payload(
    *, relationship: Mapping[str, Any], source_type: Mapping[str, Any], target_type: Mapping[str, Any],
    field_name: str, derivations: list[dict[str, Any]], target_records: list[dict[str, Any]],
    storage_relationships: list[dict[str, Any]],
) -> dict[str, Any]:
    correspondences=structural_reference_key_correspondences(derivations,target_records)
    source_exprs=_unique_text(row.get("composed_reference_value_expression") for row in derivations)
    target_exprs=_unique_text(row.get("storage_key_expression") for row in target_records)
    target_key_fields=_unique_text(field for item in correspondences for field in item.get("target_key_fields") or ())
    diagnostics=[]
    basis: dict[str, Any]

    signature_count=len({canonical_json(item.get("canonical_signature")) for item in correspondences})
    if correspondences:
        if signature_count == 1:
            join_kind="reference_value_to_target_identity"
            status="strongly_supported"
            readiness="executable_storage_join"
            candidate_count=1
        else:
            join_kind="reference_value_to_target_identity"
            status="ambiguous"
            readiness="ambiguous"
            candidate_count=signature_count
            diagnostics.append({"code":"multiple_structural_join_signatures","message":"More than one exact structural reference-to-target identity signature is observed; candidates are preserved."})
        basis={
            "match_basis":"exact_structural_expression_signature",
            "structural_correspondence_count":len(correspondences),
            "canonical_signature_count":signature_count,
            "physical_model_required":False,
            "physical_join_claimed":False,
        }
    else:
        matched=[row for row in storage_relationships if row.get("mapping_status")=="matched"]
        concrete_targets=_unique_text(row.get("target_alias") for row in matched)
        direct_exprs=_unique_text(row.get("storage_key_expression") for row in matched)
        relation_kinds=_unique_text(row.get("storage_relation_kind") for row in matched)
        direct_source_exprs=_unique_text(record_properties(row.get("payload_json")).get("reference_value_expression") for row in matched)
        source_exprs=_unique_text([*source_exprs,*direct_source_exprs])
        target_exprs=_unique_text([*target_exprs,*direct_exprs])
        candidate_count=max(len(concrete_targets),len(direct_exprs),1 if matched else 0)
        if matched and len(concrete_targets) <= 1 and len(direct_exprs) <= 1:
            join_kind="target_storage_key_reference" if "single_reference" in relation_kinds else "storage_key_relationship"
            status="strongly_supported"
            readiness="executable_storage_join" if "single_reference" in relation_kinds else "transformation_required"
            basis={
                "match_basis":"observed_storage_reference_binding",
                "storage_relationship_count":len(matched),
                "storage_relation_kinds":relation_kinds,
                "physical_model_required":False,
                "physical_join_claimed":False,
            }
        elif matched:
            join_kind="storage_key_relationship"
            status="ambiguous"
            readiness="ambiguous"
            basis={
                "match_basis":"multiple_observed_storage_reference_bindings",
                "storage_relationship_count":len(matched),
                "storage_relation_kinds":relation_kinds,
                "concrete_targets":concrete_targets,
                "physical_model_required":False,
                "physical_join_claimed":False,
            }
            diagnostics.append({"code":"multiple_storage_join_candidates","message":"Multiple storage-reference candidates are observed; no candidate is silently selected."})
        elif derivations and target_records:
            join_kind="reference_value_to_target_identity"
            status="strongly_supported"
            readiness="requires_validation"
            candidate_count=max(len(source_exprs),len(target_exprs),1)
            basis={
                "match_basis":"reference_derivation_plus_target_identity_without_exact_signature",
                "reference_derivation_count":len(derivations),
                "target_identity_observation_count":len(target_records),
                "physical_model_required":False,
                "physical_join_claimed":False,
            }
            diagnostics.append({"code":"exact_structural_signature_not_established","message":"Reference derivation and target identity are observed, but exact structural equivalence is not established."})
        else:
            join_kind="not_established"
            status="unresolved"
            readiness="not_ready"
            candidate_count=0
            basis={
                "match_basis":"insufficient_storage_join_evidence",
                "reference_derivation_count":len(derivations),
                "target_identity_observation_count":len(target_records),
                "storage_relationship_count":len(matched),
                "physical_model_required":False,
                "physical_join_claimed":False,
            }
            diagnostics.append({"code":"storage_join_semantics_not_established","message":"Declared relationship exists, but published storage evidence is insufficient to establish join semantics."})

    basis["knowledge_class"] = "derived"
    basis["quality"] = status
    basis["claim_boundary"] = "storage-level join semantics only; no physical SQL/PDM join is asserted"

    evidence_ids=_unique_text([
        *(row.get("observation_id") for row in derivations),
        *(row.get("observation_id") for row in target_records),
        *(row.get("storage_observation_id") for row in storage_relationships),
    ])
    return {
        "join_kind":join_kind,"status":status,"join_readiness":readiness,
        "source_reference_expressions":source_exprs,"target_identity_expressions":target_exprs,
        "target_key_fields":target_key_fields,"structural_correspondences":correspondences,
        "candidate_count":candidate_count,"basis":basis,
        "provenance":{"relationship_occurrence_id":relationship.get("relationship_occurrence_id"),"evidence_ids":evidence_ids},
        "diagnostics":diagnostics,
    }


def build_logical_storage_mapping_knowledge_layer(
    code_declared_item: Mapping[str,Any], model_storage_item: Mapping[str,Any], output: str|Path, *, scope_id: str,
    replace: bool=True, duckdb_memory_limit: str="1GB", duckdb_threads: int=1,
) -> dict[str,Any]:
    code=resolve_knowledge_layer_input(code_declared_item,model_kind="code-declared-data-model",schema_version="code-declared-data-model/v1",source_materialization_id="code-declared-data-model")
    storage=resolve_knowledge_layer_input(model_storage_item,model_kind="model-storage-semantics",schema_version="model-storage-semantics/v1",source_materialization_id="model-storage-semantics")
    inv=_code_inventory(code.database_path)
    output_path=Path(output).expanduser().resolve(); output_path.parent.mkdir(parents=True,exist_ok=True)
    if (output_path.exists() or output_path.is_symlink()) and not replace: raise FileExistsError(output_path)
    staging=output_path.with_name(f".{output_path.name}.building-{os.getpid()}-{uuid.uuid4().hex[:12]}"); remove_path(staging); staging.mkdir(parents=True)
    started=utc_now(); build_id=stable_id("logical_storage_mapping_build",scope_id,code.input_item.get("content_fingerprint"),storage.input_item.get("content_fingerprint"),__version__)
    c=None; sconn=None; transaction_started=False
    try:
        c=connect_database(staging/LOGICAL_STORAGE_DATABASE,memory_limit=duckdb_memory_limit,threads=duckdb_threads,preserve_insertion_order=False); initialize_schema(c,LOGICAL_STORAGE_DDL)
        # Real storage adapters can publish hundreds or thousands of mapping rows.
        # Keep one explicit transaction so row-level INSERTs do not force a DuckDB
        # commit per observation; this changes execution cost, not mapping semantics.
        c.execute("BEGIN TRANSACTION"); transaction_started=True
        c.execute("INSERT INTO logical_storage_mapping_build VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?)",[build_id,scope_id,__version__,LOGICAL_STORAGE_SCHEMA_VERSION,"building",started,canonical_json({}),canonical_json({})])
        source_id=stable_id("logical_storage_mapping_source",scope_id,code.input_item.get("artifact_id"),storage.input_item.get("artifact_id"))
        c.execute("INSERT INTO logical_storage_mapping_source VALUES (?, ?, ?, ?, ?, ?, ?, ?)",[source_id,scope_id,code.input_item.get("artifact_id"),code.input_item.get("content_fingerprint"),str(code.output_path),storage.input_item.get("artifact_id"),storage.input_item.get("content_fingerprint"),str(storage.output_path)])
        sconn=connect_database(storage.database_path,read_only=True)
        record_rows=[{
            "observation_id":str(r[0]),"repo_id":str(r[1]),"storage_alias":str(r[2] or ""),
            "storage_key_field":r[3],"storage_key_expression":r[4],"payload_json":r[5],
        } for r in sconn.execute("SELECT observation_id,repo_id,storage_alias,storage_key_field,storage_key_expression,payload_json FROM model_storage_record ORDER BY observation_id").fetchall()]
        records_by_alias=defaultdict(list)
        for row in record_rows: records_by_alias[row["storage_alias"]].append(row)
        derivation_rows=[{
            "observation_id":str(r[0]),"repo_id":str(r[1]),"source_alias":str(r[2] or ""),
            "relationship_field":str(r[3] or ""),"reference_operation":r[4],"source_operation":r[5],
            "value_converter_operation":r[6],"composed_reference_value_expression":r[7],"payload_json":r[8],
        } for r in sconn.execute("SELECT observation_id,repo_id,source_alias,relationship_field,reference_operation,source_operation,value_converter_operation,composed_reference_value_expression,payload_json FROM model_storage_reference_derivation ORDER BY observation_id").fetchall()]
        derivations_by_field=defaultdict(list)
        for row in derivation_rows: derivations_by_field[(row["source_alias"],row["relationship_field"])].append(row)
        relationship_mappings_by_declared=defaultdict(list)
        relationship_mappings_by_field=defaultdict(list)
        # entity/storage-record mappings
        for record in record_rows:
            obs,storage_repo,alias,key_expr,payload=record["observation_id"],record["repo_id"],record["storage_alias"],record["storage_key_expression"],record["payload_json"]
            candidates=inv["by_fqcn"].get(alias,[]); selected=candidates[0] if len(candidates)==1 else None
            status="matched" if selected else ("ambiguous" if len(candidates)>1 else "unresolved")
            basis="exact_storage_alias_to_fqcn" if selected else "no_unique_exact_storage_alias_to_fqcn"
            c.execute("INSERT INTO logical_storage_entity_mapping VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",[
                stable_id("logical_storage_entity_mapping",source_id,obs),source_id,obs,storage_repo,alias,key_expr,
                selected.get("repo_id") if selected else None,selected.get("type_occurrence_id") if selected else None,selected.get("fqcn") if selected else None,status,basis,
                canonical_json([x["type_occurrence_id"] for x in candidates]),payload])
            if not selected: _gap(c,source_id,"storage_alias_not_uniquely_bound","storage_record",obs,"Storage alias does not resolve to exactly one code-declared FQCN.",{"storage_alias":alias,"candidate_count":len(candidates)})
        # single and collection reference rows through one generic route
        union_sql="""SELECT observation_id,repo_id,'single_reference' relation_kind,source_alias,source_field,target_alias,target_storage_key_expression storage_key_expression,payload_json FROM model_storage_reference
                     UNION ALL
                     SELECT observation_id,repo_id,'collection_reference',source_alias,relationship_field,target_alias,composed_target_key_expression,payload_json FROM model_storage_key_lineage
                     ORDER BY observation_id"""
        for r in sconn.execute(union_sql).fetchall():
            obs,storage_repo,kind,source_alias,field,target_alias,key_expr,payload=str(r[0]),str(r[1]),str(r[2]),str(r[3] or ''),str(r[4] or ''),str(r[5] or ''),r[6],r[7]
            source_candidates=inv["by_fqcn"].get(source_alias,[]); source=source_candidates[0] if len(source_candidates)==1 else None
            target_candidates=inv["by_fqcn"].get(target_alias,[]); target=target_candidates[0] if len(target_candidates)==1 else None
            field_candidates=inv["effective"].get((source["type_occurrence_id"],field),[]) if source else []; ef=field_candidates[0] if len(field_candidates)==1 else None
            declared=[]
            if source and ef: declared=inv["rels"].get((source["type_occurrence_id"],ef["field_occurrence_id"]),[])
            declared_target_ids=sorted({x["target"] for x in declared}); declared_target=declared_target_ids[0] if len(declared_target_ids)==1 else None
            declared_type=inv["types"].get(declared_target or '')
            alignment="unresolved"; knowledge_class="candidate"
            if target and declared_target:
                if target["type_occurrence_id"]==declared_target: alignment="exact_declared_target"; knowledge_class="confirmed"
                elif _is_descendant(target["type_occurrence_id"],declared_target,inv["parents"]): alignment="observed_inherited_specialization"; knowledge_class="derived"
                else: alignment="observed_target_differs_from_declared_target"; knowledge_class="candidate"
            elif target and not declared_target: alignment="observed_target_without_unique_declared_target"; knowledge_class="derived"
            complete=bool(source and ef and target)
            status="matched" if complete else ("ambiguous" if len(source_candidates)>1 or len(target_candidates)>1 or len(field_candidates)>1 else "unresolved")
            basis="exact_fqcn_plus_effective_field" if complete else "incomplete_exact_identity_binding"
            c.execute("INSERT INTO logical_storage_relationship_mapping VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",[
                stable_id("logical_storage_relationship_mapping",source_id,kind,obs),source_id,obs,storage_repo,kind,source_alias,field,target_alias,
                source.get("repo_id") if source else None,source.get("type_occurrence_id") if source else None,ef.get("effective_field_occurrence_id") if ef else None,ef.get("is_inherited") if ef else None,
                declared_target,declared_type.get("fqcn") if declared_type else None,target.get("type_occurrence_id") if target else None,target.get("fqcn") if target else None,
                alignment,knowledge_class,key_expr,status,basis,payload])
            relationship_mapping_row={
                "storage_observation_id":obs,"storage_repo_id":storage_repo,"storage_relation_kind":kind,
                "source_alias":source_alias,"source_field":field,"target_alias":target_alias,
                "source_logical_type_occurrence_id":source.get("type_occurrence_id") if source else None,
                "declared_target_type_occurrence_id":declared_target,"observed_target_type_occurrence_id":target.get("type_occurrence_id") if target else None,
                "storage_key_expression":key_expr,"mapping_status":status,"mapping_basis":basis,"payload_json":payload,
            }
            relationship_mappings_by_field[(source_alias,field)].append(relationship_mapping_row)
            if source and ef and target:
                # Bind an observed storage relationship to each compatible declared
                # relationship occurrence.  This preserves multiple semantic edges
                # from one field while still accepting an observed concrete subtype
                # for a declared abstract/base target.
                for declared_row in declared:
                    declared_target_id=declared_row.get("target")
                    if target["type_occurrence_id"]==declared_target_id or _is_descendant(target["type_occurrence_id"],declared_target_id,inv["parents"]):
                        relationship_mappings_by_declared[declared_row["relationship_occurrence_id"]].append(relationship_mapping_row)
            if not complete: _gap(c,source_id,"storage_relationship_not_fully_bound","storage_relationship",obs,"Storage relationship does not resolve to unique source type, effective field and target type.",{"source_alias":source_alias,"field":field,"target_alias":target_alias,"source_candidates":len(source_candidates),"field_candidates":len(field_candidates),"target_candidates":len(target_candidates)})
        # storage-level join semantics are useful knowledge, derived in KLC from observed
        # reference/value flow plus target storage identities. No PDM/SQL claim is made.
        for relationship in inv["relationships"]:
            source_type=inv["types"].get(relationship["source"]); target_type=inv["types"].get(relationship["target"])
            field_name=inv["fields"].get(relationship["field_occurrence_id"],"")
            if not source_type or not target_type or not field_name:
                continue
            derivations=derivations_by_field.get((source_type["fqcn"],field_name),[])
            target_records=records_by_alias.get(target_type["fqcn"],[])
            storage_relationships=list(relationship_mappings_by_declared.get(relationship["relationship_occurrence_id"],[]))
            semantic=_join_semantic_payload(
                relationship=relationship,source_type=source_type,target_type=target_type,field_name=field_name,
                derivations=derivations,target_records=target_records,storage_relationships=storage_relationships,
            )
            c.execute("INSERT INTO logical_storage_join_semantic VALUES ("+",".join("?" for _ in range(21))+")",[
                stable_id("logical_storage_join_semantic",source_id,relationship["relationship_occurrence_id"]),source_id,
                relationship["relationship_occurrence_id"],relationship["repo_id"],relationship["source"],source_type["fqcn"],
                relationship["field_occurrence_id"],field_name,relationship["target"],target_type["fqcn"],
                semantic["join_kind"],semantic["status"],semantic["join_readiness"],
                canonical_json(semantic["source_reference_expressions"]),canonical_json(semantic["target_identity_expressions"]),
                canonical_json(semantic["target_key_fields"]),canonical_json(semantic["structural_correspondences"]),semantic["candidate_count"],
                canonical_json(semantic["basis"]),canonical_json(semantic["provenance"]),canonical_json(semantic["diagnostics"]),
            ])
        sconn.close(); sconn=None
        counts=_counts(c)
        checks={
            "all_entity_rows_bound": c.execute("SELECT count(*)=0 FROM logical_storage_entity_mapping WHERE mapping_status<>'matched'").fetchone()[0],
            "all_relationship_rows_bound": c.execute("SELECT count(*)=0 FROM logical_storage_relationship_mapping WHERE mapping_status<>'matched'").fetchone()[0],
            "fuzzy_matching_used": False,
            "name_normalization_used": False,
            "physical_join_inferred": False,
            "storage_join_semantics_materialized": c.execute("SELECT count(*)>0 FROM logical_storage_join_semantic").fetchone()[0],
        }
        completed=utc_now(); c.execute("UPDATE logical_storage_mapping_build SET completed_at=?,build_status='complete',counts_json=?,checks_json=? WHERE build_id=?",[completed,canonical_json(counts),canonical_json(checks),build_id]); c.execute("COMMIT"); transaction_started=False; c.execute("CHECKPOINT"); c.close(); c=None
        repos=tuple(sorted(set(code.manifest.get("repository_ids") or ()) | set(storage.manifest.get("repository_ids") or ())))
        manifest=KnowledgeLayerManifest(scope_id=scope_id,repository_ids=repos,modes=("data-model",),producer_version=__version__,build_id=build_id,build_status="complete",counts=counts,
          materialized_marts=("logical-storage-entity-mapping","logical-storage-relationship-mapping","logical-storage-join-semantics"),capabilities=("common.logical-storage-mapping","common.logical-storage-identity","common.logical-storage-relationship","common.logical-storage-join-semantics"),
          artifacts={"database":LOGICAL_STORAGE_DATABASE,"manifest":"knowledge-layer-manifest.json"},source_evidence=(),validation_status="complete",validation=checks,
          metadata={"logical_storage_mapping_schema_version":LOGICAL_STORAGE_SCHEMA_VERSION,"started_at":started,"completed_at":completed,"code_declared_input_artifact_id":code.input_item.get("artifact_id"),"model_storage_input_artifact_id":storage.input_item.get("artifact_id")})
        write_manifest(staging/'knowledge-layer-manifest.json',manifest); publish_directory_atomic(staging,output_path,replace=replace,existing_label="knowledge-layer output"); return manifest.to_dict()
    except Exception:
        if sconn is not None: sconn.close()
        if c is not None:
            if transaction_started:
                with suppress(Exception): c.execute("ROLLBACK")
            c.close()
        remove_path(staging); raise
