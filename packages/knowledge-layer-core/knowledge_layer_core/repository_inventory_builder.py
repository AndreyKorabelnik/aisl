from __future__ import annotations

from collections import defaultdict
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any, Mapping, Sequence
import uuid

from prepared_knowledge_runtime.contracts import KnowledgeLayerManifest
from prepared_knowledge_runtime.database import connect_database, initialize_schema
from prepared_knowledge_runtime.io import write_json
from prepared_knowledge_runtime.normalization import stable_id

from .interaction_evidence_catalog import interaction_boundary_records
from .materialization_contracts import CURRENT_MATERIALIZATIONS
from .metrics import canonical_json, utc_now
from .publication import publish_directory_atomic, remove_path
from .structured_member_families import derive_structural_member_families
from .repository_source_occurrences import annotate_gap_localization, build_source_occurrence_graph
from .repository_inventory_schema import (
    REPOSITORY_INVENTORY_DATABASE,
    REPOSITORY_INVENTORY_DDL,
    REPOSITORY_INVENTORY_SCHEMA_VERSION,
)
from .version import __version__



def _repository_inventory_evaluation_policy() -> dict[str, Any]:
    definition = next(
        item for item in CURRENT_MATERIALIZATIONS
        if item.materialization_id == "repository-inventory"
    )
    required = sorted(item.artifact_kind for item in definition.required_evidence)
    produce_if_missing = sorted(
        item.artifact_kind
        for item in definition.optional_evidence
        if item.production_policy == "produce_if_missing"
    )
    existing_only = sorted(
        item.artifact_kind
        for item in definition.optional_evidence
        if item.production_policy == "existing_only"
    )
    return {
        "mode": "bounded_default",
        "required": required,
        "produce_if_missing": produce_if_missing,
        "existing_only": existing_only,
        "claim": "bounded preflight evidence is produced according to the official materialization contract; deeper optional evidence is consumed only when already available",
    }


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"evidence envelope must be an object: {path}")
    return value


def _source_id(envelope: Mapping[str, Any]) -> str:
    return str((envelope.get("source_snapshot") or {}).get("source_id") or "").strip()


def _positive_metrics(coverage: Mapping[str, Any]) -> dict[str, int | float | str | bool]:
    out: dict[str, int | float | str | bool] = {}
    for key, value in coverage.items():
        if isinstance(value, (bool, int, float, str)):
            out[str(key)] = value
    return out


def _descriptor_labels(envelope: Mapping[str, Any]) -> set[str]:
    labels: set[str] = set()
    payload = envelope.get("payload") or {}
    if isinstance(payload, Mapping):
        for key in payload:
            labels.add(str(key).lower())
        for value in payload.values():
            if isinstance(value, list):
                for item in value:
                    if not isinstance(item, Mapping):
                        continue
                    for key in ("fact_type", "artifact_name", "section", "record_kind", "path", "relative_path"):
                        raw = item.get(key)
                        if raw:
                            labels.add(str(raw).lower())
    return labels


def _signal_count(coverage: Mapping[str, Any]) -> int:
    """Return a generic positive observed-count signal from an official coverage map.

    This helper intentionally contains no KLC concept semantics. It is used only to
    summarize observed Core evidence when a payload has no explicit family records.
    """
    positive: list[int] = []
    excluded_tokens = (
        "file_count", "files_", "gap", "failed", "error", "missing",
        "unreadable", "unsupported", "ambiguous", "unresolved",
    )
    for key, value in coverage.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        key_l = str(key).lower()
        if any(token in key_l for token in excluded_tokens):
            continue
        if key_l.endswith("_count") or key_l.endswith("_total") or key_l == "score":
            if value > 0:
                positive.append(int(value))
    return max(positive, default=0)


def _structural_salience_score(*, count: int, coverage_status: str, unsupported: bool = False, diagnostics: int = 0) -> float:
    """Repository-local salience only; this is deliberately *not* a novelty score.

    True novelty requires comparison against other observed structural fingerprints and
    therefore belongs to downstream mining/portfolio analysis, not one repository run.
    """
    repetition = min(35.0, 8.0 * math.log2(max(1, count) + 1))
    coverage = 20.0 if coverage_status == "complete" else 10.0 if coverage_status == "partial" else 5.0
    frontier = 30.0 if unsupported else 10.0
    diagnostic_signal = min(15.0, diagnostics * 2.0)
    return round(min(100.0, repetition + coverage + frontier + diagnostic_signal), 3)


def _evidence_families(repo_id: str, envelope: Mapping[str, Any]) -> list[dict[str, Any]]:
    kind = str(envelope.get("artifact_kind") or "unknown-evidence")
    version = str(envelope.get("schema_version") or "unknown")
    coverage = envelope.get("coverage") or {}
    diagnostics = [item for item in (envelope.get("diagnostics") or []) if isinstance(item, Mapping)]
    payload = envelope.get("payload") or {}
    sections: list[tuple[str, int, dict[str, Any]]] = []
    if isinstance(payload, Mapping):
        for section_name, value in payload.items():
            if not isinstance(value, list):
                continue
            if value and all(isinstance(item, Mapping) and (item.get("fact_type") or item.get("section") or item.get("artifact_name")) for item in value):
                for item in value:
                    assert isinstance(item, Mapping)
                    label = str(item.get("fact_type") or item.get("section") or item.get("artifact_name") or section_name)
                    count = int(item.get("record_count") or item.get("records_count") or 1)
                    sections.append((label, count, {"payload_section": section_name, "descriptor": {str(k): v for k, v in item.items() if str(k) in {"fact_type", "section", "artifact_name", "record_count", "records_count", "format"}}}))
            else:
                sections.append((str(section_name), len(value), {"payload_section": section_name}))
    if not sections:
        sections.append((kind, max(1, _signal_count(coverage)), {"payload_section": None}))
    family_kind_map = {
        "java-type-structure-evidence": "java_structure",
        "sql-analysis": "sql_structure",
        "interaction-boundary-evidence": "interaction_boundary_structure",
        "reference-data-evidence": "reference_data_structure",
        "persistence-lineage-evidence": "persistence_structure",
        "storage-usage-evidence": "storage_usage_structure",
        "model-storage-evidence": "model_storage_structure",
        "java-persistence-mapping-evidence": "persistence_mapping_structure",
        "system-description-evidence": "system_structure",
        "value-flow-evidence": "value_flow_structure",
        "data-model-candidate-evidence": "candidate_signal_structure",
    }
    result: list[dict[str, Any]] = []
    for label, count, section_metrics in sections:
        if count <= 0:
            count = _signal_count(coverage)
        family_id = stable_id("repository_inventory_family", repo_id, kind, version, label)
        result.append({
            "family_id": family_id,
            "family_kind": family_kind_map.get(kind, "official_evidence_structure"),
            "family_label": label,
            "source_artifact_kind": kind,
            "source_schema_version": version,
            "count": max(0, count),
            "structural_salience_score": _structural_salience_score(
                count=max(1, count),
                coverage_status=str(coverage.get("coverage_status") or "unknown"),
                diagnostics=len(diagnostics),
            ),
            "discovery_kind": "none", "discovery_basis": {"reason": "discovery_classification_pending"},
            "observed_metrics": {**_positive_metrics(coverage), **section_metrics, "record_count": max(0, count)},
            "descriptor_labels": [label.lower()],
            "evidence_refs": [{
                "artifact_id": envelope.get("artifact_id"),
                "artifact_kind": kind,
                "schema_version": version,
                "content_fingerprint": envelope.get("content_fingerprint"),
                "observed_section": label,
            }],
        })
    return result


def _extension_families(repo_id: str, structure: Mapping[str, Any]) -> list[dict[str, Any]]:
    out = []
    outside_frontier = {str(item.get("extension")) for item in structure.get("outside_analyzer_frontier_extension_families") or [] if isinstance(item, Mapping)}
    for item in structure.get("extension_inventory") or []:
        if not isinstance(item, Mapping):
            continue
        ext = str(item.get("extension") or "<none>")
        count = int(item.get("file_count") or 0)
        is_outside_frontier = ext in outside_frontier or int(item.get("outside_analyzer_frontier_file_count") or 0) > 0 and int(item.get("analyzer_eligible_file_count") or 0) == 0
        out.append({
            "family_id": stable_id("repository_inventory_extension_family", repo_id, ext),
            "family_kind": "file_extension",
            "family_label": ext,
            "source_artifact_kind": "repository-structure-evidence",
            "source_schema_version": "repository-structure-evidence/v1",
            "count": count,
            "structural_salience_score": _structural_salience_score(count=count, coverage_status="complete", unsupported=is_outside_frontier),
            "discovery_kind": "none", "discovery_basis": {"reason": "discovery_classification_pending"},
            "observed_metrics": {
                "file_count": count,
                "analyzer_eligible_file_count": int(item.get("analyzer_eligible_file_count") or 0),
                "outside_analyzer_frontier_file_count": int(item.get("outside_analyzer_frontier_file_count") or 0),
                "outside_analyzer_frontier_extension_family": is_outside_frontier,
            },
            "descriptor_labels": [],
            "evidence_refs": [{"artifact_id": structure.get("artifact_id"), "artifact_kind": "repository-structure-evidence", "schema_version": "repository-structure-evidence/v1", "content_fingerprint": structure.get("content_fingerprint")}],
        })
    return out


def _source_metadata(evidence_items: Sequence[Mapping[str, Any]], envelopes: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    for item, envelope in zip(evidence_items, envelopes):
        if (str(envelope.get("artifact_kind") or ""), str(envelope.get("schema_version") or "")) != ("repository-structure-evidence", "repository-structure-evidence/v1"):
            continue
        metadata = item.get("source_metadata") or {}
        if isinstance(metadata, Mapping):
            return {str(key): value for key, value in metadata.items() if value is not None}
    return {}


def _composition(files: Sequence[Mapping[str, Any]], extensions: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    ext_counts = {str(item.get("extension") or "<none>"): int(item.get("file_count") or 0) for item in extensions}
    language_exts = {
        "java": {".java"}, "kotlin": {".kt", ".kts"}, "sql": {".sql"}, "python": {".py"},
        "javascript": {".js", ".jsx"}, "typescript": {".ts", ".tsx"}, "go": {".go"},
        "csharp": {".cs"}, "cpp": {".cpp", ".cc", ".cxx", ".h", ".hpp"}, "scala": {".scala"},
    }
    languages = []
    for language, exts in language_exts.items():
        count = sum(ext_counts.get(ext, 0) for ext in exts)
        if count:
            languages.append({"language": language, "file_count": count, "basis": {"extensions": sorted(ext for ext in exts if ext_counts.get(ext, 0))}})
    languages.sort(key=lambda item: (-item["file_count"], item["language"]))
    return {
        "file_count": len(files),
        "extension_family_count": len(extensions),
        "total_bytes": sum(int(item.get("byte_size") or 0) for item in files),
        "analyzer_eligible_file_count": sum(1 for item in files if bool(item.get("analyzer_eligible"))),
        "outside_analyzer_frontier_file_count": sum(1 for item in files if not bool(item.get("analyzer_eligible"))),
        "languages": languages,
    }


def _technology_signals(repo_id: str, files: Sequence[Mapping[str, Any]], structure_artifact_id: str) -> list[dict[str, Any]]:
    paths = {str(item.get("repository_relative_path") or "").replace("\\", "/").lower() for item in files}
    names = {Path(path).name.lower() for path in paths}
    rules = [
        ("build", "maven", lambda: "pom.xml" in names, ["pom.xml"]),
        ("build", "gradle", lambda: bool({"build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts"} & names), sorted({"build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts"} & names)),
        ("build", "node-package", lambda: "package.json" in names, ["package.json"]),
        ("build", "python-package", lambda: bool({"pyproject.toml", "setup.py", "setup.cfg"} & names), sorted({"pyproject.toml", "setup.py", "setup.cfg"} & names)),
        ("build", "go-modules", lambda: "go.mod" in names, ["go.mod"]),
        ("build", "cargo", lambda: "cargo.toml" in names, ["cargo.toml"]),
        ("container", "docker", lambda: any(name == "dockerfile" or name.startswith("dockerfile.") for name in names), sorted(name for name in names if name == "dockerfile" or name.startswith("dockerfile."))),
        ("deployment", "helm", lambda: "chart.yaml" in names, ["Chart.yaml"]),
        ("api_spec", "openapi", lambda: any("openapi" in name or name.startswith("swagger.") for name in names), sorted(name for name in names if "openapi" in name or name.startswith("swagger."))),
    ]
    out = []
    for category, technology, predicate, markers in rules:
        if not predicate():
            continue
        out.append({
            "technology_id": stable_id("repository_inventory_technology", repo_id, category, technology),
            "category": category, "technology": technology, "status": "strongly_supported",
            "confidence": "strongly_supported_inference",
            "basis": {"observed_file_markers": markers, "source_artifact_id": structure_artifact_id},
        })
    return out


def _evaluation_phase(envelopes: Sequence[Mapping[str, Any]]) -> tuple[str, dict[str, Any]]:
    policy = _repository_inventory_evaluation_policy()
    available = {str(env.get("artifact_kind") or "") for env in envelopes}
    deep = sorted(available & set(policy["existing_only"]))
    phase = "post_analysis" if deep else "preflight"
    return phase, {
        "basis": "actual_official_evidence_set",
        "deep_evidence_artifact_kinds": deep,
        "bounded_evidence_artifact_kinds": sorted(available - set(deep)),
        "interpretation": "post_analysis means the snapshot includes at least one deeper existing-only evidence product; preflight means it is based only on required/bounded evidence",
    }


def _normalized_completeness_status(raw: str, *, diagnostics: Sequence[Mapping[str, Any]] = ()) -> str:
    value = str(raw or "unknown").strip().lower()
    if value in {"complete", "completed", "supported"}:
        return "supported_with_gaps" if diagnostics else "complete"
    if value in {"partial", "supported_with_gaps"}:
        return "partial" if value == "partial" else "supported_with_gaps"
    if value in {"unsupported", "failed"}:
        return "unsupported"
    if value in {"not_evaluated", "not_assessed", "unknown", ""}:
        return "not_evaluated"
    if value == "ignored_with_reason":
        return value
    return "supported_with_gaps"


def _apply_discovery_classification(families: Sequence[dict[str, Any]]) -> None:
    """Classify only Core-level discovery states supported by observed frontier facts.

    Repository-local salience is never promoted to structural novelty. Cross-repository
    novelty is a downstream Miner/Portfolio concern based on structural fingerprints.
    """
    for family in families:
        metrics = family.get("observed_metrics") or {}
        outside_frontier = bool(metrics.get("outside_analyzer_frontier_extension_family"))
        salience = float(family.get("structural_salience_score") or 0.0)
        if outside_frontier:
            kind = "unknown_primitive"
            basis = {
                "reason": "observed_structure_is_outside_official_analyzer_frontier",
                "observed_metrics": metrics,
            }
        else:
            kind = "none"
            basis = {
                "reason": "no_core_level_unknown_classification",
                "structural_salience_score": salience,
                "novelty_ownership": "downstream_cross_repository_mining",
            }
        family["discovery_kind"] = kind
        family["discovery_basis"] = basis


def _completeness_rows(repo_id: str, structure: Mapping[str, Any], envelopes: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    structure_diagnostics = [dict(item) for item in structure.get("diagnostics") or [] if isinstance(item, Mapping)]
    rows.append({
        "completeness_id": stable_id("repository_inventory_completeness", repo_id, "repository_landscape", "repository"),
        "subject_kind": "repository_landscape", "subject_id": "repository",
        "status": _normalized_completeness_status(str((structure.get("coverage") or {}).get("coverage_status") or "unknown"), diagnostics=structure_diagnostics),
        "evidence_evaluation_status": "evaluated",
        "basis": {"artifact_id": structure.get("artifact_id"), "coverage": _positive_metrics(structure.get("coverage") or {})},
        "diagnostics": structure_diagnostics,
    })
    by_kind = {str(env.get("artifact_kind") or ""): env for env in envelopes}
    for kind in sorted(by_kind):
        env = by_kind[kind]
        diagnostics = [dict(item) for item in env.get("diagnostics") or [] if isinstance(item, Mapping)]
        raw = str((env.get("coverage") or {}).get("coverage_status") or "unknown")
        rows.append({
            "completeness_id": stable_id("repository_inventory_completeness", repo_id, "evidence", kind),
            "subject_kind": "evidence", "subject_id": kind,
            "status": _normalized_completeness_status(raw, diagnostics=diagnostics),
            "evidence_evaluation_status": "evaluated",
            "basis": {"artifact_id": env.get("artifact_id"), "schema_version": env.get("schema_version"), "coverage": _positive_metrics(env.get("coverage") or {})},
            "diagnostics": diagnostics,
        })
    return rows


def _coverage_gap_rows(repo_id: str, envelopes: Sequence[Mapping[str, Any]], candidates: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for env in envelopes:
        kind = str(env.get("artifact_kind") or "")
        coverage_status = str((env.get("coverage") or {}).get("coverage_status") or "unknown")
        diagnostics = [dict(item) for item in env.get("diagnostics") or [] if isinstance(item, Mapping)]
        if coverage_status in {"partial", "unsupported", "failed"}:
            rows.append({
                "gap_occurrence_id": stable_id("repository_inventory_gap", repo_id, "evidence_coverage", kind, coverage_status),
                "gap_kind": "evidence_coverage_gap", "subject_kind": "evidence", "subject_id": kind,
                "discovery_kind": "none", "coverage_status": _normalized_completeness_status(coverage_status, diagnostics=diagnostics),
                "relevance_status": "repository_landscape", "family_id": None, "source_artifact_id": env.get("artifact_id"),
                "evidence_refs": [{"artifact_id": env.get("artifact_id"), "artifact_kind": kind, "schema_version": env.get("schema_version"), "content_fingerprint": env.get("content_fingerprint")}],
                "diagnostics": diagnostics, "basis": {"observed_coverage": _positive_metrics(env.get("coverage") or {})},
            })
    for item in candidates:
        if str(item.get("discovery_kind") or "none") != "unknown_primitive":
            continue
        rows.append({
            "gap_occurrence_id": stable_id("repository_inventory_gap", repo_id, "discovery", item.get("family_id"), "unknown_primitive"),
            "gap_kind": "structural_discovery_gap", "subject_kind": "structural_family", "subject_id": str(item.get("family_id") or ""),
            "discovery_kind": "unknown_primitive", "coverage_status": "supported_with_gaps", "relevance_status": "repository_landscape",
            "family_id": item.get("family_id"), "source_artifact_id": None,
            "evidence_refs": list((item.get("basis") or {}).get("evidence_refs") or []), "diagnostics": [], "basis": dict(item.get("basis") or {}),
        })
    rows.sort(key=lambda item: (item["gap_kind"], item["subject_kind"], item["subject_id"], item["gap_occurrence_id"]))
    return rows


def _interaction_interfaces(
    repo_id: str,
    evidence_items: Sequence[Mapping[str, Any]],
    evidence_paths: Sequence[Path],
    envelopes: Sequence[Mapping[str, Any]],
) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
    for item, path, envelope in zip(evidence_items, evidence_paths, envelopes):
        if str(envelope.get("artifact_kind") or "") != "interaction-boundary-evidence":
            continue
        records = interaction_boundary_records(path, envelope)
        artifact_id = str(envelope.get("artifact_id") or "")
        normalized = []
        for ordinal, record in enumerate(records, start=1):
            direction = str(record.get("direction") or "unknown").lower()
            endpoint = record.get("endpoint_or_topic_resolved") or record.get("endpoint_or_topic_raw")
            explicit_peer = record.get("peer_system") or record.get("target_system") or record.get("source_system")
            peer = str(explicit_peer).strip() if explicit_peer is not None and str(explicit_peer).strip() else None
            normalized.append({
                "interface_id": stable_id("repository_inventory_interface", repo_id, str(record.get("interface_id") or ""), ordinal, canonical_json(record)),
                "direction": direction,
                "boundary_kind": record.get("boundary_kind"), "protocol": record.get("protocol"),
                "operation": record.get("operation"), "endpoint_or_topic": endpoint, "http_method": record.get("http_method"),
                "peer_system": peer, "peer_resolution_status": "explicit" if peer else "unresolved",
                "evidence_status": "observed", "source_artifact_id": artifact_id,
                "basis": {"interface_id": record.get("interface_id"), "service_aliases": record.get("service_aliases") or [], "source_artifact_id": artifact_id},
            })
        return "evaluated", normalized, [dict(d) for d in envelope.get("diagnostics") or [] if isinstance(d, Mapping)]
    return "not_evaluated", [], []


def _storage_summary(envelopes: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    kinds = {"persistence-lineage-evidence", "storage-usage-evidence", "model-storage-evidence", "java-persistence-mapping-evidence"}
    observed = []
    for env in envelopes:
        kind = str(env.get("artifact_kind") or "")
        if kind not in kinds:
            continue
        observed.append({"artifact_kind": kind, "coverage": _positive_metrics(env.get("coverage") or {}), "artifact_id": env.get("artifact_id")})
    return {"evaluation_status": "evaluated" if observed else "not_evaluated", "official_evidence": observed}


def build_repository_inventory_knowledge_layer(
    evidence_items: Sequence[Mapping[str, Any]],
    evidence_paths: Sequence[Path],
    output: str | Path,
    *,
    scope_id: str,
    replace: bool = True,
    duckdb_memory_limit: str = "1GB",
    duckdb_threads: int = 1,
) -> dict[str, Any]:
    if len(evidence_items) != len(evidence_paths) or not evidence_items:
        raise ValueError("repository-inventory requires evidence items with resolved paths")
    envelopes = [_read_json(path) for path in evidence_paths]
    structures = [env for env in envelopes if (env.get("artifact_kind"), env.get("schema_version")) == ("repository-structure-evidence", "repository-structure-evidence/v1")]
    if len(structures) != 1:
        raise ValueError("repository-inventory requires exactly one repository-structure-evidence/v1 artifact")
    structure = structures[0]
    repo_id = _source_id(structure)
    if not repo_id:
        raise ValueError("repository structure evidence has no source id")
    foreign = sorted({source for source in (_source_id(env) for env in envelopes) if source and source != repo_id})
    if foreign:
        raise ValueError(f"repository-inventory evidence must belong to one repository; foreign source ids: {foreign}")

    metadata = _source_metadata(evidence_items, envelopes)
    identity = {
        "repository_id": metadata.get("repository_id"), "repository_name": metadata.get("repository_name") or repo_id,
        "source_kind": metadata.get("source_kind"), "repository_url": metadata.get("repository_url"),
        "default_branch": metadata.get("default_branch"),
    }
    by_identity = {(str(env.get("artifact_kind")), str(env.get("schema_version"))): env for env in envelopes}
    path_by_identity = {(str(env.get("artifact_kind")), str(env.get("schema_version"))): path for env, path in zip(envelopes, evidence_paths)}
    shape_envelope = by_identity.get(("structured-file-shape-evidence", "structured-file-shape-evidence/v1"))
    structural_members = (
        derive_structural_member_families(repo_id, shape_envelope)
        if shape_envelope is not None
        else {"evaluation_status": "not_evaluated", "families": [], "members": [], "diagnostics": []}
    )
    families = _extension_families(repo_id, structure)
    for shape_family in structural_members["families"]:
        count = int(shape_family.get("occurrence_count") or 0)
        families.append({
            "family_id": shape_family["family_id"],
            "family_kind": "structured_file_shape",
            "family_label": shape_family["family_label"],
            "source_artifact_kind": "structured-file-shape-evidence",
            "source_schema_version": "structured-file-shape-evidence/v1",
            "count": count,
            "structural_salience_score": _structural_salience_score(
                count=max(1, count),
                coverage_status=str((shape_envelope or {}).get("coverage", {}).get("coverage_status") or "unknown"),
                diagnostics=len((shape_envelope or {}).get("diagnostics") or []),
            ),
            "discovery_kind": "none", "discovery_basis": {"reason": "discovery_classification_pending"},
            "observed_metrics": {
                "record_count": count,
                "shape_count": int(shape_family.get("shape_count") or 0),
                "dominant_structure_rate": float(shape_family.get("dominant_structure_rate") or 0.0),
                "syntax": shape_family.get("syntax"),
            },
            "descriptor_labels": ["structured_file_shape", str(shape_family.get("syntax") or "unknown")],
            "evidence_refs": [{
                "artifact_id": (shape_envelope or {}).get("artifact_id"),
                "artifact_kind": "structured-file-shape-evidence",
                "schema_version": "structured-file-shape-evidence/v1",
                "content_fingerprint": (shape_envelope or {}).get("content_fingerprint"),
                "member_ids": shape_family.get("member_ids") or [],
            }],
        })
    for env in envelopes:
        if env is not structure:
            families.extend(_evidence_families(repo_id, env))
    families.sort(key=lambda item: (-float(item["structural_salience_score"]), item["family_kind"], item["family_label"]))

    _apply_discovery_classification(families)

    # Discovery candidates are reserved for evidence-backed Core frontier gaps.
    # High repository-local salience is useful ranking metadata, not a novelty claim.
    candidates = []
    for family in families:
        if str(family.get("discovery_kind") or "none") != "unknown_primitive":
            continue
        candidates.append({
            "candidate_id": stable_id("repository_inventory_candidate", family["family_id"]),
            "family_id": family["family_id"], "family_kind": family["family_kind"],
            "structural_salience_score": family["structural_salience_score"], "discovery_kind": "unknown_primitive",
            "basis": {"observed_metrics": family["observed_metrics"], "evidence_refs": family["evidence_refs"], "discovery_basis": family["discovery_basis"]},
        })

    files = [dict(item) for item in structure.get("files") or [] if isinstance(item, Mapping)]
    extensions = [dict(item) for item in structure.get("extension_inventory") or [] if isinstance(item, Mapping)]
    composition = _composition(files, extensions)
    technologies = _technology_signals(repo_id, files, str(structure.get("artifact_id") or ""))
    interfaces_status, interfaces, interface_diagnostics = _interaction_interfaces(repo_id, evidence_items, evidence_paths, envelopes)
    inputs = [item for item in interfaces if item["direction"] == "inbound"]
    outputs = [item for item in interfaces if item["direction"] == "outbound"]
    storage = _storage_summary(envelopes)
    data_footprint_kinds = {"data-model-candidate-evidence", "reference-data-evidence", "value-flow-evidence", "sql-analysis"}
    data_footprint = {
        "sql_files": next((int(item.get("file_count") or 0) for item in extensions if str(item.get("extension") or "") == ".sql"), 0),
        "official_evidence": [
            {"artifact_kind": str(env.get("artifact_kind") or ""), "artifact_id": env.get("artifact_id"), "coverage": _positive_metrics(env.get("coverage") or {})}
            for env in envelopes if str(env.get("artifact_kind") or "") in data_footprint_kinds
        ],
        "claim_boundary": "observed data-related Core evidence only; no repository-level semantic concept classification is produced",
    }
    evaluation_phase, evaluation_basis = _evaluation_phase(envelopes)
    completeness = _completeness_rows(repo_id, structure, envelopes)
    coverage_gaps = _coverage_gap_rows(repo_id, envelopes, candidates)
    source_occurrence_graph = build_source_occurrence_graph(
        repo_id=repo_id,
        families=families,
        candidates=candidates,
        coverage_gaps=coverage_gaps,
        structural_members=structural_members,
        repository_files=files,
        envelopes_by_identity=by_identity,
        envelope_paths_by_identity=path_by_identity,
    )

    diagnostics = [dict(item) for item in structure.get("diagnostics") or [] if isinstance(item, Mapping)] + interface_diagnostics + [dict(item) for item in structural_members.get("diagnostics") or [] if isinstance(item, Mapping)]
    discovery_counts: dict[str, int] = defaultdict(int)
    for family in families:
        discovery_counts[str(family.get("discovery_kind") or "none")] += 1
    completeness_counts: dict[str, int] = defaultdict(int)
    for item in completeness:
        completeness_counts[str(item["status"])] += 1

    coverage_gaps = annotate_gap_localization(coverage_gaps, source_occurrence_graph["links"])


    report = {
        "format": REPOSITORY_INVENTORY_SCHEMA_VERSION, "repository_id": repo_id, "identity": identity,
        "evaluation": {"phase": evaluation_phase, "basis": evaluation_basis},
        "summary": {
            "root_file_count": len(files), "extension_family_count": len(extensions), "structural_family_count": len(families),
            "discovery_candidate_count": len(candidates), "discovery_counts": dict(sorted(discovery_counts.items())),
            "unknown_primitive_count": len(candidates),
            "inbound_interface_count": len(inputs), "outbound_interface_count": len(outputs), "technology_count": len(technologies),
            "structural_member_count": len(structural_members["members"]), "structured_shape_family_count": len(structural_members["families"]),
            "coverage_gap_count": len(coverage_gaps), "completeness_counts": dict(sorted(completeness_counts.items())),
            "source_occurrence_count": len(source_occurrence_graph["occurrences"]), "source_occurrence_link_count": len(source_occurrence_graph["links"]),
        },
        "composition": composition, "technologies": technologies,
        "interfaces": {"evaluation_status": interfaces_status, "items": interfaces},
        "inputs": {"evaluation_status": interfaces_status, "items": inputs}, "outputs": {"evaluation_status": interfaces_status, "items": outputs},
        "storage": storage, "data_footprint": data_footprint, "evaluation_policy": _repository_inventory_evaluation_policy(),
        "repository_landscape_coverage": dict(structure.get("coverage") or {}), "coverage_matrix": completeness, "coverage_gaps": coverage_gaps,
        "extension_inventory": extensions,
        "outside_analyzer_frontier_extension_families": [dict(item) for item in structure.get("outside_analyzer_frontier_extension_families") or [] if isinstance(item, Mapping)],
        "structural_report": {"structural_families": families, "discovery_candidates": candidates, "structural_members": structural_members},
        "discovery_report": {
            "unknown_primitive_family_ids": sorted(item["family_id"] for item in candidates),
            "structural_salience": {
                "meaning": "repository-local ranking metadata derived from observed counts, coverage, frontier and diagnostics",
                "novelty_claim": False,
                "novelty_ownership": "downstream_cross_repository_mining",
            },
        },
        "source_localization": {
            "schema_version": source_occurrence_graph["schema_version"],
            "storage": "normalized_duckdb",
            "occurrence_count": len(source_occurrence_graph["occurrences"]),
            "link_count": len(source_occurrence_graph["links"]),
            "supported_object_kinds": sorted({item["object_kind"] for item in source_occurrence_graph["links"]}),
            "claim_boundary": "SourceOccurrence records identify observed source provenance only; they do not themselves assert semantic meaning, novelty, or benchmark representativeness",
        },
        "diagnostics": diagnostics,
        "claim_boundary": "repository inventory combines observed official Core evidence and source-registry metadata into one phased structural landscape; unknown primitives require explicit analyzer-frontier evidence, repository-local salience is not a novelty claim, and missing evidence remains visible through coverage/diagnostics",
    }

    output_path = Path(output).expanduser().resolve()
    if (output_path.exists() or output_path.is_symlink()) and not replace:
        raise FileExistsError(f"knowledge-layer output already exists: {output_path}")
    staging = output_path.with_name(f".{output_path.name}.building-{os.getpid()}-{uuid.uuid4().hex[:12]}")
    remove_path(staging); staging.mkdir(parents=True)
    database_path = staging / REPOSITORY_INVENTORY_DATABASE
    source_fingerprints = sorted(str(env.get("content_fingerprint") or "") for env in envelopes)
    metadata_fingerprint = hashlib.sha256(canonical_json(metadata).encode("utf-8")).hexdigest()
    build_id = stable_id("repository_inventory_build", scope_id, repo_id, *source_fingerprints, metadata_fingerprint, __version__, REPOSITORY_INVENTORY_SCHEMA_VERSION)
    started_at = utc_now(); connection = None
    try:
        connection = connect_database(database_path, memory_limit=duckdb_memory_limit, threads=duckdb_threads, preserve_insertion_order=False)
        initialize_schema(connection, REPOSITORY_INVENTORY_DDL)
        connection.execute("INSERT INTO repository_inventory_build VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)", [build_id, scope_id, repo_id, __version__, REPOSITORY_INVENTORY_SCHEMA_VERSION, "building", evaluation_phase, canonical_json(evaluation_basis), started_at, canonical_json({}), canonical_json({})])
        for item, path, env in zip(evidence_items, evidence_paths, envelopes):
            source_occurrence_id = stable_id("repository_inventory_source", env.get("artifact_id"), env.get("content_fingerprint"))
            connection.execute("INSERT INTO repository_inventory_source VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", [source_occurrence_id, scope_id, repo_id, env.get("artifact_id"), env.get("artifact_kind"), env.get("schema_version"), env.get("content_fingerprint"), str(path), canonical_json(env.get("coverage") or {}), canonical_json(env.get("diagnostics") or [])])
        connection.execute("INSERT INTO repository_inventory_identity VALUES (?, ?, ?, ?, ?, ?, ?, ?)", [scope_id, repo_id, identity.get("repository_id"), identity.get("repository_name"), identity.get("source_kind"), identity.get("repository_url"), identity.get("default_branch"), canonical_json(metadata)])
        source_artifact_id = str(structure.get("artifact_id") or "")
        for ordinal, item in enumerate(files, start=1):
            connection.execute("INSERT INTO repository_inventory_file VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", [stable_id("repository_inventory_file", repo_id, ordinal, item.get("repository_relative_path")), scope_id, repo_id, item.get("repository_relative_path"), item.get("file_name"), item.get("extension") or "<none>", item.get("byte_size"), item.get("sha256"), bool(item.get("readable")), bool(item.get("analyzer_eligible")), item.get("analyzer_frontier_status") or "unknown", source_artifact_id])
        for item in extensions:
            connection.execute("INSERT INTO repository_inventory_extension VALUES (?, ?, ?, ?, ?, ?, ?, ?)", [stable_id("repository_inventory_extension", repo_id, item.get("extension")), scope_id, repo_id, item.get("extension") or "<none>", int(item.get("file_count") or 0), int(item.get("analyzer_eligible_file_count") or 0), int(item.get("outside_analyzer_frontier_file_count") or 0), source_artifact_id])
        for item in technologies:
            connection.execute("INSERT INTO repository_inventory_technology VALUES (?, ?, ?, ?, ?, ?, ?, ?)", [item["technology_id"], scope_id, repo_id, item["category"], item["technology"], item["status"], item["confidence"], canonical_json(item["basis"])])
        for item in interfaces:
            connection.execute("INSERT INTO repository_inventory_interface VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", [item["interface_id"], scope_id, repo_id, item["direction"], item.get("boundary_kind"), item.get("protocol"), item.get("operation"), item.get("endpoint_or_topic"), item.get("http_method"), item.get("peer_system"), item["peer_resolution_status"], item["evidence_status"], item["source_artifact_id"], canonical_json(item["basis"])])
        for family in families:
            connection.execute("INSERT INTO repository_inventory_structural_family VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", [family["family_id"], scope_id, repo_id, family["family_kind"], family["family_label"], family.get("source_artifact_kind"), family.get("source_schema_version"), int(family["count"]), float(family["structural_salience_score"]), family["discovery_kind"], canonical_json(family["discovery_basis"]), canonical_json(family["observed_metrics"]), canonical_json(family["evidence_refs"])])
        for member in structural_members["members"]:
            connection.execute(
                "INSERT INTO repository_inventory_structural_member VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [stable_id("repository_inventory_structural_member", repo_id, member.get("member_id")), scope_id, repo_id, member["family_id"], member.get("member_id"), member.get("repository_relative_path"), (member.get("content_identity") or {}).get("sha256"), member.get("syntax") or "unknown", member.get("parse_status") or "unknown", member.get("structure_signature") or "unknown", member.get("variant_signature"), canonical_json(member.get("variant_roles") or []), canonical_json(member.get("structural_size") or {}), canonical_json(member.get("minority_states") or []), canonical_json(member.get("cardinality_extremes") or []), bool(member.get("observation_truncated")), canonical_json(member.get("provenance") or {})]
            )
        for item in candidates:
            connection.execute("INSERT INTO repository_inventory_candidate VALUES (?, ?, ?, ?, ?, ?, ?, ?)", [item["candidate_id"], scope_id, repo_id, item["family_id"], item["family_kind"], float(item["structural_salience_score"]), item["discovery_kind"], canonical_json(item["basis"])])
        for item in completeness:
            connection.execute("INSERT INTO repository_inventory_completeness VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", [item["completeness_id"], scope_id, repo_id, item["subject_kind"], item["subject_id"], item["status"], item["evidence_evaluation_status"], canonical_json(item["basis"]), canonical_json(item["diagnostics"])])
        for item in coverage_gaps:
            connection.execute("INSERT INTO repository_inventory_coverage_gap VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", [item["gap_occurrence_id"], scope_id, repo_id, item["gap_kind"], item["subject_kind"], item["subject_id"], item["discovery_kind"], item["coverage_status"], item["relevance_status"], item.get("family_id"), item.get("source_artifact_id"), item["localization_scope_kind"], item["localization_status"], canonical_json(item["evidence_refs"]), canonical_json(item["diagnostics"]), canonical_json(item["basis"])])
        for item in source_occurrence_graph["occurrences"]:
            connection.execute("INSERT INTO repository_inventory_source_occurrence VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", [item["occurrence_id"], scope_id, repo_id, item["repository_relative_path"], item["localization_kind"], item.get("line_start"), item.get("line_end"), item.get("content_sha256"), canonical_json(item.get("provenance") or [])])
        for item in source_occurrence_graph["links"]:
            connection.execute("INSERT INTO repository_inventory_object_occurrence VALUES (?, ?, ?, ?, ?, ?, ?, ?)", [item["link_id"], scope_id, repo_id, item["object_kind"], item["object_id"], item["occurrence_id"], item["linkage_role"], canonical_json(item.get("basis") or {})])
        for ordinal, item in enumerate(diagnostics, start=1):
            connection.execute("INSERT INTO repository_inventory_diagnostic VALUES (?, ?, ?, ?, ?, ?, ?)", [stable_id("repository_inventory_diagnostic", repo_id, ordinal, item.get("code"), item.get("message")), scope_id, repo_id, item.get("code") or "repository_inventory_diagnostic", item.get("severity") or "info", item.get("message") or "", canonical_json(item.get("basis") or item)])
        counts = {
            "repository_inventory_source": len(envelopes), "repository_inventory_file": len(files), "repository_inventory_extension": len(extensions),
            "repository_inventory_technology": len(technologies), "repository_inventory_interface": len(interfaces), "repository_inventory_input": len(inputs), "repository_inventory_output": len(outputs),
            "repository_inventory_structural_family": len(families), "repository_inventory_structural_member": len(structural_members["members"]), "repository_inventory_candidate": len(candidates),
            "repository_inventory_discovery_candidate": len(candidates),
            "repository_inventory_completeness": len(completeness), "repository_inventory_coverage_gap": len(coverage_gaps), "repository_inventory_source_occurrence": len(source_occurrence_graph["occurrences"]), "repository_inventory_object_occurrence": len(source_occurrence_graph["links"]), "repository_inventory_diagnostic": len(diagnostics),
        }
        checks = {
            "single_repository_scope": True,
            "repository_structure_source_present": True,
            "file_count_matches_structure_evidence": len(files) == int((structure.get("coverage") or {}).get("all_file_count") or len(files)),
            "unknown_primitive_requires_explicit_frontier_evidence": all(
                bool((family.get("observed_metrics") or {}).get("outside_analyzer_frontier_extension_family"))
                for family in families if family.get("discovery_kind") == "unknown_primitive"
            ),
            "discovery_kinds_are_core_level_only": all(str(family.get("discovery_kind") or "none") in {"none", "unknown_primitive"} for family in families),
            "deep_missing_evidence_is_visible": True,
        }
        if not checks["file_count_matches_structure_evidence"]:
            raise ValueError(f"repository-inventory validation failed: {checks}")
        completed_at = utc_now()
        connection.execute("UPDATE repository_inventory_build SET completed_at=?, build_status='complete', counts_json=?, checks_json=? WHERE build_id=?", [completed_at, canonical_json(counts), canonical_json(checks), build_id])
        connection.execute("CHECKPOINT"); connection.close(); connection = None
        write_json(staging / "repository_inventory.json", report)
        manifest = KnowledgeLayerManifest(
            scope_id=scope_id, repository_ids=(repo_id,), modes=("repository-inventory",), producer_version=__version__, build_id=build_id,
            build_status="complete", counts=counts,
            materialized_marts=("repository-inventory", "repository-coverage-frontier", "repository-discovery", "repository-system-passport"),
            capabilities=tuple(["common.repository-inventory", "common.repository-identity", "common.repository-technologies", "common.repository-interfaces", "common.repository-inputs-outputs", "common.repository-data-footprint", "common.repository-storage-footprint", "common.repository-coverage", "common.repository-coverage-gaps", "common.repository-structural-families", "common.repository-unknown-primitives", "common.repository-discovery", "common.repository-source-occurrences"] + (["common.repository-structural-members"] if structural_members["evaluation_status"] == "evaluated" else [])),
            artifacts={"database": REPOSITORY_INVENTORY_DATABASE, "manifest": "knowledge-layer-manifest.json", "repository_inventory": "repository_inventory.json"},
            source_evidence=tuple({"artifact_id": env.get("artifact_id"), "artifact_kind": env.get("artifact_kind"), "schema_version": env.get("schema_version"), "content_fingerprint": env.get("content_fingerprint"), "artifact_path": str(path)} for env, path in zip(envelopes, evidence_paths)),
            validation_status="complete", validation=checks,
            metadata={"repository_inventory_schema_version": REPOSITORY_INVENTORY_SCHEMA_VERSION, "evaluation_phase": evaluation_phase, "evaluation_basis": evaluation_basis, "repository_landscape_coverage": structure.get("coverage") or {}, "coverage_gap_count": len(coverage_gaps), "diagnostics": diagnostics, "evaluation_policy": report["evaluation_policy"], "started_at": started_at, "completed_at": completed_at},
        )
        write_json(staging / "knowledge-layer-manifest.json", manifest.to_dict())
        publish_directory_atomic(staging, output_path, replace=replace, existing_label="knowledge-layer output")
        return manifest.to_dict()
    except Exception:
        if connection is not None:
            connection.close()
        remove_path(staging)
        raise
