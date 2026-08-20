from __future__ import annotations

"""Uncapped facts-only store for source observations consumed by WKL/evidence CLI.

The ordinary normalized store remains intentionally capped for navigation. This
artifact persists the complete, bounded-to-enabled-stages observation stream so a
workspace builder can materialize every source fact without receiving the entire
fact base in an LLM prompt.
"""

from collections import Counter
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterable

from code_analyzer_core import __version__ as CORE_VERSION
from code_analyzer_core.models import AnalysisResult, Fact
from code_analyzer_core.utils import write_json

ARTIFACT_ID = "source_observation_fact_store"
SCHEMA_VERSION = "source-observation-fact-store/v1"

# These are universal, source-observed facts needed by data-model workspaces. The
# list deliberately contains no project-specific domain entities.
SOURCE_OBSERVATION_FACT_TYPES = {
    "configuration_entry",
    "configuration_object_observation",
    "configuration_reference_observation",
    "configuration_reference_resolution_observation",
    "configuration_comment_observation",
    "code_annotation",
    "java_method_call_observation",
    "java_method_reference_observation",
    "constructed_value_observation",
    "call_argument_flow_observation",
    "java_call_parameter_binding_observation",
    "java_call_result_binding_observation",
    "java_method_parameter_observation",
    "java_method_implementation_observation",
    "java_method_parameter_correspondence_observation",
    "collection_mutation_observation",
    "type_reference_observation",
    "gradle_project_observation",
    "gradle_module_observation",
    "gradle_external_dependency_observation",
    "gradle_plugin_observation",
    "gradle_version_catalog_observation",
    "gradle_included_build_observation",
    "gradle_source_set_observation",
    "gradle_repository_observation",
    "gradle_applied_script_observation",
    "gradle_unresolved_dependency_observation",
    "build_dependency_observation",
    "module_dependency_observation",
    "cross_module_type_resolution_observation",
    "cross_module_call_resolution_observation",
    "module_boundary_interaction_observation",
    "unresolved_module_reference_observation",
    "tsa_annotation_observation",
    "tsa_converter_configuration_observation",
    "tsa_configuration_directive_observation",
    "tsa_reference_operation_observation",
    "tsa_key_expression_observation",
    "tsa_storage_key_lineage_observation",
    "tsa_reference_value_derivation_observation",
    "storage_alias_assignment_observation",
    "storage_record_observation",
    "storage_reference_observation",
}


def _safe_type_name(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]+", "_", value.strip().replace("-", "_"))


def _fact_id(fact: Fact) -> str:
    props = fact.properties or {}
    for key in ("observation_id", "external_dependency_id", "configuration_entry_id"):
        if props.get(key):
            return str(props[key])
    first = fact.evidence[0] if fact.evidence else None
    payload = "\u001f".join(
        [
            fact.fact_type,
            fact.name,
            str(getattr(first, "file_path", "") or ""),
            str(getattr(first, "line_start", "") or ""),
            json.dumps(props, ensure_ascii=False, sort_keys=True, default=str),
        ]
    )
    return f"source_fact_{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:24]}"


def _row(fact: Fact) -> dict[str, Any]:
    return {
        "fact_id": _fact_id(fact),
        "fact_type": fact.fact_type,
        "name": fact.name,
        "properties": dict(fact.properties or {}),
        "evidence": [ref.model_dump(mode="json") for ref in fact.evidence],
    }


def _source_facts(result: AnalysisResult, additional_facts: Iterable[Fact] = ()) -> Iterable[Fact]:
    for fact in result.config_facts:
        if fact.fact_type in SOURCE_OBSERVATION_FACT_TYPES:
            yield fact
    additional = tuple(additional_facts)
    for fact in result.facts:
        if fact.fact_type == "external_dependency" and (fact.properties or {}).get("dependency_kind") in {"maven_artifact", "gradle_artifact"}:
            yield fact
        elif fact.fact_type in SOURCE_OBSERVATION_FACT_TYPES:
            yield fact
    yield from additional


def bounded_source_observation_preview(facts: Iterable[Fact], *, max_per_type: int = 500) -> list[Fact]:
    """Return a deterministic navigation preview while the full stream stays in JSONL."""
    counts: Counter[str] = Counter()
    preview: list[Fact] = []
    for fact in facts:
        if counts[fact.fact_type] >= max_per_type:
            continue
        counts[fact.fact_type] += 1
        preview.append(fact)
    return preview


def _sort_key(row: dict[str, Any]) -> tuple[Any, ...]:
    evidence = row.get("evidence") or []
    first = evidence[0] if evidence else {}
    return (
        str(first.get("file_path") or ""),
        int(first.get("line_start") or 0),
        int(first.get("line_end") or 0),
        str(row.get("name") or ""),
        str(row.get("fact_id") or ""),
    )


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> dict[str, Any]:
    digest = hashlib.sha256()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            line = json.dumps(row, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":")) + "\n"
            handle.write(line)
            digest.update(line.encode("utf-8"))
    return {
        "relative_path": f"facts/full_by_type/{path.name}",
        "format": "jsonl",
        "records_count": len(rows),
        "bytes": path.stat().st_size,
        "sha256": digest.hexdigest(),
    }


def write_source_observation_fact_store(
    *,
    result: AnalysisResult,
    facts_dir: Path,
    additional_facts: Iterable[Fact] = (),
) -> dict[str, Any]:
    full_dir = facts_dir / "full_by_type"
    full_dir.mkdir(parents=True, exist_ok=True)
    for old in full_dir.glob("*.jsonl"):
        old.unlink()

    source_facts = list(_source_facts(result, additional_facts))
    fact_types = sorted({fact.fact_type for fact in source_facts})
    section_index: dict[str, Any] = {}
    counts: Counter[str] = Counter()
    total_bytes = 0
    total_records = 0
    for fact_type in fact_types:
        rows = [_row(fact) for fact in source_facts if fact.fact_type == fact_type]
        rows.sort(key=_sort_key)
        metadata = _write_jsonl(full_dir / f"{_safe_type_name(fact_type)}.jsonl", rows)
        section_index[fact_type] = metadata
        counts[fact_type] = len(rows)
        total_records += len(rows)
        total_bytes += int(metadata["bytes"])
        del rows

    manifest = {
        "artifact_id": ARTIFACT_ID,
        "schema_version": SCHEMA_VERSION,
        "producer": {"name": "code-analyzer-core", "version": CORE_VERSION},
        "storage_policy": "uncapped_per_enabled_stage_jsonl_with_bounded_cli_reads",
        "semantic_policy": {
            "project_specific_semantics_applied": False,
            "domain_object_classification_performed": False,
            "key_classification_performed": False,
            "relationship_or_join_verdict_performed": False,
            "confidence_or_status_assigned": False,
        },
        "source_scope": "source files and configuration files processed by enabled stages",
        "fact_types": dict(sorted(counts.items())),
        "records_count": total_records,
        "bytes": total_bytes,
        "section_index": section_index,
    }
    manifest_path = facts_dir / "full_fact_manifest.json"
    write_json(manifest_path, manifest)
    return {
        "requested": True,
        "status": "success",
        "manifest_path": str(manifest_path),
        "records_count": total_records,
        "bytes": total_bytes,
        "fact_type_counts": dict(sorted(counts.items())),
        "section_index": section_index,
    }

