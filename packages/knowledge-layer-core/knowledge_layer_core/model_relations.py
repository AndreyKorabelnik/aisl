from __future__ import annotations

import json
import re
from collections import defaultdict
from typing import Any, Iterable

from prepared_knowledge_runtime.normalization import stable_id

_REFERENCE_OPERATIONS = {
    "referenceField": ("reference_field", "one"),
    "referenceCollection": ("reference_collection", "many"),
    "reference": ("reference_field", "one"),
    "references": ("reference_collection", "many"),
    "replaceReferenceCollection": ("reference_collection", "many"),
    "replacePolymorphicReferenceCollection": ("polymorphic_reference_collection", "many"),
}
_SCALAR_SIMPLE_NAMES = {
    "boolean", "byte", "short", "int", "long", "float", "double", "char",
    "Boolean", "Byte", "Short", "Integer", "Long", "Float", "Double", "Character",
    "String", "Date", "Instant", "LocalDate", "LocalDateTime", "OffsetDateTime", "ZonedDateTime",
    "BigDecimal", "BigInteger", "UUID", "byte[]",
}


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _decode(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default
    return value


def _quoted_string(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"\"", "'"}:
        return text[1:-1]
    return None


def _converter_model_simple_name(converter_fqcn: str, model_simple_names: Iterable[str]) -> str | None:
    """Resolve an observed converter owner to one configured model by name containment.

    This is deliberately independent of any project-specific converter suffix.  A match
    is emitted only when the longest contained configured model name is unique.
    """
    converter_simple = converter_fqcn.rsplit(".", 1)[-1]
    matches = sorted(
        {name for name in model_simple_names if name and name in converter_simple},
        key=lambda value: (-len(value), value),
    )
    if not matches:
        return None
    longest = len(matches[0])
    winners = [name for name in matches if len(name) == longest]
    return winners[0] if len(winners) == 1 else None


def _is_scalar_target(type_name: str | None) -> bool:
    if not type_name:
        return True
    simple = type_name.rsplit(".", 1)[-1]
    return simple in _SCALAR_SIMPLE_NAMES or type_name.startswith(("java.lang.", "java.time."))


def _nested_converter_method(call_text: str | None) -> str | None:
    if not call_text:
        return None
    match = re.search(r',\s*([A-Za-z_$][\w$]*)\s*\(', call_text)
    return match.group(1) if match else None


def _method_from_ref_assignment(expression: str | None, field_name: str) -> str | None:
    if not expression or field_name not in expression:
        return None
    match = re.match(r'\s*([A-Za-z_$][\w$]*)\s*\(', expression)
    return match.group(1) if match else None


def _field_name_from_arg_flows(call_id: str, arg_flows_by_call: dict[str, list[dict[str, Any]]]) -> str | None:
    for row in arg_flows_by_call.get(call_id, []):
        raw_index = row.get("argument_index")
        if raw_index is None or int(raw_index) != 0:
            continue
        value = _quoted_string(row.get("source_expression"))
        if value:
            return value
    return None


def build_model_relationship_rows(
    *,
    key_rows: Iterable[dict[str, Any]],
    type_rows: Iterable[dict[str, Any]],
    field_rows: Iterable[dict[str, Any]],
    inheritance_rows: Iterable[dict[str, Any]],
    type_reference_rows: Iterable[dict[str, Any]],
    method_call_rows: Iterable[dict[str, Any]],
    argument_flow_rows: Iterable[dict[str, Any]],
    constructed_value_rows: Iterable[dict[str, Any]],
    tsa_reference_rows: Iterable[dict[str, Any]] = (),
    tsa_key_expression_rows: Iterable[dict[str, Any]] = (),
) -> tuple[list[tuple[Any, ...]], list[tuple[Any, ...]], list[tuple[Any, ...]], list[tuple[Any, ...]], list[tuple[Any, ...]]]:
    key_rows = list(key_rows)
    type_rows = list(type_rows)
    field_rows = list(field_rows)
    inheritance_rows = list(inheritance_rows)
    type_reference_rows = list(type_reference_rows)
    method_call_rows = list(method_call_rows)
    argument_flow_rows = list(argument_flow_rows)
    constructed_value_rows = list(constructed_value_rows)
    tsa_reference_rows = list(tsa_reference_rows)
    tsa_key_expression_rows = list(tsa_key_expression_rows)

    key_ids_by_object: dict[str, list[str]] = defaultdict(list)
    source_repo_by_object: dict[str, str] = {}
    for row in key_rows:
        fqcn = str(row.get("object_fqcn") or "")
        key_id = str(row.get("key_observation_id") or "")
        if fqcn and key_id:
            key_ids_by_object[fqcn].append(key_id)
            source_repo_by_object.setdefault(fqcn, str(row.get("repo_id") or ""))
    root_model_objects = set(key_ids_by_object)

    type_id_by_fqcn: dict[str, str] = {}
    type_repo_by_fqcn: dict[str, str] = {}
    for row in type_rows:
        fqcn = str(row.get("fqcn") or "")
        type_id = str(row.get("java_type_occurrence_id") or "")
        if fqcn and type_id:
            type_id_by_fqcn.setdefault(fqcn, type_id)
            type_repo_by_fqcn.setdefault(fqcn, str(row.get("repo_id") or ""))

    # Converter owners are themselves Java types in the workspace. Matching a
    # converter name against every type therefore selects the converter class
    # itself as the longest name and silently disconnects TSA operations from
    # configured model objects. Restrict name containment to objects that have
    # mechanically observed key metadata and are actually traversed by this mart.
    simple_to_model_objects: dict[str, list[str]] = defaultdict(list)
    for fqcn in sorted(root_model_objects):
        if fqcn in type_id_by_fqcn:
            simple_to_model_objects[fqcn.rsplit(".", 1)[-1]].append(fqcn)

    parent_by_child: dict[str, str] = {}
    for row in inheritance_rows:
        child = str(row.get("child_fqcn") or "")
        parent = str(row.get("resolved_parent_fqcn") or "")
        relation_kind = str(row.get("relation_kind") or "extends")
        if child and parent and relation_kind == "extends":
            parent_by_child.setdefault(child, parent)

    fields_by_owner: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in field_rows:
        owner = str(row.get("owner_fqcn") or "")
        name = str(row.get("field_name") or "")
        if owner and name:
            fields_by_owner[owner].append(row)

    type_ref_by_owner_field: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in type_reference_rows:
        if str(row.get("reference_role") or "") != "field_type":
            continue
        owner = str(row.get("owner_fqcn") or "")
        member = str(row.get("member_name") or "")
        if owner and member:
            type_ref_by_owner_field[(owner, member)].append(row)

    arg_flows_by_call: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in argument_flow_rows:
        call_id = str(row.get("call_observation_local_id") or row.get("call_observation_id") or "")
        if call_id:
            arg_flows_by_call[call_id].append(row)

    constructed_by_owner: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in constructed_value_rows:
        owner = str(row.get("owner_fqcn") or "")
        if owner:
            constructed_by_owner[owner].append(row)

    tsa_keys_by_owner: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in tsa_key_expression_rows:
        owner = str(row.get("owner_fqcn") or "")
        if owner:
            normalized = dict(row)
            normalized.setdefault("expression_text", row.get("key_expression"))
            normalized.setdefault("input_symbols_json", row.get("key_input_symbols_json") or row.get("input_symbols_json"))
            tsa_keys_by_owner[owner].append(normalized)

    method_calls_by_owner_method: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    operation_groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in method_call_rows:
        owner = str(row.get("owner_fqcn") or "")
        owner_method = str(row.get("owner_method") or "")
        if owner and owner_method:
            method_calls_by_owner_method[(owner, owner_method)].append(row)
        target_method = str(row.get("target_method") or row.get("method") or "")
        if target_method not in _REFERENCE_OPERATIONS:
            continue
        model_simple = _converter_model_simple_name(owner, simple_to_model_objects)
        candidates = simple_to_model_objects.get(model_simple or "", [])
        if len(candidates) != 1:
            continue
        call_id = str(row.get("source_observation_occurrence_id") or row.get("observation_id") or "")
        local_call_id = str(row.get("local_observation_id") or row.get("call_observation_id") or call_id)
        field_name = _field_name_from_arg_flows(local_call_id, arg_flows_by_call)
        if not field_name:
            field_name = _field_name_from_arg_flows(call_id, arg_flows_by_call)
        if not field_name:
            continue
        enriched = dict(row)
        enriched["source_object_fqcn"] = candidates[0]
        enriched["field_name"] = field_name
        enriched["operation_name"] = target_method
        enriched["call_id"] = call_id
        operation_groups[(candidates[0], field_name)].append(enriched)

    # Prefer interpreter observations when available. They preserve the exact TSA API
    # occurrence and argument AST while leaving relationship classification mechanical.
    for row in tsa_reference_rows:
        owner = str(row.get("owner_fqcn") or "")
        model_simple = _converter_model_simple_name(owner, simple_to_model_objects)
        candidates = simple_to_model_objects.get(model_simple or "", [])
        if len(candidates) != 1:
            continue
        expressions = _decode(row.get("argument_expressions_json") or row.get("argument_expressions"), [])
        field_name = None
        if isinstance(expressions, list) and expressions:
            field_name = _quoted_string(expressions[0])
            if not field_name and isinstance(expressions[0], str):
                token = expressions[0].strip()
                known_fields = {str(f.get("field_name") or "") for f in fields_by_owner.get(candidates[0], [])}
                if token in known_fields:
                    field_name = token
        if not field_name:
            continue
        method = str(row.get("method") or "")
        kind = str(row.get("tsa_observation_kind") or "")
        if not method:
            method = "referenceCollection" if kind == "reference_collection_call" else "referenceField"
        enriched = dict(row)
        enriched["source_object_fqcn"] = candidates[0]
        enriched["field_name"] = field_name
        enriched["operation_name"] = method
        enriched["call_id"] = str(row.get("source_observation_occurrence_id") or row.get("observation_id") or "")
        operation_groups[(candidates[0], field_name)].append(enriched)

    def effective_fields(object_fqcn: str) -> list[dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        seen: set[str] = set()
        current = object_fqcn
        depth = 0
        while current and current not in seen:
            seen.add(current)
            for row in fields_by_owner.get(current, []):
                name = str(row.get("field_name") or "")
                if not name or name in result:
                    continue
                effective = dict(row)
                effective["effective_owner_fqcn"] = object_fqcn
                effective["declaration_owner_fqcn"] = current
                effective["inherited"] = depth > 0
                effective["inheritance_depth"] = depth
                result[name] = effective
            current = parent_by_child.get(current, "")
            depth += 1
        return [result[name] for name in sorted(result)]

    def resolved_field_target(field: dict[str, Any]) -> tuple[str | None, list[str]]:
        owner = str(field.get("declaration_owner_fqcn") or field.get("owner_fqcn") or "")
        name = str(field.get("field_name") or "")
        refs = type_ref_by_owner_field.get((owner, name), [])
        resolved = sorted({str(row.get("resolved_fqcn") or "") for row in refs if row.get("resolved_fqcn")})
        candidates: set[str] = set(resolved)
        for row in refs:
            values = _decode(row.get("candidate_fqcns_json") or row.get("candidate_fqcns"), [])
            if isinstance(values, list):
                candidates.update(str(value) for value in values if value)
        return (resolved[0] if len(resolved) == 1 else None, sorted(candidates))

    def source_key_expressions(converter_owner: str, operation: dict[str, Any]) -> list[dict[str, Any]]:
        rows = []
        operation_method = str(operation.get("owner_method") or operation.get("owner_operation") or "")
        for row in tsa_keys_by_owner.get(converter_owner, []):
            owner_method = str(row.get("owner_method") or row.get("owner_operation") or "")
            same_method = bool(operation_method) and (owner_method == operation_method or owner_method.endswith("." + operation_method))
            default_convert = not operation_method and (not owner_method or owner_method == "convert" or owner_method.endswith(".convert"))
            if same_method or default_convert:
                if row.get("expression_text"):
                    rows.append(row)
        for row in constructed_by_owner.get(converter_owner, []):
            row_method = str(row.get("owner_method") or "")
            if operation_method and row_method != operation_method:
                continue
            if not operation_method and row_method != "convert":
                continue
            if str(row.get("target_variable") or "") != "key":
                continue
            expression = str(row.get("expression_text") or row.get("expression") or "")
            if expression:
                rows.append(row)
        return rows

    def target_method_for_operation(operation: dict[str, Any], field_name: str) -> str | None:
        method = _nested_converter_method(str(operation.get("expression_text") or operation.get("call_text") or ""))
        if method:
            return method
        owner = str(operation.get("owner_fqcn") or "")
        for row in constructed_by_owner.get(owner, []):
            if str(row.get("owner_method") or "") != "convert" or str(row.get("target_variable") or "") != "refKey":
                continue
            method = _method_from_ref_assignment(str(row.get("expression_text") or row.get("expression") or ""), field_name)
            if method:
                return method
        return None

    def target_key_expressions(converter_owner: str, nested_method: str | None) -> list[dict[str, Any]]:
        if not nested_method:
            return []

        def direct_key_rows(method_name: str) -> list[dict[str, Any]]:
            rows: list[dict[str, Any]] = []
            for row in tsa_keys_by_owner.get(converter_owner, []):
                owner_method = str(row.get("owner_method") or row.get("owner_operation") or "")
                if owner_method == method_name or owner_method.endswith("." + method_name):
                    expression = str(row.get("expression_text") or "")
                    if expression:
                        rows.append(row)
            for row in constructed_by_owner.get(converter_owner, []):
                if str(row.get("owner_method") or "") != method_name or str(row.get("target_variable") or "") != "key":
                    continue
                expression = str(row.get("expression_text") or row.get("expression") or "")
                # A child/reference key is observed as a derivation from parentKey.
                # Calls that merely assign `key = convertX(...)` are navigation, not key expressions.
                if re.match(r"\s*parentKey\s*\+", expression):
                    rows.append(row)
            return rows

        method_candidates = [nested_method]
        if nested_method.endswith("Collection"):
            method_candidates.append(nested_method[: -len("Collection")])
        result: list[dict[str, Any]] = []
        for method_name in method_candidates:
            result.extend(direct_key_rows(method_name))

        # Polymorphic collection dispatchers call several concrete converter methods.
        # Follow only directly observed calls and collect their actual parent-derived keys.
        called_methods = sorted({
            str(call.get("target_method") or "")
            for call in method_calls_by_owner_method.get((converter_owner, nested_method), [])
            if str(call.get("target_method") or "").startswith("convert")
        })
        for method_name in called_methods:
            result.extend(direct_key_rows(method_name))
        return result

    relationship_rows: list[tuple[Any, ...]] = []
    key_expression_rows: list[tuple[Any, ...]] = []
    polymorphic_rows: list[tuple[Any, ...]] = []
    embedded_rows: list[tuple[Any, ...]] = []
    candidate_rows: list[tuple[Any, ...]] = []

    # Traverse the observed object graph from registered roots. A queue is used
    # instead of iterating only root objects so nested owned types contribute their
    # own outgoing relationships. Each type is expanded once, which makes cycles
    # and repeated reuse deterministic and safe.
    classes_to_scan = list(sorted(root_model_objects))
    visited_objects: set[str] = set()
    scan_index = 0
    while scan_index < len(classes_to_scan):
        source_object = classes_to_scan[scan_index]
        scan_index += 1
        if source_object in visited_objects:
            continue
        visited_objects.add(source_object)
        source_repo = source_repo_by_object.get(source_object) or type_repo_by_fqcn.get(source_object, "")
        for field in effective_fields(source_object):
            field_id = str(field.get("code_field_occurrence_id") or "")
            field_name = str(field.get("field_name") or "")
            declaration_owner = str(field.get("declaration_owner_fqcn") or "")
            inherited = bool(field.get("inherited"))
            depth = int(field.get("inheritance_depth") or 0)
            field_annotations = _decode(field.get("annotations_json") or field.get("annotations"), [])
            exclusion_annotations = _decode(field.get("model_exclusion_annotations_json") or field.get("model_exclusion_annotations"), [])
            observed_ignore_annotations = sorted(
                {str(value).rsplit(".", 1)[-1] for value in field_annotations if str(value).rsplit(".", 1)[-1] == "MetaIgnore"}
            )
            exclusion_annotations = sorted({str(value) for value in exclusion_annotations} | set(observed_ignore_annotations))
            excluded = bool(field.get("model_exclusion_observed")) or bool(observed_ignore_annotations)
            target_fqcn, target_candidates = resolved_field_target(field)
            operations = operation_groups.get((source_object, field_name), [])
            if excluded:
                candidate_id = stable_id("model_relationship_candidate", source_object, field_id, "excluded_field")
                candidate_rows.append((candidate_id, source_repo, source_object, field_id, field_name, declaration_owner,
                    target_fqcn or str(field.get("element_type") or field.get("declared_type") or ""), "excluded_field_type_reference",
                    _json(target_candidates), True, _json(exclusion_annotations), _json(["code_field", "model_exclusion_annotation"]),
                    _json({"inherited": inherited, "inheritance_depth": depth})))
                continue
            if not target_fqcn and not target_candidates:
                continue
            if target_fqcn and _is_scalar_target(target_fqcn):
                continue

            if operations and not target_fqcn:
                operation_names = sorted({str(row["operation_name"]) for row in operations})
                operation_ids = sorted({str(row.get("call_id") or "") for row in operations if row.get("call_id")})
                candidate_id = stable_id("model_relationship_candidate", source_object, field_id, "converter_unresolved_target")
                candidate_rows.append((candidate_id, source_repo, source_object, field_id, field_name, declaration_owner,
                    str(field.get("element_type") or field.get("declared_type") or ""), "converter_relation_unresolved_target",
                    _json(target_candidates), False, _json(exclusion_annotations),
                    _json(["java_field_type", "converter_operation"]),
                    _json({"inherited": inherited, "inheritance_depth": depth, "converter_operations": operation_names,
                           "converter_operation_observation_ids": operation_ids})))
                continue

            if target_fqcn and target_fqcn in type_id_by_fqcn and target_fqcn not in visited_objects:
                classes_to_scan.append(target_fqcn)

            if operations:
                operation_names = {str(row["operation_name"]) for row in operations}
                if "replacePolymorphicReferenceCollection" in operation_names:
                    operation_name = "replacePolymorphicReferenceCollection"
                elif operation_names.intersection({"replaceReferenceCollection", "referenceCollection", "references"}):
                    operation_name = sorted(operation_names.intersection({"replaceReferenceCollection", "referenceCollection", "references"}))[0]
                elif "reference" in operation_names:
                    operation_name = "reference"
                else:
                    operation_name = "referenceField"
                relation_kind, cardinality = _REFERENCE_OPERATIONS[operation_name]
                relationship_id = stable_id("model_relationship", source_object, field_id, relation_kind, target_fqcn or _json(target_candidates))
                converter_owners = sorted({str(row.get("owner_fqcn") or "") for row in operations if row.get("owner_fqcn")})
                operation_ids = sorted({str(row.get("call_id") or "") for row in operations if row.get("call_id")})
                target_key_ids = sorted(key_ids_by_object.get(target_fqcn or "", []))
                relationship_rows.append((relationship_id, source_repo, source_object, type_id_by_fqcn.get(source_object),
                    _json(sorted(key_ids_by_object.get(source_object, []))), field_id, field_name, declaration_owner, inherited, depth,
                    type_repo_by_fqcn.get(target_fqcn or ""), target_fqcn or target_candidates[0], type_id_by_fqcn.get(target_fqcn or ""),
                    _json(target_key_ids), relation_kind, cardinality, field.get("container_kind"), operation_name,
                    _json(converter_owners), _json(operation_ids), _json(["java_field_type", "converter_operation"]),
                    _json({"target_candidates": target_candidates})))
                expression_seen: set[tuple[str, str, str, str]] = set()
                for operation in operations:
                    owner = str(operation.get("owner_fqcn") or "")
                    operation_observation_id = str(operation.get("call_id") or "")
                    for expr_row in source_key_expressions(owner, operation):
                        expression = str(expr_row.get("expression_text") or expr_row.get("expression") or "")
                        obs_id = str(expr_row.get("source_observation_occurrence_id") or expr_row.get("observation_id") or "")
                        marker = ("source", expression, obs_id, operation_observation_id)
                        if marker in expression_seen or not expression or not obs_id:
                            continue
                        expression_seen.add(marker)
                        key_expression_rows.append((stable_id("model_relationship_key_expression", relationship_id, *marker), relationship_id,
                            "source", expression, str(expr_row.get("repo_id") or source_repo), owner,
                            expr_row.get("owner_method"), obs_id, _json(_decode(expr_row.get("input_symbols_json"), [])),
                            _json({
                                "binding_kind": "same_converter_method_reference_operation",
                                "reference_operation_observation_id": operation_observation_id,
                                "source_object_fqcn": source_object,
                                "source_field_name": field_name,
                                "target_type_fqcn": target_fqcn,
                                "endpoint_key_observation_ids": sorted(key_ids_by_object.get(source_object, [])),
                            })))
                    nested = target_method_for_operation(operation, field_name)
                    for expr_row in target_key_expressions(owner, nested):
                        expression = str(expr_row.get("expression_text") or expr_row.get("expression") or "")
                        obs_id = str(expr_row.get("source_observation_occurrence_id") or expr_row.get("observation_id") or "")
                        marker = ("target", expression, obs_id, operation_observation_id)
                        if marker in expression_seen or not expression or not obs_id:
                            continue
                        expression_seen.add(marker)
                        key_expression_rows.append((stable_id("model_relationship_key_expression", relationship_id, *marker), relationship_id,
                            "target", expression, str(expr_row.get("repo_id") or source_repo), owner,
                            expr_row.get("owner_method"), obs_id, _json(_decode(expr_row.get("input_symbols_json"), [])),
                            _json({
                                "binding_kind": "nested_converter_method_reference_operation",
                                "reference_operation_observation_id": operation_observation_id,
                                "source_object_fqcn": source_object,
                                "source_field_name": field_name,
                                "target_type_fqcn": target_fqcn,
                                "endpoint_key_observation_ids": target_key_ids,
                                "nested_converter_method": nested,
                            })))
                    if operation_name == "replacePolymorphicReferenceCollection":
                        nested = target_method_for_operation(operation, field_name)
                        for call in method_calls_by_owner_method.get((owner, nested or ""), []):
                            text = str(call.get("expression_text") or call.get("call_text") or "")
                            for concrete in re.findall(r'"([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)+)"', text):
                                if concrete.startswith(("java.", "javax.")):
                                    continue
                                obs_id = str(call.get("source_observation_occurrence_id") or call.get("observation_id") or "")
                                polymorphic_rows.append((stable_id("model_relationship_polymorphic_target", relationship_id, concrete, obs_id),
                                    relationship_id, concrete, type_id_by_fqcn.get(concrete), str(call.get("repo_id") or source_repo), obs_id,
                                    _json({"converter_owner_fqcn": owner, "owner_method": nested})))
                continue

            if target_fqcn and target_fqcn in type_id_by_fqcn:
                cardinality = "many" if str(field.get("container_kind") or "") == "collection" else "one"
                if target_fqcn in root_model_objects:
                    relation_kind = "configured_object_collection" if cardinality == "many" else "configured_object_reference"
                    evidence_kinds = ["java_field_type", "configuration_type_correspondence"]
                else:
                    relation_kind = "owned_object_collection" if cardinality == "many" else "owned_object_reference"
                    evidence_kinds = ["java_field_type", "workspace_java_type"]
                relationship_id = stable_id("model_relationship", source_object, field_id, relation_kind, target_fqcn)
                relationship_rows.append((relationship_id, source_repo, source_object, type_id_by_fqcn.get(source_object),
                    _json(sorted(key_ids_by_object.get(source_object, []))), field_id, field_name, declaration_owner, inherited, depth,
                    type_repo_by_fqcn.get(target_fqcn), target_fqcn, type_id_by_fqcn.get(target_fqcn),
                    _json(sorted(key_ids_by_object.get(target_fqcn, []))), relation_kind, cardinality, field.get("container_kind"), None,
                    _json([]), _json([]), _json(evidence_kinds), _json({"target_is_registered_root": target_fqcn in root_model_objects})))
                continue

            candidate_id = stable_id("model_relationship_candidate", source_object, field_id, "unresolved_target")
            candidate_rows.append((candidate_id, source_repo, source_object, field_id, field_name, declaration_owner,
                target_fqcn or str(field.get("element_type") or field.get("declared_type") or ""), "unresolved_target_type",
                _json(target_candidates), False, _json(exclusion_annotations), _json(["java_field_type"]),
                _json({"inherited": inherited, "inheritance_depth": depth})))

    # Deterministically compact repeated POJO/JSON observations while preserving all evidence IDs.
    expression_groups: dict[tuple[str, str, str], list[tuple[Any, ...]]] = defaultdict(list)
    for row in key_expression_rows:
        expression_groups[(str(row[1]), str(row[2]), str(row[3]))].append(row)
    compact_expressions: list[tuple[Any, ...]] = []
    for (relationship_id, endpoint_role, expression_text), rows in sorted(expression_groups.items()):
        repos = sorted({str(row[4]) for row in rows if row[4]})
        owners = sorted({str(row[5]) for row in rows if row[5]})
        methods = sorted({str(row[6]) for row in rows if row[6]})
        observations = sorted({str(row[7]) for row in rows if row[7]})
        input_symbols: set[str] = set()
        payloads: list[Any] = []
        for row in rows:
            input_symbols.update(str(value) for value in _decode(row[8], []) if value)
            payload = _decode(row[9], {})
            if payload:
                payloads.append(payload)
        compact_expressions.append((
            stable_id("model_relationship_key_expression", relationship_id, endpoint_role, expression_text),
            relationship_id, endpoint_role, expression_text, _json(repos), _json(owners), _json(methods),
            _json(observations), _json(sorted(input_symbols)), _json({"observations": payloads}),
        ))

    polymorphic_groups: dict[tuple[str, str, str | None], list[tuple[Any, ...]]] = defaultdict(list)
    for row in polymorphic_rows:
        polymorphic_groups[(str(row[1]), str(row[2]), str(row[3]) if row[3] else None)].append(row)
    compact_polymorphic: list[tuple[Any, ...]] = []
    for (relationship_id, target_fqcn, target_type_id), rows in sorted(polymorphic_groups.items()):
        repos = sorted({str(row[4]) for row in rows if row[4]})
        observations = sorted({str(row[5]) for row in rows if row[5]})
        converter_owners: set[str] = set()
        owner_methods: set[str] = set()
        for row in rows:
            payload = _decode(row[6], {})
            if payload.get("converter_owner_fqcn"):
                converter_owners.add(str(payload["converter_owner_fqcn"]))
            if payload.get("owner_method"):
                owner_methods.add(str(payload["owner_method"]))
        compact_polymorphic.append((
            stable_id("model_relationship_polymorphic_target", relationship_id, target_fqcn),
            relationship_id, target_fqcn, target_type_id, _json(repos), _json(observations),
            _json({"converter_owner_fqcns": sorted(converter_owners), "owner_methods": sorted(owner_methods)}),
        ))

    def unique(rows: list[tuple[Any, ...]]) -> list[tuple[Any, ...]]:
        return [row for _, row in sorted({str(row[0]): row for row in rows}.items())]
    return unique(relationship_rows), compact_expressions, compact_polymorphic, unique(embedded_rows), unique(candidate_rows)
