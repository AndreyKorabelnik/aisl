from __future__ import annotations

from collections import defaultdict
import json
import os
from pathlib import Path
from typing import Any, Iterable, Mapping
import uuid

from .attribute_extension_context_schema import (
    ATTRIBUTE_EXTENSION_CONTEXT_DATABASE,
    ATTRIBUTE_EXTENSION_CONTEXT_DDL,
    ATTRIBUTE_EXTENSION_CONTEXT_SCHEMA_VERSION,
    ATTRIBUTE_EXTENSION_CONTEXT_TABLES,
)
from prepared_knowledge_runtime.contracts import KnowledgeLayerManifest
from prepared_knowledge_runtime.database import connect_database, initialize_schema
from prepared_knowledge_runtime.io import write_manifest
from .storage_join_correspondence import structural_reference_key_correspondences
from .logical_physical_mapping_ingestion import resolve_knowledge_layer_input
from .metrics import canonical_json, utc_now
from prepared_knowledge_runtime.normalization import stable_id
from .publication import publish_directory_atomic, remove_path
from .version import __version__


def _counts(connection: Any) -> dict[str, int]:
    return {table: int(connection.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0]) for table in ATTRIBUTE_EXTENSION_CONTEXT_TABLES}


def _json_value(value: Any, default: Any) -> Any:
    if value in (None, ""):
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value))
    except Exception:
        return default


def _unique(values: Iterable[Any]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in result:
            result.append(text)
    return result


def _rows(con: Any, sql: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
    cur = con.execute(sql, list(params))
    names = [str(item[0]) for item in cur.description]
    return [dict(zip(names, row, strict=True)) for row in cur.fetchall()]


def _source_refs(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = payload.get("source_refs") or []
    return [dict(row) for row in rows if isinstance(row, Mapping)]


def _record_properties(payload: Any) -> dict[str, Any]:
    value = _json_value(payload, {})
    if not isinstance(value, Mapping):
        return {}
    props = value.get("properties") or {}
    return dict(props) if isinstance(props, Mapping) else {}


def _physical_candidates(anchor: Mapping[str, Any]) -> list[dict[str, Any]]:
    value = anchor.get("physical_candidates") or []
    return [dict(row) for row in value if isinstance(row, Mapping)]


def _normalized_identifier(value: Any) -> str:
    return "".join(ch for ch in str(value or "").casefold() if ch.isalnum())


def _storage_reference_field_observations(derivations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in derivations:
        observation_id = str(row.get("observation_id") or "").strip()
        if observation_id and observation_id in seen:
            continue
        if observation_id:
            seen.add(observation_id)
        payload = _json_value(row.get("payload_json"), {})
        source_refs = _json_value(row.get("source_refs_json"), [])
        if not isinstance(source_refs, list):
            source_refs = []
        if not source_refs and isinstance(payload, Mapping):
            source_refs = _source_refs(payload)
        observations.append({
            "evidence_kind": "observed_storage_reference_field",
            "observation_id": observation_id or None,
            "repo_id": row.get("repo_id"),
            "api_framework": row.get("api_framework"),
            "source_owner_fqcn": row.get("source_owner_fqcn"),
            "source_operation": row.get("source_operation"),
            "source_alias": row.get("source_alias"),
            "storage_reference_field_name": row.get("relationship_field"),
            "reference_operation": row.get("reference_operation"),
            "value_converter_operation": row.get("value_converter_operation"),
            "reference_value_expression": row.get("composed_reference_value_expression"),
            "source_refs": [dict(item) for item in source_refs if isinstance(item, Mapping)],
        })
    return observations


def _annotate_sql_join_examples(
    examples: list[dict[str, Any]], *, source_field: str,
    source_anchor: Mapping[str, Any] | None, target_anchor: Mapping[str, Any] | None,
    target_key_fields: list[str], storage_field_observations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    source_relations = {
        str(item.get("sql_relation_id") or "")
        for item in (source_anchor or {}).get("observed_sql_relations") or []
        if isinstance(item, Mapping) and item.get("sql_relation_id")
    }
    target_relations = {
        str(item.get("sql_relation_id") or "")
        for item in (target_anchor or {}).get("observed_sql_relations") or []
        if isinstance(item, Mapping) and item.get("sql_relation_id")
    }
    source_usage_ids = {
        str(item.get("sql_column_usage_id") or "")
        for item in (source_anchor or {}).get("observed_field_usages") or []
        if isinstance(item, Mapping)
        and _normalized_identifier(item.get("field")) == _normalized_identifier(source_field)
        and item.get("sql_column_usage_id")
    }
    target_key_names = {_normalized_identifier(value) for value in target_key_fields if _normalized_identifier(value)}
    target_key_usage_ids = {
        str(item.get("sql_column_usage_id") or "")
        for item in (target_anchor or {}).get("observed_field_usages") or []
        if isinstance(item, Mapping)
        and _normalized_identifier(item.get("field")) in target_key_names
        and item.get("sql_column_usage_id")
    }
    source_storage_names = {
        _normalized_identifier(item.get("storage_reference_field_name"))
        for item in storage_field_observations
        if _normalized_identifier(item.get("storage_reference_field_name"))
    }
    source_candidate_names = {_normalized_identifier(source_field), *source_storage_names}
    source_candidate_names.discard("")

    rank = {
        "exact_source_field_to_target_key": 0,
        "source_field_to_target_relation": 1,
        "source_target_relation_pair": 2,
        "source_field_related": 3,
        "target_key_analog": 4,
        "target_relation_analog": 5,
        "source_relation_related": 6,
        "related_anchor": 7,
    }
    annotated: list[dict[str, Any]] = []
    for raw in examples:
        item = dict(raw)
        participants = {str(value) for value in item.get("participating_relation_ids") or [] if value}
        participants.update(str(value) for value in (item.get("left_relation_id"), item.get("right_relation_id")) if value)
        source_relation_match = bool(participants & source_relations)
        target_relation_match = bool(participants & target_relations)
        source_field_match = False
        target_key_match = False
        exact_pair_match = False
        source_field_match_basis: set[str] = set()
        target_key_match_basis: set[str] = set()
        matched_source_columns: set[str] = set()
        matched_target_columns: set[str] = set()

        for pair in item.get("column_pairs") or []:
            if not isinstance(pair, Mapping):
                continue
            sides: list[dict[str, Any]] = []
            for side in ("left", "right"):
                relation_id = str(pair.get(f"{side}_relation_id") or "")
                usage_id = str(pair.get(f"{side}_column_usage_id") or "")
                column = str(pair.get(f"{side}_column") or "")
                normalized_column = _normalized_identifier(column)
                source_by_usage = bool(usage_id and usage_id in source_usage_ids)
                source_by_storage_name = bool(
                    relation_id in source_relations and normalized_column and normalized_column in source_candidate_names
                )
                target_by_usage = bool(usage_id and usage_id in target_key_usage_ids)
                target_by_storage_key = bool(
                    relation_id in target_relations and normalized_column and normalized_column in target_key_names
                )
                if source_by_usage or source_by_storage_name:
                    source_field_match = True
                    if source_by_usage:
                        source_field_match_basis.add("logical_field_sql_usage_id")
                    if source_by_storage_name:
                        source_field_match_basis.add("source_relation_column_matches_storage_reference_field")
                    if column:
                        matched_source_columns.add(column)
                if target_by_usage or target_by_storage_key:
                    target_key_match = True
                    if target_by_usage:
                        target_key_match_basis.add("logical_key_field_sql_usage_id")
                    if target_by_storage_key:
                        target_key_match_basis.add("target_relation_column_matches_storage_key_field")
                    if column:
                        matched_target_columns.add(column)
                sides.append({"source": source_by_usage or source_by_storage_name, "target_key": target_by_usage or target_by_storage_key})
            if len(sides) == 2 and ((sides[0]["source"] and sides[1]["target_key"]) or (sides[1]["source"] and sides[0]["target_key"])):
                exact_pair_match = True

        if exact_pair_match:
            relevance = "exact_source_field_to_target_key"
        elif source_field_match and target_relation_match:
            relevance = "source_field_to_target_relation"
        elif source_relation_match and target_relation_match:
            relevance = "source_target_relation_pair"
        elif source_field_match:
            relevance = "source_field_related"
        elif target_key_match:
            relevance = "target_key_analog"
        elif target_relation_match:
            relevance = "target_relation_analog"
        elif source_relation_match:
            relevance = "source_relation_related"
        else:
            relevance = "related_anchor"

        item["relationship_relevance"] = relevance
        item["relationship_relevance_basis"] = {
            "source_field_usage_match": source_field_match,
            "target_key_usage_match": target_key_match,
            "source_relation_match": source_relation_match,
            "target_relation_match": target_relation_match,
            "exact_column_pair_match": exact_pair_match,
            "source_field_match_basis": sorted(source_field_match_basis),
            "target_key_match_basis": sorted(target_key_match_basis),
            "matched_source_columns": sorted(matched_source_columns),
            "matched_target_columns": sorted(matched_target_columns),
        }
        annotated.append(item)

    return sorted(
        annotated,
        key=lambda item: (
            rank.get(str(item.get("relationship_relevance") or ""), 99),
            str(item.get("file") or ""),
            int(item.get("line_start") or 0),
            str(item.get("sql_join_edge_id") or ""),
        ),
    )


def _anchor_json(anchor: Mapping[str, Any] | None) -> dict[str, Any]:
    if not anchor:
        return {
            "storage_aliases": [], "storage_key_fields": [], "storage_key_expressions": [],
            "observed_sql_relations": [], "observed_field_usages": [],
            "observed_sql_projections": [], "observed_sql_joins": [], "physical_candidates": [],
        }
    return {
        key: anchor.get(key) or []
        for key in (
            "storage_aliases", "storage_key_fields", "storage_key_expressions",
            "observed_sql_relations", "observed_field_usages", "observed_sql_projections",
            "observed_sql_joins", "physical_candidates",
        )
    }


def _structural_correspondences(
    derivations: list[dict[str, Any]], target_records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return structural_reference_key_correspondences(derivations, target_records)


def _classify_join(
    *, declared_target_fqcn: str, storage_relationships: list[dict[str, Any]],
    derivations: list[dict[str, Any]], target_records: list[dict[str, Any]],
    structural_correspondences: list[dict[str, Any]],
) -> tuple[str, str, str, dict[str, Any], list[dict[str, Any]]]:
    props = [_record_properties(row.get("payload_json")) for row in storage_relationships]
    operations = _unique([item.get("reference_operation") for item in props])
    relation_kinds = _unique([row.get("storage_relation_kind") for row in storage_relationships])
    concrete_targets = _unique([row.get("target_alias") for row in storage_relationships if row.get("target_alias")])
    alignments = _unique([row.get("target_alignment") for row in storage_relationships])
    diagnostics: list[dict[str, Any]] = []

    polymorphic = (
        "replacePolymorphicReferenceCollection" in operations
        or len([value for value in concrete_targets if value != declared_target_fqcn]) > 1
        or any(value == "observed_inherited_specialization" for value in alignments)
    )
    if polymorphic:
        return (
            "resolve_reference_collection", "confirmed", "unresolved_requires_subtype_or_representation",
            {
                "kind": "polymorphic_or_multi_target_reference_collection",
                "reference_operations": operations,
                "storage_relation_kinds": relation_kinds,
                "declared_target_fqcn": declared_target_fqcn,
                "observed_concrete_targets": concrete_targets,
            },
            [{
                "code": "physical_join_not_established_for_polymorphic_collection",
                "message": "Logical relationship and concrete target observations are available, but no single SQL representation is selected without subtype/representation evidence.",
            }],
        )

    collection_lineages = [
        item for item in props
        if bool(item.get("source_key_passed_into_target_key"))
        and str(item.get("composed_target_key_expression") or "").strip()
    ]
    if "collection_reference" in relation_kinds and collection_lineages:
        return (
            "derive_source_identity_from_target_key", "confirmed", "transformation_required",
            {
                "kind": "observed_parent_key_embedded_in_child_storage_key",
                "reference_operations": operations,
                "source_key_passed_into_target_key": True,
                "observation_count": len(collection_lineages),
            }, diagnostics,
        )

    if structural_correspondences:
        return (
            "resolve_reference_value_to_target_key", "confirmed", "transformation_required",
            {
                "kind": "exact_structural_reference_value_to_target_key",
                "derivation_count": len(derivations),
                "target_key_observation_count": len(target_records),
                "structural_correspondence_count": len(structural_correspondences),
            }, diagnostics,
        )

    direct_single = [item for item in storage_relationships if str(item.get("storage_relation_kind") or "") == "single_reference"]
    if direct_single:
        direct_derivations = [
            str(row.get("composed_reference_value_expression") or "").strip()
            for row in derivations
            if str(row.get("composed_reference_value_expression") or "").strip()
        ]
        return (
            "equals", "confirmed", "direct_candidate_requires_physical_representation_check",
            {
                "kind": "exact_single_reference_to_declared_target",
                "storage_observation_count": len(direct_single),
                "reference_operations": operations,
                "direct_reference_value_expressions": direct_derivations,
                "note": "Logical equality/reference semantics are separate from the physical SQL representation; observed SQL anchors must be consulted before generating a JOIN.",
            }, diagnostics,
        )

    if derivations and target_records:
        diagnostics.append({
            "code": "reference_key_structural_signature_not_confirmed",
            "message": "Reference-value derivation and target storage-key observations exist for the declared target, but no exact structural signature was established.",
        })
        return (
            "resolve_reference_value_to_target_key", "strongly_supported", "transformation_required",
            {
                "kind": "declared_target_plus_observed_reference_derivation_and_target_key",
                "derivation_count": len(derivations),
                "target_key_observation_count": len(target_records),
                "structural_correspondence_count": 0,
            }, diagnostics,
        )

    return (
        "not_established", "unresolved", "unresolved",
        {
            "kind": "insufficient_storage_or_reference_evidence",
            "storage_relationship_count": len(storage_relationships),
            "reference_derivation_count": len(derivations),
            "target_key_observation_count": len(target_records),
        },
        [{
            "code": "join_semantics_not_established",
            "message": "Declared relationship exists, but current typed storage evidence is insufficient to classify the technical join semantics.",
        }],
    )



def _usefulness_classification(
    *,
    join_method: str,
    relationship_confidence: str,
    sql_generation_status: str,
    cardinality: str,
    polymorphic: bool,
    concrete_targets: list[str],
    basis: Mapping[str, Any],
    source_object_observed_in_sql: bool,
    target_object_observed_in_sql: bool,
) -> dict[str, Any]:
    """Classify the most useful consumer claim without overwriting evidence confidence.

    ``relationship_confidence`` continues to describe the technical relationship/storage
    semantics.  This projection answers a different question: what may a consumer safely
    *do* with the currently published evidence?  It deliberately permits useful
    strongly-supported/probable guidance while keeping ambiguity and residual checks
    explicit.
    """
    exact_sql = bool(basis.get("exact_relationship_sql_join_observed"))
    source_field_sql = bool(basis.get("source_relationship_field_observed_in_sql"))
    storage_field_count = int(basis.get("source_storage_field_observation_count") or 0)
    classification_basis = {
        "relationship_confidence": relationship_confidence,
        "sql_generation_status": sql_generation_status,
        "exact_relationship_sql_join_observed": exact_sql,
        "source_relationship_field_observed_in_sql": source_field_sql,
        "source_storage_field_observation_count": storage_field_count,
        "source_object_observed_in_sql": source_object_observed_in_sql,
        "target_object_observed_in_sql": target_object_observed_in_sql,
        "cardinality": cardinality,
        "polymorphic": polymorphic,
    }

    if join_method == "not_established":
        return {
            "classification": "unresolved",
            "claim_kind": "technical_join",
            "recommended_action": "inspect_missing_storage_or_sql_evidence",
            "classification_basis": classification_basis,
            "residual_checks": ["technical_join_semantics_not_established"],
        }

    if polymorphic or join_method == "resolve_reference_collection":
        return {
            "classification": "ambiguity",
            "claim_kind": "polymorphic_collection_navigation",
            "recommended_action": "select_concrete_target_or_representation_before_sql",
            "candidate_targets": list(concrete_targets),
            "classification_basis": classification_basis,
            "residual_checks": ["select_subtype_or_physical_representation"],
            "row_multiplicity": "many",
        }

    if exact_sql:
        return {
            "classification": "confirmed",
            "claim_kind": "existing_sql_join",
            "recommended_action": "reuse_observed_sql_join",
            "classification_basis": classification_basis,
            "residual_checks": [],
            "row_multiplicity": cardinality,
        }

    if join_method == "derive_source_identity_from_target_key" and cardinality == "many":
        classification = "strongly_supported" if relationship_confidence == "confirmed" else "probable"
        residual = ["preserve_or_reduce_collection_row_multiplicity"]
        if not source_object_observed_in_sql or not target_object_observed_in_sql:
            residual.append("locate_observed_sql_representation")
        return {
            "classification": classification,
            "claim_kind": "collection_storage_navigation",
            "recommended_action": "derive_parent_identity_from_child_storage_key",
            "classification_basis": classification_basis,
            "residual_checks": residual,
            "row_multiplicity": "many",
        }

    if join_method == "resolve_reference_value_to_target_key":
        if relationship_confidence == "confirmed" and storage_field_count > 0:
            classification = "strongly_supported"
        elif relationship_confidence in {"confirmed", "strongly_supported"}:
            classification = "probable"
        else:
            classification = "unresolved"
        residual: list[str] = []
        if not source_field_sql:
            residual.append("confirm_source_sql_column_or_projection")
        if not target_object_observed_in_sql:
            residual.append("locate_target_sql_representation")
        return {
            "classification": classification,
            "claim_kind": "proposed_sql_join",
            "recommended_action": "derive_join_from_published_reference_and_key_encoding",
            "classification_basis": classification_basis,
            "residual_checks": residual,
            "row_multiplicity": cardinality,
        }

    if join_method == "equals":
        return {
            "classification": "probable" if relationship_confidence == "confirmed" else "unresolved",
            "claim_kind": "proposed_direct_reference_join",
            "recommended_action": "confirm_physical_sql_representation_before_join",
            "classification_basis": classification_basis,
            "residual_checks": ["confirm_physical_reference_representation"],
            "row_multiplicity": cardinality,
        }

    return {
        "classification": "probable" if relationship_confidence in {"confirmed", "strongly_supported"} else "unresolved",
        "claim_kind": "technical_relationship_guidance",
        "recommended_action": "use_published_evidence_with_explicit_residual_checks",
        "classification_basis": classification_basis,
        "residual_checks": ["consumer_specific_validation"],
        "row_multiplicity": cardinality,
    }


def build_attribute_extension_context_knowledge_layer(
    code_declared_item: Mapping[str, Any],
    model_storage_item: Mapping[str, Any],
    logical_storage_item: Mapping[str, Any],
    cross_artifact_item: Mapping[str, Any],
    sql_item: Mapping[str, Any],
    output: str | Path,
    *,
    scope_id: str,
    replace: bool = True,
    duckdb_memory_limit: str = "1GB",
    duckdb_threads: int = 1,
) -> dict[str, Any]:
    code = resolve_knowledge_layer_input(
        code_declared_item, model_kind="code-declared-data-model", schema_version="code-declared-data-model/v1",
        source_materialization_id="code-declared-data-model",
    )
    storage = resolve_knowledge_layer_input(
        model_storage_item, model_kind="model-storage-semantics", schema_version="model-storage-semantics/v1",
        source_materialization_id="model-storage-semantics",
    )
    logical_storage = resolve_knowledge_layer_input(
        logical_storage_item, model_kind="logical-storage-model-mapping", schema_version="logical-storage-model-mapping/v2",
        source_materialization_id="logical-storage-mapping",
    )
    cross = resolve_knowledge_layer_input(
        cross_artifact_item, model_kind="cross-artifact-data-model-mapping", schema_version="cross-artifact-data-model-mapping/v6",
        source_materialization_id="cross-artifact-data-model-mapping",
    )
    sql = resolve_knowledge_layer_input(
        sql_item, model_kind="sql-observed-data-usage", schema_version="knowledge_layer_sql/v2",
        source_materialization_id="sql-analysis",
    )

    output_path = Path(output).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if (output_path.exists() or output_path.is_symlink()) and not replace:
        raise FileExistsError(output_path)
    staging = output_path.with_name(f".{output_path.name}.building-{os.getpid()}-{uuid.uuid4().hex[:12]}")
    remove_path(staging)
    staging.mkdir(parents=True)
    started = utc_now()
    build_id = stable_id(
        "attribute_extension_context_build", scope_id,
        code.input_item.get("content_fingerprint"), storage.input_item.get("content_fingerprint"),
        logical_storage.input_item.get("content_fingerprint"), cross.input_item.get("content_fingerprint"),
        sql.input_item.get("content_fingerprint"), __version__,
    )

    out = cc = ms = ls = ca = sq = None
    try:
        out = connect_database(staging / ATTRIBUTE_EXTENSION_CONTEXT_DATABASE, memory_limit=duckdb_memory_limit, threads=duckdb_threads, preserve_insertion_order=False)
        initialize_schema(out, ATTRIBUTE_EXTENSION_CONTEXT_DDL)
        out.execute(
            "INSERT INTO attribute_extension_context_build VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?)",
            [build_id, scope_id, __version__, ATTRIBUTE_EXTENSION_CONTEXT_SCHEMA_VERSION, "building", started, canonical_json({}), canonical_json({})],
        )
        sources = (
            ("code_declared", code), ("model_storage", storage), ("logical_storage", logical_storage),
            ("cross_artifact", cross), ("sql", sql),
        )
        for role, source in sources:
            out.execute(
                "INSERT INTO attribute_extension_context_source VALUES (?, ?, ?, ?, ?, ?)",
                [stable_id("attribute_extension_context_source", scope_id, role, source.input_item.get("artifact_id")), scope_id, role,
                 source.input_item.get("artifact_id"), source.input_item.get("content_fingerprint"), str(source.output_path)],
            )

        cc = connect_database(code.database_path, read_only=True)
        ms = connect_database(storage.database_path, read_only=True)
        ls = connect_database(logical_storage.database_path, read_only=True)
        ca = connect_database(cross.database_path, read_only=True)
        sq = connect_database(sql.database_path, read_only=True)

        types = {row["type_occurrence_id"]: row for row in _rows(cc, "SELECT type_occurrence_id,repo_id,fully_qualified_name,simple_name,type_kind FROM code_declared_type")}
        records_by_alias: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in _rows(ms, "SELECT observation_id,repo_id,storage_alias,storage_key_field,storage_key_expression,source_refs_json,payload_json FROM model_storage_record ORDER BY storage_alias,observation_id"):
            records_by_alias[str(row.get("storage_alias") or "")].append(row)
        derivations_by_field: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for row in _rows(ms, "SELECT observation_id,repo_id,api_framework,source_owner_fqcn,source_operation,source_alias,relationship_field,reference_operation,value_converter_operation,composed_reference_value_expression,source_refs_json,payload_json FROM model_storage_reference_derivation ORDER BY source_alias,relationship_field,observation_id"):
            derivations_by_field[(str(row.get("source_alias") or ""), str(row.get("relationship_field") or ""))].append(row)
        storage_rels_by_field: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for row in _rows(ls, "SELECT * FROM logical_storage_relationship_mapping WHERE mapping_status='matched' ORDER BY source_alias,source_field,target_alias,storage_observation_id"):
            storage_rels_by_field[(str(row.get("source_alias") or ""), str(row.get("source_field") or ""))].append(row)

        cross_relations_by_fqcn: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in _rows(ca, "SELECT * FROM cross_artifact_storage_sql_mapping WHERE mapping_status='matched' ORDER BY logical_fully_qualified_name,sql_relation_id"):
            cross_relations_by_fqcn[str(row.get("logical_fully_qualified_name") or "")].append(row)
        field_usage_by_fqcn: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in _rows(ca, "SELECT * FROM cross_artifact_logical_field_sql_usage WHERE mapping_status='matched' ORDER BY logical_fully_qualified_name,logical_field_name,sql_query_id,sql_column_usage_id"):
            field_usage_by_fqcn[str(row.get("logical_fully_qualified_name") or "")].append(row)
        physical_by_sql_object: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in _rows(ca, "SELECT * FROM cross_artifact_sql_physical_mapping WHERE mapping_status='matched' ORDER BY sql_object_id,physical_table_code"):
            physical_by_sql_object[str(row.get("sql_object_id") or "")].append(row)

        projections_by_query: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in _rows(sq, "SELECT sql_projection_id,repo_id,query_id,file,line_start,output_name,expression,expression_kind,resolution_status,resolution_basis FROM sql_projection ORDER BY query_id,projection_ordinal"):
            projections_by_query[str(row.get("query_id") or "")].append(row)
        joins_by_query: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in _rows(sq, "SELECT sql_join_edge_id,repo_id,query_id,file,line_start,join_type,condition_kind,predicate,left_relation_id,right_relation_id,right_relation_name,participating_relation_ids_json,column_pairs_json,expression_links_json,additional_predicates_json,temporal_or_range_predicates_json,resolution_status,physical_join_confirmed FROM sql_join_edge ORDER BY query_id,join_ordinal"):
            for key in ("participating_relation_ids_json", "column_pairs_json", "expression_links_json", "additional_predicates_json", "temporal_or_range_predicates_json"):
                row[key[:-5]] = _json_value(row.pop(key), [])
            joins_by_query[str(row.get("query_id") or "")].append(row)

        anchors: dict[str, dict[str, Any]] = {}
        for type_id, type_row in sorted(types.items(), key=lambda item: str(item[1].get("fully_qualified_name") or "")):
            fqcn = str(type_row.get("fully_qualified_name") or "")
            storage_records = records_by_alias.get(fqcn, [])
            relations = cross_relations_by_fqcn.get(fqcn, [])
            usages = field_usage_by_fqcn.get(fqcn, [])
            relation_ids = {str(row.get("sql_relation_id") or "") for row in relations}
            query_ids = {str(row.get("sql_query_id") or "") for row in usages}
            sql_projections: list[dict[str, Any]] = []
            sql_joins: list[dict[str, Any]] = []
            for query_id in sorted(query_ids):
                sql_projections.extend(projections_by_query.get(query_id, [])[:40])
                for join in joins_by_query.get(query_id, []):
                    participants = set(str(x) for x in (join.get("participating_relation_ids") or []))
                    participants.update(str(x) for x in (join.get("left_relation_id"), join.get("right_relation_id")) if x)
                    if participants & relation_ids:
                        sql_joins.append(join)
            physical: list[dict[str, Any]] = []
            seen_physical: set[tuple[str, str]] = set()
            for relation in relations:
                for item in physical_by_sql_object.get(str(relation.get("sql_relation_id") or ""), []):
                    key = (str(item.get("physical_model_table_id") or ""), str(item.get("physical_table_code") or ""))
                    if key in seen_physical:
                        continue
                    seen_physical.add(key)
                    physical.append({
                        "physical_model_table_id": item.get("physical_model_table_id"),
                        "physical_table_name": item.get("physical_table_name"),
                        "physical_table_code": item.get("physical_table_code"),
                        "mapping_basis": item.get("mapping_basis"),
                        "knowledge_class": item.get("knowledge_class"),
                    })
            anchor = {
                "logical_type_occurrence_id": type_id,
                "logical_fully_qualified_name": fqcn,
                "storage_aliases": _unique([row.get("storage_alias") for row in storage_records] + [row.get("storage_alias") for row in relations]),
                "storage_key_fields": _unique(row.get("storage_key_field") for row in storage_records),
                "storage_key_expressions": _unique(row.get("storage_key_expression") for row in storage_records),
                "observed_sql_relations": [{
                    "sql_relation_id": row.get("sql_relation_id"), "repo_id": row.get("sql_repo_id"),
                    "relation_name": row.get("sql_relation_name"), "logical_name": row.get("sql_logical_name"),
                    "usage_role": row.get("sql_usage_role"), "representation_variant": row.get("representation_variant"),
                    "knowledge_class": row.get("knowledge_class"), "mapping_basis": row.get("mapping_basis"),
                } for row in relations],
                "observed_field_usages": [{
                    "field": row.get("logical_field_name"), "sql_column_usage_id": row.get("sql_column_usage_id"),
                    "sql_relation_id": row.get("sql_relation_id"), "query_id": row.get("sql_query_id"),
                    "file": row.get("sql_file"), "column": row.get("sql_column_name"), "usage_role": row.get("sql_usage_role"),
                    "knowledge_class": row.get("knowledge_class"), "mapping_basis": row.get("mapping_basis"),
                } for row in usages],
                "observed_sql_projections": sql_projections[:80],
                "observed_sql_joins": sql_joins[:80],
                "physical_candidates": physical,
            }
            anchors[fqcn] = anchor
            basis = {
                "storage_identity_observed": bool(storage_records),
                "storage_sql_correspondence_count": len(relations),
                "logical_field_sql_usage_count": len(usages),
                "sql_join_example_count": len(sql_joins),
                "physical_candidate_count": len(physical),
            }
            knowledge_class = "confirmed" if storage_records and relations else ("derived" if storage_records or relations or usages else "candidate")
            out.execute(
                "INSERT INTO attribute_extension_object_anchor VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [stable_id("attribute_extension_object_anchor", scope_id, type_id), type_id, fqcn,
                 canonical_json(anchor["storage_aliases"]), canonical_json(anchor["storage_key_fields"]), canonical_json(anchor["storage_key_expressions"]),
                 canonical_json(anchor["observed_sql_relations"]), canonical_json(anchor["observed_field_usages"]),
                 canonical_json(anchor["observed_sql_projections"]), canonical_json(anchor["observed_sql_joins"]),
                 canonical_json(anchor["physical_candidates"]), knowledge_class, canonical_json(basis),
                 canonical_json({"code_artifact_id": code.input_item.get("artifact_id"), "cross_artifact_id": cross.input_item.get("artifact_id"), "sql_artifact_id": sql.input_item.get("artifact_id")})],
            )

        relationship_rows = _rows(cc, """
            SELECT r.relationship_occurrence_id,r.repo_id,r.source_type_occurrence_id,r.target_type_occurrence_id,
                   r.field_occurrence_id,r.relationship_kind,r.resolution_status,
                   s.fully_qualified_name AS source_fqcn,t.fully_qualified_name AS target_fqcn,
                   f.name AS source_field,f.declared_type_expression
            FROM code_declared_relationship r
            JOIN code_declared_type s ON s.type_occurrence_id=r.source_type_occurrence_id
            JOIN code_declared_type t ON t.type_occurrence_id=r.target_type_occurrence_id
            JOIN code_declared_field f ON f.field_occurrence_id=r.field_occurrence_id
            WHERE r.resolution_status NOT IN ('unresolved','ambiguous')
            ORDER BY s.fully_qualified_name,f.name,t.fully_qualified_name,r.relationship_occurrence_id
        """)
        for relationship in relationship_rows:
            source_fqcn = str(relationship.get("source_fqcn") or "")
            source_field = str(relationship.get("source_field") or "")
            target_fqcn = str(relationship.get("target_fqcn") or "")
            storage_relationships = storage_rels_by_field.get((source_fqcn, source_field), [])
            derivations = derivations_by_field.get((source_fqcn, source_field), [])
            concrete_targets = _unique(row.get("target_alias") for row in storage_relationships if row.get("target_alias"))
            target_aliases = concrete_targets or [target_fqcn]
            target_records = [row for alias in target_aliases for row in records_by_alias.get(alias, [])]
            correspondences = _structural_correspondences(derivations, target_records)
            join_method, confidence, sql_status, basis, diagnostics = _classify_join(
                declared_target_fqcn=target_fqcn, storage_relationships=storage_relationships,
                derivations=derivations, target_records=target_records,
                structural_correspondences=correspondences,
            )
            relation_kinds = _unique(row.get("storage_relation_kind") for row in storage_relationships)
            operations = _unique(_record_properties(row.get("payload_json")).get("reference_operation") for row in storage_relationships)
            cardinality = "many" if ("collection_reference" in relation_kinds or any("Collection" in op for op in operations)) else "one"
            alignments = _unique(row.get("target_alignment") for row in storage_relationships)
            target_alignment = alignments[0] if len(alignments) == 1 else ("multiple_observed_targets" if alignments else "declared_only")
            polymorphic = join_method == "resolve_reference_collection" and (len(concrete_targets) > 1 or any(value == "observed_inherited_specialization" for value in alignments))
            source_refs = []
            for row in [*storage_relationships, *derivations, *target_records]:
                source_refs.extend(_source_refs(_json_value(row.get("payload_json"), {})))
            source_anchor = anchors.get(source_fqcn)
            target_anchor = anchors.get(target_fqcn)
            joined_examples: list[dict[str, Any]] = []
            seen_join_ids: set[str] = set()
            for anchor in (source_anchor, target_anchor):
                for item in (anchor or {}).get("observed_sql_joins") or []:
                    jid = str(item.get("sql_join_edge_id") or "")
                    if jid and jid not in seen_join_ids:
                        seen_join_ids.add(jid); joined_examples.append(item)
            child_key_exprs = _unique([
                _record_properties(row.get("payload_json")).get("composed_target_key_expression")
                or row.get("storage_key_expression")
                for row in storage_relationships
            ])
            source_parent_exprs = _unique(row.get("storage_key_expression") for row in records_by_alias.get(source_fqcn, []))
            target_key_fields = _unique(row.get("storage_key_field") for row in target_records)
            target_key_exprs = _unique(row.get("storage_key_expression") for row in target_records)
            reference_exprs = _unique(row.get("composed_reference_value_expression") for row in derivations)
            storage_field_observations = _storage_reference_field_observations(derivations)
            joined_examples = _annotate_sql_join_examples(
                joined_examples, source_field=source_field, source_anchor=source_anchor, target_anchor=target_anchor,
                target_key_fields=target_key_fields, storage_field_observations=storage_field_observations,
            )
            relevance_counts: dict[str, int] = defaultdict(int)
            for example in joined_examples:
                relevance_counts[str(example.get("relationship_relevance") or "related_anchor")] += 1
            source_field_observed_in_sql = any(
                bool((example.get("relationship_relevance_basis") or {}).get("source_field_usage_match"))
                for example in joined_examples
            ) or any(
                _normalized_identifier(item.get("field")) == _normalized_identifier(source_field)
                for item in (source_anchor or {}).get("observed_field_usages") or []
                if isinstance(item, Mapping)
            )
            exact_relationship_join_observed = any(
                example.get("relationship_relevance") == "exact_source_field_to_target_key" for example in joined_examples
            )
            basis = {
                **basis,
                "source_storage_field_observation_count": len(storage_field_observations),
                "source_storage_field_observations": storage_field_observations,
                "source_relationship_field_observed_in_sql": source_field_observed_in_sql,
                "exact_relationship_sql_join_observed": exact_relationship_join_observed,
                "sql_join_example_relevance_counts": dict(sorted(relevance_counts.items())),
            }
            basis["usefulness"] = _usefulness_classification(
                join_method=join_method,
                relationship_confidence=confidence,
                sql_generation_status=sql_status,
                cardinality=cardinality,
                polymorphic=polymorphic,
                concrete_targets=concrete_targets,
                basis=basis,
                source_object_observed_in_sql=bool((source_anchor or {}).get("observed_sql_relations")),
                target_object_observed_in_sql=bool((target_anchor or {}).get("observed_sql_relations")),
            )
            physical = []
            seen_p: set[tuple[str, str]] = set()
            for item in [*_physical_candidates(source_anchor or {}), *_physical_candidates(target_anchor or {})]:
                key = (str(item.get("physical_model_table_id") or ""), str(item.get("physical_table_code") or ""))
                if key not in seen_p:
                    seen_p.add(key); physical.append(item)
            diagnostic_payload = list(diagnostics)
            if not (source_anchor or {}).get("observed_sql_relations"):
                diagnostic_payload.append({"code": "source_object_not_observed_in_sql", "message": "No SQL relation is currently mapped to the relationship source object."})
            if not (target_anchor or {}).get("observed_sql_relations"):
                diagnostic_payload.append({"code": "target_object_not_observed_in_sql", "message": "No SQL relation is currently mapped to the declared target object."})
            if storage_field_observations and not source_field_observed_in_sql:
                diagnostic_payload.append({
                    "code": "storage_reference_field_not_observed_in_current_sql",
                    "message": "Typed storage evidence observes the relationship reference field, but current SQL evidence does not observe that source relationship field on a mapped source relation. Treat it as a source-extraction candidate, not as a confirmed existing SQL column usage.",
                    "storage_reference_field_names": _unique(
                        item.get("storage_reference_field_name") for item in storage_field_observations
                    ),
                })
            if joined_examples and not exact_relationship_join_observed:
                diagnostic_payload.append({
                    "code": "observed_sql_join_examples_are_related_analogs",
                    "message": "Observed SQL JOIN examples are relevant to the source/target anchors or storage key pattern, but no example directly joins the selected source relationship field to the target storage key. Use labeled analogs as supporting evidence, not as proof of an existing exact JOIN.",
                    "relevance_counts": dict(sorted(relevance_counts.items())),
                })
            join_semantic_id = stable_id("attribute_extension_join_semantic", scope_id, relationship.get("relationship_occurrence_id"))
            out.execute(
                "INSERT INTO attribute_extension_join_semantic VALUES (" + ",".join("?" for _ in range(30)) + ")",
                [join_semantic_id, relationship.get("repo_id"), relationship.get("source_type_occurrence_id"), source_fqcn,
                 relationship.get("field_occurrence_id"), source_field, relationship.get("declared_type_expression"),
                 relationship.get("target_type_occurrence_id"), target_fqcn, relationship.get("relationship_kind"), cardinality,
                 target_alignment, polymorphic, canonical_json(concrete_targets), join_method, confidence, sql_status,
                 canonical_json(reference_exprs), canonical_json(target_key_fields), canonical_json(target_key_exprs),
                 canonical_json(source_parent_exprs), canonical_json(child_key_exprs), canonical_json(correspondences),
                 canonical_json(_anchor_json(source_anchor)), canonical_json(_anchor_json(target_anchor)),
                 canonical_json(joined_examples[:100]), canonical_json(physical), canonical_json(basis),
                 canonical_json({"code_relationship_id": relationship.get("relationship_occurrence_id"), "source_refs": source_refs}),
                 canonical_json(diagnostic_payload)],
            )
            if join_method == "not_established":
                out.execute(
                    "INSERT INTO attribute_extension_context_gap VALUES (?, ?, ?, ?, ?, ?, ?)",
                    [stable_id("attribute_extension_context_gap", join_semantic_id, "join_semantics_not_established"),
                     "join_semantics_not_established", "warning", "join_semantic", join_semantic_id,
                     "Declared relationship has no actionable technical join semantics in current evidence.", canonical_json(basis)],
                )
            if join_method == "resolve_reference_collection":
                out.execute(
                    "INSERT INTO attribute_extension_context_gap VALUES (?, ?, ?, ?, ?, ?, ?)",
                    [stable_id("attribute_extension_context_gap", join_semantic_id, "polymorphic_collection_sql_unresolved"),
                     "polymorphic_collection_sql_unresolved", "info", "join_semantic", join_semantic_id,
                     "Polymorphic/reference collection remains unresolved for SQL until subtype and physical representation evidence is sufficient.",
                     canonical_json({"concrete_targets": concrete_targets, "target_alignment": target_alignment})],
                )

        counts = _counts(out)
        checks = {
            "join_semantics_exist": counts["attribute_extension_join_semantic"] > 0,
            "unsafe_direct_physical_join_inference_used": False,
            "fuzzy_identity_matching_used": False,
            "generated_sql_emitted": False,
            "unknown_join_method_count": int(out.execute("SELECT count(*) FROM attribute_extension_join_semantic WHERE join_method NOT IN ('equals','derive_source_identity_from_target_key','resolve_reference_value_to_target_key','resolve_reference_collection','not_established')").fetchone()[0]),
        }
        completed = utc_now()
        out.execute(
            "UPDATE attribute_extension_context_build SET completed_at=?,build_status='complete',counts_json=?,checks_json=? WHERE build_id=?",
            [completed, canonical_json(counts), canonical_json(checks), build_id],
        )
        out.execute("CHECKPOINT")
        out.close(); out = None
        for con in (cc, ms, ls, ca, sq):
            con.close()
        cc = ms = ls = ca = sq = None

        repos = tuple(sorted(set(code.manifest.get("repository_ids") or ()) | set(storage.manifest.get("repository_ids") or ()) | set(sql.manifest.get("repository_ids") or ())))
        manifest = KnowledgeLayerManifest(
            scope_id=scope_id, repository_ids=repos, modes=("data-model", "sql"), producer_version=__version__,
            build_id=build_id, build_status="complete", counts=counts,
            materialized_marts=("data-model-attribute-object-anchor", "data-model-attribute-join-semantics", "data-model-attribute-extension-gap"),
            capabilities=("common.data-model-attribute-extension-context", "common.data-model-agent-join-semantics", "common.data-model-sql-anchor-context"),
            artifacts={"database": ATTRIBUTE_EXTENSION_CONTEXT_DATABASE, "manifest": "knowledge-layer-manifest.json"},
            source_evidence=(), validation_status="complete", validation=checks,
            metadata={
                "model_schema_version": ATTRIBUTE_EXTENSION_CONTEXT_SCHEMA_VERSION, "started_at": started, "completed_at": completed,
                "code_declared_input_artifact_id": code.input_item.get("artifact_id"),
                "model_storage_input_artifact_id": storage.input_item.get("artifact_id"),
                "logical_storage_input_artifact_id": logical_storage.input_item.get("artifact_id"),
                "cross_artifact_input_artifact_id": cross.input_item.get("artifact_id"),
                "sql_input_artifact_id": sql.input_item.get("artifact_id"),
            },
        )
        write_manifest(staging / "knowledge-layer-manifest.json", manifest)
        publish_directory_atomic(staging, output_path, replace=replace, existing_label="knowledge-layer output")
        return manifest.to_dict()
    except Exception:
        for con in (sq, ca, ls, ms, cc, out):
            if con is not None:
                try:
                    con.close()
                except Exception:
                    pass
        remove_path(staging)
        raise
