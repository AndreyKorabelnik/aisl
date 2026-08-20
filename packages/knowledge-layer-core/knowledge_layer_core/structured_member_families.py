from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
from typing import Any, Mapping, Sequence

from prepared_knowledge_runtime.normalization import stable_id


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _feature_set(member: Mapping[str, Any]) -> frozenset[tuple[str, str]]:
    """Use shallow structural paths for family identity; deeper paths remain variant detail."""
    features: set[tuple[str, str]] = set()
    for row in member.get("path_observations") or []:
        if not isinstance(row, Mapping):
            continue
        path = str(row.get("path") or "")
        value_type = str(row.get("value_type") or "")
        if not path or not value_type:
            continue
        depth = 0 if path == "/" else path.count("/")
        if depth <= 2:
            features.add((path, value_type))
    if not features:
        features.add(("/", str(member.get("root_type") or "unknown")))
    return frozenset(features)


def _similarity(left: frozenset[tuple[str, str]], right: frozenset[tuple[str, str]]) -> float:
    union = left | right
    if not union:
        return 1.0
    return len(left & right) / len(union)


def _components(members: Sequence[Mapping[str, Any]], *, threshold: float = 0.60) -> list[list[int]]:
    features = [_feature_set(item) for item in members]
    by_syntax: dict[str, list[int]] = defaultdict(list)
    for index, member in enumerate(members):
        by_syntax[str(member.get("syntax") or "unknown")].append(index)
    components: list[list[int]] = []
    for syntax in sorted(by_syntax):
        indices = by_syntax[syntax]
        adjacency: dict[int, set[int]] = {idx: set() for idx in indices}
        for pos, left in enumerate(indices):
            for right in indices[pos + 1:]:
                if _similarity(features[left], features[right]) >= threshold:
                    adjacency[left].add(right)
                    adjacency[right].add(left)
        unseen = set(indices)
        while unseen:
            start = min(unseen, key=lambda idx: str(members[idx].get("member_id") or ""))
            stack = [start]
            group: list[int] = []
            unseen.remove(start)
            while stack:
                current = stack.pop()
                group.append(current)
                for neighbor in sorted(adjacency[current], key=lambda idx: str(members[idx].get("member_id") or ""), reverse=True):
                    if neighbor in unseen:
                        unseen.remove(neighbor)
                        stack.append(neighbor)
            components.append(sorted(group, key=lambda idx: str(members[idx].get("member_id") or "")))
    return components


def derive_structural_member_families(repo_id: str, envelope: Mapping[str, Any]) -> dict[str, Any]:
    if (str(envelope.get("artifact_kind") or ""), str(envelope.get("schema_version") or "")) != (
        "structured-file-shape-evidence", "structured-file-shape-evidence/v1"
    ):
        raise ValueError("structured member derivation requires structured-file-shape-evidence/v1")
    members = [dict(item) for item in envelope.get("members") or [] if isinstance(item, Mapping)]
    members.sort(key=lambda item: (str(item.get("syntax") or ""), str(item.get("repository_relative_path") or ""), str(item.get("member_id") or "")))
    if not members:
        return {"evaluation_status": "evaluated", "families": [], "members": [], "diagnostics": []}

    family_rows: list[dict[str, Any]] = []
    member_rows: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []

    for group in _components(members):
        group_members = [members[index] for index in group]
        syntax = str(group_members[0].get("syntax") or "unknown")
        feature_counter: Counter[tuple[str, str]] = Counter()
        shape_counter: Counter[str] = Counter()
        state_counter: Counter[tuple[str, str, str]] = Counter()
        cardinality_by_path: dict[str, list[int]] = defaultdict(list)
        for member in group_members:
            feature_counter.update(_feature_set(member))
            shape_counter[str(member.get("structure_signature") or "unknown")] += 1
            for row in member.get("state_observations") or []:
                if isinstance(row, Mapping):
                    state_counter[(str(row.get("path") or ""), str(row.get("value_type") or ""), str(row.get("state") or ""))] += 1
            for row in member.get("cardinality_observations") or []:
                if isinstance(row, Mapping) and isinstance(row.get("length"), int):
                    cardinality_by_path[str(row.get("path") or "")].append(int(row["length"]))
        member_count = len(group_members)
        consensus = sorted((path, value_type) for (path, value_type), count in feature_counter.items() if count * 2 >= member_count)
        family_material = {"repo_id": repo_id, "syntax": syntax, "consensus_features": consensus}
        family_id = stable_id("repository_structured_family", repo_id, hashlib.sha256(_canonical(family_material).encode("utf-8")).hexdigest())
        dominant_signature, dominant_count = sorted(shape_counter.items(), key=lambda item: (-item[1], item[0]))[0]

        family_rows.append({
            "family_id": family_id,
            "family_kind": "structured_file_shape",
            "family_label": f"{syntax}-shape-{family_id[-12:]}",
            "syntax": syntax,
            "occurrence_count": member_count,
            "shape_count": len(shape_counter),
            "dominant_structure_signature": dominant_signature,
            "dominant_structure_count": dominant_count,
            "dominant_structure_rate": round(dominant_count / member_count, 6),
            "consensus_path_types": [{"path": path, "value_type": value_type, "member_count": feature_counter[(path, value_type)]} for path, value_type in consensus],
            "member_ids": [str(item.get("member_id") or "") for item in group_members],
            "source_artifact_id": envelope.get("artifact_id"),
            "source_content_fingerprint": envelope.get("content_fingerprint"),
            "claim_boundary": "family membership is deterministic structural similarity over official observed member descriptors; no business or semantic equivalence is asserted",
        })

        shape_counts = dict(shape_counter)
        for member in group_members:
            roles: list[str] = []
            structure_signature = str(member.get("structure_signature") or "unknown")
            if structure_signature == dominant_signature:
                roles.append("dominant_structure")
            else:
                roles.append("rare_structure")
            if bool(member.get("observation_truncated")):
                roles.append("partial_observation")

            minority_states: list[dict[str, Any]] = []
            for row in member.get("state_observations") or []:
                if not isinstance(row, Mapping):
                    continue
                token = (str(row.get("path") or ""), str(row.get("value_type") or ""), str(row.get("state") or ""))
                count = state_counter[token]
                if count * 2 < member_count:
                    minority_states.append({
                        "path": token[0], "value_type": token[1], "state": token[2],
                        "family_member_count": count, "family_rate": round(count / member_count, 6),
                    })
            if minority_states:
                roles.append("minority_state")

            cardinality_extremes: list[dict[str, Any]] = []
            for row in member.get("cardinality_observations") or []:
                if not isinstance(row, Mapping) or not isinstance(row.get("length"), int):
                    continue
                path = str(row.get("path") or "")
                length = int(row["length"])
                values = cardinality_by_path.get(path) or []
                if not values:
                    continue
                min_value, max_value = min(values), max(values)
                role = None
                if length == min_value and min_value < max_value:
                    role = "minimum"
                if length == max_value and max_value > min_value:
                    role = "maximum" if role is None else "minimum_and_maximum"
                if role:
                    cardinality_extremes.append({"path": path, "length": length, "family_min": min_value, "family_max": max_value, "role": role})
            if cardinality_extremes:
                roles.append("cardinality_extreme")

            member_rows.append({
                "family_id": family_id,
                "member_id": member.get("member_id"),
                "repository_relative_path": member.get("repository_relative_path"),
                "content_identity": dict(member.get("content_identity") or {}),
                "syntax": syntax,
                "parse_status": member.get("parse_status") or "unknown",
                "structure_signature": structure_signature,
                "variant_signature": member.get("variant_signature"),
                "structure_family_occurrence_count": shape_counts.get(structure_signature, 0),
                "structural_size": dict(member.get("structural_size") or {}),
                "variant_roles": sorted(set(roles)),
                "minority_states": sorted(minority_states, key=lambda item: (item["path"], item["value_type"], item["state"])),
                "cardinality_extremes": sorted(cardinality_extremes, key=lambda item: item["path"]),
                "observation_truncated": bool(member.get("observation_truncated")),
                "provenance": dict(member.get("provenance") or {}),
            })

    family_rows.sort(key=lambda item: (item["syntax"], item["family_id"]))
    member_rows.sort(key=lambda item: (item["family_id"], item["repository_relative_path"], str(item["member_id"])))
    return {"evaluation_status": "evaluated", "families": family_rows, "members": member_rows, "diagnostics": diagnostics}
