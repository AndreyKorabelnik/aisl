from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from code_analyzer_core import __version__ as CORE_VERSION
from code_analyzer_core.models import AnalysisResult, Fact, InterfaceInfo, RelationInfo
from code_analyzer_core.utils import write_json

ARTIFACT_ID = "reference_data_fact_base"
SCHEMA_VERSION = "reference-data-fact-base/v2"
SAMPLE_LIMIT = 80




def _source_set_from_path(value: Any) -> str:
    norm = "/" + str(value or "").replace("\\", "/").strip("/").lower() + "/"
    if any(token in norm for token in ("/src/test/", "/tests/", "/test/")):
        return "test"
    if any(token in norm for token in ("/db/migration/", "/migrations/", "/migration/", "/liquibase/", "/flyway/")):
        return "migration"
    if any(token in norm for token in ("/fixture/", "/fixtures/")):
        return "fixture"
    if any(token in norm for token in ("/example/", "/examples/", "/sample/", "/samples/")):
        return "example_sample"
    if any(token in norm for token in ("/generated/", "/target/generated/", "/build/generated/")):
        return "generated"
    if any(token in norm for token in ("/docs/", "/documentation/")):
        return "documentation"
    if "/src/main/" in norm:
        return "production"
    return "unknown"


def _observed_source_set(properties: dict[str, Any], evidence: list[dict[str, Any]]) -> str:
    explicit = str(properties.get("source_set") or "").strip().lower()
    if explicit in {"production", "test", "migration", "fixture", "example_sample", "generated", "documentation", "unknown"}:
        return explicit
    if explicit == "main":
        return "production"
    for key in ("file", "file_path", "source_file", "absolute_file"):
        if properties.get(key):
            return _source_set_from_path(properties.get(key))
    for ref in evidence:
        if isinstance(ref, dict):
            value = ref.get("file_path") or ref.get("file")
            if value:
                return _source_set_from_path(value)
    return "unknown"

def _stable_id(prefix: str, *parts: Any) -> str:
    raw = "|".join(str(part or "").replace("\\", "/").strip().lower() for part in parts)
    digest = hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def _evidence(item: Any) -> list[dict[str, Any]]:
    refs = getattr(item, "evidence", None) or []
    return [ref.model_dump(mode="json") for ref in refs]


def _fact_id(fact: Fact) -> str:
    props = fact.properties or {}
    preferred = (
        "declared_value_set_id",
        "declared_value_id",
        "literal_data_write_id",
        "db_schema_table_id",
        "db_schema_column_id",
        "db_schema_key_id",
        "db_schema_relationship_id",
        "db_schema_index_id",
        "db_schema_constraint_id",
        "db_schema_sequence_id",
        "db_schema_trigger_id",
        "storage_access_id",
        "persistent_write_id",
        "read_from_storage_id",
        "source_to_storage_lineage_id",
        "storage_to_access_lineage_id",
        "data_source_id",
        "ingress_id",
        "access_boundary_id",
        "external_dependency_id",
        "scheduled_job_id",
        "storage_lineage_gap_id",
        "data_model_lineage_gap_id",
    )
    for key in preferred:
        value = props.get(key)
        if value:
            return str(value)
    for key, value in props.items():
        if key.endswith("_id") and value:
            return str(value)
    first_ref = _evidence(fact)[:1]
    return _stable_id("fact", fact.fact_type, fact.name, first_ref)


def _fact_item(fact: Fact) -> dict[str, Any]:
    evidence = _evidence(fact)
    properties = dict(fact.properties or {})
    properties.setdefault("source_set", _observed_source_set(properties, evidence))
    return {
        "fact_id": _fact_id(fact),
        "fact_type": fact.fact_type,
        "name": fact.name,
        "properties": properties,
        "evidence": evidence,
    }


def _interface_item(interface: InterfaceInfo) -> dict[str, Any]:
    direction = interface.direction.value if hasattr(interface.direction, "value") else str(interface.direction)
    kind = interface.kind.value if hasattr(interface.kind, "value") else str(interface.kind)
    props = interface.properties or {}
    interface_id = str(props.get("interface_id") or props.get("operation_id") or _stable_id(
        "interface",
        kind,
        direction,
        interface.name,
        interface.operation,
        interface.path,
        interface.method,
    ))
    evidence = _evidence(interface)
    properties = {
        "direction": direction,
        "kind": kind,
        "schema_ref": interface.schema_ref,
        "operation": interface.operation,
        "path": interface.path,
        "method": interface.method,
        **props,
    }
    properties.setdefault("source_set", _observed_source_set(properties, evidence))
    return {
        "fact_id": interface_id,
        "fact_type": "interface_observation",
        "name": interface.name,
        "properties": properties,
        "evidence": evidence,
    }


def _relation_item(relation: RelationInfo) -> dict[str, Any]:
    props = relation.properties or {}
    relation_id = str(props.get("relation_id") or props.get("operation_link_id") or _stable_id(
        "relation",
        relation.source,
        relation.target,
        relation.relation_type,
    ))
    evidence = _evidence(relation)
    properties = {
        "source": relation.source,
        "target": relation.target,
        "relation_type": relation.relation_type,
        **props,
    }
    properties.setdefault("source_set", _observed_source_set(properties, evidence))
    return {
        "fact_id": relation_id,
        "fact_type": "relation_observation",
        "name": relation.relation_type,
        "properties": properties,
        "evidence": evidence,
    }


def _jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    digest = hashlib.sha256()
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            line = json.dumps(row, ensure_ascii=False, default=str, separators=(",", ":")) + "\n"
            fh.write(line)
            digest.update(line.encode("utf-8"))
            count += 1
    return {
        "relative_path": path.as_posix(),
        "records_count": count,
        "bytes": path.stat().st_size if path.exists() else 0,
        "sha256": digest.hexdigest(),
        "format": "jsonl",
    }


def _matches(fact: Fact, fact_types: set[str], prefixes: tuple[str, ...] = ()) -> bool:
    return fact.fact_type in fact_types or any(fact.fact_type.startswith(prefix) for prefix in prefixes)


def _select(result: AnalysisResult, fact_types: set[str], prefixes: tuple[str, ...] = ()) -> list[dict[str, Any]]:
    return [_fact_item(fact) for fact in result.facts if _matches(fact, fact_types, prefixes)]


def _coverage(result: AnalysisResult) -> dict[str, Any]:
    coverage = result.coverage or {}
    keys = (
        "declared_value_scan",
        "declared_value_set_summary",
        "db_schema",
        "java_traceability",
        "java_persistence_lineage",
        "java_data_model_lineage",
        "openapi",
        "sql",
        "normalized_facts",
        "low_level_facts",
        "heavy_tools",
        "evidence_coverage",
    )
    return {key: coverage.get(key) for key in keys if key in coverage}


def _relation_is_direct_observation(relation: RelationInfo) -> bool:
    props = relation.properties or {}
    text = " ".join(str(value or "") for value in (
        relation.relation_type,
        props.get("evidence_type"),
        props.get("relation_kind"),
        props.get("derivation_kind"),
    )).lower()
    if any(token in text for token in ("candidate", "inferred", "name_match", "name_based")):
        return False
    return bool(_evidence(relation) or props.get("declared") or props.get("source_fact_id"))


def build_reference_data_fact_base(*, result: AnalysisResult, out_dir: Path) -> dict[str, Any]:
    """Build a deterministic facts-only payload for reference-data-evidence/v1 publication.

    The artifact does not identify candidates, owners, reference-data classes or
    population semantics. It only groups already observed analyzer facts so that
    the LLM can perform the semantic assessment.
    """

    compact_dir = out_dir / "compact"
    detail_dir = compact_dir / ARTIFACT_ID

    declared_value_sets = _select(result, {"declared_value_set"})
    declared_value_set_summaries = _select(result, {"declared_value_set_summary"})
    declared_values = _select(result, {"declared_value"})
    literal_data_writes = _select(result, {"literal_data_write"})

    physical_assets = _select(result, {"db_schema_table"})
    physical_attributes = _select(result, {"db_schema_column"})
    physical_constraints = _select(
        result,
        {
            "db_schema_key",
            "db_schema_relationship",
            "db_schema_index",
            "db_schema_constraint",
            "db_schema_sequence",
            "db_schema_partitioning",
            "db_schema_trigger",
            "jpa_entity",
            "jpa_relationship",
            "jpa_inheritance",
        },
    )

    storage_operations = _select(
        result,
        {
            "storage_access",
            "sql_access",
            "persistent_write",
            "read_from_storage",
            "storage_to_access_lineage",
            "stored_field_to_response_field_mapping",
        },
        prefixes=("sql_insert", "sql_update", "sql_delete", "sql_merge", "sql_select"),
    )
    join_observations = _select(result, {"sql_join_observation"})
    source_to_storage_lineage = _select(
        result,
        {
            "data_source",
            "source_to_storage_lineage",
            "field_lineage",
            "attribute_mapping",
            "attribute_derivation",
            "data_trace",
        },
    )
    ingress_and_jobs = (
        [_interface_item(item) for item in result.interfaces]
        + _select(
            result,
            {
                "system_ingress",
                "rest_operation",
                "kafka_consumer",
                "scheduled_job",
                "access_boundary",
                "startup_loader",
                "batch_job",
                "file_import",
            },
        )
    )
    external_dependencies = _select(
        result,
        {
            "external_dependency",
            "external_dependency_call",
            "http_outbound_call",
            "kafka_consumer",
            "file_import",
            "jdbc_external_read",
        },
    )
    observed_relations = [_relation_item(item) for item in result.relations if _relation_is_direct_observation(item)]
    unresolved_gaps = _select(
        result,
        {
            "storage_lineage_gap",
            "data_model_lineage_gap",
            "source_inspection_request",
            "call_chain_diagnostic",
        },
    )
    configuration_facts = [_fact_item(fact) for fact in result.config_facts]

    groups: dict[str, list[dict[str, Any]]] = {
        "physical_assets": physical_assets,
        "physical_attributes": physical_attributes,
        "physical_constraints": physical_constraints,
        "declared_value_sets": declared_value_sets,
        "declared_value_set_summaries": declared_value_set_summaries,
        "declared_values": declared_values,
        "literal_data_writes": literal_data_writes,
        "storage_operations": storage_operations,
        "join_observations": join_observations,
        "source_to_storage_lineage": source_to_storage_lineage,
        "ingress_and_jobs": ingress_and_jobs,
        "external_dependencies": external_dependencies,
        "observed_relations": observed_relations,
        "configuration_facts": configuration_facts,
        "unresolved_gaps": unresolved_gaps,
    }

    section_index: dict[str, Any] = {}
    total_bytes = 0
    total_records = 0
    for section_name, rows in groups.items():
        meta = _jsonl(detail_dir / f"{section_name}.jsonl", rows)
        meta["relative_path"] = f"{ARTIFACT_ID}/{section_name}.jsonl"
        section_index[section_name] = meta
        total_bytes += int(meta.get("bytes") or 0)
        total_records += int(meta.get("records_count") or 0)

    source_sets = Counter(
        str((item.get("properties") or {}).get("source_set") or "unknown")
        for item in declared_value_sets
    )
    syntax_kinds = Counter(
        str((item.get("properties") or {}).get("syntax_kind") or "unknown")
        for item in declared_value_sets
    )
    truncation_count = sum(
        1
        for item in declared_value_sets
        if bool((item.get("properties") or {}).get("extraction_truncated"))
    )
    all_source_sets = Counter(
        str((item.get("properties") or {}).get("source_set") or "unknown")
        for rows in groups.values()
        for item in rows
    )

    summary = {
        **{section_name: len(rows) for section_name, rows in groups.items()},
        "declared_value_sets_by_source_set": dict(sorted(source_sets.items())),
        "all_facts_by_source_set": dict(sorted(all_source_sets.items())),
        "by_syntax_kind": dict(sorted(syntax_kinds.items())),
        "truncated_declared_value_sets": truncation_count,
        "detail_records_count": total_records,
        "detail_bytes": total_bytes,
    }

    artifact = {
        "schema_version": SCHEMA_VERSION,
        "artifact_id": ARTIFACT_ID,
        "artifact_kind": "task_oriented_facts_only_llm_input",
        "producer": {
            "name": "code-analyzer-core",
            "version": CORE_VERSION,
        },
        "semantic_policy": {
            "analyzer_classifies_nsi_or_reference_data": False,
            "analyzer_forms_nsi_candidates": False,
            "analyzer_determines_owner": False,
            "analyzer_determines_population_source": False,
            "syntax_kind_is_not_business_classification": True,
            "absence_is_interpretable_only_with_coverage": True,
        },
        "negative_observation_policy": {
            "allowed_wording": "In the analyzed files and supported constructs, no additional path was detected.",
            "prohibited_inference": "Absence of an observed path does not prove that the path does not exist outside the analyzed scope or unsupported constructs.",
        },
        "summary": summary,
        "coverage": _coverage(result),
        "known_limitations": [
            "Only files and constructs processed by enabled analyzer stages are represented.",
            "Dynamic SQL, reflection, runtime-generated values and external artifacts can remain unresolved.",
            "A declared value set is linked to a physical table only when an explicit table target is present in analyzer facts; name similarity is not used.",
            "Samples are bounded. Use section_index/detail JSONL or evidence access API for full materialized facts.",
        ],
        "samples": {
            section_name: rows[:SAMPLE_LIMIT]
            for section_name, rows in groups.items()
            if section_name != "declared_values"
        },
        "section_index": section_index,
    }
    artifact_path = compact_dir / f"{ARTIFACT_ID}.json"
    write_json(artifact_path, artifact)

    manifest = {
        "artifact_id": ARTIFACT_ID,
        "schema_version": SCHEMA_VERSION,
        "producer": "code-analyzer-core",
        "producer_version": CORE_VERSION,
        "llm_generated": False,
        "contains_business_classification": False,
        "contains_nsi_classification": False,
        "contains_nsi_candidates": False,
        "output_path": f"compact/{ARTIFACT_ID}.json",
        "detail_dir": f"compact/{ARTIFACT_ID}",
        "section_index": section_index,
        "summary": summary,
    }
    write_json(compact_dir / f"{ARTIFACT_ID}_manifest.json", manifest)

    return {
        "requested": True,
        "status": "success",
        "artifact_path": str(artifact_path),
        "manifest_path": str(compact_dir / f"{ARTIFACT_ID}_manifest.json"),
        "summary": summary,
        "semantic_classification_performed": False,
    }
