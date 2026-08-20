from __future__ import annotations

import json
from typing import Any, Iterable


def java_string_literal_value(expression: Any) -> str | None:
    text = str(expression or "").strip()
    if len(text) < 2:
        return None
    if text[0] == '"' and text[-1] == '"':
        try:
            value = json.loads(text)
        except json.JSONDecodeError:
            return None
        return value if isinstance(value, str) else None
    if text[0] == "'" and text[-1] == "'" and len(text) == 3:
        return text[1]
    return None


def _tree_child(node: dict[str, Any], field: str) -> dict[str, Any] | None:
    for child in node.get("children") or []:
        if isinstance(child, dict) and child.get("field") == field:
            return child
    return None


def _tree_method_name(node: dict[str, Any]) -> str:
    child = _tree_child(node, "name")
    return str((child or {}).get("value") or (child or {}).get("text") or "")


def _tree_argument_nodes(node: dict[str, Any]) -> list[dict[str, Any]]:
    arguments = _tree_child(node, "arguments")
    if not arguments:
        return []
    return [child for child in (arguments.get("children") or []) if isinstance(child, dict)]


def getter_field_name(method_name: str) -> str | None:
    if method_name.startswith("get") and len(method_name) > 3:
        suffix = method_name[3:]
        return suffix[:1].lower() + suffix[1:]
    if method_name.startswith("is") and len(method_name) > 2:
        suffix = method_name[2:]
        return suffix[:1].lower() + suffix[1:]
    return None


def infer_key_fields_from_expression_tree(node: Any) -> tuple[str, ...]:
    """Return field names explicitly accessed by getter/get syntax in a key expression.

    This is intentionally syntax-only. Receiver identity is not interpreted and
    the result is never a claim that the fields are a declared primary key.
    """
    found: list[str] = []

    def add(value: str | None) -> None:
        text = str(value or "").strip()
        if text and text not in found:
            found.append(text)

    def visit(value: Any) -> None:
        if not isinstance(value, dict):
            return
        node_type = str(value.get("node_type") or "")
        if node_type == "method_invocation":
            method_name = _tree_method_name(value)
            getter = getter_field_name(method_name)
            if getter:
                add(getter)
            elif method_name == "get":
                args = _tree_argument_nodes(value)
                if len(args) == 1:
                    add(java_string_literal_value(args[0].get("value") or args[0].get("text")))
        for child in value.get("children") or []:
            visit(child)
        if node_type == "bound_expression":
            visit(value.get("binding_tree"))

    visit(node)
    return tuple(found)


def canonical_key_expression_node(node: Any, key_fields: Iterable[str]) -> Any | None:
    """Canonicalize syntax only when accesses resolve to an allowed key field.

    Receiver identity is discarded only for an accessor whose final property is
    in ``key_fields``. Unknown calls/identifiers return ``None`` rather than being
    guessed. This is the shared implementation used by legacy workspace
    diagnostics and typed KLC composition.
    """
    fields = tuple(str(value) for value in key_fields if str(value))
    if not isinstance(node, dict):
        return None
    node_type = str(node.get("node_type") or "")
    if node_type in {"string_literal", "character_literal", "char_literal"}:
        raw = node.get("value") or node.get("text")
        value = java_string_literal_value(raw)
        return ["literal", value] if value is not None else None
    if node_type in {
        "decimal_integer_literal", "hex_integer_literal", "integer_literal",
        "decimal_floating_point_literal", "true", "false",
    }:
        return ["scalar", str(node.get("value") or node.get("text") or "")]
    if node_type == "binary_expression":
        left = canonical_key_expression_node(_tree_child(node, "left"), fields)
        right = canonical_key_expression_node(_tree_child(node, "right"), fields)
        operator = str(node.get("operator") or (_tree_child(node, "operator") or {}).get("value") or "")
        if left is None or right is None or not operator:
            return None
        return ["binary", operator, left, right]
    if node_type == "method_invocation":
        method_name = _tree_method_name(node)
        getter_field = getter_field_name(method_name)
        if getter_field in fields:
            return ["target_key_field", getter_field]
        if method_name == "get":
            args = _tree_argument_nodes(node)
            if len(args) == 1:
                field_name = java_string_literal_value(args[0].get("value") or args[0].get("text"))
                if field_name in fields:
                    return ["target_key_field", field_name]
        if method_name in {
            "asText", "asLong", "asInt", "asDouble", "asBoolean",
            "longValue", "intValue", "doubleValue", "textValue", "toString",
        }:
            return canonical_key_expression_node(_tree_child(node, "object"), fields)
        return None
    if node_type == "bound_expression":
        return canonical_key_expression_node(node.get("binding_tree"), fields)
    if node_type in {"parenthesized_expression", "cast_expression"}:
        for child in node.get("children") or []:
            if not isinstance(child, dict) or child.get("field") in {"type", "operator"}:
                continue
            canonical = canonical_key_expression_node(child, fields)
            if canonical is not None:
                return canonical
        return None
    if node_type in {"field_access", "scoped_identifier"}:
        field_child = _tree_child(node, "field") or _tree_child(node, "name")
        field_name = str((field_child or {}).get("value") or (field_child or {}).get("text") or "")
        if field_name in fields:
            return ["target_key_field", field_name]
        return None
    if node_type == "identifier":
        value = str(node.get("value") or node.get("text") or "")
        if value in fields:
            return ["target_key_field", value]
        return None
    return None
