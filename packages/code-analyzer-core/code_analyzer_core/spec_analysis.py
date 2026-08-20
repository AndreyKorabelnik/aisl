from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any
import hashlib
import json

import yaml

from code_analyzer_core import __version__ as CORE_VERSION
from code_analyzer_core.utils import normalize_name, write_json
from code_analyzer_core.repository_contract import (
    now_utc,
    repo_id_from_path,
    safe_run_id,
    write_repository_analysis_manifest,
    repository_analysis_root_for_static_output,
)
from code_analyzer_core.pipeline import ANALYSIS_CONTRACT_VERSION, EVIDENCE_TOOL_CONTRACT_VERSION

SPEC_ANALYSIS_PROFILE_ID = "spec-evidence-workspace"
SPEC_WORKSPACE_CONTRACT_TYPE = "java"  # compatibility contract used by existing evidence tools API catalog


def _stable_id(prefix: str, *parts: Any) -> str:
    raw = "|".join(str(p or "").strip().lower() for p in parts if p is not None)
    if not raw:
        raw = prefix.lower()
    return f"{prefix}_{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:10]}"


def _read_yaml_mapping(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8", errors="ignore")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Expected YAML mapping in {path}")
    return data


def _read_json_mapping(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="ignore")) or {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _as_list(value: Any) -> list[dict[str, Any]]:
    return [x for x in (value or []) if isinstance(x, dict)] if isinstance(value, list) else []


def _evidence_refs(item: dict[str, Any]) -> list[str]:
    refs: list[str] = []
    for key in ("evidence_refs", "source_evidence_refs", "related_evidence_refs"):
        value = item.get(key)
        if isinstance(value, list):
            refs.extend(str(x) for x in value if x)
        elif isinstance(value, str) and value:
            refs.append(value)
    if item.get("id"):
        refs.insert(0, str(item.get("id")))
    seen: set[str] = set()
    out: list[str] = []
    for ref in refs:
        if ref in seen:
            continue
        seen.add(ref)
        out.append(ref)
    return out


def _spec_evidence(ref: str | None = None, *, artifact: str = "data-evidence.yaml", item: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    refs = [ref] if ref else []
    if item:
        refs.extend(_evidence_refs(item))
    refs = [x for x in refs if x]
    return [{
        "file": artifact,
        "extractor": "spec_static_analyzer",
        "evidence_refs": refs,
        "source_type": "spec_artifacts",
    }]


def _status_to_evidence_level(status: Any) -> str:
    text = str(status or "").lower()
    if text in {"derived_by_static_analysis", "observed_in_code", "observed_in_schema", "confirmed", "confirmed_by_analyzer"}:
        return "confirmed_by_analyzer"
    if text.startswith("candidate"):
        return "candidate_signal_navigation_only"
    if text in {"not_observed", "not_applicable"}:
        return "not_applicable"
    return "unresolved"


def _artifact_manifest_path(spec_artifacts: Path) -> Path | None:
    for p in [spec_artifacts / "artifacts_manifest.json", spec_artifacts.parent / "artifacts_manifest.json"]:
        if p.exists() and p.is_file():
            return p
    return None


def _discover_support_artifacts(spec_artifacts: Path) -> list[dict[str, Any]]:
    candidates: list[Path] = []
    for name in ["proposal.md", "design.md", "tasks.md", "owner_review_checklist.md", "known_limitations.md", "report.md"]:
        p = spec_artifacts / name
        if p.exists() and p.is_file():
            candidates.append(p)
    specs_dir = spec_artifacts / "specs"
    if specs_dir.exists():
        candidates.extend(sorted(specs_dir.rglob("spec.md")))
    out: list[dict[str, Any]] = []
    for p in sorted(candidates):
        rel = str(p.relative_to(spec_artifacts)).replace("\\", "/")
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            text = ""
        out.append({
            "artifact_id": _stable_id("spec_artifact", rel),
            "relative_path": rel,
            "content_type": "text/markdown" if p.suffix.lower() == ".md" else "text/plain",
            "role": "spec_support_artifact",
            "chars": len(text),
            "sha1": hashlib.sha1(text.encode("utf-8", errors="ignore")).hexdigest(),
        })
    return out


def _build_navigation(data: dict[str, Any]) -> dict[str, Any]:
    interfaces = []
    operations = []
    schemas = []

    for idx, iface in enumerate(_as_list(data.get("interfaces")), start=1):
        iid = str(iface.get("id") or iface.get("suggested_id") or _stable_id("interface", idx, iface.get("endpoint_or_resource")))
        op = str(iface.get("operation") or iid)
        schema_ref = iface.get("payload_schema_ref")
        interfaces.append({
            "id": iid,
            "name": iface.get("endpoint_or_resource") or iface.get("topic_or_channel") or op or iid,
            "kind": iface.get("kind") or "spec_interface",
            "direction": iface.get("direction") or "unknown",
            "operation": op,
            "path": iface.get("endpoint_or_resource") or iface.get("topic_or_channel"),
            "schema_ref": schema_ref,
            "description": iface.get("description"),
            "source_type": "spec_artifacts",
            "evidence_refs": _evidence_refs(iface),
        })
        operations.append({
            "id": iface.get("operation_id") or _stable_id("operation", iid, op),
            "operation": op,
            "interfaces": [iid],
            "interface_names": [interfaces[-1]["name"]],
            "schemas": [schema_ref] if schema_ref else [],
            "source_type": "spec_artifacts",
        })

    for payload in _as_list(data.get("payload_schemas")):
        name = payload.get("java_class_name") or payload.get("technical_name") or payload.get("name") or payload.get("id")
        fields = []
        for f in _as_list(payload.get("fields")):
            fields.append({
                "name": f.get("name") or f.get("technical_name"),
                "type": f.get("java_type") or f.get("type") or f.get("sql_type") or "unknown",
                "source_type": "spec_artifacts",
                "evidence_refs": _evidence_refs(f),
            })
        schemas.append({
            "id": payload.get("id") or _stable_id("schema", name),
            "name": name,
            "kind": payload.get("schema_kind") or "spec_payload_schema",
            "fields": fields,
            "source_type": "spec_artifacts",
            "evidence_refs": _evidence_refs(payload),
        })

    return {
        "artifact": "navigation",
        "source_type": "spec_artifacts",
        "counts": {"interfaces": len(interfaces), "operations": len(operations), "schemas": len(schemas)},
        "interfaces": interfaces,
        "operations": operations,
        "schemas": schemas,
        "declared_value_sets": [],
    }


def _build_facts(data: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    facts: dict[str, list[dict[str, Any]]] = {}

    def add(ftype: str, item: dict[str, Any]) -> None:
        facts.setdefault(ftype, []).append(item)

    # Payload schemas and attributes -> attribute_occurrence.
    for payload in _as_list(data.get("payload_schemas")):
        container = payload.get("java_class_name") or payload.get("technical_name") or payload.get("name") or payload.get("id")
        for f in _as_list(payload.get("fields")):
            name = f.get("name") or f.get("technical_name")
            if not name:
                continue
            fid = f.get("id") or _stable_id("attribute_occurrence", container, name)
            add("attribute_occurrence", {
                "attribute_occurrence_id": fid,
                "container_kind": "spec_payload_schema",
                "container_name": container,
                "attribute_name": name,
                "attribute_type": f.get("java_type") or f.get("type") or "unknown",
                "attribute_role": "payload_field",
                "evidence_level": _status_to_evidence_level(f.get("evidence_status")),
                "source_type": "spec_artifacts",
                "evidence": _spec_evidence(fid, item=f),
            })

    # Storage structures and attributes.
    attrs_by_storage: dict[str, list[dict[str, Any]]] = {}
    for attr in _as_list(data.get("storage_attributes")):
        sid = str(attr.get("storage_ref") or attr.get("storage_id") or "")
        attrs_by_storage.setdefault(sid, []).append(attr)
        name = attr.get("physical_name") or attr.get("technical_name") or attr.get("name")
        if name:
            aid = attr.get("id") or _stable_id("storage_attr", sid, name)
            add("attribute_occurrence", {
                "attribute_occurrence_id": aid,
                "container_kind": "storage_target",
                "container_name": attr.get("table_name") or sid,
                "storage_target": attr.get("table_name") or sid,
                "attribute_name": name,
                "attribute_type": attr.get("sql_type") or attr.get("java_type") or "unknown",
                "attribute_role": "storage_column",
                "evidence_level": _status_to_evidence_level(attr.get("evidence_status")),
                "source_type": "spec_artifacts",
                "evidence": _spec_evidence(aid, item=attr),
            })

    for storage in _as_list(data.get("storages")):
        sid = str(storage.get("id") or storage.get("suggested_id") or _stable_id("storage", storage.get("physical_name")))
        tname = storage.get("physical_name") or storage.get("table_name") or sid
        fields = []
        for attr in attrs_by_storage.get(sid, []):
            fields.append({
                "db_column_name": attr.get("physical_name") or attr.get("technical_name") or attr.get("name"),
                "attribute_name": attr.get("physical_name") or attr.get("technical_name") or attr.get("name"),
                "attribute_type": attr.get("sql_type") or attr.get("java_type") or "unknown",
                "nullable": attr.get("nullable"),
                "description": attr.get("comment") or attr.get("description"),
                "constraints": attr.get("constraints") or [],
            })
        add("persistent_structure", {
            "persistent_structure_id": sid,
            "storage_kind": "database" if str(storage.get("storage_kind") or "").lower() in {"database", "physical_table", "storage_target"} else storage.get("storage_kind") or "storage_target",
            "container_kind": "storage_target",
            "container_name": tname,
            "storage_target": tname,
            "schema_name": storage.get("schema_name"),
            "fields": fields,
            "evidence_level": _status_to_evidence_level(storage.get("evidence_status")),
            "source_type": "spec_artifacts",
            "evidence": _spec_evidence(sid, item=storage),
        })

    # Interfaces -> ingress/access boundary facts.
    for iface in _as_list(data.get("interfaces")):
        iid = str(iface.get("id") or iface.get("suggested_id") or _stable_id("iface", iface.get("operation")))
        direction = str(iface.get("direction") or "").lower()
        kind = str(iface.get("kind") or "spec_interface")
        endpoint = iface.get("endpoint_or_resource") or iface.get("topic_or_channel")
        common = {
            "operation": iface.get("operation"),
            "operation_id": iface.get("operation_id"),
            "endpoint_or_topic": endpoint,
            "payload_type": iface.get("payload_schema_ref"),
            "evidence_level": _status_to_evidence_level(iface.get("evidence_status")),
            "source_type": "spec_artifacts",
            "evidence": _spec_evidence(iid, item=iface),
        }
        if direction == "inbound":
            add("system_ingress", {"ingress_id": iid, "origin_kind": kind, "source_payload": iface.get("payload_schema_ref"), **common})
        elif direction == "outbound":
            add("access_boundary", {"access_boundary_id": iid, "boundary_kind": kind, "response_or_payload_type": iface.get("payload_schema_ref"), **common})

    # Transformations -> mappings/derivations.
    for tr in _as_list(data.get("transformations")):
        tid = str(tr.get("id") or tr.get("transformation_id") or _stable_id("transformation", tr))
        base = {
            "source_container": tr.get("source_object"),
            "source_field": tr.get("source_attribute"),
            "target_container": tr.get("target_object"),
            "target_field": tr.get("target_attribute"),
            "expression": tr.get("expression"),
            "mapping_kind": tr.get("transformation_kind") or tr.get("mapping_type") or "spec_transformation",
            "evidence_level": _status_to_evidence_level(tr.get("status") or tr.get("evidence_status")),
            "source_type": "spec_artifacts",
            "evidence": _spec_evidence(tid, item=tr),
        }
        add("attribute_mapping", {"attribute_mapping_id": tid, **base})
        if tr.get("expression"):
            add("attribute_derivation", {"attribute_derivation_id": tid, "derivation_expression": tr.get("expression"), **base})

    # Flows -> source/storage/access lineage and writes.
    for flow in _as_list(data.get("flows")):
        fid = str(flow.get("id") or flow.get("flow_id") or _stable_id("flow", flow))
        source = flow.get("source") if isinstance(flow.get("source"), dict) else {}
        target = flow.get("target") if isinstance(flow.get("target"), dict) else {}
        source_obj = source.get("object") or flow.get("source_object")
        target_obj = target.get("object") or flow.get("target_object")
        flow_kind = flow.get("flow_type") or flow.get("flow_kind") or "spec_flow"
        lineage = {
            "source_to_storage_lineage_id": fid,
            "operation": source.get("operation") or flow.get("operation"),
            "source_payload": source_obj,
            "source_object": source_obj,
            "storage_target": target_obj,
            "storage_field": None,
            "lineage_status": flow.get("status") or "unresolved",
            "flow_kind": flow_kind,
            "evidence_level": _status_to_evidence_level(flow.get("evidence_status") or flow.get("status")),
            "source_type": "spec_artifacts",
            "evidence": _spec_evidence(fid, item=flow),
        }
        add("source_to_storage_lineage", lineage)
        if target_obj:
            add("persistent_write", {
                "persistent_write_id": _stable_id("persistent_write", fid),
                "operation": source.get("operation") or flow.get("operation"),
                "saved_object": target_obj,
                "storage_target": target_obj,
                "written_fields": flow.get("output_attributes") or [],
                "evidence_level": lineage["evidence_level"],
                "source_type": "spec_artifacts",
                "evidence": _spec_evidence(fid, item=flow),
            })

    for access in _as_list(data.get("access_paths")):
        aid = str(access.get("id") or access.get("access_path_id") or _stable_id("access", access))
        storage = access.get("storage") or access.get("storage_object") or access.get("source_storage_object")
        boundary = access.get("access_boundary") or access.get("endpoint_or_topic") or access.get("description")
        add("read_from_storage", {
            "read_from_storage_id": _stable_id("read", aid),
            "storage_object": storage,
            "storage_symbol": storage,
            "evidence_level": _status_to_evidence_level(access.get("evidence_status") or access.get("access_status")),
            "source_type": "spec_artifacts",
            "evidence": _spec_evidence(aid, item=access),
        })
        add("access_boundary", {
            "access_boundary_id": aid,
            "boundary_kind": access.get("boundary_kind") or "spec_access_path",
            "endpoint_or_topic": boundary,
            "response_or_payload_type": access.get("response_or_payload_type"),
            "fields": access.get("fields") or [],
            "evidence_level": _status_to_evidence_level(access.get("evidence_status") or access.get("access_status")),
            "source_type": "spec_artifacts",
            "evidence": _spec_evidence(aid, item=access),
        })
        add("storage_to_access_lineage", {
            "storage_to_access_lineage_id": _stable_id("storage_to_access", aid),
            "read_evidence_ref": _stable_id("read", aid),
            "access_evidence_ref": aid,
            "source_storage_object": storage,
            "access_boundary": boundary,
            "lineage_status": access.get("same_data_status") or access.get("status") or "unresolved",
            "source_type": "spec_artifacts",
            "evidence": _spec_evidence(aid, item=access),
        })

    # Gaps.
    for gap in _as_list(data.get("gaps")):
        gid = str(gap.get("id") or _stable_id("gap", gap))
        item = {
            "data_model_lineage_gap_id": gid,
            "gap_kind": gap.get("gap_type") or "spec_gap",
            "target": (gap.get("affected_object_refs") or [None])[0] if isinstance(gap.get("affected_object_refs"), list) else gap.get("affected_object_refs"),
            "reason": gap.get("reason") or gap.get("impact"),
            "missing_links": gap.get("missing_links") or [],
            "evidence_level": "unresolved",
            "source_type": "spec_artifacts",
            "evidence": _spec_evidence(gid, item=gap),
        }
        add("data_model_lineage_gap", item)
        add("unresolved_gap", {"unresolved_gap_id": gid, **item})

    return facts


def _write_facts(out: Path, facts: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    facts_dir = out / "facts" / "facts_by_type"
    facts_dir.mkdir(parents=True, exist_ok=True)
    counts = {}
    total = 0
    for ftype, items in sorted(facts.items()):
        write_json(facts_dir / f"{ftype}.json", items)
        counts[ftype] = len(items)
        total += len(items)
    summary = {"artifact": "fact_summary", "source_type": "spec_artifacts", "total_facts": total, "by_type": counts}
    write_json(out / "facts" / "fact_summary.json", summary)
    return summary


def _write_db_schema(out: Path, data: dict[str, Any]) -> dict[str, int]:
    storages = _as_list(data.get("storages"))
    storage_attrs = _as_list(data.get("storage_attributes"))
    attrs_by_storage: dict[str, list[dict[str, Any]]] = {}
    for attr in storage_attrs:
        attrs_by_storage.setdefault(str(attr.get("storage_ref") or ""), []).append(attr)

    tables = []
    columns = []
    keys = []
    rels = []
    indexes = []
    for storage in storages:
        sid = str(storage.get("id") or storage.get("suggested_id") or _stable_id("storage", storage.get("physical_name")))
        tname = storage.get("physical_name") or storage.get("table_name") or sid
        table_id = _stable_id("db_schema_table", sid, tname)
        tables.append({
            "db_schema_table_id": table_id,
            "table_name": tname,
            "schema_name": storage.get("schema_name"),
            "description": storage.get("description"),
            "source_type": "spec_artifacts",
            "evidence_level": _status_to_evidence_level(storage.get("evidence_status")),
            "evidence": _spec_evidence(sid, item=storage),
        })
        for attr in attrs_by_storage.get(sid, []):
            cname = attr.get("physical_name") or attr.get("technical_name") or attr.get("name")
            if not cname:
                continue
            columns.append({
                "db_schema_column_id": _stable_id("db_schema_column", sid, cname),
                "table_name": tname,
                "schema_name": storage.get("schema_name"),
                "column_name": cname,
                "sql_type": attr.get("sql_type") or attr.get("java_type") or "unknown",
                "java_type": attr.get("java_type"),
                "nullable": attr.get("nullable"),
                "description": attr.get("comment") or attr.get("description"),
                "source_type": "spec_artifacts",
                "evidence_level": _status_to_evidence_level(attr.get("evidence_status")),
                "evidence": _spec_evidence(str(attr.get("id") or cname), item=attr),
            })
    overview = {
        "artifact": "db_schema_overview",
        "source_type": "spec_artifacts",
        "tables_extracted": len(tables),
        "columns_extracted": len(columns),
        "keys_extracted": len(keys),
        "relationships_extracted": len(rels),
        "indexes_extracted": len(indexes),
        "schema_source": "data-evidence.yaml",
    }
    for base in [out / "sql", out / "compact"]:
        base.mkdir(parents=True, exist_ok=True)
        write_json(base / "db_schema_overview.json", overview)
        write_json(base / "db_schema_tables.json", tables)
        write_json(base / "db_schema_columns.json", columns)
        write_json(base / "db_schema_keys.json", keys)
        write_json(base / "db_schema_relationships.json", rels)
        write_json(base / "db_schema_indexes.json", indexes)
    return {"db_schema_tables": len(tables), "db_schema_columns": len(columns), "db_schema_keys": 0, "db_schema_relationships": 0, "db_schema_indexes": 0}


def _write_compact(out: Path, data: dict[str, Any], facts: dict[str, list[dict[str, Any]]], navigation: dict[str, Any], counts: dict[str, Any], repo_id: str, system_name: str, project_code: str) -> None:
    compact = out / "compact"
    compact.mkdir(parents=True, exist_ok=True)
    for fact_type, compact_name in [
        ("system_ingress", "ingress"),
        ("persistent_write", "persistent_writes"),
        ("source_to_storage_lineage", "source_to_storage_lineage"),
        ("storage_lineage_gap", "storage_lineage_gaps"),
        ("read_from_storage", "read_from_storage"),
        ("access_boundary", "access_boundaries"),
        ("storage_to_access_lineage", "storage_to_access_lineage"),
        ("stored_field_to_response_field_mapping", "stored_field_to_response_field_mappings"),
        ("attribute_occurrence", "attribute_occurrences"),
        ("attribute_mapping", "attribute_mappings"),
        ("attribute_derivation", "attribute_derivations"),
        ("data_model_lineage_gap", "data_model_lineage_gaps"),
        ("unresolved_gap", "unresolved_gaps"),
    ]:
        write_json(compact / f"{compact_name}.json", facts.get(fact_type, []))
    write_json(compact / "navigation.json", navigation)
    write_json(compact / "first_pass.json", {
        "artifact": "first_pass",
        "source_type": "spec_artifacts",
        "repo_id": repo_id,
        "system_name": system_name,
        "project_code": project_code,
        "counts": counts,
        "data_evidence_metadata": data.get("metadata") or {},
        "message": "Generated by analyze-spec from deterministic SDD/data-evidence artifacts; no code evidence is included.",
    })
    write_json(compact / "package_manifest.json", {
        "artifact": "compact_package_manifest",
        "source_type": "spec_artifacts",
        "items": sorted(p.name for p in compact.glob("*.json")),
    })


def _write_evidence_coverage(out: Path, data: dict[str, Any], counts: dict[str, Any]) -> dict[str, Any]:
    metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
    substitution_grade = metadata.get("substitution_grade") is True
    limitations = [
        {
            "component": "source_inspection",
            "status": "not_available_for_spec_artifacts",
            "gap_type": "source_inspection_not_available",
            "impact": "This workspace was built from specification artifacts; direct source code inspection is not available.",
        }
    ]
    if not substitution_grade:
        limitations.append({
            "component": "data_evidence_yaml",
            "status": "substitution_grade_not_confirmed",
            "gap_type": "spec_evidence_not_substitution_grade",
            "impact": "metadata.substitution_grade is not true; downstream conclusions must be treated as partial/spec-derived.",
        })
    coverage = {
        "artifact": "evidence_coverage",
        "format_version": "1.0",
        "policy": "spec_artifacts_to_standard_analysis_output",
        "source_type": "spec_artifacts",
        "code_evidence_included": False,
        "source_inspection_available": False,
        "generated_from_code_evidence": bool(metadata.get("generated_from_code_evidence", True)),
        "substitution_grade": substitution_grade,
        "authoritative_specification": bool(metadata.get("authoritative_specification", False)),
        "business_owner_confirmed": bool(metadata.get("business_owner_confirmed", False)),
        "business_decisions_made": bool(metadata.get("business_decisions_made", False)),
        "export_completeness": metadata.get("export_completeness") or {},
        "section_order": metadata.get("section_order") or [],
        "schema_evolution_policy": metadata.get("schema_evolution_policy") or "unknown sections are preserved as data-evidence sections and should not break consumers",
        "stages": {
            "spec_artifact_discovery": {"requested_by_profile": True, "status": "success"},
            "data_evidence_yaml_parse": {"requested_by_profile": True, "status": "success"},
            "standard_analysis_output_build": {"requested_by_profile": True, "status": "success"},
            "java_structural_scan": {"requested_by_profile": False, "status": "not_run_source_type_spec_artifacts"},
            "sql_scan": {"requested_by_profile": False, "status": "not_run_source_type_spec_artifacts"},
            "db_schema_scan": {"requested_by_profile": False, "status": "not_run_source_type_spec_artifacts"},
        },
        "counts": counts,
        "limitations": limitations,
        "heavy_tools": {
            "spoon_scan": {"status": "removed_from_fast_core", "requested_by_profile": False},
            "semgrep_scan": {"status": "removed_from_fast_core", "requested_by_profile": False},
            "targeted_semgrep_scan": {"status": "removed_from_fast_core", "requested_by_profile": False},
        },
    }
    write_json(out / "evidence_coverage.json", coverage)
    write_json(out / "diagnostics" / "evidence_coverage.json", coverage)
    return coverage


def _capabilities() -> list[str]:
    return [
        "operation", "interface", "schema", "symbol", "field", "search", "relation", "query", "lineage", "show", "flow",
        "confirmed-evidence", "candidate-signal", "unresolved-gap", "ingress", "storage-access", "stored-data-access",
        "read-from-storage", "access-boundary", "storage-to-access-lineage", "stored-field-to-response-field-mapping",
        "data-source", "persistent-write", "source-to-storage-lineage", "storage-lineage-gap", "persistent-structure",
        "attribute-occurrence", "attribute-mapping", "attribute-derivation", "data-model-lineage-gap",
        "system-data-model-overview", "system-table-catalog", "event-source-catalog", "system-scenario-catalog",
        "db-schema-overview", "db-table-catalog", "db-table-detail", "db-column-catalog", "db-relationship-catalog", "db-index-catalog",
        "facts-by-type", "workspace-persistent-model", "workspace-attribute-catalog", "workspace-table-catalog",
        "workspace-table-attribute-catalog", "workspace-attribute-graph", "workspace-source-to-storage-lineage",
        "workspace-data-model-lineage-gaps", "evidence-coverage", "transformation-catalog", "foreign-data-persistence-cases",
    ]


def run_spec_analysis(
    *,
    spec_artifacts: str | Path,
    analysis_out: str | Path,
    repo_id: str | None = None,
    project_code: str = "UNKNOWN",
    system_name: str = "unknown-system",
    run_id: str | None = None,
    analysis_profile: str | Path | None = None,
    verbose: bool = False,
) -> dict[str, Any]:
    artifacts = Path(spec_artifacts).resolve()
    if not artifacts.exists() or not artifacts.is_dir():
        raise FileNotFoundError(f"Spec artifacts directory not found: {artifacts}")
    data_path = artifacts / "data-evidence.yaml"
    if not data_path.exists():
        raise FileNotFoundError(f"data-evidence.yaml is required for analyze-spec: {data_path}")
    data = _read_yaml_mapping(data_path)
    metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
    rid = repo_id_from_path(artifacts.parent if artifacts.name == "artifacts" else artifacts, repo_id or metadata.get("repo_id"))
    sys_name = system_name if system_name != "unknown-system" else str((data.get("system") or {}).get("system_name") or metadata.get("system_name") or rid)
    profile_path = Path(analysis_profile).resolve() if analysis_profile else None
    profile_meta: dict[str, Any] = {
        "profile_id": SPEC_ANALYSIS_PROFILE_ID,
        "profile_version": "1",
        "source_type": "spec_artifacts",
    }
    if profile_path and profile_path.exists():
        try:
            loaded = _read_yaml_mapping(profile_path)
            profile_meta.update({k: v for k, v in loaded.items() if k in {"profile_id", "profile_version", "name", "description", "source_type"}})
        except Exception:
            pass
    profile_meta.setdefault("profile_id", SPEC_ANALYSIS_PROFILE_ID)

    rid_run = safe_run_id(run_id)
    out = Path(analysis_out).resolve()
    for sub in ["core", "compact", "facts/facts_by_type", "diagnostics", "lazy", "sql", "spec_artifacts"]:
        (out / sub).mkdir(parents=True, exist_ok=True)

    navigation = _build_navigation(data)
    facts = _build_facts(data)
    fact_summary = _write_facts(out, facts)
    db_counts = _write_db_schema(out, data)

    section_counts = {k: len(v) for k, v in data.items() if isinstance(v, list)}
    counts = {
        "source_type": "spec_artifacts",
        "interfaces": len(_as_list(data.get("interfaces"))),
        "schemas": len(_as_list(data.get("payload_schemas"))),
        "payload_schemas": len(_as_list(data.get("payload_schemas"))),
        "entities": len(_as_list(data.get("entities"))),
        "attributes": len(_as_list(data.get("attributes"))),
        "storages": len(_as_list(data.get("storages"))),
        "storage_attributes": len(_as_list(data.get("storage_attributes"))),
        "flows": len(_as_list(data.get("flows"))),
        "transformations": len(_as_list(data.get("transformations"))),
        "access_paths": len(_as_list(data.get("access_paths"))),
        "gaps": len(_as_list(data.get("gaps"))),
        "facts": fact_summary.get("total_facts"),
        "relations": len(facts.get("attribute_mapping", [])) + len(facts.get("source_to_storage_lineage", [])) + len(facts.get("storage_to_access_lineage", [])),
        "files_analyzed": 1 + len(_discover_support_artifacts(artifacts)),
        **db_counts,
        "attribute_occurrences": len(facts.get("attribute_occurrence", [])),
        "attribute_mappings": len(facts.get("attribute_mapping", [])),
        "attribute_derivations": len(facts.get("attribute_derivation", [])),
        "source_to_storage_lineages": len(facts.get("source_to_storage_lineage", [])),
        "persistent_writes": len(facts.get("persistent_write", [])),
        "data_model_lineage_gaps": len(facts.get("data_model_lineage_gap", [])),
    }

    _write_compact(out, data, facts, navigation, counts, rid, sys_name, project_code)
    coverage = _write_evidence_coverage(out, data, counts)

    artifact_manifest = _read_json_mapping(_artifact_manifest_path(artifacts) or Path("__missing__"))
    support_artifacts = _discover_support_artifacts(artifacts)
    write_json(out / "spec_artifacts" / "artifact_index.json", {
        "artifact": "spec_artifact_index",
        "source_type": "spec_artifacts",
        "spec_artifacts_dir": str(artifacts),
        "data_evidence_path": str(data_path),
        "artifacts_manifest_path": str(_artifact_manifest_path(artifacts)) if _artifact_manifest_path(artifacts) else None,
        "artifacts_manifest": artifact_manifest,
        "support_artifacts": support_artifacts,
        "section_counts": section_counts,
    })
    write_json(out / "spec_artifacts" / "data_evidence_metadata.json", metadata)

    write_json(out / "core" / "repository.json", {
        "system_name": sys_name,
        "project_code": project_code,
        "repo_path": str(artifacts),
        "stack": ["spec_artifacts", "data_evidence_yaml"],
        "files_analyzed": counts["files_analyzed"],
        "source_type": "spec_artifacts",
    })

    started_at = now_utc()
    manifest = {
        "artifact": "analysis-output",
        "analysis_output_contract_version": ANALYSIS_CONTRACT_VERSION,
        "evidence_tool_contract_version": EVIDENCE_TOOL_CONTRACT_VERSION,
        "core_version": CORE_VERSION,
        "created_by": "code-analyzer-core",
        "created_at": started_at,
        "analysis_scope": "repository",
        "repo_path": str(artifacts),
        "repo_id": rid,
        "static_analysis_output": str(out),
        "workspace_type": SPEC_WORKSPACE_CONTRACT_TYPE,
        "system_name": sys_name,
        "project_code": project_code,
        "analysis_profile": profile_meta,
        "analysis_profile_id": profile_meta.get("profile_id"),
        "source_type": "spec_artifacts",
        "workspace_contract_type": SPEC_WORKSPACE_CONTRACT_TYPE,
        "code_evidence_included": False,
        "source_inspection_available": False,
        "generated_from_code_evidence": bool(metadata.get("generated_from_code_evidence", True)),
        "substitution_grade": metadata.get("substitution_grade"),
        "authoritative_specification": bool(metadata.get("authoritative_specification", False)),
        "business_owner_confirmed": bool(metadata.get("business_owner_confirmed", False)),
        "business_decisions_made": bool(metadata.get("business_decisions_made", False)),
        "output_policy": "strict_evidence_contract_json_lazy_evidence_human_views_external",
        "evidence_provider": {"access_api": "code_evidence.access", "capabilities": _capabilities()},
        "enabled_capabilities": _capabilities(),
        "counts": counts,
    }
    write_json(out / "manifest.json", manifest)
    write_json(out / "diagnostics" / "run.json", {
        "status": "success",
        "source_type": "spec_artifacts",
        "analysis_profile": profile_meta,
        "started_at": started_at,
        "finished_at": now_utc(),
        "counts": counts,
    })
    write_json(out / "diagnostics" / "scanner_status.json", {"spec_static_analysis": {"status": "success"}, "evidence_coverage": coverage})

    latest = {
        "repo_id": rid,
        "repo_path": str(artifacts),
        "system_name": sys_name,
        "project_code": project_code,
        "fp_id": rid,
        "fp_name": rid,
        "profile": SPEC_WORKSPACE_CONTRACT_TYPE,
        "workspace_type": SPEC_WORKSPACE_CONTRACT_TYPE,
        "run_id": rid_run,
        "static_analysis_output": str(out),
        "analysis_out": str(out),
        "updated_at": now_utc(),
        "counts": counts,
    }
    repo_manifest = write_repository_analysis_manifest(
        repository_analysis_root=repository_analysis_root_for_static_output(out),
        repo_id=rid,
        source_repository_path=artifacts,
        static_analysis_output=out,
        static_profile=str(profile_meta.get("profile_id") or SPEC_ANALYSIS_PROFILE_ID),
        run_id=rid_run,
        project_code=project_code,
        system_name=sys_name,
        counts=counts,
    )
    return {"repo": latest, "repository_analysis_manifest": repo_manifest, "analysis_out": str(out), "static_analysis_output": str(out), "source_type": "spec_artifacts"}
