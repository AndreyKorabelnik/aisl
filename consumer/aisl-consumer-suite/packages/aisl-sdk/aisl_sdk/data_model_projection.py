from __future__ import annotations

from typing import Any, Iterable, Mapping


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _list_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(v) for v in value if isinstance(v, Mapping)]


def _text(value: Any) -> str:
    return str(value or "").strip()


def _unique_nonempty(values: Iterable[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = _text(value)
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result

def _docs(value: Any) -> dict[str, Any]:
    docs = _dict(value)
    return {
        key: docs[key]
        for key in ("display_name", "summary", "description")
        if key in docs and docs[key] not in (None, "")
    }


def _scalar_type(declared: str) -> str:
    value = declared.strip()
    mapping = {
        "Long": "long",
        "long": "long",
        "Integer": "integer",
        "int": "integer",
        "Boolean": "boolean",
        "boolean": "boolean",
        "Date": "date",
        "LocalDate": "date",
        "LocalDateTime": "datetime",
        "OffsetDateTime": "datetime",
        "String": "string",
    }
    return mapping.get(value, value or "unknown")


def _storage_parts(rel: Mapping[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    storage = _dict(rel.get("storage_semantics"))
    candidates = _list_dicts(storage.get("candidate_mappings"))
    if isinstance(storage.get("mapping"), Mapping):
        candidates = [dict(storage["mapping"])] + candidates
    observations = _list_dicts(storage.get("observations"))
    derivations = _list_dicts(storage.get("reference_value_derivations"))
    return storage, candidates, observations, derivations


def _stored_as(rel: Mapping[str, Any]) -> str | None:
    _storage, candidates, observations, derivations = _storage_parts(rel)
    kinds = _unique_nonempty(x.get("storage_relation_kind") for x in candidates)
    if len(kinds) == 1:
        return kinds[0]
    if derivations:
        return "reference_value"
    operations = _unique_nonempty(x.get("reference_operation") for x in observations)
    if operations == ["referenceField"]:
        return "single_reference"
    if operations == ["replaceReferenceCollection"]:
        return "collection_reference"
    return None


def _target_storage_field(rel: Mapping[str, Any]) -> str | None:
    _storage, _candidates, observations, _derivations = _storage_parts(rel)
    values = _unique_nonempty(x.get("target_storage_key_field") for x in observations)
    return values[0] if len(values) == 1 else None


def _field_projection(field: Mapping[str, Any], relationships: list[dict[str, Any]]) -> dict[str, Any]:
    docs = _docs(field.get("documentation"))
    cardinalities = _unique_nonempty(
        _text(_dict(rel.get("cardinality")).get("value")) for rel in relationships
    )
    result: dict[str, Any] = {
        "name": _text(field.get("name")),
        "type": _scalar_type(_text(field.get("declared_type_expression"))),
    }
    if relationships:
        result["type"] = "reference_collection" if "many" in cardinalities else "reference"
        result["declared_type"] = _text(field.get("declared_type_expression"))
        if len(relationships) > 1:
            result["relationship_count"] = len(relationships)
    if docs.get("display_name"):
        result["display_name"] = docs["display_name"]
    if docs.get("description") or docs.get("summary"):
        result["description"] = docs.get("description") or docs.get("summary")
    if field.get("is_inherited") is True:
        result["inherited"] = True
        result["inherited_depth"] = int(field.get("inherited_depth") or 0)
    return {k: v for k, v in result.items() if v not in (None, "", [])}


def _key_projection(storage_identities: list[dict[str, Any]], include_provenance: bool) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for identity in storage_identities:
        item: dict[str, Any] = {
            "kind": "storage_identity",
            "status": identity.get("status"),
            "basis": identity.get("basis"),
            "storage_alias": identity.get("storage_alias"),
            "storage_key_expression": identity.get("storage_key_expression"),
            "repo_id": identity.get("storage_repo_id"),
        }
        observation = _dict(identity.get("observation"))
        if observation.get("observation_id"):
            item["source_observation_id"] = observation["observation_id"]
        if include_provenance and observation.get("source_refs"):
            item["source_refs"] = observation["source_refs"]
        result.append({k: v for k, v in item.items() if v not in (None, "", [])})
    return result


def _storage_key_derivations(rel: Mapping[str, Any], include_provenance: bool) -> list[dict[str, Any]]:
    _storage, candidates, observations, _derivations = _storage_parts(rel)
    obs_by_id = {_text(x.get("observation_id")): x for x in observations if _text(x.get("observation_id"))}
    result: list[dict[str, Any]] = []
    for candidate in candidates:
        obs = obs_by_id.get(_text(candidate.get("storage_observation_id")), {})
        item: dict[str, Any] = {
            "source_observation_id": candidate.get("storage_observation_id"),
            "storage_repo_id": candidate.get("storage_repo_id"),
            "storage_relation_kind": candidate.get("storage_relation_kind"),
            "reference_operation": obs.get("reference_operation"),
            "source_operation": obs.get("source_operation"),
            "target_converter_operation": obs.get("target_converter_operation"),
            "target_storage_key_field": obs.get("target_storage_key_field"),
            "reference_value_expression": obs.get("reference_value_expression"),
            "target_key_expression": candidate.get("storage_key_expression") or obs.get("target_storage_key_expression"),
            "knowledge_class": candidate.get("knowledge_class"),
            "mapping_status": candidate.get("mapping_status"),
            "mapping_basis": candidate.get("mapping_basis"),
        }
        if include_provenance and obs.get("source_refs"):
            item["source_refs"] = obs["source_refs"]
        result.append({k: v for k, v in item.items() if v not in (None, "", [])})
    return result


def _reference_correspondences(rel: Mapping[str, Any], include_provenance: bool) -> list[dict[str, Any]]:
    _storage, _candidates, _observations, derivations = _storage_parts(rel)
    result: list[dict[str, Any]] = []
    for derivation in derivations:
        item: dict[str, Any] = {
            "source_observation_id": derivation.get("observation_id"),
            "repo_id": derivation.get("repo_id"),
            "reference_operation": derivation.get("reference_operation"),
            "source_operation": derivation.get("source_operation"),
            "value_converter_operation": derivation.get("value_converter_operation"),
            "reference_value_expression": derivation.get("reference_value_expression"),
            "composed_reference_value_expression": derivation.get("composed_reference_value_expression"),
            "target_key_operation": derivation.get("target_key_operation"),
            "target_key_expression": derivation.get("target_key_expression"),
            "target_key_fields": derivation.get("target_key_fields"),
            "match_basis": derivation.get("match_basis"),
        }
        if include_provenance and derivation.get("source_refs"):
            item["source_refs"] = derivation["source_refs"]
        result.append({k: v for k, v in item.items() if v not in (None, "", [])})
    return result


def _relationship_projection(rel: Mapping[str, Any], include_provenance: bool) -> dict[str, Any]:
    declared = _dict(rel.get("declared_relationship"))
    target = _dict(rel.get("target"))
    cardinality = _dict(rel.get("cardinality"))
    storage, candidates, _observations, _derivations = _storage_parts(rel)
    storage_join = _dict(rel.get("storage_join"))
    physical = _dict(rel.get("physical_mapping"))
    target_fields = [str(x) for x in storage_join.get("target_key_fields") or [] if str(x)]
    target_field = target_fields[0] if len(target_fields) == 1 else _target_storage_field(rel)
    stored_as = _stored_as(rel)

    basis = _dict(storage_join.get("basis"))
    provenance = _dict(storage_join.get("provenance"))
    join: dict[str, Any] = {
        "status": storage_join.get("status") or "unresolved",
        "kind": storage_join.get("join_kind") or "not_established",
        "readiness": storage_join.get("join_readiness") or "not_ready",
        "source_expressions": list(storage_join.get("source_reference_expressions") or []),
        "target_expressions": list(storage_join.get("target_identity_expressions") or []),
        "target_key_fields": target_fields,
        "candidate_count": int(storage_join.get("candidate_count") or 0),
        "match_basis": basis.get("match_basis"),
        "evidence_ids": list(provenance.get("evidence_ids") or []),
    }
    if physical.get("physical_join_confirmed") is True:
        join["physical_join_confirmed"] = True
        for key in ("method", "condition", "join_condition"):
            if physical.get(key) not in (None, ""):
                join[key] = physical[key]

    result: dict[str, Any] = {
        "relationship_id": rel.get("relationship_id") or declared.get("relationship_id"),
        "kind": declared.get("relationship_kind"),
        "source_field": rel.get("source_field") or declared.get("source_field"),
        "target_object": target.get("fqcn") or declared.get("target_fqcn"),
        "target_name": target.get("name") or declared.get("target_name"),
        "target_field": target_field,
        "cardinality": cardinality.get("value"),
        "stored_as": stored_as,
        "storage_status": storage.get("status") or "not_available",
        "join": {k: v for k, v in join.items() if v not in (None, "", [])},
    }
    ambiguity_count = max(
        len(candidates) if storage.get("status") == "ambiguous" else 0,
        int(storage_join.get("candidate_count") or 0) if storage_join.get("status") == "ambiguous" else 0,
    )
    if ambiguity_count:
        result["ambiguity"] = {
            "status": "ambiguous",
            "candidate_count": ambiguity_count,
            "rule": "Preserve all published candidates; do not silently select one.",
        }
    if include_provenance:
        result["evidence_detail"] = {
            "storage_basis": storage.get("basis"),
            "storage_key_derivations": _storage_key_derivations(rel, True),
            "reference_value_derivations": _reference_correspondences(rel, True),
            "structural_correspondences": list(storage_join.get("structural_correspondences") or []),
            "join_basis": basis,
            "join_diagnostics": list(storage_join.get("diagnostics") or []),
            "declared_provenance": declared.get("provenance"),
            "declared_source_ref": declared.get("source_ref"),
            "physical_mapping": physical,
        }
    return {k: v for k, v in result.items() if v not in (None, "", [])}


def project_data_model_object(
    context: Mapping[str, Any],
    *,
    profile_id: str | None = None,
    profile_fingerprint: str | None = None,
    resolution: Mapping[str, Any] | None = None,
    include_provenance: bool = False,
) -> dict[str, Any]:
    obj = _dict(context.get("object"))
    fields = _list_dicts(context.get("fields"))
    rels_raw = _list_dicts(context.get("relationships"))
    rels_by_field: dict[str, list[dict[str, Any]]] = {}
    for rel in rels_raw:
        field_name = _text(rel.get("source_field"))
        if field_name:
            rels_by_field.setdefault(field_name, []).append(rel)
    rels = [_relationship_projection(r, include_provenance) for r in rels_raw]
    docs = _docs(obj.get("documentation"))
    storage_ids = _list_dicts(context.get("storage_identities"))

    confirmed = [r for r in rels if _dict(r.get("join")).get("status") == "confirmed"]
    executable = [r for r in rels if _dict(r.get("join")).get("readiness") == "executable_storage_join"]
    strongly_supported = [r for r in rels if _dict(r.get("join")).get("status") == "strongly_supported"]
    ambiguous = [r for r in rels if _dict(r.get("join")).get("status") == "ambiguous" or r.get("storage_status") == "ambiguous"]
    unresolved = [r for r in rels if _dict(r.get("join")).get("status") in {"unresolved", "not_available", None}]

    result: dict[str, Any] = {
        "schema_version": "aisl_data_model_api/v2",
        "source_schema_version": context.get("schema_version"),
        "system_id": context.get("system_id"),
        "revision_id": context.get("revision_id"),
        "profile_id": profile_id,
        "profile_fingerprint": profile_fingerprint,
        "object": {
            "id": obj.get("object_id"),
            "name": obj.get("name"),
            "kind": obj.get("type_kind"),
            "fqcn": obj.get("fqcn"),
            "display_name": docs.get("display_name"),
            "description": docs.get("description") or docs.get("summary"),
        },
        "fields": [_field_projection(f, rels_by_field.get(_text(f.get("name")), [])) for f in fields],
        "keys": _key_projection(storage_ids, include_provenance),
        "relationships": rels,
        "summary": {
            "field_count": len(fields),
            "relationship_count": len(rels),
            "confirmed_storage_join_count": len(confirmed),
            "executable_storage_join_count": len(executable),
            "strongly_supported_storage_join_count": len(strongly_supported),
            "ambiguous_relationship_count": len(ambiguous),
            "unresolved_join_count": len(unresolved),
        },
        "storage_context": _dict(context.get("storage_context")),
        "gaps": list(context.get("gaps") or []),
        "interpretation": {
            "storage_join_semantics_are_not_physical_sql_join_claims": True,
            "automatic_join_requires_readiness_executable_storage_join": True,
            "ambiguous_candidates_must_be_preserved": True,
            "not_observed_does_not_mean_system_wide_absence": True,
        },
    }
    if include_provenance and resolution is not None:
        result["object_resolution"] = dict(resolution)
    result["object"] = {k: v for k, v in result["object"].items() if v not in (None, "")}
    for key in ("profile_id", "profile_fingerprint"):
        if result.get(key) in (None, ""):
            result.pop(key, None)
    if not result["gaps"]:
        result.pop("gaps")
    return result


