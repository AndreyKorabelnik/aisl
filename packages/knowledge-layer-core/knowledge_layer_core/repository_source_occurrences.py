from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from prepared_knowledge_runtime.normalization import stable_id

from .interaction_evidence_catalog import interaction_boundary_records


LOCALIZATION_KINDS = frozenset({"exact_span", "declaration", "statement", "section", "file"})


def _positive_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _repo_path(value: Any) -> str | None:
    text = str(value or "").replace("\\", "/").strip()
    if not text or text == "unknown":
        return None
    while text.startswith("./"):
        text = text[2:]
    if text.startswith("/") or "../" in f"/{text}":
        return None
    return text


def _source_ref(
    raw: Mapping[str, Any],
    *,
    path_field: str,
    localization_kind: str,
) -> dict[str, Any] | None:
    path = _repo_path(raw.get(path_field))
    if not path:
        return None
    line_start = _positive_int(raw.get("line_start"))
    line_end = _positive_int(raw.get("line_end"))
    if line_start is not None and line_end is not None and line_end < line_start:
        line_end = None
    if localization_kind not in LOCALIZATION_KINDS:
        raise ValueError(f"unsupported localization_kind: {localization_kind}")
    if line_start is None:
        localization_kind = "file"
        line_end = None
    elif line_end is None:
        line_end = line_start
    return {
        "repository_relative_path": path,
        "localization_kind": localization_kind,
        "line_start": line_start,
        "line_end": line_end,
        "extractor": raw.get("extractor"),
    }


def _iter_direct_source_refs(value: Any, *, localization_kind: str = "exact_span"):
    """Read only explicit published provenance keys; this is not recursive source discovery."""
    if isinstance(value, Mapping):
        direct = value.get("source_ref")
        if isinstance(direct, Mapping):
            item = _source_ref(direct, path_field="repository_relative_path", localization_kind=localization_kind)
            if item:
                yield item
        direct_many = value.get("source_refs")
        if isinstance(direct_many, list):
            for ref in direct_many:
                if not isinstance(ref, Mapping):
                    continue
                if "repository_relative_path" in ref:
                    item = _source_ref(ref, path_field="repository_relative_path", localization_kind=localization_kind)
                elif "file" in ref:
                    item = _source_ref(ref, path_field="file", localization_kind=localization_kind)
                else:
                    item = None
                if item:
                    yield item


def _sql_fact_records(envelope_path: Path, envelope: Mapping[str, Any], fact_type: str) -> list[dict[str, Any]]:
    payload = envelope.get("payload") or {}
    shards = payload.get("fact_shards") or []
    descriptor = next(
        (item for item in shards if isinstance(item, Mapping) and str(item.get("fact_type") or "") == fact_type),
        None,
    )
    if descriptor is None:
        return []
    relative = Path(str(descriptor.get("path") or ""))
    if not str(relative) or relative.is_absolute() or ".." in relative.parts:
        return []
    resolved = (envelope_path.parent / relative).resolve()
    try:
        resolved.relative_to(envelope_path.parent.resolve())
    except ValueError:
        return []
    if not resolved.is_file():
        # Synthetic/unit-test envelopes can legitimately omit sidecar shards.
        return []
    records: list[dict[str, Any]] = []
    with resolved.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            if isinstance(row, dict) and str(row.get("fact_type") or "") == fact_type:
                records.append(row)
    return records


def family_source_refs(
    family: Mapping[str, Any],
    *,
    envelope: Mapping[str, Any] | None,
    envelope_path: Path | None,
    structural_members: Mapping[str, Any],
    repository_files: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Return source refs from official evidence shapes for one Inventory family.

    The function intentionally enumerates known contracts instead of guessing arbitrary
    dictionaries. Missing provenance remains an empty result.
    """
    kind = str(family.get("source_artifact_kind") or "")
    label = str(family.get("family_label") or "")
    family_kind = str(family.get("family_kind") or "")
    refs: list[dict[str, Any]] = []

    if family_kind == "file_extension":
        for item in repository_files:
            if str(item.get("extension") or "<none>") != label:
                continue
            path = _repo_path(item.get("repository_relative_path"))
            if path:
                refs.append({"repository_relative_path": path, "localization_kind": "file", "line_start": None, "line_end": None, "extractor": "repository_structure"})
        return refs

    if family_kind == "structured_file_shape":
        member_ids: set[str] = set()
        for evidence_ref in family.get("evidence_refs") or []:
            if isinstance(evidence_ref, Mapping):
                member_ids.update(str(value) for value in evidence_ref.get("member_ids") or [])
        for member in structural_members.get("members") or []:
            if not isinstance(member, Mapping) or str(member.get("member_id") or "") not in member_ids:
                continue
            path = _repo_path(member.get("repository_relative_path"))
            if path:
                refs.append({"repository_relative_path": path, "localization_kind": "file", "line_start": None, "line_end": None, "extractor": "structured_file_shape"})
        return refs

    if envelope is None:
        return refs

    if kind == "java-type-structure-evidence":
        payload = envelope.get("payload") or {}
        records = payload.get(label) or []
        if isinstance(records, list):
            declared_sections = {
                "type_declarations", "field_declarations", "inheritance_declarations",
                "annotation_declarations", "enum_constant_declarations",
            }
            loc_kind = "declaration" if label in declared_sections else "exact_span"
            for record in records:
                if not isinstance(record, Mapping):
                    continue
                refs.extend(_iter_direct_source_refs(record, localization_kind=loc_kind))
                if label == "source_units":
                    path = _repo_path(record.get("repository_relative_path"))
                    if path:
                        refs.append({"repository_relative_path": path, "localization_kind": "file", "line_start": None, "line_end": None, "extractor": "java_source_unit"})
        return refs

    if kind == "data-model-candidate-evidence":
        profile = envelope.get("candidate_profile") or {}
        for record in profile.get("evidence") or []:
            if not isinstance(record, Mapping):
                continue
            item = _source_ref(record, path_field="path", localization_kind="exact_span")
            if item:
                refs.append(item)
        return refs

    if kind == "interaction-boundary-evidence" and envelope_path is not None:
        for record in interaction_boundary_records(envelope_path, envelope):
            for evidence_ref in record.get("evidence_refs") or []:
                if not isinstance(evidence_ref, Mapping):
                    continue
                item = _source_ref(evidence_ref, path_field="file", localization_kind="exact_span")
                if item:
                    refs.append(item)
        return refs

    if kind == "sql-analysis" and envelope_path is not None:
        for record in _sql_fact_records(envelope_path, envelope, label):
            item = _source_ref(record, path_field="file", localization_kind="statement")
            if item:
                refs.append(item)
            for evidence_ref in record.get("evidence") or []:
                if isinstance(evidence_ref, Mapping):
                    evidence_item = _source_ref(evidence_ref, path_field="file", localization_kind="statement")
                    if evidence_item:
                        refs.append(evidence_item)
        return refs

    payload = envelope.get("payload") or {}
    records = payload.get(label) if isinstance(payload, Mapping) else None
    if isinstance(records, list):
        for record in records:
            if isinstance(record, Mapping):
                refs.extend(_iter_direct_source_refs(record))
    elif isinstance(records, Mapping):
        refs.extend(_iter_direct_source_refs(records))

    # Some official evidence families publish direct records outside `payload`.
    for top_level_key in ("storage_accesses", "storage_reads", "storage_writes", "storage_records", "storage_references", "storage_key_lineage"):
        if label != top_level_key:
            continue
        for record in envelope.get(top_level_key) or []:
            if isinstance(record, Mapping):
                refs.extend(_iter_direct_source_refs(record))
    return refs


def annotate_gap_localization(
    coverage_gaps: Sequence[Mapping[str, Any]],
    source_occurrence_links: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Describe the strongest *observed* localization scope for every gap.

    This deliberately does not manufacture a source location for analysis-level gaps.
    """
    localized = {
        str(item.get("object_id") or "")
        for item in source_occurrence_links
        if str(item.get("object_kind") or "") == "coverage_gap"
    }
    rows: list[dict[str, Any]] = []
    for raw in coverage_gaps:
        item = dict(raw)
        gap_id = str(item.get("gap_occurrence_id") or "")
        if gap_id in localized:
            item["localization_scope_kind"] = "source_occurrence"
            item["localization_status"] = "localized"
        elif str(item.get("gap_kind") or "") == "evidence_coverage_gap" and item.get("source_artifact_id"):
            item["localization_scope_kind"] = "evidence_artifact"
            item["localization_status"] = "not_source_localized"
        else:
            item["localization_scope_kind"] = "unresolved"
            item["localization_status"] = "unresolved"
        rows.append(item)
    return rows


def build_source_occurrence_graph(
    *,
    repo_id: str,
    families: Sequence[Mapping[str, Any]],
    candidates: Sequence[Mapping[str, Any]],
    coverage_gaps: Sequence[Mapping[str, Any]],
    structural_members: Mapping[str, Any],
    repository_files: Sequence[Mapping[str, Any]],
    envelopes_by_identity: Mapping[tuple[str, str], Mapping[str, Any]],
    envelope_paths_by_identity: Mapping[tuple[str, str], Path],
) -> dict[str, Any]:
    file_sha = {
        str(item.get("repository_relative_path") or ""): item.get("sha256")
        for item in repository_files
        if item.get("repository_relative_path")
    }
    occurrences: dict[str, dict[str, Any]] = {}
    links: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    family_occurrences: dict[str, list[str]] = defaultdict(list)

    def add_occurrence(ref: Mapping[str, Any], source_context: Mapping[str, Any]) -> str | None:
        path = _repo_path(ref.get("repository_relative_path"))
        if not path:
            return None
        line_start = _positive_int(ref.get("line_start"))
        line_end = _positive_int(ref.get("line_end"))
        if line_start is None:
            line_end = None
        elif line_end is None:
            line_end = line_start
        localization_kind = str(ref.get("localization_kind") or ("exact_span" if line_start else "file"))
        if localization_kind not in LOCALIZATION_KINDS:
            localization_kind = "exact_span" if line_start else "file"
        content_sha256 = file_sha.get(path)
        occurrence_id = stable_id(
            "repository_source_occurrence", repo_id, path, localization_kind,
            line_start or "", line_end or "", content_sha256 or "",
        )
        provenance = {
            "source_artifact_kind": source_context.get("source_artifact_kind"),
            "source_schema_version": source_context.get("source_schema_version"),
            "extractor": ref.get("extractor"),
        }
        row = occurrences.setdefault(occurrence_id, {
            "occurrence_id": occurrence_id,
            "repository_relative_path": path,
            "localization_kind": localization_kind,
            "line_start": line_start,
            "line_end": line_end,
            "content_sha256": content_sha256,
            "provenance": [],
        })
        if provenance not in row["provenance"]:
            row["provenance"].append(provenance)
        return occurrence_id

    def add_link(object_kind: str, object_id: str, occurrence_id: str, role: str, basis: Mapping[str, Any]) -> None:
        key = (object_kind, object_id, occurrence_id, role)
        links.setdefault(key, {
            "link_id": stable_id("repository_inventory_object_occurrence", repo_id, *key),
            "object_kind": object_kind,
            "object_id": object_id,
            "occurrence_id": occurrence_id,
            "linkage_role": role,
            "basis": dict(basis),
        })

    for family in families:
        identity = (str(family.get("source_artifact_kind") or ""), str(family.get("source_schema_version") or ""))
        refs = family_source_refs(
            family,
            envelope=envelopes_by_identity.get(identity),
            envelope_path=envelope_paths_by_identity.get(identity),
            structural_members=structural_members,
            repository_files=repository_files,
        )
        seen: set[str] = set()
        for ref in refs:
            occurrence_id = add_occurrence(ref, family)
            if not occurrence_id or occurrence_id in seen:
                continue
            seen.add(occurrence_id)
            family_occurrences[str(family["family_id"])].append(occurrence_id)
            add_link("structural_family", str(family["family_id"]), occurrence_id, "observed_family_occurrence", {"evidence_refs": family.get("evidence_refs") or []})

    family_by_id = {str(item.get("family_id") or ""): item for item in families}
    for member in structural_members.get("members") or []:
        if not isinstance(member, Mapping):
            continue
        family_id = str(member.get("family_id") or "")
        family = family_by_id.get(family_id)
        if family is None:
            continue
        path = _repo_path(member.get("repository_relative_path"))
        if not path:
            continue
        occurrence_id = add_occurrence({
            "repository_relative_path": path,
            "localization_kind": "file",
            "extractor": "structured_file_shape",
        }, family)
        if occurrence_id:
            add_link("structural_member", str(member.get("member_id") or ""), occurrence_id, "observed_member_occurrence", {"family_id": family_id})

    for candidate in candidates:
        family_id = str(candidate.get("family_id") or "")
        for occurrence_id in family_occurrences.get(family_id, []):
            add_link("discovery_candidate", str(candidate["candidate_id"]), occurrence_id, "candidate_family_occurrence", {"family_id": family_id, "discovery_kind": candidate.get("discovery_kind")})


    for gap in coverage_gaps:
        gap_id = str(gap["gap_occurrence_id"])
        family_id = str(gap.get("family_id") or "")
        if family_id:
            for occurrence_id in family_occurrences.get(family_id, []):
                add_link("coverage_gap", gap_id, occurrence_id, "related_family_occurrence", {"family_id": family_id, "gap_kind": gap.get("gap_kind")})

        # Coverage diagnostics may publish explicit Core-owned provenance. Read only
        # source_ref/source_refs keys; do not infer locations from messages or paths.
        evidence_ref = next((item for item in gap.get("evidence_refs") or [] if isinstance(item, Mapping)), {})
        gap_context = {
            "source_artifact_kind": evidence_ref.get("artifact_kind") or (gap.get("subject_id") if gap.get("subject_kind") == "evidence" else None),
            "source_schema_version": evidence_ref.get("schema_version"),
        }
        for diagnostic in gap.get("diagnostics") or []:
            if not isinstance(diagnostic, Mapping):
                continue
            for ref in _iter_direct_source_refs(diagnostic):
                occurrence_id = add_occurrence(ref, gap_context)
                if occurrence_id:
                    add_link("coverage_gap", gap_id, occurrence_id, "diagnostic_source_occurrence", {"gap_kind": gap.get("gap_kind"), "source_artifact_id": gap.get("source_artifact_id")})

    occurrence_rows = sorted(occurrences.values(), key=lambda item: (item["repository_relative_path"], item.get("line_start") or 0, item.get("line_end") or 0, item["occurrence_id"]))
    for row in occurrence_rows:
        row["provenance"].sort(key=lambda item: (str(item.get("source_artifact_kind") or ""), str(item.get("source_schema_version") or ""), str(item.get("extractor") or "")))
    link_rows = sorted(links.values(), key=lambda item: (item["object_kind"], item["object_id"], item["occurrence_id"], item["linkage_role"]))
    return {
        "schema_version": "repository-source-occurrence/v1",
        "occurrences": occurrence_rows,
        "links": link_rows,
        "family_occurrence_ids": {key: sorted(set(value)) for key, value in sorted(family_occurrences.items())},
    }
