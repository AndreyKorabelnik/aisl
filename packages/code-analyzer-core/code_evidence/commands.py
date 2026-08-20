from __future__ import annotations

import functools
import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any

import typer

from .helpers import load_navigation, load_core, print_json, read_json, repo_from_analysis, write_lazy, snippet_lines
from .fdp_view import FdpViewDependencies, _fdp_concrete_text, _fdp_list, _fdp_source_scope, _fdp_unique_strings
from . import fdp_view as _fdp_view
from .source import find_symbol_files, extract_callables, extract_callable_body, read_text, search_repo, find_possible_implementations, source_inspection_bundle, source_open_bundle
from code_analyzer_core.utils import normalize_name


def _hash(value: Any) -> str:
    return hashlib.sha1(str(value).encode("utf-8")).hexdigest()[:24]



EVIDENCE_ID_KEYS = [
    "evidence_id", "id", "ref_id",
    # Prefer the most specific record ID. Lineage rows often also contain
    # query_id, but the evidence reference should be the lineage_id.
    "lineage_id", "comment_id", "object_id", "attribute_id",
    "schema_id", "operation_id", "interface_id",
    "field_lineage_id", "output_field_provenance_id", "call_chain_diagnostic_id", "source_to_storage_lineage_id",
    "trace_id", "ingress_id", "origin_id", "call_id", "storage_access_id",
    "data_source_id", "persistent_write_id", "jooq_batch_bind_mapping_id", "jooq_parameterized_sql_mapping_id", "java_lineage_pattern_id",
    "spring_component_dependency_id", "template_method_dispatch_id", "factory_method_mapping_id", "builder_field_mapping_id", "stream_collection_lineage_id", "mapstruct_mapper_signature_id",
    "read_from_storage_id", "access_boundary_id", "storage_to_access_lineage_id", "stored_field_to_response_field_mapping_id", "storage_lineage_gap_id", "source_inspection_request_id",
    "persistent_structure_id", "attribute_occurrence_id", "attribute_mapping_id", "attribute_derivation_id", "data_model_lineage_gap_id",
    "cross_repo_attribute_flow_candidate_id",
    "workspace_table_id", "workspace_table_attribute_id", "workspace_attribute_edge_id",
    "attribute_origin_candidate_id", "attribute_rename_chain_id", "attribute_journey_id", "attribute_lineage_break_id",
    "workspace_source_to_storage_lineage_id", "workspace_data_model_lineage_gap_id",
    "workspace_table_relationship_candidate_id", "workspace_key_candidate_id",
    "db_schema_table_id", "db_schema_column_id", "db_schema_key_id", "db_schema_relationship_id", "db_schema_index_id",
    "declared_value_set_id", "declared_value_set_summary_id", "declared_value_id", "literal_data_write_id",
    "occurrence_id", "edge_id", "field_flow_id", "flow_id", "fact_id", "query_id",
]


def _iter_json_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(p for p in root.rglob("*.json") if p.is_file())


def _record_id(item: dict[str, Any]) -> str | None:
    for key in EVIDENCE_ID_KEYS:
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _short_summary(item: dict[str, Any]) -> str:
    for keys in [
        ("output_field_provenance_id", "published_field"),
        ("trace_id", "trace_status"),
        ("ingress_id", "origin_kind"),
        ("call_id", "callee_method"),
        ("storage_access_id", "access_kind"),
        ("data_source_id", "source_kind"),
        ("persistent_write_id", "storage_target"),
        ("jooq_batch_bind_mapping_id", "storage_table"),
        ("java_lineage_pattern_id", "pattern_kind"),
        ("spring_component_dependency_id", "declared_type"),
        ("template_method_dispatch_id", "overriding_operation"),
        ("factory_method_mapping_id", "target_container"),
        ("builder_field_mapping_id", "operation"),
        ("stream_collection_lineage_id", "source_collection"),
        ("read_from_storage_id", "storage_symbol"),
        ("access_boundary_id", "boundary_kind"),
        ("storage_to_access_lineage_id", "access_boundary"),
        ("stored_field_to_response_field_mapping_id", "response_field"),
        ("source_to_storage_lineage_id", "storage_field"),
        ("storage_lineage_gap_id", "gap_kind"),
        ("persistent_structure_id", "storage_target"),
        ("attribute_occurrence_id", "attribute_name"),
        ("attribute_mapping_id", "target_field"),
        ("attribute_derivation_id", "target_field"),
        ("data_model_lineage_gap_id", "gap_kind"),
        ("cross_repo_attribute_flow_candidate_id", "flow_kind"),
        ("workspace_table_id", "table_name"),
        ("workspace_table_attribute_id", "db_column_name"),
        ("workspace_attribute_edge_id", "edge_type"),
        ("attribute_origin_candidate_id", "attribute_name"),
        ("attribute_rename_chain_id", "target_attribute"),
        ("attribute_journey_id", "normalized_attribute_name"),
        ("attribute_lineage_break_id", "lineage_break_reason"),
        ("workspace_table_relationship_candidate_id", "relationship_kind"),
        ("workspace_key_candidate_id", "key_role"),
        ("db_schema_table_id", "table_name"),
        ("db_schema_column_id", "column_name"),
        ("db_schema_key_id", "constraint_name"),
        ("db_schema_relationship_id", "constraint_name"),
        ("db_schema_index_id", "index_name"),
        ("declared_value_set_id", "syntax_kind"),
        ("declared_value_id", "key"),
        ("declared_value_set_summary_id", "syntax_kind"),
        ("literal_data_write_id", "target_table"),
        ("source_object", "source_field"),
        ("source_payload", "source_field"),
        ("source_parameter", "sink_kind"),
        ("source_object", "target_object"),
        ("object_name", "column_name"),
        ("query_id", "target_object"),
        ("comment_text",),
        ("name",),
        ("id",),
    ]:
        values = [str(item.get(k) or "").strip() for k in keys]
        values = [v for v in values if v]
        if values:
            text = " -> ".join(values) if len(values) == 2 and keys == ("source_object", "target_object") else " | ".join(values)
            return text[:300]
    return json.dumps({k: item.get(k) for k in list(item)[:5]}, ensure_ascii=False, default=str)[:300]


def _manifest_entries_from_data(data: Any, *, source_file: str, repo_id_filter: str | None = None) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            rid = _record_id(node)
            if rid:
                if repo_id_filter and str(node.get("repo_id") or "") not in {"", repo_id_filter}:
                    return
                entry = {
                    "evidence_id": rid,
                    "source_file": source_file,
                    "kind": node.get("kind") or node.get("artifact") or node.get("finding_type") or source_file.split("/")[-1].removesuffix(".json"),
                    "repo_id": node.get("repo_id"),
                    "query_id": node.get("query_id"),
                    "lineage_id": node.get("lineage_id"),
                    "comment_id": node.get("comment_id"),
                    "object_name": node.get("object_name") or node.get("target_object") or node.get("source_object"),
                    "file": node.get("file"),
                    "line_start": node.get("line_start"),
                    "summary": _short_summary(node),
                }
                entries.append({k: v for k, v in entry.items() if v is not None})
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(data)
    return entries


def export_manifest(
    *,
    analysis_out: Path | None = None,
    max_entries: int = 200000,
) -> dict[str, Any]:
    """Build a deterministic evidence manifest from one repository analysis output.

    The manifest is intentionally simple: it exposes all stable evidence IDs that
    LLM findings may reference (`query_id`, `lineage_id`, `comment_id`, Java
    operation/schema/interface ids, etc.). `evidence-eval` then verifies that
    final structured results only cite evidence that exists in this manifest.
    """
    roots: list[tuple[Path, str]] = []
    source: dict[str, Any] = {}

    if analysis_out is not None:
        root = Path(analysis_out).resolve()
        roots.append((root, "static-analysis-output"))
        source["static_analysis_output"] = str(root)

    if not roots:
        raise ValueError("Provide --static-analysis-output")

    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for root, root_kind in roots:
        for path in _iter_json_files(root):
            data = read_json(path, None)
            try:
                rel = str(path.relative_to(root)).replace("\\", "/")
            except Exception:
                rel = str(path)
            for entry in _manifest_entries_from_data(data, source_file=f"{root_kind}/{rel}", repo_id_filter=None):
                eid = str(entry.get("evidence_id") or "")
                if not eid or eid in seen:
                    continue
                seen.add(eid)
                entries.append(entry)
                if len(entries) >= max_entries:
                    break
            if len(entries) >= max_entries:
                break
        if len(entries) >= max_entries:
            break

    return {
        "artifact": "evidence_manifest",
        "manifest_version": "1.0",
        "source": source,
        "entry_count": len(entries),
        "evidence_ids": sorted(seen),
        "evidence": entries,
    }


def _source_snippet(file_value: str | None, line_start: int | None, line_end: int | None, *, radius: int = 2, max_chars: int = 12000) -> str | None:
    if not file_value or not line_start:
        return None
    try:
        p = Path(file_value)
        if not p.exists():
            return None
        text = read_text(p)
        lines = text.splitlines()
        start = max(1, int(line_start) - radius)
        end = min(len(lines), int(line_end or line_start) + radius)
        snippet = "\n".join(lines[start - 1:end])
        return snippet[:max_chars]
    except Exception:
        return None


def _materialize_evidence(obj: Any) -> Any:
    """Add snippets lazily to evidence records that only contain file/line locations."""
    if isinstance(obj, dict):
        out = {k: _materialize_evidence(v) for k, v in obj.items()}
        if ("file" in out or "file_path" in out) and "line_start" in out and not out.get("snippet"):
            sn = _source_snippet(out.get("file") or out.get("file_path"), out.get("line_start"), out.get("line_end"))
            if sn:
                out["snippet"] = sn
        return out
    if isinstance(obj, list):
        return [_materialize_evidence(x) for x in obj]
    return obj


def _candidate_schema(nav: dict[str, Any], schema_name: str) -> dict[str, Any] | None:
    return _match_by_id_or_name(nav.get("schemas") or [], schema_name, "name")


def operation(analysis_out: Path, operation_id: str) -> dict[str, Any]:
    nav = load_navigation(analysis_out)
    ops = nav.get("operations") or []
    op = _match_by_id_or_name(ops, operation_id, "operation")
    if not op:
        raise typer.BadParameter(f"operation not found: {operation_id}")
    interface_ids = set(op.get("interfaces") or [])
    schema_names = set(op.get("schemas") or [])
    interfaces = [x for x in nav.get("interfaces", []) if x.get("id") in interface_ids]
    schemas = [x for x in nav.get("schemas", []) if x.get("name") in schema_names]
    obj = _materialize_evidence({"kind": "operation", "operation": op, "interfaces": interfaces, "schemas": schemas})
    write_lazy(analysis_out, "operation", operation_id, obj)
    return obj


def interface(analysis_out: Path, interface_id: str) -> dict[str, Any]:
    nav = load_navigation(analysis_out)
    item = _match_by_id_or_name(nav.get("interfaces") or [], interface_id, "name", "operation", "path")
    if not item:
        raise typer.BadParameter(f"interface not found: {interface_id}")
    related_schema = None
    if item.get("schema_ref"):
        related_schema = _candidate_schema(nav, str(item["schema_ref"]))
    obj = _materialize_evidence({"kind": "interface", "interface": item, "schema": related_schema})
    write_lazy(analysis_out, "interface", interface_id, obj)
    return obj


def schema(analysis_out: Path, schema_id_or_name: str) -> dict[str, Any]:
    nav = load_navigation(analysis_out)
    item = _match_by_id_or_name(nav.get("schemas") or [], schema_id_or_name, "name")
    if not item:
        item = _match_by_id_or_name(load_core(analysis_out, "schemas"), schema_id_or_name, "name")
    if not item:
        raise typer.BadParameter(f"schema not found: {schema_id_or_name}")

    # In the lean analyzer schema indexes are intentionally brief. Attach source preview lazily.
    source_matches = []
    repo = repo_from_analysis(analysis_out)
    schema_name = str(item.get("name") or schema_id_or_name)
    for p in find_symbol_files(repo, schema_name)[:5]:
        text = read_text(p)
        source_matches.append({
            "file": str(p),
            "callables": extract_callables(text)[:80],
            "preview": "\n".join(text.splitlines()[:160])[:12000],
        })
    obj = _materialize_evidence({"kind": "schema", "schema": item, "source_matches": source_matches})
    write_lazy(analysis_out, "schema", schema_id_or_name, obj)
    return obj


def symbol(analysis_out: Path, symbol_name: str) -> dict[str, Any]:
    repo = repo_from_analysis(analysis_out)
    matches = []
    for p in find_symbol_files(repo, symbol_name)[:10]:
        text = read_text(p)
        matches.append({
            "file": str(p),
            "callables": extract_callables(text)[:120],
            "preview": "\n".join(text.splitlines()[:100])[:10000],
        })
    if not matches:
        raise typer.BadParameter(f"symbol not found: {symbol_name}")
    obj = {"kind": "symbol", "symbol": symbol_name, "matches": matches}
    write_lazy(analysis_out, "symbol", symbol_name, obj)
    return obj


def callable(analysis_out: Path, symbol_name: str, callable_name: str, max_chars: int = 20000) -> dict[str, Any]:
    repo = repo_from_analysis(analysis_out)
    matches = []
    for p in find_symbol_files(repo, symbol_name)[:10]:
        text = read_text(p)
        body = extract_callable_body(text, callable_name)
        if body:
            snippet = body["snippet"]
            truncated = len(snippet) > max_chars
            body = {**body, "snippet": snippet[:max_chars], "truncated": truncated}
            matches.append({"file": str(p), "callable": callable_name, **body})
    if not matches:
        candidates = []
        for p in find_symbol_files(repo, symbol_name)[:5]:
            candidates.append({"file": str(p), "callables": extract_callables(read_text(p))[:80]})
        raise typer.BadParameter(json.dumps({"error": "callable not found", "symbol": symbol_name, "callable": callable_name, "candidate_symbols": candidates}, ensure_ascii=False))
    obj = {"kind": "callable", "symbol": symbol_name, "callable": callable_name, "matches": matches}
    write_lazy(analysis_out, "callable", f"{symbol_name}.{callable_name}", obj)
    return obj


def search(analysis_out: Path, token: str, max_results: int = 30, context: int = 2) -> dict[str, Any]:
    repo = repo_from_analysis(analysis_out)
    hits = search_repo(repo, token, max_results=max_results, context=context)
    obj = {"kind": "search", "token": token, "hits": hits, "hit_count": len(hits)}
    write_lazy(analysis_out, "search", token, obj)
    return obj


def _iter_index_items(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        out: list[dict[str, Any]] = []
        for key in ["operations", "interfaces", "schemas", "candidate_operations", "referenced_schema_catalog"]:
            value = data.get(key)
            if isinstance(value, list):
                out.extend([x for x in value if isinstance(x, dict)])
        return out
    return []


def _artifact_search(analysis_out: Path, token: str, max_results: int = 50) -> dict[str, Any]:
    q = token.lower()
    files = [
        analysis_out / "compact" / "first_pass.json",
        analysis_out / "compact" / "navigation.json",
        analysis_out / "compact" / "package_manifest.json",
        analysis_out / "facts" / "fact_summary.json",
    ]
    files.extend(sorted((analysis_out / "facts" / "facts_by_type").glob("*.json")))
    hits: list[dict[str, Any]] = []
    for path in files:
        data = read_json(path, None)
        for item in _iter_index_items(data):
            if len(hits) >= max_results:
                break
            s = json.dumps(item, ensure_ascii=False, default=str)
            if q in s.lower():
                hits.append({"source_file": str(path.relative_to(analysis_out)), "item": _materialize_evidence(item)})
        if len(hits) >= max_results:
            break
    return {"kind": "artifact_search", "token": token, "hits": hits, "hit_count": len(hits)}


def _combined_artifact_and_source_search(analysis_out: Path, token: str, *, kind: str, max_results: int = 50) -> dict[str, Any]:
    artifact = _artifact_search(analysis_out, token, max_results=max_results)
    repo_hits = search_repo(repo_from_analysis(analysis_out), token, max_results=max(10, max_results // 2), context=3)
    obj = {
        "kind": kind,
        "token": token,
        "artifact_hits": artifact["hits"],
        "artifact_hit_count": artifact["hit_count"],
        "source_hits": repo_hits,
        "source_hit_count": len(repo_hits),
        "note": "Lean analyzer stores slim indexes only. Use symbol/callable/search for exact source evidence.",
    }
    write_lazy(analysis_out, kind, token, obj)
    return obj


def field(analysis_out: Path, token: str, max_results: int = 50) -> dict[str, Any]:
    return _combined_artifact_and_source_search(analysis_out, token, kind="field", max_results=max_results)


def _canonical_fact_type(value: str) -> str:
    return (value or "").strip().replace("-", "_")


def _full_fact_path(analysis_out: Path, fact_type: str) -> Path:
    safe = re.sub(r"[^a-zA-Z0-9_]+", "_", _canonical_fact_type(fact_type))
    return analysis_out / "facts" / "full_by_type" / f"{safe}.jsonl"


def _read_jsonl_rows(path: Path, *, max_results: int | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            try:
                value = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                rows.append(value)
                if max_results is not None and len(rows) >= max(0, int(max_results)):
                    break
    return rows


def facts_by_type(analysis_out: Path, fact_type: str, max_results: int = 200) -> dict[str, Any]:
    requested_fact_type = fact_type
    canonical_fact_type = _canonical_fact_type(fact_type)
    full_path = _full_fact_path(analysis_out, canonical_fact_type)
    capped_path = analysis_out / "facts" / "facts_by_type" / f"{canonical_fact_type}.json"
    if full_path.exists():
        facts = _read_jsonl_rows(full_path, max_results=max_results)
        source = "full_by_type_jsonl"
    elif capped_path.exists():
        data = read_json(capped_path, [])
        facts = data[:max_results] if isinstance(data, list) else []
        source = "normalized_capped_json"
    else:
        available = {p.stem for p in (analysis_out / "facts" / "facts_by_type").glob("*.json")}
        available.update(p.stem for p in (analysis_out / "facts" / "full_by_type").glob("*.jsonl"))
        raise typer.BadParameter(f"fact type not found: {requested_fact_type}. Available: {', '.join(sorted(available)[:80])}")
    obj = _materialize_evidence({
        "kind": "facts-by-type",
        "fact_type": canonical_fact_type,
        "requested_fact_type": requested_fact_type,
        "fact_store_source": source,
        "facts": facts,
        "returned": len(facts),
    })
    write_lazy(analysis_out, "facts-by-type", canonical_fact_type, obj)
    return obj


def relation(analysis_out: Path, token: str, max_results: int = 50) -> dict[str, Any]:
    return _combined_artifact_and_source_search(analysis_out, token, kind="relation", max_results=max_results)


def query(analysis_out: Path, token: str, max_results: int = 50) -> dict[str, Any]:
    return _combined_artifact_and_source_search(analysis_out, token, kind="query", max_results=max_results)


def lineage(analysis_out: Path, token: str, max_results: int = 50) -> dict[str, Any]:
    return _combined_artifact_and_source_search(analysis_out, token, kind="lineage", max_results=max_results)



def show(analysis_out: Path, evidence_id: str, max_results: int = 20) -> dict[str, Any]:
    """Resolve one stable evidence id from analyzer artifacts.

    This is the generic traceability entry point for report evidence_refs. It is
    intentionally id-first: `flow_000001` and `field_flow_000001` are resolved
    exactly, while older navigation ids such as `operation_000001` still use their
    dedicated materializers where possible.
    """
    eid = str(evidence_id).strip()
    if not eid:
        raise typer.BadParameter("evidence id is required")

    if eid.startswith("flow_"):
        return flow(analysis_out, eid, max_results=1)
    if eid.startswith("field_flow_"):
        return field_flow(analysis_out, eid, max_results=1)
    if eid.startswith("field_lineage_"):
        return field_lineage(analysis_out, eid, max_results=1)
    if eid.startswith("output_field_provenance_"):
        return output_field_provenance(analysis_out, eid, max_results=1)
    if eid.startswith("call_chain_diagnostic_"):
        return call_chain_diagnostic(analysis_out, eid, max_results=1)
    if eid.startswith("ingress_") or eid.startswith("origin_"):
        return ingress(analysis_out, eid, max_results=1)
    if eid.startswith("call_"):
        return call(analysis_out, eid, max_results=1)
    if eid.startswith("trace_"):
        return trace(analysis_out, eid, max_results=1)
    if eid.startswith("storage_access_"):
        return storage_access(analysis_out, eid, max_results=1)
    if eid.startswith("data_source_"):
        return data_source(analysis_out, eid, max_results=1)
    if eid.startswith("persistent_write_"):
        return persistent_write(analysis_out, eid, max_results=1)
    if eid.startswith("jooq_batch_bind_mapping_"):
        return jooq_batch_bind_mappings(analysis_out, eid, max_results=1)
    if eid.startswith("jooq_parameterized_sql_mapping_"):
        return jooq_parameterized_sql_mappings(analysis_out, eid, max_results=1)
    if eid.startswith("java_lineage_pattern_"):
        return java_lineage_patterns(analysis_out, eid, max_results=1)
    if eid.startswith("spring_component_dependency_"):
        return spring_component_dependencies(analysis_out, eid, max_results=1)
    if eid.startswith("template_method_dispatch_"):
        return template_method_dispatches(analysis_out, eid, max_results=1)
    if eid.startswith("factory_method_mapping_"):
        return factory_method_mappings(analysis_out, eid, max_results=1)
    if eid.startswith("builder_field_mapping_"):
        return builder_field_mappings(analysis_out, eid, max_results=1)
    if eid.startswith("stream_collection_lineage_"):
        return stream_collection_lineages(analysis_out, eid, max_results=1)
    if eid.startswith("mapstruct_mapper_signature_"):
        return mapstruct_mapper_signatures(analysis_out, eid, max_results=1)
    if eid.startswith("source_to_storage_lineage_"):
        return source_to_storage_lineage(analysis_out, eid, max_results=1)
    if eid.startswith("storage_lineage_gap_"):
        return storage_lineage_gap(analysis_out, eid, max_results=1)
    if eid.startswith("persistent_structure_"):
        return persistent_structure(analysis_out, eid, max_results=1)
    if eid.startswith("attribute_occurrence_"):
        return attribute_occurrence(analysis_out, eid, max_results=1)
    if eid.startswith("attribute_mapping_"):
        return attribute_mapping(analysis_out, eid, max_results=1)
    if eid.startswith("attribute_derivation_"):
        return attribute_derivation(analysis_out, eid, max_results=1)
    if eid.startswith("data_model_lineage_gap_"):
        return data_model_lineage_gap(analysis_out, eid, max_results=1)
    if eid.startswith("declared_value_set_") or eid.startswith("declared_value_"):
        return declared_value_set(analysis_out, eid, max_results=1)
    if eid.startswith("literal_data_write_"):
        return literal_data_write(analysis_out, eid, max_results=1)
    if eid.startswith("operation_"):
        return operation(analysis_out, eid)
    if eid.startswith("interface_"):
        return interface(analysis_out, eid)
    if eid.startswith("schema_"):
        return schema(analysis_out, eid)

    hits: list[dict[str, Any]] = []
    for path in _iter_json_files(analysis_out):
        data = read_json(path, None)
        for item in _iter_index_items(data):
            if len(hits) >= max_results:
                break
            if _record_id(item) == eid:
                hits.append({"source_file": str(path.relative_to(analysis_out)), "item": _materialize_evidence(item)})
            else:
                props = item.get("properties") if isinstance(item.get("properties"), dict) else {}
                if _record_id(props) == eid:
                    hits.append({"source_file": str(path.relative_to(analysis_out)), "item": _materialize_evidence(item)})
        if len(hits) >= max_results:
            break

    if not hits:
        # Last resort: substring search in compact/facts artifacts plus source search.
        return _combined_artifact_and_source_search(analysis_out, eid, kind="show", max_results=max_results)

    obj = {
        "kind": "show",
        "evidence_id": eid,
        "hits": hits,
        "hit_count": len(hits),
        "note": "Generic evidence resolver for report evidence_refs. Prefer dedicated commands only when a profile asks for a narrower view.",
    }
    write_lazy(analysis_out, "show", eid, obj)
    return obj

def flow(analysis_out: Path, token: str, max_results: int = 50) -> dict[str, Any]:
    """Return source-to-sink Java data-flow evidence for a token.

    Searches compact/data_flows.json and normalized source_to_sink_flow facts.
    This command is intentionally lightweight: it returns analyzer-built flow paths
    plus source snippets for the methods/sinks that support them.
    """
    q = token.lower()
    files = [
        analysis_out / "compact" / "data_flows.json",
        analysis_out / "facts" / "facts_by_type" / "source_to_sink_flow.json",
    ]
    hits: list[dict[str, Any]] = []
    for path in files:
        if path.suffix.lower() == ".jsonl" and path.exists():
            items: list[dict[str, Any]] = []
            with path.open("r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        item = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(item, dict):
                        items.append(item)
        else:
            data = read_json(path, None)
            items = data if isinstance(data, list) else []
        for item in items:
            if len(hits) >= max_results:
                break
            blob = json.dumps(item, ensure_ascii=False, default=str)
            if q in blob.lower():
                hits.append({"source_file": str(path.relative_to(analysis_out)), "item": _materialize_evidence(item)})
        if len(hits) >= max_results:
            break
    if not hits:
        # Fallback to generic artifact/source search so the LLM still gets useful context.
        return _combined_artifact_and_source_search(analysis_out, token, kind="flow", max_results=max_results)
    obj = {
        "kind": "flow",
        "token": token,
        "hits": hits,
        "hit_count": len(hits),
        "note": "Flow evidence is analyzer-built source-to-sink evidence. Use flow_id in evidence_refs when citing this path.",
    }
    write_lazy(analysis_out, "flow", token, obj)
    return obj


def field_flow(analysis_out: Path, token: str, max_results: int = 50) -> dict[str, Any]:
    """Return Java identifier/field propagation evidence for a token.

    Searches compact/field_flows.json and normalized field_identifier_flow facts.
    Use field_flow_id in evidence_refs when citing field-level propagation.
    """
    q = token.lower()
    files = [
        analysis_out / "compact" / "field_flows.json",
        analysis_out / "facts" / "facts_by_type" / "field_identifier_flow.json",
    ]
    hits: list[dict[str, Any]] = []
    for path in files:
        data = read_json(path, None)
        items = data if isinstance(data, list) else []
        for item in items:
            if len(hits) >= max_results:
                break
            blob = json.dumps(item, ensure_ascii=False, default=str)
            if q in blob.lower():
                hits.append({"source_file": str(path.relative_to(analysis_out)), "item": _materialize_evidence(item)})
        if len(hits) >= max_results:
            break
    if not hits:
        return _combined_artifact_and_source_search(analysis_out, token, kind="field-flow", max_results=max_results)
    obj = {
        "kind": "field-flow",
        "token": token,
        "hits": hits,
        "hit_count": len(hits),
        "note": "Field-flow evidence is analyzer-built identifier/field propagation evidence. Use field_flow_id in evidence_refs when citing this path.",
    }
    write_lazy(analysis_out, "field-flow", token, obj)
    return obj





def _field_flow_analysis_out(analysis_out: Path, repo_id: str | None) -> tuple[Path, str | None]:
    """Validate one repository analysis output without guessing repository identity."""
    root = Path(analysis_out).resolve()
    manifest = read_json(root / "manifest.json", {}) or {}
    actual_repo_id = manifest.get("repo_id")
    if repo_id and actual_repo_id and str(actual_repo_id) != str(repo_id):
        raise ValueError(f"repo_id mismatch: requested={repo_id!r}, analysis_output_repo_id={actual_repo_id!r}")
    return root, str(actual_repo_id or repo_id) if (actual_repo_id or repo_id) else None

def field_flow_occurrence(analysis_out: Path, token: str, repo_id: str | None = None, max_results: int = 50) -> dict[str, Any]:
    """Return full Tree-sitter-backed field occurrences by id, symbol or field path."""
    resolved_out, resolved_repo_id = _field_flow_analysis_out(analysis_out, repo_id)
    items = read_json(resolved_out / "catalog" / "field_occurrences.json", []) or []
    q = str(token or "").strip().lower()
    hits = []
    for item in items if isinstance(items, list) else []:
        if len(hits) >= max_results:
            break
        if q and q not in json.dumps(item, ensure_ascii=False, default=str).lower():
            continue
        hits.append(_materialize_evidence(item))
    obj = {
        "kind": "field-flow-occurrence",
        "repository_id": resolved_repo_id,
        "analysis_out": str(resolved_out),
        "token": token,
        "hit_count": len(hits),
        "items": hits,
        "source_artifact": "catalog/field_occurrences.json",
        "policy": "Direct AST-backed occurrences only; no business-semantic identity claim.",
    }
    write_lazy(resolved_out, "field-flow-occurrence", token or "all", obj)
    return obj


def field_flow_edge(analysis_out: Path, token: str, repo_id: str | None = None, max_results: int = 50) -> dict[str, Any]:
    """Return full Tree-sitter-backed field-flow edges by id or technical token."""
    resolved_out, resolved_repo_id = _field_flow_analysis_out(analysis_out, repo_id)
    items = read_json(resolved_out / "catalog" / "field_flow_edges.json", []) or []
    q = str(token or "").strip().lower()
    hits = []
    for item in items if isinstance(items, list) else []:
        if len(hits) >= max_results:
            break
        if q and q not in json.dumps(item, ensure_ascii=False, default=str).lower():
            continue
        hits.append(_materialize_evidence(item))
    obj = {
        "kind": "field-flow-edge",
        "repository_id": resolved_repo_id,
        "analysis_out": str(resolved_out),
        "token": token,
        "hit_count": len(hits),
        "items": hits,
        "source_artifact": "catalog/field_flow_edges.json",
        "policy": "Each edge must have a concrete Tree-sitter AST basis and explicit resolution status.",
    }
    write_lazy(resolved_out, "field-flow-edge", token or "all", obj)
    return obj


def field_flow_neighborhood(
    analysis_out: Path,
    occurrence_id: str,
    repo_id: str | None = None,
    direction: str = "both",
    max_depth: int = 3,
    max_nodes: int = 100,
) -> dict[str, Any]:
    """Traverse the materialized immediate field-flow graph with strict bounds."""
    resolved_out, resolved_repo_id = _field_flow_analysis_out(analysis_out, repo_id)
    direction = str(direction or "both").lower()
    if direction not in {"in", "out", "both"}:
        raise ValueError("direction must be one of: in, out, both")
    max_depth = max(0, min(int(max_depth), 4))
    max_nodes = max(1, min(int(max_nodes), 500))
    occurrences = read_json(resolved_out / "catalog" / "field_occurrences.json", []) or []
    edges = read_json(resolved_out / "catalog" / "field_flow_edges.json", []) or []
    occurrence_by_id = {
        str(item.get("occurrence_id")): item
        for item in occurrences if isinstance(item, dict) and item.get("occurrence_id")
    }
    if occurrence_id not in occurrence_by_id:
        raise ValueError(f"field occurrence not found in repository analysis: {occurrence_id}")
    outgoing: dict[str, list[dict[str, Any]]] = {}
    incoming: dict[str, list[dict[str, Any]]] = {}
    for edge in edges if isinstance(edges, list) else []:
        if not isinstance(edge, dict):
            continue
        source_id = str(edge.get("source_occurrence_id") or "")
        target_id = str(edge.get("target_occurrence_id") or "")
        if source_id:
            outgoing.setdefault(source_id, []).append(edge)
        if target_id:
            incoming.setdefault(target_id, []).append(edge)
    for bucket in list(outgoing.values()) + list(incoming.values()):
        bucket.sort(key=lambda x: str(x.get("edge_id") or ""))

    visited = {occurrence_id}
    frontier = [(occurrence_id, 0)]
    selected_edges: dict[str, dict[str, Any]] = {}
    truncated = False
    while frontier:
        current_id, depth = frontier.pop(0)
        if depth >= max_depth:
            continue
        candidates: list[dict[str, Any]] = []
        if direction in {"out", "both"}:
            candidates.extend(outgoing.get(current_id, []))
        if direction in {"in", "both"}:
            candidates.extend(incoming.get(current_id, []))
        candidates.sort(key=lambda x: str(x.get("edge_id") or ""))
        for edge in candidates:
            edge_id = str(edge.get("edge_id") or "")
            if edge_id:
                selected_edges[edge_id] = edge
            next_id = str(edge.get("target_occurrence_id") if str(edge.get("source_occurrence_id")) == current_id else edge.get("source_occurrence_id") or "")
            if not next_id or next_id in visited:
                continue
            if len(visited) >= max_nodes:
                truncated = True
                frontier.clear()
                break
            visited.add(next_id)
            frontier.append((next_id, depth + 1))

    selected_occurrences = [occurrence_by_id[x] for x in sorted(visited) if x in occurrence_by_id]
    selected_edge_items = [selected_edges[x] for x in sorted(selected_edges)]
    obj = {
        "kind": "field-flow-neighborhood",
        "repository_id": resolved_repo_id,
        "analysis_out": str(resolved_out),
        "start_occurrence_id": occurrence_id,
        "direction": direction,
        "max_depth": max_depth,
        "max_nodes": max_nodes,
        "node_count": len(selected_occurrences),
        "edge_count": len(selected_edge_items),
        "truncated": truncated,
        "occurrences": selected_occurrences,
        "edges": selected_edge_items,
        "policy": "Bounded traversal of already materialized immediate AST-backed edges; no transitive semantic conclusion is produced.",
    }
    write_lazy(resolved_out, "field-flow-neighborhood", occurrence_id, obj)
    return obj


def field_lineage(analysis_out: Path, token: str = "", max_results: int = 50) -> dict[str, Any]:
    """Return Java field-level lineage evidence across ingress/outbound/storage boundaries."""
    return _search_json_artifacts(
        analysis_out, token, kind="field-lineage",
        files=[analysis_out / "compact" / "field_lineage.json", analysis_out / "facts" / "facts_by_type" / "field_lineage.json"],
        max_results=max_results,
    )


def output_field_provenance(analysis_out: Path, token: str = "", max_results: int = 50) -> dict[str, Any]:
    """Return provenance for Java fields published in REST/Kafka/HTTP or persisted to storage."""
    return _search_json_artifacts(
        analysis_out, token, kind="output-field-provenance",
        files=[analysis_out / "compact" / "output_field_provenance.json", analysis_out / "facts" / "facts_by_type" / "output_field_provenance.json"],
        max_results=max_results,
    )


def call_chain_diagnostic(analysis_out: Path, token: str = "", max_results: int = 50) -> dict[str, Any]:
    """Return diagnostics explaining why publisher/helper operations lack ingress/caller chains."""
    return _search_json_artifacts(
        analysis_out, token, kind="call-chain-diagnostic",
        files=[analysis_out / "compact" / "call_chain_diagnostics.json", analysis_out / "facts" / "facts_by_type" / "call_chain_diagnostic.json"],
        max_results=max_results,
    )


def _search_json_artifacts(analysis_out: Path, token: str, *, kind: str, files: list[Path], max_results: int = 50, type_filter: str | None = None, table_filter: str | None = None) -> dict[str, Any]:
    q = (token or "").lower()
    hits: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for path in files:
        if path.suffix.lower() == ".jsonl" and path.exists():
            items: list[dict[str, Any]] = []
            with path.open("r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        item = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(item, dict):
                        items.append(item)
        else:
            data = read_json(path, None)
            items = data if isinstance(data, list) else []
        for item in items:
            if len(hits) >= max_results:
                break
            item_type = item.get("trace_type") or (item.get("properties") or {}).get("trace_type")
            if type_filter and str(item_type or "") != type_filter:
                continue
            if table_filter and not _item_matches_table(item, table_filter):
                continue
            blob = json.dumps(item, ensure_ascii=False, default=str)
            if not q or q in blob.lower():
                rid = _record_id(item.get("properties") or {}) or _record_id(item) or blob[:160]
                if rid in seen_ids:
                    continue
                seen_ids.add(rid)
                hits.append({"source_file": str(path.relative_to(analysis_out)), "item": _materialize_evidence(item)})
        if len(hits) >= max_results:
            break
    if not hits and q:
        return _combined_artifact_and_source_search(analysis_out, token, kind=kind, max_results=max_results)
    obj = {"kind": kind, "token": token, "table_filter": table_filter, "hits": hits, "hit_count": len(hits)}
    write_lazy(analysis_out, kind, token or "all", obj)
    return obj


def ingress(analysis_out: Path, token: str = "", max_results: int = 50) -> dict[str, Any]:
    return _search_json_artifacts(
        analysis_out, token, kind="ingress",
        files=[analysis_out / "compact" / "ingress.json", analysis_out / "facts" / "facts_by_type" / "system_ingress.json"],
        max_results=max_results,
    )


def call(analysis_out: Path, token: str = "", max_results: int = 50) -> dict[str, Any]:
    return _search_json_artifacts(
        analysis_out, token, kind="call",
        files=[analysis_out / "compact" / "method_calls.json", analysis_out / "facts" / "facts_by_type" / "method_call.json"],
        max_results=max_results,
    )



def confirmed_evidence(analysis_out: Path, token: str = "", max_results: int = 50) -> dict[str, Any]:
    return _search_json_artifacts(
        analysis_out, token, kind="confirmed-evidence",
        files=[analysis_out / "compact" / "confirmed_evidence.json"],
        max_results=max_results,
    )


def candidate_signal(analysis_out: Path, token: str = "", max_results: int = 50) -> dict[str, Any]:
    return _search_json_artifacts(
        analysis_out, token, kind="candidate-signal",
        files=[analysis_out / "compact" / "candidate_signals.json"],
        max_results=max_results,
    )


def unresolved_gap(analysis_out: Path, token: str = "", max_results: int = 50) -> dict[str, Any]:
    return _search_json_artifacts(
        analysis_out, token, kind="unresolved-gap",
        files=[analysis_out / "compact" / "unresolved_gaps.json"],
        max_results=max_results,
    )

def storage_access(analysis_out: Path, token: str = "", max_results: int = 50) -> dict[str, Any]:
    return _search_json_artifacts(
        analysis_out, token, kind="storage-access",
        files=[analysis_out / "compact" / "storage_accesses.json", analysis_out / "facts" / "facts_by_type" / "storage_access.json"],
        max_results=max_results,
    )


def data_source(analysis_out: Path, token: str = "", max_results: int = 50) -> dict[str, Any]:
    return _search_json_artifacts(
        analysis_out, token, kind="data-source",
        files=[analysis_out / "compact" / "data_sources.json", analysis_out / "facts" / "facts_by_type" / "data_source.json"],
        max_results=max_results,
    )


def persistent_write(analysis_out: Path, token: str = "", max_results: int = 50, table: str | None = None) -> dict[str, Any]:
    return _search_json_artifacts(
        analysis_out, token, kind="persistent-write",
        files=[analysis_out / "compact" / "persistent_writes.json", analysis_out / "facts" / "facts_by_type" / "persistent_write.json"],
        max_results=max_results,
        table_filter=table,
    )


def source_to_storage_lineage(analysis_out: Path, token: str = "", max_results: int = 50, table: str | None = None) -> dict[str, Any]:
    return _search_json_artifacts(
        analysis_out, token, kind="source-to-storage-lineage",
        files=[analysis_out / "compact" / "source_to_storage_lineage.json", analysis_out / "facts" / "facts_by_type" / "source_to_storage_lineage.json"],
        max_results=max_results,
        table_filter=table,
    )


def storage_lineage_gap(analysis_out: Path, token: str = "", max_results: int = 50) -> dict[str, Any]:
    return _search_json_artifacts(
        analysis_out, token, kind="storage-lineage-gap",
        files=[analysis_out / "compact" / "storage_lineage_gaps.json", analysis_out / "facts" / "facts_by_type" / "storage_lineage_gap.json"],
        max_results=max_results,
    )


def read_from_storage(analysis_out: Path, token: str = "", max_results: int = 50) -> dict[str, Any]:
    return _search_json_artifacts(
        analysis_out, token, kind="read-from-storage",
        files=[analysis_out / "compact" / "read_from_storage.json", analysis_out / "facts" / "facts_by_type" / "read_from_storage.json"],
        max_results=max_results,
    )


def access_boundary(analysis_out: Path, token: str = "", max_results: int = 50) -> dict[str, Any]:
    return _search_json_artifacts(
        analysis_out, token, kind="access-boundary",
        files=[analysis_out / "compact" / "access_boundaries.json", analysis_out / "facts" / "facts_by_type" / "access_boundary.json"],
        max_results=max_results,
    )


def storage_to_access_lineage(analysis_out: Path, token: str = "", max_results: int = 50) -> dict[str, Any]:
    return _search_json_artifacts(
        analysis_out, token, kind="storage-to-access-lineage",
        files=[analysis_out / "compact" / "storage_to_access_lineage.json", analysis_out / "facts" / "facts_by_type" / "storage_to_access_lineage.json"],
        max_results=max_results,
    )


def stored_field_to_response_field_mapping(analysis_out: Path, token: str = "", max_results: int = 50) -> dict[str, Any]:
    return _search_json_artifacts(
        analysis_out, token, kind="stored-field-to-response-field-mapping",
        files=[analysis_out / "compact" / "stored_field_to_response_field_mappings.json", analysis_out / "facts" / "facts_by_type" / "stored_field_to_response_field_mapping.json"],
        max_results=max_results,
    )


def _facts_by_type_items(analysis_out: Path, fact_type: str) -> list[dict[str, Any]]:
    full_path = _full_fact_path(analysis_out, fact_type)
    if full_path.exists():
        return _read_jsonl_rows(full_path)
    data = read_json(analysis_out / "facts" / "facts_by_type" / f"{fact_type}.json", []) or []
    return data if isinstance(data, list) else []


def _compact_or_facts(analysis_out: Path, compact_name: str, fact_type: str) -> list[dict[str, Any]]:
    data = read_json(analysis_out / "compact" / f"{compact_name}.json", None)
    if isinstance(data, list):
        return data
    return _facts_by_type_items(analysis_out, fact_type)


def _item_matches_blob(item: dict[str, Any], token: str) -> bool:
    if not token:
        return True
    try:
        return token.lower() in json.dumps(item, ensure_ascii=False, default=str).lower()
    except Exception:
        return token.lower() in str(item).lower()





def _item_matches_table(item: dict[str, Any], table: str | None) -> bool:
    if not table:
        return True
    q = str(table or "").lower()
    props = item.get("properties") if isinstance(item.get("properties"), dict) else item
    values = []
    for key in ["storage_target", "storage_table", "table_or_repository", "table_name", "source_table", "target_table"]:
        value = props.get(key) if isinstance(props, dict) else None
        if isinstance(value, list):
            values.extend(str(x).lower() for x in value)
        elif value is not None:
            values.append(str(value).lower())
    for group_key in ["write_target_fields", "where_key_fields", "source_to_saved_field_mappings"]:
        for entry in (props.get(group_key) if isinstance(props, dict) else None) or []:
            if isinstance(entry, dict):
                values.extend(str(entry.get(k) or "").lower() for k in ["storage_table", "storage_target"])
    return any(v == q or v.endswith("." + q) for v in values if v)


def java_lineage_patterns(analysis_out: Path, token: str = "", max_results: int = 100) -> dict[str, Any]:
    return _search_json_artifacts(
        analysis_out, token, kind="java-lineage-patterns",
        files=[analysis_out / "facts" / "facts_by_type" / "java_lineage_pattern.json"],
        max_results=max_results,
    )


def jooq_batch_bind_mappings(analysis_out: Path, token: str = "", max_results: int = 100, table: str | None = None) -> dict[str, Any]:
    return _search_json_artifacts(
        analysis_out, token, kind="jooq-batch-bind-mappings",
        files=[analysis_out / "facts" / "facts_by_type" / "jooq_batch_bind_mapping.json"],
        max_results=max_results,
        table_filter=table,
    )


def jooq_parameterized_sql_mappings(analysis_out: Path, token: str = "", max_results: int = 100) -> dict[str, Any]:
    return _search_json_artifacts(
        analysis_out, token, kind="jooq-parameterized-sql-mappings",
        files=[analysis_out / "facts" / "facts_by_type" / "jooq_parameterized_sql_mapping.json"],
        max_results=max_results,
    )


def spring_component_dependencies(analysis_out: Path, token: str = "", max_results: int = 100) -> dict[str, Any]:
    return _search_json_artifacts(
        analysis_out, token, kind="spring-component-dependencies",
        files=[analysis_out / "facts" / "facts_by_type" / "spring_component_dependency.json"],
        max_results=max_results,
    )


def template_method_dispatches(analysis_out: Path, token: str = "", max_results: int = 100) -> dict[str, Any]:
    return _search_json_artifacts(
        analysis_out, token, kind="template-method-dispatches",
        files=[analysis_out / "facts" / "facts_by_type" / "template_method_dispatch.json"],
        max_results=max_results,
    )


def factory_method_mappings(analysis_out: Path, token: str = "", max_results: int = 100) -> dict[str, Any]:
    return _search_json_artifacts(
        analysis_out, token, kind="factory-method-mappings",
        files=[analysis_out / "facts" / "facts_by_type" / "factory_method_mapping.json"],
        max_results=max_results,
    )


def builder_field_mappings(analysis_out: Path, token: str = "", max_results: int = 100) -> dict[str, Any]:
    return _search_json_artifacts(
        analysis_out, token, kind="builder-field-mappings",
        files=[analysis_out / "facts" / "facts_by_type" / "builder_field_mapping.json"],
        max_results=max_results,
    )


def stream_collection_lineages(analysis_out: Path, token: str = "", max_results: int = 100) -> dict[str, Any]:
    return _search_json_artifacts(
        analysis_out, token, kind="stream-collection-lineages",
        files=[analysis_out / "facts" / "facts_by_type" / "stream_collection_lineage.json"],
        max_results=max_results,
    )

def mapstruct_mapper_signatures(analysis_out: Path, token: str = "", max_results: int = 100) -> dict[str, Any]:
    return _search_json_artifacts(
        analysis_out, token, kind="mapstruct-mapper-signatures",
        files=[analysis_out / "facts" / "facts_by_type" / "mapstruct_mapper_signature.json"],
        max_results=max_results,
    )


def stored_data_access(analysis_out: Path, token: str = "", max_results: int = 50) -> dict[str, Any]:
    writes = [x for x in _compact_or_facts(analysis_out, "persistent_writes", "persistent_write") if _item_matches_blob(x, token)]
    reads = [x for x in _compact_or_facts(analysis_out, "read_from_storage", "read_from_storage") if _item_matches_blob(x, token)]
    boundaries = [x for x in _compact_or_facts(analysis_out, "access_boundaries", "access_boundary") if _item_matches_blob(x, token)]
    lineages = [x for x in _compact_or_facts(analysis_out, "storage_to_access_lineage", "storage_to_access_lineage") if _item_matches_blob(x, token)]
    mappings = [x for x in _compact_or_facts(analysis_out, "stored_field_to_response_field_mappings", "stored_field_to_response_field_mapping") if _item_matches_blob(x, token)]
    gaps = [x for x in _compact_or_facts(analysis_out, "storage_lineage_gaps", "storage_lineage_gap") if _item_matches_blob(x, token)]
    requests = [x for x in _compact_or_facts(analysis_out, "source_inspection_requests", "source_inspection_request") if _item_matches_blob(x, token)]

    read_by_id = {str(x.get("read_from_storage_id") or (x.get("properties") or {}).get("read_from_storage_id") or ""): x for x in reads}
    boundary_by_id = {str(x.get("access_boundary_id") or (x.get("properties") or {}).get("access_boundary_id") or ""): x for x in boundaries}
    mapping_by_lineage: dict[str, list[dict[str, Any]]] = {}
    for m in mappings:
        props = m.get("properties") or m
        lid = str(props.get("storage_to_access_lineage_id") or "")
        mapping_by_lineage.setdefault(lid, []).append(m)

    scenarios: list[dict[str, Any]] = []
    for idx, lin in enumerate(lineages[:max_results], start=1):
        props = lin.get("properties") or lin
        lid = str(props.get("storage_to_access_lineage_id") or props.get("evidence_id") or f"storage_to_access_lineage_{idx:06d}")
        rid = str(props.get("read_evidence_ref") or "")
        aid = str(props.get("access_evidence_ref") or "")
        read = read_by_id.get(rid, {})
        boundary = boundary_by_id.get(aid, {})
        read_props = read.get("properties") or read
        boundary_props = boundary.get("properties") or boundary
        related_mappings = mapping_by_lineage.get(lid, [])
        overlap = []
        for mp in related_mappings[:100]:
            mprops = mp.get("properties") or mp
            overlap.append({
                "saved_field": mprops.get("storage_field"),
                "exposed_field": mprops.get("response_field"),
                "mapping_type": mprops.get("mapping_type"),
                "evidence_level": mprops.get("evidence_level") or mprops.get("evidence_maturity_level"),
            })
        status = str(props.get("lineage_status") or "unresolved")
        if status == "confirmed" and overlap:
            access_status = "confirmed_same_saved_data_access_candidate"
        elif status == "confirmed":
            access_status = "access_found_field_overlap_missing"
        else:
            access_status = "access_found_same_data_unresolved"
        scenarios.append({
            "scenario_id": f"stored_data_access_{idx:06d}",
            "access_status": access_status,
            "persistence_side": {
                "write_evidence_refs": [x.get("persistent_write_id") or (x.get("properties") or {}).get("persistent_write_id") for x in writes[:20]],
                "writes_available_count": len(writes),
                "note": "writes are listed for correlation; the analyzer does not decide foreign-data risk",
            },
            "access_side": {
                "read_evidence_ref": rid,
                "access_evidence_ref": aid,
                "storage_object": read_props.get("storage_object") or props.get("source_storage_object"),
                "read_symbol": read_props.get("storage_symbol"),
                "boundary_kind": boundary_props.get("boundary_kind"),
                "endpoint_or_topic": boundary_props.get("endpoint_or_topic"),
                "response_or_payload_type": boundary_props.get("response_or_payload_type"),
                "exposed_fields": boundary_props.get("fields") or [],
            },
            "same_data_status": "confirmed_same_data" if status == "confirmed" and overlap else "unresolved",
            "field_overlap": overlap,
            "lineage": lin,
            "gaps": [g for g in gaps if _item_matches_blob(g, str(read_props.get("storage_object") or props.get("source_storage_object") or ""))][:20],
        })

    if writes and not boundaries:
        for idx, w in enumerate(writes[:max_results], start=1):
            wprops = w.get("properties") or w
            scenarios.append({
                "scenario_id": f"stored_data_access_save_only_{idx:06d}",
                "access_status": "no_access_found",
                "persistence_side": {
                    "write_evidence_ref": wprops.get("persistent_write_id"),
                    "storage_object": wprops.get("saved_object"),
                    "storage_target": wprops.get("storage_target"),
                    "saved_fields": wprops.get("written_fields") or [],
                },
                "access_side": {
                    "read_evidence_ref": None,
                    "access_evidence_ref": None,
                    "boundary_kind": None,
                    "endpoint_or_topic": None,
                    "exposed_fields": [],
                },
                "same_data_status": "unresolved",
                "field_overlap": [],
                "gaps": ["access_boundary_not_found"],
            })

    scenarios = scenarios[:max_results]
    obj = {
        "kind": "stored-data-access",
        "analysis_out": str(analysis_out),
        "filters": {"token": token},
        "selection_policy": "materialize storage-to-access lineages first; if none and writes exist, materialize save-only scenarios; no risk decision is made by analyzer",
        "counts": {
            "persistent_writes": len(writes),
            "read_from_storage": len(reads),
            "access_boundaries": len(boundaries),
            "storage_to_access_lineages": len(lineages),
            "stored_field_mappings": len(mappings),
            "storage_lineage_gaps": len(gaps),
            "source_inspection_requests": len(requests),
        },
        "total_count": max(len(lineages), len(writes) if not boundaries else len(lineages)),
        "included_count": len(scenarios),
        "omitted_count": max(0, max(len(lineages), len(writes) if not boundaries else len(lineages)) - len(scenarios)),
        "materialization_status": "full" if len(scenarios) >= max(len(lineages), len(writes) if not boundaries else len(lineages)) else "truncated",
        "stored_data_access": scenarios,
        "policy": {
            "analyzer_role": "evidence_only_no_risk_decision",
            "llm_rule": "risk requires persistence-side foreign/external saved data plus access-side same saved data exposure; save-only is not confirmed risk",
            "strict_levels": ["confirmed", "unresolved", "not_applicable"],
        },
    }
    write_lazy(analysis_out, "stored-data-access", token or "all", obj)
    return obj



# ---------------------------------------------------------------------------
# System data-model description views
# ---------------------------------------------------------------------------

def _props(item: dict[str, Any]) -> dict[str, Any]:
    return item.get("properties") if isinstance(item.get("properties"), dict) else item


def _item_id(item: dict[str, Any]) -> str | None:
    props = _props(item)
    return _record_id(props) or _record_id(item)


def _locations_from_item(item: dict[str, Any]) -> list[dict[str, Any]]:
    evs = item.get("evidence") or _props(item).get("evidence") or []
    out: list[dict[str, Any]] = []
    if isinstance(evs, list):
        for ev in evs:
            if not isinstance(ev, dict):
                continue
            out.append({k: ev.get(k) for k in ["file", "file_path", "line_start", "line_end", "extractor", "snippet"] if ev.get(k) is not None})
    return out


def _evidence_refs(item: dict[str, Any]) -> list[str]:
    props = _props(item)
    refs: list[str] = []
    for key in ["source_evidence_refs", "evidence_refs", "related_evidence_refs"]:
        value = props.get(key) or item.get(key)
        if isinstance(value, list):
            refs.extend(str(x) for x in value if x)
        elif isinstance(value, str) and value:
            refs.append(value)
    rid = _item_id(item)
    if rid:
        refs.insert(0, rid)
    # stable unique order
    seen: set[str] = set()
    out: list[str] = []
    for ref in refs:
        if ref in seen:
            continue
        seen.add(ref)
        out.append(ref)
    return out


def _strict_evidence_level(item: dict[str, Any], *, default: str = "unresolved") -> str:
    props = _props(item)
    raw = str(props.get("evidence_level") or props.get("evidence_maturity_level") or props.get("lineage_status") or props.get("trace_status") or default).lower()
    if raw in {"confirmed", "confirmed_by_analyzer", "confirmed_by_static_analysis"}:
        return "confirmed_by_analyzer"
    if raw in {"confirmed_by_llm_source_inspection"}:
        return "confirmed_by_llm_source_inspection"
    if raw in {"candidate", "candidate_signal", "candidate_signal_navigation_only"}:
        return "candidate_signal_navigation_only"
    if raw in {"not_applicable"}:
        return "not_applicable"
    return "unresolved"


def _provenance(item: dict[str, Any], source_artifact: str) -> dict[str, Any]:
    refs = _evidence_refs(item)
    locations = _locations_from_item(item)
    return {
        "source_artifact": source_artifact,
        "evidence_refs": refs,
        "locations": locations[:3],
        "provenance_status": "present" if refs or locations else "missing",
    }


def _ddl_scope_from_locations(locations: list[dict[str, Any]]) -> str:
    path = " ".join(str(x.get("file") or x.get("file_path") or "") for x in locations).replace("\\", "/").lower()
    if "/src/test/" in path or "/test/" in path:
        return "test_resource"
    if "/src/main/" in path or "/main/" in path:
        return "production_resource"
    return "unknown"


def _split_sql_columns(body: str) -> list[str]:
    parts: list[str] = []
    cur: list[str] = []
    depth = 0
    for ch in body:
        if ch == "(":
            depth += 1
        elif ch == ")" and depth:
            depth -= 1
        if ch == "," and depth == 0:
            s = "".join(cur).strip()
            if s:
                parts.append(s)
            cur = []
        else:
            cur.append(ch)
    s = "".join(cur).strip()
    if s:
        parts.append(s)
    return parts


def _columns_from_sql_statement(statement: str, columns_hint: list[Any] | None = None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    text = statement or ""
    m = re.search(r"\bcreate\s+table\s+[a-zA-Z0-9_.$\"{}]+\s*\((.*)\)", text, re.IGNORECASE | re.DOTALL)
    if m:
        for raw in _split_sql_columns(m.group(1)):
            line = " ".join(raw.strip().split())
            if not line:
                continue
            low = line.lower()
            if low.startswith(("constraint ", "primary key", "foreign key", "unique ", "check ")):
                continue
            tokens = line.split()
            if not tokens:
                continue
            name = tokens[0].strip('"`[]')
            dtype = tokens[1] if len(tokens) > 1 else "unknown"
            nullable = None if " not null" not in low else False
            constraints = []
            if "primary key" in low:
                constraints.append("primary_key")
            if "unique" in low:
                constraints.append("unique")
            out.append({"name": name, "type": dtype, "nullable": nullable, "description": None, "constraints": constraints, "evidence_level": "confirmed_by_analyzer"})
    if not out and columns_hint:
        for c in columns_hint:
            if isinstance(c, str):
                out.append({"name": c, "type": "unknown", "nullable": None, "description": None, "constraints": [], "evidence_level": "confirmed_by_analyzer"})
    return out


def _table_name_from_sql_fact(item: dict[str, Any]) -> str | None:
    props = _props(item)
    for key in ["table", "target_table", "object_name", "name"]:
        v = props.get(key) or item.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip().strip('"')
    tables = props.get("tables") or []
    if isinstance(tables, list) and tables:
        return str(tables[0]).strip('"')
    return None


def _sql_create_facts(analysis_out: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for path in sorted((analysis_out / "facts" / "facts_by_type").glob("sql_*.json")):
        if "create" not in path.stem.lower():
            continue
        data = read_json(path, []) or []
        if isinstance(data, list):
            out.extend([x for x in data if isinstance(x, dict)])
    # Some installations only expose SQL facts through confirmed_evidence.
    ce = read_json(analysis_out / "compact" / "confirmed_evidence.json", []) or []
    if isinstance(ce, list):
        for item in ce:
            blob = json.dumps(item, ensure_ascii=False, default=str).lower()
            if "create" in blob and ("table" in blob or "view" in blob):
                out.append(item)
    return out



def _db_schema_items(analysis_out: Path, name: str) -> list[dict[str, Any]]:
    data = read_json(analysis_out / "compact" / f"{name}.json", None)
    if isinstance(data, list):
        return data
    data = read_json(analysis_out / "sql" / f"{name}.json", [])
    return data if isinstance(data, list) else []


def db_schema_overview(analysis_out: Path, token: str = "", max_results: int = 10000) -> dict[str, Any]:
    overview = read_json(analysis_out / "compact" / "db_schema_overview.json", None)
    if not isinstance(overview, dict):
        overview = read_json(analysis_out / "sql" / "db_schema_overview.json", {}) or {}
    tables = [x for x in _db_schema_items(analysis_out, "db_schema_tables") if _item_matches_blob(x, token)]
    relationships = [x for x in _db_schema_items(analysis_out, "db_schema_relationships") if _item_matches_blob(x, token)]
    obj = {
        "kind": "db-schema-overview",
        "analysis_out": str(analysis_out),
        "token": token,
        "overview": overview,
        "matched_tables_sample": tables[:max_results],
        "matched_relationships_sample": relationships[:max_results],
        "policy": "physical DB model extracted from schema-bearing sources such as jOOQ generated classes; use DDL/SQL lineage as complementary evidence",
    }
    write_lazy(analysis_out, "db-schema-overview", token or "all", obj)
    return obj


def db_table_catalog(analysis_out: Path, token: str = "", max_results: int = 10000) -> dict[str, Any]:
    tables = [x for x in _db_schema_items(analysis_out, "db_schema_tables") if _item_matches_blob(x, token)]
    selected = tables[:max_results]
    obj = {
        "kind": "db-table-catalog",
        "analysis_out": str(analysis_out),
        "token": token,
        "selection_policy": "confirmed physical DB tables from schema-bearing generated classes and DB schema artifacts",
        "matched_count": len(tables),
        "included_count": len(selected),
        "items": selected,
    }
    write_lazy(analysis_out, "db-table-catalog", token or "all", obj)
    return obj


def db_column_catalog(analysis_out: Path, token: str = "", max_results: int = 10000) -> dict[str, Any]:
    cols = [x for x in _db_schema_items(analysis_out, "db_schema_columns") if _item_matches_blob(x, token)]
    selected = cols[:max_results]
    obj = {
        "kind": "db-column-catalog",
        "analysis_out": str(analysis_out),
        "token": token,
        "selection_policy": "confirmed physical DB columns from schema-bearing generated classes",
        "matched_count": len(cols),
        "included_count": len(selected),
        "items": selected,
    }
    write_lazy(analysis_out, "db-column-catalog", token or "all", obj)
    return obj


def db_relationship_catalog(analysis_out: Path, token: str = "", max_results: int = 10000) -> dict[str, Any]:
    rels = [x for x in _db_schema_items(analysis_out, "db_schema_relationships") if _item_matches_blob(x, token)]
    selected = rels[:max_results]
    obj = {
        "kind": "db-relationship-catalog",
        "analysis_out": str(analysis_out),
        "token": token,
        "selection_policy": "confirmed DB relationships, primarily foreign keys from jOOQ Keys.java",
        "matched_count": len(rels),
        "included_count": len(selected),
        "items": selected,
    }
    write_lazy(analysis_out, "db-relationship-catalog", token or "all", obj)
    return obj


def db_index_catalog(analysis_out: Path, token: str = "", max_results: int = 10000) -> dict[str, Any]:
    idx = [x for x in _db_schema_items(analysis_out, "db_schema_indexes") if _item_matches_blob(x, token)]
    selected = idx[:max_results]
    obj = {
        "kind": "db-index-catalog",
        "analysis_out": str(analysis_out),
        "token": token,
        "selection_policy": "confirmed DB indexes from jOOQ Indexes.java",
        "matched_count": len(idx),
        "included_count": len(selected),
        "items": selected,
    }
    write_lazy(analysis_out, "db-index-catalog", token or "all", obj)
    return obj


def db_table_detail(analysis_out: Path, token: str, max_results: int = 10000) -> dict[str, Any]:
    table_token = token or ""
    tables = [x for x in _db_schema_items(analysis_out, "db_schema_tables") if _item_matches_blob(x, table_token)]
    table_names = {str(t.get("table_name") or "").lower() for t in tables}
    cols = [x for x in _db_schema_items(analysis_out, "db_schema_columns") if str(x.get("table_name") or "").lower() in table_names or _item_matches_blob(x, table_token)]
    keys = [x for x in _db_schema_items(analysis_out, "db_schema_keys") if str(x.get("table_name") or "").lower() in table_names or _item_matches_blob(x, table_token)]
    rels = [x for x in _db_schema_items(analysis_out, "db_schema_relationships") if str(x.get("source_table") or "").lower() in table_names or str(x.get("target_table") or "").lower() in table_names or _item_matches_blob(x, table_token)]
    idx = [x for x in _db_schema_items(analysis_out, "db_schema_indexes") if str(x.get("table_name") or "").lower() in table_names or _item_matches_blob(x, table_token)]
    obj = {
        "kind": "db-table-detail",
        "analysis_out": str(analysis_out),
        "token": token,
        "tables": tables[:max_results],
        "columns": cols[:max_results],
        "keys": keys[:max_results],
        "relationships": rels[:max_results],
        "indexes": idx[:max_results],
        "hit_count": len(tables) + len(cols) + len(keys) + len(rels) + len(idx),
    }
    write_lazy(analysis_out, "db-table-detail", token or "all", obj)
    return obj


# ---------------------------------------------------------------------------
# Generic evidence facets added after real-application research
# ---------------------------------------------------------------------------

_WORD_SPLIT_RE = re.compile(r"[^a-z0-9]+")


def _norm_model_token(value: Any) -> str:
    text = normalize_name(str(value or ""))
    return re.sub(r"[^a-z0-9]", "", text)


def _scope_from_file_path(value: Any) -> str:
    path = str(value or "").replace("\\", "/").lower()
    if "/src/test/" in path or "/test/" in path or "mockito" in path:
        return "test_code"
    if "/generated/" in path or "/target/generated" in path or "/build/generated" in path:
        return "generated_code"
    if "/src/main/resources/" in path or path.endswith((".yml", ".yaml", ".properties")):
        return "config_or_resource"
    if path.endswith((".sql", ".ddl")) or "changelog" in path or "liquibase" in path:
        return "migration_sql"
    if "/src/main/" in path or "/main/" in path:
        return "production_code"
    return "unknown"


def _scope_from_item(item: dict[str, Any]) -> str:
    props = _props(item)
    candidates: list[str] = []
    for key in ["file", "file_path"]:
        if props.get(key) or item.get(key):
            candidates.append(_scope_from_file_path(props.get(key) or item.get(key)))
    for loc in _locations_from_item(item):
        candidates.append(_scope_from_file_path(loc.get("file") or loc.get("file_path")))
    for scope in ["production_code", "test_code", "generated_code", "migration_sql", "config_or_resource"]:
        if scope in candidates:
            return scope
    return candidates[0] if candidates else "unknown"


def _table_name_observations(table_name: Any, description: Any = None) -> dict[str, Any]:
    """Publish literal naming-pattern observations without assigning a table role."""
    name = normalize_name(str(table_name or ""))
    desc = normalize_name(str(description or ""))
    text = f"{name} {desc}"
    observed_patterns: list[str] = []
    if any(tok in name for tok in ["history", "hist", "audit", "journal", "log"]):
        observed_patterns.append("name_contains_history_audit_token")
    if name.endswith("_history") or name.endswith("history") or name.endswith("_hist"):
        observed_patterns.append("history_table_naming_pattern")
    if any(tok in text for tok in ["try_count", "planned_send", "planed_send", "processing", "retry", "queue", "event"]):
        observed_patterns.append("transport_or_retry_token_observed")
    if any(tok in name for tok in ["config", "setting", "settings", "white_list", "whitelist"]):
        observed_patterns.append("configuration_naming_token_observed")
    if any(tok in name for tok in ["dictionary", "dict", "tarif", "terbank", "operator", "product_price", "state", "code", "limit", "external_system_map"]):
        observed_patterns.append("dictionary_or_reference_naming_token_observed")
    if name.endswith("_link") or name == "link" or "link" in name:
        observed_patterns.append("link_naming_token_observed")
    if name.endswith("_info") or name.endswith("info"):
        observed_patterns.append("info_suffix_observed")
    return {"normalized_table_name": name, "observed_name_patterns": sorted(set(observed_patterns))}


def _db_unique_columns(keys: list[dict[str, Any]], indexes: list[dict[str, Any]]) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for k in keys:
        kind = str(k.get("constraint_kind") or "").lower()
        if kind not in {"primary_key", "unique_key"}:
            continue
        table = str(k.get("table_name") or "")
        cols = [str(c) for c in (k.get("columns") or []) if c]
        if table and len(cols) == 1:
            out.setdefault(table.lower(), set()).add(cols[0].lower())
    for idx in indexes:
        if not idx.get("unique"):
            continue
        table = str(idx.get("table_name") or "")
        cols = [str(c) for c in (idx.get("columns") or []) if c]
        if table and len(cols) == 1:
            out.setdefault(table.lower(), set()).add(cols[0].lower())
    return out


def _relationship_cardinality(src_table: str, src_cols: list[str], tgt_table: str, tgt_cols: list[str], unique_cols: dict[str, set[str]]) -> str:
    src_unique = len(src_cols) == 1 and src_cols[0].lower() in unique_cols.get(src_table.lower(), set())
    tgt_unique = len(tgt_cols) == 1 and tgt_cols[0].lower() in unique_cols.get(tgt_table.lower(), set())
    if src_unique and tgt_unique:
        return "one_to_zero_or_one_candidate"
    if src_unique and not tgt_unique:
        return "one_to_many_candidate"
    if tgt_unique and not src_unique:
        return "many_to_one_candidate"
    return "many_to_many_or_unknown"


def _build_access_exposure(analysis_out: Path) -> dict[str, dict[str, Any]]:
    reads = _compact_or_facts(analysis_out, "read_from_storage", "read_from_storage")
    lineages = _compact_or_facts(analysis_out, "storage_to_access_lineage", "storage_to_access_lineage")
    boundaries = _compact_or_facts(analysis_out, "access_boundaries", "access_boundary")
    boundary_by_id = {str((_props(b).get("access_boundary_id") or _item_id(b) or "")): b for b in boundaries}
    by_table: dict[str, dict[str, Any]] = {}
    for r in reads:
        rp = _props(r)
        table = str(rp.get("storage_object") or rp.get("storage_symbol") or rp.get("table_name") or "").strip()
        if not table:
            continue
        card = by_table.setdefault(table.lower(), {
            "table": table,
            "read_count": 0,
            "read_by_external_endpoint": False,
            "read_contexts": {},
            "endpoints": [],
            "evidence_refs": [],
        })
        card["read_count"] += 1
        rid = _item_id(r)
        if rid:
            card["evidence_refs"].append(rid)
    for lin in lineages:
        lp = _props(lin)
        table = str(lp.get("source_storage_object") or lp.get("storage_object") or lp.get("storage_target") or "").strip()
        if not table:
            continue
        card = by_table.setdefault(table.lower(), {
            "table": table,
            "read_count": 0,
            "read_by_external_endpoint": False,
            "read_contexts": {},
            "endpoints": [],
            "evidence_refs": [],
        })
        card["read_contexts"]["response_building"] = card["read_contexts"].get("response_building", 0) + 1
        card["read_by_external_endpoint"] = True
        bid = str(lp.get("access_evidence_ref") or "")
        bp = _props(boundary_by_id.get(bid, {}) or {})
        endpoint = bp.get("endpoint_or_topic") or lp.get("access_boundary") or bp.get("operation")
        if endpoint and endpoint not in card["endpoints"]:
            card["endpoints"].append(endpoint)
        rid = _item_id(lin)
        if rid:
            card["evidence_refs"].append(rid)
    for card in by_table.values():
        card["evidence_refs"] = _fdp_unique_strings(card.get("evidence_refs") or [])
    return by_table


def _infer_domain_key_relationships(tables: list[dict[str, Any]], columns: list[dict[str, Any]], keys: list[dict[str, Any]], indexes: list[dict[str, Any]], existing_keys: set[tuple[str, str, str, str]], max_items: int = 500) -> list[dict[str, Any]]:
    unique_cols = _db_unique_columns(keys, indexes)
    by_norm: dict[str, list[tuple[str, str, bool]]] = {}
    for col in columns:
        table = str(col.get("table_name") or "")
        column = str(col.get("column_name") or "")
        if not table or not column:
            continue
        norm = _norm_model_token(column)
        if len(norm) < 3:
            continue
        is_unique = column.lower() in unique_cols.get(table.lower(), set())
        if is_unique or norm in {"ucpid", "ucp", "clientid", "deviceid", "phonenumber", "cardnumber", "phoneid", "cardid"}:
            by_norm.setdefault(norm, []).append((table, column, is_unique))
    out: list[dict[str, Any]] = []
    for norm, refs in sorted(by_norm.items()):
        if len(refs) < 2 or len(refs) > 20:
            continue
        for i in range(len(refs)):
            for j in range(i + 1, len(refs)):
                lt, lc, lu = refs[i]
                rt, rc, ru = refs[j]
                key = (lt.lower(), lc.lower(), rt.lower(), rc.lower())
                rev = (rt.lower(), rc.lower(), lt.lower(), lc.lower())
                if key in existing_keys or rev in existing_keys:
                    continue
                if not (lu or ru):
                    continue
                rid = f"data_model_relation_{_hash(lt + '.' + lc + '->' + rt + '.' + rc)[:16]}"
                out.append({
                    "relationship_id": rid,
                    "relationship_kind": "same_normalized_domain_key_observation",
                    "left": {"table": lt, "columns": [lc]},
                    "right": {"table": rt, "columns": [rc]},
                    "left_column_unique": bool(lu),
                    "right_column_unique": bool(ru),
                    "declared_fk": False,
                    "observations": ["same_normalized_domain_key", "unique_index_or_key_present"],
                    "evidence_refs": [],
                })
                existing_keys.add(key)
                if len(out) >= max_items:
                    return out
    return out


def data_model_relationships(analysis_out: Path, token: str = "", max_results: int = 10000) -> dict[str, Any]:
    tables = [x for x in _db_schema_items(analysis_out, "db_schema_tables") if _item_matches_blob(x, token)]
    keys = _db_schema_items(analysis_out, "db_schema_keys")
    indexes = _db_schema_items(analysis_out, "db_schema_indexes")
    rels = _db_schema_items(analysis_out, "db_schema_relationships")
    jpa_rels = _facts_by_type_items(analysis_out, "jpa_relationship")
    sql_join_observations = _facts_by_type_items(analysis_out, "sql_join_observation")
    access_by_table = _build_access_exposure(analysis_out)

    relationship_observations: list[dict[str, Any]] = []
    for relation in rels:
        relationship_observations.append({
            "relationship_id": relation.get("db_schema_relationship_id") or _item_id(relation),
            "observation_kind": "declared_foreign_key",
            "left": {
                "table": relation.get("source_table"),
                "schema": relation.get("source_schema"),
                "columns": relation.get("source_columns") or [],
            },
            "right": {
                "table": relation.get("target_table"),
                "schema": relation.get("target_schema"),
                "columns": relation.get("target_columns") or [],
            },
            "constraint_name": relation.get("constraint_name"),
            "source_type": relation.get("source_type"),
            "evidence_refs": _evidence_refs(relation),
        })

    for relation in jpa_rels:
        props = relation.get("properties") if isinstance(relation.get("properties"), dict) else relation
        relationship_observations.append({
            "relationship_id": relation.get("fact_id") or props.get("jpa_relationship_id") or _item_id(relation),
            "observation_kind": "jpa_relationship_declaration",
            "relationship_kind": props.get("relationship_kind"),
            "left": {
                "entity": props.get("source_entity"),
                "field": props.get("source_field"),
                "table_identity": props.get("source_table_identity"),
            },
            "right": {"entity": props.get("target_entity"), "type": props.get("target_type")},
            "join_columns": props.get("join_columns") or [],
            "mapped_by": props.get("mapped_by"),
            "optional": props.get("optional"),
            "evidence_refs": relation.get("evidence") or _evidence_refs(relation),
        })

    for observation in sql_join_observations:
        props = observation.get("properties") if isinstance(observation.get("properties"), dict) else observation
        relationship_observations.append({
            "relationship_id": observation.get("fact_id") or _item_id(observation),
            "observation_kind": "native_sql_join_usage",
            "left": {"table": props.get("source_table"), "alias": props.get("source_alias")},
            "right": {"table": props.get("target_table"), "alias": props.get("target_alias")},
            "join_condition": props.get("join_condition_preview"),
            "evidence_refs": observation.get("evidence") or _evidence_refs(observation),
        })

    alternate_keys: list[dict[str, Any]] = []
    for key in keys:
        if str(key.get("constraint_kind") or "").lower() in {"primary_key", "unique_key"}:
            alternate_keys.append({
                "table": key.get("table_name"),
                "schema": key.get("schema_name"),
                "columns": key.get("columns") or [],
                "constraint_kind": key.get("constraint_kind"),
                "constraint_name": key.get("constraint_name"),
                "evidence_refs": _evidence_refs(key),
            })
    for index in indexes:
        if index.get("unique"):
            alternate_keys.append({
                "table": index.get("table_name"),
                "schema": index.get("schema_name"),
                "columns": index.get("columns") or [],
                "constraint_kind": "unique_index",
                "constraint_name": index.get("index_name"),
                "evidence_refs": _evidence_refs(index),
            })

    selected_relationships = [x for x in relationship_observations if _item_matches_blob(x, token)][:max_results]
    obj = {
        "kind": "data-model-relationships",
        "analysis_out": str(analysis_out),
        "token": token,
        "selection_policy": "directly observed database constraints, ORM declarations and SQL join expressions only; no role, ownership, cardinality or domain-relation inference",
        "summary": {
            "tables": len(tables),
            "declared_foreign_keys": len(rels),
            "jpa_relationship_declarations": len(jpa_rels),
            "sql_join_observations": len(sql_join_observations),
            "relationship_observations_included": len(selected_relationships),
            "declared_unique_or_primary_keys": len(alternate_keys),
            "tables_with_access_exposure": sum(1 for x in access_by_table.values() if x.get("read_by_external_endpoint")),
        },
        "tables": tables[:max_results],
        "declared_keys": alternate_keys[:max_results],
        "relationship_observations": selected_relationships,
        "access_exposure": [x for x in access_by_table.values() if _item_matches_blob(x, token)][:max_results],
        "policy": {
            "analyzer_role": "evidence_only_no_business_decision",
            "semantic_classification_performed": False,
            "inferred_table_roles_emitted": False,
            "inferred_domain_relationships_emitted": False,
        },
    }
    write_lazy(analysis_out, "data-model-relationships", token or "all", obj)
    return obj

def _operation_semantics_from_boundary(card: dict[str, Any]) -> str:
    text = normalize_name(" ".join(str(card.get(k) or "") for k in ["operation", "method_name", "endpoint_or_topic", "request_type", "response_type", "payload_type", "description"]))
    method = str(card.get("http_method") or "").upper()
    if any(x in text for x in ["health", "reconfigure", "configuration", "dictionary", "tables"]):
        return "admin_or_dictionary"
    if any(x in text for x in ["update", "modify", "change", "disable", "enable", "set", "register", "sync", "remove", "delete", "block", "unblock"]):
        return "write_or_command"
    if method in {"GET"} or any(x in text for x in ["get", "find", "profile", "list", "info", "history", "bycard", "byucp"]):
        return "read_or_access"
    if str(card.get("source_kind") or card.get("kind") or "").lower() == "kafka":
        return "async_event"
    return "unknown"


def _storage_object_from_item(item: dict[str, Any]) -> str | None:
    p = _props(item)
    for key in ["storage_target", "storage_object", "saved_object", "table_name", "storage_symbol", "source_storage_object"]:
        v = p.get(key) or item.get(key)
        if v:
            return str(v)
    return None


def _source_scan_boundary_hints(analysis_out: Path, *, max_results: int = 200) -> list[dict[str, Any]]:
    hints: list[dict[str, Any]] = []
    try:
        repo = repo_from_analysis(analysis_out)
    except Exception:
        return hints
    patterns = [
        ("external_procedure_call", "callProcedure"),
        ("outbound_kafka", "KafkaTemplate"),
        ("outbound_kafka", "ProducerRecord"),
        ("cache", "@Cacheable"),
        ("cache", "@CachePut"),
        ("scheduled_job", "AbstractSingleThreadJob"),
    ]
    seen: set[tuple[str, str, int]] = set()
    for kind, token in patterns:
        for hit in search_repo(repo, token, max_results=max_results, context=2):
            path = str(hit.get("file") or "")
            line = int(hit.get("line") or hit.get("line_start") or 0)
            key = (kind, path, line)
            if key in seen:
                continue
            seen.add(key)
            hints.append({
                "boundary_id": f"source_hint_{kind}_{_hash(path + ':' + str(line))[:12]}",
                "direction": "outbound" if kind in {"external_procedure_call", "outbound_kafka"} else ("cache" if kind == "cache" else "scheduled"),
                "boundary_kind": kind,
                "observed_pattern_kind": "source_search_boundary_token",
                "source_scope": _scope_from_file_path(path),
                "file": path,
                "line_start": line,
                "snippet": hit.get("snippet"),
                "evidence_basis": [f"source_search_token:{token}"],
            })
            if len(hints) >= max_results:
                return hints
    return hints


def system_boundaries(analysis_out: Path, token: str = "", max_results: int = 10000) -> dict[str, Any]:
    events = _event_sources(analysis_out, max_results=max_results)
    writes = _compact_or_facts(analysis_out, "persistent_writes", "persistent_write")
    reads = _compact_or_facts(analysis_out, "read_from_storage", "read_from_storage")
    access = _compact_or_facts(analysis_out, "access_boundaries", "access_boundary")
    cards: list[dict[str, Any]] = []
    for ev in events:
        direction = ev.get("direction") or "unknown"
        kind = ev.get("kind") or ev.get("source_kind") or "unknown"
        card = {
            "boundary_id": ev.get("event_source_id") or ev.get("interface_id") or ev.get("ingress_id") or ev.get("access_boundary_id"),
            "direction": direction,
            "boundary_kind": kind,
            "operation": ev.get("operation"),
            "class_name": ev.get("class_name"),
            "method_name": ev.get("method_name"),
            "endpoint_or_topic": ev.get("endpoint_or_topic"),
            "endpoint_or_topic_raw": ev.get("endpoint_or_topic_raw"),
            "endpoint_or_topic_resolution_status": ev.get("endpoint_or_topic_resolution_status"),
            "topic_setting": ev.get("topic_name_raw") if kind == "kafka" else None,
            "http_method": ev.get("http_method"),
            "request_type": ev.get("request_type"),
            "response_type": ev.get("response_type"),
            "payload_type": ev.get("payload_type"),
            "source_scope": _scope_from_item(ev),
            "evidence_origin": ev.get("evidence_origin") or ev.get("evidence_level"),
            "evidence_refs": ((ev.get("provenance") or {}).get("evidence_refs") or []),
        }
        card["operation_semantics"] = _operation_semantics_from_boundary(card)
        cards.append(card)
    for w in writes:
        p = _props(w)
        storage = _storage_object_from_item(w)
        card = {
            "boundary_id": p.get("persistent_write_id") or _item_id(w),
            "direction": "local_persistence",
            "boundary_kind": "Database",
            "operation": p.get("operation") or p.get("method_name"),
            "operation_kind": p.get("write_kind") or p.get("operation_kind"),
            "storage_object": storage,
            "storage_name_observations": _table_name_observations(storage) if storage else {},
            "write_fields": p.get("written_fields") or p.get("saved_fields") or [],
            "source_scope": _scope_from_item(w),
            "evidence_refs": _evidence_refs(w),
            "operation_semantics": "local_storage_write",
        }
        cards.append(card)
    for r in reads:
        p = _props(r)
        storage = _storage_object_from_item(r)
        cards.append({
            "boundary_id": p.get("read_from_storage_id") or _item_id(r),
            "direction": "local_read",
            "boundary_kind": "Database",
            "operation": p.get("operation") or p.get("method_name"),
            "storage_object": storage,
            "storage_name_observations": _table_name_observations(storage) if storage else {},
            "source_scope": _scope_from_item(r),
            "evidence_refs": _evidence_refs(r),
            "operation_semantics": "local_storage_read",
        })
    for a in access:
        p = _props(a)
        cards.append({
            "boundary_id": p.get("access_boundary_id") or _item_id(a),
            "direction": "outbound",
            "boundary_kind": p.get("boundary_kind") or "access_boundary",
            "operation": p.get("operation") or p.get("method_name"),
            "endpoint_or_topic": p.get("endpoint_or_topic"),
            "response_type": p.get("response_or_payload_type"),
            "payload_type": p.get("payload_type") or p.get("response_or_payload_type"),
            "source_scope": _scope_from_item(a),
            "evidence_refs": _evidence_refs(a),
            "operation_semantics": "outbound_or_response_access",
        })
    cards.extend(_source_scan_boundary_hints(analysis_out, max_results=min(max_results, 200)))
    filtered = [c for c in cards if _item_matches_blob(c, token)]
    selected = filtered[:max_results]
    summary_counts: dict[str, int] = {}
    for c in filtered:
        key = f"{c.get('direction')}:{c.get('boundary_kind')}"
        summary_counts[key] = summary_counts.get(key, 0) + 1
    obj = {
        "kind": "system-boundaries",
        "analysis_out": str(analysis_out),
        "token": token,
        "selection_policy": "system boundary evidence cards for REST/Kafka/jobs/outbound/storage/cache; analyzer reports technical boundaries and does not make business conclusions",
        "summary": {
            "total_boundaries": len(filtered),
            "included_count": len(selected),
            "by_direction_and_kind": summary_counts,
        },
        "items": selected,
        "policy": {
            "analyzer_role": "evidence_only_no_business_decision",
            "operation_semantics_rule": "read/write/command/admin are technical classifications inferred from code patterns and must not be treated as business risk decisions",
            "source_scan_hints_rule": "source_search_token hints are candidate evidence; use exact cards/refs before asserting confirmed flows",
        },
    }
    write_lazy(analysis_out, "system-boundaries", token or "all", obj)
    return obj

def _physical_table_items(analysis_out: Path, *, max_results: int = 10000) -> list[dict[str, Any]]:
    tables: dict[str, dict[str, Any]] = {}

    for item in _db_schema_items(analysis_out, "db_schema_tables"):
        name = str(item.get("table_name") or "").strip()
        if not name:
            continue
        cols = [
            {
                "name": c.get("column_name"),
                "type": c.get("sql_type") or "unknown",
                "java_type": c.get("java_type"),
                "nullable": c.get("nullable"),
                "description": c.get("description"),
                "constraints": [],
                "evidence_level": "confirmed_by_analyzer",
            }
            for c in _db_schema_items(analysis_out, "db_schema_columns")
            if str(c.get("table_name") or "").lower() == name.lower()
        ]
        tables[name.lower()] = {
            "table_name": name,
            "schema_name": item.get("schema_name"),
            "object_type": "physical_table",
            "classification_status": "confirmed_physical_table",
            "description": item.get("description"),
            "columns": cols,
            "keys": item.get("primary_keys") or [],
            "relationships": item.get("foreign_keys_out") or [],
            "indexes": item.get("indexes") or [],
            "ddl_scope": "production_resource" if "/src/main/" in str(item.get("file") or "") else "unknown",
            "evidence_level": "confirmed_by_analyzer",
            "provenance": {"source": "db_schema", "file": item.get("file"), "line_start": item.get("line_start")},
        }

    for item in _sql_create_facts(analysis_out):
        props = _props(item)
        name = _table_name_from_sql_fact(item)
        if not name:
            continue
        statement = str(props.get("statement_preview") or "")
        cols = _columns_from_sql_statement(statement, props.get("columns") if isinstance(props.get("columns"), list) else None)
        locs = _locations_from_item(item)
        existing = tables.setdefault(name.lower(), {
            "table_name": name,
            "schema_name": name.split(".")[0] if "." in name else None,
            "object_type": "physical_table",
            "classification_status": "confirmed_physical_table",
            "description": None,
            "columns": [],
            "keys": [],
            "relationships": [],
            "ddl_scope": _ddl_scope_from_locations(locs),
            "evidence_level": "confirmed_by_analyzer",
            "provenance": _provenance(item, "sql_ddl"),
        })
        known = {str(c.get("name") or "").lower() for c in existing.get("columns") or []}
        for col in cols:
            if str(col.get("name") or "").lower() not in known:
                existing["columns"].append(col)
                known.add(str(col.get("name") or "").lower())

    for item in _compact_or_facts(analysis_out, "persistent_structures", "persistent_structure"):
        props = _props(item)
        name = str(props.get("storage_target") or props.get("container_name") or "").strip()
        if not name:
            continue
        fields = []
        for f in props.get("fields") or []:
            if isinstance(f, dict):
                fields.append({
                    "name": f.get("db_column_name") or f.get("attribute_name") or f.get("name"),
                    "type": f.get("type") or f.get("attribute_type") or "unknown",
                    "nullable": f.get("nullable"),
                    "description": f.get("description"),
                    "constraints": f.get("constraints") or [],
                    "evidence_level": _strict_evidence_level(item, default="confirmed"),
                })
        existing = tables.setdefault(name.lower(), {
            "table_name": name,
            "schema_name": None,
            "object_type": "physical_table" if props.get("storage_kind") == "database" else "storage_target",
            "classification_status": "confirmed_physical_table" if props.get("storage_kind") == "database" else "candidate_storage_target",
            "description": None,
            "columns": [],
            "keys": [],
            "relationships": [],
            "ddl_scope": "unknown",
            "evidence_level": _strict_evidence_level(item, default="confirmed"),
            "provenance": _provenance(item, "persistent_structure"),
        })
        known = {str(c.get("name") or "").lower() for c in existing.get("columns") or []}
        for col in fields:
            if col.get("name") and str(col.get("name")).lower() not in known:
                existing["columns"].append(col)
                known.add(str(col.get("name")).lower())

    return list(tables.values())[:max_results]


def system_table_catalog(analysis_out: Path, token: str = "", max_results: int = 10000) -> dict[str, Any]:
    items = [x for x in _physical_table_items(analysis_out, max_results=100000) if _item_matches_blob(x, token)]
    total = len(items)
    selected = items[:max_results]
    obj = {
        "kind": "system-table-catalog",
        "analysis_out": str(analysis_out),
        "token": token,
        "selection_policy": "physical tables and storage targets from DB schema, SQL DDL and persistent-structure evidence; DDL scope is production/test/unknown by source path",
        "total_count": total,
        "matched_count": total,
        "included_count": len(selected),
        "omitted_count": max(0, total - len(selected)),
        "materialization_status": "full" if total <= len(selected) else "truncated",
        "items": selected,
    }
    write_lazy(analysis_out, "system-table-catalog", token or "all", obj)
    return obj


def _attribute_objects(analysis_out: Path, *, max_results: int = 10000) -> list[dict[str, Any]]:
    by_container: dict[str, dict[str, Any]] = {}
    for item in _compact_or_facts(analysis_out, "attribute_occurrences", "attribute_occurrence"):
        props = _props(item)
        cname = str(props.get("container_name") or "unknown")
        ckind = str(props.get("container_kind") or "java_object")
        obj = by_container.setdefault(cname, {
            "object_name": cname,
            "object_type": ckind,
            "classification_status": ckind,
            "fields": [],
            "evidence_level": _strict_evidence_level(item, default="confirmed"),
            "provenance": _provenance(item, "attribute_occurrence"),
        })
        field_name = props.get("attribute_name") or props.get("field_name")
        if field_name:
            obj["fields"].append({
                "name": field_name,
                "type": props.get("attribute_type") or props.get("field_type") or "unknown",
                "role": props.get("attribute_role"),
                "description": props.get("description"),
                "evidence_level": _strict_evidence_level(item, default="confirmed"),
                "provenance": _provenance(item, "attribute_occurrence"),
            })
    return list(by_container.values())[:max_results]


def _description_hints(analysis_out: Path, *, max_results: int = 20) -> list[dict[str, Any]]:
    hints: list[dict[str, Any]] = []
    manifest = read_json(analysis_out / "manifest.json", {}) or {}
    for key in ["project_code", "system_name", "repo_id"]:
        value = manifest.get(key)
        if value:
            hints.append({"source": "manifest", "text": f"{key}: {value}", "evidence_ref": "manifest.json"})
    try:
        repo = repo_from_analysis(analysis_out)
        for name in ["README.md", "readme.md", "README.txt"]:
            path = repo / name
            if path.exists():
                text = read_text(path).strip()
                if text:
                    hints.append({"source": "README", "text": text[:1000], "evidence_ref": str(path)})
                    break
        for p in list(repo.rglob("application*.yml"))[:3] + list(repo.rglob("application*.yaml"))[:3] + list(repo.rglob("application*.properties"))[:3]:
            text = read_text(p)
            for line in text.splitlines():
                if "spring.application.name" in line or "application:" in line or "name:" in line:
                    hints.append({"source": "application_config", "text": line.strip()[:300], "evidence_ref": str(p)})
                    break
            if len(hints) >= max_results:
                break
    except Exception:
        pass
    return hints[:max_results]



_PLACEHOLDER_RE = re.compile(r"\$\{([^}:]+)(?::([^}]*))?\}")


def _config_property_map(analysis_out: Path) -> dict[str, Any]:
    props: dict[str, Any] = {}
    for item in _facts_by_type_items(analysis_out, "config_property"):
        name = str(item.get("name") or (item.get("properties") or {}).get("name") or "")
        val = (item.get("properties") or {}).get("value")
        if name:
            props[name] = val
    return props


def _resolve_config_placeholder(value: Any, config: dict[str, Any]) -> tuple[Any, str, str | None]:
    """Resolve simple ${property[:default]} references without inventing values."""
    if value is None:
        return None, "missing", "value is not present in extracted evidence"
    text = str(value)
    m = _PLACEHOLDER_RE.fullmatch(text.strip())
    if not m:
        if _PLACEHOLDER_RE.search(text):
            # Mixed SpEL/property expressions are intentionally not guessed.
            return text, "unresolved_config_binding", "value contains embedded property/SpEL expression that was not resolved deterministically"
        return value, "literal", None
    key, default = m.group(1), m.group(2)
    if key in config:
        return config.get(key), "resolved_config_property", None
    if default not in (None, ""):
        return default, "resolved_default_value", None
    return text, "unresolved_config_binding", f"configuration property {key!r} was not found in extracted config facts"


def _operation_parts(operation: Any) -> tuple[str | None, str | None]:
    op = str(operation or "")
    if "." not in op:
        return (op or None), None
    cls, meth = op.rsplit(".", 1)
    return (cls or None), (meth or None)


def _operation_id_by_interface(nav: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for op in nav.get("operations") or []:
        if not isinstance(op, dict):
            continue
        oid = op.get("id")
        for iid in op.get("interfaces") or []:
            if iid and oid:
                out[str(iid)] = str(oid)
    return out


def _resolution_fields(kind: str, raw_value: Any, config: dict[str, Any]) -> dict[str, Any]:
    resolved, status, reason = _resolve_config_placeholder(raw_value, config)
    out: dict[str, Any] = {
        "endpoint_or_topic": resolved,
        "endpoint_or_topic_raw": raw_value,
        "endpoint_or_topic_resolution_status": status,
    }
    if kind == "kafka":
        out["topic_name"] = resolved if status not in {"missing"} else None
        out["topic_name_raw"] = raw_value
        out["topic_resolution_status"] = status
    elif kind == "rest":
        out["endpoint_path"] = resolved if status not in {"missing"} else None
        out["endpoint_path_raw"] = raw_value
        out["path_resolution_status"] = status
    if reason:
        out["unresolved_reason"] = reason
    return out


def _event_sources(analysis_out: Path, *, max_results: int = 1000) -> list[dict[str, Any]]:
    attrs_by_container = {x["object_name"]: x.get("fields") or [] for x in _attribute_objects(analysis_out, max_results=max_results * 2)}
    config = _config_property_map(analysis_out)
    sources: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()

    def add_source(raw: dict[str, Any]) -> None:
        key = (
            raw.get("direction"), raw.get("kind") or raw.get("source_kind"), raw.get("operation"),
            raw.get("endpoint_or_topic"), raw.get("payload_type"), raw.get("interface_id"), raw.get("ingress_id"), raw.get("access_boundary_id"),
        )
        if key in seen:
            return
        seen.add(key)
        raw.setdefault("event_source_id", f"event_source_{len(sources)+1:06d}")
        raw.setdefault("evidence_origin", "analyzer_observation")
        raw.pop("confidence", None)
        sources.append(raw)

    nav = read_json(analysis_out / "compact" / "navigation.json", {}) or {}
    op_by_interface = _operation_id_by_interface(nav)
    interfaces = nav.get("interfaces") or []
    for idx, it in enumerate([x for x in interfaces if isinstance(x, dict)], start=1):
        blob = json.dumps(it, ensure_ascii=False, default=str).lower()
        direction = str(it.get("direction") or "").lower() or ("inbound" if any(x in blob for x in ["rest", "controller", "requestmapping", "getmapping", "postmapping"]) else "internal")
        if direction not in {"inbound", "outbound"} and not any(x in blob for x in ["rest", "kafka", "http", "api", "controller", "listener", "scheduled"]):
            continue
        payload = it.get("schema_ref") or it.get("request_type") or it.get("payload_type") or it.get("response_type")
        kind = str(it.get("kind") or "unknown").lower()
        if "kafka" in blob:
            kind = "kafka"
        elif "rest" in blob or "controller" in blob or "mapping" in blob:
            kind = "rest"
        elif "scheduled" in blob:
            kind = "scheduler"
        raw_endpoint = it.get("path") or it.get("endpoint") or it.get("topic") or it.get("name")
        cls, meth = _operation_parts(it.get("operation"))
        resolved = _resolution_fields(kind, raw_endpoint, config)
        add_source({
            "interface_id": it.get("id") or f"interface_{idx:06d}",
            "operation_id": op_by_interface.get(str(it.get("id") or "")),
            "source_kind": kind,
            "kind": kind,
            "direction": direction or "internal",
            "operation": it.get("operation") or it.get("operation_id") or it.get("method") or it.get("name"),
            "class_name": cls,
            "method_name": meth,
            "controller_class": cls if kind == "rest" else None,
            "listener_class": cls if kind == "kafka" and direction == "inbound" else None,
            "producer_class": cls if kind == "kafka" and direction == "outbound" else None,
            **resolved,
            "http_method": it.get("method") if kind == "rest" else None,
            "request_type": payload if direction == "inbound" else None,
            "response_type": payload if direction == "outbound" and kind == "rest" else None,
            "payload_type": payload,
            "description": it.get("description") or _short_summary(it),
            "input_attributes": attrs_by_container.get(str(payload), [])[:200],
            "evidence_level": "confirmed_by_analyzer",
            "provenance": {"source_artifact": "navigation.interfaces", "evidence_refs": [str(it.get("id") or it.get("name") or f"interface_{idx}")]},
        })
        if len(sources) >= max_results:
            return sources

    for item in _compact_or_facts(analysis_out, "ingress", "system_ingress"):
        props = _props(item)
        payload = props.get("source_payload") or props.get("payload_type") or props.get("request_type")
        kind = props.get("origin_kind") or props.get("ingress_kind") or "unknown"
        if kind == "rest_controller":
            kind_norm = "rest"
        elif kind == "kafka_listener":
            kind_norm = "kafka"
        else:
            kind_norm = str(kind or "unknown")
        raw_endpoint = props.get("endpoint_or_topic") or props.get("endpoint") or props.get("topic")
        cls = props.get("class_name")
        meth = props.get("method_name")
        if not cls or not meth:
            cls2, meth2 = _operation_parts(props.get("operation") or props.get("ingress_operation_id"))
            cls = cls or cls2
            meth = meth or meth2
        resolved = _resolution_fields(kind_norm, raw_endpoint, config)
        add_source({
            "ingress_id": props.get("ingress_id") or _item_id(item),
            "operation_id": props.get("operation_id") or props.get("ingress_operation_id"),
            "source_kind": kind_norm,
            "kind": kind_norm,
            "direction": "inbound",
            "operation": props.get("ingress_operation_id") or props.get("operation") or props.get("method_name"),
            "class_name": cls,
            "method_name": meth,
            "controller_class": cls if kind_norm == "rest" else None,
            "listener_class": cls if kind_norm == "kafka" else None,
            **resolved,
            "request_type": payload,
            "payload_type": payload,
            "payload_parameter": props.get("payload_parameter"),
            "description": props.get("reason") or _short_summary(props),
            "input_attributes": attrs_by_container.get(str(payload), [])[:200],
            "evidence_level": _strict_evidence_level(item, default="confirmed"),
            "provenance": _provenance(item, "system_ingress"),
        })
        if len(sources) >= max_results:
            return sources

    for item in _compact_or_facts(analysis_out, "access_boundaries", "access_boundary"):
        props = _props(item)
        payload = props.get("response_or_payload_type") or props.get("payload_type")
        kind = props.get("boundary_kind") or "unknown"
        if kind in {"kafka_publish", "kafka", "kafka_producer"}:
            kind_norm = "kafka"
        elif kind in {"rest", "http", "rest_response", "http_client"}:
            kind_norm = "rest" if kind != "http_client" else "http"
        else:
            kind_norm = str(kind)
        raw_endpoint = props.get("endpoint_or_topic")
        cls, meth = _operation_parts(props.get("operation") or props.get("method_name"))
        resolved = _resolution_fields(kind_norm, raw_endpoint, config)
        add_source({
            "access_boundary_id": props.get("access_boundary_id") or _item_id(item),
            "operation_id": props.get("operation_id") or props.get("operation"),
            "source_kind": kind_norm,
            "kind": kind_norm,
            "direction": "outbound",
            "operation": props.get("method_name") or props.get("operation"),
            "class_name": cls,
            "method_name": meth,
            "producer_class": cls if kind_norm == "kafka" else None,
            **resolved,
            "response_type": payload if kind_norm in {"rest", "http"} else None,
            "payload_type": payload,
            "description": _short_summary(props),
            "input_attributes": attrs_by_container.get(str(payload), [])[:200],
            "evidence_level": _strict_evidence_level(item, default="confirmed"),
            "provenance": _provenance(item, "access_boundary"),
        })
        if len(sources) >= max_results:
            return sources
    return sources[:max_results]


def event_source_catalog(analysis_out: Path, token: str = "", max_results: int = 10000) -> dict[str, Any]:
    items = [x for x in _event_sources(analysis_out, max_results=max_results) if _item_matches_blob(x, token)]
    total = len(items)
    selected = items[:max_results]
    obj = {
        "kind": "event-source-catalog",
        "analysis_out": str(analysis_out),
        "token": token,
        "selection_policy": "REST/Kafka/scheduler/outbound event source index from navigation.interfaces, system_ingress and access_boundary evidence; no fake ids are generated",
        "total_count": total,
        "matched_count": total,
        "included_count": len(selected),
        "omitted_count": max(0, total - len(selected)),
        "materialization_status": "full" if total <= len(selected) else "truncated",
        "items": selected,
    }
    write_lazy(analysis_out, "event-source-catalog", token or "all", obj)
    return obj


def system_scenario_catalog(analysis_out: Path, token: str = "", max_results: int = 10000) -> dict[str, Any]:
    event_sources = _event_sources(analysis_out, max_results=max_results)
    items = [x for x in _scenario_items(analysis_out, event_sources, max_results=max_results) if _item_matches_blob(x, token)]
    total = len(items)
    selected = items[:max_results]
    obj = {
        "kind": "system-scenario-catalog",
        "analysis_out": str(analysis_out),
        "token": token,
        "selection_policy": "Compact scenario index inferred from source-to-storage, storage-to-access and event source evidence; scenarios are evidence navigation objects, not business decisions",
        "total_count": total,
        "matched_count": total,
        "included_count": len(selected),
        "omitted_count": max(0, total - len(selected)),
        "materialization_status": "full" if total <= len(selected) else "truncated",
        "items": selected,
    }
    write_lazy(analysis_out, "system-scenario-catalog", token or "all", obj)
    return obj


def _mapping_items(analysis_out: Path, *, max_results: int = 10000) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []

    def append_mapping(item: dict[str, Any], source_artifact: str, *, props: dict[str, Any] | None = None) -> bool:
        props = props or _props(item)
        out.append({
            "mapping_id": _item_id(item),
            "source_attribute": props.get("source_field") or props.get("storage_field"),
            "source_object": props.get("source_container") or props.get("storage_object") or props.get("read_type"),
            "target_attribute": props.get("target_field") or props.get("response_field"),
            "target_object": props.get("target_container") or props.get("response_or_payload_type"),
            "mapping_type": props.get("mapping_kind") or props.get("mapping_type") or props.get("derivation_kind") or "unknown",
            "expression": props.get("expression") or props.get("derivation_expression"),
            "evidence_level": _strict_evidence_level(item, default="confirmed" if source_artifact == "attribute_mapping" else "unresolved"),
            "provenance": _provenance(item, source_artifact),
            "source_scope": props.get("source_scope") or _fdp_source_scope(item),
        })
        return len(out) >= max_results

    for source_artifact, compact_name, fact_type in [
        ("attribute_mapping", "attribute_mappings", "attribute_mapping"),
        ("attribute_derivation", "attribute_derivations", "attribute_derivation"),
        ("stored_field_to_response_field_mapping", "stored_field_to_response_field_mappings", "stored_field_to_response_field_mapping"),
    ]:
        for item in _compact_or_facts(analysis_out, compact_name, fact_type):
            if append_mapping(item, source_artifact):
                return out

    # Deep Java lineage hints are not confirmed mappings by themselves. They are
    # made visible here so derived FDP views can explain a candidate
    # source->saved-field segment when the hint target is the same saved object.
    for source_artifact, compact_name, fact_type, id_key in [
        ("factory_method_mapping", "factory_method_mappings", "factory_method_mapping", "factory_method_mapping_id"),
        ("builder_field_mapping", "builder_field_mappings", "builder_field_mapping", "builder_field_mapping_id"),
    ]:
        for item in _compact_or_facts(analysis_out, compact_name, fact_type):
            props = _props(item)
            target_container = props.get("target_container") or props.get("target_object") or props.get("saved_object")
            if not target_container:
                candidates = _fdp_unique_strings(_fdp_list(props.get("target_container_candidates")))
                if len(candidates) == 1:
                    target_container = candidates[0]
            for idx, fm in enumerate(_fdp_list(props.get("field_mappings")), start=1):
                if not isinstance(fm, dict):
                    continue
                target_attr = fm.get("target_field") or fm.get("target_attribute") or fm.get("storage_field") or fm.get("storage_attribute")
                if not target_attr:
                    continue
                source_attr = fm.get("source_field") or fm.get("source_attribute")
                mapping_id = f"{props.get(id_key) or _item_id(item) or source_artifact}:{idx}"
                out.append({
                    "mapping_id": mapping_id,
                    "source_attribute": source_attr,
                    "source_object": fm.get("source_object") or fm.get("source_container"),
                    "target_attribute": target_attr,
                    "target_object": fm.get("target_container") or target_container or fm.get("target_object") or fm.get("saved_object"),
                    "mapping_type": fm.get("mapping_kind") or props.get("mapping_kind") or source_artifact,
                    "expression": fm.get("expression") or fm.get("source_expression"),
                    "evidence_level": "candidate_signal_navigation_only",
                    "provenance": _provenance(item, source_artifact),
                    "source_scope": props.get("source_scope") or _fdp_source_scope(item),
                    "evidence_policy": props.get("evidence_policy") or "local Java mapping hint only; not confirmed source-to-storage persistence evidence",
                })
                if len(out) >= max_results:
                    return out

    # jOOQ positional mappings are technical bind-order hints.  Only SET/write
    # slots are exposed as source->saved candidates; WHERE/key slots are
    # deliberately kept out of saved-field mappings to avoid presenting
    # filter/key values as persisted foreign data.
    for source_artifact, compact_name, fact_type, id_key, default_kind in [
        ("jooq_batch_bind_mapping", "jooq_batch_bind_mappings", "jooq_batch_bind_mapping", "jooq_batch_bind_mapping_id", "jooq_batch_bind_order"),
        ("jooq_parameterized_sql_mapping", "jooq_parameterized_sql_mappings", "jooq_parameterized_sql_mapping", "jooq_parameterized_sql_mapping_id", "jooq_parameterized_bind_order"),
    ]:
        for item in _compact_or_facts(analysis_out, compact_name, fact_type):
            props = _props(item)
            target_container = props.get("storage_table") or props.get("storage_table_ref") or props.get("target_table")
            mappings = _fdp_list(props.get("write_target_fields"))
            if not mappings:
                mappings = [m for m in _fdp_list(props.get("mappings")) if isinstance(m, dict) and m.get("field_role") == "write_target_field"]
            for idx, fm in enumerate(mappings, start=1):
                if not isinstance(fm, dict):
                    continue
                target_attr = fm.get("storage_field") or fm.get("storage_attribute") or fm.get("target_field") or fm.get("target_attribute")
                if not target_attr:
                    continue
                source_attr = fm.get("source_field") or fm.get("source_attribute")
                source_expr = fm.get("source_expression") or fm.get("expression")
                mapping_id = f"{props.get(id_key) or _item_id(item) or source_artifact}:{idx}"
                out.append({
                    "mapping_id": mapping_id,
                    "source_attribute": source_attr,
                    "source_object": fm.get("source_object") or fm.get("source_container"),
                    "target_attribute": target_attr,
                    "target_object": target_container,
                    "mapping_type": fm.get("mapping_kind") or props.get("mapping_kind") or default_kind,
                    "expression": source_expr,
                    "evidence_level": "candidate_signal_navigation_only",
                    "provenance": _provenance(item, source_artifact),
                    "source_scope": props.get("source_scope") or _fdp_source_scope(item),
                    "evidence_policy": props.get("evidence_policy") or "jOOQ/SQL bind-order mapping is technical candidate evidence; WHERE/key slots are not treated as saved fields",
                    "field_role": "write_target_field",
                })
                if len(out) >= max_results:
                    return out

    # MapStruct/mapper signatures are object-level bridges. If explicit
    # @Mapping(source=..., target=...) annotations are available, expose those as
    # candidate field mappings; otherwise keep the fact as object_bridge_only.
    for item in _compact_or_facts(analysis_out, "mapstruct_mapper_signatures", "mapstruct_mapper_signature"):
        props = _props(item)
        source_object = props.get("source_container") or props.get("source_object")
        target_object = props.get("target_container") or props.get("target_object")
        if not (source_object or target_object):
            continue
        field_mappings = [m for m in _fdp_list(props.get("field_mappings")) if isinstance(m, dict)]
        for idx, fm in enumerate(field_mappings, start=1):
            target_attr = fm.get("target_field") or fm.get("target_attribute") or fm.get("target_path")
            source_attr = fm.get("source_field") or fm.get("source_attribute") or fm.get("source_path")
            if not target_attr:
                continue
            out.append({
                "mapping_id": f"{props.get('mapstruct_mapper_signature_id') or _item_id(item) or 'mapstruct_mapper_signature'}:{idx}",
                "source_attribute": source_attr,
                "source_object": fm.get("source_object") or source_object,
                "target_attribute": target_attr,
                "target_object": fm.get("target_container") or target_object,
                "mapping_type": fm.get("mapping_kind") or "mapstruct_annotation_field_mapping",
                "expression": fm.get("expression") or props.get("operation") or props.get("method_name"),
                "evidence_level": "candidate_signal_navigation_only",
                "provenance": _provenance(item, "mapstruct_mapper_signature"),
                "source_scope": props.get("source_scope") or _fdp_source_scope(item),
                "evidence_policy": props.get("evidence_policy") or "MapStruct annotation field mapping is candidate only; generated implementation/runtime persistence is not confirmed",
                "object_bridge_only": False,
            })
            if len(out) >= max_results:
                return out
        out.append({
            "mapping_id": props.get("mapstruct_mapper_signature_id") or _item_id(item),
            "source_attribute": None,
            "source_object": source_object,
            "target_attribute": None,
            "target_object": target_object,
            "mapping_type": props.get("mapping_kind") or "mapstruct_mapper_signature",
            "expression": props.get("operation") or props.get("method_name"),
            "evidence_level": "candidate_signal_navigation_only",
            "provenance": _provenance(item, "mapstruct_mapper_signature"),
            "source_scope": props.get("source_scope") or _fdp_source_scope(item),
            "evidence_policy": props.get("evidence_policy") or "mapper signature is object-level bridge only; no field-level mapping confirmed",
            "object_bridge_only": True,
        })
        if len(out) >= max_results:
            return out

    # Stream/collection facts do not carry field-level mappings on their own.
    # When a stream mapper method also has local factory/builder field mapping
    # evidence, expose an extra candidate object bridge so FDP can explain
    # collection input -> mapped record -> batch write without upgrading the
    # chain to confirmed.
    stream_mapper_methods: dict[str, list[dict[str, Any]]] = {}
    for stream_item in _compact_or_facts(analysis_out, "stream_collection_lineages", "stream_collection_lineage"):
        sp = _props(stream_item)
        mapper_names: set[str] = set()
        for ref in _fdp_list(sp.get("method_references")):
            if not isinstance(ref, dict):
                continue
            method_name = _fdp_concrete_text(ref.get("method"))
            if method_name:
                mapper_names.add(method_name)
        for mapped in _fdp_list(sp.get("mapped_collection_candidates")):
            if not isinstance(mapped, dict):
                continue
            method_name = _fdp_concrete_text(mapped.get("mapper_method") or mapped.get("method"))
            if method_name:
                mapper_names.add(method_name)
        for method_name in mapper_names:
            stream_mapper_methods.setdefault(method_name, []).append({"item": stream_item, "props": sp})

    if stream_mapper_methods:
        for source_artifact, compact_name, fact_type, id_key in [
            ("factory_method_mapping", "factory_method_mappings", "factory_method_mapping", "factory_method_mapping_id"),
            ("builder_field_mapping", "builder_field_mappings", "builder_field_mapping", "builder_field_mapping_id"),
        ]:
            for item in _compact_or_facts(analysis_out, compact_name, fact_type):
                props = _props(item)
                method_name = _fdp_concrete_text(props.get("method_name"))
                if not method_name:
                    op_name = _fdp_concrete_text(props.get("operation"))
                    method_name = op_name.split(".")[-1] if op_name and "." in op_name else op_name
                if not method_name or method_name not in stream_mapper_methods:
                    continue
                target_container = props.get("target_container") or props.get("target_object") or props.get("saved_object")
                if not target_container:
                    candidates = _fdp_unique_strings(_fdp_list(props.get("target_container_candidates")))
                    if len(candidates) == 1:
                        target_container = candidates[0]
                for stream_ctx in stream_mapper_methods.get(method_name, []):
                    stream_props = stream_ctx["props"]
                    stream_item = stream_ctx["item"]
                    source_collection = stream_props.get("source_collection")
                    source_element_type = stream_props.get("source_element_type") or stream_props.get("source_collection_element_type")
                    for idx, fm in enumerate(_fdp_list(props.get("field_mappings")), start=1):
                        if not isinstance(fm, dict):
                            continue
                        target_attr = fm.get("target_field") or fm.get("target_attribute") or fm.get("storage_field") or fm.get("storage_attribute")
                        if not target_attr:
                            continue
                        source_attr = fm.get("source_field") or fm.get("source_attribute")
                        mapping_id = f"{props.get(id_key) or _item_id(item) or source_artifact}:stream:{stream_props.get('stream_collection_lineage_id') or _item_id(stream_item) or method_name}:{idx}"
                        out.append({
                            "mapping_id": mapping_id,
                            "source_attribute": source_attr,
                            "source_object": source_element_type or source_collection or fm.get("source_object") or fm.get("source_container"),
                            "target_attribute": target_attr,
                            "target_object": fm.get("target_container") or target_container or fm.get("target_object") or fm.get("saved_object"),
                            "mapping_type": f"stream_collection_{fm.get('mapping_kind') or props.get('mapping_kind') or source_artifact}",
                            "expression": fm.get("expression") or fm.get("source_expression"),
                            "evidence_level": "candidate_signal_navigation_only",
                            "provenance": {
                                "source_artifact": "stream_collection_lineage+" + source_artifact,
                                "evidence_refs": _fdp_unique_strings((_provenance(item, source_artifact).get("evidence_refs") or []) + (_provenance(stream_item, "stream_collection_lineage").get("evidence_refs") or [])),
                                "locations": (_provenance(item, source_artifact).get("locations") or []) + (_provenance(stream_item, "stream_collection_lineage").get("locations") or []),
                            },
                            "source_scope": props.get("source_scope") or stream_props.get("source_scope") or _fdp_source_scope(item),
                            "evidence_policy": "collection provenance plus local mapper field mapping; candidate only, persistence requires separate write evidence",
                            "stream_source_collection": source_collection,
                            "stream_collection_lineage_ref": stream_props.get("stream_collection_lineage_id") or _item_id(stream_item),
                        })
                        if len(out) >= max_results:
                            return out
    return out

def _gap_items(analysis_out: Path, *, max_results: int = 10000) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for source_artifact, compact_name, fact_type in [
        ("data_model_lineage_gap", "data_model_lineage_gaps", "data_model_lineage_gap"),
        ("storage_lineage_gap", "storage_lineage_gaps", "storage_lineage_gap"),
        ("unresolved_gap", "unresolved_gaps", "unresolved_gap"),
    ]:
        for item in _compact_or_facts(analysis_out, compact_name, fact_type):
            props = _props(item)
            out.append({
                "gap_id": _item_id(item) or f"gap_{len(out)+1:06d}",
                "gap_type": props.get("gap_kind") or props.get("gap_type") or source_artifact,
                "target": props.get("target") or props.get("operation") or props.get("container") or props.get("field"),
                "reason": props.get("reason") or props.get("description") or _short_summary(props),
                "missing_links": props.get("missing_links") or [],
                "evidence_level": "unresolved",
                "provenance": _provenance(item, source_artifact),
            })
            if len(out) >= max_results:
                return out
    return out


def _scenario_items(analysis_out: Path, event_sources: list[dict[str, Any]], *, max_results: int = 1000) -> list[dict[str, Any]]:
    scenarios: list[dict[str, Any]] = []
    raw_s2s = _compact_or_facts(analysis_out, "source_to_storage_lineage", "source_to_storage_lineage")
    # FDP is a case view, not a field-lineage dump.  Real applications may now
    # emit many source_to_storage_lineage rows for one DAO/write, especially after
    # cross-DAO jOOQ field mapping.  Group by concrete write/storage boundary so
    # case materialization stays bounded while field mappings remain available in
    # local_persistence.source_to_saved_field_mappings.
    s2s: list[dict[str, Any]] = []
    seen_s2s_cases: set[tuple[str, str]] = set()
    for item in raw_s2s:
        props = _props(item)
        storage_key = _fdp_concrete_text(props.get("storage_target") or props.get("storage_object") or props.get("saved_object"))
        boundary_key = str(props.get("persistent_write_id") or props.get("storage_access_id") or _item_id(item) or "")
        key = (boundary_key, storage_key)
        if key in seen_s2s_cases:
            continue
        seen_s2s_cases.add(key)
        s2s.append(item)
    stoa = _compact_or_facts(analysis_out, "storage_to_access_lineage", "storage_to_access_lineage")
    writes = _compact_or_facts(analysis_out, "persistent_writes", "persistent_write")
    reads = _compact_or_facts(analysis_out, "read_from_storage", "read_from_storage")
    boundaries = _compact_or_facts(analysis_out, "access_boundaries", "access_boundary")
    source_by_text = {json.dumps(x, ensure_ascii=False, default=str).lower(): x for x in event_sources}

    def related_event(props: dict[str, Any]) -> str | None:
        blob = json.dumps(props, ensure_ascii=False, default=str).lower()
        for _, ev in source_by_text.items():
            op = str(ev.get("operation") or "").lower()
            if op and op in blob:
                return ev.get("event_source_id")
        return event_sources[0].get("event_source_id") if event_sources else None

    for item in s2s[:max_results]:
        props = _props(item)
        scenarios.append({
            "scenario_id": f"scenario_{len(scenarios)+1:06d}",
            "name": props.get("operation") or props.get("source_payload") or "source-to-storage flow",
            "description": "Inbound/internal data is transformed and handed to storage boundary" if props else "source-to-storage flow",
            "trigger": {"event_source_ref": related_event(props)},
            "main_operation": props.get("operation") or props.get("terminal_operation_id"),
            "steps": props.get("path") or props.get("steps") or [],
            "input_objects": [props.get("source_payload") or props.get("source_object")],
            "output_objects": [props.get("saved_object") or props.get("storage_target")],
            "storage_objects": [props.get("storage_target") or props.get("storage_object")],
            "status": props.get("lineage_status") or "unresolved",
            "evidence_level": _strict_evidence_level(item, default="unresolved"),
            "provenance": _provenance(item, "source_to_storage_lineage"),
        })
        if len(scenarios) >= max_results:
            return scenarios
    for item in stoa[:max_results-len(scenarios)]:
        props = _props(item)
        scenarios.append({
            "scenario_id": f"scenario_{len(scenarios)+1:06d}",
            "name": props.get("access_boundary") or "storage-to-access flow",
            "description": "Stored data is read and exposed through an access boundary",
            "trigger": {"event_source_ref": related_event(props)},
            "main_operation": props.get("operation") or props.get("access_boundary"),
            "steps": props.get("path") or props.get("steps") or [],
            "input_objects": [props.get("source_storage_object") or props.get("storage_object")],
            "output_objects": [props.get("response_or_payload_type") or props.get("access_boundary")],
            "storage_objects": [props.get("source_storage_object") or props.get("storage_object")],
            "status": props.get("lineage_status") or "unresolved",
            "evidence_level": _strict_evidence_level(item, default="unresolved"),
            "provenance": _provenance(item, "storage_to_access_lineage"),
        })
        if len(scenarios) >= max_results:
            return scenarios
    if not scenarios:
        for ev in event_sources[:max_results]:
            scenarios.append({
                "scenario_id": f"scenario_{len(scenarios)+1:06d}",
                "name": ev.get("operation") or ev.get("endpoint_or_topic") or "event-driven scenario",
                "description": "Scenario inferred from event/access boundary; no complete data flow was materialized",
                "trigger": {"event_source_ref": ev.get("event_source_id")},
                "main_operation": ev.get("operation"),
                "steps": [],
                "input_objects": [ev.get("payload_type")],
                "output_objects": [],
                "storage_objects": [],
                "status": "unresolved",
                "evidence_level": ev.get("evidence_level") or "unresolved",
                "provenance": ev.get("provenance") or {},
            })
    return scenarios


def _data_flow_items(analysis_out: Path, mappings: list[dict[str, Any]], *, max_results: int = 1000) -> list[dict[str, Any]]:
    flows: list[dict[str, Any]] = []
    attrs_by_object = {x["object_name"]: x.get("fields") or [] for x in _attribute_objects(analysis_out, max_results=max_results * 5)}
    for source_artifact, compact_name, fact_type, flow_kind in [
        ("source_to_storage_lineage", "source_to_storage_lineage", "source_to_storage_lineage", "inbound_to_storage"),
        ("storage_to_access_lineage", "storage_to_access_lineage", "storage_to_access_lineage", "storage_to_response"),
    ]:
        for item in _compact_or_facts(analysis_out, compact_name, fact_type):
            props = _props(item)
            source_obj = props.get("source_payload") or props.get("source_object") or props.get("source_storage_object") or props.get("storage_object")
            target_obj = props.get("saved_object") or props.get("storage_target") or props.get("response_or_payload_type") or props.get("access_boundary")
            props_blob = json.dumps(props, ensure_ascii=False, default=str)
            related_maps = []
            for m in mappings:
                source_attr = str(m.get("source_attribute") or "")
                target_attr = str(m.get("target_attribute") or "")
                if source_obj and (m.get("source_object") == source_obj or (source_attr and source_attr in props_blob)):
                    related_maps.append(m)
                    continue
                if target_obj and (m.get("target_object") == target_obj or (target_attr and target_attr in props_blob)):
                    related_maps.append(m)
            flows.append({
                "flow_id": f"flow_{len(flows)+1:06d}",
                "scenario_ref": None,
                "flow_kind": flow_kind,
                "source": {"object": source_obj, "operation": props.get("operation"), "boundary_kind": props.get("origin_kind") or props.get("source_kind") or "unknown"},
                "target": {"object": target_obj, "operation": props.get("storage_method") or props.get("access_boundary"), "boundary_kind": "table" if flow_kind == "inbound_to_storage" else props.get("boundary_kind") or "unknown"},
                "input_attributes": attrs_by_object.get(str(source_obj), [])[:300],
                "output_attributes": attrs_by_object.get(str(target_obj), [])[:300],
                "attribute_mappings": related_maps[:500],
                "gaps": props.get("missing_links") or [],
                "status": props.get("lineage_status") or props.get("trace_status") or "unresolved",
                "evidence_level": _strict_evidence_level(item, default="unresolved"),
                "provenance": _provenance(item, source_artifact),
            })
            if len(flows) >= max_results:
                return flows
    if not flows and mappings:
        flows.append({
            "flow_id": "flow_000001",
            "scenario_ref": None,
            "flow_kind": "internal_transform",
            "source": {"object": mappings[0].get("source_object"), "operation": None, "boundary_kind": "internal"},
            "target": {"object": mappings[0].get("target_object"), "operation": None, "boundary_kind": "internal"},
            "input_attributes": [],
            "output_attributes": [],
            "attribute_mappings": mappings[:max_results],
            "gaps": [],
            "status": "confirmed" if any(m.get("evidence_level") == "confirmed_by_analyzer" for m in mappings) else "unresolved",
            "evidence_level": "confirmed_by_analyzer" if any(m.get("evidence_level") == "confirmed_by_analyzer" for m in mappings) else "unresolved",
            "provenance": {"source_artifact": "attribute_mapping", "evidence_refs": [m.get("mapping_id") for m in mappings[:20] if m.get("mapping_id")]},
        })
    return flows


def system_data_model_overview(analysis_out: Path, token: str = "", max_results: int = 10000) -> dict[str, Any]:
    token = str(token or "")
    manifest = read_json(analysis_out / "manifest.json", {}) or {}
    first_pass = read_json(analysis_out / "compact" / "first_pass.json", {}) or {}
    fact_summary = read_json(analysis_out / "facts" / "fact_summary.json", {}) or {}
    evidence_cov = read_json(analysis_out / "evidence_coverage.json", {}) or read_json(analysis_out / "diagnostics" / "evidence_coverage.json", {}) or {}
    tables = [x for x in _physical_table_items(analysis_out, max_results=max_results) if _item_matches_blob(x, token)]
    java_objects = [x for x in _attribute_objects(analysis_out, max_results=max_results) if _item_matches_blob(x, token)]
    event_sources = [x for x in _event_sources(analysis_out, max_results=max_results) if _item_matches_blob(x, token)]
    mappings = [x for x in _mapping_items(analysis_out, max_results=max_results) if _item_matches_blob(x, token)]
    gaps = [x for x in _gap_items(analysis_out, max_results=max_results) if _item_matches_blob(x, token)]
    scenarios = [x for x in _scenario_items(analysis_out, event_sources, max_results=max_results) if _item_matches_blob(x, token)]
    flows = [x for x in _data_flow_items(analysis_out, mappings, max_results=max_results) if _item_matches_blob(x, token)]
    requests = source_inspection_request(analysis_out, token, max_results=min(max_results, 1000)).get("hits") or []

    def section(items: list[dict[str, Any]], name: str) -> dict[str, Any]:
        total = len(items)
        selected = items[:max_results]
        return {
            "section_name": name,
            "total_count": total,
            "matched_count": total,
            "included_count": len(selected),
            "omitted_count": max(0, total - len(selected)),
            "materialization_status": "full" if total <= len(selected) else "truncated",
            "items": selected,
        }

    obj = {
        "kind": "system-data-model-overview",
        "analysis_out": str(analysis_out),
        "token": token,
        "selection_policy": "system-level evidence overview for final_response.json: materializes physical model, event sources, Java data objects, scenarios, data flows, mappings, gaps and source inspection requests; no business decision is made",
        "system_overview": {
            "repo_id": manifest.get("repo_id") or first_pass.get("repo_id"),
            "system_name": manifest.get("system_name") or first_pass.get("system_name"),
            "project_code": manifest.get("project_code") or first_pass.get("project_code"),
            "stack": [x for x in ["java" if (analysis_out / "compact" / "navigation.json").exists() else None, "spring" if event_sources else None, "liquibase" if tables else None] if x],
            "description_hints": _description_hints(analysis_out),
            "evidence_level": "confirmed_by_analyzer" if manifest or first_pass else "unresolved",
        },
        "coverage": {
            "fact_summary": fact_summary,
            "first_pass_counts": first_pass.get("counts") or {},
            "table_count": len(tables),
            "java_object_count": len(java_objects),
            "event_source_count": len(event_sources),
            "scenario_count": len(scenarios),
            "data_flow_count": len(flows),
            "mapping_count": len(mappings),
            "gap_count": len(gaps),
            "evidence_coverage_policy": (evidence_cov or {}).get("policy"),
            "coverage_limitations_count": len((evidence_cov or {}).get("limitations") or []),
        },
        "coverage_limitations": (evidence_cov or {}).get("limitations") or [],
        "primary_evidence_sources": ["config_scan", "java_structural_scan", "sql_scan", "db_schema_scan", "java_data_flow_build", "java_traceability_build", "java_data_model_lineage_build", "java_persistence_lineage_build"],
        "sections": {
            "event_sources": section(event_sources, "event_sources"),
            "physical_tables": section(tables, "physical_tables"),
            "java_data_objects": section(java_objects, "java_data_objects"),
            "system_scenarios": section(scenarios, "system_scenarios"),
            "data_flows": section(flows, "data_flows"),
            "attribute_mappings": section(mappings, "attribute_mappings"),
            "gaps": section(gaps, "gaps"),
            "source_inspection_requests": section([h.get("item") or h for h in requests if isinstance(h, dict)], "source_inspection_requests"),
        },
        "policy": {
            "analyzer_role": "evidence_only_no_business_decision",
            "strict_levels": ["confirmed_by_analyzer", "candidate_signal_navigation_only", "unresolved", "not_applicable"],
            "llm_rule": "build narrative from materialized sections; do not invent scenarios, mappings, keys, or table targets not represented here",
        },
    }
    write_lazy(analysis_out, "system-data-model-overview", token or "all", obj)
    return obj


# ---------------------------------------------------------------------------
# Code-to-OpenSpec data evidence context
# ---------------------------------------------------------------------------

_OPENSPEC_SECTIONS = {
    "summary",
    "system",
    "boundaries",
    "interfaces",
    "payload_schemas",
    "entities",
    "attributes",
    "authority_signals",
    "storages",
    "storage_attributes",
    "scenarios",
    "flows",
    "transformations",
    "access_paths",
    "external_data_persistence_cases",
    "lifecycle_evidence_signals",
    "constraints",
    "gaps",
    "omissions",
    "evidence_ref_index",
}

_AUTHORITY_SIGNAL_RE = re.compile(r"(master|source[_-]?of[_-]?truth|authoritative|reference|nsi|dict|dictionary)", re.IGNORECASE)
_LIFECYCLE_SIGNAL_RE = re.compile(r"(status|state|create|update|delete|archive|history|audit|valid[_-]?from|valid[_-]?to|start[_-]?date|end[_-]?date)", re.IGNORECASE)


def _openspec_id(prefix: str, *parts: Any) -> str:
    raw = "|".join(str(p or "").strip().lower() for p in parts if p is not None)
    if not raw:
        raw = prefix.lower()
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:8].upper()
    return f"{prefix}-{digest}"


def _status_from_evidence_level(level: Any, *, default: str = "unresolved_static_analysis") -> str:
    text = str(level or "").lower()
    if text in {"confirmed", "confirmed_by_analyzer", "confirmed_by_static_analysis"}:
        return "derived_by_static_analysis"
    if text in {"confirmed_by_llm_source_inspection"}:
        return "derived_by_static_analysis"
    if text in {"candidate", "candidate_signal", "candidate_signal_navigation_only"}:
        return "candidate_by_naming"
    if text in {"not_observed", "not_applicable"}:
        return "not_observed"
    return default


def _compact_items(items: list[dict[str, Any]], *, token: str = "", max_items: int = 100) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    matched = [x for x in items if _item_matches_blob(x, token)]
    selected = matched[:max_items]
    return selected, {
        "matched_count": len(matched),
        "included_count": len(selected),
        "omitted_count": max(0, len(matched) - len(selected)),
        "materialization_status": "full" if len(matched) <= len(selected) else "truncated",
    }


def _scanner_coverage_gaps(analysis_out: Path) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    coverage = read_json(analysis_out / "evidence_coverage.json", {}) or read_json(analysis_out / "diagnostics" / "evidence_coverage.json", {}) or {}
    for limitation in (coverage.get("limitations") or []) if isinstance(coverage, dict) else []:
        if not isinstance(limitation, dict):
            continue
        component = limitation.get("component") or "unknown_component"
        gaps.append({
            "id": _openspec_id("GAP", limitation.get("gap_type"), component, limitation.get("status")),
            "gap_type": limitation.get("gap_type") or "analysis_coverage_limitation",
            "component": component,
            "status": "unresolved_static_analysis",
            "impact": limitation.get("impact"),
            "diagnostic_ref": "evidence_coverage.json",
            "evidence_refs": [],
        })
    return gaps


def _normal_gap_type(raw: Any, fallback: str) -> str:
    text = str(raw or fallback or "unknown_gap").strip().lower().replace("-", "_").replace(" ", "_")
    known = {
        "field_mapping_unresolved": "unresolved_source_to_storage_mapping",
        "storage_lineage_gap": "unresolved_storage_to_access_mapping",
        "data_model_lineage_gap": "unresolved_source_to_storage_mapping",
    }
    return known.get(text, text or "unknown_gap")


def _openspec_gap_items(analysis_out: Path, *, max_results: int = 10000) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in _gap_items(analysis_out, max_results=max_results):
        gid = item.get("gap_id") or _openspec_id("GAP", item.get("gap_type"), item.get("target"), item.get("reason"))
        out.append({
            "id": gid if str(gid).startswith("GAP-") else _openspec_id("GAP", gid),
            "gap_type": _normal_gap_type(item.get("gap_type"), "unresolved_static_analysis"),
            "affected_object_refs": [x for x in [item.get("target")] if x],
            "reason": item.get("reason"),
            "impact": "limits_authoritative_spec_generation; requires manual/spec confirmation",
            "status": "unresolved_static_analysis",
            "evidence_refs": item.get("provenance", {}).get("evidence_refs") or [],
            "provenance": item.get("provenance") or {},
        })
        if len(out) >= max_results:
            return out
    out.extend(_scanner_coverage_gaps(analysis_out))
    return out[:max_results]


def _openspec_interfaces(event_sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in event_sources:
        resource = item.get("endpoint_path") or item.get("topic_name") or item.get("endpoint_or_topic") or item.get("endpoint_or_topic_raw")
        kind = str(item.get("kind") or "unknown").lower()
        iid = item.get("interface_id") or item.get("event_source_id") or _openspec_id("IFACE", kind, resource, item.get("operation"))
        out.append({
            "id": iid,
            "suggested_id": _openspec_id("IFACE", kind, item.get("direction"), resource, item.get("operation")),
            "direction": item.get("direction") or "unknown",
            "kind": kind,
            "endpoint_or_resource": resource,
            "topic_or_channel": item.get("topic_name") if kind == "kafka" else None,
            "operation": item.get("operation"),
            "operation_id": item.get("operation_id"),
            "payload_schema_ref": item.get("payload_type") or item.get("request_type") or item.get("response_type"),
            "source_system_candidate": item.get("source_system_candidate"),
            "target_system_candidate": item.get("target_system_candidate"),
            "evidence_status": _status_from_evidence_level(item.get("evidence_level"), default="observed_in_code"),
            "evidence_refs": (item.get("provenance") or {}).get("evidence_refs") or [item.get("event_source_id")],
            "original_identifiers": [x for x in [item.get("interface_id"), item.get("operation_id"), item.get("class_name"), item.get("method_name")] if x],
            "provenance": item.get("provenance") or {},
        })
    return out


def _openspec_payload_schemas(java_objects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for obj in java_objects:
        name = obj.get("object_name")
        fields = []
        for f in obj.get("fields") or []:
            if not isinstance(f, dict):
                continue
            fields.append({
                "name": f.get("name"),
                "java_type": f.get("type"),
                "validation_annotations": f.get("validation_annotations") or [],
                "serialization_aliases": f.get("serialization_aliases") or [],
                "evidence_status": _status_from_evidence_level(f.get("evidence_level"), default="observed_in_code"),
                "evidence_refs": (f.get("provenance") or {}).get("evidence_refs") or [],
            })
        out.append({
            "id": _openspec_id("PAYLOAD", name),
            "suggested_id": _openspec_id("PAYLOAD", name),
            "java_class_name": name,
            "schema_kind": obj.get("object_type") or "java_object",
            "fields": fields,
            "source_interface_refs": [],
            "evidence_status": _status_from_evidence_level(obj.get("evidence_level"), default="observed_in_code"),
            "evidence_refs": (obj.get("provenance") or {}).get("evidence_refs") or [],
            "provenance": obj.get("provenance") or {},
        })
    return out


def _openspec_storages(tables: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    storages: list[dict[str, Any]] = []
    attrs: list[dict[str, Any]] = []
    for table in tables:
        tname = table.get("table_name")
        sid = _openspec_id("STORE", table.get("schema_name"), tname)
        storages.append({
            "id": sid,
            "suggested_id": sid,
            "storage_kind": table.get("object_type") or "storage_target",
            "physical_name": tname,
            "schema_name": table.get("schema_name"),
            "classification_status": table.get("classification_status"),
            "keys": table.get("keys") or [],
            "relationships": table.get("relationships") or [],
            "indexes": table.get("indexes") or [],
            "read_write_evidence_status": table.get("evidence_level") or "derived_by_static_analysis",
            "evidence_status": _status_from_evidence_level(table.get("evidence_level"), default="observed_in_schema"),
            "evidence_refs": (table.get("provenance") or {}).get("evidence_refs") or [],
            "provenance": table.get("provenance") or {},
            "original_identifiers": [x for x in [table.get("schema_name"), tname] if x],
        })
        for col in table.get("columns") or []:
            if not isinstance(col, dict):
                continue
            cname = col.get("name")
            attrs.append({
                "id": _openspec_id("ATTR", sid, cname),
                "suggested_id": _openspec_id("ATTR", sid, cname),
                "storage_ref": sid,
                "table_name": tname,
                "physical_name": cname,
                "sql_type": col.get("type"),
                "java_type": col.get("java_type"),
                "nullable": col.get("nullable"),
                "default": col.get("default"),
                "comment": col.get("description"),
                "constraints": col.get("constraints") or [],
                "evidence_status": _status_from_evidence_level(col.get("evidence_level"), default="observed_in_schema"),
                "evidence_refs": (col.get("provenance") or table.get("provenance") or {}).get("evidence_refs") or [],
            })
    return storages, attrs


def _openspec_entities(tables: list[dict[str, Any]], java_objects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for table in tables:
        name = table.get("table_name")
        out.append({
            "id": _openspec_id("ENTITY", "table", name),
            "suggested_id": _openspec_id("ENTITY", "table", name),
            "technical_name": name,
            "entity_kind": "storage_backed_entity_candidate",
            "backing_store_ref": _openspec_id("STORE", table.get("schema_name"), name),
            "attribute_refs": [_openspec_id("ATTR", _openspec_id("STORE", table.get("schema_name"), name), (c or {}).get("name")) for c in table.get("columns") or [] if isinstance(c, dict)],
            "business_meaning_status": "unknown_business_meaning",
            "evidence_status": _status_from_evidence_level(table.get("evidence_level"), default="observed_in_schema"),
            "evidence_refs": (table.get("provenance") or {}).get("evidence_refs") or [],
            "original_identifiers": [x for x in [name] if x],
        })
    for obj in java_objects:
        name = obj.get("object_name")
        out.append({
            "id": _openspec_id("ENTITY", "java", name),
            "suggested_id": _openspec_id("ENTITY", "java", name),
            "technical_name": name,
            "entity_kind": "java_data_object_candidate",
            "backing_payload_ref": _openspec_id("PAYLOAD", name),
            "business_meaning_status": "unknown_business_meaning",
            "evidence_status": _status_from_evidence_level(obj.get("evidence_level"), default="observed_in_code"),
            "evidence_refs": (obj.get("provenance") or {}).get("evidence_refs") or [],
            "original_identifiers": [x for x in [name] if x],
        })
    return out


def _authority_signals(items: list[dict[str, Any]], *, max_results: int = 1000) -> list[dict[str, Any]]:
    signals: list[dict[str, Any]] = []
    for item in items:
        blob = json.dumps(item, ensure_ascii=False, default=str)
        if not _AUTHORITY_SIGNAL_RE.search(blob):
            continue
        name = item.get("table_name") or item.get("object_name") or item.get("operation") or item.get("endpoint_or_resource") or _short_summary(item)
        signals.append({
            "id": _openspec_id("AUTH", name, blob[:200]),
            "signal_type": "technical_authority_naming_signal",
            "technical_name": name,
            "status": "candidate_by_naming",
            "source_of_truth_decision": "not_made_by_analyzer",
            "reason": "Identifier/config text contains source/master/reference/authoritative-like wording; this is not proof of business source-of-truth.",
            "evidence_refs": (item.get("provenance") or {}).get("evidence_refs") or item.get("evidence_refs") or [],
        })
        if len(signals) >= max_results:
            break
    return signals


def _lifecycle_signals(items: list[dict[str, Any]], *, max_results: int = 1000) -> list[dict[str, Any]]:
    signals: list[dict[str, Any]] = []
    for item in items:
        blob = json.dumps(item, ensure_ascii=False, default=str)
        if not _LIFECYCLE_SIGNAL_RE.search(blob):
            continue
        name = item.get("table_name") or item.get("object_name") or item.get("operation") or item.get("physical_name") or _short_summary(item)
        signals.append({
            "id": _openspec_id("LC", name, blob[:200]),
            "signal_type": "technical_lifecycle_naming_or_operation_signal",
            "technical_name": name,
            "status": "candidate_by_naming",
            "lifecycle_decision": "not_made_by_analyzer",
            "reason": "Code/schema/config contains lifecycle-like wording; this is not proof of approved business lifecycle.",
            "evidence_refs": (item.get("provenance") or {}).get("evidence_refs") or item.get("evidence_refs") or [],
        })
        if len(signals) >= max_results:
            break
    return signals


def _openspec_constraints(analysis_out: Path, tables: list[dict[str, Any]], *, max_results: int = 10000) -> list[dict[str, Any]]:
    constraints: list[dict[str, Any]] = []
    for table in tables:
        tname = table.get("table_name")
        for rel in table.get("relationships") or []:
            constraints.append({
                "id": _openspec_id("CON", tname, "relationship", rel),
                "constraint_kind": "db_relationship",
                "object_ref": _openspec_id("STORE", table.get("schema_name"), tname),
                "details": rel,
                "status": "observed_in_schema",
                "evidence_refs": (table.get("provenance") or {}).get("evidence_refs") or [],
            })
        for key in table.get("keys") or []:
            constraints.append({
                "id": _openspec_id("CON", tname, "key", key),
                "constraint_kind": "db_key",
                "object_ref": _openspec_id("STORE", table.get("schema_name"), tname),
                "details": key,
                "status": "observed_in_schema",
                "evidence_refs": (table.get("provenance") or {}).get("evidence_refs") or [],
            })
        if len(constraints) >= max_results:
            return constraints
    # Include explicit validation-like facts if available later; no invention here.
    return constraints[:max_results]



def _evidence_ref_index_for_context(sections: dict[str, Any], *, max_results: int = 10000) -> list[dict[str, Any]]:
    refs: dict[str, dict[str, Any]] = {}

    def walk(section_name: str, node: Any) -> None:
        if isinstance(node, dict):
            for ref in node.get("evidence_refs") or []:
                if not ref:
                    continue
                refs.setdefault(str(ref), {"evidence_ref": str(ref), "sections": set()})["sections"].add(section_name)
            prov = node.get("provenance") or {}
            if isinstance(prov, dict):
                for ref in prov.get("evidence_refs") or []:
                    refs.setdefault(str(ref), {"evidence_ref": str(ref), "sections": set()})["sections"].add(section_name)
            for value in node.values():
                walk(section_name, value)
        elif isinstance(node, list):
            for item in node:
                walk(section_name, item)

    for name, value in sections.items():
        walk(name, value)
    out = []
    for ref, data in refs.items():
        out.append({"evidence_ref": ref, "sections": sorted(data["sections"])})
        if len(out) >= max_results:
            break
    return out


def _section_payload(name: str, items: list[dict[str, Any]], *, token: str, max_items: int) -> dict[str, Any]:
    selected, stats = _compact_items(items, token=token, max_items=max_items)
    return {"section_name": name, **stats, "items": selected}


def openspec_data_evidence_context(
    analysis_out: Path,
    *,
    section: str | None = None,
    token: str = "",
    max_items: int = 100,
) -> dict[str, Any]:
    section = (section or "").strip() or None
    if section and section not in _OPENSPEC_SECTIONS:
        return {
            "kind": "openspec-data-evidence-context",
            "format_version": "1.0",
            "analysis_out": str(analysis_out),
            "error": f"unknown section: {section}",
            "available_sections": sorted(_OPENSPEC_SECTIONS),
        }

    manifest = read_json(analysis_out / "manifest.json", {}) or {}
    fact_summary = read_json(analysis_out / "facts" / "fact_summary.json", {}) or {}
    first_pass = read_json(analysis_out / "compact" / "first_pass.json", {}) or {}
    tables = _physical_table_items(analysis_out, max_results=100000)
    java_objects = _attribute_objects(analysis_out, max_results=100000)
    event_sources = _event_sources(analysis_out, max_results=100000)
    mappings = _mapping_items(analysis_out, max_results=100000)
    flows = _data_flow_items(analysis_out, mappings, max_results=100000)
    scenarios = _scenario_items(analysis_out, event_sources, max_results=100000)
    access = stored_data_access(analysis_out, token="", max_results=100000).get("stored_data_access") or []
    gaps = _openspec_gap_items(analysis_out, max_results=100000)

    interfaces = _openspec_interfaces(event_sources)
    payload_schemas = _openspec_payload_schemas(java_objects)
    storages, storage_attrs = _openspec_storages(tables)
    entities = _openspec_entities(tables, java_objects)
    transformations = []
    for item in mappings:
        tid = _openspec_id("TRN", item.get("source_object"), item.get("source_attribute"), item.get("target_object"), item.get("target_attribute"), item.get("expression"))
        transformations.append({
            "id": tid,
            "suggested_id": tid,
            "transformation_kind": _transformation_kind_from_item(item),
            "source_attribute": item.get("source_attribute"),
            "source_object": item.get("source_object"),
            "target_attribute": item.get("target_attribute"),
            "target_object": item.get("target_object"),
            "expression": item.get("expression"),
            "status": _status_from_evidence_level(item.get("evidence_level"), default="unresolved_static_analysis"),
            "evidence_refs": (item.get("provenance") or {}).get("evidence_refs") or [],
            "provenance": item.get("provenance") or {},
        })

    flow_items = []
    for f in flows:
        fid = _openspec_id("FLOW", f.get("flow_kind"), f.get("source", {}).get("object"), f.get("target", {}).get("object"), f.get("status"))
        flow_items.append({"id": fid, "suggested_id": fid, "flow_type": f.get("flow_kind") or "unresolved_flow", **f})

    scenario_items = []
    for sc in scenarios:
        sid = _openspec_id("SCN", sc.get("name"), sc.get("main_operation"), sc.get("status"))
        scenario_items.append({"id": sid, "suggested_id": sid, **sc})

    access_items = []
    for ap in access:
        aid = _openspec_id("ACCESS", ap.get("access_status"), ap.get("storage"), ap.get("access_boundary"), ap.get("description"))
        access_items.append({"id": aid, "suggested_id": aid, **ap})

    all_signal_candidates = tables + java_objects + interfaces + storage_attrs + flow_items + transformations
    authority = _authority_signals(all_signal_candidates, max_results=10000)
    lifecycle = _lifecycle_signals(all_signal_candidates, max_results=10000)
    constraints = _openspec_constraints(analysis_out, tables, max_results=10000)
    fdp_cases = _openspec_fdp_cases(analysis_out, flows, access_items, max_results=10000)

    attr_items = storage_attrs[:]
    for schema in payload_schemas:
        for field in schema.get("fields") or []:
            attr_items.append({
                "id": _openspec_id("ATTR", schema.get("id"), field.get("name")),
                "suggested_id": _openspec_id("ATTR", schema.get("id"), field.get("name")),
                "payload_schema_ref": schema.get("id"),
                "technical_name": field.get("name"),
                "java_type": field.get("java_type"),
                "evidence_status": field.get("evidence_status"),
                "evidence_refs": field.get("evidence_refs") or [],
            })

    sections: dict[str, Any] = {
        "system": {
            "repo_id": manifest.get("repo_id") or first_pass.get("repo_id"),
            "system_name": manifest.get("system_name") or first_pass.get("system_name"),
            "project_code": manifest.get("project_code") or first_pass.get("project_code"),
            "detected_stack": [x for x in ["java" if (analysis_out / "compact" / "navigation.json").exists() else None, "spring" if event_sources else None, "sql" if tables or (analysis_out / "sql").exists() else None] if x],
            "description_hints": _description_hints(analysis_out),
            "business_purpose_status": "candidate_by_naming_or_not_observed",
            "evidence_status": "derived_by_static_analysis" if manifest or first_pass else "unresolved_static_analysis",
        },
        "boundaries": [
            {"id": _openspec_id("BOUND", "ingress"), "boundary_kind": "ingress", "status": "observed_in_code" if any(i.get("direction") == "inbound" for i in interfaces) else "not_observed", "interface_refs": [i.get("id") for i in interfaces if i.get("direction") == "inbound"][:max_items]},
            {"id": _openspec_id("BOUND", "storage"), "boundary_kind": "storage", "status": "observed_in_code" if storages else "not_observed", "storage_refs": [s.get("id") for s in storages[:max_items]]},
            {"id": _openspec_id("BOUND", "access"), "boundary_kind": "output/access", "status": "observed_in_code" if access_items else "not_observed", "access_refs": [a.get("id") for a in access_items[:max_items]]},
            {"id": _openspec_id("BOUND", "external_dependency"), "boundary_kind": "external_dependency", "status": "observed_in_code" if any(i.get("direction") == "outbound" for i in interfaces) else "not_observed", "interface_refs": [i.get("id") for i in interfaces if i.get("direction") == "outbound"][:max_items]},
        ],
        "interfaces": interfaces,
        "payload_schemas": payload_schemas,
        "entities": entities,
        "attributes": attr_items,
        "authority_signals": authority,
        "storages": storages,
        "storage_attributes": storage_attrs,
        "scenarios": scenario_items,
        "flows": flow_items,
        "transformations": transformations,
        "access_paths": access_items,
        "external_data_persistence_cases": fdp_cases,
        "lifecycle_evidence_signals": lifecycle,
        "constraints": constraints,
        "gaps": gaps,
        "omissions": [
            {
                "omission_type": "system_graph_not_included",
                "reason": "This context is scoped to one repository and does not perform producer-consumer matching or system graph construction.",
            },
            {
                "omission_type": "business_decisions_not_made",
                "reason": "Analyzer does not assign owners, source-of-truth, SLA, business criticality, or authoritative business meaning.",
            },
        ],
    }
    sections["evidence_ref_index"] = _evidence_ref_index_for_context(sections, max_results=10000)

    summary = {
        "available_sections": sorted(sections.keys()),
        "counts": {name: (len(value) if isinstance(value, list) else 1 if value else 0) for name, value in sections.items() if name != "evidence_ref_index"},
        "scanner_coverage_gaps": [g for g in gaps if g.get("gap_type") == "partial_static_analysis"],
        "policy": {
            "authoritative_specification": False,
            "business_decisions_made": False,
            "system_graph_included": False,
            "spec_vs_code_validation_included": False,
            "source_of_truth_decision_made": False,
        },
    }
    sections["summary"] = summary

    selected_sections: dict[str, Any]
    if section:
        value = sections.get(section)
        if isinstance(value, list):
            selected_sections = {section: _section_payload(section, value, token=token, max_items=max_items)}
        else:
            selected_sections = {section: value}
    else:
        selected_sections = {}
        for name, value in sections.items():
            if isinstance(value, list):
                selected_sections[name] = _section_payload(name, value, token=token, max_items=max_items)
            else:
                selected_sections[name] = value

    obj = {
        "kind": "openspec-data-evidence-context",
        "format_version": "1.0",
        "analysis_profile": manifest.get("analysis_profile", {}).get("profile_id") if isinstance(manifest.get("analysis_profile"), dict) else manifest.get("analysis_profile"),
        "repo_id": manifest.get("repo_id") or first_pass.get("repo_id"),
        "scope": "single_repository",
        "section": section,
        "token": token,
        "max_items": max_items,
        "generation_policy": {
            "authoritative_specification": False,
            "business_decisions_made": False,
            "system_graph_included": False,
            "spec_vs_code_validation_included": False,
            "source_of_truth_decision_made": False,
        },
        "sections": selected_sections,
        "evidence_ref_index": selected_sections.get("evidence_ref_index") if section == "evidence_ref_index" else sections["evidence_ref_index"][:max_items],
        "omissions": selected_sections.get("omissions") if section == "omissions" else sections["omissions"],
        "coverage": {
            "fact_summary": fact_summary,
            "first_pass_counts": first_pass.get("counts") or {},
        },
        "policy": {
            "analyzer_role": "deterministic_evidence_only_no_openspec_generation",
            "authority_signals_rule": "authority_signals are not source-of-truth decisions; they are technical/naming signals requiring owner/spec confirmation.",
            "lifecycle_signals_rule": "lifecycle_evidence_signals are not approved lifecycle requirements; they are technical signals only.",
            "fdp_rule": "external_data_persistence_cases are evidence candidates, not risk or violation decisions.",
            "ids_rule": "suggested_id values are deterministic hash-based candidates and do not depend on runtime paths.",
        },
    }
    write_lazy(analysis_out, "openspec-data-evidence-context", section or token or "all", obj)
    return obj



def _stable_export_sort_key(item: Any) -> str:
    if isinstance(item, dict):
        for key in ("id", "suggested_id", "transformation_id", "case_id", "interface_id", "evidence_ref", "technical_name", "physical_name", "java_class_name", "name"):
            value = item.get(key)
            if value is not None:
                return str(value)
        return json.dumps(item, ensure_ascii=False, sort_keys=True, default=str)[:500]
    return str(item)


def _stable_sort_export_value(value: Any) -> Any:
    if isinstance(value, list):
        return [_stable_sort_export_value(x) for x in sorted(value, key=_stable_export_sort_key)]
    if isinstance(value, dict):
        return {k: _stable_sort_export_value(v) for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))}
    return value


def _extract_full_section_from_context(section_name: str, value: Any) -> tuple[Any, dict[str, Any]]:
    if isinstance(value, dict) and "items" in value and "section_name" in value:
        items = value.get("items") or []
        total = int(value.get("matched_count", len(items)) or 0)
        exported = len(items) if isinstance(items, list) else 0
        omitted = int(value.get("omitted_count", max(0, total - exported)) or 0)
        if omitted > 0:
            status = "truncated_by_export_limit"
        elif total == 0 and section_name == "constraints":
            status = "not_available_in_analysis"
        elif total == 0:
            status = "empty"
        else:
            status = "complete"
        return _stable_sort_export_value(items), {
            "status": status,
            "exported": exported,
            "total": total,
            "omitted": omitted,
        }
    if isinstance(value, list):
        total = len(value)
        status = "empty" if total == 0 else "complete"
        if total == 0 and section_name == "constraints":
            status = "not_available_in_analysis"
        return _stable_sort_export_value(value), {"status": status, "exported": total, "total": total, "omitted": 0}
    status = "complete" if value else "empty"
    return _stable_sort_export_value(value), {"status": status, "exported": 1 if value else 0, "total": 1 if value else 0, "omitted": 0}


def openspec_data_evidence_full(analysis_out: Path) -> dict[str, Any]:
    """Return full deterministic data-evidence export for SDD artifacts.

    Unlike openspec_data_evidence_context this view is not a prompt-sized
    context and does not sample/top-N sections. It is intended as a factual
    artifact source for pipeline YAML packaging. Analyzer still does not make
    business decisions or generate an authoritative specification.
    """
    # Reuse the same collectors as the compact/drill-down context, but request a
    # full export limit high enough to avoid regular prompt-oriented truncation.
    # If this ever truncates, the export is explicitly marked non-substitution-grade.
    full_limit = 1_000_000_000
    ctx = openspec_data_evidence_context(analysis_out, section=None, token="", max_items=full_limit)
    manifest = read_json(analysis_out / "manifest.json", {}) or {}
    sections_in = ctx.get("sections") or {}

    preferred_sections = [
        "system",
        "boundaries",
        "interfaces",
        "payload_schemas",
        "entities",
        "attributes",
        "authority_signals",
        "storages",
        "storage_attributes",
        "scenarios",
        "flows",
        "transformations",
        "access_paths",
        "external_data_persistence_cases",
        "lifecycle_evidence_signals",
        "constraints",
        "gaps",
        "omissions",
        "evidence_ref_index",
    ]
    # Schema-evolution rule: preferred_sections control stable ordering for the
    # currently known data-evidence contract, but full export must preserve any
    # additional factual section later added by openspec_data_evidence_context.
    # This keeps pipeline/YAML packaging schema-agnostic: new sections require no
    # pipeline change and are exported automatically once analyzer collectors add
    # them to the context sections.
    dynamic_section_names = [str(k) for k in sections_in.keys() if str(k) not in set(preferred_sections)]
    export_section_order = preferred_sections + sorted(dynamic_section_names)

    exported_sections: dict[str, Any] = {}
    completeness: dict[str, dict[str, Any]] = {}
    for name in export_section_order:
        if name == "evidence_ref_index":
            value = ctx.get("evidence_ref_index") or sections_in.get(name) or []
        elif name == "omissions":
            value = ctx.get("omissions") or sections_in.get(name) or []
        else:
            value = sections_in.get(name)
        exported, stats = _extract_full_section_from_context(name, value)
        exported_sections[name] = exported
        completeness[name] = stats

    truncated = [name for name, stats in completeness.items() if str(stats.get("status")) == "truncated_by_export_limit"]
    failed = [name for name, stats in completeness.items() if str(stats.get("status")) == "failed"]
    substitution_grade = not truncated and not failed

    analysis_profile = manifest.get("analysis_profile", {})
    if isinstance(analysis_profile, dict):
        analysis_profile_id = analysis_profile.get("profile_id") or analysis_profile.get("id")
    else:
        analysis_profile_id = analysis_profile

    metadata = {
        "format": "data_evidence",
        "format_version": "1.0",
        "schema_version": "0.3-deterministic-factual",
        "source_view": "openspec-data-evidence-full",
        "source_view_format_version": "1.0",
        "repo_id": manifest.get("repo_id") or ctx.get("repo_id"),
        "analysis_profile": analysis_profile_id or ctx.get("analysis_profile"),
        "scope": "single_repository",
        "generated_from": "code_analysis",
        "generated_from_code_evidence": True,
        "substitution_grade": substitution_grade,
        "substitution_grade_reasons": [] if substitution_grade else [
            {"reason": "one_or_more_sections_not_fully_exported", "sections": truncated + failed}
        ],
        "authoritative_specification": False,
        "business_decisions_made": False,
        "business_owner_confirmed": False,
        "system_graph_included": False,
        "spec_vs_code_validation_included": False,
        "source_of_truth_decision_made": False,
        "export_policy": "full_deterministic_export_no_sampling",
        "section_order": export_section_order,
        "schema_evolution_policy": "new factual sections emitted by the analyzer context are preserved automatically in this full export; downstream consumers should ignore unknown sections they do not understand",
        "export_completeness": completeness,
    }

    obj = {
        "kind": "openspec-data-evidence-full",
        "format_version": "1.0",
        "metadata": metadata,
    }
    for section_name in export_section_order:
        obj[section_name] = exported_sections[section_name]
    obj["policy"] = {
            "analyzer_role": "deterministic_factual_export_only_no_openspec_generation",
            "authoritative_specification_rule": "This artifact is code-derived evidence, not an approved specification.",
            "substitution_grade_rule": "substitution_grade means downstream SDD profiles may use this artifact instead of direct code evidence; it does not imply owner confirmation or source-of-truth status.",
            "no_business_decisions_rule": "Analyzer does not assign owners, source-of-truth, SLA, business criticality, or approved lifecycle.",
            "no_sampling_rule": "Factual sections are exported completely from available analysis evidence; no top-N sampling is applied.",
            "schema_evolution_rule": "Data-evidence sections may evolve; this full export preserves analyzer-emitted sections without hardcoding YAML packaging in the pipeline.",
        }
    write_lazy(analysis_out, "openspec-data-evidence-full", "all", obj)
    return obj



# ---------------------------------------------------------------------------
# Fast evidence-oriented core views replacing historical Spoon/Semgrep dependency
# ---------------------------------------------------------------------------

def evidence_coverage(analysis_out: Path, token: str = "", max_results: int = 10000) -> dict[str, Any]:
    cov = read_json(analysis_out / "evidence_coverage.json", {}) or read_json(analysis_out / "diagnostics" / "evidence_coverage.json", {}) or {}
    if token:
        # Keep top-level structure but filter limitations/stages by token for quick drilldown.
        stages = cov.get("stages") or {}
        cov = dict(cov)
        cov["stages"] = {k: v for k, v in stages.items() if token.lower() in json.dumps({k: v}, ensure_ascii=False, default=str).lower()}
        cov["limitations"] = [x for x in cov.get("limitations") or [] if _item_matches_blob(x, token)][:max_results]
    obj = {"kind": "evidence-coverage", "analysis_out": str(analysis_out), "token": token, "coverage": cov}
    write_lazy(analysis_out, "evidence-coverage", token or "all", obj)
    return obj


def _transformation_kind_from_item(item: dict[str, Any]) -> str:
    text = " ".join(str(item.get(k) or "") for k in ("mapping_type", "expression_kind", "derivation_kind", "expression", "operation", "source_expression"))
    low = text.lower()
    if any(x in low for x in ["join", "lookup", "reference"]):
        return "lookup_or_join"
    if any(x in low for x in ["filter", "where", "predicate"]):
        return "filter"
    if any(x in low for x in ["row_number", "rank", "over(", "window"]):
        return "window"
    if any(x in low for x in ["group by", "sum(", "count(", "avg(", "min(", "max(", "aggregation"]):
        return "aggregation"
    if any(x in low for x in ["constant", "default", "literal"]):
        return "default_or_constant"
    if any(x in low for x in ["rename", "alias"]):
        return "rename"
    if item.get("source_attribute") and item.get("target_attribute") and normalize_name(str(item.get("source_attribute"))) == normalize_name(str(item.get("target_attribute"))):
        return "direct_mapping"
    if item.get("expression") or item.get("source_expression"):
        return "derivation"
    return str(item.get("mapping_type") or item.get("expression_kind") or "unresolved_transformation")


def transformation_catalog(analysis_out: Path, token: str = "", max_results: int = 1000) -> dict[str, Any]:
    mappings = _mapping_items(analysis_out, max_results=100000)
    derivations = _compact_or_facts(analysis_out, "attribute_derivations", "attribute_derivation")
    items: list[dict[str, Any]] = []
    for raw in mappings + derivations:
        item = raw.get("properties") or raw
        if not isinstance(item, dict):
            continue
        if token and not _item_matches_blob(item, token):
            continue
        source_object = item.get("source_object") or item.get("source_container") or item.get("source_payload")
        target_object = item.get("target_object") or item.get("target_container") or item.get("storage_target") or item.get("saved_object")
        source_attr = item.get("source_attribute") or item.get("source_field")
        target_attr = item.get("target_attribute") or item.get("target_field") or item.get("storage_field")
        tid = item.get("attribute_mapping_id") or item.get("attribute_derivation_id") or _openspec_id("TRN", source_object, source_attr, target_object, target_attr, item.get("expression") or item.get("source_expression"))
        items.append({
            "transformation_id": str(tid),
            "suggested_id": _openspec_id("TRN", source_object, source_attr, target_object, target_attr, item.get("expression") or item.get("source_expression")),
            "transformation_kind": _transformation_kind_from_item(item),
            "source_object": source_object,
            "source_attribute": source_attr,
            "target_object": target_object,
            "target_attribute": target_attr,
            "expression": item.get("expression") or item.get("source_expression"),
            "mapping_type": item.get("mapping_type"),
            "evidence_status": _status_from_evidence_level(item.get("evidence_level") or item.get("evidence_maturity_level"), default="unresolved_static_analysis"),
            "evidence_refs": item.get("evidence_refs") or (item.get("provenance") or {}).get("evidence_refs") or [],
            "provenance": item.get("provenance") or {},
            "raw": item,
        })
        if len(items) >= max_results:
            break
    by_kind: dict[str, int] = {}
    for item in items:
        by_kind[item["transformation_kind"]] = by_kind.get(item["transformation_kind"], 0) + 1
    obj = {
        "kind": "transformation-catalog",
        "analysis_out": str(analysis_out),
        "token": token,
        "selection_policy": "compact transformation evidence from built-in SQL/Java mapping and derivation facts; no Spoon/Semgrep required",
        "matched_count": len(items),
        "included_count": len(items),
        "by_transformation_kind": by_kind,
        "items": items,
    }
    write_lazy(analysis_out, "transformation-catalog", token or "all", obj)
    return obj


# ---------------------------------------------------------------------------
# Conceptual model implementation profile derived view
# ---------------------------------------------------------------------------

_CONCEPTUAL_CACHE_RE = re.compile(r"(cache|redis|hazelcast|memcached|caffeine)", re.IGNORECASE)
_CONCEPTUAL_EXTERNAL_RE = re.compile(r"(resttemplate|webclient|feign|http|api|connector|gateway|adapter|proxy|remote)", re.IGNORECASE)
_CONCEPTUAL_URL_RE = re.compile(r"(url|uri|host|endpoint|base[_\-.]?path|base[_\-.]?url)", re.IGNORECASE)


def _conceptual_id(prefix: str, *parts: Any) -> str:
    raw = "|".join(str(p or "").strip().lower() for p in parts if p is not None)
    if not raw:
        raw = prefix
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10]
    return f"{prefix}_{digest}"


def _first_non_empty(*values: Any) -> Any:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        if isinstance(value, list) and not value:
            continue
        return value
    return None


def _conceptual_location(item: dict[str, Any]) -> dict[str, Any]:
    props = _props(item)
    locs = _locations_from_item(item)
    loc = locs[0] if locs else {}
    file_value = _first_non_empty(props.get("file"), props.get("file_path"), loc.get("file"), loc.get("file_path"))
    return {
        k: v for k, v in {
            "file": file_value,
            "class": _first_non_empty(props.get("class_name"), props.get("controller_class"), props.get("listener_class"), props.get("producer_class")),
            "method": _first_non_empty(props.get("method_name"), props.get("method"), props.get("operation")),
            "line_start": _first_non_empty(props.get("line_start"), loc.get("line_start")),
            "line_end": _first_non_empty(props.get("line_end"), loc.get("line_end")),
        }.items() if v is not None
    }


def _conceptual_status(item: dict[str, Any], *, default: str = "candidate") -> str:
    level = _strict_evidence_level(item, default=default)
    if level in {"confirmed_by_analyzer", "confirmed_by_llm_source_inspection"}:
        return "confirmed_by_code"
    if level == "candidate_signal_navigation_only":
        return "inferred_from_names"
    if level == "not_applicable":
        return "not_applicable"
    raw = str(_first_non_empty(_props(item).get("evidence_status"), _props(item).get("status"), default) or "").lower()
    if raw in {"confirmed", "derived_by_static_analysis", "physical_table_confirmed"}:
        return "confirmed_by_code"
    if raw in {"candidate", "candidate_by_naming", "inferred_from_names"}:
        return "inferred_from_names"
    return "not_confirmed_by_code" if raw == "not_confirmed_by_code" else "unresolved_static_analysis"


def _conceptual_refs(item: dict[str, Any]) -> list[str]:
    return _evidence_refs(item)


def _append_unique(items: list[dict[str, Any]], item: dict[str, Any], seen: set[tuple[str, str]]) -> None:
    key = (str(item.get("kind") or ""), normalize_name(str(item.get("name") or item.get("id") or "")))
    if key in seen:
        return
    seen.add(key)
    items.append(item)


def _sql_object_kind(props: dict[str, Any]) -> str:
    text = " ".join(str(_first_non_empty(props.get(k), "")) for k in ["kind", "object_kind", "statement_type", "statement_preview", "sql", "statement"])
    low = text.lower()
    if "materialized view" in low:
        return "materialized_view"
    if re.search(r"\bcreate\s+view\b", low):
        return "db_view"
    if re.search(r"\bcreate\s+table\b", low):
        return "db_table"
    return str(_first_non_empty(props.get("object_kind"), props.get("kind"), "sql_object"))


def _conceptual_asset_inventory(analysis_out: Path, *, max_results: int) -> list[dict[str, Any]]:
    assets: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    for item in _db_schema_items(analysis_out, "db_schema_tables"):
        name = str(_first_non_empty(item.get("table_name"), item.get("name"), item.get("object_name")) or "").strip()
        if not name:
            continue
        _append_unique(assets, {
            "id": _conceptual_id("conceptual_asset", "db_table", name),
            "kind": "db_table",
            "name": name,
            "implementation_status": "physical_table_confirmed",
            "evidence_status": "confirmed_by_code",
            "evidence_refs": _conceptual_refs(item),
            "location": _conceptual_location(item),
            "source_artifact": "db_schema_tables",
        }, seen)
        if len(assets) >= max_results:
            return assets

    for item in _sql_create_facts(analysis_out):
        props = _props(item)
        name = _table_name_from_sql_fact(item)
        if not name:
            continue
        kind = _sql_object_kind(props)
        _append_unique(assets, {
            "id": _conceptual_id("conceptual_asset", kind, name),
            "kind": "cache_view" if kind == "materialized_view" and str(name).lower().startswith("cache.") else kind,
            "name": name,
            "implementation_status": "confirmed_sql_view" if "view" in kind else "confirmed_sql_object",
            "evidence_status": "confirmed_by_code",
            "evidence_refs": _conceptual_refs(item),
            "location": _conceptual_location(item),
            "source_artifact": "sql_create",
        }, seen)
        if len(assets) >= max_results:
            return assets

    for item in _compact_or_facts(analysis_out, "persistent_structures", "persistent_structure"):
        props = _props(item)
        name = str(_first_non_empty(props.get("storage_target"), props.get("object_name"), props.get("table_name"), props.get("name")) or "").strip()
        if not name:
            continue
        _append_unique(assets, {
            "id": _conceptual_id("conceptual_asset", "persistent_structure", name),
            "kind": "persistent_structure",
            "name": name,
            "implementation_status": "table_candidate_only" if not _conceptual_refs(item) else "confirmed_by_static_evidence",
            "evidence_status": _conceptual_status(item),
            "evidence_refs": _conceptual_refs(item),
            "location": _conceptual_location(item),
            "source_artifact": "persistent_structure",
        }, seen)
        if len(assets) >= max_results:
            return assets

    for item in _compact_or_facts(analysis_out, "attribute_occurrences", "attribute_occurrence"):
        props = _props(item)
        container = str(_first_non_empty(props.get("container_name"), props.get("object_name"), props.get("class_name")) or "").strip()
        if not container:
            continue
        ckind = str(props.get("container_kind") or "java_object").lower()
        if any(x in ckind or x in container.lower() for x in ["dto", "request", "response", "payload"]):
            kind = "java_dto"
        elif "entity" in ckind or container.lower().endswith("entity"):
            kind = "java_entity"
        else:
            kind = "java_object"
        _append_unique(assets, {
            "id": _conceptual_id("conceptual_asset", kind, container),
            "kind": kind,
            "name": container,
            "implementation_status": "java_object_only",
            "evidence_status": _conceptual_status(item, default="confirmed"),
            "evidence_refs": _conceptual_refs(item),
            "location": _conceptual_location(item),
            "source_artifact": "attribute_occurrence",
        }, seen)
        if len(assets) >= max_results:
            return assets

    for ev in _event_sources(analysis_out, max_results=max_results):
        name = str(_first_non_empty(ev.get("endpoint_path"), ev.get("topic"), ev.get("endpoint_or_topic"), ev.get("operation"), ev.get("method_name")) or "").strip()
        if not name:
            continue
        source_kind = str(ev.get("source_kind") or ev.get("kind") or "event_source").lower()
        if source_kind in {"rest", "http"}:
            kind = "api_endpoint" if ev.get("direction") != "outbound" else "external_service"
        elif source_kind == "kafka":
            kind = "kafka_topic"
        elif source_kind == "scheduler":
            kind = "scheduled_job"
        else:
            kind = "event_source"
        _append_unique(assets, {
            "id": _conceptual_id("conceptual_asset", kind, name),
            "kind": kind,
            "name": name,
            "direction": ev.get("direction"),
            "payload_type": ev.get("payload_type"),
            "request_type": ev.get("request_type"),
            "response_type": ev.get("response_type"),
            "implementation_status": "confirmed_event_source",
            "evidence_status": ev.get("evidence_level") or "confirmed_by_code",
            "evidence_refs": (ev.get("provenance") or {}).get("evidence_refs") or [],
            "location": {k: ev.get(k) for k in ["class_name", "method_name", "operation"] if ev.get(k)},
            "source_artifact": "event_source_catalog",
        }, seen)
        if len(assets) >= max_results:
            return assets

    for item in _compact_or_facts(analysis_out, "data_sources", "data_source"):
        props = _props(item)
        name = str(_first_non_empty(props.get("path"), props.get("file"), props.get("source_name"), props.get("name")) or "").strip()
        if not name:
            continue
        _append_unique(assets, {
            "id": _conceptual_id("conceptual_asset", "file_source", name),
            "kind": "file_source",
            "name": name,
            "implementation_status": "confirmed_by_static_evidence",
            "evidence_status": _conceptual_status(item),
            "evidence_refs": _conceptual_refs(item),
            "location": _conceptual_location(item),
            "source_artifact": "data_source",
        }, seen)
        if len(assets) >= max_results:
            return assets

    for item in _compact_or_facts(analysis_out, "config_resolutions", "config_resolution"):
        props = _props(item)
        name = str(_first_non_empty(props.get("property_key"), props.get("key"), props.get("name"), props.get("placeholder")) or "").strip()
        if not name:
            continue
        _append_unique(assets, {
            "id": _conceptual_id("conceptual_asset", "config_property", name),
            "kind": "config_property",
            "name": name,
            "implementation_status": "config_derived_candidate",
            "evidence_status": _conceptual_status(item, default="candidate"),
            "evidence_refs": _conceptual_refs(item),
            "location": _conceptual_location(item),
            "source_artifact": "config_resolution",
        }, seen)
        if len(assets) >= max_results:
            return assets

    return assets


def _normalize_operation_kind(*values: Any) -> str:
    text = " ".join(str(v or "") for v in values).lower()
    if "insert overwrite" in text:
        return "INSERT_OVERWRITE"
    if "merge" in text:
        return "MERGE"
    if "insert" in text or "save" in text or "persist" in text or "create" in text:
        return "INSERT"
    if "update" in text or "modify" in text:
        return "UPDATE"
    if "delete" in text or "remove" in text:
        return "DELETE"
    if "select" in text or "read" in text or "find" in text or "get" in text or "query" in text:
        return "READ"
    if "write" in text:
        return "WRITE"
    return "UNKNOWN"


def _conceptual_io_points(analysis_out: Path, *, max_results: int) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []

    def add(source_artifact: str, item: dict[str, Any], *, default_kind: str, target_keys: list[str]) -> None:
        if len(items) >= max_results:
            return
        props = _props(item)
        target = _first_non_empty(*(props.get(k) for k in target_keys))
        op_kind = _normalize_operation_kind(props.get("operation_kind"), props.get("write_kind"), props.get("access_kind"), props.get("query_kind"), props.get("statement_type"), props.get("method_name"), default_kind)
        operation = _first_non_empty(props.get("operation"), props.get("method_name"), props.get("terminal_operation_id"), props.get("query_id"))
        items.append({
            "id": _conceptual_id("conceptual_io", source_artifact, _item_id(item), target, operation, op_kind),
            "source_artifact": source_artifact,
            "operation_kind": op_kind,
            "target_asset": target,
            "trigger_or_endpoint": _first_non_empty(props.get("endpoint"), props.get("endpoint_or_topic"), props.get("topic"), props.get("operation")),
            "operation": operation,
            "location": _conceptual_location(item),
            "evidence_status": _conceptual_status(item),
            "evidence_refs": _conceptual_refs(item),
            "summary": _short_summary(props),
        })

    for source_artifact, compact_name, fact_type, default_kind, target_keys in [
        ("storage_access", "storage_accesses", "storage_access", "READ", ["storage_target", "storage_symbol", "repository", "receiver", "target_table"]),
        ("persistent_write", "persistent_writes", "persistent_write", "WRITE", ["storage_target", "target_table", "storage_symbol", "repository", "receiver"]),
        ("read_from_storage", "read_from_storage", "read_from_storage", "READ", ["storage_target", "storage_symbol", "source_table", "repository", "receiver"]),
        ("source_to_storage_lineage", "source_to_storage_lineage", "source_to_storage_lineage", "WRITE", ["storage_target", "storage_field", "saved_object", "target_table"]),
        ("stored_data_access", "stored_field_to_response_field_mappings", "stored_field_to_response_field_mapping", "READ", ["storage_target", "storage_field", "read_type"]),
    ]:
        for item in _compact_or_facts(analysis_out, compact_name, fact_type):
            add(source_artifact, item, default_kind=default_kind, target_keys=target_keys)
            if len(items) >= max_results:
                return items

    return items


def _conceptual_mapper_mappings(analysis_out: Path, *, max_results: int) -> list[dict[str, Any]]:
    mappings: list[dict[str, Any]] = []
    raw_items = _mapping_items(analysis_out, max_results=max_results * 3)
    raw_items.extend(_facts_by_type_items(analysis_out, "field_propagation"))
    raw_items.extend(_facts_by_type_items(analysis_out, "field_identifier_flow"))
    raw_items.extend(_facts_by_type_items(analysis_out, "field_lineage"))

    for raw in raw_items:
        item = raw.get("properties") if isinstance(raw.get("properties"), dict) else raw
        if not isinstance(item, dict):
            continue
        source_object = _first_non_empty(item.get("source_object"), item.get("source_container"), item.get("source_payload"), item.get("source_type"), item.get("from_object"))
        target_object = _first_non_empty(item.get("target_object"), item.get("target_container"), item.get("saved_object"), item.get("storage_target"), item.get("target_type"), item.get("to_object"))
        source_field = _first_non_empty(item.get("source_attribute"), item.get("source_field"), item.get("from_field"), item.get("field"))
        target_field = _first_non_empty(item.get("target_attribute"), item.get("target_field"), item.get("storage_field"), item.get("response_field"), item.get("to_field"))
        if not any([source_object, target_object, source_field, target_field]):
            continue
        mappings.append({
            "id": _conceptual_id("conceptual_mapping", _item_id(raw), source_object, source_field, target_object, target_field),
            "source_object": source_object,
            "target_object": target_object,
            "source_field": source_field,
            "target_field": target_field,
            "mapping_kind": _first_non_empty(item.get("mapping_kind"), item.get("mapping_type"), item.get("derivation_kind"), item.get("flow_kind"), "unknown"),
            "expression": _first_non_empty(item.get("expression"), item.get("source_expression"), item.get("derivation_expression")),
            "evidence_status": _conceptual_status(raw, default="confirmed"),
            "evidence_refs": _conceptual_refs(raw),
            "location": _conceptual_location(raw),
            "source_artifact": _first_non_empty(item.get("source_artifact"), item.get("fact_type"), "mapping_evidence"),
        })
        if len(mappings) >= max_results:
            break
    return mappings


def _service_name_candidate(props: dict[str, Any]) -> str | None:
    for key in ["service_name", "service", "client_name", "client_class", "receiver", "target_service", "endpoint_or_topic", "endpoint", "url", "base_url_property", "property_key"]:
        value = props.get(key)
        if isinstance(value, str) and value.strip():
            text = value.strip()
            if "/" in text and not text.startswith("http"):
                return text.strip("/").split("/")[0] or text
            return text
    return None


def _conceptual_external_dependencies(analysis_out: Path, *, max_results: int) -> list[dict[str, Any]]:
    deps: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    def add(source_artifact: str, item: dict[str, Any], props: dict[str, Any]) -> None:
        if len(deps) >= max_results:
            return
        blob = json.dumps(props, ensure_ascii=False, default=str)
        if not (_CONCEPTUAL_EXTERNAL_RE.search(blob) or str(props.get("direction") or "").lower() == "outbound" or _CONCEPTUAL_URL_RE.search(blob)):
            return
        name = _service_name_candidate(props) or _short_summary(props)
        dep = {
            "id": _conceptual_id("conceptual_external_dependency", source_artifact, name, _item_id(item)),
            "service_name_candidate": name,
            "client_class": _first_non_empty(props.get("client_class"), props.get("class_name"), props.get("receiver"), props.get("producer_class")),
            "method": _first_non_empty(props.get("method_name"), props.get("operation"), props.get("callee_method")),
            "base_url_property": _first_non_empty(props.get("base_url_property"), props.get("property_key"), props.get("placeholder")),
            "resolved_base_url": _first_non_empty(props.get("resolved_base_url"), props.get("resolved_value"), props.get("url"), props.get("endpoint"), props.get("endpoint_or_topic")),
            "resolution_status": _first_non_empty(props.get("resolution_status"), props.get("status"), "not_resolved"),
            "direction": _first_non_empty(props.get("direction"), "outbound"),
            "evidence_status": _conceptual_status(item),
            "evidence_refs": _conceptual_refs(item),
            "location": _conceptual_location(item),
            "source_artifact": source_artifact,
        }
        key = (str(dep.get("client_class") or ""), normalize_name(str(dep.get("service_name_candidate") or "")))
        if key in seen:
            return
        seen.add(key)
        deps.append(dep)

    for item in _compact_or_facts(analysis_out, "access_boundaries", "access_boundary"):
        add("access_boundary", item, _props(item))
    for item in _compact_or_facts(analysis_out, "call_chain_diagnostics", "call_chain_diagnostic"):
        add("call_chain_diagnostic", item, _props(item))
    for item in _compact_or_facts(analysis_out, "config_resolutions", "config_resolution"):
        add("config_resolution", item, _props(item))
    for ev in _event_sources(analysis_out, max_results=max_results * 2):
        if ev.get("direction") == "outbound":
            pseudo = {"properties": ev}
            add("event_source_catalog", pseudo, ev)
    return deps[:max_results]


def _conceptual_triggers(analysis_out: Path, *, max_results: int) -> list[dict[str, Any]]:
    triggers: list[dict[str, Any]] = []
    for ev in _event_sources(analysis_out, max_results=max_results * 2):
        blob = json.dumps(ev, ensure_ascii=False, default=str).lower()
        kind = str(ev.get("source_kind") or ev.get("kind") or "event_source").lower()
        if "scheduler" in kind or "scheduled" in blob or "cron" in blob:
            trigger_kind = "scheduled_job"
        elif kind in {"rest", "http"}:
            trigger_kind = "pump_endpoint" if any(x in blob for x in ["pump", "trigger"]) else "rest_endpoint"
        elif kind == "kafka":
            trigger_kind = "kafka_listener" if ev.get("direction") != "outbound" else "kafka_publish"
        else:
            trigger_kind = kind
        triggers.append({
            "id": _conceptual_id("conceptual_trigger", trigger_kind, ev.get("operation"), ev.get("endpoint_path"), ev.get("topic")),
            "trigger_kind": trigger_kind,
            "endpoint_or_schedule_or_topic": _first_non_empty(ev.get("endpoint_path"), ev.get("endpoint_or_topic"), ev.get("topic"), ev.get("schedule")),
            "operation": ev.get("operation"),
            "class_name": ev.get("class_name"),
            "method_name": ev.get("method_name"),
            "direction": ev.get("direction"),
            "payload_type": ev.get("payload_type"),
            "request_type": ev.get("request_type"),
            "response_type": ev.get("response_type"),
            "evidence_status": ev.get("evidence_level") or "confirmed_by_code",
            "evidence_refs": (ev.get("provenance") or {}).get("evidence_refs") or [],
            "source_artifact": "event_source_catalog",
        })
        if len(triggers) >= max_results:
            return triggers

    for item in _facts_by_type_items(analysis_out, "scheduled_job"):
        props = _props(item)
        triggers.append({
            "id": _conceptual_id("conceptual_trigger", "scheduled_job", _item_id(item), props.get("method_name")),
            "trigger_kind": "scheduled_job",
            "endpoint_or_schedule_or_topic": _first_non_empty(props.get("schedule"), props.get("cron")),
            "operation": _first_non_empty(props.get("operation"), props.get("method_name")),
            "class_name": props.get("class_name"),
            "method_name": props.get("method_name"),
            "evidence_status": _conceptual_status(item),
            "evidence_refs": _conceptual_refs(item),
            "location": _conceptual_location(item),
            "source_artifact": "scheduled_job",
        })
        if len(triggers) >= max_results:
            break
    return triggers


def _conceptual_cache_assets(analysis_out: Path, *, max_results: int) -> list[dict[str, Any]]:
    caches: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    def add(kind: str, name: str, item: dict[str, Any], source_artifact: str, *, access_kind: Any = None, source_tables: Any = None) -> None:
        if len(caches) >= max_results or not name:
            return
        cache = {
            "id": _conceptual_id("conceptual_cache", kind, name, _item_id(item)),
            "cache_kind": kind,
            "asset_name": name,
            "access_kind": access_kind,
            "source_tables": source_tables or [],
            "ttl_or_invalidation_evidence": _first_non_empty(_props(item).get("ttl"), _props(item).get("expiration"), _props(item).get("invalidation")),
            "evidence_status": _conceptual_status(item),
            "evidence_refs": _conceptual_refs(item),
            "location": _conceptual_location(item),
            "source_artifact": source_artifact,
        }
        key = (kind, normalize_name(name))
        if key in seen:
            return
        seen.add(key)
        caches.append(cache)

    for source_artifact, compact_name, fact_type in [
        ("storage_access", "storage_accesses", "storage_access"),
        ("access_boundary", "access_boundaries", "access_boundary"),
    ]:
        for item in _compact_or_facts(analysis_out, compact_name, fact_type):
            props = _props(item)
            blob = json.dumps(props, ensure_ascii=False, default=str)
            if not _CONCEPTUAL_CACHE_RE.search(blob):
                continue
            name = str(_first_non_empty(props.get("cache_name"), props.get("storage_target"), props.get("receiver"), props.get("endpoint_or_topic"), props.get("method_name")) or "")
            low = blob.lower()
            if "redis" in low:
                kind = "redis"
            elif "hazelcast" in low:
                kind = "hazelcast"
            elif "caffeine" in low:
                kind = "caffeine"
            elif "memcached" in low:
                kind = "memcached"
            else:
                kind = "cache"
            add(kind, name, item, source_artifact, access_kind=_first_non_empty(props.get("access_kind"), props.get("method_name")))
            if len(caches) >= max_results:
                return caches

    for item in _sql_create_facts(analysis_out):
        props = _props(item)
        kind = _sql_object_kind(props)
        name = _table_name_from_sql_fact(item) or ""
        low = f"{kind} {name} {json.dumps(props, ensure_ascii=False, default=str)}".lower()
        if kind == "materialized_view" or low.startswith("cache.") or ".cache" in low or " cache" in low:
            add("db_materialized_view" if kind == "materialized_view" else "cache_schema_view", name, item, "sql_create", access_kind="refresh_or_read", source_tables=props.get("source_tables") or props.get("tables") or [])
        if len(caches) >= max_results:
            return caches
    return caches


def _conceptual_entity_implementation_links(analysis_out: Path, *, max_results: int) -> list[dict[str, Any]]:
    links: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()

    def add(link_type: str, conceptual_entity: Any, implementation_target: Any, item: dict[str, Any], source_artifact: str, status: str | None = None) -> None:
        if len(links) >= max_results or not conceptual_entity or not implementation_target:
            return
        key = (link_type, normalize_name(str(conceptual_entity)), normalize_name(str(implementation_target)))
        if key in seen:
            return
        seen.add(key)
        links.append({
            "id": _conceptual_id("conceptual_link", link_type, conceptual_entity, implementation_target),
            "link_type": link_type,
            "conceptual_entity_candidate": conceptual_entity,
            "implementation_target": implementation_target,
            "evidence_status": status or _conceptual_status(item),
            "evidence_refs": _conceptual_refs(item),
            "location": _conceptual_location(item),
            "source_artifact": source_artifact,
        })

    for item in _compact_or_facts(analysis_out, "source_to_storage_lineage", "source_to_storage_lineage"):
        props = _props(item)
        add("source_payload_to_storage", _first_non_empty(props.get("source_payload"), props.get("source_object")), props.get("storage_target"), item, "source_to_storage_lineage", status="concept_confirmed_by_code" if str(props.get("lineage_status") or "").lower() == "confirmed" else None)
        add("saved_object_to_storage", props.get("saved_object"), props.get("storage_target"), item, "source_to_storage_lineage")
        if len(links) >= max_results:
            return links

    for item in _mapping_items(analysis_out, max_results=max_results * 3):
        source = _first_non_empty(item.get("source_object"), item.get("source_container"), item.get("source_payload"))
        target = _first_non_empty(item.get("target_object"), item.get("target_container"), item.get("saved_object"), item.get("storage_target"))
        add("object_mapping", source, target, item, "mapping_evidence")
        if len(links) >= max_results:
            return links

    # Name-based weak links between Java objects and physical tables. These are explicitly marked as candidates.
    tables = [str(x.get("table_name") or "") for x in _db_schema_items(analysis_out, "db_schema_tables") if x.get("table_name")]
    containers = sorted({str(_props(x).get("container_name") or "") for x in _compact_or_facts(analysis_out, "attribute_occurrences", "attribute_occurrence") if _props(x).get("container_name")})
    for container in containers:
        c_norm = normalize_name(container.replace("DTO", "").replace("Dto", "").replace("Entity", ""))
        for table in tables:
            t_norm = normalize_name(table.replace("_", ""))
            if c_norm and (c_norm == t_norm or c_norm in t_norm or t_norm in c_norm):
                add("name_based_object_table_candidate", container, table, {"properties": {"evidence_status": "candidate_by_naming"}}, "name_match", status="inferred_from_names")
                if len(links) >= max_results:
                    return links
    return links


def _counts_by(items: list[dict[str, Any]], key: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for item in items:
        value = str(item.get(key) or "unknown")
        out[value] = out.get(value, 0) + 1
    return dict(sorted(out.items()))


_CONCEPTUAL_CARD_TECHNICAL_SUFFIXES = {
    "entity", "entities", "dto", "request", "response", "payload", "service", "controller",
    "repository", "repo", "dao", "mapper", "converter", "adapter", "client", "proxy",
    "gateway", "impl", "implementation", "model", "view", "record", "records", "message",
    "event", "events", "handler", "listener", "producer", "consumer",
}
_CONCEPTUAL_CARD_SUPPORTING_SUFFIXES = {
    "history", "histories", "archive", "archives", "audit", "audits", "outbox", "queue",
    "queues", "notification", "notifications", "log", "logs", "status", "statuses", "state",
    "states", "version", "versions", "single", "details", "detail", "item", "items",
}
_CONCEPTUAL_CARD_SUPPORTING_PATTERN_TOKENS = {
    "history", "archive", "audit", "outbox", "queue", "notification", "notifications",
    "log", "status", "state", "version", "single", "details", "detail", "item", "cache",
}
_CONCEPTUAL_CARD_ACTION_TOKENS = {
    "add", "remove", "delete", "del", "create", "update", "modify", "save", "persist",
    "insert", "merge", "get", "find", "read", "load", "select", "query", "put",
    "set", "check", "validate", "process", "execute", "run", "handle", "trigger", "refresh",
    "send", "publish", "consume", "listen", "call", "map", "convert",
}


def _singularize_conceptual_token(token: str) -> str:
    if len(token) > 4 and token.endswith("ies"):
        return f"{token[:-3]}y"
    if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def _conceptual_name_tokens(value: Any) -> list[str]:
    if value is None:
        return []
    text = str(value).strip()
    if not text:
        return []
    # Keep the concrete object part from schema.table, URLs and endpoint-like strings.
    text = text.strip()
    text = re.sub(r"^[A-Z]+\s+", "", text)
    if "://" in text:
        text = text.split("://", 1)[1].split("/", 1)[0]
    if "/" in text:
        path = re.sub(r"^[A-Z]+\s+", "", text).strip("/")
        parts = [p for p in path.split("/") if p]
        if parts:
            last_norm = normalize_name(parts[-1])
            # Endpoints are often /domain/action; prefer the domain segment over pure CRUD/action verbs.
            if last_norm in _CONCEPTUAL_CARD_ACTION_TOKENS and len(parts) > 1:
                text = parts[-2]
            else:
                text = parts[-1]
    if "." in text and not re.search(r"\.[a-zA-Z]{2,4}(:|/|$)", text):
        text = text.split(".")[-1]
    norm = normalize_name(text)
    tokens = [_singularize_conceptual_token(t) for t in norm.split("_") if t]
    tokens = [t for t in tokens if t not in _CONCEPTUAL_CARD_TECHNICAL_SUFFIXES and not re.fullmatch(r"v?\d+", t)]
    while tokens and tokens[-1] in _CONCEPTUAL_CARD_ACTION_TOKENS:
        tokens = tokens[:-1]
    return [t for t in tokens if t not in _CONCEPTUAL_CARD_ACTION_TOKENS]


def _conceptual_card_family(value: Any) -> str | None:
    tokens = _conceptual_name_tokens(value)
    if not tokens:
        return None
    while len(tokens) > 1 and tokens[-1] in _CONCEPTUAL_CARD_SUPPORTING_SUFFIXES:
        tokens = tokens[:-1]
    if not tokens:
        return None
    return "_".join(tokens)


def _conceptual_display_name(family: str) -> str:
    if not family:
        return "Unknown"
    return " ".join(part.capitalize() for part in family.split("_") if part) or family


def _conceptual_subdomain_candidate(*names: Any) -> str | None:
    for name in names:
        if not isinstance(name, str):
            continue
        text = name.strip()
        text = re.sub(r"^[A-Z]+\s+", "", text)
        if "." in text and not text.startswith("http"):
            left = text.split(".", 1)[0].strip()
            if left:
                return normalize_name(left)
        if "/" in text.strip("/"):
            first = text.strip("/").split("/", 1)[0]
            if first and first.upper() not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
                return normalize_name(first)
    return None


def _conceptual_card_evidence_refs(*items: dict[str, Any], limit: int = 80) -> list[str]:
    refs: list[str] = []
    for item in items:
        for ref in item.get("evidence_refs") or []:
            if ref:
                refs.append(str(ref))
    out: list[str] = []
    seen: set[str] = set()
    for ref in refs:
        if ref in seen:
            continue
        seen.add(ref)
        out.append(ref)
        if len(out) >= limit:
            break
    return out


def _conceptual_card_asset_bucket(kind: str) -> str | None:
    return {
        "db_table": "db_tables",
        "persistent_structure": "db_tables",
        "db_view": "db_views",
        "materialized_view": "materialized_views",
        "cache_view": "materialized_views",
        "java_entity": "java_entities",
        "java_dto": "java_dtos",
        "java_object": "java_objects",
        "api_endpoint": "api_endpoints",
        "kafka_topic": "kafka_topics",
        "external_service": "external_services",
        "config_property": "config_properties",
        "file_source": "config_properties",
    }.get(kind)


def _conceptual_card_asset_ref(asset: dict[str, Any]) -> dict[str, Any]:
    return {k: asset.get(k) for k in ["id", "kind", "name", "implementation_status", "evidence_status", "evidence_refs", "source_artifact"] if asset.get(k) is not None}


def _conceptual_card_physical_status(card: dict[str, Any]) -> str:
    assets = card["assets"]
    if any((x.get("implementation_status") == "physical_table_confirmed") or (x.get("kind") == "db_table" and x.get("evidence_status") == "confirmed_by_code") for x in assets["db_tables"]):
        return "confirmed_schema_table"
    if assets["db_tables"]:
        return "table_candidate_only"
    if assets["materialized_views"] or assets["db_views"] or assets["cache_assets"]:
        return "cache_or_view_only"
    if assets["java_entities"] or assets["java_dtos"] or assets["java_objects"]:
        return "java_object_only"
    if assets["external_services"] or card.get("external_dependency_refs"):
        return "external_dependency_only"
    return "not_confirmed"


def _conceptual_card_concept_status(card: dict[str, Any]) -> str:
    statuses = [str(x.get("evidence_status") or "") for group in card["assets"].values() for x in group]
    statuses.extend(str(x.get("evidence_status") or "") for x in card.get("_related_items", []))
    link_types = {str(x.get("link_type") or "") for x in card.get("_links", [])}
    if any(s in {"confirmed_by_code", "concept_confirmed_by_code"} for s in statuses):
        return "confirmed_by_code"
    if card.get("external_dependency_refs") and not any(card["assets"].get(k) for k in ["db_tables", "java_entities", "java_dtos", "java_objects"]):
        return "concept_confirmed_or_referenced"
    if link_types and link_types <= {"name_based_object_table_candidate"}:
        return "inferred_from_names"
    if statuses:
        return "partial"
    return "not_confirmed_by_code"


def _conceptual_card_overall_status(card: dict[str, Any]) -> str:
    concept_status = card.get("concept_confirmation_status")
    physical_status = card.get("physical_confirmation_status")
    if concept_status == "confirmed_by_code" and physical_status == "confirmed_schema_table":
        return "confirmed_by_code"
    if concept_status in {"confirmed_by_code", "concept_confirmed_or_referenced", "partial"}:
        return "partial"
    if concept_status == "inferred_from_names":
        return "inferred_from_names"
    return "not_confirmed_by_code"


def _conceptual_card_patterns(card: dict[str, Any]) -> list[str]:
    names = " ".join(card.get("technical_name_keys") or []).lower()
    assets = card["assets"]
    patterns: set[str] = set()
    if assets["db_tables"] or assets["java_entities"]:
        patterns.add("aggregate")
    if any(t in names for t in ["dict", "dictionary", "reference", "catalog", "nsi", "type", "category"]):
        patterns.add("dictionary")
    if any(t in names for t in ["master", "employee", "permission", "profile"]):
        patterns.add("master_data")
    if any(t in names for t in ["booking", "reservation", "order", "payment", "transaction", "request"]):
        patterns.add("transaction")
    if any(t in names for t in ["_link", "link_", "relation", "mapping", "xref", "_to_"]):
        patterns.add("link_table")
    if any(t in names for t in ["audit", "history", "log", "status_history"]):
        patterns.add("audit_history")
    if "archive" in names:
        patterns.add("archive")
    if any(t in names for t in ["outbox", "queue", "notification"]):
        patterns.add("outbox_or_queue")
    if assets["cache_assets"]:
        patterns.add("cache_projection")
    if assets["materialized_views"]:
        patterns.add("materialized_view")
    if card.get("external_dependency_refs") and not assets["db_tables"]:
        patterns.add("externalized_master_data")
    if any(any(term in str(_first_non_empty(x.get("trigger_kind"), x.get("endpoint_or_schedule_or_topic"), x.get("operation")) or "").lower() for term in ["pump", "trigger", "import"]) for x in card.get("_triggers", [])):
        patterns.add("pump_import")
    if any(str(x.get("trigger_kind") or "") == "scheduled_job" for x in card.get("_triggers", [])):
        patterns.add("scheduled_refresh")
    if len(assets["db_tables"]) + len(assets["db_views"]) + len(assets["materialized_views"]) + len(assets["cache_assets"]) > 1:
        patterns.add("split_implementation")
    if any(t in names.split() or t in names for t in _CONCEPTUAL_CARD_SUPPORTING_PATTERN_TOKENS):
        patterns.add("technical_supporting_asset")
    if card.get("concept_confirmation_status") == "inferred_from_names":
        patterns.add("name_based_candidate_only")
    preferred_order = [
        "aggregate", "dictionary", "master_data", "transaction", "link_table", "audit_history",
        "archive", "outbox_or_queue", "cache_projection", "materialized_view",
        "externalized_master_data", "pump_import", "scheduled_refresh", "split_implementation",
        "technical_supporting_asset", "name_based_candidate_only",
    ]
    return [p for p in preferred_order if p in patterns]


def _conceptual_card_limitations(card: dict[str, Any]) -> list[str]:
    limitations: list[str] = []
    if card.get("concept_confirmation_status") == "inferred_from_names":
        limitations.append("This card is built only from name-based candidates; do not treat it as confirmed implementation lineage without drill-down evidence.")
    if card.get("physical_confirmation_status") in {"java_object_only", "external_dependency_only", "not_confirmed"}:
        limitations.append("Local physical table is not confirmed by this derived view; use table/storage drill-down before claiming local persistence.")
    if any(x.get("link_type") == "name_based_object_table_candidate" for x in card.get("_links", [])):
        limitations.append("Name-based object/table links are candidate-only and must not be promoted to confirmed lineage.")
    return limitations


def _conceptual_implementation_cards(
    assets: list[dict[str, Any]],
    io_points: list[dict[str, Any]],
    mapper_mappings: list[dict[str, Any]],
    external_dependencies: list[dict[str, Any]],
    triggers: list[dict[str, Any]],
    cache_assets: list[dict[str, Any]],
    links: list[dict[str, Any]],
    *,
    max_results: int,
) -> list[dict[str, Any]]:
    cards: dict[str, dict[str, Any]] = {}

    def card_for(family: str | None) -> dict[str, Any] | None:
        if not family:
            return None
        if family not in cards:
            cards[family] = {
                "card_id": _conceptual_id("concept_card", family),
                "canonical_name_candidate": _conceptual_display_name(family),
                "technical_name_keys": [],
                "concept_family": family,
                "subdomain_candidate": None,
                "concept_confirmation_status": "not_confirmed_by_code",
                "physical_confirmation_status": "not_confirmed",
                "evidence_status": "not_confirmed_by_code",
                "evidence_refs": [],
                "assets": {
                    "db_tables": [],
                    "db_views": [],
                    "materialized_views": [],
                    "cache_assets": [],
                    "java_entities": [],
                    "java_dtos": [],
                    "java_objects": [],
                    "api_endpoints": [],
                    "kafka_topics": [],
                    "external_services": [],
                    "config_properties": [],
                },
                "io_summary": {
                    "read_count": 0,
                    "write_count": 0,
                    "insert_count": 0,
                    "update_count": 0,
                    "delete_count": 0,
                    "merge_count": 0,
                    "io_point_refs": [],
                },
                "mapper_mapping_refs": [],
                "trigger_refs": [],
                "external_dependency_refs": [],
                "cache_asset_refs": [],
                "concept_implementation_link_refs": [],
                "implementation_patterns": [],
                "limitations": [],
                "_related_items": [],
                "_links": [],
                "_triggers": [],
            }
        return cards[family]

    def add_name(card: dict[str, Any], *names: Any) -> None:
        for name in names:
            if not name:
                continue
            text = str(name).strip()
            if not text:
                continue
            if _conceptual_card_family(text) is None and normalize_name(text) in _CONCEPTUAL_CARD_ACTION_TOKENS:
                continue
            if text not in card["technical_name_keys"]:
                card["technical_name_keys"].append(text)
            if not card.get("subdomain_candidate"):
                card["subdomain_candidate"] = _conceptual_subdomain_candidate(text)

    def append_unique_ref(card: dict[str, Any], bucket: str, value: Any) -> None:
        if not value:
            return
        text = str(value)
        if text not in card[bucket]:
            card[bucket].append(text)

    def append_unique_obj(bucket: list[dict[str, Any]], value: dict[str, Any]) -> None:
        vid = value.get("id") or value.get("name") or value.get("asset_name")
        if any((x.get("id") or x.get("name") or x.get("asset_name")) == vid for x in bucket):
            return
        bucket.append(value)

    for asset in assets:
        name = asset.get("name")
        family_source = _first_non_empty(asset.get("payload_type"), asset.get("request_type"), asset.get("response_type"), name) if str(asset.get("kind") or "") in {"api_endpoint", "kafka_topic"} else name
        card = card_for(_conceptual_card_family(family_source))
        if not card:
            continue
        bucket = _conceptual_card_asset_bucket(str(asset.get("kind") or ""))
        if bucket:
            append_unique_obj(card["assets"][bucket], _conceptual_card_asset_ref(asset))
        add_name(card, name, asset.get("payload_type"), asset.get("request_type"), asset.get("response_type"))
        card["_related_items"].append(asset)

    for cache in cache_assets:
        name = cache.get("asset_name")
        card = card_for(_conceptual_card_family(name))
        if not card:
            continue
        append_unique_obj(card["assets"]["cache_assets"], {k: cache.get(k) for k in ["id", "cache_kind", "asset_name", "access_kind", "evidence_status", "evidence_refs", "source_artifact"] if cache.get(k) is not None})
        append_unique_ref(card, "cache_asset_refs", cache.get("id"))
        add_name(card, name)
        card["_related_items"].append(cache)

    for io in io_points:
        families = {_conceptual_card_family(io.get("target_asset")), _conceptual_card_family(io.get("operation")), _conceptual_card_family(io.get("trigger_or_endpoint"))}
        families.discard(None)
        for family in families:
            card = card_for(family)
            if not card:
                continue
            op_kind = str(io.get("operation_kind") or "").upper()
            if op_kind in {"READ", "SELECT"}:
                card["io_summary"]["read_count"] += 1
            elif op_kind == "WRITE":
                card["io_summary"]["write_count"] += 1
            elif op_kind in {"INSERT", "INSERT_OVERWRITE"}:
                card["io_summary"]["insert_count"] += 1
            elif op_kind == "UPDATE":
                card["io_summary"]["update_count"] += 1
            elif op_kind == "DELETE":
                card["io_summary"]["delete_count"] += 1
            elif op_kind == "MERGE":
                card["io_summary"]["merge_count"] += 1
            if io.get("id") and io.get("id") not in card["io_summary"]["io_point_refs"]:
                card["io_summary"]["io_point_refs"].append(io.get("id"))
            add_name(card, io.get("target_asset"), io.get("operation"), io.get("trigger_or_endpoint"))
            card["_related_items"].append(io)

    for mapping in mapper_mappings:
        families = {_conceptual_card_family(mapping.get("source_object")), _conceptual_card_family(mapping.get("target_object"))}
        families.discard(None)
        for family in families:
            card = card_for(family)
            if not card:
                continue
            append_unique_ref(card, "mapper_mapping_refs", mapping.get("id"))
            add_name(card, mapping.get("source_object"), mapping.get("target_object"))
            card["_related_items"].append(mapping)

    for trigger in triggers:
        payload_family = _conceptual_card_family(_first_non_empty(trigger.get("payload_type"), trigger.get("request_type"), trigger.get("response_type")))
        if payload_family:
            families = {payload_family}
        else:
            families = {_conceptual_card_family(trigger.get("endpoint_or_schedule_or_topic")), _conceptual_card_family(trigger.get("operation")), _conceptual_card_family(trigger.get("class_name")), _conceptual_card_family(trigger.get("method_name"))}
        families.discard(None)
        for family in families:
            card = card_for(family)
            if not card:
                continue
            append_unique_ref(card, "trigger_refs", trigger.get("id"))
            add_name(card, trigger.get("endpoint_or_schedule_or_topic"), trigger.get("operation"), trigger.get("class_name"), trigger.get("method_name"), trigger.get("payload_type"), trigger.get("request_type"), trigger.get("response_type"))
            card["_related_items"].append(trigger)
            card["_triggers"].append(trigger)

    for dep in external_dependencies:
        families = {_conceptual_card_family(dep.get("service_name_candidate")), _conceptual_card_family(dep.get("client_class")), _conceptual_card_family(dep.get("method"))}
        families.discard(None)
        for family in families:
            card = card_for(family)
            if not card:
                continue
            append_unique_ref(card, "external_dependency_refs", dep.get("id"))
            append_unique_obj(card["assets"]["external_services"], {k: dep.get(k) for k in ["id", "service_name_candidate", "client_class", "method", "direction", "evidence_status", "evidence_refs", "source_artifact"] if dep.get(k) is not None})
            add_name(card, dep.get("service_name_candidate"), dep.get("client_class"), dep.get("method"))
            card["_related_items"].append(dep)

    for link in links:
        families = {_conceptual_card_family(link.get("conceptual_entity_candidate")), _conceptual_card_family(link.get("implementation_target"))}
        families.discard(None)
        for family in families:
            card = card_for(family)
            if not card:
                continue
            append_unique_ref(card, "concept_implementation_link_refs", link.get("id"))
            add_name(card, link.get("conceptual_entity_candidate"), link.get("implementation_target"))
            card["_related_items"].append(link)
            card["_links"].append(link)

    finalized: list[dict[str, Any]] = []
    for family in sorted(cards):
        card = cards[family]
        card["technical_name_keys"] = sorted(card["technical_name_keys"], key=lambda x: (normalize_name(x), x))[:30]
        card["concept_confirmation_status"] = _conceptual_card_concept_status(card)
        card["physical_confirmation_status"] = _conceptual_card_physical_status(card)
        card["evidence_status"] = _conceptual_card_overall_status(card)
        card["evidence_refs"] = _conceptual_card_evidence_refs(*card.get("_related_items", []))
        card["implementation_patterns"] = _conceptual_card_patterns(card)
        card["limitations"] = _conceptual_card_limitations(card)
        # Avoid internal grouping helpers in the public evidence payload.
        card.pop("_related_items", None)
        card.pop("_links", None)
        card.pop("_triggers", None)
        finalized.append(card)
        if len(finalized) >= max_results:
            break
    return finalized


def conceptual_implementation_profile(analysis_out: Path, token: str = "", max_results: int = 1000) -> dict[str, Any]:
    """Return a deterministic implementation-facing view for conceptual model reports.

    This command does not run new scanners and does not classify sensitive/PII data.
    It groups already extracted evidence into physical assets, I/O points, mappings,
    external dependencies, triggers, cache assets and implementation links so LLM
    profiles can cite concrete code/storage facts without manually stitching many
    low-level views together.
    """
    per_section = max(1, max_results)
    assets = _conceptual_asset_inventory(analysis_out, max_results=per_section)
    io_points = _conceptual_io_points(analysis_out, max_results=per_section)
    mapper_mappings = _conceptual_mapper_mappings(analysis_out, max_results=per_section)
    external_dependencies = _conceptual_external_dependencies(analysis_out, max_results=per_section)
    triggers = _conceptual_triggers(analysis_out, max_results=per_section)
    cache_assets = _conceptual_cache_assets(analysis_out, max_results=per_section)
    links = _conceptual_entity_implementation_links(analysis_out, max_results=per_section)

    if token:
        assets = [x for x in assets if _item_matches_blob(x, token)][:per_section]
        io_points = [x for x in io_points if _item_matches_blob(x, token)][:per_section]
        mapper_mappings = [x for x in mapper_mappings if _item_matches_blob(x, token)][:per_section]
        external_dependencies = [x for x in external_dependencies if _item_matches_blob(x, token)][:per_section]
        triggers = [x for x in triggers if _item_matches_blob(x, token)][:per_section]
        cache_assets = [x for x in cache_assets if _item_matches_blob(x, token)][:per_section]
        links = [x for x in links if _item_matches_blob(x, token)][:per_section]

    concept_cards = _conceptual_implementation_cards(
        assets,
        io_points,
        mapper_mappings,
        external_dependencies,
        triggers,
        cache_assets,
        links,
        max_results=per_section,
    )

    coverage = {
        "asset_inventory_count": len(assets),
        "io_points_count": len(io_points),
        "mapper_mappings_count": len(mapper_mappings),
        "external_dependencies_count": len(external_dependencies),
        "triggers_count": len(triggers),
        "cache_assets_count": len(cache_assets),
        "concept_implementation_links_count": len(links),
        "concept_implementation_cards_count": len(concept_cards),
        "assets_by_kind": _counts_by(assets, "kind"),
        "io_points_by_operation_kind": _counts_by(io_points, "operation_kind"),
        "triggers_by_kind": _counts_by(triggers, "trigger_kind"),
        "cache_assets_by_kind": _counts_by(cache_assets, "cache_kind"),
        "concept_cards_by_evidence_status": _counts_by(concept_cards, "evidence_status"),
        "concept_cards_by_physical_confirmation_status": _counts_by(concept_cards, "physical_confirmation_status"),
    }
    obj = {
        "kind": "conceptual-implementation-profile",
        "analysis_out": str(analysis_out),
        "token": token,
        "selection_policy": "derived implementation view and concept-centric implementation cards over existing compact/facts artifacts; no new scanner stage, no external model comparison and no sensitive/PII classification",
        "asset_inventory": assets,
        "io_points": io_points,
        "mapper_mappings": mapper_mappings,
        "external_dependencies": external_dependencies,
        "triggers": triggers,
        "cache_assets": cache_assets,
        "concept_implementation_links": links,
        "concept_implementation_cards": concept_cards,
        "coverage": coverage,
        "limitations": [
            "This is a derived presentation view over existing analyzer artifacts; it does not inspect source code beyond already materialized evidence.",
            "Name-based object/table links are marked as inferred_from_names and must not be treated as confirmed implementation lineage.",
            "Sensitive/PII signals are intentionally not produced by this view.",
            "Concept implementation cards are deterministic groupings over this response; they do not compare against external conceptual models.",
            "If a section is empty, use lower-level drill-down commands such as system-table-catalog, event-source-catalog, storage-access, transformation-catalog or source-inspect.",
        ],
    }
    write_lazy(analysis_out, "conceptual-implementation-profile", token or "all", obj)
    return obj




def _fdp_deps() -> FdpViewDependencies:
    return FdpViewDependencies(
        compact_or_facts=_compact_or_facts,
        event_sources=_event_sources,
        mapping_items=_mapping_items,
        data_flow_items=_data_flow_items,
        stored_data_access=stored_data_access,
        db_schema_items=_db_schema_items,
        item_id=_item_id,
        item_matches_blob=_item_matches_blob,
        locations_from_item=_locations_from_item,
        evidence_refs=_evidence_refs,
        openspec_id=_openspec_id,
        props=_props,
        status_from_evidence_level=_status_from_evidence_level,
        read_json=read_json,
        write_lazy=write_lazy,
    )


def _openspec_fdp_cases(analysis_out: Path, flows: list[dict[str, Any]], access_paths: list[dict[str, Any]], *, max_results: int = 10000) -> list[dict[str, Any]]:
    return _fdp_view.openspec_fdp_cases(analysis_out, flows, access_paths, max_results=max_results, deps=_fdp_deps())


def foreign_data_persistence_cases(
    analysis_out: Path,
    token: str = "",
    max_results: int = 1000,
    *,
    external_access: str | None = None,
    source_interpretation: str | None = None,
    same_data_link: str | None = None,
    with_persistent_write_refs: str | bool | None = None,
    with_saved_attributes: str | bool | None = None,
    case_id: str | None = None,
) -> dict[str, Any]:
    return _fdp_view.foreign_data_persistence_cases(
        analysis_out,
        token=token,
        max_results=max_results,
        external_access=external_access,
        source_interpretation=source_interpretation,
        same_data_link=same_data_link,
        with_persistent_write_refs=with_persistent_write_refs,
        with_saved_attributes=with_saved_attributes,
        case_id=case_id,
        deps=_fdp_deps(),
    )


def foreign_data_persistence_case_detail(analysis_out: Path, case_id: str, token: str = "") -> dict[str, Any]:
    return _fdp_view.foreign_data_persistence_case_detail(analysis_out, case_id, token=token, deps=_fdp_deps())


def source_inspection_request(analysis_out: Path, token: str = "", max_results: int = 50) -> dict[str, Any]:
    return _search_json_artifacts(
        analysis_out, token, kind="source-inspection-request",
        files=[analysis_out / "compact" / "source_inspection_requests.json", analysis_out / "facts" / "facts_by_type" / "source_inspection_request.json"],
        max_results=max_results,
    )


def source_inspect(analysis_out: Path, token: str, max_results: int = 20, context: int = 4, max_chars: int = 20000) -> dict[str, Any]:
    repo = repo_from_analysis(analysis_out)
    bundle = source_inspection_bundle(repo, token, max_results=max_results, context=context, max_chars=max_chars)
    obj = {"kind": "source-inspect", "analysis_out": str(analysis_out), **bundle}
    write_lazy(analysis_out, "source-inspect", token, obj)
    return obj


def source_open(
    analysis_out: Path,
    file_or_token: str,
    *,
    line: int | None = None,
    start_line: int | None = None,
    end_line: int | None = None,
    context: int = 8,
    max_chars: int = 20000,
) -> dict[str, Any]:
    repo = repo_from_analysis(analysis_out)
    bundle = source_open_bundle(
        repo,
        file_or_token,
        line=line,
        start_line=start_line,
        end_line=end_line,
        context=context,
        max_chars=max_chars,
    )
    obj = {"kind": "source-open", "analysis_out": str(analysis_out), **bundle}
    write_lazy(analysis_out, "source-open", file_or_token, obj)
    return obj


def find_implementations(analysis_out: Path, token: str, max_results: int = 20, context: int = 4) -> dict[str, Any]:
    repo = repo_from_analysis(analysis_out)
    hits = find_possible_implementations(repo, token, max_results=max_results, context=context)
    obj = {
        "kind": "find-implementations",
        "analysis_out": str(analysis_out),
        "token": token,
        "hits": hits,
        "hit_count": len(hits),
        "policy": "read_only_targeted_source_inspection",
    }
    write_lazy(analysis_out, "find-implementations", token, obj)
    return obj



def persistent_structure(analysis_out: Path, token: str = "", max_results: int = 50) -> dict[str, Any]:
    return _search_json_artifacts(
        analysis_out, token, kind="persistent-structure",
        files=[analysis_out / "compact" / "persistent_structures.json", analysis_out / "facts" / "facts_by_type" / "persistent_structure.json"],
        max_results=max_results,
    )


def attribute_occurrence(analysis_out: Path, token: str = "", max_results: int = 50) -> dict[str, Any]:
    return _search_json_artifacts(
        analysis_out, token, kind="attribute-occurrence",
        files=[analysis_out / "compact" / "attribute_occurrences.json", analysis_out / "facts" / "facts_by_type" / "attribute_occurrence.json"],
        max_results=max_results,
    )


def attribute_mapping(analysis_out: Path, token: str = "", max_results: int = 50) -> dict[str, Any]:
    return _search_json_artifacts(
        analysis_out, token, kind="attribute-mapping",
        files=[analysis_out / "compact" / "attribute_mappings.json", analysis_out / "facts" / "facts_by_type" / "attribute_mapping.json"],
        max_results=max_results,
    )


def attribute_derivation(analysis_out: Path, token: str = "", max_results: int = 50) -> dict[str, Any]:
    return _search_json_artifacts(
        analysis_out, token, kind="attribute-derivation",
        files=[analysis_out / "compact" / "attribute_derivations.json", analysis_out / "facts" / "facts_by_type" / "attribute_derivation.json"],
        max_results=max_results,
    )


def data_dictionary(analysis_out: Path, token: str = "", max_results: int = 50) -> dict[str, Any]:
    return _search_json_artifacts(
        analysis_out, token, kind="data-dictionary",
        files=[analysis_out / "compact" / "data_dictionary.json", analysis_out / "facts" / "facts_by_type" / "data_dictionary_entry.json"],
        max_results=max_results,
    )


def external_dependency(analysis_out: Path, token: str = "", max_results: int = 50) -> dict[str, Any]:
    return _search_json_artifacts(
        analysis_out, token, kind="external-dependency",
        files=[
            analysis_out / "compact" / "external_dependencies.json",
            analysis_out / "facts" / "facts_by_type" / "external_dependency.json",
            analysis_out / "facts" / "facts_by_type" / "external_dependency_call.json",
        ],
        max_results=max_results,
    )


def sql_query_model(analysis_out: Path, token: str = "", max_results: int = 50) -> dict[str, Any]:
    return _search_json_artifacts(
        analysis_out, token, kind="sql-query-model",
        files=[analysis_out / "compact" / "sql_query_models.json", analysis_out / "facts" / "facts_by_type" / "sql_query_model.json"],
        max_results=max_results,
    )


def system_interface_catalog(analysis_out: Path, token: str = "", max_results: int = 10000) -> dict[str, Any]:
    data = read_json(analysis_out / "compact" / "system_interface_catalog.json", None)
    if isinstance(data, dict):
        interfaces: list[dict[str, Any]] = []
        for key in ("production_interfaces", "test_interfaces", "all_interfaces", "interfaces", "items"):
            value = data.get(key)
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict) and _item_matches_blob(item, token):
                        interfaces.append(item)
        # Preserve original grouping when unfiltered; otherwise return matching items.
        if token:
            selected = interfaces[:max_results]
            obj = {
                "kind": "system-interface-catalog",
                "analysis_out": str(analysis_out),
                "token": token,
                "total_count": len(interfaces),
                "included_count": len(selected),
                "omitted_count": max(0, len(interfaces) - len(selected)),
                "items": selected,
            }
        else:
            obj = dict(data)
            obj.setdefault("kind", "system-interface-catalog")
            obj.setdefault("analysis_out", str(analysis_out))
            all_count = len(data.get("all_interfaces") or []) or len(interfaces)
            obj.setdefault("total_count", all_count)
            if isinstance(obj.get("all_interfaces"), list) and len(obj["all_interfaces"]) > max_results:
                obj["all_interfaces"] = obj["all_interfaces"][:max_results]
                obj["materialization_status"] = "truncated"
                obj["included_count"] = max_results
                obj["omitted_count"] = max(0, all_count - max_results)
        write_lazy(analysis_out, "system-interface-catalog", token or "all", obj)
        return obj
    return _search_json_artifacts(
        analysis_out, token, kind="system-interface-catalog",
        files=[analysis_out / "facts" / "facts_by_type" / "system_interface_catalog.json"],
        max_results=max_results,
    )


def system_description_compact(analysis_out: Path, token: str = "", max_results: int = 10000) -> dict[str, Any]:
    data = read_json(analysis_out / "compact" / "system_description_compact.json", None)
    if isinstance(data, dict):
        obj = dict(data)
        obj.setdefault("kind", "system-description-compact")
        obj.setdefault("analysis_out", str(analysis_out))
        write_lazy(analysis_out, "system-description-compact", token or "all", obj)
        return obj
    return {"kind": "system-description-compact", "analysis_out": str(analysis_out), "token": token, "hit_count": 0, "hits": []}


def system_report_evidence_pack(analysis_out: Path, token: str = "", max_results: int = 10000) -> dict[str, Any]:
    data = read_json(analysis_out / "compact" / "system_report_evidence_pack.json", None)
    if isinstance(data, dict):
        obj = dict(data)
        obj.setdefault("kind", "system-report-evidence-pack")
        obj.setdefault("analysis_out", str(analysis_out))
        # The pack is designed for report materialization. Keep it intact by default.
        # The evidence access layer records a lazy copy for agents/report stages.
        write_lazy(analysis_out, "system-report-evidence-pack", token or "all", obj)
        return obj
    return {"kind": "system-report-evidence-pack", "analysis_out": str(analysis_out), "token": token, "hit_count": 0, "hits": []}


def storage_usage_summary(analysis_out: Path, token: str = "", max_results: int = 50, table: str | None = None) -> dict[str, Any]:
    return _search_json_artifacts(
        analysis_out, token, kind="storage-usage-summary",
        files=[analysis_out / "compact" / "storage_usage_summaries.json", analysis_out / "facts" / "facts_by_type" / "storage_usage_summary.json"],
        max_results=max_results,
        table_filter=table,
    )


def scenario_storage_summary(analysis_out: Path, token: str = "", max_results: int = 50, table: str | None = None) -> dict[str, Any]:
    return _search_json_artifacts(
        analysis_out, token, kind="scenario-storage-summary",
        files=[analysis_out / "compact" / "scenario_storage_summaries.json", analysis_out / "facts" / "facts_by_type" / "scenario_storage_summary.json"],
        max_results=max_results,
        table_filter=table,
    )


def declared_value_set_summary(analysis_out: Path, token: str = "", max_results: int = 50) -> dict[str, Any]:
    return _search_json_artifacts(
        analysis_out, token, kind="declared-value-set-summary",
        files=[analysis_out / "compact" / "declared_value_set_summaries.json", analysis_out / "facts" / "facts_by_type" / "declared_value_set_summary.json"],
        max_results=max_results,
    )



def jooq_batch_write_summary(analysis_out: Path, token: str = "", max_results: int = 50, table: str | None = None) -> dict[str, Any]:
    return _search_json_artifacts(
        analysis_out, token, kind="jooq-batch-write-summary",
        files=[analysis_out / "compact" / "jooq_batch_write_summaries.json", analysis_out / "facts" / "facts_by_type" / "jooq_batch_write_summary.json"],
        max_results=max_results,
        table_filter=table,
    )


def data_model_lineage_gap(analysis_out: Path, token: str = "", max_results: int = 50) -> dict[str, Any]:
    return _search_json_artifacts(
        analysis_out, token, kind="data-model-lineage-gap",
        files=[analysis_out / "compact" / "data_model_lineage_gaps.json", analysis_out / "facts" / "facts_by_type" / "data_model_lineage_gap.json"],
        max_results=max_results,
    )



# --- Java workspace data-model evidence commands ----------------------------

def _workspace_query_parts(*, token: str = "", attribute: str | None = None, repo_id: str | None = None, storage_target: str | None = None) -> list[str]:
    return [x.lower() for x in [token or "", attribute or "", repo_id or "", storage_target or ""] if x]


def _workspace_item_matches(item: Any, q_parts: list[str]) -> bool:
    if not q_parts:
        return True
    try:
        blob = json.dumps(item, ensure_ascii=False, default=str).lower()
    except Exception:
        blob = str(item).lower()
    return all(q in blob for q in q_parts)


def _filter_workspace_list(data: Any, *, token: str = "", attribute: str | None = None, repo_id: str | None = None, storage_target: str | None = None, max_results: int = 50) -> tuple[list[Any], int, int]:
    rows = data if isinstance(data, list) else []
    q_parts = _workspace_query_parts(token=token, attribute=attribute, repo_id=repo_id, storage_target=storage_target)
    matched = [x for x in rows if _workspace_item_matches(x, q_parts)]
    return matched[:max_results], len(rows), len(matched)


_GENERIC_ATTRIBUTE_NAMES = {
    "id", "key", "code", "name", "type", "value", "date", "time", "status", "state",
    "data", "text", "number", "count", "amount", "sum", "flag", "result", "request",
    "response", "object", "item", "message", "description", "created", "updated",
}


def _workspace_attr_name(item: dict[str, Any]) -> str:
    for key in (
        "normalized_attribute_name", "canonical_attribute", "attribute_name", "source_attribute",
        "target_attribute", "java_field_name", "java_field", "db_column_name", "column_name",
        "source_field", "target_field", "storage_field", "field",
    ):
        value = item.get(key)
        if value:
            return str(value)
    return ""


def _is_generic_attribute_name(name: str) -> bool:
    raw = str(name or "").strip().lower()
    if not raw:
        return False
    normalized = "".join(ch for ch in raw if ch.isalnum() or ch == "_").strip("_")
    return normalized in _GENERIC_ATTRIBUTE_NAMES


def _workspace_refs(item: dict[str, Any]) -> list[str]:
    refs = item.get("source_evidence_refs") or item.get("evidence_refs") or []
    if isinstance(refs, str):
        refs = [refs]
    if not isinstance(refs, list):
        refs = []
    return [str(r) for r in refs if r]


def _workspace_object_classification(item: dict[str, Any], artifact_name: str) -> dict[str, Any]:
    item_type = _workspace_item_type(item, artifact_name)
    classification_status = "not_applicable"
    physical_object_type = None
    if item_type == "physical_table":
        physical_object_type = "confirmed_physical_table"
        classification_status = "confirmed" if _workspace_refs(item) else "confirmed_without_refs"
    elif item_type == "table_attribute":
        physical_object_type = "confirmed_table_attribute"
        classification_status = "confirmed" if _workspace_refs(item) else "confirmed_without_refs"
    elif item_type == "table_relationship":
        relationship_status = str(item.get("relationship_status") or "")
        if relationship_status == "confirmed_relationship":
            physical_object_type = "confirmed_table_relationship"
            classification_status = "confirmed" if _workspace_refs(item) else "confirmed_without_refs"
        elif relationship_status == "candidate_relationship":
            physical_object_type = "candidate_table_relationship"
            classification_status = "candidate"
        else:
            physical_object_type = "unresolved_table_relationship"
            classification_status = "unresolved"
    elif item_type == "key_candidate":
        role = str(item.get("key_role") or "")
        if role in {"primary_key", "foreign_key", "PK", "FK"}:
            physical_object_type = "confirmed_key"
            classification_status = "confirmed" if _workspace_refs(item) else "confirmed_without_refs"
        else:
            physical_object_type = "candidate_key"
            classification_status = "candidate"
    elif item_type in {"source_to_storage_lineage", "attribute_graph_edge", "attribute_rename_chain"}:
        physical_object_type = item_type
        classification_status = "confirmed" if _workspace_evidence_level(item) == "confirmed_by_analyzer" and _workspace_refs(item) else _workspace_evidence_level(item)
    elif item_type in {"data_model_lineage_gap", "attribute_lineage_break"}:
        physical_object_type = item_type
        classification_status = "unresolved" if _workspace_evidence_level(item) == "unresolved" else _workspace_evidence_level(item)
    else:
        physical_object_type = item_type
    return {
        "object_type": item_type,
        "physical_object_type": physical_object_type,
        "classification_status": classification_status,
    }


def _workspace_candidate_quality(item: dict[str, Any]) -> dict[str, Any]:
    attr_name = _workspace_attr_name(item)
    generic = _is_generic_attribute_name(attr_name)
    reasons = item.get("candidate_reasons") or []
    if isinstance(reasons, str):
        reasons = [r.strip() for r in reasons.split(",") if r.strip()]
    if not isinstance(reasons, list):
        reasons = []
    repo_count = len({str(x) for x in (item.get("repo_ids") or []) if x})
    if not repo_count:
        repo_count = len({str(item.get("source_repo_id") or ""), str(item.get("target_repo_id") or "")} - {""})
    source_occurrence = item.get("source_occurrence") if isinstance(item.get("source_occurrence"), dict) else {}
    target_occurrence = item.get("target_occurrence") if isinstance(item.get("target_occurrence"), dict) else {}
    has_storage = bool(item.get("storage_target") or item.get("storage_targets") or source_occurrence.get("storage_target") or target_occurrence.get("storage_target"))
    has_type = "same_field_type" in reasons or bool(item.get("attribute_type") or item.get("type"))
    score = 0
    score += 40 if not generic else -40
    score += min(repo_count, 5) * 5
    score += 15 if has_storage else 0
    score += 10 if has_type else 0
    score += 10 if "same_payload_contract" in reasons else 0
    if generic:
        quality = "generic_attribute_name_noise"
    elif score >= 55:
        quality = "strong_candidate_signal"
    elif score >= 30:
        quality = "medium_candidate_signal"
    else:
        quality = "weak_name_based_candidate"
    return {
        "candidate_quality": quality,
        "selection_score": score,
        "generic_attribute_name": generic,
        "candidate_reasons": reasons or item.get("candidate_reasons"),
    }


def _workspace_selection_key(item: Any) -> tuple[int, str]:
    if not isinstance(item, dict):
        return (0, str(item))
    quality = _workspace_candidate_quality(item)
    return (int(quality.get("selection_score") or 0), str(_workspace_attr_name(item)))


def _filter_workspace_payload(data: Any, *, token: str = "", attribute: str | None = None, repo_id: str | None = None, storage_target: str | None = None, max_results: int = 50) -> Any:
    q_parts = _workspace_query_parts(token=token, attribute=attribute, repo_id=repo_id, storage_target=storage_target)
    if isinstance(data, list):
        return [x for x in data if _workspace_item_matches(x, q_parts)][:max_results]
    if isinstance(data, dict):
        out: dict[str, Any] = {}
        for k, v in data.items():
            if isinstance(v, list):
                out[k] = [x for x in v if _workspace_item_matches(x, q_parts)][:max_results]
            else:
                out[k] = v
        return out
    return data


def _workspace_evidence_level(item: dict[str, Any]) -> str:
    if str(item.get("relationship_status") or "") == "candidate_relationship":
        return "candidate_signal_navigation_only"
    if item.get("candidate_signals"):
        return "candidate_signal_navigation_only"
    maturity = str(item.get("evidence_maturity_level") or "").strip().lower()
    if maturity == "confirmed":
        return "confirmed_by_analyzer"
    if maturity == "not_applicable":
        return "not_applicable"
    if maturity == "unresolved" or item.get("gap_kind") or item.get("data_model_lineage_gap_id") or item.get("workspace_data_model_lineage_gap_id"):
        return "unresolved"
    return "unresolved"


def _workspace_item_type(item: dict[str, Any], artifact_name: str) -> str:
    for key, value in {
        "workspace_table_id": "physical_table",
        "workspace_table_attribute_id": "table_attribute",
        "workspace_attribute_edge_id": "attribute_graph_edge",
        "attribute_origin_candidate_id": "attribute_origin_candidate",
        "attribute_rename_chain_id": "attribute_rename_chain",
        "attribute_journey_id": "attribute_journey",
        "attribute_lineage_break_id": "attribute_lineage_break",
        "workspace_source_to_storage_lineage_id": "source_to_storage_lineage",
        "workspace_data_model_lineage_gap_id": "data_model_lineage_gap",
        "workspace_table_relationship_candidate_id": "table_relationship",
        "workspace_key_candidate_id": "key_candidate",
        "cross_repo_attribute_flow_candidate_id": "cross_repo_attribute_flow_candidate",
    }.items():
        if item.get(key):
            return value
    if artifact_name == "workspace_attribute_graph" and item.get("node_id"):
        return "attribute_graph_node"
    return artifact_name


def _workspace_enrich_item(item: Any, *, artifact_name: str, source_path: Path) -> Any:
    if not isinstance(item, dict):
        return item
    out = dict(item)
    out.setdefault("item_type", _workspace_item_type(out, artifact_name))
    out.setdefault("evidence_level", _workspace_evidence_level(out))
    refs = _workspace_refs(out)
    provenance = {
        "source_artifact": artifact_name,
        "source_file": str(source_path),
        "evidence_refs": refs,
        "provenance_status": "present" if refs else "missing",
    }
    out.setdefault("provenance", provenance)
    out.setdefault("provenance_status", provenance["provenance_status"])
    for k, v in _workspace_object_classification(out, artifact_name).items():
        out.setdefault(k, v)
    if out.get("evidence_level") == "confirmed_by_analyzer" and not refs:
        out.setdefault("evidence_warning", "confirmed item has no concrete evidence_refs in this view; treat provenance as incomplete, not as additional confirmation")
    if artifact_name == "cross_repo_attribute_flow_candidates" or out.get("candidate_signals") or str(out.get("relationship_status") or "") == "candidate_relationship":
        for k, v in _workspace_candidate_quality(out).items():
            out.setdefault(k, v)
    return out


def _workspace_envelope(kind: str, analysis_out: Path, artifact_name: str, source_path: Path, *, token: str, attribute: str | None, repo_id: str | None, table: str | None, items: list[Any], total_count: int, matched_count: int, selection_policy: str | None = None) -> dict[str, Any]:
    enriched = [_workspace_enrich_item(x, artifact_name=artifact_name, source_path=source_path) for x in items]
    omitted = max(0, matched_count - len(enriched))
    if matched_count == 0 and total_count == 0:
        status = "not_materialized"
    elif omitted > 0:
        status = "truncated"
    else:
        status = "full"
    return {
        "kind": kind,
        "analysis_out": str(analysis_out),
        "source_artifact": artifact_name,
        "source_file": str(source_path),
        "filters": {"token": token, "attribute": attribute, "repo_id": repo_id, "table": table},
        "selection_policy": selection_policy or "filter_exact_context_then_keep_source_order; max_results limits materialized items",
        "total_count": total_count,
        "matched_count": matched_count,
        "included_count": len(enriched),
        "omitted_count": omitted,
        "materialization_status": status,
        "items": enriched,
        "hit_count": len(enriched),
    }


def workspace_boundary_field_flow_index(analysis_out: Path, token: str = "", *, repo_id: str | None = None, max_results: int = 100) -> dict[str, Any]:
    """Return compact repository-qualified field-flow entry/exit points attached to boundaries."""
    return _workspace_compact_list_command(
        analysis_out,
        artifact_name="workspace_boundary_field_flow_index",
        kind="workspace-boundary-field-flow-index",
        token=token,
        repo_id=repo_id,
        max_results=max_results,
    )


def workspace_attribute_catalog(analysis_out: Path, token: str = "", *, attribute: str | None = None, repo_id: str | None = None, max_results: int = 50) -> dict[str, Any]:
    path = analysis_out / "portfolio" / "compact" / "workspace_attribute_catalog.json"
    data = read_json(path, []) or []
    items, total_count, matched_count = _filter_workspace_list(data, token=token, attribute=attribute, repo_id=repo_id, max_results=max_results)
    obj = _workspace_envelope("workspace-attribute-catalog", analysis_out, "workspace_attribute_catalog", path, token=token, attribute=attribute, repo_id=repo_id, table=None, items=items, total_count=total_count, matched_count=matched_count)
    write_lazy(analysis_out, "workspace-attribute-catalog", token or attribute or repo_id or "all", obj)
    return obj


def workspace_persistent_model(analysis_out: Path, token: str = "", *, attribute: str | None = None, repo_id: str | None = None, storage_target: str | None = None, max_results: int = 50) -> dict[str, Any]:
    path = analysis_out / "portfolio" / "compact" / "workspace_persistent_model.json"
    data = read_json(path, {}) or {}
    filtered = _filter_workspace_payload(data, token=token, attribute=attribute, repo_id=repo_id, storage_target=storage_target, max_results=max_results)
    obj = {"kind": "workspace-persistent-model", "analysis_out": str(analysis_out), "token": token, "attribute": attribute, "repo_id": repo_id, "storage_target": storage_target, "model": filtered}
    write_lazy(analysis_out, "workspace-persistent-model", token or attribute or repo_id or storage_target or "all", obj)
    return obj


def cross_repo_attribute_flow_candidates(analysis_out: Path, token: str = "", *, attribute: str | None = None, repo_id: str | None = None, max_results: int = 50) -> dict[str, Any]:
    return _workspace_compact_list_command(analysis_out, artifact_name="cross_repo_attribute_flow_candidates", kind="cross-repo-attribute-flow-candidates", token=token, attribute=attribute, repo_id=repo_id, max_results=max_results)


def _workspace_compact_list_command(
    analysis_out: Path,
    *,
    artifact_name: str,
    kind: str,
    token: str = "",
    attribute: str | None = None,
    repo_id: str | None = None,
    table: str | None = None,
    max_results: int = 50,
) -> dict[str, Any]:
    path = analysis_out / "portfolio" / "compact" / f"{artifact_name}.json"
    data = read_json(path, []) or []
    if isinstance(data, dict) and "items" in data:
        data = data.get("items") or []
    if artifact_name == "cross_repo_attribute_flow_candidates" and isinstance(data, list):
        q_parts = _workspace_query_parts(token=token, attribute=attribute, repo_id=repo_id, storage_target=table)
        matched = [x for x in data if _workspace_item_matches(x, q_parts)]
        matched = sorted(matched, key=_workspace_selection_key, reverse=True)
        items, total_count, matched_count = matched[:max_results], len(data), len(matched)
        selection_policy = "filter_context_then_rank_non_generic_storage_or_type_supported_candidates_first; max_results limits materialized items"
    else:
        items, total_count, matched_count = _filter_workspace_list(data, token=token, attribute=attribute, repo_id=repo_id, storage_target=table, max_results=max_results)
        selection_policy = None
    obj = _workspace_envelope(kind, analysis_out, artifact_name, path, token=token, attribute=attribute, repo_id=repo_id, table=table, items=items, total_count=total_count, matched_count=matched_count, selection_policy=selection_policy)
    write_lazy(analysis_out, kind, token or attribute or repo_id or table or "all", obj)
    return obj


def _workspace_compact_model_command(
    analysis_out: Path,
    *,
    artifact_name: str,
    kind: str,
    token: str = "",
    attribute: str | None = None,
    repo_id: str | None = None,
    table: str | None = None,
    max_results: int = 50,
) -> dict[str, Any]:
    path = analysis_out / "portfolio" / "compact" / f"{artifact_name}.json"
    data = read_json(path, {}) or {}
    filtered = _filter_workspace_payload(data, token=token, attribute=attribute, repo_id=repo_id, storage_target=table, max_results=max_results)
    section_counts: dict[str, dict[str, Any]] = {}
    if isinstance(data, dict) and isinstance(filtered, dict):
        for key, raw_value in data.items():
            if isinstance(raw_value, list):
                filtered_value = filtered.get(key) if isinstance(filtered, dict) else []
                if isinstance(filtered_value, list):
                    filtered[key] = [_workspace_enrich_item(x, artifact_name=f"{artifact_name}.{key}", source_path=path) for x in filtered_value]
                    section_counts[key] = {
                        "total_count": len(raw_value),
                        "included_count": len(filtered[key]),
                        "omitted_count": max(0, len(raw_value) - len(filtered[key])),
                        "materialization_status": "truncated" if len(raw_value) > len(filtered[key]) else "full",
                    }
    obj = {
        "kind": kind,
        "analysis_out": str(analysis_out),
        "source_artifact": artifact_name,
        "source_file": str(path),
        "filters": {"token": token, "attribute": attribute, "repo_id": repo_id, "table": table},
        "section_counts": section_counts,
        "model": filtered,
    }
    write_lazy(analysis_out, kind, token or attribute or repo_id or table or "all", obj)
    return obj


def workspace_table_catalog(analysis_out: Path, token: str = "", *, repo_id: str | None = None, table: str | None = None, max_results: int = 50) -> dict[str, Any]:
    return _workspace_compact_list_command(analysis_out, artifact_name="workspace_table_catalog", kind="workspace-table-catalog", token=token, repo_id=repo_id, table=table, max_results=max_results)


def workspace_table_attribute_catalog(analysis_out: Path, token: str = "", *, attribute: str | None = None, repo_id: str | None = None, table: str | None = None, max_results: int = 50) -> dict[str, Any]:
    return _workspace_compact_list_command(analysis_out, artifact_name="workspace_table_attribute_catalog", kind="workspace-table-attribute-catalog", token=token, attribute=attribute, repo_id=repo_id, table=table, max_results=max_results)


def workspace_attribute_graph(analysis_out: Path, token: str = "", *, attribute: str | None = None, repo_id: str | None = None, table: str | None = None, max_results: int = 50) -> dict[str, Any]:
    return _workspace_compact_model_command(analysis_out, artifact_name="workspace_attribute_graph", kind="workspace-attribute-graph", token=token, attribute=attribute, repo_id=repo_id, table=table, max_results=max_results)


def attribute_origin_candidates(analysis_out: Path, token: str = "", *, attribute: str | None = None, repo_id: str | None = None, max_results: int = 50) -> dict[str, Any]:
    return _workspace_compact_list_command(analysis_out, artifact_name="attribute_origin_candidates", kind="attribute-origin-candidates", token=token, attribute=attribute, repo_id=repo_id, max_results=max_results)


def attribute_rename_chains(analysis_out: Path, token: str = "", *, attribute: str | None = None, repo_id: str | None = None, max_results: int = 50) -> dict[str, Any]:
    return _workspace_compact_list_command(analysis_out, artifact_name="attribute_rename_chains", kind="attribute-rename-chains", token=token, attribute=attribute, repo_id=repo_id, max_results=max_results)


def attribute_journey_by_fp(analysis_out: Path, token: str = "", *, attribute: str | None = None, repo_id: str | None = None, max_results: int = 50) -> dict[str, Any]:
    return _workspace_compact_list_command(analysis_out, artifact_name="attribute_journey_by_fp", kind="attribute-journey-by-fp", token=token, attribute=attribute, repo_id=repo_id, max_results=max_results)


def attribute_lineage_breaks(analysis_out: Path, token: str = "", *, attribute: str | None = None, repo_id: str | None = None, max_results: int = 50) -> dict[str, Any]:
    return _workspace_compact_list_command(analysis_out, artifact_name="attribute_lineage_breaks", kind="attribute-lineage-breaks", token=token, attribute=attribute, repo_id=repo_id, max_results=max_results)


def workspace_source_to_storage_lineage(analysis_out: Path, token: str = "", *, attribute: str | None = None, repo_id: str | None = None, table: str | None = None, max_results: int = 50) -> dict[str, Any]:
    return _workspace_compact_list_command(analysis_out, artifact_name="workspace_source_to_storage_lineage", kind="workspace-source-to-storage-lineage", token=token, attribute=attribute, repo_id=repo_id, table=table, max_results=max_results)


def workspace_data_model_lineage_gaps(analysis_out: Path, token: str = "", *, attribute: str | None = None, repo_id: str | None = None, table: str | None = None, max_results: int = 50) -> dict[str, Any]:
    return _workspace_compact_list_command(analysis_out, artifact_name="workspace_data_model_lineage_gaps", kind="workspace-data-model-lineage-gaps", token=token, attribute=attribute, repo_id=repo_id, table=table, max_results=max_results)


def workspace_er_model_candidates(analysis_out: Path, token: str = "", *, repo_id: str | None = None, table: str | None = None, max_results: int = 50) -> dict[str, Any]:
    return _workspace_compact_model_command(analysis_out, artifact_name="workspace_er_model_candidates", kind="workspace-er-model-candidates", token=token, repo_id=repo_id, table=table, max_results=max_results)


def workspace_table_relationship_candidates(analysis_out: Path, token: str = "", *, repo_id: str | None = None, table: str | None = None, max_results: int = 50) -> dict[str, Any]:
    return _workspace_compact_list_command(analysis_out, artifact_name="workspace_table_relationship_candidates", kind="workspace-table-relationship-candidates", token=token, repo_id=repo_id, table=table, max_results=max_results)


def workspace_key_candidates(analysis_out: Path, token: str = "", *, repo_id: str | None = None, table: str | None = None, max_results: int = 50) -> dict[str, Any]:
    return _workspace_compact_list_command(analysis_out, artifact_name="workspace_key_candidates", kind="workspace-key-candidates", token=token, repo_id=repo_id, table=table, max_results=max_results)


def _section_summary(section: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": section.get("kind"),
        "source_artifact": section.get("source_artifact"),
        "total_count": section.get("total_count"),
        "matched_count": section.get("matched_count"),
        "included_count": section.get("included_count"),
        "omitted_count": section.get("omitted_count"),
        "materialization_status": section.get("materialization_status"),
        "selection_policy": section.get("selection_policy"),
    }


def workspace_table_detail(analysis_out: Path, table: str, *, repo_id: str | None = None, max_results: int = 1000) -> dict[str, Any]:
    """Focused AS data-model view for one table/storage target.

    This command intentionally combines existing compact evidence views without generating
    a separate agent pack. It gives LLM enough table-scoped material to place into
    final_response.json.
    """
    if not table:
        raise ValueError("workspace-table-detail requires --table")
    sections = {
        "table_catalog": workspace_table_catalog(analysis_out, table=table, repo_id=repo_id, max_results=max_results),
        "table_attributes": workspace_table_attribute_catalog(analysis_out, table=table, repo_id=repo_id, max_results=max_results),
        "relationships": workspace_table_relationship_candidates(analysis_out, table=table, repo_id=repo_id, max_results=max_results),
        "key_candidates": workspace_key_candidates(analysis_out, table=table, repo_id=repo_id, max_results=max_results),
        "source_to_storage_lineage": workspace_source_to_storage_lineage(analysis_out, table=table, repo_id=repo_id, max_results=max_results),
        "data_model_lineage_gaps": workspace_data_model_lineage_gaps(analysis_out, table=table, repo_id=repo_id, max_results=max_results),
    }
    return {
        "kind": "workspace-table-detail",
        "analysis_out": str(analysis_out),
        "table": table,
        "repo_id": repo_id,
        "selection_policy": "focused_detail_by_table; includes table, attributes, relationships, keys, source-to-storage chains and profile-specific gaps",
        "section_summaries": {k: _section_summary(v) for k, v in sections.items()},
        "sections": sections,
    }


def workspace_attribute_detail(analysis_out: Path, attribute: str, *, repo_id: str | None = None, max_results: int = 1000) -> dict[str, Any]:
    """Focused AS data-model view for one normalized or technical attribute name."""
    if not attribute:
        raise ValueError("workspace-attribute-detail requires --attribute")
    sections = {
        "attribute_catalog": workspace_attribute_catalog(analysis_out, attribute=attribute, repo_id=repo_id, max_results=max_results),
        "table_attributes": workspace_table_attribute_catalog(analysis_out, attribute=attribute, repo_id=repo_id, max_results=max_results),
        "attribute_graph": workspace_attribute_graph(analysis_out, attribute=attribute, repo_id=repo_id, max_results=max_results),
        "origin_candidates": attribute_origin_candidates(analysis_out, attribute=attribute, repo_id=repo_id, max_results=max_results),
        "rename_chains": attribute_rename_chains(analysis_out, attribute=attribute, repo_id=repo_id, max_results=max_results),
        "lineage_breaks": attribute_lineage_breaks(analysis_out, attribute=attribute, repo_id=repo_id, max_results=max_results),
        "journey_by_fp": attribute_journey_by_fp(analysis_out, attribute=attribute, repo_id=repo_id, max_results=max_results),
        "source_to_storage_lineage": workspace_source_to_storage_lineage(analysis_out, attribute=attribute, repo_id=repo_id, max_results=max_results),
        "cross_repo_flow_candidates": cross_repo_attribute_flow_candidates(analysis_out, attribute=attribute, repo_id=repo_id, max_results=max_results),
        "data_model_lineage_gaps": workspace_data_model_lineage_gaps(analysis_out, attribute=attribute, repo_id=repo_id, max_results=max_results),
    }
    return {
        "kind": "workspace-attribute-detail",
        "analysis_out": str(analysis_out),
        "attribute": attribute,
        "normalized_attribute_name": normalize_name(attribute),
        "repo_id": repo_id,
        "selection_policy": "focused_detail_by_attribute; includes occurrences, graph edges, origins, renames, breaks, journeys, storage destinations, cross-repo candidates and profile-specific gaps",
        "section_summaries": {k: _section_summary(v) for k, v in sections.items()},
        "sections": sections,
    }


def workspace_er_view(analysis_out: Path, token: str = "", *, repo_id: str | None = None, table: str | None = None, max_results: int = 5000) -> dict[str, Any]:
    """ER-focused view split by relationship status for final_response materialization."""
    rel_path = analysis_out / "portfolio" / "compact" / "workspace_table_relationship_candidates.json"
    table_path = analysis_out / "portfolio" / "compact" / "workspace_table_catalog.json"
    key_path = analysis_out / "portfolio" / "compact" / "workspace_key_candidates.json"
    rels_raw = read_json(rel_path, []) or []
    tables_raw = read_json(table_path, []) or []
    keys_raw = read_json(key_path, []) or []
    q_parts = _workspace_query_parts(token=token, repo_id=repo_id, storage_target=table)
    rels = [r for r in rels_raw if _workspace_item_matches(r, q_parts)]
    tables = [t for t in tables_raw if _workspace_item_matches(t, q_parts)] if q_parts else list(tables_raw)
    keys = [k for k in keys_raw if _workspace_item_matches(k, q_parts)]
    rels_enriched = [_workspace_enrich_item(r, artifact_name="workspace_table_relationship_candidates", source_path=rel_path) for r in rels]
    confirmed = [r for r in rels_enriched if r.get("relationship_status") == "confirmed_relationship"]
    candidates = [r for r in rels_enriched if r.get("relationship_status") == "candidate_relationship" and not r.get("generic_attribute_name")]
    weak = [r for r in rels_enriched if r.get("relationship_status") == "candidate_relationship" and r.get("generic_attribute_name")]
    involved_tables = {str(x.get("source_table") or "") for x in rels_enriched} | {str(x.get("target_table") or "") for x in rels_enriched}
    if table:
        involved_tables.add(str(table))
    if involved_tables:
        tables = [t for t in tables_raw if str(t.get("table_name") or "") in involved_tables or _workspace_item_matches(t, q_parts)]
    table_items = [_workspace_enrich_item(t, artifact_name="workspace_table_catalog", source_path=table_path) for t in tables[:max_results]]
    key_items = [_workspace_enrich_item(k, artifact_name="workspace_key_candidates", source_path=key_path) for k in keys[:max_results]]
    included_rels = (confirmed + candidates + weak)[:max_results]
    return {
        "kind": "workspace-er-view",
        "analysis_out": str(analysis_out),
        "filters": {"token": token, "repo_id": repo_id, "table": table},
        "selection_policy": "ER-focused view: confirmed relationships first, then candidate relationships, then weak generic/name-based signals; max_results limits relationships",
        "total_count": len(rels_raw),
        "matched_count": len(rels),
        "included_count": len(included_rels),
        "omitted_count": max(0, len(rels) - len(included_rels)),
        "materialization_status": "truncated" if len(rels) > len(included_rels) else "full" if rels_raw else "not_materialized",
        "counts_by_status": {
            "confirmed_relationships": len(confirmed),
            "candidate_relationships": len(candidates),
            "weak_name_based_relationships": len(weak),
        },
        "nodes": {"tables": table_items, "key_candidates": key_items},
        "relationships": {
            "confirmed": confirmed[:max_results],
            "candidate": candidates[:max_results],
            "weak_name_based": weak[:max_results],
        },
    }

def trace(analysis_out: Path, token: str = "", max_results: int = 50, trace_type: str | None = None) -> dict[str, Any]:
    return _search_json_artifacts(
        analysis_out, token, kind="trace",
        files=[analysis_out / "compact" / "traces.json", analysis_out / "facts" / "facts_by_type" / "data_trace.json"],
        max_results=max_results,
        type_filter=trace_type,
    )



def declared_value_set(analysis_out: Path, token: str = "", max_results: int = 50) -> dict[str, Any]:
    return _search_json_artifacts(
        analysis_out, token, kind="declared-value-set",
        files=[
            analysis_out / "compact" / "reference_data_fact_base" / "declared_value_sets.jsonl",
            analysis_out / "compact" / "reference_data_fact_base" / "declared_values.jsonl",
            analysis_out / "compact" / "declared_value_sets.json",
            analysis_out / "compact" / "declared_value_set_summaries.json",
            analysis_out / "facts" / "facts_by_type" / "declared_value_set.json",
            analysis_out / "facts" / "facts_by_type" / "declared_value_set_summary.json",
            analysis_out / "facts" / "facts_by_type" / "declared_value.json",
        ],
        max_results=max_results,
    )


def literal_data_write(analysis_out: Path, token: str = "", max_results: int = 50) -> dict[str, Any]:
    return _search_json_artifacts(
        analysis_out, token, kind="literal-data-write",
        files=[
            analysis_out / "compact" / "reference_data_fact_base" / "literal_data_writes.jsonl",
            analysis_out / "compact" / "literal_data_writes.json",
            analysis_out / "facts" / "facts_by_type" / "literal_data_write.json",
        ],
        max_results=max_results,
    )


def traces_for_operation(analysis_out: Path, operation_id: str, max_results: int = 50) -> dict[str, Any]:
    return trace(analysis_out, operation_id, max_results=max_results)


def traces_for_payload(analysis_out: Path, token: str, max_results: int = 50) -> dict[str, Any]:
    return trace(analysis_out, token, max_results=max_results)

# --- Shared evidence command helpers -------------------------------------------------

def _matches_token(obj: Any, token: str) -> bool:
    q = token.lower()
    try:
        return q in json.dumps(obj, ensure_ascii=False, default=str).lower()
    except Exception:
        return q in str(obj).lower()


def _limit(items: list[dict[str, Any]], max_results: int) -> list[dict[str, Any]]:
    return items[:max(0, int(max_results))]


# ---------------------------------------------------------------------------
# LLM run artifact evidence views
# ---------------------------------------------------------------------------

def _read_jsonl(path: Path, max_results: int = 1000) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    items: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
            if isinstance(item, dict):
                items.append(item)
        except Exception:
            items.append({"raw": line})
        if len(items) >= max_results:
            break
    return items


def _llm_out_path(llm_out: Path) -> Path:
    p = Path(llm_out)
    if not p.exists():
        raise FileNotFoundError(f"llm-out path does not exist: {p}")
    if not p.is_dir():
        raise NotADirectoryError(f"llm-out path is not a directory: {p}")
    return p


def _rel_or_str(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root)).replace("\\", "/")
    except Exception:
        return str(path)


def _llm_iteration_dirs(llm_out: Path) -> list[Path]:
    root = _llm_out_path(llm_out)
    idir = root / "iterations"
    if not idir.exists():
        return []
    return sorted([p for p in idir.glob("iteration_*") if p.is_dir()])


def llm_run_summary(llm_out: Path) -> dict[str, Any]:
    root = _llm_out_path(llm_out)
    summary = read_json(root / "pipeline_summary.json", {}) or {}
    state = read_json(root / "state.json", {}) or {}
    run = read_json(root / "run.json", {}) or {}
    final_exists = (root / "final_response.json").exists()
    errors = _read_jsonl(root / "errors.jsonl", max_results=10000)
    iterations = _llm_iteration_dirs(root)
    return {
        "kind": "llm-run-summary",
        "llm_out": str(root),
        "final_response_exists": final_exists,
        "iteration_count": len(iterations),
        "error_count": len(errors),
        "summary": summary,
        "state": state,
        "run": run,
        "artifacts": {
            "final_response": "final_response.json" if final_exists else None,
            "pipeline_summary": "pipeline_summary.json" if (root / "pipeline_summary.json").exists() else None,
            "state": "state.json" if (root / "state.json").exists() else None,
            "errors": "errors.jsonl" if (root / "errors.jsonl").exists() else None,
            "enabled_evidence_tools": "enabled_evidence_tools.json" if (root / "enabled_evidence_tools.json").exists() else None,
            "agent_runtime_context": "agent_runtime_context.json" if (root / "agent_runtime_context.json").exists() else None,
            "agent_system_prompt": "agent_system_prompt.md" if (root / "agent_system_prompt.md").exists() else None,
            "agent_usage_policy": "agent_usage_policy.md" if (root / "agent_usage_policy.md").exists() else None,
            "iterations_dir": "iterations" if (root / "iterations").exists() else None,
        },
    }


def llm_final_response(llm_out: Path) -> dict[str, Any]:
    root = _llm_out_path(llm_out)
    path = root / "final_response.json"
    data = read_json(path, None)
    return {
        "kind": "llm-final-response",
        "llm_out": str(root),
        "path": str(path),
        "exists": path.exists(),
        "final_response": data if data is not None else {},
    }


def llm_errors(llm_out: Path, token: str = "", max_results: int = 1000) -> dict[str, Any]:
    root = _llm_out_path(llm_out)
    token = str(token or "")
    errors = [x for x in _read_jsonl(root / "errors.jsonl", max_results=100000) if _item_matches_blob(x, token)]
    selected = errors[:max_results]
    return {
        "kind": "llm-errors",
        "llm_out": str(root),
        "token": token,
        "total_count": len(errors),
        "included_count": len(selected),
        "omitted_count": max(0, len(errors) - len(selected)),
        "items": selected,
    }


def llm_iterations(llm_out: Path, token: str = "", max_results: int = 1000) -> dict[str, Any]:
    root = _llm_out_path(llm_out)
    token = str(token or "")
    items: list[dict[str, Any]] = []
    for idir in _llm_iteration_dirs(root):
        parsed = read_json(idir / "parsed_response.json", {}) or {}
        parse_meta = read_json(idir / "response_parse_meta.json", {}) or {}
        evidence_results = read_json(idir / "evidence_results.json", {}) or {}
        agent_requests = read_json(idir / "agent_requests.json", {}) or {}
        request = read_json(idir / "request.json", {}) or {}
        item = {
            "iteration": idir.name,
            "dir": _rel_or_str(idir, root),
            "llm_status": parsed.get("status") if isinstance(parsed, dict) else None,
            "summary": parsed.get("summary") if isinstance(parsed, dict) else None,
            "agent_request_count": len((agent_requests or {}).get("agent_requests") or []) if isinstance(agent_requests, dict) else None,
            "evidence_result_count": len((evidence_results or {}).get("results") or []) if isinstance(evidence_results, dict) else None,
            "json_parse_mode": parse_meta.get("mode") if isinstance(parse_meta, dict) else None,
            "prompt": _rel_or_str(idir / "prompt.md", root) if (idir / "prompt.md").exists() else None,
            "request": _rel_or_str(idir / "request.json", root) if (idir / "request.json").exists() else None,
            "response_raw": _rel_or_str(idir / "response_raw.json", root) if (idir / "response_raw.json").exists() else None,
            "parsed_response": _rel_or_str(idir / "parsed_response.json", root) if (idir / "parsed_response.json").exists() else None,
            "evidence_results": _rel_or_str(idir / "evidence_results.json", root) if (idir / "evidence_results.json").exists() else None,
            "enabled_tool_count": ((request.get("meta") or {}).get("enabled_evidence_tools") or {}).get("command_count") if isinstance(request, dict) else None,
        }
        if _item_matches_blob(item, token):
            items.append(item)
    selected = items[:max_results]
    return {"kind": "llm-iterations", "llm_out": str(root), "token": token, "total_count": len(items), "included_count": len(selected), "omitted_count": max(0, len(items)-len(selected)), "items": selected}


def llm_evidence_results(llm_out: Path, token: str = "", max_results: int = 1000) -> dict[str, Any]:
    root = _llm_out_path(llm_out)
    token = str(token or "")
    hits: list[dict[str, Any]] = []
    for idir in _llm_iteration_dirs(root):
        data = read_json(idir / "evidence_results.json", {}) or {}
        for idx, item in enumerate((data.get("results") or []) if isinstance(data, dict) else [], 1):
            row = {"iteration": idir.name, "result_index": idx, **(item if isinstance(item, dict) else {"value": item})}
            if _item_matches_blob(row, token):
                hits.append(row)
    selected = hits[:max_results]
    return {"kind": "llm-evidence-results", "llm_out": str(root), "token": token, "total_count": len(hits), "included_count": len(selected), "omitted_count": max(0, len(hits)-len(selected)), "items": selected}


def llm_agent_requests(llm_out: Path, token: str = "", max_results: int = 1000) -> dict[str, Any]:
    root = _llm_out_path(llm_out)
    token = str(token or "")
    hits: list[dict[str, Any]] = []
    for idir in _llm_iteration_dirs(root):
        data = read_json(idir / "agent_requests.json", {}) or {}
        for idx, item in enumerate((data.get("agent_requests") or []) if isinstance(data, dict) else [], 1):
            row = {"iteration": idir.name, "request_index": idx, **(item if isinstance(item, dict) else {"value": item})}
            if _item_matches_blob(row, token):
                hits.append(row)
    selected = hits[:max_results]
    return {"kind": "llm-agent-requests", "llm_out": str(root), "token": token, "total_count": len(hits), "included_count": len(selected), "omitted_count": max(0, len(hits)-len(selected)), "items": selected}


def _collect_gap_like(node: Any, path: str = "") -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if isinstance(node, dict):
        for key, value in node.items():
            next_path = f"{path}.{key}" if path else str(key)
            key_l = str(key).lower()
            if key_l in {"gaps", "missing_evidence", "omissions", "usage_constraints"} and isinstance(value, list):
                for idx, item in enumerate(value, 1):
                    if isinstance(item, dict):
                        out.append({"path": next_path, "index": idx, **item})
                    else:
                        out.append({"path": next_path, "index": idx, "description": str(item)})
            out.extend(_collect_gap_like(value, next_path))
    elif isinstance(node, list):
        for idx, item in enumerate(node, 1):
            out.extend(_collect_gap_like(item, f"{path}[{idx}]"))
    return out


def llm_gaps(llm_out: Path, token: str = "", max_results: int = 1000) -> dict[str, Any]:
    root = _llm_out_path(llm_out)
    token = str(token or "")
    final_response = read_json(root / "final_response.json", {}) or {}
    gaps = [x for x in _collect_gap_like(final_response) if _item_matches_blob(x, token)]
    selected = gaps[:max_results]
    return {"kind": "llm-gaps", "llm_out": str(root), "token": token, "total_count": len(gaps), "included_count": len(selected), "omitted_count": max(0, len(gaps)-len(selected)), "items": selected}


def llm_truncation_summary(llm_out: Path, token: str = "", max_results: int = 1000) -> dict[str, Any]:
    root = _llm_out_path(llm_out)
    token = str(token or "")
    findings: list[dict[str, Any]] = []
    for err in _read_jsonl(root / "errors.jsonl", max_results=100000):
        blob = json.dumps(err, ensure_ascii=False, default=str).lower()
        if "trunc" in blob or "length" in blob or "json_fence" in blob:
            findings.append({"source": "errors.jsonl", **err})
    final_response = read_json(root / "final_response.json", {}) or {}
    def walk(node: Any, path: str = "") -> None:
        if isinstance(node, dict):
            markers = {k: v for k, v in node.items() if str(k).lower() in {"truncated", "columns_omitted_count", "omitted_count", "materialization_status"}}
            if markers and any(str(v).lower() in {"true", "truncated", "compact_subset"} or (isinstance(v, int) and v > 0) for v in markers.values()):
                findings.append({"source": "final_response.json", "path": path, "markers": markers})
            for k, v in node.items():
                walk(v, f"{path}.{k}" if path else str(k))
        elif isinstance(node, list):
            for i, v in enumerate(node, 1):
                walk(v, f"{path}[{i}]")
    walk(final_response)
    findings = [x for x in findings if _item_matches_blob(x, token)]
    selected = findings[:max_results]
    return {"kind": "llm-truncation-summary", "llm_out": str(root), "token": token, "total_count": len(findings), "included_count": len(selected), "omitted_count": max(0, len(findings)-len(selected)), "items": selected}


def agent_runtime_context(analysis_out: Path | None = None, llm_out: Path | None = None) -> dict[str, Any]:
    root = _llm_out_path(llm_out) if llm_out is not None else None
    enabled = read_json(root / "enabled_evidence_tools.json", {}) if root else {}
    summary = read_json(root / "pipeline_summary.json", {}) if root else {}
    if analysis_out is None and isinstance(summary, dict) and summary.get("analysis_output"):
        analysis_out = Path(str(summary.get("analysis_output")))
    return {
        "kind": "agent-runtime-context",
        "format": "agent_runtime_context",
        "format_version": "1.0",
        "knowledge_access_mode": "runtime_evidence_tools",
        "final_response_role": "semantic_summary_and_evidence_tool_navigation",
        "analysis_output": str(analysis_out) if analysis_out else None,
        "llm_output": str(root) if root else None,
        "final_response": str(root / "final_response.json") if root and (root / "final_response.json").exists() else None,
        "enabled_evidence_tools": str(root / "enabled_evidence_tools.json") if root and (root / "enabled_evidence_tools.json").exists() else None,
        "agent_system_prompt": str(root / "agent_system_prompt.md") if root and (root / "agent_system_prompt.md").exists() else None,
        "agent_usage_policy": str(root / "agent_usage_policy.md") if root and (root / "agent_usage_policy.md").exists() else None,
        "catalog": {
            "source": "enabled_evidence_tools.json" if enabled else "packaged evidence_tool_catalog.json",
            "command_count": enabled.get("command_count") if isinstance(enabled, dict) else None,
            "enabled_command_ids": enabled.get("enabled_command_ids") if isinstance(enabled, dict) else [],
        },
        "recommended_entrypoint_command_ids": {
            "static_db_schema": ["db_schema_overview", "db_table_catalog", "db_table_detail", "db_column_catalog", "db_relationship_catalog", "db_index_catalog"],
            "static_lineage": ["source_to_storage_lineage", "attribute_mapping", "attribute_derivation", "interface", "operation", "source_inspect"],
            "llm_run": ["llm_run_summary", "llm_final_response", "llm_errors", "llm_evidence_results", "llm_agent_requests", "llm_gaps", "llm_truncation_summary"],
        },
        "usage_rules": [
            "Read final_response.json as semantic summary and navigation, not as a full copy of all evidence.",
            "Use enabled_evidence_tools.json as the source of evidence tool syntax; do not invent commands or options.",
            "Use exact evidence tool detail views when compact final_response sections are truncated or incomplete.",
            "Prefer static analyzer evidence detail over LLM summary when answering factual questions about code or schema.",
        ],
    }

def _git_change_dir(analysis_out: Path) -> Path:
    if (analysis_out / "git-change-evidence").exists():
        return analysis_out / "git-change-evidence"
    if analysis_out.name == "git-change-evidence":
        return analysis_out
    return analysis_out


def _git_change_data(analysis_out: Path, name: str, default: Any) -> Any:
    return read_json(_git_change_dir(analysis_out) / f"{name}.json", default)


def _git_change_list(analysis_out: Path, name: str, token: str = "", max_results: int = 10000) -> tuple[list[dict[str, Any]], int]:
    data = _git_change_data(analysis_out, name, [])
    items = data if isinstance(data, list) else []
    filtered = [x for x in items if isinstance(x, dict) and _item_matches_blob(x, token)]
    return filtered[:max_results], len(filtered)


def git_change_summary(analysis_out: Path, token: str = "", max_results: int = 10000) -> dict[str, Any]:
    root = _git_change_dir(analysis_out)
    meta = _git_change_data(analysis_out, "git_change_metadata", {}) or {}
    diff = _git_change_data(analysis_out, "diff_summary", {}) or {}
    complexity = _git_change_data(analysis_out, "complexity_metrics", {}) or {}
    risks = _git_change_data(analysis_out, "risk_signals", {}) or {}
    impact = _git_change_data(analysis_out, "data_impact_summary", {}) or {}
    test_doc = _git_change_data(analysis_out, "test_doc_delta", {}) or {}
    change_metadata = meta.get("change_metadata") if isinstance(meta, dict) else None
    if not isinstance(change_metadata, dict):
        change_metadata = {}
    obj = {
        "kind": "git-change-summary",
        "analysis_out": str(analysis_out),
        "git_change_evidence": str(root),
        "token": token,
        "metadata": meta,
        "change_metadata": change_metadata,
        "diff_summary": diff,
        "complexity_metrics": complexity,
        "risk_signals": risks,
        "data_impact_summary": impact,
        "test_doc_summary": {k: v for k, v in test_doc.items() if not str(k).endswith("files")},
        "policy": "Assesses code change complexity/risk/data impact only; author/committer metadata is traceability-only and must not be used for personal evaluation.",
    }
    write_lazy(root, "git-change-summary", token or "all", obj)
    return obj


def git_change_metadata(analysis_out: Path) -> dict[str, Any]:
    root = _git_change_dir(analysis_out)
    meta = _git_change_data(analysis_out, "git_change_metadata", {}) or {}
    change_metadata = meta.get("change_metadata") if isinstance(meta, dict) else None
    if not isinstance(change_metadata, dict):
        change_metadata = {
            "repo_id": meta.get("repo_id") if isinstance(meta, dict) else None,
            "change_id": None,
            "change_type": "unknown",
            "source_branch": None,
            "target_branch": None,
            "commit_range": {
                "before": (meta.get("range") or {}).get("base_commit") if isinstance(meta, dict) else None,
                "after": (meta.get("range") or {}).get("target_commit") if isinstance(meta, dict) else None,
            },
            "commit_count": 0,
            "authors": [],
            "committers": [],
            "reviewers": [],
            "metadata_sources": [],
            "metadata_limitations": ["Structured change_metadata is not available in this workspace."],
            "authoring_note": "Author/committer metadata is recorded only for traceability and is not used for scoring or personal evaluation.",
        }
    obj = {
        "kind": "git-change-metadata",
        "analysis_out": str(analysis_out),
        "git_change_evidence": str(root),
        "change_metadata": change_metadata,
        "snapshot_analyzer": meta.get("snapshot_analyzer") if isinstance(meta, dict) else None,
        "analysis_profile": meta.get("analysis_profile") if isinstance(meta, dict) else None,
        "policy": "Neutral traceability metadata only; do not use for engineer scoring, KPI, productivity or personal evaluation.",
    }
    write_lazy(root, "git-change-metadata", "all", obj)
    return obj


def git_change_file_catalog(analysis_out: Path, token: str = "", max_results: int = 10000) -> dict[str, Any]:
    items, matched = _git_change_list(analysis_out, "changed_file_catalog", token, max_results)
    obj = {"kind": "git-change-file-catalog", "analysis_out": str(analysis_out), "token": token, "matched_count": matched, "included_count": len(items), "items": items}
    write_lazy(_git_change_dir(analysis_out), "git-change-file-catalog", token or "all", obj)
    return obj


def git_change_file_detail(analysis_out: Path, file: str, max_results: int = 10000) -> dict[str, Any]:
    token = file or ""
    files, file_count = _git_change_list(analysis_out, "changed_file_catalog", token, max_results)
    hunks, hunk_count = _git_change_list(analysis_out, "changed_hunk_catalog", token, max_results)
    obj = {"kind": "git-change-file-detail", "analysis_out": str(analysis_out), "file": file, "files": files, "hunks": hunks, "hit_count": file_count + hunk_count}
    write_lazy(_git_change_dir(analysis_out), "git-change-file-detail", file or "all", obj)
    return obj


def git_change_lineage_delta(analysis_out: Path, token: str = "", max_results: int = 10000) -> dict[str, Any]:
    items, matched = _git_change_list(analysis_out, "lineage_delta", token, max_results)
    obj = {"kind": "git-change-lineage-delta", "analysis_out": str(analysis_out), "token": token, "matched_count": matched, "included_count": len(items), "items": items}
    write_lazy(_git_change_dir(analysis_out), "git-change-lineage-delta", token or "all", obj)
    return obj


def git_change_transformation_delta(analysis_out: Path, token: str = "", max_results: int = 10000) -> dict[str, Any]:
    items, matched = _git_change_list(analysis_out, "transformation_delta", token, max_results)
    obj = {"kind": "git-change-transformation-delta", "analysis_out": str(analysis_out), "token": token, "matched_count": matched, "included_count": len(items), "items": items}
    write_lazy(_git_change_dir(analysis_out), "git-change-transformation-delta", token or "all", obj)
    return obj


def git_change_data_impact(analysis_out: Path, token: str = "", max_results: int = 10000) -> dict[str, Any]:
    impact = _git_change_data(analysis_out, "data_impact_summary", {}) or {}
    table_delta, _ = _git_change_list(analysis_out, "table_delta", token, max_results)
    column_delta, _ = _git_change_list(analysis_out, "column_delta", token, max_results)
    relationship_delta, _ = _git_change_list(analysis_out, "relationship_delta", token, max_results)
    lineage_delta, _ = _git_change_list(analysis_out, "lineage_delta", token, max_results)
    flow_delta, _ = _git_change_list(analysis_out, "flow_delta", token, max_results)
    event_delta, _ = _git_change_list(analysis_out, "event_source_delta", token, max_results)
    obj = {
        "kind": "git-change-data-impact",
        "analysis_out": str(analysis_out),
        "token": token,
        "summary": impact,
        "table_delta": table_delta,
        "column_delta": column_delta,
        "relationship_delta": relationship_delta,
        "lineage_delta": lineage_delta,
        "flow_delta": flow_delta,
        "event_source_delta": event_delta,
    }
    write_lazy(_git_change_dir(analysis_out), "git-change-data-impact", token or "all", obj)
    return obj


def git_change_coverage_delta(analysis_out: Path, token: str = "", max_results: int = 10000) -> dict[str, Any]:
    delta = _git_change_data(analysis_out, "before_after_coverage_delta", {}) or {}
    if token and isinstance(delta, dict):
        stages = delta.get("stage_deltas") or []
        delta = dict(delta)
        delta["stage_deltas"] = [x for x in stages if _item_matches_blob(x, token)][:max_results]
    obj = {"kind": "git-change-coverage-delta", "analysis_out": str(analysis_out), "token": token, "coverage_delta": delta}
    write_lazy(_git_change_dir(analysis_out), "git-change-coverage-delta", token or "all", obj)
    return obj


def git_change_risk_signals(analysis_out: Path, token: str = "", max_results: int = 10000) -> dict[str, Any]:
    risks = _git_change_data(analysis_out, "risk_signals", {}) or {}
    complexity = _git_change_data(analysis_out, "complexity_metrics", {}) or {}
    test_doc = _git_change_data(analysis_out, "test_doc_delta", {}) or {}
    obj = {"kind": "git-change-risk-signals", "analysis_out": str(analysis_out), "token": token, "risk_signals": risks, "complexity_metrics": complexity, "test_doc_delta": test_doc}
    write_lazy(_git_change_dir(analysis_out), "git-change-risk-signals", token or "all", obj)
    return obj


def git_change_object_detail(analysis_out: Path, object_id: str, max_results: int = 10000) -> dict[str, Any]:
    token = object_id or ""
    sections: dict[str, Any] = {}
    total = 0
    for name in ["table_delta", "column_delta", "relationship_delta", "lineage_delta", "transformation_delta", "flow_delta", "event_source_delta", "changed_file_catalog"]:
        items, matched = _git_change_list(analysis_out, name, token, max_results)
        sections[name] = items
        total += matched
    obj = {"kind": "git-change-object-detail", "analysis_out": str(analysis_out), "object_id": object_id, "hit_count": total, "sections": sections}
    write_lazy(_git_change_dir(analysis_out), "git-change-object-detail", token or "all", obj)
    return obj
