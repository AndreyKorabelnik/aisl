from __future__ import annotations

from collections import defaultdict, deque
from pathlib import Path
from typing import Any, Iterable
import json
import re

from code_analyzer_core.models import AnalysisResult, EvidenceRef, Fact


def _first_evidence(evidence: list[Any]) -> list[EvidenceRef]:
    return list(evidence[:1]) if evidence else []


def _evidence_sort_key(item: Any) -> tuple[int, int, int, str, int, int, str]:
    extractor = str(getattr(item, "extractor", "") or "")
    priority = {
        "java_trace_builder_storage": 0,
        "java_trace_builder_trace": 1,
        "java_stored_data_access_boundary": 2,
        "java_persistence_lineage": 3,
        "java_data_model_lineage": 4,
        "java_tree_sitter": 20,
    }.get(extractor, 10)
    line_start = getattr(item, "line_start", None)
    line_end = getattr(item, "line_end", None)
    complete_span = 0 if line_start is not None and line_end is not None else 1
    span = (int(line_end) - int(line_start)) if line_start is not None and line_end is not None else 10**9
    return (
        priority,
        complete_span,
        span,
        str(getattr(item, "file_path", "") or ""),
        int(line_start or 0),
        int(line_end or 0),
        extractor,
    )


def _best_evidence(existing: list[EvidenceRef], candidates: list[Any], *, limit: int = 3) -> list[EvidenceRef]:
    unique: dict[tuple[Any, ...], EvidenceRef] = {}
    for raw in [*existing, *candidates]:
        if raw is None:
            continue
        item = raw if isinstance(raw, EvidenceRef) else EvidenceRef.model_validate(raw)
        key = (item.file_path, item.line_start, item.line_end, item.extractor, item.snippet)
        unique[key] = item
    return sorted(unique.values(), key=_evidence_sort_key)[:limit]


def _source_set_from_evidence(evidence: list[Any]) -> str:
    if not evidence:
        return "unknown"
    path = str(getattr(evidence[0], "file_path", "") or "").replace("\\", "/").lower()
    return "test" if "/src/test/" in path else "main"


def _bounded_reference_sample(entries: Any, *, max_entries: int = 8, max_text: int = 180) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not isinstance(entries, list):
        return out
    for ent in entries[:max_entries]:
        if not isinstance(ent, dict):
            out.append({"value": str(ent)[:max_text]})
            continue
        item: dict[str, Any] = {}
        for key in ("key", "value", "label", "name", "description"):
            if ent.get(key) is not None:
                item[key] = str(ent.get(key))[:max_text]
        if not item:
            for key, value in list(ent.items())[:4]:
                item[str(key)[:40]] = str(value)[:max_text]
        out.append(item)
    return out


def _schema_entries(result: AnalysisResult) -> list[Fact]:
    out: list[Fact] = []
    seen: set[tuple[str, str, str | None]] = set()
    for schema in result.schemas:
        source_set = _source_set_from_evidence(schema.evidence)
        for comment in schema.comments or []:
            if not comment:
                continue
            key = ("schema", schema.name, None)
            if key in seen:
                continue
            seen.add(key)
            out.append(Fact(
                fact_type="data_dictionary_entry",
                name=schema.name,
                properties={
                    "entry_kind": "schema",
                    "container_name": schema.name,
                    "description": comment,
                    "source_type": schema.source_type,
                    "source_set": source_set,
                    "is_test_source": source_set == "test",
                    "evidence_maturity_level": "confirmed",
                },
                evidence=_first_evidence(schema.evidence),
            ))
        for field in schema.fields:
            description = field.description
            constraints = [a for a in field.annotations if str(a).startswith("constraint:") or str(a) in {"NotNull", "NotBlank", "NotEmpty", "required"}]
            if not description and not constraints:
                continue
            key = ("attribute", schema.name, field.name)
            if key in seen:
                continue
            seen.add(key)
            out.append(Fact(
                fact_type="data_dictionary_entry",
                name=f"{schema.name}.{field.name}",
                properties={
                    "entry_kind": "schema_attribute",
                    "container_name": schema.name,
                    "attribute_name": field.name,
                    "attribute_type": field.type,
                    "description": description,
                    "constraints": constraints,
                    "source_type": schema.source_type,
                    "source_set": source_set,
                    "is_test_source": source_set == "test",
                    "evidence_maturity_level": "confirmed" if description else "candidate",
                },
                evidence=_first_evidence(schema.evidence),
            ))
    return out


def _db_schema_description_entries(result: AnalysisResult) -> list[Fact]:
    out: list[Fact] = []
    seen: set[tuple[str, str, str | None]] = set()
    for fact in result.facts:
        if fact.fact_type not in {"db_schema_table", "db_schema_column"}:
            continue
        props = fact.properties or {}
        description = props.get("description")
        if not description:
            continue
        if fact.fact_type == "db_schema_table":
            table = props.get("qualified_table_name") or props.get("table_name") or fact.name
            key = ("table", str(table), None)
            if key in seen:
                continue
            seen.add(key)
            out.append(Fact(
                fact_type="data_dictionary_entry",
                name=str(table),
                properties={
                    "entry_kind": "db_table",
                    "table_name": props.get("table_name"),
                    "schema_name": props.get("schema_name"),
                    "qualified_table_name": table,
                    "description": description,
                    "source_type": props.get("source_type"),
                    "source_set": props.get("source_set") or _source_set_from_evidence(fact.evidence),
                    "is_test_source": props.get("is_test_source"),
                    "evidence_maturity_level": "confirmed",
                },
                evidence=_first_evidence(fact.evidence),
            ))
        else:
            table = props.get("qualified_table_name") or props.get("table_name")
            col = props.get("column_name")
            key = ("column", str(table), str(col))
            if key in seen:
                continue
            seen.add(key)
            out.append(Fact(
                fact_type="data_dictionary_entry",
                name=f"{table}.{col}",
                properties={
                    "entry_kind": "db_column",
                    "table_name": props.get("table_name"),
                    "schema_name": props.get("schema_name"),
                    "qualified_table_name": table,
                    "attribute_name": col,
                    "attribute_type": props.get("sql_type"),
                    "description": description,
                    "source_type": props.get("source_type"),
                    "source_set": props.get("source_set") or _source_set_from_evidence(fact.evidence),
                    "is_test_source": props.get("is_test_source"),
                    "evidence_maturity_level": "confirmed",
                },
                evidence=_first_evidence(fact.evidence),
            ))
    return out


def _interface_description_entries(result: AnalysisResult) -> list[Fact]:
    out: list[Fact] = []
    for i in result.interfaces:
        props = i.properties or {}
        description = props.get("openapi_description") or props.get("operation_description") or props.get("openapi_summary") or props.get("operation_summary")
        if not description:
            continue
        source_set = props.get("source_set") or _source_set_from_evidence(i.evidence)
        out.append(Fact(
            fact_type="data_dictionary_entry",
            name=str(i.operation or i.name),
            properties={
                "entry_kind": "interface_operation",
                "operation": i.operation,
                "endpoint": i.path,
                "http_method": i.method,
                "description": description,
                "source_type": props.get("syntax_provider") or "api_annotation",
                "source_set": source_set,
                "is_test_source": source_set == "test",
                "evidence_maturity_level": "confirmed",
            },
            evidence=_first_evidence(i.evidence),
        ))
    return out


def _external_dependencies(result: AnalysisResult) -> list[Fact]:
    out: list[Fact] = []
    seen: set[str] = set()
    for fact in result.facts:
        if fact.fact_type in {"external_dependency", "external_dependency_call"}:
            continue
        if fact.fact_type == "http_outbound_call":
            props = fact.properties or {}
            key = f"http:{props.get('client_receiver_type')}:{props.get('endpoint_path') or props.get('endpoint_expression')}:{props.get('operation')}"
            if key in seen:
                continue
            seen.add(key)
            out.append(Fact(
                fact_type="external_dependency",
                name=str(props.get("client_receiver_type") or props.get("client_receiver") or fact.name),
                properties={
                    "dependency_kind": "http_outbound",
                    "client_receiver": props.get("client_receiver"),
                    "client_receiver_type": props.get("client_receiver_type"),
                    "operation": props.get("operation"),
                    "endpoint_expression": props.get("endpoint_expression"),
                    "endpoint_path": props.get("endpoint_path"),
                    "base_url_property_key": props.get("base_url_property_key"),
                    "request_payload_type": props.get("request_payload_type"),
                    "response_payload_type": props.get("response_payload_type"),
                    "source_set": props.get("source_set"),
                    "is_test_source": props.get("is_test_source"),
                    "evidence_maturity_level": "confirmed",
                },
                evidence=_first_evidence(fact.evidence),
            ))
    return out


def _main_source_fact(fact: Fact) -> bool:
    return _source_set_from_evidence(fact.evidence) != "test"


_CALL_GRAPH_FACT_TYPES = {
    "java_method_call_observation",
    "type_reference_observation",
    "java_method_implementation_observation",
    "cross_module_call_resolution_observation",
}


def _fact_from_store_row(row: dict[str, Any]) -> Fact:
    return Fact(
        fact_type=str(row.get("fact_type") or ""),
        name=str(row.get("name") or ""),
        properties=dict(row.get("properties") or {}),
        evidence=[EvidenceRef.model_validate(item) for item in (row.get("evidence") or [])],
    )


def _full_source_observation_facts(
    result: AnalysisResult,
    fact_types: Iterable[str],
) -> Iterable[Fact]:
    """Stream selected source-observation types from the uncapped fact store.

    Navigation keeps a bounded preview in ``result.facts``. System-description
    scenario composition needs the complete source-declared call graph, so it
    reads only the explicitly requested JSONL sections. If the store is absent
    (for example in small unit tests), the bounded in-memory facts remain the
    deterministic fallback.
    """
    requested = tuple(sorted(set(fact_types)))
    status = dict((result.coverage or {}).get("source_observation_fact_store") or {})
    manifest_path_raw = status.get("manifest_path")
    section_index = status.get("section_index") or {}
    if status.get("status") == "success" and manifest_path_raw and isinstance(section_index, dict):
        manifest_path = Path(str(manifest_path_raw))
        artifact_root = manifest_path.parent.parent
        emitted = False
        for fact_type in requested:
            metadata = section_index.get(fact_type) or {}
            relative_path = metadata.get("relative_path") if isinstance(metadata, dict) else None
            if not relative_path:
                continue
            section_path = artifact_root / str(relative_path)
            if not section_path.is_file():
                continue
            with section_path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    if not line.strip():
                        continue
                    row = json.loads(line)
                    if row.get("fact_type") != fact_type:
                        continue
                    emitted = True
                    yield _fact_from_store_row(row)
        if emitted:
            return

    for fact in result.facts:
        if fact.fact_type in requested:
            yield fact


def _operation_call_graph(result: AnalysisResult) -> tuple[dict[str, set[str]], dict[tuple[str, str], str]]:
    """Compose a conservative source-declared call graph from existing observations.

    Resolution is intentionally limited to explicit source evidence:
    - exact cross-module call resolution observations;
    - unqualified calls within the same owner type;
    - field receiver -> exact resolved field type -> method;
    - a unique non-test declared implementation for interface/abstract calls.

    Ambiguous implementation sets are not traversed.
    """
    field_types: dict[tuple[str, str], str] = {}
    implementations: dict[tuple[str, str], set[str]] = defaultdict(set)
    known_operations: set[str] = set()

    for fact in _full_source_observation_facts(result, _CALL_GRAPH_FACT_TYPES):
        if not _main_source_fact(fact):
            continue
        props = fact.properties or {}
        if fact.fact_type == "type_reference_observation" and props.get("reference_role") == "field_type":
            owner = str(props.get("owner_fqcn") or "")
            member = str(props.get("member_name") or "").split(".")[-1]
            resolved = str(props.get("resolved_fqcn") or "")
            if owner and member and resolved:
                field_types[(owner, member)] = resolved
        elif fact.fact_type == "java_method_implementation_observation":
            key = (str(props.get("declared_owner_fqcn") or ""), str(props.get("declared_method") or ""))
            operation = str(props.get("implementation_method_operation") or "")
            if all(key) and operation:
                implementations[key].add(operation)
        owner_operation = str(props.get("owner_operation") or props.get("operation") or "")
        if owner_operation:
            known_operations.add(owner_operation)

    for iface in result.interfaces:
        operation = str(iface.operation or iface.name or "")
        if operation:
            known_operations.add(operation)
    # Storage/outbound facts are compact downstream boundaries rather than source
    # observations, but their operation identities are valid call-graph terminals.
    for fact in result.facts:
        props = fact.properties or {}
        for key in ("owner_operation", "operation", "source_operation", "storage_operation"):
            operation = str(props.get(key) or "")
            if operation:
                known_operations.add(operation)

    graph: dict[str, set[str]] = defaultdict(set)
    basis: dict[tuple[str, str], str] = {}

    for fact in _full_source_observation_facts(result, {"java_method_call_observation", "cross_module_call_resolution_observation"}):
        if not _main_source_fact(fact):
            continue
        props = fact.properties or {}
        if fact.fact_type == "cross_module_call_resolution_observation":
            caller = str(props.get("caller_operation") or "")
            callee = str(props.get("callee_operation") or "")
            if caller and callee:
                graph[caller].add(callee)
                basis[(caller, callee)] = "cross_module_exact"
            continue
        if fact.fact_type != "java_method_call_observation":
            continue
        if int(props.get("call_depth") or 0) != 0:
            continue
        caller = str(props.get("owner_operation") or "")
        method = str(props.get("method") or "")
        owner_fqcn = str(props.get("owner_fqcn") or "")
        if not caller or not method:
            continue

        target_fqcns: list[str] = []
        if props.get("is_unqualified"):
            if owner_fqcn:
                target_fqcns.append(owner_fqcn)
        else:
            receiver = str(props.get("receiver_expression") or "")
            if receiver.startswith("this."):
                receiver = receiver[5:]
            if re.fullmatch(r"[A-Za-z_$][\w$]*", receiver):
                resolved = field_types.get((owner_fqcn, receiver))
                if resolved:
                    target_fqcns.append(resolved)
                elif receiver[:1].isupper():
                    target_fqcns.append(receiver)

        for target_fqcn in target_fqcns:
            target_type = target_fqcn.rsplit(".", 1)[-1]
            callee = f"{target_type}.{method}"
            implementation_set = implementations.get((target_fqcn, method), set())
            if callee not in known_operations and not implementation_set:
                continue
            graph[caller].add(callee)
            basis[(caller, callee)] = "receiver_type_exact"
            if len(implementation_set) == 1:
                implementation = next(iter(implementation_set))
                graph[callee].add(implementation)
                basis[(callee, implementation)] = "unique_declared_implementation"

    return graph, basis


def _reachable_operations(
    start: str,
    graph: dict[str, set[str]],
    basis: dict[tuple[str, str], str],
    *,
    max_depth: int = 7,
    max_edges: int = 80,
) -> tuple[set[str], list[dict[str, Any]]]:
    queue = deque([(start, 0)])
    visited = {start}
    edges: list[dict[str, Any]] = []
    while queue and len(edges) < max_edges:
        current, depth = queue.popleft()
        if depth >= max_depth:
            continue
        for target in sorted(graph.get(current, ())):
            if target in visited:
                continue
            visited.add(target)
            edges.append({
                "from_operation": current,
                "to_operation": target,
                "resolution_basis": basis.get((current, target), "observed_source_call"),
                "depth": depth + 1,
            })
            queue.append((target, depth + 1))
            if len(edges) >= max_edges:
                break
    return visited, edges


def _scenario_candidates(result: AnalysisResult) -> list[Fact]:
    by_op: dict[str, dict[str, Any]] = defaultdict(lambda: {"interfaces": []})
    interface_evidence: dict[str, list[EvidenceRef]] = defaultdict(list)
    for i in result.interfaces:
        if _source_set_from_evidence(i.evidence) == "test":
            continue
        op = str(i.operation or i.name or "")
        if not op:
            continue
        by_op[op]["interfaces"].append({
            "direction": str(i.direction.value if hasattr(i.direction, "value") else i.direction),
            "kind": str(i.kind.value if hasattr(i.kind, "value") else i.kind),
            "path": i.path,
            "method": i.method,
            "schema_ref": i.schema_ref,
            "boundary_role": (i.properties or {}).get("boundary_role"),
            "description": (i.properties or {}).get("openapi_description") or (i.properties or {}).get("operation_description") or (i.properties or {}).get("openapi_summary") or (i.properties or {}).get("operation_summary"),
        })
        interface_evidence[op] = _best_evidence(interface_evidence[op], i.evidence)

    graph, edge_basis = _operation_call_graph(result)
    external_by_operation: dict[str, list[dict[str, Any]]] = defaultdict(list)
    storage_by_operation: dict[str, list[dict[str, Any]]] = defaultdict(list)
    evidence_by_operation: dict[str, list[EvidenceRef]] = defaultdict(list)

    for fact in result.facts:
        if not _main_source_fact(fact):
            continue
        props = fact.properties or {}
        op = str(props.get("operation") or props.get("source_operation") or props.get("storage_operation") or "")
        if not op:
            continue
        if fact.fact_type in {"external_dependency_call", "http_outbound_call"}:
            external_by_operation[op].append({
                "fact_type": fact.fact_type,
                "name": fact.name,
                "operation": op,
                "dependency_kind": props.get("dependency_kind") or ("http_outbound" if fact.fact_type == "http_outbound_call" else None),
                "endpoint_expression": props.get("endpoint_expression"),
                "endpoint_path": props.get("endpoint_path"),
                "base_url_property_key": props.get("base_url_property_key"),
                "request_payload_type": props.get("request_payload_type"),
                "response_payload_type": props.get("response_payload_type"),
            })
            evidence_by_operation[op] = _best_evidence(evidence_by_operation[op], fact.evidence)
        elif fact.fact_type in {"storage_access", "persistent_write"}:
            storage_by_operation[op].append({
                "fact_type": fact.fact_type,
                "name": fact.name,
                "operation": op,
                "storage_target": props.get("storage_target") or props.get("table_or_repository") or props.get("target_table"),
                "access_kind": props.get("access_kind") or props.get("write_kind"),
                "storage_method": props.get("storage_method"),
            })
            evidence_by_operation[op] = _best_evidence(evidence_by_operation[op], fact.evidence)

    out: list[Fact] = []
    for idx, (op, data) in enumerate(sorted(by_op.items()), 1):
        interfaces = data.get("interfaces") or []
        if not interfaces:
            continue
        entrypoints = [x for x in interfaces if x.get("boundary_role") in {"rest_request", "kafka_consume"} or x.get("direction") == "inbound"]
        if not entrypoints:
            continue

        reachable, call_chain = _reachable_operations(op, graph, edge_basis)
        external_calls: list[dict[str, Any]] = []
        storage_touches: list[dict[str, Any]] = []
        scenario_evidence = list(interface_evidence.get(op) or [])
        seen_external: set[tuple[Any, ...]] = set()
        seen_storage: set[tuple[Any, ...]] = set()
        for reachable_op in sorted(reachable):
            for item in external_by_operation.get(reachable_op, ()):
                key = (item.get("operation"), item.get("endpoint_path"), item.get("endpoint_expression"), item.get("dependency_kind"))
                if key not in seen_external:
                    seen_external.add(key)
                    external_calls.append(item)
            for item in storage_by_operation.get(reachable_op, ()):
                key = (item.get("operation"), item.get("storage_target"), item.get("access_kind"), item.get("storage_method"))
                if key not in seen_storage:
                    seen_storage.add(key)
                    storage_touches.append(item)
            scenario_evidence = _best_evidence(scenario_evidence, evidence_by_operation.get(reachable_op, []))

        has_composed_boundary = bool(external_calls or storage_touches)
        out.append(Fact(
            fact_type="system_scenario_candidate",
            name=op,
            properties={
                "scenario_id": f"scenario_{idx:06d}",
                "entrypoints": entrypoints[:8],
                "interfaces": interfaces[:20],
                "external_calls": external_calls[:30],
                "storage_touches": storage_touches[:40],
                "call_chain": call_chain,
                "reachable_operation_count": len(reachable),
                "composition_status": "observed_source_call_chain" if has_composed_boundary else "entrypoint_only",
                "scenario_evidence_kind": "entrypoint_plus_observed_source_call_graph",
                "evidence_maturity_level": "candidate",
                "composition_policy": "exact_source_call_resolution_only; ambiguous implementations are not traversed",
            },
            evidence=scenario_evidence[:3],
        ))
    return out



def _storage_target_from_props(props: dict[str, Any]) -> str:
    for key in ("storage_target", "table_or_repository", "target_table", "storage_table", "saved_object"):
        value = props.get(key)
        if value:
            return str(value)
    return "unknown_storage_target"


def _storage_usage_summaries(result: AnalysisResult) -> list[Fact]:
    buckets: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "read_count": 0,
        "write_count": 0,
        "mutation_count": 0,
        "access_count": 0,
        "operations": [],
        "storage_methods": set(),
        "evidence": [],
        "source_sets": set(),
    })
    for fact in result.facts:
        if fact.fact_type not in {"storage_access", "persistent_write"}:
            continue
        props = fact.properties or {}
        target = _storage_target_from_props(props)
        if target == "unknown_storage_target":
            continue
        bucket = buckets[target]
        bucket["access_count"] += 1
        kind = str(props.get("access_kind") or props.get("write_kind") or "unknown").lower()
        if kind == "read":
            bucket["read_count"] += 1
        elif kind in {"write", "insert", "update", "batch_insert", "merge"} or fact.fact_type == "persistent_write":
            bucket["write_count"] += 1
        elif kind in {"mutation", "delete"}:
            bucket["mutation_count"] += 1
        op = props.get("operation") or props.get("source_operation") or props.get("storage_operation")
        if op and op not in bucket["operations"]:
            bucket["operations"].append(op)
        method = props.get("storage_method")
        if method:
            bucket["storage_methods"].add(str(method))
        source_set = props.get("source_set") or _source_set_from_evidence(fact.evidence)
        if source_set:
            bucket["source_sets"].add(str(source_set))
        if fact.evidence and len(bucket["evidence"]) < 3:
            bucket["evidence"].extend(_first_evidence(fact.evidence))
    out: list[Fact] = []
    for idx, (target, bucket) in enumerate(sorted(buckets.items()), 1):
        out.append(Fact(
            fact_type="storage_usage_summary",
            name=target,
            properties={
                "storage_usage_summary_id": f"storage_usage_summary_{idx:06d}",
                "storage_target": target,
                "access_count": bucket["access_count"],
                "read_count": bucket["read_count"],
                "write_count": bucket["write_count"],
                "mutation_count": bucket["mutation_count"],
                "operations": bucket["operations"][:50],
                "operation_count": len(bucket["operations"]),
                "storage_methods": sorted(bucket["storage_methods"]),
                "source_sets": sorted(bucket["source_sets"]),
                "summary_basis": "storage_access_and_persistent_write_facts",
                "evidence_maturity_level": "confirmed",
            },
            evidence=list(bucket["evidence"])[:3],
        ))
    return out


def _scenario_storage_summaries(result: AnalysisResult) -> list[Fact]:
    # Build report-friendly scenario/storage summaries from all available
    # interface, storage, lineage and access-boundary facts.  Earlier versions
    # emitted a row only when an inbound interface operation id exactly matched a
    # storage operation id.  Real Java applications frequently split controller,
    # service and DAO operation names, so the exact-match rule produced an empty
    # catalog despite rich persistence evidence.  The summary now keeps exact
    # inbound matches when available and also emits method/service/DAO operation
    # summaries with an explicit resolution status.  This is intentionally coarse
    # evidence for system reports, not field-level end-to-end proof.
    by_op: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "entrypoints": [],
        "reads": set(),
        "writes": set(),
        "mutations": set(),
        "storage_touches": [],
        "traces": [],
        "lineage_samples": [],
        "access_boundaries": [],
        "external_calls": [],
        "evidence": [],
    })

    def add_evidence(bucket: dict[str, Any], fact: Fact) -> None:
        if fact.evidence:
            bucket["evidence"] = _best_evidence(bucket["evidence"], fact.evidence)

    for iface in result.interfaces:
        props = iface.properties or {}
        direction = str(iface.direction.value if hasattr(iface.direction, "value") else iface.direction)
        boundary_role = props.get("boundary_role")
        if direction != "inbound" and boundary_role not in {"rest_request", "kafka_consume"}:
            continue
        op = str(iface.operation or iface.name or "")
        if not op:
            continue
        bucket = by_op[op]
        bucket["entrypoints"].append({
            "operation": op,
            "kind": str(iface.kind.value if hasattr(iface.kind, "value") else iface.kind),
            "path": iface.path,
            "method": iface.method,
            "schema_ref": iface.schema_ref,
            "description": props.get("operation_description") or props.get("operation_summary") or props.get("openapi_description") or props.get("openapi_summary"),
        })
        if iface.evidence:
            bucket["evidence"] = _best_evidence(bucket["evidence"], iface.evidence)

    for fact in result.facts:
        props = fact.properties or {}
        op = props.get("operation") or props.get("terminal_operation_id") or props.get("persistence_operation_id") or props.get("source_operation") or props.get("storage_operation") or props.get("access_boundary")
        if not op:
            continue
        op = str(op)
        bucket = by_op[op]
        if fact.fact_type == "storage_access":
            target = _storage_target_from_props(props)
            if target == "unknown_storage_target":
                continue
            kind = str(props.get("access_kind") or "unknown").lower()
            if kind == "read":
                bucket["reads"].add(target)
            elif kind in {"write", "insert", "update", "merge", "batch_insert"}:
                bucket["writes"].add(target)
            elif kind in {"mutation", "delete"}:
                bucket["mutations"].add(target)
            bucket["storage_touches"].append({
                "fact_type": fact.fact_type,
                "storage_target": target,
                "access_kind": kind,
                "storage_method": props.get("storage_method"),
                "storage_access_id": props.get("storage_access_id"),
            })
            add_evidence(bucket, fact)
        elif fact.fact_type == "persistent_write":
            target = _storage_target_from_props(props)
            if target == "unknown_storage_target":
                continue
            bucket["writes"].add(target)
            bucket["storage_touches"].append({
                "fact_type": fact.fact_type,
                "storage_target": target,
                "access_kind": props.get("write_kind") or "write",
                "storage_method": props.get("storage_method"),
                "storage_access_id": props.get("storage_access_id"),
                "persistent_write_id": props.get("persistent_write_id"),
                "saved_object": props.get("saved_object"),
            })
            add_evidence(bucket, fact)
        elif fact.fact_type == "source_to_storage_lineage":
            target = _storage_target_from_props(props)
            if target != "unknown_storage_target":
                bucket["writes"].add(target)
            bucket["lineage_samples"].append({
                "fact_type": fact.fact_type,
                "lineage_id": props.get("source_to_storage_lineage_id"),
                "source_kind": props.get("source_kind"),
                "source_payload": props.get("source_payload"),
                "source_field": props.get("source_field"),
                "storage_target": target if target != "unknown_storage_target" else None,
                "storage_field": props.get("storage_field"),
                "missing_links": props.get("missing_links") or [],
            })
            add_evidence(bucket, fact)
        elif fact.fact_type == "storage_to_access_lineage":
            target = props.get("source_storage_object") or props.get("storage_object") or props.get("storage_target")
            if target:
                bucket["reads"].add(str(target))
            bucket["lineage_samples"].append({
                "fact_type": fact.fact_type,
                "lineage_id": props.get("storage_to_access_lineage_id"),
                "source_storage_object": target,
                "access_boundary": props.get("access_boundary"),
                "lineage_status": props.get("lineage_status"),
                "missing_links": props.get("missing_links") or [],
            })
            add_evidence(bucket, fact)
        elif fact.fact_type == "access_boundary":
            bucket["access_boundaries"].append({
                "access_boundary_id": props.get("access_boundary_id"),
                "boundary_kind": props.get("boundary_kind"),
                "endpoint_or_topic": props.get("endpoint_or_topic"),
                "response_or_payload_type": props.get("response_or_payload_type"),
                "external_access": props.get("external_access"),
            })
            add_evidence(bucket, fact)
        elif fact.fact_type == "data_trace":
            target = props.get("table_or_repository")
            if target:
                kind = str(props.get("db_write_kind") or props.get("sink_kind") or "unknown").lower()
                if "write" in kind or "insert" in kind or "persist" in kind:
                    bucket["writes"].add(str(target))
                else:
                    bucket["reads"].add(str(target))
            bucket["traces"].append({
                "trace_id": props.get("trace_id"),
                "trace_type": props.get("trace_type"),
                "trace_status": props.get("trace_status"),
                "storage_access_id": props.get("storage_access_id"),
                "table_or_repository": target,
                "missing_links": props.get("missing_links") or [],
            })
            add_evidence(bucket, fact)
        elif fact.fact_type in {"external_dependency", "external_dependency_call", "http_outbound_call"}:
            bucket["external_calls"].append({
                "name": fact.name,
                "dependency_kind": props.get("dependency_kind") or ("http_outbound" if fact.fact_type == "http_outbound_call" else None),
                "client_receiver_type": props.get("client_receiver_type"),
                "endpoint_path": props.get("endpoint_path"),
            })
            add_evidence(bucket, fact)
    out: list[Fact] = []
    idx = 0
    for op, bucket in sorted(by_op.items()):
        has_activity = bool(bucket["reads"] or bucket["writes"] or bucket["mutations"] or bucket["external_calls"] or bucket["traces"] or bucket["lineage_samples"] or bucket["access_boundaries"] or bucket["storage_touches"])
        if not has_activity:
            continue
        idx += 1
        resolution = "direct_inbound_entrypoint_match" if bucket["entrypoints"] else "no_direct_inbound_entrypoint_matched"
        out.append(Fact(
            fact_type="scenario_storage_summary",
            name=op,
            properties={
                "scenario_storage_summary_id": f"scenario_storage_summary_{idx:06d}",
                "operation": op,
                "entrypoint_resolution_status": resolution,
                "entrypoints": bucket["entrypoints"][:10],
                "read_storage_targets": sorted(bucket["reads"]),
                "write_storage_targets": sorted(bucket["writes"]),
                "mutation_storage_targets": sorted(bucket["mutations"]),
                "storage_touches": bucket["storage_touches"][:80],
                "trace_samples": bucket["traces"][:30],
                "lineage_samples": bucket["lineage_samples"][:40],
                "access_boundaries": bucket["access_boundaries"][:30],
                "external_calls": bucket["external_calls"][:30],
                "summary_basis": "operation_plus_storage_lineage_access_boundary_external_call_facts",
                "evidence_maturity_level": "candidate" if resolution != "direct_inbound_entrypoint_match" else "confirmed_coarse",
            },
            evidence=list(bucket["evidence"])[:3],
        ))
    return out


def _jooq_batch_write_summaries(result: AnalysisResult) -> list[Fact]:
    out: list[Fact] = []
    seq = 0
    for fact in result.facts:
        if fact.fact_type != "jooq_batch_bind_mapping":
            continue
        props = fact.properties or {}
        table = props.get("storage_table")
        if not table:
            continue
        mappings = props.get("mappings") or []
        write_fields = props.get("write_target_fields") or [m for m in mappings if isinstance(m, dict) and m.get("field_role") == "write_target_field"]
        seq += 1
        out.append(Fact(
            fact_type="jooq_batch_write_summary",
            name=f"{props.get('operation')}: {table}",
            properties={
                "jooq_batch_write_summary_id": f"jooq_batch_write_summary_{seq:06d}",
                "jooq_batch_bind_mapping_id": props.get("jooq_batch_bind_mapping_id"),
                "operation": props.get("operation"),
                "class_name": props.get("class_name"),
                "method_name": props.get("method_name"),
                "storage_table": table,
                "storage_table_ref": props.get("storage_table_ref"),
                "mapping_kind": props.get("mapping_kind"),
                "write_fields": [
                    {
                        "storage_field": m.get("storage_field"),
                        "storage_field_ref": m.get("storage_field_ref"),
                        "source_object": m.get("source_object"),
                        "source_field": m.get("source_field"),
                        "source_generation": m.get("source_generation"),
                        "mapping_status": m.get("mapping_status"),
                    }
                    for m in write_fields if isinstance(m, dict)
                ][:64],
                "where_key_fields": props.get("where_key_fields") or [],
                "summary_basis": "jooq_batch_bind_mapping_without_full_persistence_lineage",
                "evidence_maturity_level": "confirmed",
            },
            evidence=_first_evidence(fact.evidence),
        ))
    return out



def _declared_value_set_summaries_from_existing_sets(result: AnalysisResult, *, max_sets: int = 300) -> list[Fact]:
    value_sets = [fact for fact in result.facts if fact.fact_type == "declared_value_set"]
    if not value_sets:
        return []
    existing_set_ids = {
        str((fact.properties or {}).get("declared_value_set_id"))
        for fact in result.facts
        if fact.fact_type == "declared_value_set_summary" and (fact.properties or {}).get("declared_value_set_id")
    }

    def rank(fact: Fact) -> tuple[int, str, str]:
        props = fact.properties or {}
        return (
            int(props.get("entries_count") or 0),
            str(props.get("source_set") or "unknown"),
            str(props.get("name") or fact.name),
        )

    out: list[Fact] = []
    for fact in sorted(value_sets, key=rank, reverse=True):
        props = fact.properties or {}
        set_id = props.get("declared_value_set_id")
        if set_id and str(set_id) in existing_set_ids:
            continue
        if len(out) >= max_sets:
            break
        summary_id = props.get("declared_value_set_summary_id") or (f"{set_id}_summary" if set_id else None)
        out.append(Fact(
            fact_type="declared_value_set_summary",
            name=str(props.get("name") or fact.name),
            properties={
                "declared_value_set_summary_id": summary_id,
                "declared_value_set_id": set_id,
                "name": props.get("name") or fact.name,
                "syntax_kind": props.get("syntax_kind"),
                "location_kind": props.get("location_kind"),
                "source_set": props.get("source_set"),
                "entries_count": props.get("entries_count"),
                "entries_observed_count": props.get("entries_observed_count"),
                "sample_entries": _bounded_reference_sample(props.get("sample_entries") or props.get("entries") or [], max_entries=12),
                "key_type": props.get("key_type"),
                "value_type": props.get("value_type"),
                "source_expression": str(props.get("source_expression"))[:300] if props.get("source_expression") is not None else None,
                "extraction_truncated": bool(props.get("extraction_truncated")),
                "truncation_reason": props.get("truncation_reason"),
                "retrieval": props.get("retrieval"),
                "summary_policy": "bounded_summary_of_observed_declared_value_set",
                "semantic_classification_performed": False,
            },
            evidence=_first_evidence(fact.evidence),
        ))
    return out

def build_system_description_enrichment_facts(result: AnalysisResult) -> tuple[list[Fact], dict[str, Any]]:
    """Build cheap, derived evidence for system description.

    The function only re-packages already collected scanner facts into views that
    are useful for LLM system-description profiles. It does not infer business
    meaning, source-of-truth, or end-to-end lineage.
    """
    facts: list[Fact] = []
    for builder in (
        _schema_entries,
        _db_schema_description_entries,
        _interface_description_entries,
        _external_dependencies,
        _storage_usage_summaries,
        _scenario_storage_summaries,
        _jooq_batch_write_summaries,
        _declared_value_set_summaries_from_existing_sets,
        _scenario_candidates,
    ):
        facts.extend(builder(result))
    counts: dict[str, int] = defaultdict(int)
    for fact in facts:
        counts[fact.fact_type] += 1
    return facts, {"requested": True, "facts_extracted": len(facts), "facts_by_type": dict(sorted(counts.items())), "policy": "derived_from_existing_evidence_no_business_inference"}
