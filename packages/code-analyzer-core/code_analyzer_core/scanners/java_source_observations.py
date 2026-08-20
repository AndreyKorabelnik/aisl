from __future__ import annotations

"""Universal source observations derived from the shared Tree-sitter Java AST.

The scanner publishes syntax-level facts only. It deliberately does not decide that
an annotation, call, expression, type, or registry-like mutation has any project-
specific meaning. It publishes neither domain entities nor relationship/key/JOIN verdicts.
"""

from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable
import re

from code_analyzer_core.models import EvidenceRef, Fact
from code_analyzer_core.scanners.java_syntax import (
    JAVA_SYNTAX_EXTRACTOR,
    JavaAnnotation,
    JavaAssignment,
    JavaCall,
    JavaClass,
    JavaInitializer,
    JavaMethod,
    JavaMethodReference,
    JavaSyntaxFile,
    parse_java_files,
)

_SIMPLE_TYPES = {
    "byte", "short", "int", "long", "float", "double", "boolean", "char", "void",
    "Byte", "Short", "Integer", "Long", "Float", "Double", "Boolean", "Character",
    "String", "Object", "Class", "var", "unknown",
}
_JAVA_CONTAINER_TYPES = {
    "List", "Set", "Collection", "Iterable", "Map", "Optional", "Stream", "ArrayList",
    "HashMap", "HashSet", "LinkedHashMap", "LinkedHashSet",
}
_MUTATION_METHOD_KINDS = {
    "put": "map_entry_assignment",
    "putIfAbsent": "map_entry_assignment",
    "add": "collection_addition",
    "addAll": "collection_addition",
    "set": "value_assignment_call",
    "setValue": "value_assignment_call",
    "register": "registration_call",
    "registerType": "registration_call",
    "bind": "binding_call",
    "configure": "configuration_call",
}

def _stable_id(prefix: str, *parts: object) -> str:
    import hashlib

    payload = "\u001f".join(str(part or "") for part in parts)
    return f"{prefix}_{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:20]}"


def _simple_type(value: str | None) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    text = re.sub(r"\[\]$", "", text)
    if "<" in text:
        text = text.split("<", 1)[0].strip()
    return text.split(".")[-1]


def _type_tokens(value: str | None) -> list[str]:
    text = str(value or "")
    tokens = re.findall(r"\b[A-Z][A-Za-z0-9_$]*\b", text)
    return list(dict.fromkeys(token for token in tokens if token not in _SIMPLE_TYPES and token not in _JAVA_CONTAINER_TYPES))


def _ast_value(
    raw: str | None,
    expression_tree: dict[str, Any] | None,
    input_symbols: Iterable[str] | None,
) -> dict[str, Any]:
    """Package an already parsed Tree-sitter expression without reparsing source text."""
    tree = dict(expression_tree or {})
    return {
        "raw": str(raw or "").strip(),
        "node_type": tree.get("node_type"),
        "input_symbols": list(input_symbols or ()),
        "expression_tree": tree,
    }


def _call_argument_node_types(call: JavaCall) -> list[str | None]:
    return [
        (call.argument_trees[index] or {}).get("node_type")
        if index < len(call.argument_trees) else None
        for index in range(len(call.args))
    ]



def _call_parent(call: JavaCall, calls: Iterable[JavaCall]) -> JavaCall | None:
    containers = [
        candidate for candidate in calls
        if candidate is not call
        and candidate.start_byte <= call.start_byte
        and candidate.end_byte >= call.end_byte
    ]
    return min(containers, key=lambda item: item.end_byte - item.start_byte) if containers else None


def _nested_calls(call: JavaCall, calls: Iterable[JavaCall]) -> list[JavaCall]:
    return sorted(
        [
            candidate for candidate in calls
            if candidate is not call
            and call.start_byte <= candidate.start_byte
            and call.end_byte >= candidate.end_byte
        ],
        key=lambda item: item.start_byte,
    )


def _call_depth(call: JavaCall, calls: Iterable[JavaCall]) -> int:
    depth = 0
    current = call
    while True:
        parent = _call_parent(current, calls)
        if parent is None:
            return depth
        depth += 1
        current = parent


def _method_reference_facts(
    parsed: JavaSyntaxFile,
    *,
    operation: str,
    owner: dict[str, Any],
    references: Iterable[JavaMethodReference],
) -> list[Fact]:
    facts: list[Fact] = []
    for reference in references:
        facts.append(Fact(
            fact_type="java_method_reference_observation",
            name=f"{operation}:{reference.text}",
            properties={
                "observation_id": _stable_id("methodref", parsed.file, operation, reference.start_byte, reference.text),
                **owner,
                "qualifier_expression": reference.qualifier,
                "referenced_method": reference.method,
                "reference_text": reference.text,
                "qualifier_expression_tree": dict(reference.qualifier_tree or {}),
                "qualifier_input_symbols": list(reference.qualifier_symbols),
                "syntax_provider": "tree_sitter",
            },
            evidence=_evidence(parsed.file, reference.line_start, reference.line_end, reference.text),
        ))
    return facts

def _call_observation_id(parsed: JavaSyntaxFile, operation: str, call: JavaCall) -> str:
    return _stable_id("call", parsed.file, operation, call.start_byte, call.text)


def _resolve_type_name(parsed: JavaSyntaxFile, type_name: str, local_type_index: dict[str, list[str]]) -> dict[str, Any]:
    token = _simple_type(type_name)
    if "." in type_name and type_name.rsplit(".", 1)[-1] == token:
        return {"resolution": "explicit_fqcn", "resolved_fqcn": type_name, "candidate_fqcns": [type_name]}

    # Java lexical resolution is not a workspace-wide simple-name vote. A
    # single-type import is direct source evidence and therefore takes
    # precedence over unrelated same-name declarations elsewhere in the
    # repository. When there is no explicit import, a declaration from the
    # current package is the next mechanically observable candidate.
    exact_imports = sorted({
        value for value in parsed.imports
        if not value.endswith(".*") and value.rsplit(".", 1)[-1] == token
    })
    if len(exact_imports) == 1:
        return {"resolution": "explicit_import", "resolved_fqcn": exact_imports[0], "candidate_fqcns": exact_imports}
    if len(exact_imports) > 1:
        return {"resolution": "ambiguous_explicit_imports", "candidate_fqcns": exact_imports}

    local_candidates = sorted(dict.fromkeys(local_type_index.get(token) or []))
    same_package = [candidate for candidate in local_candidates if candidate.rsplit(".", 1)[0] == parsed.package]
    if len(same_package) == 1:
        return {"resolution": "same_package", "resolved_fqcn": same_package[0], "candidate_fqcns": same_package}
    if len(same_package) > 1:
        return {"resolution": "ambiguous_same_package", "candidate_fqcns": same_package}
    if len(local_candidates) == 1:
        return {"resolution": "workspace_source_definition", "resolved_fqcn": local_candidates[0], "candidate_fqcns": local_candidates}
    if len(local_candidates) > 1:
        return {"resolution": "ambiguous_candidates", "candidate_fqcns": local_candidates}
    return {"resolution": "unresolved", "candidate_fqcns": []}


def _annotation_properties(annotation: JavaAnnotation, parsed: JavaSyntaxFile, local_type_index: dict[str, list[str]]) -> dict[str, Any]:
    resolution = _resolve_type_name(parsed, annotation.name, local_type_index)
    structured = list(annotation.structured_arguments)
    arguments: dict[str, Any] = {}
    argument_order: list[str] = []
    for index, item in enumerate(structured):
        key = str(item.get("name") or f"value[{index}]")
        argument_order.append(key)
        arguments[key] = {
            "raw": item.get("raw"),
            "node_type": item.get("node_type"),
            "input_symbols": list(item.get("input_symbols") or ()),
            "expression_tree": dict(item.get("expression_tree") or {}),
        }
    return {
        "annotation": annotation.name,
        "annotation_fqcn": resolution.get("resolved_fqcn"),
        "annotation_resolution": resolution.get("resolution"),
        "annotation_candidate_fqcns": resolution.get("candidate_fqcns"),
        "annotation_text": annotation.text,
        "arguments_raw": annotation.arguments,
        "arguments": arguments,
        "argument_order": argument_order,
        "syntax_provider": "tree_sitter",
    }


def _evidence(path: Path, line_start: int | None, line_end: int | None, snippet: str | None = None) -> list[EvidenceRef]:
    return [EvidenceRef(
        file_path=str(path),
        line_start=line_start,
        line_end=line_end,
        extractor=JAVA_SYNTAX_EXTRACTOR,
    )]


def _fqcn(parsed: JavaSyntaxFile, cls: JavaClass) -> str:
    return f"{parsed.package}.{cls.name}" if parsed.package else cls.name


def _owner_properties(parsed: JavaSyntaxFile, cls: JavaClass, method: JavaMethod | None = None) -> dict[str, Any]:
    props: dict[str, Any] = {
        "owner_type": cls.name,
        "owner_fqcn": _fqcn(parsed, cls),
    }
    if method is not None:
        props.update({"owner_method": method.name, "owner_operation": method.operation})
    return props


def _call_target_assignment(call: JavaCall, assignments: Iterable[JavaAssignment]) -> JavaAssignment | None:
    candidates = [a for a in assignments if a.start_byte <= call.start_byte and a.end_byte >= call.end_byte]
    return min(candidates, key=lambda a: a.end_byte - a.start_byte) if candidates else None


def _annotation_facts(parsed: JavaSyntaxFile, cls: JavaClass, local_type_index: dict[str, list[str]]) -> list[Fact]:
    facts: list[Fact] = []
    owner = _owner_properties(parsed, cls)
    for annotation in cls.annotations:
        props = {**owner, "owner_kind": "type", **_annotation_properties(annotation, parsed, local_type_index)}
        facts.append(Fact(
            fact_type="code_annotation",
            name=f"{owner['owner_fqcn']}@{annotation.name}",
            properties={"observation_id": _stable_id("ann", parsed.file, cls.name, annotation.line_start, annotation.text), **props},
            evidence=_evidence(parsed.file, annotation.line_start, annotation.line_end, annotation.text),
        ))
    for field in cls.fields:
        for annotation in field.annotations:
            props = {
                **owner,
                "owner_kind": "field",
                "member_name": field.name,
                "member_type": field.type,
                **_annotation_properties(annotation, parsed, local_type_index),
            }
            facts.append(Fact(
                fact_type="code_annotation",
                name=f"{owner['owner_fqcn']}.{field.name}@{annotation.name}",
                properties={"observation_id": _stable_id("ann", parsed.file, cls.name, field.name, annotation.line_start, annotation.text), **props},
                evidence=_evidence(parsed.file, annotation.line_start, annotation.line_end, annotation.text),
            ))
    for method in cls.methods:
        method_owner = _owner_properties(parsed, cls, method)
        for annotation in method.annotations:
            props = {**method_owner, "owner_kind": "method", "member_name": method.name, **_annotation_properties(annotation, parsed, local_type_index)}
            facts.append(Fact(
                fact_type="code_annotation",
                name=f"{method.operation}@{annotation.name}",
                properties={"observation_id": _stable_id("ann", parsed.file, method.operation, annotation.line_start, annotation.text), **props},
                evidence=_evidence(parsed.file, annotation.line_start, annotation.line_end, annotation.text),
            ))
        for parameter in method.params:
            for annotation in parameter.annotations:
                props = {
                    **method_owner,
                    "owner_kind": "parameter",
                    "member_name": parameter.name,
                    "member_type": parameter.type,
                    **_annotation_properties(annotation, parsed, local_type_index),
                }
                facts.append(Fact(
                    fact_type="code_annotation",
                    name=f"{method.operation}({parameter.name})@{annotation.name}",
                    properties={"observation_id": _stable_id("ann", parsed.file, method.operation, parameter.name, annotation.text), **props},
                    evidence=_evidence(parsed.file, method.line_start, method.line_end, annotation.text),
                ))
    return facts


def _type_reference_facts(parsed: JavaSyntaxFile, cls: JavaClass, local_type_index: dict[str, list[str]]) -> list[Fact]:
    facts: list[Fact] = []
    owner = _owner_properties(parsed, cls)

    def append(reference: str, role: str, *, member_name: str | None = None, member_type: str | None = None, line_start: int | None = None, line_end: int | None = None) -> None:
        for token in _type_tokens(reference):
            resolved = _resolve_type_name(parsed, token, local_type_index)
            props = {
                "observation_id": _stable_id("typeref", parsed.file, cls.name, role, member_name, token, line_start),
                **owner,
                "reference_role": role,
                "referenced_type": token,
                "declared_type_expression": reference,
                "resolution": resolved.get("resolution"),
                "resolved_fqcn": resolved.get("resolved_fqcn"),
                "candidate_fqcns": resolved.get("candidate_fqcns"),
                "member_name": member_name,
                "member_type": member_type,
                "syntax_provider": "tree_sitter",
            }
            facts.append(Fact(
                fact_type="type_reference_observation",
                name=f"{owner['owner_fqcn']} -> {token}",
                properties={key: value for key, value in props.items() if value is not None},
                evidence=_evidence(parsed.file, line_start or cls.line_start, line_end or line_start or cls.line_end),
            ))

    for super_type in cls.super_types:
        append(super_type, "super_type", line_start=cls.line_start, line_end=cls.line_end)
    for field in cls.fields:
        append(field.type, "field_type", member_name=field.name, member_type=field.type, line_start=field.line_start, line_end=field.line_end)
    for method in cls.methods:
        append(method.return_type, "method_return_type", member_name=method.name, member_type=method.return_type, line_start=method.line_start, line_end=method.line_end)
        for parameter in method.params:
            append(parameter.type, "method_parameter_type", member_name=f"{method.name}.{parameter.name}", member_type=parameter.type, line_start=method.line_start, line_end=method.line_end)
    return facts

def _scope_owner_properties(
    parsed: JavaSyntaxFile,
    cls: JavaClass,
    *,
    operation: str,
    scope_kind: str,
    owner_method: str | None = None,
    member_name: str | None = None,
) -> dict[str, Any]:
    props = _owner_properties(parsed, cls)
    props.update({
        "owner_operation": operation,
        "owner_scope_kind": scope_kind,
    })
    if owner_method:
        props["owner_method"] = owner_method
    if member_name:
        props["member_name"] = member_name
    return props


def _constructed_assignment_facts(
    parsed: JavaSyntaxFile,
    *,
    operation: str,
    owner: dict[str, Any],
    assignments: Iterable[JavaAssignment],
    calls: Iterable[JavaCall],
) -> list[Fact]:
    call_list = list(calls)
    facts: list[Fact] = []
    for assignment in assignments:
        related_calls = [call for call in call_list if assignment.start_byte <= call.start_byte and assignment.end_byte >= call.end_byte]
        props = {
            "observation_id": _stable_id("value", parsed.file, operation, assignment.start_byte, assignment.target),
            **owner,
            "target_variable": assignment.target,
            "target_kind": "variable_or_assignment",
            "declared_type": assignment.declared_type,
            "assignment_kind": assignment.assignment_kind,
            "source_start_byte": assignment.start_byte,
            "source_end_byte": assignment.end_byte,
            "lexical_scope_start_byte": assignment.lexical_scope_start_byte,
            "lexical_scope_end_byte": assignment.lexical_scope_end_byte,
            "lexical_scope_depth": assignment.lexical_scope_depth,
            "expression": assignment.expression,
            "expression_tree": dict(assignment.expression_tree or {}),
            "input_symbols": list(assignment.input_symbols),
            "nested_call_observation_ids": [
                _call_observation_id(parsed, operation, call) for call in related_calls
            ],
            "syntax_provider": "tree_sitter",
        }
        facts.append(Fact(
            fact_type="constructed_value_observation",
            name=f"{operation}:{assignment.target}",
            properties={key: value for key, value in props.items() if value is not None},
            evidence=_evidence(parsed.file, assignment.line_start, assignment.line_end, assignment.text),
        ))
    return facts


def _return_value_facts(parsed: JavaSyntaxFile, method: JavaMethod, owner: dict[str, Any]) -> list[Fact]:
    facts: list[Fact] = []
    for index, returned in enumerate(method.returns):
        facts.append(Fact(
            fact_type="constructed_value_observation",
            name=f"{method.operation}:return[{index}]",
            properties={
                "observation_id": _stable_id("return", parsed.file, method.operation, returned.start_byte, returned.expression),
                **owner,
                "target_kind": "return_value",
                "target_variable": None,
                "declared_type": method.return_type,
                "assignment_kind": "return_statement",
                "source_start_byte": returned.start_byte,
                "source_end_byte": returned.end_byte,
                "lexical_scope_start_byte": returned.lexical_scope_start_byte,
                "lexical_scope_end_byte": returned.lexical_scope_end_byte,
                "lexical_scope_depth": returned.lexical_scope_depth,
                "expression": returned.expression,
                "expression_tree": dict(returned.expression_tree or {}),
                "input_symbols": list(returned.input_symbols),
                "syntax_provider": "tree_sitter",
            },
            evidence=_evidence(parsed.file, returned.line_start, returned.line_end, returned.text),
        ))
    return facts


def _call_observation_facts(
    parsed: JavaSyntaxFile,
    *,
    operation: str,
    owner: dict[str, Any],
    calls: Iterable[JavaCall],
    assignments: Iterable[JavaAssignment] = (),
    default_target_variable: str | None = None,
    default_target_declared_type: str | None = None,
) -> list[Fact]:
    facts: list[Fact] = []
    assignment_list = list(assignments)
    call_list = list(calls)
    for call in call_list:
        assignment = _call_target_assignment(call, assignment_list)
        target_variable = assignment.target if assignment else default_target_variable
        target_declared_type = assignment.declared_type if assignment else default_target_declared_type
        call_id = _call_observation_id(parsed, operation, call)
        parent_call = _call_parent(call, call_list)
        nested_calls = _nested_calls(call, call_list)
        call_props = {
            "observation_id": call_id,
            **owner,
            "receiver_expression": call.receiver,
            "receiver_expression_tree": dict(call.receiver_tree or {}),
            "receiver_input_symbols": list(call.receiver_symbols),
            "method": call.method,
            "argument_count": len(call.args),
            "argument_node_types": _call_argument_node_types(call),
            "call_text": call.text,
            "call_start_byte": call.start_byte,
            "call_end_byte": call.end_byte,
            "lexical_scope_start_byte": call.lexical_scope_start_byte,
            "lexical_scope_end_byte": call.lexical_scope_end_byte,
            "lexical_scope_depth": call.lexical_scope_depth,
            "is_unqualified": call.is_unqualified,
            "target_variable": target_variable,
            "target_declared_type": target_declared_type,
            "parent_call_observation_id": _call_observation_id(parsed, operation, parent_call) if parent_call else None,
            "nested_call_observation_ids": [_call_observation_id(parsed, operation, item) for item in nested_calls],
            "call_depth": _call_depth(call, call_list),
            "syntax_provider": "tree_sitter",
        }
        facts.append(Fact(
            fact_type="java_method_call_observation",
            name=f"{operation}:{call.receiver + '.' if call.receiver else ''}{call.method}",
            properties={key: value for key, value in call_props.items() if value is not None},
            evidence=_evidence(parsed.file, call.line_start, call.line_end, call.text),
        ))
        for index, argument in enumerate(call.args):
            argument_tree = call.argument_trees[index] if index < len(call.argument_trees) else {}
            argument_symbols = call.argument_symbols[index] if index < len(call.argument_symbols) else ()
            facts.append(Fact(
                fact_type="call_argument_flow_observation",
                name=f"{operation}:{call.method}[{index}]",
                properties={
                    "observation_id": _stable_id("argflow", call_id, index),
                    **owner,
                    "call_observation_id": call_id,
                    "receiver_expression": call.receiver,
                    "target_method": call.method,
                    "argument_index": index,
                    "call_start_byte": call.start_byte,
                    "call_end_byte": call.end_byte,
                    "lexical_scope_start_byte": call.lexical_scope_start_byte,
                    "lexical_scope_end_byte": call.lexical_scope_end_byte,
                    "lexical_scope_depth": call.lexical_scope_depth,
                    "source_expression": argument,
                    "input_symbols": list(argument_symbols),
                    "expression_tree": dict(argument_tree or {}),
                    "target_variable": target_variable,
                    "syntax_provider": "tree_sitter",
                },
                evidence=_evidence(parsed.file, call.line_start, call.line_end, call.text),
            ))
        mutation_kind = _MUTATION_METHOD_KINDS.get(call.method)
        if mutation_kind:
            facts.append(Fact(
                fact_type="collection_mutation_observation",
                name=f"{operation}:{call.receiver or '<unqualified>'}.{call.method}",
                properties={
                    "observation_id": _stable_id("mutation", call_id, mutation_kind),
                    **owner,
                    "operation_kind": mutation_kind,
                    "receiver_expression": call.receiver,
                    "method": call.method,
                    "argument_count": len(call.args),
                    "call_observation_id": call_id,
                    "syntax_provider": "tree_sitter",
                },
                evidence=_evidence(parsed.file, call.line_start, call.line_end, call.text),
            ))
    return facts


def _field_initializer_facts(parsed: JavaSyntaxFile, cls: JavaClass) -> list[Fact]:
    facts: list[Fact] = []
    for field in cls.fields:
        if not field.initializer:
            continue
        operation = f"{cls.name}.<field:{field.name}>"
        owner = _scope_owner_properties(
            parsed,
            cls,
            operation=operation,
            scope_kind="field_initializer",
            member_name=field.name,
        )
        facts.append(Fact(
            fact_type="constructed_value_observation",
            name=f"{operation}:{field.name}",
            properties={
                "observation_id": _stable_id("fieldvalue", parsed.file, operation, field.name, field.initializer),
                **owner,
                "target_kind": "field_initializer",
                "target_variable": field.name,
                "declared_type": field.type,
                "assignment_kind": "field_initializer",
                "expression": field.initializer,
                "expression_tree": dict(field.initializer_tree or {}),
                "input_symbols": list(field.initializer_symbols),
                "nested_call_observation_ids": [
                    _call_observation_id(parsed, operation, call) for call in field.initializer_calls
                ],
                "syntax_provider": "tree_sitter",
            },
            evidence=_evidence(parsed.file, field.line_start, field.line_end, field.raw),
        ))
        facts.extend(_call_observation_facts(
            parsed,
            operation=operation,
            owner=owner,
            calls=field.initializer_calls,
            default_target_variable=field.name,
            default_target_declared_type=field.type,
        ))
    return facts


def _initializer_facts(parsed: JavaSyntaxFile, cls: JavaClass, initializer: JavaInitializer) -> list[Fact]:
    owner_method = "<clinit>" if initializer.is_static else f"<initializer@{initializer.line_start}>"
    owner = _scope_owner_properties(
        parsed,
        cls,
        operation=initializer.operation,
        scope_kind="static_initializer" if initializer.is_static else "instance_initializer",
        owner_method=owner_method,
    )
    facts = _constructed_assignment_facts(
        parsed,
        operation=initializer.operation,
        owner=owner,
        assignments=initializer.assignments,
        calls=initializer.calls,
    )
    facts.extend(_call_observation_facts(
        parsed,
        operation=initializer.operation,
        owner=owner,
        calls=initializer.calls,
        assignments=initializer.assignments,
    ))
    return facts


def _method_facts(parsed: JavaSyntaxFile, cls: JavaClass, method: JavaMethod) -> list[Fact]:
    owner = _scope_owner_properties(
        parsed,
        cls,
        operation=method.operation,
        scope_kind="method",
        owner_method=method.name,
    )
    facts = _constructed_assignment_facts(
        parsed,
        operation=method.operation,
        owner=owner,
        assignments=method.assignments,
        calls=method.calls,
    )
    facts.extend(_return_value_facts(parsed, method, owner))
    facts.extend(_call_observation_facts(
        parsed,
        operation=method.operation,
        owner=owner,
        calls=method.calls,
        assignments=method.assignments,
    ))
    facts.extend(_method_reference_facts(
        parsed,
        operation=method.operation,
        owner=owner,
        references=method.method_references,
    ))
    return facts


def _method_signature(parsed: JavaSyntaxFile, cls: JavaClass, method: JavaMethod) -> str:
    parameter_types = ",".join(parameter.type for parameter in method.params)
    return f"{_fqcn(parsed, cls)}#{method.name}({parameter_types})"


_STRICT_SOURCE_TYPE_RESOLUTIONS = {"explicit_fqcn", "explicit_import", "same_package"}


def _method_parameter_declaration_facts(parsed: JavaSyntaxFile, cls: JavaClass, method: JavaMethod) -> list[Fact]:
    """Publish every declared method parameter, including primitive/container types.

    Type-reference observations intentionally omit primitives and common containers.
    A parameter declaration is a separate syntax fact and must therefore not depend
    on whether its type participates in type resolution.
    """
    owner = _scope_owner_properties(
        parsed,
        cls,
        operation=method.operation,
        scope_kind="method",
        owner_method=method.name,
    )
    is_interface_method = cls.kind == "interface"
    is_abstract_method = is_interface_method or "abstract" in set(str(method.modifiers or "").split())
    declaration_kind = (
        "interface_method_parameter" if is_interface_method
        else "abstract_method_parameter" if is_abstract_method
        else "method_parameter"
    )
    signature = _method_signature(parsed, cls, method)
    return [
        Fact(
            fact_type="java_method_parameter_observation",
            name=f"{method.operation}[{position}] {parameter.name}",
            properties={
                "observation_id": _stable_id("method_parameter", signature, position, parameter.name),
                **owner,
                "method_name": method.name,
                "method_operation": method.operation,
                "method_signature": signature,
                "parameter_name": parameter.name,
                "parameter_type": parameter.type,
                "parameter_position": position,
                "declaration_kind": declaration_kind,
                "is_interface_method": is_interface_method,
                "is_abstract_method": is_abstract_method,
                "syntax_provider": "tree_sitter",
                "observation_policy": "declared Java method parameter only; no call binding, runtime dispatch, or semantic verdict",
            },
            evidence=_evidence(parsed.file, method.line_start, method.line_end, parameter.raw),
        )
        for position, parameter in enumerate(method.params)
    ]


def _erased_type_key(parsed: JavaSyntaxFile, value: str, local_type_index: dict[str, list[str]]) -> str:
    raw = re.sub(r"\s+", "", str(value or ""))
    dimensions = "[]" * raw.count("[]")
    base = re.sub(r"\[\]", "", raw)
    if "<" in base:
        base = base.split("<", 1)[0]
    if base in _SIMPLE_TYPES or base[:1].islower():
        return f"{base}{dimensions}"
    resolution = _resolve_type_name(parsed, base, local_type_index)
    resolved = resolution.get("resolved_fqcn")
    if resolved and resolution.get("resolution") in _STRICT_SOURCE_TYPE_RESOLUTIONS:
        return f"{resolved}{dimensions}"
    return f"raw:{base}{dimensions}"


def _exact_method_signature_key(
    parsed: JavaSyntaxFile,
    method: JavaMethod,
    local_type_index: dict[str, list[str]],
) -> tuple[str, tuple[str, ...]]:
    return (
        method.name,
        tuple(_erased_type_key(parsed, parameter.type, local_type_index) for parameter in method.params),
    )


def _repository_declaration_indexes(parsed_files: list[JavaSyntaxFile]) -> tuple[dict[str, tuple[JavaSyntaxFile, JavaClass]], dict[str, list[tuple[JavaSyntaxFile, JavaClass]]]]:
    by_fqcn: dict[str, tuple[JavaSyntaxFile, JavaClass]] = {}
    by_simple: dict[str, list[tuple[JavaSyntaxFile, JavaClass]]] = defaultdict(list)
    for parsed in parsed_files:
        for cls in parsed.classes:
            by_fqcn[_fqcn(parsed, cls)] = (parsed, cls)
            by_simple[cls.name].append((parsed, cls))
    return by_fqcn, by_simple


def _repository_method_declaration_facts(
    parsed_files: list[JavaSyntaxFile],
    local_type_index: dict[str, list[str]],
) -> list[Fact]:
    """Publish exact direct implementation/override correspondences.

    The relation is deliberately correspondence-only. A direct ``implements`` or
    ``extends`` declaration plus equal erased parameter types identifies a source
    method candidate, but does not prove which implementation is selected at runtime.
    """
    by_fqcn, _ = _repository_declaration_indexes(parsed_files)
    facts: list[Fact] = []
    for implementation_parsed in parsed_files:
        for implementation_class in implementation_parsed.classes:
            direct_super_types = [*implementation_class.implements]
            if implementation_class.extends:
                direct_super_types.append(implementation_class.extends)
            for raw_super_type in direct_super_types:
                resolution = _resolve_type_name(implementation_parsed, raw_super_type, local_type_index)
                if resolution.get("resolution") not in _STRICT_SOURCE_TYPE_RESOLUTIONS:
                    continue
                super_fqcn = str(resolution.get("resolved_fqcn") or "")
                super_entry = by_fqcn.get(super_fqcn)
                if not super_entry:
                    continue
                super_parsed, super_class = super_entry
                super_methods: dict[tuple[str, tuple[str, ...]], list[JavaMethod]] = defaultdict(list)
                for method in super_class.methods:
                    super_methods[_exact_method_signature_key(super_parsed, method, local_type_index)].append(method)
                for implementation_method in implementation_class.methods:
                    key = _exact_method_signature_key(implementation_parsed, implementation_method, local_type_index)
                    candidates = super_methods.get(key, [])
                    if len(candidates) != 1:
                        continue
                    declared_method = candidates[0]
                    declared_signature = _method_signature(super_parsed, super_class, declared_method)
                    implementation_signature = _method_signature(implementation_parsed, implementation_class, implementation_method)
                    evidence = _evidence(
                        implementation_parsed.file,
                        implementation_method.line_start,
                        implementation_method.line_end,
                        implementation_method.text,
                    )
                    common = {
                        "declared_owner_fqcn": super_fqcn,
                        "declared_owner_kind": super_class.kind,
                        "declared_method": declared_method.name,
                        "declared_method_operation": declared_method.operation,
                        "declared_method_signature": declared_signature,
                        "implementation_owner_fqcn": _fqcn(implementation_parsed, implementation_class),
                        "implementation_owner_kind": implementation_class.kind,
                        "implementation_method": implementation_method.name,
                        "implementation_method_operation": implementation_method.operation,
                        "implementation_method_signature": implementation_signature,
                        "direct_relation": "implements" if raw_super_type in implementation_class.implements else "extends",
                        "relation_kind": "correspondence",
                        "resolution_basis": "direct_source_supertype_declaration_and_exact_erased_parameter_types",
                        "syntax_provider": "tree_sitter",
                        "observation_policy": "source-declared implementation candidate only; no runtime dispatch or selected-implementation verdict",
                    }
                    facts.append(Fact(
                        fact_type="java_method_implementation_observation",
                        name=f"{declared_method.operation} -> {implementation_method.operation}",
                        properties={
                            "observation_id": _stable_id("method_implementation", declared_signature, implementation_signature),
                            **common,
                        },
                        evidence=evidence,
                    ))
                    for position, (declared_parameter, implementation_parameter) in enumerate(
                        zip(declared_method.params, implementation_method.params)
                    ):
                        facts.append(Fact(
                            fact_type="java_method_parameter_correspondence_observation",
                            name=(
                                f"{declared_method.operation}.{declared_parameter.name}[{position}] -> "
                                f"{implementation_method.operation}.{implementation_parameter.name}[{position}]"
                            ),
                            properties={
                                "observation_id": _stable_id(
                                    "method_parameter_correspondence",
                                    declared_signature, implementation_signature, position,
                                ),
                                **common,
                                "parameter_position": position,
                                "declared_parameter": declared_parameter.name,
                                "declared_parameter_type": declared_parameter.type,
                                "implementation_parameter": implementation_parameter.name,
                                "implementation_parameter_type": implementation_parameter.type,
                            },
                            evidence=evidence,
                        ))
    return facts


def _repository_interprocedural_binding_facts(
    parsed_files: list[JavaSyntaxFile],
    local_type_index: dict[str, list[str]],
) -> list[Fact]:
    """Bind calls to exact source-declared receiver methods across Java types.

    Resolution is intentionally narrow: the receiver must be a simple identifier
    whose declared type is observed on a field, parameter, or local declaration,
    and that type must resolve through an explicit FQCN/import or the same package.
    Wildcard imports, repository-wide simple-name voting, DI selection, and runtime
    dispatch are not used.
    """
    by_fqcn, _ = _repository_declaration_indexes(parsed_files)
    facts: list[Fact] = []
    for parsed in parsed_files:
        for cls in parsed.classes:
            caller_fqcn = _fqcn(parsed, cls)
            fields = {field.name: field.type for field in cls.fields}
            for caller in cls.methods:
                variables = dict(fields)
                variables.update({parameter.name: parameter.type for parameter in caller.params})
                for assignment in caller.assignments:
                    if assignment.declared_type and re.fullmatch(r"[A-Za-z_$][A-Za-z0-9_$]*", assignment.target):
                        variables[assignment.target] = assignment.declared_type
                owner = _scope_owner_properties(
                    parsed, cls, operation=caller.operation, scope_kind="method", owner_method=caller.name
                )
                for call in caller.calls:
                    receiver = str(call.receiver or "").strip()
                    if not re.fullmatch(r"[A-Za-z_$][A-Za-z0-9_$]*", receiver):
                        continue
                    declared_type = variables.get(receiver)
                    if declared_type is None and receiver[:1].isupper():
                        declared_type = receiver
                    if not declared_type:
                        continue
                    resolution = _resolve_type_name(parsed, declared_type, local_type_index)
                    if resolution.get("resolution") not in _STRICT_SOURCE_TYPE_RESOLUTIONS:
                        continue
                    target_fqcn = str(resolution.get("resolved_fqcn") or "")
                    if not target_fqcn or target_fqcn == caller_fqcn:
                        continue
                    target_entry = by_fqcn.get(target_fqcn)
                    if not target_entry:
                        continue
                    target_parsed, target_class = target_entry
                    candidates = [
                        method for method in target_class.methods
                        if method.name == call.method and len(method.params) == len(call.args)
                    ]
                    if len(candidates) != 1:
                        continue
                    callee = candidates[0]
                    call_id = _call_observation_id(parsed, caller.operation, call)
                    callee_signature = _method_signature(target_parsed, target_class, callee)
                    common = {
                        **owner,
                        "call_observation_id": call_id,
                        "caller_operation": caller.operation,
                        "call_start_byte": call.start_byte,
                        "call_end_byte": call.end_byte,
                        "lexical_scope_start_byte": call.lexical_scope_start_byte,
                        "lexical_scope_end_byte": call.lexical_scope_end_byte,
                        "lexical_scope_depth": call.lexical_scope_depth,
                        "receiver_expression": receiver,
                        "receiver_declared_type": declared_type,
                        "receiver_type_resolution": resolution.get("resolution"),
                        "callee_owner_fqcn": target_fqcn,
                        "callee_owner_kind": target_class.kind,
                        "callee_operation": callee.operation,
                        "callee_signature": callee_signature,
                        "callee_method": callee.name,
                        "resolution": "exact_declared_receiver_type_and_unique_source_method_name_arity",
                        "syntax_provider": "tree_sitter",
                        "observation_policy": "exact source call-to-declared-method binding only; no runtime implementation selection or semantic verdict",
                    }
                    for index, argument in enumerate(call.args):
                        parameter = callee.params[index]
                        argument_tree = call.argument_trees[index] if index < len(call.argument_trees) else {}
                        argument_symbols = call.argument_symbols[index] if index < len(call.argument_symbols) else ()
                        facts.append(Fact(
                            fact_type="java_call_parameter_binding_observation",
                            name=f"{caller.operation}:{call.method}[{index}] -> {parameter.name}",
                            properties={
                                "observation_id": _stable_id("call_parameter_binding", call_id, callee_signature, index),
                                **common,
                                "argument_index": index,
                                "caller_expression": argument,
                                "caller_input_symbols": list(argument_symbols),
                                "caller_expression_tree": dict(argument_tree or {}),
                                "callee_parameter": parameter.name,
                                "callee_parameter_type": parameter.type,
                            },
                            evidence=_evidence(parsed.file, call.line_start, call.line_end, call.text),
                        ))
                    assignment = _call_target_assignment(call, caller.assignments)
                    parent = _call_parent(call, caller.calls)
                    parent_argument_index = _parent_argument_index(parent, call)
                    result_target_kind = (
                        "assigned_variable" if assignment is not None
                        else "parent_call_argument" if parent is not None and parent_argument_index is not None
                        else "call_result"
                    )
                    result_properties = {
                        "observation_id": _stable_id("call_result_binding", call_id, callee_signature),
                        **common,
                        "callee_return_type": callee.return_type,
                        "result_target_kind": result_target_kind,
                        "target_variable": assignment.target if assignment is not None else None,
                        "target_declared_type": assignment.declared_type if assignment is not None else None,
                        "target_assignment_start_byte": assignment.start_byte if assignment is not None else None,
                        "target_assignment_end_byte": assignment.end_byte if assignment is not None else None,
                        "target_scope_start_byte": assignment.lexical_scope_start_byte if assignment is not None else None,
                        "target_scope_end_byte": assignment.lexical_scope_end_byte if assignment is not None else None,
                        "target_scope_depth": assignment.lexical_scope_depth if assignment is not None else None,
                        "parent_call_observation_id": (
                            _call_observation_id(parsed, caller.operation, parent) if parent is not None else None
                        ),
                        "parent_argument_index": parent_argument_index,
                    }
                    facts.append(Fact(
                        fact_type="java_call_result_binding_observation",
                        name=f"{caller.operation}:{call.method} result",
                        properties={key: value for key, value in result_properties.items() if value is not None},
                        evidence=_evidence(parsed.file, call.line_start, call.line_end, call.text),
                    ))
    return facts


def _parent_argument_index(parent: JavaCall | None, nested: JavaCall) -> int | None:
    """Locate a nested call inside Tree-sitter-delimited parent arguments.

    The Java structure and argument boundaries are supplied by Tree-sitter.  The
    small containment check below only identifies which already parsed argument
    contains the already parsed nested call; it is not a Java parser fallback.
    """
    if parent is None:
        return None
    nested_text = nested.text.strip()
    if not nested_text:
        return None
    matches = [index for index, argument in enumerate(parent.args) if nested_text in argument]
    return matches[0] if len(matches) == 1 else None


def _interprocedural_binding_facts(parsed: JavaSyntaxFile, cls: JavaClass) -> list[Fact]:
    """Publish exact same-class call bindings without interpreting their meaning.

    This deliberately resolves only calls whose receiver is absent, ``this``, or
    the declaring class and whose method name/arity identifies one local method.
    Ambiguous overloads and external dispatch remain unresolved rather than being
    guessed.  The observations allow later framework interpreters to compose
    values through helper methods while core stays framework-agnostic.
    """
    methods_by_name_arity: dict[tuple[str, int], list[JavaMethod]] = defaultdict(list)
    for candidate in cls.methods:
        methods_by_name_arity[(candidate.name, len(candidate.params))].append(candidate)

    facts: list[Fact] = []
    for caller in cls.methods:
        call_list = list(caller.calls)
        owner = _scope_owner_properties(
            parsed,
            cls,
            operation=caller.operation,
            scope_kind="method",
            owner_method=caller.name,
        )
        for call in call_list:
            receiver = str(call.receiver or "").strip()
            if receiver not in {"", "this", cls.name}:
                continue
            candidates = methods_by_name_arity.get((call.method, len(call.args)), [])
            if len(candidates) != 1:
                continue
            callee = candidates[0]
            call_id = _call_observation_id(parsed, caller.operation, call)
            callee_signature = _method_signature(parsed, cls, callee)
            for index, argument in enumerate(call.args):
                parameter = callee.params[index]
                argument_tree = call.argument_trees[index] if index < len(call.argument_trees) else {}
                argument_symbols = call.argument_symbols[index] if index < len(call.argument_symbols) else ()
                facts.append(Fact(
                    fact_type="java_call_parameter_binding_observation",
                    name=f"{caller.operation}:{call.method}[{index}] -> {parameter.name}",
                    properties={
                        "observation_id": _stable_id("call_parameter_binding", call_id, callee_signature, index),
                        **owner,
                        "call_observation_id": call_id,
                        "caller_operation": caller.operation,
                        "call_start_byte": call.start_byte,
                        "call_end_byte": call.end_byte,
                        "lexical_scope_start_byte": call.lexical_scope_start_byte,
                        "lexical_scope_end_byte": call.lexical_scope_end_byte,
                        "lexical_scope_depth": call.lexical_scope_depth,
                        "callee_owner_fqcn": _fqcn(parsed, cls),
                        "callee_operation": callee.operation,
                        "callee_signature": callee_signature,
                        "callee_method": callee.name,
                        "argument_index": index,
                        "caller_expression": argument,
                        "caller_input_symbols": list(argument_symbols),
                        "caller_expression_tree": dict(argument_tree or {}),
                        "callee_parameter": parameter.name,
                        "callee_parameter_type": parameter.type,
                        "resolution": "exact_same_class_name_and_arity",
                        "syntax_provider": "tree_sitter",
                        "observation_policy": "exact syntactic call-to-parameter binding only; no value equivalence or semantic verdict",
                    },
                    evidence=_evidence(parsed.file, call.line_start, call.line_end, call.text),
                ))

            assignment = _call_target_assignment(call, caller.assignments)
            parent = _call_parent(call, call_list)
            parent_argument_index = _parent_argument_index(parent, call)
            if assignment is not None:
                result_target_kind = "assigned_variable"
            elif parent is not None and parent_argument_index is not None:
                result_target_kind = "parent_call_argument"
            else:
                result_target_kind = "call_result"
            properties = {
                "observation_id": _stable_id("call_result_binding", call_id, callee_signature),
                **owner,
                "call_observation_id": call_id,
                "caller_operation": caller.operation,
                "call_start_byte": call.start_byte,
                "call_end_byte": call.end_byte,
                "lexical_scope_start_byte": call.lexical_scope_start_byte,
                "lexical_scope_end_byte": call.lexical_scope_end_byte,
                "lexical_scope_depth": call.lexical_scope_depth,
                "callee_owner_fqcn": _fqcn(parsed, cls),
                "callee_operation": callee.operation,
                "callee_signature": callee_signature,
                "callee_method": callee.name,
                "callee_return_type": callee.return_type,
                "result_target_kind": result_target_kind,
                "target_variable": assignment.target if assignment is not None else None,
                "target_declared_type": assignment.declared_type if assignment is not None else None,
                "target_assignment_start_byte": assignment.start_byte if assignment is not None else None,
                "target_assignment_end_byte": assignment.end_byte if assignment is not None else None,
                "target_scope_start_byte": assignment.lexical_scope_start_byte if assignment is not None else None,
                "target_scope_end_byte": assignment.lexical_scope_end_byte if assignment is not None else None,
                "target_scope_depth": assignment.lexical_scope_depth if assignment is not None else None,
                "parent_call_observation_id": _call_observation_id(parsed, caller.operation, parent) if parent is not None else None,
                "parent_argument_index": parent_argument_index,
                "resolution": "exact_same_class_name_and_arity",
                "syntax_provider": "tree_sitter",
                "observation_policy": "exact syntactic call-result placement only; no return-value equivalence or semantic verdict",
            }
            facts.append(Fact(
                fact_type="java_call_result_binding_observation",
                name=f"{caller.operation}:{call.method} result",
                properties={key: value for key, value in properties.items() if value is not None},
                evidence=_evidence(parsed.file, call.line_start, call.line_end, call.text),
            ))
    return facts


def build_java_source_observation_facts(files: list[Path]) -> tuple[list[Fact], dict[str, Any]]:
    parsed_files, warnings = parse_java_files(files)
    local_type_index: dict[str, list[str]] = {}
    for parsed in parsed_files:
        for cls in parsed.classes:
            local_type_index.setdefault(cls.name, []).append(_fqcn(parsed, cls))
    local_type_index = {name: sorted(dict.fromkeys(values)) for name, values in local_type_index.items()}

    facts: list[Fact] = []
    for parsed in parsed_files:
        for cls in parsed.classes:
            facts.extend(_annotation_facts(parsed, cls, local_type_index))
            facts.extend(_type_reference_facts(parsed, cls, local_type_index))
            facts.extend(_field_initializer_facts(parsed, cls))
            for initializer in cls.initializers:
                facts.extend(_initializer_facts(parsed, cls, initializer))
            for method in cls.methods:
                facts.extend(_method_parameter_declaration_facts(parsed, cls, method))
                facts.extend(_method_facts(parsed, cls, method))
            facts.extend(_interprocedural_binding_facts(parsed, cls))

    facts.extend(_repository_interprocedural_binding_facts(parsed_files, local_type_index))
    facts.extend(_repository_method_declaration_facts(parsed_files, local_type_index))

    by_type = Counter(fact.fact_type for fact in facts)
    unresolved = sum(
        1 for fact in facts
        if fact.fact_type == "type_reference_observation"
        and (fact.properties or {}).get("resolution") == "unresolved"
    )
    ambiguous = sum(
        1 for fact in facts
        if fact.fact_type == "type_reference_observation"
        and (fact.properties or {}).get("resolution") == "ambiguous_candidates"
    )
    return facts, {
        "requested": True,
        "status": "success",
        "provider": "tree_sitter",
        "files_parsed": len(parsed_files),
        "facts_extracted": len(facts),
        "fact_type_counts": dict(sorted(by_type.items())),
        "unresolved_type_references": unresolved,
        "ambiguous_type_references": ambiguous,
        "parse_warnings": list(warnings),
        "policy": "universal syntax observations only; no project-specific annotation/API meaning, domain classification, key verdict, relationship verdict, or JOIN inference",
    }
