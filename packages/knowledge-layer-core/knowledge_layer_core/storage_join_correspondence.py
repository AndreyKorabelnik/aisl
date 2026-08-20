from __future__ import annotations

import json
from typing import Any, Mapping

from .key_expression_correspondence import canonical_key_expression_node, infer_key_fields_from_expression_tree


def _json_value(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def record_properties(payload: Any) -> dict[str, Any]:
    value = _json_value(payload, {})
    if not isinstance(value, Mapping):
        return {}
    props = value.get("properties")
    return dict(props) if isinstance(props, Mapping) else {}


def source_refs(payload: Any) -> list[dict[str, Any]]:
    value = _json_value(payload, {})
    if not isinstance(value, Mapping):
        return []
    refs = value.get("source_refs")
    if refs is None:
        props = value.get("properties")
        if isinstance(props, Mapping):
            refs = props.get("source_refs")
    return [dict(item) for item in refs or () if isinstance(item, Mapping)]


def structural_reference_key_correspondences(
    derivations: list[dict[str, Any]],
    target_records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return exact syntax-derived reference-value ↔ target-identity correspondences.

    This is the canonical KLC matcher shared by logical-storage mapping and
    downstream attribute-extension knowledge. It intentionally performs no
    name similarity, domain-specific normalization, physical-table inference,
    SQL inference or fallback guessing.
    """
    matches: list[dict[str, Any]] = []
    for derivation in derivations:
        dprops = record_properties(derivation.get("payload_json"))
        d_tree = dprops.get("composed_reference_value_expression_tree")
        if not isinstance(d_tree, Mapping):
            continue
        for target in target_records:
            tprops = record_properties(target.get("payload_json"))
            t_tree = tprops.get("storage_key_expression_tree")
            if not isinstance(t_tree, Mapping):
                continue
            key_fields = infer_key_fields_from_expression_tree(t_tree)
            if not key_fields:
                continue
            left = canonical_key_expression_node(d_tree, key_fields)
            right = canonical_key_expression_node(t_tree, key_fields)
            if left is None or right is None or left != right:
                continue
            matches.append({
                "match_basis": "exact_structural_expression_signature",
                "reference_observation_id": derivation.get("observation_id"),
                "target_key_observation_id": target.get("observation_id"),
                "target_key_fields": list(key_fields),
                "reference_expression": derivation.get("composed_reference_value_expression"),
                "target_key_expression": target.get("storage_key_expression"),
                "canonical_signature": left,
                "source_refs": source_refs(derivation.get("payload_json")),
                "target_source_refs": source_refs(target.get("payload_json")),
            })
    return matches
