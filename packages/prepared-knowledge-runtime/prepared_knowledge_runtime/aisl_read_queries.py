from __future__ import annotations

import json
from typing import Any, TYPE_CHECKING

from .normalization import stable_id

if TYPE_CHECKING:
    from .query import KnowledgeLayerQuery

AISL_ITEM_READ_PROJECTION_VERSION = "aisl-item-read-projection/v1"


def _json(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _row(query: "KnowledgeLayerQuery", table: str, id_field: str, local_id: str) -> dict[str, Any] | None:
    if not query._has_relation(table):
        return None
    with query._connect() as con:
        rows = query._rows(con.execute(f'SELECT * FROM "{table}" WHERE "{id_field}"=?', [local_id]))
    return dict(rows[0]) if rows else None


def _source_fragment(source_id: str, ref: dict[str, Any], *, fallback_path: str | None = None) -> dict[str, Any] | None:
    path = str(
        ref.get("repository_relative_path")
        or ref.get("relative_file")
        or ref.get("file_path")
        or ref.get("file")
        or ref.get("path")
        or fallback_path
        or ""
    ).strip()
    if not path:
        return None
    line_start = ref.get("line_start")
    line_end = ref.get("line_end")
    locator = path
    if line_start is not None:
        locator += f":{line_start}"
        if line_end is not None and line_end != line_start:
            locator += f"-{line_end}"
    return {
        "fragment_id": stable_id("aisl_source_fragment", source_id, locator),
        "source_id": source_id,
        "fragment_kind": "source_location",
        "locator": locator,
        "content_identity": ref.get("content_identity") or ref.get("sha256"),
        "path": path,
        "line_start": line_start,
        "line_end": line_end,
        "extractor": ref.get("extractor"),
    }


def _evidence_from_source_ref(source_id: str, source_ref: dict[str, Any], *, basis: str, fallback_path: str | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    fragment = _source_fragment(source_id, source_ref, fallback_path=fallback_path)
    if fragment is None:
        return [], []
    evidence_id = stable_id("aisl_evidence", source_id, fragment["fragment_id"], basis)
    return ([{
        "evidence_id": evidence_id,
        "evidence_kind": "observed_source",
        "source_fragment_ids": [fragment["fragment_id"]],
        "basis": basis,
    }], [fragment])


def _physical_evidence(source_id: str, item: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    raw = _json(item.get("evidence_json") if "evidence_json" in item else item.get("evidence"), {})
    refs: list[dict[str, Any]] = []
    if isinstance(raw, list):
        refs.extend(dict(v) for v in raw if isinstance(v, dict))
    elif isinstance(raw, dict):
        if any(k in raw for k in ("file", "path", "file_path", "repository_relative_path", "relative_file", "line_start")):
            refs.append(raw)
        for key in ("evidence", "refs", "source_refs"):
            nested = raw.get(key)
            if isinstance(nested, list):
                refs.extend(dict(v) for v in nested if isinstance(v, dict))
    if not refs and item.get("source_file"):
        refs.append({"file": item.get("source_file")})
    evidence: list[dict[str, Any]] = []
    fragments: list[dict[str, Any]] = []
    for index, ref in enumerate(refs):
        ev, fr = _evidence_from_source_ref(source_id, ref, basis=f"physical_model_observation:{index}", fallback_path=str(item.get("source_file") or ""))
        evidence.extend(ev); fragments.extend(fr)
    return evidence, fragments


def _issue(issue_id: str, kind: str, message: str, *, basis: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"issue_id": issue_id, "kind": kind, "message": message, "basis": basis, "details": dict(details or {})}


def _code_item(query: "KnowledgeLayerQuery", item_kind: str, local_id: str) -> dict[str, Any]:
    if item_kind == "declared_object":
        result = query.get_code_declared_object(local_id)
        item = result.get("object")
        if item is None:
            return {"not_found": True}
        source_id = str(item.get("repo_id") or "unknown")
        evidence, fragments = _evidence_from_source_ref(source_id, dict(item.get("source_ref") or {}), basis="declared_type_source_ref")
        return {"item": item, "evidence": evidence, "source_fragments": fragments, "issues": []}

    if item_kind in {"declared_field", "effective_field"}:
        if item_kind == "declared_field":
            row = _row(query, "code_declared_field", "field_occurrence_id", local_id)
            if row is None:
                return {"not_found": True}
            row["documentation"] = _json(row.pop("documentation_json", None), {})
            row["source_ref"] = _json(row.pop("source_ref_json", None), {})
            row["payload"] = _json(row.pop("payload_json", None), {})
            source_id = str(row.get("repo_id") or "unknown")
            evidence, fragments = _evidence_from_source_ref(source_id, row["source_ref"], basis="declared_field_source_ref")
            return {"item": row, "evidence": evidence, "source_fragments": fragments, "issues": []}
        row = _row(query, "code_declared_effective_field", "effective_field_occurrence_id", local_id)
        if row is None:
            return {"not_found": True}
        row["provenance"] = _json(row.pop("provenance_json", None), {})
        # Effective/inherited field is derived; direct source evidence belongs to the declared field.
        declared = _row(query, "code_declared_field", "field_occurrence_id", str(row.get("field_occurrence_id") or ""))
        evidence: list[dict[str, Any]] = []; fragments: list[dict[str, Any]] = []
        if declared:
            ref = _json(declared.get("source_ref_json"), {})
            evidence, fragments = _evidence_from_source_ref(str(declared.get("repo_id") or "unknown"), ref, basis="effective_field_declared_source_ref")
        return {"item": row, "evidence": evidence, "source_fragments": fragments, "issues": []}

    if item_kind == "declared_relationship":
        row = _row(query, "code_declared_relationship", "relationship_occurrence_id", local_id)
        if row is None:
            return {"not_found": True}
        row["provenance"] = _json(row.pop("provenance_json", None), {})
        field = _row(query, "code_declared_field", "field_occurrence_id", str(row.get("field_occurrence_id") or ""))
        evidence: list[dict[str, Any]] = []; fragments: list[dict[str, Any]] = []
        if field:
            evidence, fragments = _evidence_from_source_ref(str(field.get("repo_id") or "unknown"), _json(field.get("source_ref_json"), {}), basis="relationship_declaring_field_source_ref")
        issues = []
        status = str(row.get("resolution_status") or "").lower()
        if status in {"unresolved", "ambiguous"}:
            kind = "ambiguity" if status == "ambiguous" else "unresolved_reference"
            issues.append(_issue(stable_id("aisl_issue", "declared_relationship", local_id, status), kind, f"Declared relationship resolution status is {status}.", basis="code_declared_relationship.resolution_status"))
        return {"item": row, "evidence": evidence, "source_fragments": fragments, "issues": issues}

    return {"unsupported": True, "supported_item_kinds": ["declared_object", "declared_field", "effective_field", "declared_relationship"]}


def _physical_item(query: "KnowledgeLayerQuery", item_kind: str, local_id: str) -> dict[str, Any]:
    spec = {
        "physical_table": ("physical_model_table", "physical_model_table_id"),
        "physical_column": ("physical_model_column", "physical_model_column_id"),
        "physical_key": ("physical_model_key", "physical_model_key_id"),
        "physical_relationship": ("physical_model_relationship", "physical_model_relationship_id"),
    }.get(item_kind)
    if spec is None:
        return {"unsupported": True, "supported_item_kinds": ["physical_table", "physical_column", "physical_key", "physical_relationship"]}
    row = _row(query, *spec, local_id)
    if row is None:
        return {"not_found": True}
    for key in list(row):
        if key.endswith("_json"):
            row[key[:-5]] = _json(row.pop(key), [] if key in {"joins_json", "column_codes_json", "column_pdm_ids_json", "unresolved_column_refs_json"} else {})
    row.pop("payload", None)
    source_id = str(row.get("physical_model_source_id") or "unknown")
    evidence, fragments = _physical_evidence(source_id, row)
    issues: list[dict[str, Any]] = []
    status = str(row.get("resolution_status") or "").lower()
    if status in {"unresolved", "ambiguous", "partial"}:
        kind = "ambiguity" if status == "ambiguous" else "unresolved_reference"
        issues.append(_issue(stable_id("aisl_issue", item_kind, local_id, status), kind, f"Physical model item resolution status is {status}.", basis="physical_model_resolution_status"))
    pdm_id = str(row.get("pdm_object_id") or "")
    if pdm_id and query._has_relation("physical_model_gap"):
        with query._connect() as con:
            gaps = query._rows(con.execute("SELECT * FROM physical_model_gap WHERE owner_pdm_object_id=? ORDER BY physical_model_gap_id", [pdm_id]))
        for gap in gaps:
            issues.append(_issue(str(gap.get("physical_model_gap_id")), "missing_information", str(gap.get("message") or gap.get("gap_kind") or "physical model gap"), basis="physical_model_gap", details={"gap_kind": gap.get("gap_kind"), "unresolved_ref": gap.get("unresolved_ref")}))
    return {"item": row, "evidence": evidence, "source_fragments": fragments, "issues": issues}


def _mapping_item(query: "KnowledgeLayerQuery", item_kind: str, local_id: str) -> dict[str, Any]:
    spec = {
        "entity_mapping": ("logical_physical_entity_mapping", "entity_mapping_id"),
        "field_mapping": ("logical_physical_field_mapping", "field_mapping_id"),
        "key_mapping": ("logical_physical_key_mapping", "key_mapping_id"),
        "relationship_mapping": ("logical_physical_relationship_mapping", "relationship_mapping_id"),
    }.get(item_kind)
    if spec is None:
        return {"unsupported": True, "supported_item_kinds": ["entity_mapping", "field_mapping", "key_mapping", "relationship_mapping"]}
    row = _row(query, *spec, local_id)
    if row is None:
        return {"not_found": True}
    for key in list(row):
        if key.endswith("_json"):
            row[key[:-5]] = _json(row.pop(key), [] if "candidate" in key or "diagnostics" in key else {})
    source = _row(query, "logical_physical_mapping_source", "mapping_source_id", str(row.get("mapping_source_id") or ""))
    evidence, fragments = _evidence_from_source_ref(str(row.get("repo_id") or "mapping"), dict(row.get("source_ref") or {}), basis=f"logical_physical_{item_kind}_source_ref")
    status = str(row.get("mapping_status") or "").lower()
    issues: list[dict[str, Any]] = []
    for diag in row.get("diagnostics") or []:
        if isinstance(diag, dict):
            issues.append(_issue(stable_id("aisl_issue", item_kind, local_id, json.dumps(diag, sort_keys=True, default=str)), "insufficient_evidence", str(diag.get("message") or diag.get("kind") or "mapping diagnostic"), basis="logical_physical_mapping.diagnostics", details=diag))
    if status in {"unresolved", "ambiguous", "partial"}:
        kind = "ambiguity" if status == "ambiguous" else "unresolved_reference"
        issues.append(_issue(stable_id("aisl_issue", item_kind, local_id, status), kind, f"Logical/physical mapping status is {status}.", basis="logical_physical_mapping.mapping_status"))

    correspondence: dict[str, Any] | None = None
    if source:
        code_product_id = str(source.get("code_declared_artifact_id") or "")
        physical_product_id = str(source.get("physical_model_artifact_id") or "")
        source_kind = target_kind = source_local = target_local = ""
        if item_kind == "entity_mapping":
            source_kind, source_local = "declared_object", str(row.get("logical_type_occurrence_id") or "")
            target_kind, target_local = "physical_table", str(row.get("physical_model_table_id") or "")
        elif item_kind == "field_mapping":
            source_kind, source_local = "declared_field", str(row.get("logical_field_occurrence_id") or "")
            target_kind, target_local = "physical_column", str(row.get("physical_model_column_id") or "")
        if code_product_id and physical_product_id and source_local:
            candidates = []
            candidate_key = "candidate_physical_table_ids" if item_kind == "entity_mapping" else "candidate_physical_column_ids"
            candidate_kind = "physical_table" if item_kind == "entity_mapping" else "physical_column"
            for candidate_id in row.get(candidate_key) or []:
                candidates.append({"product_id": physical_product_id, "item_kind": candidate_kind, "local_id": str(candidate_id)})
            correspondence = {
                "correspondence_id": local_id,
                "relation_kind": "maps_to",
                "source": {"product_id": code_product_id, "item_kind": source_kind, "local_id": source_local},
                "target": ({"product_id": physical_product_id, "item_kind": target_kind, "local_id": target_local} if target_local and status == "matched" else None),
                "candidate_targets": candidates,
                "resolution_status": "resolved" if target_local and status == "matched" else ("ambiguous" if len(candidates) > 1 else "unresolved"),
                "basis": str(row.get("mapping_basis") or "logical_physical_mapping"),
                "evidence_ids": [e["evidence_id"] for e in evidence],
            }
    return {"item": row, "evidence": evidence, "source_fragments": fragments, "issues": issues, "correspondence": correspondence}




def _persistence_lineage_item(query: "KnowledgeLayerQuery", item_kind: str, local_id: str) -> dict[str, Any]:
    artifact_by_kind = {
        "source_to_storage_lineage": "source_to_storage_lineage.json",
        "storage_to_access_lineage": "storage_to_access_lineage.json",
        "persistent_write": "persistent_writes.json",
        "storage_access": "storage_accesses.json",
        "storage_lineage_gap": "storage_lineage_gaps.json",
        "stored_field_to_response_field_mapping": "stored_field_to_response_field_mappings.json",
    }
    artifact_name = artifact_by_kind.get(item_kind)
    supported = list(artifact_by_kind)
    if artifact_name is None:
        return {"unsupported": True, "supported_item_kinds": supported}
    if not query._has_relation("subject_knowledge_record"):
        return {"not_found": True}
    record_kind = artifact_name.removesuffix(".json")
    with query._connect() as con:
        rows = query._rows(con.execute(
            '''SELECT record_occurrence_id, repo_id, artifact_name, record_kind, local_record_id, payload_json
               FROM subject_knowledge_record
               WHERE materialization_id='persistence-lineage'
                 AND artifact_name=? AND record_kind=? AND local_record_id=?
               ORDER BY record_occurrence_id''',
            [artifact_name, record_kind, local_id],
        ))
    if not rows:
        return {"not_found": True}
    if len(rows) > 1:
        return {
            "item": {"local_record_id": local_id, "matching_record_occurrence_ids": [str(v["record_occurrence_id"]) for v in rows]},
            "evidence": [],
            "source_fragments": [],
            "issues": [_issue(
                stable_id("aisl_issue", "persistence_lineage", item_kind, local_id, "ambiguous_identity"),
                "ambiguity",
                "Persistence-lineage local item identity matches more than one prepared record.",
                basis="subject_knowledge_record.local_record_id",
                details={"item_kind": item_kind, "match_count": len(rows)},
            )],
        }
    row = dict(rows[0])
    payload = _json(row.get("payload_json"), {})
    item = dict(payload) if isinstance(payload, dict) else {"payload": payload}
    item.setdefault("repo_id", str(row.get("repo_id") or ""))
    item.setdefault("record_occurrence_id", str(row.get("record_occurrence_id") or ""))

    evidence: list[dict[str, Any]] = []
    fragments: list[dict[str, Any]] = []
    for index, ref in enumerate(item.get("evidence") or []):
        if not isinstance(ref, dict):
            continue
        ev, fr = _evidence_from_source_ref(
            str(row.get("repo_id") or "unknown"),
            ref,
            basis=f"persistence_lineage:{item_kind}:{index}",
        )
        evidence.extend(ev)
        fragments.extend(fr)

    issues: list[dict[str, Any]] = []
    if item_kind == "storage_lineage_gap":
        issues.append(_issue(
            str(item.get("storage_lineage_gap_id") or stable_id("aisl_issue", "persistence_lineage_gap", local_id)),
            "missing_information",
            str(item.get("reason") or item.get("gap_kind") or "Persistence-lineage gap"),
            basis="persistence_lineage.storage_lineage_gap",
            details={
                "gap_kind": item.get("gap_kind"),
                "missing_links": list(item.get("missing_links") or []),
                "source_inspection_required": item.get("source_inspection_required"),
                "source_inspection_request_ids": list(item.get("source_inspection_request_ids") or []),
            },
        ))
    else:
        status = str(item.get("lineage_status") or item.get("evidence_level") or item.get("evidence_maturity_level") or "").lower()
        if status in {"unresolved", "ambiguous", "partial", "candidate", "probable"}:
            kind = "ambiguity" if status == "ambiguous" else "insufficient_evidence"
            issues.append(_issue(
                stable_id("aisl_issue", "persistence_lineage", item_kind, local_id, status),
                kind,
                f"Persistence-lineage item evidence status is {status}.",
                basis="persistence_lineage.evidence_status",
                details={
                    "lineage_status": item.get("lineage_status"),
                    "evidence_level": item.get("evidence_level"),
                    "evidence_maturity_level": item.get("evidence_maturity_level"),
                    "missing_links": list(item.get("missing_links") or []),
                },
            ))
    return {"item": item, "evidence": evidence, "source_fragments": fragments, "issues": issues}

def get_aisl_knowledge_item(query: "KnowledgeLayerQuery", *, model_kind: str, item_kind: str, local_id: str) -> dict[str, Any]:
    model_kind = str(model_kind or "").strip()
    item_kind = str(item_kind or "").strip()
    local_id = str(local_id or "").strip()
    if not item_kind or not local_id:
        raise ValueError("item_kind and local_id must not be empty")
    handlers = {
        "code-declared-data-model": _code_item,
        "physical-data-model": _physical_item,
        "logical-physical-model-mapping": _mapping_item,
        "persistence-lineage": _persistence_lineage_item,
    }
    handler = handlers.get(model_kind)
    if handler is None:
        return {"schema_version": AISL_ITEM_READ_PROJECTION_VERSION, "unsupported": True, "model_kind": model_kind, "supported_model_kinds": sorted(handlers)}
    result = handler(query, item_kind, local_id)
    return {"schema_version": AISL_ITEM_READ_PROJECTION_VERSION, "model_kind": model_kind, "item_kind": item_kind, "local_id": local_id, **result}
