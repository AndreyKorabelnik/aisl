from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable
import re

from code_analyzer_core.utils import read_text

try:  # pragma: no cover - exercised by integration tests when dependency exists
    from tree_sitter import Language, Parser, Node
    import tree_sitter_java as tsjava
except Exception:  # pragma: no cover
    Language = None  # type: ignore[assignment]
    Parser = None  # type: ignore[assignment]
    Node = Any  # type: ignore[misc,assignment]
    tsjava = None  # type: ignore[assignment]


JAVA_SYNTAX_PROVIDER = "tree_sitter"
JAVA_SYNTAX_EXTRACTOR = "java_tree_sitter"

_LEXICAL_SCOPE_NODE_TYPES = {
    "method_declaration", "constructor_declaration", "block", "lambda_expression",
    "catch_clause", "for_statement", "enhanced_for_statement", "switch_block",
    "switch_block_statement_group", "try_statement", "synchronized_statement",
}

def _lexical_scope_coordinates(node: Any) -> tuple[int | None, int | None, int]:
    """Return nearest lexical scope boundaries and nesting depth from Tree-sitter."""
    current = getattr(node, "parent", None)
    depth = 0
    selected = None
    while current is not None:
        if getattr(current, "type", None) in _LEXICAL_SCOPE_NODE_TYPES:
            depth += 1
            if selected is None:
                selected = current
        current = getattr(current, "parent", None)
    if selected is None:
        return None, None, depth
    return int(selected.start_byte), int(selected.end_byte), depth


def annotation_string_arg(arguments: str | None, key: str = "value") -> str | None:
    """Extract a quoted annotation argument from Tree-sitter annotation arguments.

    Tree-sitter gives the annotation argument list as a syntax-scoped text fragment.
    This helper is intentionally small: it is annotation-argument normalization, not
    Java structural parsing.
    """
    if not arguments:
        return None
    text = str(arguments).strip()
    patterns = [
        rf"\b{re.escape(key)}\s*=\s*\"([^\"]+)\"",
    ]
    if key == "value":
        patterns.append(r'^\s*\"([^\"]+)\"\s*$')
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            return m.group(1)
    return None


def annotation_bool_arg(arguments: str | None, key: str) -> bool | None:
    if not arguments:
        return None
    m = re.search(rf"\b{re.escape(key)}\s*=\s*(true|false)\b", str(arguments), re.IGNORECASE)
    if not m:
        return None
    return m.group(1).lower() == "true"


def unquote_annotation_value(value: str | None) -> str | None:
    if value is None:
        return None
    raw = str(value).strip()
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in {'\"', "'"}:
        raw = raw[1:-1]
    return raw.strip() or None


def annotation_args_map(arguments: str | None) -> dict[str, str]:
    if not arguments:
        return {}
    out: dict[str, str] = {}
    positional: list[str] = []
    for part in split_java_arguments(str(arguments).strip()):
        if "=" in part:
            key, value = part.split("=", 1)
            out[key.strip()] = value.strip()
        else:
            value = part.strip()
            if value:
                positional.append(value)
    if positional:
        out.setdefault("value", positional[0])
    return out


def annotation_values(annotations: Iterable["JavaAnnotation"]) -> list[dict[str, Any]]:
    return [
        {"name": a.name, "arguments": a.arguments, "text": a.text, "line_start": a.line_start, "line_end": a.line_end}
        for a in annotations
    ]


def _javadoc_before_node(text: str, node: Any) -> dict[str, Any]:
    """Return the Javadoc immediately attached to a Tree-sitter declaration.

    Java syntax boundaries remain owned by Tree-sitter.  This helper only
    normalizes the contents of an already identified ``/** ... */`` comment;
    it does not search Java declarations with regular expressions.
    """
    previous = getattr(node, "prev_named_sibling", None)
    if previous is None or previous.type != "block_comment":
        return {}
    raw = _text(text, previous).strip()
    if not raw.startswith("/**"):
        return {}
    source = _utf8_bytes(text)
    between = source[int(previous.end_byte):int(node.start_byte)].decode("utf-8", errors="replace")
    if between.strip():
        return {}

    body = raw[3:-2] if raw.endswith("*/") else raw[3:]
    cleaned_lines: list[str] = []
    for line in body.splitlines():
        value = line.strip()
        if value.startswith("*"):
            value = value[1:].lstrip()
        cleaned_lines.append(value)

    summary_lines: list[str] = []
    tags: dict[str, str] = {}
    current_tag: str | None = None
    for line in cleaned_lines:
        if line.startswith("@"):
            head, _, tail = line[1:].partition(" ")
            current_tag = head.strip() or None
            if current_tag:
                tags[current_tag] = tail.strip()
            continue
        if current_tag and line:
            tags[current_tag] = " ".join(part for part in (tags.get(current_tag), line) if part).strip()
        elif line:
            summary_lines.append(line)

    summary = " ".join(summary_lines).strip() or None
    display_name = tags.get("name") or None
    description = tags.get("description") or summary
    return {
        "raw": raw,
        "summary": summary,
        "display_name": display_name,
        "description": description,
        "tags": tags,
        "line_start": _line_start(previous),
        "line_end": _line_end(previous),
    }


@dataclass(frozen=True)
class JavaAnnotation:
    name: str
    text: str
    arguments: str | None
    line_start: int
    line_end: int
    structured_arguments: tuple[dict[str, Any], ...] = ()

    def string_arg(self, key: str = "value") -> str | None:
        """Return a quoted annotation argument from the already parsed annotation text."""
        return annotation_string_arg(self.arguments, key)

    def bool_arg(self, key: str) -> bool | None:
        """Return a boolean annotation argument from the already parsed annotation text."""
        return annotation_bool_arg(self.arguments, key)

    def args_map(self) -> dict[str, str]:
        return annotation_args_map(self.arguments)


@dataclass(frozen=True)
class JavaParam:
    name: str
    type: str
    raw: str
    annotations: tuple[JavaAnnotation, ...] = ()




@dataclass(frozen=True)
class JavaCall:
    receiver: str | None
    method: str
    args: tuple[str, ...]
    args_text: str
    text: str
    line_start: int
    line_end: int
    start_byte: int
    end_byte: int
    is_unqualified: bool = False
    argument_trees: tuple[dict[str, Any], ...] = ()
    argument_symbols: tuple[tuple[str, ...], ...] = ()
    receiver_tree: dict[str, Any] = field(default_factory=dict)
    receiver_symbols: tuple[str, ...] = ()
    lexical_scope_start_byte: int | None = None
    lexical_scope_end_byte: int | None = None
    lexical_scope_depth: int = 0


@dataclass(frozen=True)
class JavaAssignment:
    target: str
    expression: str
    text: str
    line_start: int
    line_end: int
    start_byte: int
    end_byte: int
    declared_type: str | None = None
    assignment_kind: str = "assignment"
    expression_tree: dict[str, Any] = field(default_factory=dict)
    input_symbols: tuple[str, ...] = ()
    lexical_scope_start_byte: int | None = None
    lexical_scope_end_byte: int | None = None
    lexical_scope_depth: int = 0


@dataclass(frozen=True)
class JavaReturn:
    expression: str
    text: str
    line_start: int
    line_end: int
    start_byte: int
    end_byte: int
    expression_tree: dict[str, Any] = field(default_factory=dict)
    input_symbols: tuple[str, ...] = ()
    lexical_scope_start_byte: int | None = None
    lexical_scope_end_byte: int | None = None
    lexical_scope_depth: int = 0


@dataclass(frozen=True)
class JavaObjectCreation:
    type: str
    args: tuple[str, ...]
    args_text: str
    text: str
    line_start: int
    line_end: int
    start_byte: int
    end_byte: int
    argument_trees: tuple[dict[str, Any], ...] = ()
    argument_symbols: tuple[tuple[str, ...], ...] = ()


@dataclass(frozen=True)
class JavaLambda:
    params: tuple[str, ...]
    body: str
    body_kind: str
    text: str
    line_start: int
    line_end: int
    start_byte: int
    end_byte: int


@dataclass(frozen=True)
class JavaMethodReference:
    qualifier: str | None
    method: str
    text: str
    line_start: int
    line_end: int
    start_byte: int
    end_byte: int
    qualifier_tree: dict[str, Any] = field(default_factory=dict)
    qualifier_symbols: tuple[str, ...] = ()


@dataclass(frozen=True)
class JavaEnhancedFor:
    var: str
    type: str
    iterable: str
    text: str
    line_start: int
    line_end: int
    start_byte: int
    end_byte: int


@dataclass(frozen=True)
class JavaFieldAccess:
    receiver: str | None
    field: str
    text: str
    line_start: int
    line_end: int
    start_byte: int
    end_byte: int


@dataclass(frozen=True)
class JavaEnumConstant:
    name: str
    args: tuple[str, ...]
    text: str
    line_start: int
    line_end: int


@dataclass(frozen=True)
class JavaField:
    class_name: str
    name: str
    type: str
    raw: str
    line_start: int
    line_end: int
    annotations: tuple[JavaAnnotation, ...] = ()
    modifiers: str = ""
    initializer: str | None = None
    initializer_tree: dict[str, Any] = field(default_factory=dict)
    initializer_symbols: tuple[str, ...] = ()
    initializer_calls: tuple[JavaCall, ...] = ()
    initializer_object_creations: tuple[JavaObjectCreation, ...] = ()
    documentation: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class JavaMethod:
    class_name: str
    class_kind: str
    name: str
    return_type: str
    params: tuple[JavaParam, ...]
    raw_params: str
    modifiers: str
    annotations: tuple[JavaAnnotation, ...]
    annotation_window: str
    text: str
    body: str
    file: Path
    line_start: int
    line_end: int
    calls: tuple[JavaCall, ...] = ()
    assignments: tuple[JavaAssignment, ...] = ()
    returns: tuple[JavaReturn, ...] = ()
    object_creations: tuple[JavaObjectCreation, ...] = ()
    lambdas: tuple[JavaLambda, ...] = ()
    method_references: tuple[JavaMethodReference, ...] = ()
    enhanced_for: tuple[JavaEnhancedFor, ...] = ()
    field_accesses: tuple[JavaFieldAccess, ...] = ()
    body_line_start: int | None = None
    body_line_end: int | None = None

    @property
    def operation(self) -> str:
        return f"{self.class_name}.{self.name}"


@dataclass(frozen=True)
class JavaInitializer:
    class_name: str
    is_static: bool
    text: str
    file: Path
    line_start: int
    line_end: int
    calls: tuple[JavaCall, ...] = ()
    assignments: tuple[JavaAssignment, ...] = ()
    object_creations: tuple[JavaObjectCreation, ...] = ()

    @property
    def operation(self) -> str:
        label = "<clinit>" if self.is_static else f"<initializer@{self.line_start}>"
        return f"{self.class_name}.{label}"


@dataclass(frozen=True)
class JavaClass:
    name: str
    kind: str
    file: Path
    package: str
    annotations: tuple[JavaAnnotation, ...]
    modifiers: str
    text: str
    line_start: int
    line_end: int
    modifier_tokens: tuple[str, ...] = ()
    type_parameters: tuple[str, ...] = ()
    extends: str | None = None
    extends_base: str | None = None
    extends_type_arguments: tuple[str, ...] = ()
    implements: tuple[str, ...] = ()
    implements_bases: tuple[str, ...] = ()
    implements_type_arguments: tuple[tuple[str, ...], ...] = ()
    super_types: tuple[str, ...] = ()
    enum_constants: tuple[JavaEnumConstant, ...] = ()
    fields: tuple[JavaField, ...] = ()
    methods: tuple[JavaMethod, ...] = ()
    initializers: tuple[JavaInitializer, ...] = ()
    documentation: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class JavaSyntaxFile:
    file: Path
    text: str
    package: str
    imports: tuple[str, ...]
    classes: tuple[JavaClass, ...]
    parse_errors: int = 0
    provider: str = JAVA_SYNTAX_PROVIDER
    tree: Any = field(default=None, repr=False, compare=False)

    @property
    def root_node(self) -> Any | None:
        return self.tree.root_node if self.tree is not None else None

    @property
    def source_bytes(self) -> bytes:
        return _utf8_bytes(self.text)

    def node_text(self, node: Any | None) -> str:
        return _text(self.text, node)

    def node_location(self, node: Any) -> dict[str, Any]:
        return {
            "node_type": node.type,
            "start_byte": int(node.start_byte),
            "end_byte": int(node.end_byte),
            "start_point": [int(node.start_point[0]) + 1, int(node.start_point[1]) + 1],
            "end_point": [int(node.end_point[0]) + 1, int(node.end_point[1]) + 1],
        }

    @property
    def methods(self) -> tuple[JavaMethod, ...]:
        return tuple(m for c in self.classes for m in c.methods)

    @property
    def fields(self) -> tuple[JavaField, ...]:
        return tuple(f for c in self.classes for f in c.fields)


@dataclass(frozen=True)
class JavaMethodContext:
    parsed_file: JavaSyntaxFile
    java_class: JavaClass
    method: JavaMethod
    imports: tuple[str, ...]

    @property
    def operation(self) -> str:
        return self.method.operation

    def syntax_dict(self) -> dict[str, Any]:
        return method_syntax_dict(self.method)


@dataclass(frozen=True)
class JavaSyntaxWorkspace:
    parsed_files: tuple[JavaSyntaxFile, ...]
    warnings: tuple[str, ...]
    provider: str = JAVA_SYNTAX_PROVIDER

    @property
    def classes(self) -> tuple[JavaClass, ...]:
        return tuple(c for f in self.parsed_files for c in f.classes)

    @property
    def methods(self) -> tuple[JavaMethod, ...]:
        return tuple(m for f in self.parsed_files for m in f.methods)

    @property
    def method_contexts(self) -> tuple[JavaMethodContext, ...]:
        contexts: list[JavaMethodContext] = []
        for parsed in self.parsed_files:
            for cls in parsed.classes:
                for method in cls.methods:
                    contexts.append(JavaMethodContext(parsed_file=parsed, java_class=cls, method=method, imports=parsed.imports))
        return tuple(contexts)

    @property
    def parse_errors(self) -> int:
        return sum(f.parse_errors for f in self.parsed_files)

    def diagnostics(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "files_parsed": len(self.parsed_files),
            "classes_extracted": len(self.classes),
            "methods_extracted": len(self.methods),
            "parse_errors": self.parse_errors,
            "warnings": list(self.warnings),
            **java_syntax_cache_stats(),
        }


def tree_sitter_available() -> tuple[bool, str]:
    if Language is None or Parser is None or tsjava is None:
        return False, "tree-sitter or tree-sitter-java is not importable"
    try:
        _parser()
        return True, "ok"
    except Exception as exc:  # pragma: no cover
        return False, str(exc)


@lru_cache(maxsize=1)
def _language() -> Any:
    if Language is None or tsjava is None:
        raise RuntimeError("tree-sitter Java parser is unavailable; install tree-sitter and tree-sitter-java")
    return Language(tsjava.language())


@lru_cache(maxsize=1)
def _parser() -> Any:
    if Parser is None:
        raise RuntimeError("tree-sitter parser is unavailable; install tree-sitter")
    return Parser(_language())


@lru_cache(maxsize=128)
def _utf8_bytes(text: str) -> bytes:
    return text.encode("utf-8")


def _text(text: str, node: Any | None) -> str:
    if node is None:
        return ""
    # Tree-sitter reports UTF-8 byte offsets, while Python string slicing uses
    # Unicode code-point indexes. Real applications often contain Cyrillic
    # comments/Javadocs before declarations; slicing the str directly shifts
    # later nodes and corrupts class/method names. Slice encoded bytes instead.
    return _utf8_bytes(text)[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def _line_start(node: Any | None) -> int | None:
    if node is None:
        return None
    return int(node.start_point[0]) + 1


def _line_end(node: Any | None) -> int | None:
    if node is None:
        return None
    return int(node.end_point[0]) + 1


def _field(node: Any, name: str) -> Any | None:
    try:
        value = node.child_by_field_name(name)
        if value is not None:
            return value
    except Exception:
        pass
    # Tree-sitter Java does not expose every grammar component as a named field
    # in the Python API (notably modifiers). Provide a stable fallback by node type.
    type_fallbacks = {
        "modifiers": {"modifiers"},
        "body": {"class_body", "interface_body", "enum_body", "record_body", "block"},
        "parameters": {"formal_parameters", "record_declaration_parameters"},
        "type": {"type_identifier", "generic_type", "integral_type", "floating_point_type", "boolean_type", "void_type", "scoped_type_identifier", "array_type"},
        "name": {"identifier", "type_identifier"},
        "interfaces": {"super_interfaces", "extends_interfaces"},
        "superclass": {"superclass"},
        "arguments": {"annotation_argument_list", "argument_list"},
    }.get(name)
    if type_fallbacks:
        for child in getattr(node, "children", []) or []:
            if child.type in type_fallbacks:
                return child
    return None


def _named_children(node: Any) -> list[Any]:
    return [c for c in node.children if getattr(c, "is_named", False)]


def _children_of_type(node: Any, types: set[str]) -> list[Any]:
    return [c for c in _named_children(node) if c.type in types]


def _walk(node: Any) -> Iterable[Any]:
    yield node
    for child in getattr(node, "children", []) or []:
        yield from _walk(child)


def _first_named_identifier_text(text: str, node: Any | None) -> str | None:
    if node is None:
        return None
    if node.type in {"identifier", "type_identifier", "scoped_identifier"}:
        return _text(text, node)
    for child in _walk(node):
        if child.type in {"identifier", "type_identifier", "scoped_identifier"}:
            return _text(text, child)
    return None


def _simple_annotation_name(value: str) -> str:
    return value.split(".")[-1].strip()


def _normalized_node_text(text: str, node: Any | None, *, max_chars: int = 800) -> str:
    value = " ".join(_text(text, node).split()).strip()
    return value[:max_chars]


def _expression_tree_from_node(
    text: str,
    node: Any | None,
    *,
    max_depth: int = 14,
    max_nodes: int = 256,
) -> dict[str, Any]:
    """Serialize a compact bounded expression tree directly from Tree-sitter nodes.

    Raw text and byte bounds are retained at the expression root. Descendants keep
    Tree-sitter node/field/operator structure and leaf values, avoiding repeated
    source fragments while preserving deterministic reconstruction evidence.
    """
    if node is None:
        return {}
    budget = {"remaining": max_nodes}
    literal_types = {
        "string_literal", "character_literal", "decimal_integer_literal",
        "hex_integer_literal", "octal_integer_literal", "binary_integer_literal",
        "decimal_floating_point_literal", "hex_floating_point_literal",
        "true", "false", "null_literal", "class_literal",
    }

    def visit(current: Any, depth: int, field_name: str | None = None, *, root: bool = False) -> dict[str, Any]:
        budget["remaining"] -= 1
        node_type = str(current.type)
        result: dict[str, Any] = {"node_type": node_type}
        if field_name:
            result["field"] = field_name
        if root:
            result.update({
                "text": _normalized_node_text(text, current),
                "start_byte": int(current.start_byte),
                "end_byte": int(current.end_byte),
            })
        operator_node = None
        try:
            operator_node = current.child_by_field_name("operator")
        except Exception:
            operator_node = None
        if operator_node is not None:
            result["operator"] = _normalized_node_text(text, operator_node, max_chars=40)
        named_children = [child for child in (getattr(current, "children", ()) or ()) if getattr(child, "is_named", False)]
        if not named_children or node_type in literal_types:
            result["value"] = _normalized_node_text(text, current)
        if depth >= max_depth or budget["remaining"] <= 0:
            result["truncated"] = True
            return result
        children: list[dict[str, Any]] = []
        for index, child in enumerate(getattr(current, "children", ()) or ()):
            if budget["remaining"] <= 0:
                break
            child_field = None
            try:
                child_field = current.field_name_for_child(index)
            except Exception:
                child_field = None
            if not getattr(child, "is_named", False) and child_field != "operator":
                continue
            children.append(visit(child, depth + 1, child_field))
        if children:
            result["children"] = children
        if budget["remaining"] <= 0:
            result["truncated"] = True
        return result

    return visit(node, 0, root=True)

def _expression_symbols_from_node(text: str, node: Any | None) -> tuple[str, ...]:
    """Collect value-bearing symbols from Tree-sitter expression nodes."""
    if node is None:
        return ()
    found: list[str] = []

    def add(value: str) -> None:
        normalized = " ".join(value.split()).strip()
        if normalized and normalized not in found:
            found.append(normalized)

    def walk(current: Any, parent_type: str | None = None, field_name: str | None = None) -> None:
        node_type = str(current.type)
        if node_type == "method_invocation":
            object_node = _field(current, "object")
            name_node = _field(current, "name")
            if object_node is not None and name_node is not None:
                add(f"{_normalized_node_text(text, object_node)}.{_normalized_node_text(text, name_node)}")
            if object_node is not None:
                walk(object_node, node_type, "object")
            arguments_node = _field(current, "arguments")
            if arguments_node is not None:
                for child in _named_children(arguments_node):
                    walk(child, "argument_list", None)
            return
        if node_type == "field_access":
            add(_normalized_node_text(text, current))
            object_node = _field(current, "object")
            if object_node is not None:
                walk(object_node, node_type, "object")
            return
        if node_type in {"identifier", "scoped_identifier"}:
            if not (parent_type == "method_invocation" and field_name == "name") and not (parent_type == "field_access" and field_name == "field"):
                add(_normalized_node_text(text, current))
            return
        if node_type == "object_creation_expression":
            arguments_node = _field(current, "arguments")
            if arguments_node is not None:
                for child in _named_children(arguments_node):
                    walk(child, "argument_list", None)
            return
        for index, child in enumerate(getattr(current, "children", ()) or ()):
            if not getattr(child, "is_named", False):
                continue
            child_field = None
            try:
                child_field = current.field_name_for_child(index)
            except Exception:
                child_field = None
            walk(child, node_type, child_field)

    walk(node)
    return tuple(found)


def _argument_nodes(arguments_node: Any | None) -> tuple[Any, ...]:
    if arguments_node is None:
        return ()
    return tuple(_named_children(arguments_node))


def _structured_annotation_arguments(text: str, node: Any) -> tuple[dict[str, Any], ...]:
    args_node = _field(node, "arguments")
    if args_node is None:
        return ()
    result: list[dict[str, Any]] = []
    positional_index = 0
    for child in _named_children(args_node):
        key: str | None = None
        value_node = child
        if child.type == "element_value_pair":
            key_node = _field(child, "key")
            value_node = _field(child, "value")
            key = _normalized_node_text(text, key_node) if key_node is not None else None
        else:
            key = "value" if positional_index == 0 else f"value[{positional_index}]"
            positional_index += 1
        if value_node is None:
            continue
        result.append({
            "name": key,
            "raw": _normalized_node_text(text, value_node),
            "node_type": str(value_node.type),
            "expression_tree": _expression_tree_from_node(text, value_node),
            "input_symbols": list(_expression_symbols_from_node(text, value_node)),
        })
    return tuple(result)


def _annotation_name(text: str, node: Any) -> str:
    name_node = _field(node, "name")
    value = _text(text, name_node).strip() if name_node is not None else _text(text, node).strip().lstrip("@").split("(", 1)[0]
    return _simple_annotation_name(value)


def _annotation_args(text: str, node: Any) -> str | None:
    args_node = _field(node, "arguments")
    if args_node is None:
        raw = _text(text, node)
        if "(" in raw and raw.endswith(")"):
            return raw[raw.find("(") + 1:-1]
        return None
    raw = _text(text, args_node)
    if raw.startswith("(") and raw.endswith(")"):
        return raw[1:-1]
    return raw or None


def _annotations_from_modifiers(text: str, modifiers: Any | None) -> tuple[JavaAnnotation, ...]:
    if modifiers is None:
        return ()
    annotations: list[JavaAnnotation] = []
    for child in _named_children(modifiers):
        if child.type in {"annotation", "marker_annotation"}:
            annotations.append(JavaAnnotation(
                name=_annotation_name(text, child),
                text=_text(text, child).strip(),
                arguments=_annotation_args(text, child),
                line_start=_line_start(child) or 1,
                line_end=_line_end(child) or (_line_start(child) or 1),
                structured_arguments=_structured_annotation_arguments(text, child),
            ))
    return tuple(annotations)


def _modifiers_text_without_annotations(text: str, modifiers: Any | None) -> str:
    if modifiers is None:
        return ""
    parts: list[str] = []
    for child in modifiers.children:
        if child.type not in {"annotation", "marker_annotation"}:
            val = _text(text, child).strip()
            if val:
                parts.append(val)
    return " ".join(parts)


def _node_type_text(text: str, node: Any | None) -> str:
    if node is None:
        return "unknown"
    return " ".join(_text(text, node).replace("\n", " ").split()) or "unknown"


def _strip_param_decorations(raw: str) -> str:
    # Preserve generic type text, but remove common annotations/modifiers from the compact param type.
    import re
    cleaned = re.sub(r"@\w+(?:\([^)]*\))?\s*", "", raw)
    cleaned = re.sub(r"\b(final|@Valid)\b", "", cleaned).strip()
    return " ".join(cleaned.split())


def _parse_parameter(text: str, node: Any) -> JavaParam | None:
    name_node = _field(node, "name")
    type_node = _field(node, "type")
    if name_node is None:
        return None
    raw = _text(text, node).strip()
    name = _text(text, name_node).strip()
    typ = _node_type_text(text, type_node)
    annotations = _annotations_from_modifiers(text, _field(node, "modifiers"))
    if not typ or typ == "unknown":
        cleaned = _strip_param_decorations(raw)
        toks = cleaned.split()
        if len(toks) >= 2:
            typ = " ".join(toks[:-1])
    return JavaParam(name=name, type=typ or "unknown", raw=raw, annotations=annotations)


def _parse_params(text: str, params_node: Any | None) -> tuple[JavaParam, ...]:
    if params_node is None:
        return ()
    params: list[JavaParam] = []
    for child in _named_children(params_node):
        if child.type in {"formal_parameter", "spread_parameter", "receiver_parameter"}:
            param = _parse_parameter(text, child)
            if param:
                params.append(param)
    return tuple(params)


def _parse_field(text: str, class_name: str, node: Any) -> list[JavaField]:
    type_node = _field(node, "type")
    typ = _node_type_text(text, type_node)
    modifiers_node = _field(node, "modifiers")
    annotations = _annotations_from_modifiers(text, modifiers_node)
    modifier_text = _modifiers_text_without_annotations(text, modifiers_node)
    documentation = _javadoc_before_node(text, node)
    fields: list[JavaField] = []
    for child in _named_children(node):
        if child.type != "variable_declarator":
            continue
        name_node = _field(child, "name")
        name = _text(text, name_node).strip() if name_node is not None else ""
        if not name:
            continue
        value_node = _field(child, "value")
        initializer = " ".join(_text(text, value_node).split()).strip() if value_node is not None else None
        calls, _assignments, _returns, creations, _lambdas, _method_refs, _loops, _field_accesses = _method_syntax_elements(text, value_node)
        fields.append(JavaField(
            class_name=class_name,
            name=name,
            type=typ,
            raw=_text(text, node).strip(),
            line_start=_line_start(node) or 1,
            line_end=_line_end(node) or (_line_start(node) or 1),
            annotations=annotations,
            modifiers=modifier_text,
            initializer=initializer,
            initializer_tree=_expression_tree_from_node(text, value_node),
            initializer_symbols=_expression_symbols_from_node(text, value_node),
            initializer_calls=calls,
            initializer_object_creations=creations,
            documentation=documentation,
        ))
    return fields


def _parse_record_components(text: str, class_name: str, node: Any) -> list[JavaField]:
    fields: list[JavaField] = []
    params_node = _field(node, "parameters") or _field(node, "body")
    if params_node is None:
        return fields
    for child in _walk(params_node):
        if child.type not in {"formal_parameter", "spread_parameter"}:
            continue
        param = _parse_parameter(text, child)
        if not param:
            continue
        fields.append(JavaField(
            class_name=class_name,
            name=param.name,
            type=param.type,
            raw=param.raw,
            line_start=_line_start(child) or 1,
            line_end=_line_end(child) or (_line_start(child) or 1),
            annotations=param.annotations,
        ))
    return fields



def split_java_arguments(args_text: str | None) -> tuple[str, ...]:
    """Split a Java argument-list string without using regex-level syntax parsing."""
    if not args_text:
        return ()
    raw = args_text.strip()
    if raw.startswith("(") and raw.endswith(")"):
        raw = raw[1:-1]
    out: list[str] = []
    cur: list[str] = []
    depth = 0
    in_string = False
    quote = ""
    esc = False
    for ch in raw:
        if in_string:
            cur.append(ch)
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == quote:
                in_string = False
            continue
        if ch in {"'", '"'}:
            in_string = True
            quote = ch
            cur.append(ch)
            continue
        if ch in "([{<":
            depth += 1
            cur.append(ch)
            continue
        if ch in ")]}>":
            depth = max(0, depth - 1)
            cur.append(ch)
            continue
        if ch == "," and depth == 0:
            value = " ".join("".join(cur).split()).strip()
            if value:
                out.append(value)
            cur = []
            continue
        cur.append(ch)
    value = " ".join("".join(cur).split()).strip()
    if value:
        out.append(value)
    return tuple(out)


def _parse_call(text: str, node: Any) -> JavaCall | None:
    name_node = _field(node, "name")
    args_node = _field(node, "arguments")
    if name_node is None:
        return None
    method = _text(text, name_node).strip()
    receiver_node = _field(node, "object")
    receiver = _text(text, receiver_node).strip() if receiver_node is not None else None
    args_text = _text(text, args_node).strip() if args_node is not None else ""
    argument_nodes = _argument_nodes(args_node)
    scope_start, scope_end, scope_depth = _lexical_scope_coordinates(node)
    return JavaCall(
        receiver=receiver,
        method=method,
        args=tuple(_normalized_node_text(text, item) for item in argument_nodes),
        args_text=args_text[1:-1] if args_text.startswith("(") and args_text.endswith(")") else args_text,
        text=_text(text, node).strip(),
        line_start=_line_start(node) or 1,
        line_end=_line_end(node) or (_line_start(node) or 1),
        start_byte=int(node.start_byte),
        end_byte=int(node.end_byte),
        is_unqualified=receiver is None,
        argument_trees=tuple(_expression_tree_from_node(text, item) for item in argument_nodes),
        argument_symbols=tuple(_expression_symbols_from_node(text, item) for item in argument_nodes),
        receiver_tree=_expression_tree_from_node(text, receiver_node) if receiver_node is not None else {},
        receiver_symbols=_expression_symbols_from_node(text, receiver_node) if receiver_node is not None else (),
        lexical_scope_start_byte=scope_start,
        lexical_scope_end_byte=scope_end,
        lexical_scope_depth=scope_depth,
    )


def _type_from_local_declaration(text: str, declarator_node: Any) -> str | None:
    parent = getattr(declarator_node, "parent", None)
    if parent is not None and parent.type in {"local_variable_declaration", "field_declaration"}:
        type_node = _field(parent, "type")
        if type_node is not None:
            return _node_type_text(text, type_node)
    return None


def _parse_assignment(text: str, node: Any) -> JavaAssignment | None:
    scope_start, scope_end, scope_depth = _lexical_scope_coordinates(node)
    if node.type == "variable_declarator":
        name_node = _field(node, "name")
        value_node = _field(node, "value")
        if name_node is None:
            return None
        # Keep declarations without an initializer.  They are required to
        # distinguish a method-local value assigned in several branches from
        # an implicit class-field write.  Consumers that need an initializer
        # continue to see an empty expression and can ignore it.
        expression = " ".join(_text(text, value_node).split()).strip() if value_node is not None else ""
        return JavaAssignment(
            target=_text(text, name_node).strip(),
            expression=expression,
            text=_text(text, node).strip(),
            line_start=_line_start(node) or 1,
            line_end=_line_end(node) or (_line_start(node) or 1),
            start_byte=int(node.start_byte),
            end_byte=int(node.end_byte),
            declared_type=_type_from_local_declaration(text, node),
            assignment_kind="variable_declaration",
            expression_tree=_expression_tree_from_node(text, value_node) if value_node is not None else {},
            input_symbols=_expression_symbols_from_node(text, value_node) if value_node is not None else (),
            lexical_scope_start_byte=scope_start,
            lexical_scope_end_byte=scope_end,
            lexical_scope_depth=scope_depth,
        )
    if node.type == "assignment_expression":
        left_node = _field(node, "left")
        right_node = _field(node, "right")
        if left_node is None or right_node is None:
            return None
        return JavaAssignment(
            target=" ".join(_text(text, left_node).split()).strip(),
            expression=" ".join(_text(text, right_node).split()).strip(),
            text=_text(text, node).strip(),
            line_start=_line_start(node) or 1,
            line_end=_line_end(node) or (_line_start(node) or 1),
            start_byte=int(node.start_byte),
            end_byte=int(node.end_byte),
            declared_type=None,
            assignment_kind="assignment_expression",
            expression_tree=_expression_tree_from_node(text, right_node),
            input_symbols=_expression_symbols_from_node(text, right_node),
            lexical_scope_start_byte=scope_start,
            lexical_scope_end_byte=scope_end,
            lexical_scope_depth=scope_depth,
        )
    return None


def _parse_return(text: str, node: Any) -> JavaReturn | None:
    expr_node = next((c for c in _named_children(node) if c.type != "comment"), None)
    if expr_node is None:
        return None
    scope_start, scope_end, scope_depth = _lexical_scope_coordinates(node)
    return JavaReturn(
        expression=" ".join(_text(text, expr_node).split()).strip(),
        text=_text(text, node).strip(),
        line_start=_line_start(node) or 1,
        line_end=_line_end(node) or (_line_start(node) or 1),
        start_byte=int(node.start_byte),
        end_byte=int(node.end_byte),
        expression_tree=_expression_tree_from_node(text, expr_node),
        input_symbols=_expression_symbols_from_node(text, expr_node),
        lexical_scope_start_byte=scope_start,
        lexical_scope_end_byte=scope_end,
        lexical_scope_depth=scope_depth,
    )


def _parse_object_creation(text: str, node: Any) -> JavaObjectCreation | None:
    type_node = _field(node, "type") or _field(node, "name")
    args_node = _field(node, "arguments")
    if type_node is None:
        return None
    args_text = _text(text, args_node).strip() if args_node is not None else ""
    argument_nodes = _argument_nodes(args_node)
    return JavaObjectCreation(
        type=_node_type_text(text, type_node),
        args=tuple(_normalized_node_text(text, item) for item in argument_nodes),
        args_text=args_text[1:-1] if args_text.startswith("(") and args_text.endswith(")") else args_text,
        text=_text(text, node).strip(),
        line_start=_line_start(node) or 1,
        line_end=_line_end(node) or (_line_start(node) or 1),
        start_byte=int(node.start_byte),
        end_byte=int(node.end_byte),
        argument_trees=tuple(_expression_tree_from_node(text, item) for item in argument_nodes),
        argument_symbols=tuple(_expression_symbols_from_node(text, item) for item in argument_nodes),
    )


def _parse_lambda(text: str, node: Any) -> JavaLambda | None:
    params_node = _field(node, "parameters")
    body_node = _field(node, "body")
    params: list[str] = []
    if params_node is not None:
        if params_node.type == "identifier":
            params.append(_text(text, params_node).strip())
        else:
            for child in _walk(params_node):
                if child.type == "identifier":
                    value = _text(text, child).strip()
                    if value and value not in params:
                        params.append(value)
    return JavaLambda(
        params=tuple(params),
        body=" ".join(_text(text, body_node).split()).strip() if body_node is not None else "",
        body_kind=getattr(body_node, "type", "unknown") if body_node is not None else "unknown",
        text=_text(text, node).strip(),
        line_start=_line_start(node) or 1,
        line_end=_line_end(node) or (_line_start(node) or 1),
        start_byte=int(node.start_byte),
        end_byte=int(node.end_byte),
    )


def _parse_method_reference(text: str, node: Any) -> JavaMethodReference | None:
    raw = _text(text, node).strip()
    if "::" not in raw:
        return None
    qualifier, method = raw.rsplit("::", 1)
    method = method.strip()
    qualifier_node = next((child for child in _named_children(node) if child.end_byte <= node.end_byte and _text(text, child).strip() == qualifier.strip()), None)
    if not method:
        return None
    return JavaMethodReference(
        qualifier=qualifier.strip() or None,
        method=method,
        text=raw,
        qualifier_tree=_expression_tree_from_node(text, qualifier_node) if qualifier_node is not None else {},
        qualifier_symbols=_expression_symbols_from_node(text, qualifier_node) if qualifier_node is not None else (),
        line_start=_line_start(node) or 1,
        line_end=_line_end(node) or (_line_start(node) or 1),
        start_byte=int(node.start_byte),
        end_byte=int(node.end_byte),
    )


def _parse_enhanced_for(text: str, node: Any) -> JavaEnhancedFor | None:
    type_node = _field(node, "type")
    name_node = _field(node, "name")
    value_node = _field(node, "value")
    if name_node is None or value_node is None:
        return None
    return JavaEnhancedFor(
        var=_text(text, name_node).strip(),
        type=_node_type_text(text, type_node),
        iterable=" ".join(_text(text, value_node).split()).strip(),
        text=_text(text, node).strip(),
        line_start=_line_start(node) or 1,
        line_end=_line_end(node) or (_line_start(node) or 1),
        start_byte=int(node.start_byte),
        end_byte=int(node.end_byte),
    )


def _parse_field_access(text: str, node: Any) -> JavaFieldAccess | None:
    receiver_node = _field(node, "object")
    field_node = _field(node, "field") or _field(node, "name")
    if field_node is None:
        return None
    return JavaFieldAccess(
        receiver=_text(text, receiver_node).strip() if receiver_node is not None else None,
        field=_text(text, field_node).strip(),
        text=_text(text, node).strip(),
        line_start=_line_start(node) or 1,
        line_end=_line_end(node) or (_line_start(node) or 1),
        start_byte=int(node.start_byte),
        end_byte=int(node.end_byte),
    )


def _method_syntax_elements(text: str, body_node: Any | None) -> tuple[tuple[JavaCall, ...], tuple[JavaAssignment, ...], tuple[JavaReturn, ...], tuple[JavaObjectCreation, ...], tuple[JavaLambda, ...], tuple[JavaMethodReference, ...], tuple[JavaEnhancedFor, ...], tuple[JavaFieldAccess, ...]]:
    if body_node is None:
        return (), (), (), (), (), (), (), ()
    calls: list[JavaCall] = []
    assignments: list[JavaAssignment] = []
    returns: list[JavaReturn] = []
    creations: list[JavaObjectCreation] = []
    lambdas: list[JavaLambda] = []
    method_refs: list[JavaMethodReference] = []
    enhanced_for: list[JavaEnhancedFor] = []
    field_accesses: list[JavaFieldAccess] = []
    seen_assignment_spans: set[tuple[int, int]] = set()
    for child in _walk(body_node):
        if child.type == "method_invocation":
            call = _parse_call(text, child)
            if call:
                calls.append(call)
        elif child.type in {"variable_declarator", "assignment_expression"}:
            assignment = _parse_assignment(text, child)
            if assignment:
                key = (assignment.start_byte, assignment.end_byte)
                if key not in seen_assignment_spans:
                    assignments.append(assignment)
                    seen_assignment_spans.add(key)
        elif child.type == "return_statement":
            ret = _parse_return(text, child)
            if ret:
                returns.append(ret)
        elif child.type == "object_creation_expression":
            creation = _parse_object_creation(text, child)
            if creation:
                creations.append(creation)
        elif child.type == "lambda_expression":
            lam = _parse_lambda(text, child)
            if lam:
                lambdas.append(lam)
        elif child.type == "method_reference":
            ref = _parse_method_reference(text, child)
            if ref:
                method_refs.append(ref)
        elif child.type == "enhanced_for_statement":
            loop = _parse_enhanced_for(text, child)
            if loop:
                enhanced_for.append(loop)
        elif child.type == "field_access":
            access = _parse_field_access(text, child)
            if access:
                field_accesses.append(access)
    return (
        tuple(sorted(calls, key=lambda c: c.start_byte)),
        tuple(sorted(assignments, key=lambda a: a.start_byte)),
        tuple(sorted(returns, key=lambda r: r.start_byte)),
        tuple(sorted(creations, key=lambda c: c.start_byte)),
        tuple(sorted(lambdas, key=lambda l: l.start_byte)),
        tuple(sorted(method_refs, key=lambda r: r.start_byte)),
        tuple(sorted(enhanced_for, key=lambda f: f.start_byte)),
        tuple(sorted(field_accesses, key=lambda f: f.start_byte)),
    )

def _parse_method(text: str, file: Path, class_name: str, class_kind: str, node: Any) -> JavaMethod | None:
    name_node = _field(node, "name")
    if name_node is None:
        return None
    name = _text(text, name_node).strip()
    return_node = _field(node, "type")
    if node.type == "constructor_declaration":
        return_type = class_name
    else:
        return_type = _node_type_text(text, return_node)
    params_node = _field(node, "parameters")
    params = _parse_params(text, params_node)
    modifiers = _field(node, "modifiers")
    annotations = _annotations_from_modifiers(text, modifiers)
    body_node = _field(node, "body")
    body = _text(text, body_node) if body_node is not None else ""
    raw_params = _text(text, params_node).strip()[1:-1] if params_node is not None and _text(text, params_node).strip().startswith("(") else _text(text, params_node)
    calls, assignments, returns, object_creations, lambdas, method_references, enhanced_for, field_accesses = _method_syntax_elements(text, body_node)
    return JavaMethod(
        class_name=class_name,
        class_kind=class_kind,
        name=name,
        return_type=return_type,
        params=params,
        raw_params=raw_params or "",
        modifiers=_modifiers_text_without_annotations(text, modifiers),
        annotations=annotations,
        annotation_window="\n".join(a.text for a in annotations),
        text=_text(text, node),
        body=body,
        file=file,
        line_start=_line_start(node) or 1,
        line_end=_line_end(node) or (_line_start(node) or 1),
        calls=calls,
        assignments=assignments,
        returns=returns,
        object_creations=object_creations,
        lambdas=lambdas,
        method_references=method_references,
        enhanced_for=enhanced_for,
        field_accesses=field_accesses,
        body_line_start=_line_start(body_node),
        body_line_end=_line_end(body_node),
    )



def _parse_initializer(text: str, file: Path, class_name: str, node: Any, *, is_static: bool) -> JavaInitializer:
    calls, assignments, _returns, creations, _lambdas, _method_refs, _loops, _field_accesses = _method_syntax_elements(text, node)
    return JavaInitializer(
        class_name=class_name,
        is_static=is_static,
        text=_text(text, node),
        file=file,
        line_start=_line_start(node) or 1,
        line_end=_line_end(node) or (_line_start(node) or 1),
        calls=calls,
        assignments=assignments,
        object_creations=creations,
    )


def _parse_enum_constants(text: str, body: Any | None) -> tuple[JavaEnumConstant, ...]:
    if body is None:
        return ()
    constants: list[JavaEnumConstant] = []
    for child in _named_children(body):
        if child.type != "enum_constant":
            continue
        name_node = _field(child, "name")
        if name_node is None:
            name_node = next((n for n in _named_children(child) if n.type == "identifier"), None)
        name = _text(text, name_node).strip() if name_node is not None else ""
        if not name:
            continue
        args_node = _field(child, "arguments")
        args_text = _text(text, args_node).strip() if args_node is not None else ""
        constants.append(JavaEnumConstant(
            name=name,
            args=split_java_arguments(args_text),
            text=_text(text, child).strip(),
            line_start=_line_start(child) or 1,
            line_end=_line_end(child) or (_line_start(child) or 1),
        ))
    return tuple(constants)


def _type_reference_from_node(text: str, node: Any | None) -> tuple[str, str, tuple[str, ...]]:
    """Return full text, base type and generic arguments from a Tree-sitter type node."""
    if node is None:
        return "", "", ()
    full = _node_type_text(text, node)
    if node.type == "generic_type":
        args_node = next((c for c in _named_children(node) if c.type == "type_arguments"), None)
        base_node = next((c for c in _named_children(node) if c.type != "type_arguments"), None)
        base = _node_type_text(text, base_node) if base_node is not None else full
        args = tuple(_node_type_text(text, c) for c in _named_children(args_node)) if args_node is not None else ()
        return full, base, args
    if node.type == "array_type":
        element = _field(node, "element") or _field(node, "type") or next(iter(_named_children(node)), None)
        element_full, element_base, element_args = _type_reference_from_node(text, element)
        return full, element_base or element_full, element_args
    return full, full, ()


def _direct_super_type_refs(text: str, node: Any | None) -> tuple[tuple[str, str, tuple[str, ...]], ...]:
    """Return direct supertype references from Tree-sitter superclass/interface nodes."""
    if node is None:
        return ()
    type_nodes = {
        "type_identifier", "scoped_type_identifier", "generic_type", "array_type",
        "integral_type", "floating_point_type", "boolean_type",
    }
    refs: list[tuple[str, str, tuple[str, ...]]] = []
    if node.type in type_nodes:
        ref = _type_reference_from_node(text, node)
        return (ref,) if ref[0] and ref[0] != "unknown" else ()
    for child in _named_children(node):
        if child.type == "type_list":
            for item in _named_children(child):
                if item.type in type_nodes:
                    ref = _type_reference_from_node(text, item)
                    if ref[0] and ref[0] != "unknown":
                        refs.append(ref)
        elif child.type in type_nodes:
            ref = _type_reference_from_node(text, child)
            if ref[0] and ref[0] != "unknown":
                refs.append(ref)
    return tuple(refs)


def _type_parameter_names(text: str, node: Any | None) -> tuple[str, ...]:
    """Read declared generic parameter names from Tree-sitter type_parameter nodes."""
    if node is None:
        return ()
    names: list[str] = []
    for child in _named_children(node):
        if child.type != "type_parameter":
            continue
        name_node = _field(child, "name")
        if name_node is None:
            name_node = next((c for c in _named_children(child) if c.type == "type_identifier"), None)
        value = _text(text, name_node).strip() if name_node is not None else ""
        if value:
            names.append(value)
    return tuple(names)


def _parse_class(text: str, file: Path, package: str, node: Any) -> JavaClass | None:
    name_node = _field(node, "name")
    if name_node is None:
        return None
    name = _text(text, name_node).strip()
    kind = node.type.replace("_declaration", "")
    if kind == "class":
        kind = "class"
    modifiers = _field(node, "modifiers")
    annotations = _annotations_from_modifiers(text, modifiers)
    documentation = _javadoc_before_node(text, node)
    modifier_text = _modifiers_text_without_annotations(text, modifiers)
    modifier_tokens = tuple(part for part in modifier_text.split() if part)
    type_parameters_node = _field(node, "type_parameters")
    if type_parameters_node is None:
        type_parameters_node = next((c for c in _named_children(node) if c.type == "type_parameters"), None)
    type_parameters = _type_parameter_names(text, type_parameters_node)
    body = _field(node, "body")
    extends_node = _field(node, "superclass")
    interfaces_node = _field(node, "interfaces")
    extends_refs = _direct_super_type_refs(text, extends_node)
    interface_refs = _direct_super_type_refs(text, interfaces_node)
    # Interfaces use an extends_interfaces node; semantically those are still interface parents.
    if node.type == "interface_declaration" and extends_node is None and interfaces_node is not None:
        extends_refs = interface_refs
        interface_refs = ()
    super_types = tuple(dict.fromkeys([r[0] for r in extends_refs + interface_refs]))
    enum_constants = _parse_enum_constants(text, body) if node.type == "enum_declaration" else ()
    fields: list[JavaField] = []
    methods: list[JavaMethod] = []
    initializers: list[JavaInitializer] = []
    if node.type == "record_declaration":
        fields.extend(_parse_record_components(text, name, node))
    if body is not None:
        for child in _named_children(body):
            if child.type == "field_declaration":
                fields.extend(_parse_field(text, name, child))
            elif child.type in {"method_declaration", "constructor_declaration"}:
                method = _parse_method(text, file, name, kind, child)
                if method:
                    methods.append(method)
            elif child.type == "static_initializer":
                initializers.append(_parse_initializer(text, file, name, child, is_static=True))
            elif child.type == "block":
                initializers.append(_parse_initializer(text, file, name, child, is_static=False))
    return JavaClass(
        name=name,
        kind=kind,
        file=file,
        package=package,
        annotations=annotations,
        modifiers=modifier_text,
        text=_text(text, node),
        line_start=_line_start(node) or 1,
        line_end=_line_end(node) or (_line_start(node) or 1),
        modifier_tokens=modifier_tokens,
        type_parameters=type_parameters,
        extends=extends_refs[0][0] if extends_refs else None,
        extends_base=extends_refs[0][1] if extends_refs else None,
        extends_type_arguments=extends_refs[0][2] if extends_refs else (),
        implements=tuple(r[0] for r in interface_refs),
        implements_bases=tuple(r[1] for r in interface_refs),
        implements_type_arguments=tuple(r[2] for r in interface_refs),
        super_types=super_types,
        enum_constants=enum_constants,
        fields=tuple(fields),
        methods=tuple(methods),
        initializers=tuple(initializers),
        documentation=documentation,
    )


def _package_name(text: str, root: Any) -> str:
    for node in _named_children(root):
        if node.type == "package_declaration":
            for child in _walk(node):
                if child.type == "scoped_identifier":
                    return _text(text, child).strip()
            values = [_text(text, c).strip() for c in _walk(node) if c.type == "identifier"]
            if values:
                return ".".join(values)
            raw = _text(text, node).replace("package", "", 1).rstrip(";").strip()
            return raw
    return ""


def _imports(text: str, root: Any) -> tuple[str, ...]:
    imports: list[str] = []
    for node in _named_children(root):
        if node.type == "import_declaration":
            raw = _text(text, node).strip().rstrip(";")
            raw = raw.replace("import static", "", 1).replace("import", "", 1).strip()
            imports.append(raw.rstrip(".*"))
    return tuple(imports)


def parse_java_text(text: str, file: str | Path = "<memory>") -> JavaSyntaxFile:
    parser = _parser()
    source = text.encode("utf-8", errors="replace")
    tree = parser.parse(source)
    root = tree.root_node
    package = _package_name(text, root)
    imports = _imports(text, root)
    classes: list[JavaClass] = []
    for node in _named_children(root):
        if node.type in {"class_declaration", "interface_declaration", "record_declaration", "enum_declaration"}:
            cls = _parse_class(text, Path(file), package, node)
            if cls:
                classes.append(cls)
    # Include top-level nested classes as separate classes only if tree-sitter did not expose them at root.
    seen = {(c.name, c.line_start) for c in classes}
    for node in _walk(root):
        if node.type in {"class_declaration", "interface_declaration", "record_declaration", "enum_declaration"}:
            name_node = _field(node, "name")
            key = (_text(text, name_node).strip() if name_node is not None else "", _line_start(node) or 1)
            if key not in seen:
                cls = _parse_class(text, Path(file), package, node)
                if cls:
                    classes.append(cls)
                    seen.add(key)
    parse_errors = sum(1 for n in _walk(root) if getattr(n, "is_error", False) or n.type == "ERROR")
    return JavaSyntaxFile(file=Path(file), text=text, package=package, imports=imports, classes=tuple(classes), parse_errors=parse_errors, tree=tree)



@lru_cache(maxsize=4096)
def java_type_shape(type_text: str | None) -> dict[str, Any]:
    """Parse an already observed Java type with Tree-sitter.

    The helper is used for generic substitution results such as ``List<Phone>``.
    It deliberately delegates Java grammar to Tree-sitter rather than interpreting
    nested generic syntax with regular expressions.
    """
    raw = " ".join(str(type_text or "").split()).strip()
    empty = {
        "raw_type": raw or None, "base_type": None, "simple_type": None,
        "type_arguments": [], "type_references": [], "container_kind": None,
        "element_type": None, "map_key_type": None, "map_value_type": None,
        "array_dimensions": 0, "syntax_provider": JAVA_SYNTAX_PROVIDER,
    }
    if not raw:
        return empty
    parser = _parser()
    source_text = f"class __TypeHost {{ {raw} __value; }}"
    tree = parser.parse(source_text.encode("utf-8", errors="replace"))
    root = tree.root_node
    field_node = next((n for n in _walk(root) if n.type == "field_declaration"), None)
    type_node = _field(field_node, "type") if field_node is not None else None
    if type_node is None:
        return empty

    def shape(node: Any) -> dict[str, Any]:
        text_value = _node_type_text(source_text, node)
        if node.type == "array_type":
            element_node = _field(node, "element") or _field(node, "type") or next(iter(_named_children(node)), None)
            child = shape(element_node) if element_node is not None else {}
            result = dict(child)
            result["raw_type"] = text_value
            result["array_dimensions"] = int(child.get("array_dimensions") or 0) + 1
            result["container_kind"] = "array"
            result["element_type"] = child.get("raw_type") or child.get("base_type")
            return result
        if node.type == "generic_type":
            args_node = next((c for c in _named_children(node) if c.type == "type_arguments"), None)
            base_node = next((c for c in _named_children(node) if c.type != "type_arguments"), None)
            base_text = _node_type_text(source_text, base_node) if base_node is not None else text_value
            args = [shape(c) for c in _named_children(args_node)] if args_node is not None else []
            references = [base_text]
            for arg in args:
                references.extend(arg.get("type_references") or [])
            simple = base_text.rsplit(".", 1)[-1]
            collection_names = {"List", "Set", "Collection", "Iterable", "ArrayList", "LinkedList", "Page", "Slice", "Optional", "Stream"}
            map_names = {"Map", "HashMap", "LinkedHashMap", "ConcurrentHashMap"}
            container_kind = "collection" if simple in collection_names else ("map" if simple in map_names else None)
            element = None
            map_key = None
            map_value = None
            if container_kind == "collection" and args:
                element = args[0].get("raw_type") or args[0].get("base_type")
            elif container_kind == "map":
                if args:
                    map_key = args[0].get("raw_type") or args[0].get("base_type")
                if len(args) > 1:
                    map_value = args[1].get("raw_type") or args[1].get("base_type")
                    element = map_value
            return {
                "raw_type": text_value, "base_type": base_text, "simple_type": simple,
                "type_arguments": args, "type_references": list(dict.fromkeys(references)),
                "container_kind": container_kind, "element_type": element,
                "map_key_type": map_key, "map_value_type": map_value,
                "array_dimensions": 0, "syntax_provider": JAVA_SYNTAX_PROVIDER,
            }
        if node.type in {"wildcard", "wildcard_type_argument", "type_bound"}:
            children = [shape(c) for c in _named_children(node)]
            refs: list[str] = []
            for child in children:
                refs.extend(child.get("type_references") or [])
            return {
                "raw_type": text_value, "base_type": None, "simple_type": None,
                "type_arguments": children, "type_references": list(dict.fromkeys(refs)),
                "container_kind": None, "element_type": None, "map_key_type": None,
                "map_value_type": None, "array_dimensions": 0, "syntax_provider": JAVA_SYNTAX_PROVIDER,
            }
        base_text = text_value
        simple = base_text.rsplit(".", 1)[-1]
        return {
            "raw_type": text_value, "base_type": base_text, "simple_type": simple,
            "type_arguments": [], "type_references": [base_text],
            "container_kind": None, "element_type": None, "map_key_type": None,
            "map_value_type": None, "array_dimensions": 0, "syntax_provider": JAVA_SYNTAX_PROVIDER,
        }

    result = shape(type_node)
    result["raw_type"] = raw
    return result

_JAVA_FILE_PARSE_CACHE: dict[str, tuple[tuple[int, int], JavaSyntaxFile]] = {}
_JAVA_SYNTAX_CACHE_STATS: dict[str, int] = {
    "java_files_requested": 0,
    "cache_hits": 0,
    "cache_misses": 0,
    "files_failed": 0,
}


def clear_java_syntax_cache(*, reset_stats: bool = True) -> None:
    """Release cached parsed Java files and source-byte buffers.

    Parsed files retain native Tree-sitter ``Tree`` objects, while ``_utf8_bytes``
    retains the corresponding source strings and byte buffers.  Both caches belong
    to one analysis-run lifecycle and must be released together; otherwise a large
    repository can finish writing artifacts but spend an unbounded amount of time
    cleaning native syntax state during interpreter shutdown.
    """
    _JAVA_FILE_PARSE_CACHE.clear()
    _utf8_bytes.cache_clear()
    if reset_stats:
        reset_java_syntax_cache_stats()


def reset_java_syntax_cache_stats() -> None:
    for key in list(_JAVA_SYNTAX_CACHE_STATS):
        _JAVA_SYNTAX_CACHE_STATS[key] = 0


def java_syntax_cache_stats() -> dict[str, Any]:
    utf8_info = _utf8_bytes.cache_info()
    return {
        **_JAVA_SYNTAX_CACHE_STATS,
        "cache_entries": len(_JAVA_FILE_PARSE_CACHE),
        "utf8_cache_entries": int(utf8_info.currsize),
        "utf8_cache_hits": int(utf8_info.hits),
        "utf8_cache_misses": int(utf8_info.misses),
        "syntax_provider": JAVA_SYNTAX_PROVIDER,
    }


def _file_cache_key(path: Path) -> tuple[int, int]:
    stat = path.stat()
    return int(stat.st_mtime_ns), int(stat.st_size)


def parse_java_file(path: str | Path) -> JavaSyntaxFile:
    p = Path(path)
    key = _file_cache_key(p)
    cache_key = str(p.resolve())
    _JAVA_SYNTAX_CACHE_STATS["java_files_requested"] += 1
    cached = _JAVA_FILE_PARSE_CACHE.get(cache_key)
    if cached and cached[0] == key:
        _JAVA_SYNTAX_CACHE_STATS["cache_hits"] += 1
        return cached[1]
    _JAVA_SYNTAX_CACHE_STATS["cache_misses"] += 1
    parsed = parse_java_text(read_text(p), p)
    _JAVA_FILE_PARSE_CACHE[cache_key] = (key, parsed)
    return parsed


def parse_java_workspace(files: list[Path]) -> JavaSyntaxWorkspace:
    parsed: list[JavaSyntaxFile] = []
    warnings: list[str] = []
    ok, detail = tree_sitter_available()
    if not ok:
        raise RuntimeError(f"Tree-sitter Java syntax provider is required but unavailable: {detail}")
    for p in [x for x in files if x.suffix.lower() == ".java"]:
        try:
            parsed.append(parse_java_file(p))
        except Exception as exc:
            _JAVA_SYNTAX_CACHE_STATS["files_failed"] += 1
            warnings.append(f"tree-sitter failed to parse {p}: {exc}")
    return JavaSyntaxWorkspace(parsed_files=tuple(parsed), warnings=tuple(warnings))


def parse_java_files(files: list[Path]) -> tuple[list[JavaSyntaxFile], list[str]]:
    workspace = parse_java_workspace(files)
    return list(workspace.parsed_files), list(workspace.warnings)


def method_params_as_dicts(method: JavaMethod) -> list[dict[str, Any]]:
    return [{"name": p.name, "type": p.type, "raw": p.raw, "annotations": [a.name for a in p.annotations]} for p in method.params]


def method_syntax_dict(method: JavaMethod) -> dict[str, Any]:
    return {
        "method_calls": [c.__dict__ for c in method.calls],
        "syntax_assignments": [a.__dict__ for a in method.assignments],
        "returns": [r.__dict__ for r in method.returns],
        "object_creations": [c.__dict__ for c in method.object_creations],
        "lambdas": [l.__dict__ for l in method.lambdas],
        "method_references": [r.__dict__ for r in method.method_references],
        "enhanced_for": [f.__dict__ for f in method.enhanced_for],
        "field_accesses": [f.__dict__ for f in method.field_accesses],
    }


def class_annotations_text(cls: JavaClass) -> str:
    return "\n".join(a.text for a in cls.annotations)


def method_visibility(method: JavaMethod) -> str:
    mods = method.modifiers or ""
    if "private" in mods:
        return "private"
    if "protected" in mods:
        return "protected"
    if "public" in mods:
        return "public"
    return "package"
