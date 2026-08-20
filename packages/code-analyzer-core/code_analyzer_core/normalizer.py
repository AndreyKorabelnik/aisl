from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from collections import defaultdict, Counter

from code_analyzer_core.models import AnalysisResult, Fact, EvidenceRef, InterfaceInfo, SchemaInfo, RelationInfo
from code_analyzer_core.utils import normalize_name, write_json


NORMALIZED_FACT_TYPES = {
    "rest_operation",
    "kafka_consumer",
    "kafka_producer",
    "schema_definition",
    "schema_usage",
    "field_propagation",
    "type_mapping",
    "dto_construction",
    "mapper_call",
    "publication",
    "storage_access",
    "sql_access",
    "condition",
    "calculation",
    "fallback",
    "time_window",
    "config_resolution",
    "method_call",
    "operation_link",
    "business_identifier",
    "join_lookup",
    "aggregation",
    "constant",
    "enum",
    "scheduled_job",
    "pattern_evidence",
    "technical_fact",
    "technical_noise",
    "source_to_sink_flow",
    "field_identifier_flow",
    "field_occurrence",
    "field_flow_edge",
    "field_lineage",
    "output_field_provenance",
    "call_chain_diagnostic",
    "system_ingress",
    "data_trace",
    "publisher_payload",
    "serialization",
    "declared_value_set",
    "declared_value",
    "literal_data_write",
    "data_source",
    "persistent_write",
    "source_to_storage_lineage",
    "storage_lineage_gap",
    "read_from_storage",
    "access_boundary",
    "storage_to_access_lineage",
    "stored_field_to_response_field_mapping",
    "persistent_structure",
    "attribute_occurrence",
    "attribute_mapping",
    "attribute_derivation",
    "data_model_lineage_gap",
    "db_schema_table",
    "db_schema_column",
    "db_schema_key",
    "db_schema_relationship",
    "db_schema_index",
    "db_schema_trigger",
    "jpa_entity",
    "jpa_relationship",
    "jpa_inheritance",
    "java_type_declaration",
    "java_inheritance_observation",
    "effective_entity_field",
    "effective_entity_association",
    "sql_join_observation",
    "table_relationship_observation",
    "table_key_observation",
    "data_dictionary_entry",
    "external_dependency",
    "external_dependency_call",
    "system_scenario_candidate",
    "sql_query_model",
    "storage_usage_summary",
    "scenario_storage_summary",
    "declared_value_set_summary",
    "jooq_batch_write_summary",
    "jooq_batch_bind_mapping",
    "jooq_parameterized_sql_mapping",
    "java_lineage_pattern",
    "spring_component_dependency",
    "template_method_dispatch",
    "factory_method_mapping",
    "builder_field_mapping",
    "stream_collection_lineage",
    "mapstruct_mapper_signature",
    "configuration_entry",
    "configuration_object_observation",
    "configuration_reference_observation",
    "configuration_comment_observation",
    "code_annotation",
    "java_method_call_observation",
    "java_method_reference_observation",
    "framework_pattern_observation",
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
    "constructed_value_observation",
    "call_argument_flow_observation",
    "java_call_parameter_binding_observation",
    "java_call_result_binding_observation",
    "java_method_parameter_observation",
    "java_method_implementation_observation",
    "java_method_parameter_correspondence_observation",
    "collection_mutation_observation",
    "type_reference_observation",
}

SCANNER_TYPE_MAPPING = {
    "sql_table_access": "sql_access",
    "call_hint": "method_call",
    "calculation_expression": "calculation",
    "fallback_or_default": "fallback",
    "time_window_hint": "time_window",
    "config_resolution_hint": "config_resolution",
    "configuration_properties_hint": "config_resolution",
    "config_value_hint": "config_resolution",
    "business_identifier_candidate": "business_identifier",
    "join_or_lookup": "join_lookup",
    "targeted_semgrep_evidence": "pattern_evidence",
    "semgrep_match": "pattern_evidence",
    "builder_mapping": "field_propagation",
    "setter_getter_mapping": "field_propagation",
    "mapper_like": "field_propagation",
    "source_to_sink_flow": "source_to_sink_flow",
    "java_data_flow": "source_to_sink_flow",
    "field_identifier_flow": "field_identifier_flow",
    "field_flow": "field_identifier_flow",
}

INTERFACE_FACT_KIND = {
    ("rest", "inbound"): "rest_operation",
    ("rest", "outbound"): "rest_operation",
    ("kafka", "inbound"): "kafka_consumer",
    ("kafka", "outbound"): "kafka_producer",
}

SOURCE_QUALITY_CONFIDENCE = {
    "spoon": 0.90,
    "ast": 0.90,
    "semgrep": 0.80,
    "targeted_semgrep": 0.80,
    "derived_from_extracted_fact": 0.75,
    "regex": 0.60,
    "java_basic": 0.60,
    "java_tree_sitter": 0.72,
    "sqlglot": 0.70,
    "grep": 0.35,
    "unknown": 0.50,
}


def normalize_java_type(value: str | None) -> str:
    if not value:
        return "unknown"
    s = str(value).strip().strip(",;")
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"^(public|private|protected|static|final|abstract|synchronized|native)\s+", "", s)
    m = re.match(r"(?:ResponseEntity|HttpEntity|Optional)\s*<\s*(.+?)\s*>$", s)
    if m:
        s = m.group(1).strip()
    m = re.match(r"(List|Set|Collection|Iterable|Page|Flux|Mono)\s*<\s*(.+?)\s*>$", s)
    if m:
        s = f"collection<{m.group(2).strip()}>"
    s = re.sub(r"\b([a-z_][a-zA-Z0-9_]*\.)+([A-Z][A-Za-z0-9_]*)", r"\2", s)
    if s in {"=", "public", "private", "protected", "void", ""}:
        return "unknown"
    return s


def source_scope(path: str | None) -> str:
    p = (path or "").replace("\\", "/").lower()
    if "/src/test/" in p or p.endswith("test.java") or "/test/" in p:
        return "test"
    if "/target/" in p or "/build/" in p or "/generated/" in p:
        return "generated"
    if p.endswith((".yml", ".yaml", ".properties", ".conf")):
        return "config"
    if p.endswith(".sql"):
        return "sql"
    return "main"



def infer_source_quality(evidence: list[EvidenceRef], properties: dict[str, Any] | None = None) -> str:
    props = properties or {}
    if props.get("source_quality"):
        return str(props["source_quality"])
    extractors = [e.extractor for e in evidence if e.extractor]
    if any(e == "targeted_semgrep" for e in extractors):
        return "targeted_semgrep"
    if any(e == "semgrep" for e in extractors):
        return "semgrep"
    if any(e == "spoon" for e in extractors):
        return "spoon"
    if any(e == "sqlglot" for e in extractors):
        return "sqlglot"
    if any(e and "java_tree_sitter" in e for e in extractors):
        return "java_tree_sitter"
    if any(e == "java_basic" for e in extractors):
        return "java_basic"
    if any(e and "regex" in e for e in extractors):
        return "regex"
    return "unknown"


TECHNICAL_NOISE_TOKENS = [
    "log_trace", "log_debug", "log_info", "log_warn", "log_error", "logger", "logger_handler",
    "loggerhandler", "log_duration", "logduration", "monitoring", "metric", "metrics", "prometheus",
    "timer", "observe_duration", "observeduration", "string_format", "count_latency", "latency",
    "get_message", "exception", "validation", "binding_result"
]


def _noise_probe_text(fact_type: str, name: str = "", props: dict[str, Any] | None = None) -> str:
    """Return a small text probe for noise classification.

    Normalization runs over large real-app fact sets. Stringifying the whole
    properties dict is both expensive and unsafe because trace/persistence facts can
    contain nested paths, field lists and diagnostic arrays. Noise detection only
    needs names and a few stable navigation fields.
    """
    props = props or {}
    keys = (
        "operation", "operation_id", "method", "method_name", "receiver", "receiver_expression",
        "target_operation", "source_operation", "storage_target", "storage_symbol",
        "sink_kind", "target_expression", "table_or_repository", "extractor",
    )
    parts = [fact_type, name]
    for key in keys:
        value = props.get(key)
        if value is not None:
            parts.append(str(value)[:300])
    return " ".join(parts)


def is_technical_noise(fact_type: str, name: str = "", props: dict[str, Any] | None = None) -> bool:
    props = props or {}
    md = props.get("metadata") or {}
    if md.get("evidence_kind") == "technical_noise" or props.get("evidence_kind") == "technical_noise":
        return True
    low = normalize_name(_noise_probe_text(fact_type, name, props))
    if not any(tok in low for tok in TECHNICAL_NOISE_TOKENS):
        return False
    # Keep true data movement publications/storage even when technical words are present.
    if any(tok in low for tok in ["kafka", "producer", "send", "dao", "repository", "jdbc", "sql"]):
        return any(tok in low for tok in ["log_trace", "log_debug", "logger", "loggerhandler", "monitoring", "prometheus", "observe_duration", "string_format", "count_latency"])
    return True


def normalize_fact_type(fact_type: str, name: str = "", props: dict[str, Any] | None = None) -> str:
    props = props or {}
    if is_technical_noise(fact_type, name, props):
        return "technical_noise"
    if fact_type in NORMALIZED_FACT_TYPES:
        return fact_type
    mapped = SCANNER_TYPE_MAPPING.get(fact_type)
    if mapped:
        return mapped

    metadata = props.get("metadata") or {}
    evidence_kind = metadata.get("evidence_kind")
    if evidence_kind in {
        "request_field_propagation", "field_mapping"
    }:
        return "field_propagation"
    if evidence_kind == "response_construction":
        return "dto_construction"
    if evidence_kind == "kafka_publication":
        return "publication"
    if evidence_kind == "storage_or_repository_access":
        return "storage_access"
    if evidence_kind in {"next_processing_call", "rest_operation"}:
        return "method_call"

    low = normalize_name(_noise_probe_text(fact_type, name, props))
    if "kafka" in low and "send" in low:
        return "publication"
    if "repository" in low or "dao" in low or "find" in low:
        return "storage_access"
    return "technical_fact"


def subject_for_fact(fact_type: str, name: str, props: dict[str, Any]) -> str:
    if fact_type == "source_to_sink_flow":
        src = props.get("source_parameter") or props.get("source")
        sink = props.get("sink_kind") or props.get("target_expression") or props.get("sink")
        payload = props.get("payload_expression")
        return str(f"{src} -> {sink} payload {payload}" if src or sink else name)
    if fact_type == "field_identifier_flow":
        src = ".".join(str(x) for x in [props.get("source_object"), props.get("source_field")] if x)
        sink = props.get("sink_channel") or props.get("sink_kind") or props.get("sink")
        payload = props.get("sink_payload") or props.get("payload_expression")
        return str(f"{src} -> {sink} payload {payload}" if src or sink else name)
    if fact_type == "field_occurrence":
        return str(props.get("field_path") or props.get("symbol") or props.get("occurrence_id") or name)
    if fact_type == "field_flow_edge":
        return str(f"{props.get('source_occurrence_id')} -> {props.get('target_occurrence_id')} [{props.get('edge_kind')}]")
    if fact_type == "field_lineage":
        src = ".".join(str(x) for x in [props.get("source_payload"), props.get("source_field")] if x)
        tgt = ".".join(str(x) for x in [props.get("target_boundary"), props.get("target_field")] if x)
        role = props.get("field_role") or props.get("lineage_type")
        return str(f"{role}: {src} -> {tgt}" if tgt else f"{role}: {src}")
    if fact_type == "output_field_provenance":
        target = ".".join(str(x) for x in [props.get("published_boundary"), props.get("published_field")] if x)
        origin = ".".join(str(x) for x in [props.get("origin_payload"), props.get("origin_field")] if x)
        kind = props.get("ultimate_origin_kind") or props.get("origin_kind")
        return str(f"{target} origin={kind} {origin}" if origin else f"{target} origin={kind}")
    if fact_type in {"jooq_batch_bind_mapping", "jooq_parameterized_sql_mapping"}:
        return str(f"{props.get('operation')} {props.get('storage_table')} {props.get('mapping_kind')}")
    if fact_type == "mapstruct_mapper_signature":
        return str(f"{props.get('source_container')} -> {props.get('target_container')} via {props.get('operation')}")
    if fact_type == "java_lineage_pattern":
        return str(f"{props.get('pattern_kind')} {props.get('operation')}")
    if fact_type == "spring_component_dependency":
        return str(f"{props.get('source_class')}.{props.get('field_name')} -> {props.get('declared_type')}")
    if fact_type == "template_method_dispatch":
        return str(f"{props.get('candidate_template_operations')} -> {props.get('override_operation')}")
    if fact_type == "factory_method_mapping":
        return str(f"{props.get('operation')} -> {props.get('target_container')}")
    if fact_type == "builder_field_mapping":
        return str(f"{props.get('operation')} builder mapping")
    if fact_type == "stream_collection_lineage":
        return str(f"{props.get('operation')} stream({props.get('source_collection')})")
    if fact_type == "data_source":
        return str(f"{props.get('source_kind')} {props.get('source_operation')} {props.get('source_payload')}")
    if fact_type == "persistent_write":
        return str(f"{props.get('operation')} write {props.get('storage_target')}")
    if fact_type == "source_to_storage_lineage":
        src = ".".join(str(x) for x in [props.get("source_payload"), props.get("source_field")] if x)
        tgt = ".".join(str(x) for x in [props.get("storage_target"), props.get("storage_field")] if x)
        return str(f"{src} -> {tgt}" if src or tgt else name)
    if fact_type == "storage_lineage_gap":
        return str(f"{props.get('gap_kind')} {props.get('storage_operation')} {props.get('saved_object_field')}")
    if fact_type == "read_from_storage":
        return str(f"{props.get('operation')} read {props.get('storage_symbol') or props.get('storage_object')}")
    if fact_type == "access_boundary":
        return str(f"{props.get('boundary_kind')} {props.get('operation')} {props.get('endpoint_or_topic')}")
    if fact_type == "storage_to_access_lineage":
        return str(f"{props.get('source_storage_object')} -> {props.get('access_boundary')}")
    if fact_type == "stored_field_to_response_field_mapping":
        return str(f"{props.get('storage_object')}.{props.get('storage_field')} -> {props.get('response_or_payload_type')}.{props.get('response_field')}")
    if fact_type == "source_inspection_request":
        return str(f"{props.get('reason')} {props.get('target_operation')} focus={props.get('focus')}")
    if fact_type == "persistent_structure":
        return str(f"{props.get('storage_kind')} {props.get('storage_target')} {props.get('container_name')}")
    if fact_type == "attribute_occurrence":
        return str(f"{props.get('container_name')}.{props.get('attribute_name')}")
    if fact_type == "attribute_mapping":
        return str(f"{props.get('source_container')}.{props.get('source_field')} -> {props.get('target_container')}.{props.get('target_field')}")
    if fact_type == "attribute_derivation":
        return str(f"{props.get('source_fields')} -> {props.get('target_container')}.{props.get('target_field')}")
    if fact_type == "data_model_lineage_gap":
        return str(f"{props.get('gap_kind')} {props.get('container')} {props.get('field')}")
    if fact_type == "call_chain_diagnostic":
        return str(f"{props.get('target_operation')} caller_status={props.get('caller_status')}")
    if fact_type == "system_ingress":
        return str(f"{props.get('origin_kind') or props.get('ingress_kind')} {props.get('operation')}")
    if fact_type == "data_trace":
        return str(f"{props.get('trace_type')} {props.get('trace_status')} {props.get('origin_kind')} -> {props.get('terminal_operation_id')}")
    if fact_type == "db_schema_table":
        return str(f"table {props.get('table_name')} columns={props.get('column_count')}")
    if fact_type == "db_schema_column":
        return str(f"{props.get('table_name')}.{props.get('column_name')} {props.get('sql_type')}")
    if fact_type == "db_schema_key":
        return str(f"{props.get('constraint_kind')} {props.get('table_name')}({props.get('columns')})")
    if fact_type == "db_schema_relationship":
        return str(f"{props.get('source_table')}({props.get('source_columns')}) -> {props.get('target_table')}({props.get('target_columns')})")
    if fact_type == "java_type_declaration":
        return str(f"{props.get('fqcn')} kind={props.get('class_kind')} abstract={props.get('is_abstract')}")
    if fact_type == "java_inheritance_observation":
        return str(f"{props.get('child_fqcn')} {props.get('relation_kind')} {props.get('resolved_parent_fqcn') or props.get('declared_parent_reference')} [{props.get('resolution_kind')}]")
    if fact_type == "effective_entity_field":
        return str(f"{props.get('effective_owner_fqcn')}.{props.get('field_name')} <- {props.get('declared_in_fqcn')} [{props.get('association_origin')}]")
    if fact_type == "effective_entity_association":
        return str(f"{props.get('effective_owner_fqcn')}.{props.get('source_field')} -> {props.get('target_observed_fqcn') or props.get('target_type_reference_observed')} [{props.get('association_origin')}]")
    if fact_type == "table_relationship_observation":
        left = props.get("left_table") or {}
        right = props.get("right_table") or {}
        return str(f"{left.get('qualified_table_name') or left.get('table_name') or left.get('unresolved_name')} -> {right.get('qualified_table_name') or right.get('table_name') or right.get('unresolved_name')} [{props.get('relation_kind')}]")
    if fact_type == "table_key_observation":
        table = props.get("table") or {}
        columns = [item.get("column_name") or item.get("unresolved_name") for item in (props.get("columns") or []) if isinstance(item, dict)]
        return str(f"{table.get('qualified_table_name') or table.get('table_name') or table.get('unresolved_name')}({columns}) [{props.get('key_kind')}]")
    if fact_type == "db_schema_index":
        return str(f"index {props.get('index_name')} on {props.get('table_name')}({props.get('columns')})")
    if fact_type == "declared_value_set":
        return str(f"{props.get('syntax_kind')} {props.get('name')} entries={props.get('entries_count')}")
    if fact_type == "declared_value":
        return str(f"{props.get('set_name')} {props.get('key')}={props.get('value')}")
    if fact_type == "literal_data_write":
        return str(f"{props.get('operation')} {props.get('qualified_table_name') or props.get('table_name')} columns={props.get('columns')}")
    if fact_type == "field_propagation":
        src = ".".join(str(x) for x in [props.get("source_object"), props.get("source_field")] if x)
        tgt = ".".join(str(x) for x in [props.get("target_object"), props.get("target_field")] if x)
        if src or tgt:
            return f"{src} -> {tgt}".strip(" ->")
    if fact_type in {"kafka_producer", "publication"}:
        return str(props.get("send_expression") or props.get("topic_expression") or name)
    if fact_type in {"sql_access", "storage_access"}:
        return str(props.get("table") or props.get("receiver") or name)
    if fact_type == "calculation":
        return str(props.get("target") or props.get("expression") or name)
    if fact_type == "condition":
        return str(props.get("condition") or name)
    if fact_type == "config_resolution":
        return str(props.get("config_key") or name)
    return name



def _slim_evidence_refs(evs: list[EvidenceRef], *, max_refs: int = 3) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for ev in (evs or [])[:max_refs]:
        out.append({
            "file": ev.file_path,
            "line_start": ev.line_start,
            "line_end": ev.line_end,
            "extractor": ev.extractor,
            "source_scope": source_scope(ev.file_path),
        })
    return out



def _slim_json_value(value: Any, *, depth: int = 0, max_list: int = 24, max_dict: int = 32, max_text: int = 900) -> Any:
    """Return a JSON-safe bounded copy of a property value.

    Normalized fact indexes are navigation aids, not full evidence dumps. Real
    traceability facts may carry large nested paths, mapper tables or diagnostic
    arrays; copying them verbatim can make normalization non-linear.
    """
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value if len(value) <= max_text else value[:max_text] + "...<truncated>"
    if isinstance(value, (tuple, set)):
        value = list(value)
    if isinstance(value, list):
        if depth >= 2:
            return [str(x)[:max_text] for x in value[:max_list]]
        out = [_slim_json_value(x, depth=depth + 1, max_list=max_list, max_dict=max_dict, max_text=max_text) for x in value[:max_list]]
        if len(value) > max_list:
            out.append({"truncated": True, "remaining_count": len(value) - max_list})
        return out
    if isinstance(value, dict):
        if depth >= 2:
            items = list(value.items())[:max_dict]
            out = {str(k): str(v)[:max_text] for k, v in items}
        else:
            items = list(value.items())[:max_dict]
            out = {str(k): _slim_json_value(v, depth=depth + 1, max_list=max_list, max_dict=max_dict, max_text=max_text) for k, v in items}
        if len(value) > max_dict:
            out["_truncated"] = {"remaining_key_count": len(value) - max_dict}
        return out
    return str(value)[:max_text]

def _slim_properties(props: dict[str, Any] | None) -> dict[str, Any]:
    """Keep only navigation useful fields. Do not persist full snippets or noisy payloads."""
    props = props or {}
    keep = {
        "direction", "kind", "schema_ref", "schema_ref_normalized", "operation", "path", "method",
        "source", "source_normalized", "target", "target_normalized", "relation_type",
        "table", "query", "query_id", "statement_type", "receiver", "call", "method_name",
        "topic", "topic_expression", "send_expression", "config_key", "source_object", "source_field",
        "target_object", "target_field", "field", "class", "symbol", "callable", "return_type",
        "flow_id", "flow_type", "class_name", "method_visibility", "source_kind", "source_parameter", "source_type",
        "sink_kind", "sink_pattern", "receiver_expression", "target_expression", "payload_expression",
        "flow_mode", "serialization_kind",
        "field_flow_id", "occurrence_id", "edge_id", "repository_id", "method_id", "occurrence_kind",
        "field_path", "expression_text", "resolution_status", "source_occurrence_id", "target_occurrence_id",
        "edge_kind", "basis_node_type", "boundary_direction", "boundary_kind", "boundary_name", "boundary_path",
        "callee_method_id", "candidate_method_ids", "parameter_position", "argument_position", "constructor_method_id",
        "conditional_branch", "conditional_expression", "guards", "ast_node", "relative_file",
        "source_parameter", "source_role", "field_mode", "sink_channel", "sink_payload",
        "related_flow_id",
        "field_lineage_id", "lineage_type", "source_boundary", "source_operation", "source_payload",
        "source_field_type", "target_boundary", "target_operation", "target_payload", "target_location",
        "field_role", "lookup_operation", "returned_or_published", "mapping_kind",
        "output_field_provenance_id", "published_boundary", "published_operation", "published_payload",
        "published_field", "published_location", "origin_kind", "immediate_origin_kind",
        "ultimate_origin_kind", "origin_operation", "origin_payload", "origin_field",
        "origin_expression", "input_origins", "input_origin_kinds", "related_field_lineage_id",
        "source_variable", "source_variable_type",
        "container_field", "container_kind", "element_type", "nested_field", "nested_field_provenance",
        "provenance_depth", "unresolved_boundary", "callee_operation", "callee_resolution_kind",
        "call_chain_diagnostic_id", "target_operation", "caller_status", "caller_candidates",
        "resolved_call_ids", "resolved_callers", "system_ingress_status", "reason",
        "ingress_id", "origin_id", "ingress_kind", "origin_kind", "is_payload_origin",
        "operation_id", "signature", "payload_type", "payload_parameter", "endpoint_or_topic",
        "call_id", "caller_operation_id", "caller_method", "callee_operation_id", "callee_method",
        "argument_bindings", "receiver_type",
        "storage_access_id", "access_kind", "write_kind", "mutation_kind", "table_or_repository",
        "storage_method", "sql_preview",
        "read_from_storage_id", "storage_access_kind", "storage_symbol", "storage_object", "result_type", "filter_expression",
        "access_boundary_id", "boundary_kind", "response_or_payload_type", "external_access",
        "storage_to_access_lineage_id", "read_evidence_ref", "access_evidence_ref", "source_storage_object", "access_boundary", "field_mappings", "lineage_status", "same_method_lineage",
        "stored_field_to_response_field_mapping_id", "storage_object", "storage_field", "read_type", "response_field", "mapping_type", "mapping_source", "evidence_level",
        "candidate_signals", "evidence_maturity_level", "evidence_maturity_dimensions", "evidence_maturity_blockers", "unresolved_gap_lifecycle", "source_inspection_required", "source_inspection_request_ids",
        "source_scope", "storage_read", "access_boundary_status",
        "trace_id", "trace_type", "origin_trace_type", "trace_status",
        "ingress_operation_id", "earliest_observed_operation_id", "earliest_observed_reason",
        "terminal_operation_id", "outbound_operation_id", "outbound_sink_id", "persistence_operation_id",
        "argument_relation_chain", "evidence_refs",
        "jooq_batch_bind_mapping_id", "jooq_parameterized_sql_mapping_id", "storage_table", "storage_table_ref", "write_target_fields", "where_key_fields",
        "java_lineage_pattern_id", "pattern_kind", "spring_component_dependency_id", "source_class", "declared_type", "candidate_implementations",
        "template_method_dispatch_id", "subclass", "superclass", "override_operation", "candidate_template_operations",
        "factory_method_mapping_id", "builder_field_mapping_id", "stream_collection_lineage_id", "target_container", "target_variable", "target_container_candidates", "field_mappings",
        "source_collection", "source_collection_type", "source_element_type", "mapped_collection_candidates",
        "mapstruct_mapper_signature_id", "mapper_class", "source_container",

        "related_field_flow_ids", "saved_payload",
        "declared_value_set_id", "declared_value_set_summary_id", "declared_value_id", "literal_data_write_id",
        "set_name", "syntax_kind", "location_kind", "display_name", "entries_count",
        "entries_observed_count", "sample_entries", "value_facts_emitted", "extraction_truncated",
        "truncation_reason", "retrieval", "file_format", "observation_status",
        "key_type", "value_type", "source_expression", "columns", "key", "value", "entry",
        "entries", "values", "rows", "rows_count", "rows_truncated", "assignments",
        "values_are_literal_or_declared_expression", "parameterized", "literal_only", "write_expression_kind",
        "where_expression", "literal_values", "sql_expression", "change_set_id", "operation",
        "persistent_structure_id", "attribute_occurrence_id", "attribute_mapping_id",
        "attribute_derivation_id", "data_model_lineage_gap_id",
        "project_code", "system_name", "repo_id", "fp_id", "repo_path",
        "db_schema_table_id", "db_schema_column_id", "db_schema_key_id", "db_schema_relationship_id", "db_schema_index_id", "db_schema_trigger_id",
        "observation_id", "schema_version", "relation_kind", "key_kind", "left_table", "right_table", "column_pairs",
        "matched_declared_keys", "statement_id", "query_id", "join_type", "direction", "observation_basis",
        "entity_name", "orm_annotation_kind", "join_columns_declared", "referenced_column_unspecified",
        "identity_mapping_complete", "id_class", "java_operation", "parser",
        "qualified_table_name", "source_qualified_table_name", "target_qualified_table_name",
        "table_name", "normalized_table_name", "schema_name", "table_class", "table_constant", "record_type",
        "column_name", "normalized_column_name", "field_constant", "java_type", "sql_type", "sql_type_expression",
        "nullable", "default_value", "description", "constraint_name", "constraint_kind", "key_constant",
        "relationship_constant", "relationship_kind", "source_table", "source_columns", "target_table", "target_columns", "target_key_constant",
        "entity_class", "parent_class", "source_entity", "source_field", "target_entity", "target_type", "source_table_identity", "table_identity",
        "cardinality", "mapped_by", "join_columns", "optional", "fetch", "inheritance_strategy", "discriminator_column", "discriminator_value",
        "relationship_evidence_kind", "relationship_confidence", "join_condition_preview",
        "trigger_name", "trigger_timing", "trigger_events", "procedure_name", "target_tables",
        "index_constant", "index_name", "unique", "primary_keys", "foreign_keys_out", "foreign_keys_in_count", "indexes", "evidence_sources",
        "source_type", "source_set", "is_test_source", "module_name", "schema_name_basis", "evidence_maturity_level", "evidence_level",
        "boundary_role", "composition_basis", "helper_operation", "scenario_operation",
        "client_receiver", "client_receiver_type", "client_bean_name", "client_call_pattern",
        "endpoint_expression", "endpoint_path", "endpoint_path_property_key",
        "endpoint_path_observed_values", "endpoint_path_variants", "endpoint_path_resolution_basis",
        "base_url_property_key", "base_url_property_keys", "base_url_observed_values",
        "base_url_resolution_status", "endpoint_url_variants", "http_method",
        "request_payload_expression", "request_payload_type", "response_payload_type",
        "local_caller_operations", "local_call_chain_candidates", "request_observed_builder_setters",
        "property_key", "observed_values", "default_value", "target_kind", "binding_basis",
        "method_path_variants", "registration_base_path_variants", "full_path_variants",
        "service_type", "base_path_expression", "base_path_property_key", "base_path_values",
        "container", "container_kind", "container_name", "container_fqcn", "attribute_name",
        "attribute_type", "raw_type", "attribute_role", "storage_kind", "storage_target",
        "fields", "field_count", "source_container", "target_container",
        "expression", "derivation_kind", "source_fields",
        "label", "ordinal", "file", "line_start", "line_end",
        "configuration_format", "configuration_path", "parent_path", "container_path", "node_kind", "list_index", "child_count", "observation_policy",
        "path_segments", "scalar_shape", "source_path", "scalar_fields", "referenced_values", "child_paths",
        "reference_kind", "reference_value", "owner_qualified_name", "template_variable",
        "comment_text", "comment_kind", "indentation", "associated_configuration_path", "association_policy",
        "annotation", "annotation_text", "arguments_raw", "arguments", "argument_order",
        "owner_type", "owner_fqcn", "owner_kind", "owner_method", "owner_operation", "member_name", "member_type",
        "receiver_expression", "method", "arguments", "argument_count", "call_text", "is_unqualified",
        "target_variable", "target_declared_type", "declared_type", "assignment_kind", "expression_tree", "input_symbols", "nested_calls", "nested_call_observation_ids", "nested_call_summaries",
        "call_observation_id", "target_method", "argument_index", "source_expression", "operation_kind",
        "reference_role", "referenced_type", "declared_type_expression", "resolution", "syntax_provider",
    }
    out: dict[str, Any] = {}
    for k, v in props.items():
        if k in keep:
            out[k] = _slim_json_value(v)
    metavars = props.get("metavars")
    if isinstance(metavars, dict):
        slim_metavars = {}
        for key, value in metavars.items():
            if isinstance(value, dict):
                slim_metavars[key] = str(value.get("abstract_content") or value.get("text") or "")[:300]
            else:
                slim_metavars[key] = str(value)[:300]
        if slim_metavars:
            out["metavars"] = slim_metavars
    md = props.get("metadata") or {}
    if isinstance(md, dict):
        md_keep = {k: md.get(k) for k in ["evidence_kind", "source_kind"] if k in md}
        if md_keep:
            out["metadata"] = md_keep
    # Preserve short propagation hints because they are useful in first-pass reasoning.
    rfp = props.get("request_field_propagation")
    if isinstance(rfp, list):
        out["request_field_propagation"] = [str(x)[:300] for x in rfp[:8]]
    steps = props.get("steps")
    if isinstance(steps, list):
        out["steps"] = _slim_json_value(steps, max_list=12)
    missing_links = props.get("missing_links")
    if isinstance(missing_links, list):
        out["missing_links"] = [str(x)[:300] for x in missing_links[:8]]
    return out


def _cap_text(value: Any, limit: int = 1200) -> str:
    text = "" if value is None else str(value)
    return text if len(text) <= limit else text[:limit] + "...<truncated>"


def _record_from_fact_slim(f: Fact, fact_id: str) -> dict[str, Any]:
    ntype = normalize_fact_type(f.fact_type, f.name, f.properties)
    quality = infer_source_quality(f.evidence, f.properties)
    return {
        "fact_id": fact_id,
        "fact_type": ntype,
        "source_fact_type": f.fact_type,
        "subject": _cap_text(subject_for_fact(ntype, f.name, f.properties or {})),
        "name": _cap_text(f.name),
        "properties": _slim_properties(f.properties),
        "evidence": _slim_evidence_refs(f.evidence),
        "source_quality": quality,
    }


def _record_from_interface_slim(i: InterfaceInfo, fact_id: str) -> dict[str, Any]:
    kind = i.kind.value if hasattr(i.kind, "value") else str(i.kind)
    direction = i.direction.value if hasattr(i.direction, "value") else str(i.direction)
    ntype = INTERFACE_FACT_KIND.get((kind, direction), "rest_operation" if kind == "rest" else "technical_fact")
    return {
        "fact_id": fact_id,
        "fact_type": ntype,
        "source_fact_type": "interface",
        "subject": _cap_text(f"{direction} {kind} {i.name}"),
        "name": _cap_text(i.name),
        "properties": _slim_properties({
            "direction": direction,
            "kind": kind,
            "schema_ref": i.schema_ref,
            "schema_ref_normalized": normalize_java_type(i.schema_ref),
            "operation": i.operation,
            "path": i.path,
            "method": i.method,
            **(i.properties or {}),
        }),
        "evidence": _slim_evidence_refs(i.evidence),
        "source_quality": infer_source_quality(i.evidence),
    }


def _record_from_schema_slim(s: SchemaInfo, fact_id: str) -> dict[str, Any]:
    return {
        "fact_id": fact_id,
        "fact_type": "schema_definition",
        "source_fact_type": "schema",
        "subject": _cap_text(normalize_java_type(s.name)),
        "name": _cap_text(s.name),
        "properties": {
            "schema": s.name,
            "schema_normalized": normalize_java_type(s.name),
            "source_type": s.source_type,
            "field_count": len(s.fields),
            "fields_preview": [
                {"name": f.name, "type": f.type, "nested_type": f.nested_type}
                for f in s.fields[:12]
            ],
        },
        "evidence": _slim_evidence_refs(s.evidence),
        "source_quality": infer_source_quality(s.evidence),
    }


def _record_from_relation_slim(r: RelationInfo, fact_id: str) -> dict[str, Any]:
    return {
        "fact_id": fact_id,
        "fact_type": "operation_link" if "operation" in r.relation_type else "method_call",
        "source_fact_type": "relation",
        "subject": _cap_text(f"{r.source} --{r.relation_type}--> {r.target}"),
        "name": _cap_text(r.relation_type),
        "properties": _slim_properties({
            "source": r.source,
            "source_normalized": normalize_java_type(r.source),
            "target": r.target,
            "target_normalized": normalize_java_type(r.target),
            "relation_type": r.relation_type,
            **(r.properties or {}),
        }),
        "evidence": _slim_evidence_refs(r.evidence),
        "source_quality": infer_source_quality(r.evidence),
    }


def build_normalized_fact_store(result: AnalysisResult, *, max_items_per_type: int = 500) -> dict[str, Any]:
    """Build a slim, capped fact index.

    v0.23.62 keeps normalization strictly linear and memory-bounded for real-app
    traceability runs. It avoids whole-property stringification and stores capped
    records only; detailed evidence remains available through lazy evidence tool requests.
    """
    facts_by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
    total_by_type: Counter[str] = Counter()
    skipped_by_type: Counter[str] = Counter()
    fact_seq = 0

    def add_record(record: dict[str, Any]) -> None:
        ntype = str(record.get("fact_type") or "technical_fact")
        total_by_type[ntype] += 1
        if ntype in {"technical_noise", "pattern_evidence"}:
            skipped_by_type[ntype] += 1
            return
        bucket = facts_by_type[ntype]
        if len(bucket) < max_items_per_type:
            bucket.append(record)
        else:
            skipped_by_type[ntype] += 1

    def next_id() -> str:
        nonlocal fact_seq
        fact_seq += 1
        return f"fact_{fact_seq:06d}"

    groups: list[tuple[Any, Any]] = [
        (result.interfaces, _record_from_interface_slim),
        (result.schemas, _record_from_schema_slim),
        (result.relations, _record_from_relation_slim),
        (result.config_facts, _record_from_fact_slim),
        (result.mapper_facts, _record_from_fact_slim),
        (result.facts, _record_from_fact_slim),
    ]
    for collection, builder in groups:
        for item in collection:
            add_record(builder(item, next_id()))

    persisted_by_type = {k: len(v) for k, v in sorted(facts_by_type.items())}
    summary = {
        "fact_count": int(sum(total_by_type.values())),
        "persisted_fact_count": int(sum(persisted_by_type.values())),
        "evidence_count": int(sum(len(item.get("evidence") or []) for items in facts_by_type.values() for item in items)),
        "facts_by_type": dict(sorted(total_by_type.items())),
        "persisted_by_type": persisted_by_type,
        "skipped_by_type": dict(sorted(skipped_by_type.items())),
        "persistence_policy": "slim_capped_indexes_no_snippets; detailed evidence is produced lazily by the evidence provider",
        "decision_policy": "Facts only. No importance, risk, or final lineage decisions are made by the analyzer.",
        "normalization_mode": "linear_bounded_real_app_safe",
    }
    return {"facts_by_type": dict(facts_by_type), "summary": summary}

def write_normalized_fact_store(result: AnalysisResult, facts_dir: Path, *, max_items_per_type: int = 500) -> dict[str, Any]:
    facts_dir.mkdir(parents=True, exist_ok=True)
    by_type_dir = facts_dir / "facts_by_type"
    by_type_dir.mkdir(parents=True, exist_ok=True)

    # Remove obsolete full-dump files if this output directory is being reused.
    for obsolete in [facts_dir / "normalized_facts.json", facts_dir / "evidence_index.json"]:
        if obsolete.exists():
            obsolete.unlink()
    for old in by_type_dir.glob("*.json"):
        old.unlink()

    store = build_normalized_fact_store(result, max_items_per_type=max_items_per_type)
    write_json(facts_dir / "fact_summary.json", store["summary"])
    write_json(facts_dir / "normalized_fact_summary.json", store["summary"])

    for fact_type, items in sorted(store["facts_by_type"].items()):
        safe = re.sub(r"[^a-zA-Z0-9_]+", "_", fact_type)
        write_json(by_type_dir / f"{safe}.json", items)

    return store["summary"]
