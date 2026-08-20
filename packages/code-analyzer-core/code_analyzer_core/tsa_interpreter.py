from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from collections import defaultdict
from typing import Any, Iterable

from code_analyzer_core.models import Fact

_TSA_ANNOTATIONS = {
    "MetaRootEntity",
    "MetaVersionedEntity",
    "MetaEntity",
    "MetaDictionary",
    "MetaVersionedDictionary",
    "MetaVersion",
    "MetaEmbedded",
    "MetaReference",
    "MetaIgnore",
}
_DEFAULT_API_ROLES: dict[str, Any] = {
    "framework": "tsa_change_vector",
    "reference_methods": {
        "referenceField": {"kind": "field", "field_argument": 0, "value_argument": 1},
        "referenceCollection": {"kind": "collection", "field_argument": 0, "value_argument": 1},
        "replaceReferenceCollection": {"kind": "collection", "field_argument": 0, "value_argument": 1},
        "replacePolymorphicReferenceCollection": {"kind": "collection", "field_argument": 0, "value_argument": 1},
        "reference": {"kind": "field", "field_argument": 0, "value_argument": 1},
        "references": {"kind": "collection", "field_argument": 0, "value_argument": 1},
    },
    "record_key_methods": {
        "key": {"value_argument": 0, "storage_field": "key"},
        "setKey": {"value_argument": 0, "storage_field": "key"},
        "withKey": {"value_argument": 0, "storage_field": "key"},
    },
    "record_alias_methods": {
        "alias": {"value_argument": 0},
        "setAlias": {"value_argument": 0},
        "withAlias": {"value_argument": 0},
    },
}


def _normalize_api_roles(api_roles: dict[str, Any] | None) -> dict[str, Any]:
    source = deepcopy(api_roles or _DEFAULT_API_ROLES)
    normalized = {
        "framework": str(source.get("framework") or "external_builder_api"),
        "reference_methods": dict(source.get("reference_methods") or {}),
        "record_key_methods": dict(source.get("record_key_methods") or {}),
        "record_alias_methods": dict(source.get("record_alias_methods") or {}),
    }
    return normalized



def _stable_id(*parts: Any) -> str:
    raw = "|".join(json.dumps(part, sort_keys=True, ensure_ascii=False, default=str) for part in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _evidence_union(*facts: Fact) -> list:
    seen: set[tuple[Any, ...]] = set()
    output = []
    for fact in facts:
        for ref in fact.evidence:
            key = (ref.file_path, ref.line_start, ref.line_end, ref.extractor, ref.snippet)
            if key not in seen:
                seen.add(key)
                output.append(ref)
    return output


def _configuration_family(path: str) -> str | None:
    if re.search(r"(?:^|\.)pojoConverters\.types\[\d+\]$", path):
        return "pojo_converter_registration"
    if re.search(r"(?:^|\.)jsonConverters\.types\[\d+\]$", path):
        return "json_converter_registration"
    if re.search(r"(?:^|\.)jsonDictionaryConverters\.types\[\d+\]$", path):
        return "json_dictionary_converter_registration"
    return None


def _string_literal(expression: Any) -> str | None:
    value = str(expression or "").strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return None


def _tree_identifier(tree: dict[str, Any] | None) -> str | None:
    node = dict(tree or {})
    if node.get("node_type") == "identifier":
        return str(node.get("value") or node.get("text") or "").strip() or None
    return None


def _render_expression_tree(tree: dict[str, Any] | None) -> str:
    node = dict(tree or {})
    node_type = str(node.get("node_type") or "")
    if not node:
        return ""
    if node_type == "bound_expression":
        binding_tree = dict(node.get("binding_tree") or {})
        rendered = _render_expression_tree(binding_tree)
        if binding_tree.get("node_type") in {
            "identifier", "string_literal", "character_literal", "null_literal",
            "decimal_integer_literal", "decimal_floating_point_literal", "method_invocation",
        }:
            return rendered
        return f"({rendered})" if rendered else str(node.get("binding_expression") or "")
    if node_type in {
        "identifier", "string_literal", "character_literal", "null_literal",
        "decimal_integer_literal", "decimal_floating_point_literal", "true", "false",
    }:
        return str(node.get("value") or node.get("text") or "")
    if node_type == "binary_expression":
        children = list(node.get("children") or [])
        left = next((child for child in children if child.get("field") == "left"), children[0] if children else {})
        operator = next((child for child in children if child.get("field") == "operator"), {})
        right = next((child for child in children if child.get("field") == "right"), children[-1] if children else {})
        op = str(operator.get("value") or node.get("operator") or "")
        return f"{_render_expression_tree(left)} {op} {_render_expression_tree(right)}".strip()
    if node_type == "parenthesized_expression":
        children = list(node.get("children") or [])
        return f"({_render_expression_tree(children[0] if children else {})})"
    if node_type == "ternary_expression":
        children = list(node.get("children") or [])
        condition = next((child for child in children if child.get("field") == "condition"), children[0] if children else {})
        consequence = next((child for child in children if child.get("field") == "consequence"), children[1] if len(children) > 1 else {})
        alternative = next((child for child in children if child.get("field") == "alternative"), children[-1] if children else {})
        return f"{_render_expression_tree(condition)} ? {_render_expression_tree(consequence)} : {_render_expression_tree(alternative)}"
    if node_type == "method_invocation":
        children = list(node.get("children") or [])
        obj = next((child for child in children if child.get("field") == "object"), None)
        name = next((child for child in children if child.get("field") == "name"), None)
        args = next((child for child in children if child.get("field") == "arguments"), None)
        prefix = f"{_render_expression_tree(obj)}." if obj else ""
        return f"{prefix}{_render_expression_tree(name)}{_render_expression_tree(args)}"
    if node_type == "argument_list":
        if node.get("value") is not None:
            return str(node.get("value"))
        rendered = [_render_expression_tree(child) for child in node.get("children") or []]
        return f"({', '.join(item for item in rendered if item)})"
    if node_type == "method_reference":
        rendered = [_render_expression_tree(child) for child in node.get("children") or []]
        return "::".join(item for item in rendered if item)
    if node.get("text"):
        return str(node.get("text"))
    if node.get("value") is not None:
        return str(node.get("value"))
    return " ".join(filter(None, (_render_expression_tree(child) for child in node.get("children") or [])))


def _substitute_expression_tree(
    tree: dict[str, Any] | None,
    bindings: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    node = deepcopy(dict(tree or {}))
    identifier = _tree_identifier(node)
    if identifier and identifier in bindings:
        binding = bindings[identifier]
        replacement = {
            "node_type": "bound_expression",
            "parameter": identifier,
            "binding_expression": binding.get("expression"),
            "binding_tree": deepcopy(binding.get("expression_tree") or {}),
            "binding_source_operation": binding.get("source_operation"),
            "binding_call_observation_id": binding.get("call_observation_id"),
        }
        if node.get("field") is not None:
            replacement["field"] = node.get("field")
        return replacement
    if isinstance(node.get("children"), list):
        node["children"] = [
            _substitute_expression_tree(child, bindings) if isinstance(child, dict) else child
            for child in node.get("children") or []
        ]
    return node


def _collect_input_symbols(tree: dict[str, Any] | None) -> list[str]:
    symbols: list[str] = []

    def walk(node: dict[str, Any]) -> None:
        if node.get("node_type") == "bound_expression":
            walk(dict(node.get("binding_tree") or {}))
            return
        if node.get("node_type") == "identifier":
            value = str(node.get("value") or node.get("text") or "").strip()
            if value and value not in symbols:
                symbols.append(value)
        for child in node.get("children") or []:
            if isinstance(child, dict):
                walk(child)

    walk(dict(tree or {}))
    return symbols


def _int_property(properties: dict[str, Any], name: str) -> int | None:
    value = properties.get(name)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _scope_contains(properties: dict[str, Any], *, prefix: str, use_position: int | None) -> bool:
    if use_position is None:
        return True
    start = _int_property(properties, f"{prefix}scope_start_byte")
    end = _int_property(properties, f"{prefix}scope_end_byte")
    if start is None or end is None:
        return True
    return start <= use_position <= end


def _select_visible_fact(
    candidates: list[Fact],
    *,
    use_position: int | None,
    assignment_prefix: str,
) -> tuple[Fact | None, str]:
    """Choose the nearest dominating assignment visible at a source use.

    Tree-sitter supplies lexical scope and byte positions.  Candidates outside
    the use scope or after the use are rejected.  Equal-ranked candidates remain
    unresolved rather than being guessed.
    """
    if not candidates:
        return None, "no_candidates"
    if use_position is None:
        return (candidates[0], "single_candidate_without_position") if len(candidates) == 1 else (None, "missing_use_position")
    visible: list[Fact] = []
    for candidate in candidates:
        props = candidate.properties
        assignment_start = _int_property(props, f"{assignment_prefix}assignment_start_byte")
        if assignment_start is None:
            assignment_start = _int_property(props, "source_start_byte")
        if assignment_start is not None and assignment_start > use_position:
            continue
        if not _scope_contains(props, prefix=assignment_prefix, use_position=use_position):
            continue
        visible.append(candidate)
    if not visible:
        return None, "no_visible_dominating_candidate"
    def rank(item: Fact) -> tuple[int, int]:
        props = item.properties
        depth = _int_property(props, f"{assignment_prefix}scope_depth")
        if depth is None:
            depth = _int_property(props, "lexical_scope_depth") or 0
        start = _int_property(props, f"{assignment_prefix}assignment_start_byte")
        if start is None:
            start = _int_property(props, "source_start_byte") or -1
        return depth, start
    visible.sort(key=rank, reverse=True)
    best_rank = rank(visible[0])
    best = [item for item in visible if rank(item) == best_rank]
    if len(best) != 1:
        return None, "ambiguous_equal_rank_candidates"
    return best[0], "nearest_visible_dominating_assignment"


def _resolved_local_expression(
    *,
    operation: str,
    expression: Any,
    expression_tree: dict[str, Any] | None,
    constructed_by_operation_variable: dict[tuple[str, str], list[Fact]],
    use_position: int | None = None,
) -> dict[str, Any]:
    raw = str(expression or "").strip()
    tree = dict(expression_tree or {})
    identifier = _tree_identifier(tree)
    if identifier:
        candidates = constructed_by_operation_variable.get((operation, identifier), [])
        candidate, resolution = _select_visible_fact(
            candidates,
            use_position=use_position,
            assignment_prefix="lexical_",
        )
        if candidate is not None:
            props = candidate.properties
            return {
                "expression": props.get("expression"),
                "expression_tree": dict(props.get("expression_tree") or {}),
                "input_symbols": list(props.get("input_symbols") or []),
                "source_observation_id": props.get("observation_id"),
                "resolved_from_local_variable": identifier,
                "resolution": resolution,
                "fact": candidate,
            }
    return {
        "expression": raw or None,
        "expression_tree": tree,
        "input_symbols": _collect_input_symbols(tree),
        "source_observation_id": None,
        "resolved_from_local_variable": None,
        "resolution": "unresolved_or_non_identifier",
        "fact": None,
    }


def interpret_tsa_facts(
    facts: Iterable[Fact],
    *,
    api_roles: dict[str, Any] | None = None,
) -> tuple[list[Fact], dict[str, Any]]:
    """Publish TSA-specific technical observations over generic extracted facts.

    The interpreter recognizes TSA vocabulary and configuration structure, but it
    does not assert physical tables, PK/FK semantics, joinability, confidence, or
    business meaning.
    """
    source = list(facts)
    roles = _normalize_api_roles(api_roles)
    reference_method_roles = roles["reference_methods"]
    key_method_roles = roles["record_key_methods"]
    alias_method_roles = roles["record_alias_methods"]
    emitted: list[Fact] = []
    counts: defaultdict[str, int] = defaultdict(int)

    arguments_by_call: defaultdict[str, list[Fact]] = defaultdict(list)
    calls_by_id: dict[str, Fact] = {}
    parameter_bindings_by_call: defaultdict[str, list[Fact]] = defaultdict(list)
    parameter_bindings_by_caller: defaultdict[str, list[Fact]] = defaultdict(list)
    result_bindings_by_parent_call: defaultdict[str, list[Fact]] = defaultdict(list)
    result_bindings_by_caller_variable: defaultdict[tuple[str, str], list[Fact]] = defaultdict(list)
    constructed_by_operation_variable: defaultdict[tuple[str, str], list[Fact]] = defaultdict(list)
    return_values_by_operation: defaultdict[str, list[Fact]] = defaultdict(list)
    aliases_by_operation: defaultdict[str, list[tuple[str, Fact]]] = defaultdict(list)
    for fact in source:
        if fact.fact_type == "call_argument_flow_observation":
            call_id = str(fact.properties.get("call_observation_id") or "")
            if call_id:
                arguments_by_call[call_id].append(fact)
        elif fact.fact_type == "java_method_call_observation":
            call_id = str(fact.properties.get("observation_id") or "")
            if call_id:
                calls_by_id[call_id] = fact
        elif fact.fact_type == "java_call_parameter_binding_observation":
            call_id = str(fact.properties.get("call_observation_id") or "")
            caller_operation = str(fact.properties.get("caller_operation") or "")
            if call_id:
                parameter_bindings_by_call[call_id].append(fact)
            if caller_operation:
                parameter_bindings_by_caller[caller_operation].append(fact)
        elif fact.fact_type == "java_call_result_binding_observation":
            parent_call_id = str(fact.properties.get("parent_call_observation_id") or "")
            if parent_call_id:
                result_bindings_by_parent_call[parent_call_id].append(fact)
            caller_operation = str(fact.properties.get("caller_operation") or "")
            target_variable = str(fact.properties.get("target_variable") or "")
            if caller_operation and target_variable:
                result_bindings_by_caller_variable[(caller_operation, target_variable)].append(fact)
        elif fact.fact_type == "constructed_value_observation":
            p = fact.properties
            operation = str(p.get("owner_operation") or "")
            variable = str(p.get("target_variable") or "")
            if operation and variable:
                constructed_by_operation_variable[(operation, variable)].append(fact)
            if operation and (p.get("target_kind") == "return_value" or p.get("assignment_kind") == "return_statement"):
                return_values_by_operation[operation].append(fact)

    key_observations: list[Fact] = []
    reference_observations: list[Fact] = []

    for fact in source:
        p = fact.properties
        if fact.fact_type == "code_annotation" and str(p.get("annotation") or "") in _TSA_ANNOTATIONS:
            annotation = str(p.get("annotation"))
            kind = "tsa_meta_annotation"
            emitted.append(Fact(
                fact_type="tsa_annotation_observation",
                name=f"{annotation}:{p.get('owner_fqcn') or fact.name}",
                properties={
                    "observation_id": _stable_id(kind, p.get("observation_id"), annotation),
                    "tsa_observation_kind": kind,
                    "annotation": annotation,
                    "annotation_fqcn": p.get("annotation_fqcn"),
                    "annotation_resolution": p.get("annotation_resolution"),
                    "owner_kind": p.get("owner_kind"),
                    "owner_fqcn": p.get("owner_fqcn"),
                    "member_name": p.get("member_name"),
                    "arguments": p.get("arguments") or {},
                    "source_observation_id": p.get("observation_id"),
                    "observation_policy": "TSA annotation occurrence only; no storage or entity verdict",
                },
                evidence=list(fact.evidence),
            ))
            counts[kind] += 1

        if fact.fact_type == "configuration_object_observation":
            path = str(p.get("configuration_path") or "")
            family = _configuration_family(path)
            fields = dict(p.get("scalar_fields") or {})
            class_name = fields.get("className")
            if family and class_name:
                emitted.append(Fact(
                    fact_type="tsa_converter_configuration_observation",
                    name=f"{family}:{class_name}",
                    properties={
                        "observation_id": _stable_id("tsa_registration", p.get("observation_id"), class_name),
                        "tsa_observation_kind": family,
                        "configuration_path": path,
                        "configured_class_name": class_name,
                        "scalar_fields": fields,
                        "source_observation_id": p.get("observation_id"),
                        "observation_policy": "converter configuration occurrence only; no generated-table verdict",
                    },
                    evidence=list(fact.evidence),
                ))
                counts[family] += 1

        if fact.fact_type == "configuration_entry":
            path = str(p.get("configuration_path") or "")
            value = p.get("value")
            kind = None
            if re.search(r"(?:^|\.)(?:whitelist\.)?excludedFields\[\d+\]$", path):
                kind = "excluded_field"
            elif re.search(r"(?:^|\.)(?:whitelist\.)?excludedTypes\[\d+\]$", path):
                kind = "excluded_type"
            elif re.search(r"(?:^|\.)customFields\[\d+\]\.(?:source|target)$", path):
                kind = "custom_field_mapping_endpoint"
            elif re.search(r"customPrimitiveConvertors\[\d+\]\.(?:sourceField|targetField|converterClass)$", path):
                kind = "custom_primitive_converter_endpoint"
            if kind:
                emitted.append(Fact(
                    fact_type="tsa_configuration_directive_observation",
                    name=f"{kind}:{value}",
                    properties={
                        "observation_id": _stable_id("tsa_config_directive", p.get("observation_id"), path, value),
                        "tsa_observation_kind": kind,
                        "configuration_path": path,
                        "value": value,
                        "scalar_shape": p.get("scalar_shape"),
                        "source_observation_id": p.get("observation_id"),
                        "observation_policy": "configuration directive occurrence only; no semantic mapping or exclusion verdict",
                    },
                    evidence=list(fact.evidence),
                ))
                counts[kind] += 1

        if fact.fact_type == "java_method_call_observation":
            method = str(p.get("method") or p.get("method_name") or "")
            call_id = str(p.get("observation_id") or "")
            args = sorted(arguments_by_call.get(call_id, []), key=lambda x: int(x.properties.get("argument_index") or 0))
            if method in reference_method_roles:
                method_role = dict(reference_method_roles.get(method) or {})
                kind = "reference_collection_call" if method_role.get("kind") == "collection" else "reference_field_call"
                field_argument_index = int(method_role.get("field_argument", 0))
                value_argument_index = int(method_role.get("value_argument", 1))
                observation = Fact(
                    fact_type="tsa_reference_operation_observation",
                    name=f"{p.get('owner_fqcn')}:{method}",
                    properties={
                        "observation_id": _stable_id("tsa_reference", call_id, method),
                        "tsa_observation_kind": kind,
                        "owner_fqcn": p.get("owner_fqcn"),
                        "owner_operation": p.get("owner_operation"),
                        "receiver_expression": p.get("receiver_expression"),
                        "method": method,
                        "api_framework": roles["framework"],
                        "field_argument_index": field_argument_index,
                        "value_argument_index": value_argument_index,
                        "call_observation_id": call_id,
                        "call_start_byte": p.get("call_start_byte"),
                        "call_end_byte": p.get("call_end_byte"),
                        "lexical_scope_start_byte": p.get("lexical_scope_start_byte"),
                        "lexical_scope_end_byte": p.get("lexical_scope_end_byte"),
                        "lexical_scope_depth": p.get("lexical_scope_depth"),
                        "argument_expressions": [a.properties.get("source_expression") for a in args],
                        "argument_input_symbols": [a.properties.get("input_symbols") or [] for a in args],
                        "argument_expression_trees": [a.properties.get("expression_tree") or {} for a in args],
                        "nested_call_observation_ids": p.get("nested_call_observation_ids") or [],
                        "observation_policy": "observed TSA reference API call only; no FK, cardinality, or join verdict",
                    },
                    evidence=_evidence_union(fact, *args),
                )
                emitted.append(observation)
                reference_observations.append(observation)
                counts[kind] += 1
            if method in key_method_roles:
                method_role = dict(key_method_roles.get(method) or {})
                value_argument_index = int(method_role.get("value_argument", 0))
                value_argument = args[value_argument_index] if len(args) > value_argument_index else None
                resolved = _resolved_local_expression(
                    operation=str(p.get("owner_operation") or ""),
                    expression=value_argument.properties.get("source_expression") if value_argument else None,
                    expression_tree=value_argument.properties.get("expression_tree") if value_argument else {},
                    constructed_by_operation_variable=constructed_by_operation_variable,
                    use_position=_int_property(p, "call_start_byte"),
                )
                observation = Fact(
                    fact_type="tsa_key_expression_observation",
                    name=f"{p.get('owner_fqcn')}:{method}",
                    properties={
                        "observation_id": _stable_id("tsa_key_expression", call_id, method),
                        "tsa_observation_kind": "key_assignment_call",
                        "owner_fqcn": p.get("owner_fqcn"),
                        "owner_operation": p.get("owner_operation"),
                        "receiver_expression": p.get("receiver_expression"),
                        "method": method,
                        "api_framework": roles["framework"],
                        "value_argument_index": value_argument_index,
                        "storage_field": method_role.get("storage_field") or method,
                        "call_observation_id": call_id,
                        "call_start_byte": p.get("call_start_byte"),
                        "call_end_byte": p.get("call_end_byte"),
                        "lexical_scope_start_byte": p.get("lexical_scope_start_byte"),
                        "lexical_scope_end_byte": p.get("lexical_scope_end_byte"),
                        "lexical_scope_depth": p.get("lexical_scope_depth"),
                        "key_expression": value_argument.properties.get("source_expression") if value_argument else None,
                        "input_symbols": value_argument.properties.get("input_symbols") if value_argument else [],
                        "expression_tree": value_argument.properties.get("expression_tree") if value_argument else {},
                        "resolved_key_expression": resolved.get("expression"),
                        "resolved_input_symbols": resolved.get("input_symbols") or [],
                        "resolved_expression_tree": resolved.get("expression_tree") or {},
                        "resolved_from_local_variable": resolved.get("resolved_from_local_variable"),
                        "local_resolution": resolved.get("resolution"),
                        "resolved_source_observation_id": resolved.get("source_observation_id"),
                        "observation_policy": "observed key-argument expression only; no PK or uniqueness verdict",
                    },
                    evidence=_evidence_union(fact, *([value_argument] if value_argument else []), *([resolved["fact"]] if resolved.get("fact") else [])),
                )
                emitted.append(observation)
                key_observations.append(observation)
                counts["key_assignment_call"] += 1
            if method in alias_method_roles and args:
                method_role = dict(alias_method_roles.get(method) or {})
                value_argument_index = int(method_role.get("value_argument", 0))
                alias_argument = args[value_argument_index] if len(args) > value_argument_index else None
                alias_value = _string_literal(alias_argument.properties.get("source_expression") if alias_argument else None)
                operation = str(p.get("owner_operation") or "")
                if operation and alias_value:
                    alias_observation = Fact(
                        fact_type="storage_alias_assignment_observation",
                        name=f"{p.get('owner_fqcn')}:{method}",
                        properties={
                            "observation_id": _stable_id("storage_alias_assignment", call_id, method),
                            "observation_kind": "storage_record_alias_assignment",
                            "api_framework": roles["framework"],
                            "owner_fqcn": p.get("owner_fqcn"),
                            "owner_operation": operation,
                            "receiver_expression": p.get("receiver_expression"),
                            "method": method,
                            "call_observation_id": call_id,
                            "alias_expression": alias_argument.properties.get("source_expression") if alias_argument else None,
                            "alias_value": alias_value,
                            "observation_policy": "observed builder alias assignment only; no physical normalization or table-name verdict",
                        },
                        evidence=_evidence_union(fact, *([alias_argument] if alias_argument else [])),
                    )
                    emitted.append(alias_observation)
                    aliases_by_operation[operation].append((alias_value, alias_observation))
                    counts["storage_record_alias_assignment"] += 1

    keys_by_operation: defaultdict[str, list[Fact]] = defaultdict(list)
    for key_observation in key_observations:
        operation = str(key_observation.properties.get("owner_operation") or "")
        if operation:
            keys_by_operation[operation].append(key_observation)

    storage_records_by_operation: defaultdict[str, list[Fact]] = defaultdict(list)
    for operation, operation_keys in keys_by_operation.items():
        operation_aliases = aliases_by_operation.get(operation, [])
        for key_observation in operation_keys:
            kp = key_observation.properties
            receiver = str(kp.get("receiver_expression") or "").strip()
            alias_candidates = [
                (alias_value, alias_fact)
                for alias_value, alias_fact in operation_aliases
                if str(alias_fact.properties.get("receiver_expression") or "").strip() == receiver
            ]
            if len(alias_candidates) != 1:
                continue
            alias_value, alias_fact = alias_candidates[0]
            record = Fact(
                fact_type="storage_record_observation",
                name=f"{operation}:{receiver or '<builder>'}",
                properties={
                    "observation_id": _stable_id(
                        "storage_record",
                        kp.get("observation_id"),
                        alias_fact.properties.get("observation_id"),
                    ),
                    "observation_kind": "builder_storage_record",
                    "api_framework": roles["framework"],
                    "owner_fqcn": kp.get("owner_fqcn"),
                    "owner_operation": operation,
                    "builder_receiver_expression": receiver or None,
                    "storage_key_field": kp.get("storage_field") or "key",
                    "storage_key_expression": kp.get("resolved_key_expression") or kp.get("key_expression"),
                    "storage_key_expression_tree": kp.get("resolved_expression_tree") or kp.get("expression_tree") or {},
                    "storage_key_input_symbols": kp.get("resolved_input_symbols") or kp.get("input_symbols") or [],
                    "storage_key_local_variable": kp.get("resolved_from_local_variable"),
                    "storage_key_source_observation_id": kp.get("resolved_source_observation_id"),
                    "storage_alias": alias_value,
                    "storage_alias_expression": alias_fact.properties.get("alias_expression"),
                    "key_assignment_observation_id": kp.get("observation_id"),
                    "alias_assignment_observation_id": alias_fact.properties.get("observation_id"),
                    "physical_reference_encoding": "downstream_interpretation_required",
                    "observation_policy": "same builder receiver has observed alias and storage-key assignments; no alias normalization, separator, SQL, or physical-table verdict",
                },
                evidence=_evidence_union(key_observation, alias_fact),
            )
            emitted.append(record)
            storage_records_by_operation[operation].append(record)
            counts["builder_storage_record"] += 1

    def expression_payload(binding: Fact, *, source_operation: str) -> dict[str, Any]:
        props = binding.properties
        resolved = _resolved_local_expression(
            operation=source_operation,
            expression=props.get("caller_expression"),
            expression_tree=props.get("caller_expression_tree") or {},
            constructed_by_operation_variable=constructed_by_operation_variable,
            use_position=_int_property(props, "call_start_byte"),
        )
        return {
            "expression": resolved.get("expression"),
            "expression_tree": resolved.get("expression_tree") or {},
            "input_symbols": resolved.get("input_symbols") or [],
            "source_operation": source_operation,
            "call_observation_id": props.get("call_observation_id"),
            "source_observation_id": resolved.get("source_observation_id") or props.get("observation_id"),
            "resolved_from_local_variable": resolved.get("resolved_from_local_variable"),
            "fact": resolved.get("fact") or binding,
        }

    def propagate_environment(
        call_id: str,
        caller_operation: str,
        caller_environment: dict[str, dict[str, Any]],
    ) -> tuple[str | None, dict[str, dict[str, Any]], list[dict[str, Any]], list[Fact]]:
        bindings = sorted(
            parameter_bindings_by_call.get(call_id, []),
            key=lambda item: int(item.properties.get("argument_index") or 0),
        )
        if not bindings:
            return None, {}, [], []
        callee_operation = str(bindings[0].properties.get("callee_operation") or "") or None
        environment: dict[str, dict[str, Any]] = {}
        path_rows: list[dict[str, Any]] = []
        evidence_facts: list[Fact] = []
        for binding in bindings:
            props = binding.properties
            parameter = str(props.get("callee_parameter") or "")
            if not parameter:
                continue
            payload = expression_payload(binding, source_operation=caller_operation)
            caller_identifier = _tree_identifier(props.get("caller_expression_tree") or {})
            inherited = caller_environment.get(caller_identifier or "", {}) if caller_identifier else {}
            substituted_tree = _substitute_expression_tree(payload.get("expression_tree") or {}, caller_environment)
            substituted_expression = _render_expression_tree(substituted_tree) or payload.get("expression")
            environment[parameter] = {
                **payload,
                "expression": substituted_expression,
                "expression_tree": substituted_tree,
                "origin_source_observation_id": inherited.get("origin_source_observation_id") or inherited.get("source_observation_id") or payload.get("source_observation_id"),
                "origin_resolved_from_local_variable": inherited.get("origin_resolved_from_local_variable") or inherited.get("resolved_from_local_variable") or payload.get("resolved_from_local_variable"),
            }
            path_rows.append({
                "call_observation_id": props.get("call_observation_id"),
                "caller_operation": caller_operation,
                "callee_operation": props.get("callee_operation"),
                "callee_parameter": parameter,
                "caller_expression": props.get("caller_expression"),
                "resolved_expression": substituted_expression,
                "resolution": props.get("resolution"),
            })
            evidence_facts.extend([binding, payload.get("fact")])
        return callee_operation, environment, path_rows, [fact for fact in evidence_facts if isinstance(fact, Fact)]

    for reference in reference_observations:
        rp = reference.properties
        if rp.get("tsa_observation_kind") != "reference_field_call":
            continue
        reference_call_id = str(rp.get("call_observation_id") or "")
        reference_args = list(rp.get("argument_expressions") or [])
        reference_trees = list(rp.get("argument_expression_trees") or [])
        field_argument_index = int(rp.get("field_argument_index") or 0)
        value_argument_index = int(rp.get("value_argument_index") or 1)
        relationship_expression = reference_args[field_argument_index] if len(reference_args) > field_argument_index else None
        relationship_name = _string_literal(relationship_expression)
        owner_operation = str(rp.get("owner_operation") or "")
        if len(reference_args) <= max(field_argument_index, value_argument_index) or not owner_operation:
            continue

        result_bindings = [
            item for item in result_bindings_by_parent_call.get(reference_call_id, [])
            if int(item.properties.get("parent_argument_index") or -1) == value_argument_index
        ]
        binding_resolution = "nested_call_argument"
        if not result_bindings:
            value_identifier = _tree_identifier(reference_trees[value_argument_index] if len(reference_trees) > value_argument_index else {})
            if value_identifier:
                candidates = result_bindings_by_caller_variable.get(
                    (owner_operation, value_identifier),
                    [],
                )
                selected, binding_resolution = _select_visible_fact(
                    candidates,
                    use_position=_int_property(rp, "call_start_byte"),
                    assignment_prefix="target_",
                )
                result_bindings = [selected] if selected is not None else []
        if len(result_bindings) != 1:
            continue
        result_binding = result_bindings[0]
        converter_call_id = str(result_binding.properties.get("call_observation_id") or "")
        converter_operation, environment, binding_path, binding_evidence = propagate_environment(
            converter_call_id,
            owner_operation,
            {},
        )
        if not converter_operation:
            continue
        return_values = return_values_by_operation.get(converter_operation, [])
        source_aliases = aliases_by_operation.get(owner_operation, [])
        for return_value in return_values:
            vp = return_value.properties
            template_tree = dict(vp.get("expression_tree") or {})
            template_expression = str(vp.get("expression") or "")
            if template_tree.get("node_type") == "null_literal" or template_expression.strip() == "null":
                continue
            composed_tree = _substitute_expression_tree(template_tree, environment)
            composed_expression = _render_expression_tree(composed_tree)
            if not composed_expression:
                continue
            parameter_bindings = [
                {
                    "parameter": parameter,
                    "resolved_expression": payload.get("expression"),
                    "source_observation_id": payload.get("source_observation_id"),
                }
                for parameter, payload in sorted(environment.items())
            ]
            evidence_facts = [reference, result_binding, return_value, *binding_evidence]
            evidence_facts.extend(fact for _, fact in source_aliases)
            derivation = Fact(
                fact_type="tsa_reference_value_derivation_observation",
                name=f"{owner_operation}:{relationship_name or relationship_expression}->{converter_operation}",
                properties={
                    "observation_id": _stable_id(
                        "tsa_reference_value_derivation",
                        reference_call_id,
                        result_binding.properties.get("observation_id"),
                        vp.get("observation_id"),
                        parameter_bindings,
                    ),
                    "tsa_observation_kind": "reference_field_value_derivation",
                    "source_owner_fqcn": rp.get("owner_fqcn"),
                    "source_operation": owner_operation,
                    "source_alias": source_aliases[0][0] if len(source_aliases) == 1 else None,
                    "relationship_field_expression": relationship_expression,
                    "relationship_field": relationship_name,
                    "reference_operation": rp.get("method"),
                    "reference_call_observation_id": reference_call_id,
                    "reference_value_expression": reference_args[value_argument_index],
                    "reference_value_binding_resolution": binding_resolution,
                    "value_converter_operation": converter_operation,
                    "value_converter_call_observation_id": converter_call_id,
                    "return_expression_template": template_expression,
                    "return_expression_template_tree": template_tree,
                    "composed_reference_value_expression": composed_expression,
                    "composed_reference_value_expression_tree": composed_tree,
                    "composed_reference_value_input_symbols": _collect_input_symbols(composed_tree),
                    "value_converter_parameter_bindings": parameter_bindings,
                    "binding_path": binding_path,
                    "observation_policy": "observed TSA referenceField value plus exact Java call/return bindings only; no target-key equivalence, SQL, FK, or join verdict",
                },
                evidence=_evidence_union(*[fact for fact in evidence_facts if isinstance(fact, Fact)]),
            )
            emitted.append(derivation)
            counts["reference_field_value_derivation"] += 1

            return_identifier = _tree_identifier(template_tree)
            storage_candidates = []
            for candidate in storage_records_by_operation.get(converter_operation, []):
                cp = candidate.properties
                candidate_expression = str(cp.get("storage_key_expression") or "").strip()
                local_variable = str(cp.get("storage_key_local_variable") or "").strip()
                if return_identifier and local_variable == return_identifier:
                    storage_candidates.append(candidate)
                elif template_expression.strip() and candidate_expression == template_expression.strip():
                    storage_candidates.append(candidate)
            unique_storage_candidates = {
                str(item.properties.get("observation_id") or id(item)): item
                for item in storage_candidates
            }
            if len(unique_storage_candidates) == 1:
                storage_record = next(iter(unique_storage_candidates.values()))
                sp = storage_record.properties
                storage_reference = Fact(
                    fact_type="storage_reference_observation",
                    name=f"{owner_operation}:{relationship_name or relationship_expression}->{converter_operation}",
                    properties={
                        "observation_id": _stable_id(
                            "storage_reference",
                            derivation.properties.get("observation_id"),
                            sp.get("observation_id"),
                        ),
                        "observation_kind": "reference_value_from_target_storage_record",
                        "api_framework": roles["framework"],
                        "source_owner_fqcn": rp.get("owner_fqcn"),
                        "source_operation": owner_operation,
                        "source_alias": source_aliases[0][0] if len(source_aliases) == 1 else None,
                        "source_field_expression": relationship_expression,
                        "source_field": relationship_name,
                        "reference_operation": rp.get("method"),
                        "reference_call_observation_id": reference_call_id,
                        "reference_value_expression": reference_args[value_argument_index],
                        "reference_value_binding_resolution": binding_resolution,
                        "target_converter_operation": converter_operation,
                        "target_storage_record_observation_id": sp.get("observation_id"),
                        "target_alias": sp.get("storage_alias"),
                        "target_storage_key_field": sp.get("storage_key_field"),
                        "target_storage_key_expression": sp.get("storage_key_expression"),
                        "target_storage_key_expression_tree": sp.get("storage_key_expression_tree") or {},
                        "target_storage_key_input_symbols": sp.get("storage_key_input_symbols") or [],
                        "target_storage_key_local_variable": sp.get("storage_key_local_variable"),
                        "value_origin": "returned_target_storage_key",
                        "type_source": "target_storage_record.alias",
                        "key_source": "target_storage_record.storage_key",
                        "physical_encoding": "downstream_interpretation_required",
                        "binding_path": binding_path,
                        "observation_policy": "exact call-result/return/key/alias evidence only; downstream may interpret physical encoding, but core adds no separator, normalization, SQL, or join verdict",
                    },
                    evidence=_evidence_union(derivation, storage_record),
                )
                emitted.append(storage_reference)
                counts["reference_value_from_target_storage_record"] += 1

    for reference in reference_observations:
        rp = reference.properties
        if rp.get("tsa_observation_kind") != "reference_collection_call":
            continue
        reference_call_id = str(rp.get("call_observation_id") or "")
        reference_args = list(rp.get("argument_expressions") or [])
        field_argument_index = int(rp.get("field_argument_index") or 0)
        value_argument_index = int(rp.get("value_argument_index") or 1)
        relationship_expression = reference_args[field_argument_index] if len(reference_args) > field_argument_index else None
        relationship_name = _string_literal(relationship_expression)
        root_operation = str(rp.get("owner_operation") or "")
        root_keys = keys_by_operation.get(root_operation, [])
        if len(root_keys) != 1:
            continue
        source_key = root_keys[0]
        nested_results = [
            item for item in result_bindings_by_parent_call.get(reference_call_id, [])
            if int(item.properties.get("parent_argument_index") or -1) == value_argument_index
        ]
        if len(nested_results) != 1:
            continue
        collection_result = nested_results[0]
        collection_call_id = str(collection_result.properties.get("call_observation_id") or "")
        helper_operation, environment, binding_path, binding_evidence = propagate_environment(
            collection_call_id,
            root_operation,
            {},
        )
        if not helper_operation:
            continue

        queue: list[tuple[str, dict[str, dict[str, Any]], list[dict[str, Any]], list[Fact], int]] = [
            (helper_operation, environment, binding_path, binding_evidence, 0)
        ]
        visited: set[tuple[str, str]] = set()
        while queue:
            operation, current_environment, current_path, current_evidence, depth = queue.pop(0)
            if depth > 4:
                continue
            environment_fingerprint = json.dumps(
                {key: value.get("expression") for key, value in sorted(current_environment.items())},
                sort_keys=True,
                default=str,
            )
            visit_key = (operation, environment_fingerprint)
            if visit_key in visited:
                continue
            visited.add(visit_key)

            operation_keys = keys_by_operation.get(operation, [])
            for target_key in operation_keys:
                tp = target_key.properties
                template_tree = dict(tp.get("resolved_expression_tree") or tp.get("expression_tree") or {})
                composed_tree = _substitute_expression_tree(template_tree, current_environment)
                composed_expression = _render_expression_tree(composed_tree)
                source_expression = source_key.properties.get("resolved_key_expression") or source_key.properties.get("key_expression")
                target_aliases = aliases_by_operation.get(operation, [])
                source_aliases = aliases_by_operation.get(root_operation, [])
                source_key_symbols = list(source_key.properties.get("resolved_input_symbols") or source_key.properties.get("input_symbols") or [])
                target_template_symbols = list(tp.get("resolved_input_symbols") or tp.get("input_symbols") or [])
                source_key_parameters = [
                    parameter for parameter, payload in current_environment.items()
                    if payload.get("origin_source_observation_id") == source_key.properties.get("resolved_source_observation_id")
                    or payload.get("origin_resolved_from_local_variable") == source_key.properties.get("resolved_from_local_variable")
                ]
                evidence_facts = [reference, source_key, target_key, collection_result, *current_evidence]
                evidence_facts.extend(fact for _, fact in source_aliases)
                evidence_facts.extend(fact for _, fact in target_aliases)
                emitted.append(Fact(
                    fact_type="tsa_storage_key_lineage_observation",
                    name=f"{root_operation}:{relationship_name or relationship_expression}->{operation}",
                    properties={
                        "observation_id": _stable_id(
                            "tsa_storage_key_lineage",
                            reference_call_id,
                            source_key.properties.get("observation_id"),
                            target_key.properties.get("observation_id"),
                            current_path,
                        ),
                        "tsa_observation_kind": "reference_collection_storage_key_lineage",
                        "source_owner_fqcn": rp.get("owner_fqcn"),
                        "source_operation": root_operation,
                        "source_alias": source_aliases[0][0] if len(source_aliases) == 1 else None,
                        "relationship_field_expression": relationship_expression,
                        "relationship_field": relationship_name,
                        "reference_operation": rp.get("method"),
                        "reference_call_observation_id": reference_call_id,
                        "collection_helper_operation": helper_operation,
                        "target_key_operation": operation,
                        "target_path_depth": depth,
                        "target_role": "direct_reference_target",
                        "target_alias": target_aliases[0][0] if len(target_aliases) == 1 else None,
                        "target_storage_key_field": tp.get("storage_field"),
                        "source_key_expression": source_expression,
                        "source_key_expression_tree": source_key.properties.get("resolved_expression_tree") or source_key.properties.get("expression_tree") or {},
                        "source_key_input_symbols": source_key_symbols,
                        "target_key_expression_template": tp.get("resolved_key_expression") or tp.get("key_expression"),
                        "target_key_expression_template_tree": template_tree,
                        "composed_target_key_expression": composed_expression,
                        "composed_target_key_expression_tree": composed_tree,
                        "composed_target_key_input_symbols": _collect_input_symbols(composed_tree),
                        "target_key_template_input_symbols": target_template_symbols,
                        "source_key_parameter_bindings": source_key_parameters,
                        "source_key_passed_into_target_key": bool(source_key_parameters),
                        "binding_path": current_path,
                        "observation_policy": "observed TSA reference collection plus exact Java call/key-expression bindings only; no physical table, SQL, FK, or join verdict",
                    },
                    evidence=_evidence_union(*[fact for fact in evidence_facts if isinstance(fact, Fact)]),
                ))
                counts["reference_collection_storage_key_lineage"] += 1

            # The first key-producing operation on a call path is the object
            # directly referenced by this collection. Nested objects have their
            # own reference API calls and are emitted from those observations.
            if operation_keys:
                continue

            outgoing = parameter_bindings_by_caller.get(operation, [])
            call_ids = sorted({str(item.properties.get("call_observation_id") or "") for item in outgoing if item.properties.get("call_observation_id")})
            for call_id in call_ids:
                next_operation, next_environment, path_rows, next_evidence = propagate_environment(
                    call_id,
                    operation,
                    current_environment,
                )
                if not next_operation:
                    continue
                queue.append((
                    next_operation,
                    next_environment,
                    [*current_path, *path_rows],
                    [*current_evidence, *next_evidence],
                    depth + 1,
                ))

    status = {
        "status": "completed",
        "source_facts_evaluated": len(source),
        "observations_emitted": len(emitted),
        "counts_by_kind": dict(sorted(counts.items())),
        "api_framework": roles["framework"],
        "api_roles": roles,
        "facts_only_policy": "TSA vocabulary and API/config occurrences only; no table, FK, SQL, physical encoding, confidence, or business verdict",
    }
    return emitted, status
