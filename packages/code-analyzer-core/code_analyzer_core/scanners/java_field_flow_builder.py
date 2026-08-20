from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
import hashlib
import os
import re
from pathlib import Path
from typing import Any, Iterable

from tree_sitter import Node

from code_analyzer_core.models import EvidenceRef, Fact, InterfaceInfo, SchemaInfo
from code_analyzer_core.scanners.java_syntax import JavaSyntaxFile, parse_java_workspace, java_syntax_cache_stats


@dataclass(slots=True)
class JavaFileContext:
    parsed: JavaSyntaxFile

    @property
    def path(self) -> Path:
        return self.parsed.file

    @property
    def root(self) -> Node:
        root = self.parsed.root_node
        if root is None:
            raise RuntimeError(f"Tree-sitter tree is unavailable for {self.parsed.file}")
        return root

    @property
    def parse_error(self) -> bool:
        return bool(self.parsed.parse_errors)

    def text(self, node: Node | None) -> str:
        return self.parsed.node_text(node)

    def location(self, node: Node) -> dict[str, object]:
        return self.parsed.node_location(node)


def iter_named(node: Node, *types: str) -> Iterable[Node]:
    wanted = set(types)
    stack = [node]
    while stack:
        current = stack.pop()
        if not wanted or current.type in wanted:
            yield current
        stack.extend(reversed(current.named_children))


def named_ancestors(node: Node) -> Iterable[Node]:
    cur = node.parent
    while cur is not None:
        if cur.is_named:
            yield cur
        cur = cur.parent


TYPE_DECLARATIONS = {"class_declaration", "interface_declaration", "record_declaration", "enum_declaration"}
METHOD_DECLARATIONS = {"method_declaration", "constructor_declaration"}
SCOPE_NODES = {"class_body", "method_declaration", "constructor_declaration", "block", "lambda_expression", "catch_clause", "for_statement", "enhanced_for_statement"}
WRAPPER_NODES = {"parenthesized_expression", "cast_expression"}
LITERAL_NODES = {"string_literal", "character_literal", "decimal_integer_literal", "decimal_floating_point_literal", "true", "false", "null_literal"}
COLLECTION_TYPES = {
    "Collection", "List", "Set", "Queue", "Deque",
    "ArrayList", "LinkedList", "HashSet", "LinkedHashSet", "TreeSet",
    "ArrayDeque", "PriorityQueue", "Iterable",
}
COLLECTION_LAMBDA_OPERATIONS = {"forEach", "map", "flatMap", "filter", "peek"}
COLLECTION_ELEMENT_MUTATIONS = {"add", "offer", "push"}


def _stable_id(prefix: str, *parts: object) -> str:
    payload = "\x1f".join(str(p or "") for p in parts)
    return f"{prefix}_{hashlib.sha1(payload.encode('utf-8')).hexdigest()[:20]}"


def _simple_type(value: str | None) -> str:
    if not value:
        return "unknown"
    text = re.sub(r"@[A-Za-z_$][\w$]*(?:\([^)]*\))?", "", value)
    text = re.sub(r"\b(final|volatile|transient)\b", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"<.*>", "", text).replace("[]", "").strip()
    return text.rsplit(".", 1)[-1] or "unknown"


def _first_generic_type_argument(ctx: JavaFileContext, type_node: Node | None) -> str:
    """Return the first declared generic argument using only Tree-sitter nodes."""
    if type_node is None:
        return "unknown"
    if type_node.type == "array_type":
        element = type_node.child_by_field_name("element")
        return _simple_type(ctx.text(element)) if element is not None else "unknown"
    if type_node.type != "generic_type":
        return "unknown"
    arguments = next(
        (child for child in type_node.named_children if child.type == "type_arguments"),
        None,
    )
    if arguments is None or not arguments.named_children:
        return "unknown"
    candidate = arguments.named_children[0]
    if candidate.type == "wildcard":
        candidate = next(
            (
                child
                for child in candidate.named_children
                if child.type in {
                    "type_identifier", "scoped_type_identifier", "generic_type", "array_type",
                }
            ),
            None,
        )
    if candidate is None:
        return "unknown"
    return _simple_type(ctx.text(candidate))


def _property_from_accessor(name: str) -> str | None:
    raw = name or ""
    for prefix in ("get", "set"):
        if raw.startswith(prefix) and len(raw) > len(prefix) and raw[len(prefix)].isupper():
            tail = raw[len(prefix):]
            return tail[0].lower() + tail[1:]
    if raw.startswith("is") and len(raw) > 2 and raw[2].isupper():
        tail = raw[2:]
        return tail[0].lower() + tail[1:]
    return None


def _node_field(node: Node, name: str) -> Node | None:
    return node.child_by_field_name(name)


def _enclosing(node: Node, types: set[str]) -> Node | None:
    cur: Node | None = node
    while cur is not None:
        if cur.type in types:
            return cur
        cur = cur.parent
    return None


def _type_name(ctx: JavaFileContext, node: Node | None) -> str:
    if node is None:
        return "unknown"
    return _simple_type(ctx.text(node))


def _declaration_name(ctx: JavaFileContext, node: Node) -> str:
    return ctx.text(_node_field(node, "name")) or "anonymous"


def _method_id(ctx: JavaFileContext, type_name: str, node: Node, file_key: str | None = None) -> str:
    name = _declaration_name(ctx, node)
    params = _node_field(node, "parameters")
    arity = sum(1 for n in (params.named_children if params else []) if n.type in {"formal_parameter", "spread_parameter", "receiver_parameter"})
    return _stable_id("jm", file_key or str(ctx.path), type_name, name, arity, node.start_byte)


@dataclass(slots=True)
class Symbol:
    symbol_id: str
    name: str
    declared_type: str
    kind: str
    node: Node
    scope: Node
    method_id: str
    occurrence_id: str


@dataclass(slots=True)
class MethodInfo:
    method_id: str
    type_name: str
    name: str
    return_type: str
    node: Node
    body: Node | None
    params: list[Symbol] = field(default_factory=list)
    symbols: list[Symbol] = field(default_factory=list)

    @property
    def arity(self) -> int:
        return len(self.params)


@dataclass(slots=True)
class FileIndex:
    ctx: JavaFileContext
    methods: list[MethodInfo]
    fields: dict[str, tuple[str, Node]]


@dataclass(slots=True)
class ObjectBinding:
    source_id: str
    target_id: str
    kind: str
    ctx: JavaFileContext
    method: MethodInfo
    basis: Node


@dataclass(slots=True)
class ContainerBinding:
    source_id: str
    target_id: str
    target_field_tail: str
    target_builder_key: str | None
    target_receiver_id: str | None
    ctx: JavaFileContext
    method: MethodInfo
    basis: Node


@dataclass(slots=True)
class BuilderFieldObservation:
    builder_key: str
    field_tail: str
    occurrence_id: str
    label: str
    ctx: JavaFileContext
    method: MethodInfo
    basis: Node


@dataclass(slots=True)
class BuilderBuildObservation:
    builder_key: str
    result_occurrence_id: str
    label: str
    built_type: str
    ctx: JavaFileContext
    method: MethodInfo
    basis: Node


class FieldFlowBuilder:
    def __init__(
        self,
        contexts: list[JavaFileContext],
        interfaces: Iterable[InterfaceInfo] = (),
        schemas: Iterable[SchemaInfo] = (),
        repository_id: str | None = None,
        repository_root: Path | None = None,
    ):
        self.contexts = contexts
        self.repository_id = repository_id or "repository"
        self.repository_root = Path(repository_root).resolve() if repository_root else self._infer_repository_root(contexts)
        self.interfaces = list(interfaces)
        self.schemas_by_name = {
            _simple_type(schema.name): schema
            for schema in schemas
            if _simple_type(schema.name) not in {"", "unknown"}
        }
        # Boundary-seeded projection can also use source-observed builder fields
        # when DTO classes come from external dependencies and no local schema is
        # available.  No interface means no demand and therefore no projection
        # bookkeeping on ordinary repository scans.
        self.projection_enabled = bool(self.interfaces)
        self.occurrences: dict[str, dict[str, Any]] = {}
        # Retain the exact Tree-sitter origin for bounded demand-driven edges
        # materialized after local extraction.  This is not a second parse and
        # keeps later parent-path projections tied to the observed getter node.
        self._occurrence_origins: dict[str, tuple[JavaFileContext, Node, MethodInfo | None]] = {}
        self.edges: dict[str, dict[str, Any]] = {}
        # Incremental indexes over Tree-sitter-derived flow edges.  Response
        # binding queries run after local extraction and must not rescan the
        # complete edge collection for every candidate field/object.
        self._incoming_edges_by_target: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._outgoing_occurrence_ids: dict[str, list[str]] = defaultdict(list)
        self._resolved_occurrence_type_cache: dict[tuple[str, int], str] = {}
        self._occurrence_path_cache: dict[tuple[str, str, int], bool] = {}
        self.file_indexes: list[FileIndex] = []
        self.methods_by_type_name_arity: dict[tuple[str, str, int], list[MethodInfo]] = defaultdict(list)
        self.methods_by_name_arity: dict[tuple[str, int], list[MethodInfo]] = defaultdict(list)
        self.known_type_names: set[str] = set()
        self.implementations_by_interface: dict[str, set[str]] = defaultdict(set)
        self.projection_method_ids: set[str] = set()
        self.method_to_file: dict[str, FileIndex] = {}
        self.diagnostics: list[dict[str, Any]] = []
        self._file_key_cache: dict[Path, str] = {}
        self._method_return_occurrence_cache: dict[str, str] = {}
        self._expression_occurrence_cache: dict[tuple[str, int, int, str], str] = {}
        self._expression_in_progress: set[tuple[str, int, int, str]] = set()
        self._expression_cache_hits = 0
        self._expression_cache_misses = 0
        self._expression_cycle_preventions = 0
        self._builder_parent: dict[str, str] = {}
        self._builder_key_by_object_occurrence: dict[str, str] = {}
        self._builder_fields: list[BuilderFieldObservation] = []
        self._builder_builds: list[BuilderBuildObservation] = []
        self._builder_field_keys: set[tuple[str, str, str]] = set()
        self._builder_build_keys: set[tuple[str, str]] = set()
        self._object_bindings: list[ObjectBinding] = []
        self._object_binding_keys: set[tuple[str, str, str, int]] = set()
        self._container_bindings: list[ContainerBinding] = []
        self._container_binding_keys: set[tuple[str, str, str, int]] = set()
        self._object_fields: dict[str, dict[str, str]] = defaultdict(dict)
        # Keep every concrete AST occurrence for repeated access to the same
        # object field. ``_object_fields`` remains the stable primary lookup,
        # while this multimap preserves chains such as
        # ``x.getName().getSurname()`` and ``x.getName().getName()`` appearing
        # in the same method.
        self._object_field_occurrences: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
        self._object_field_occurrence_ids: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
        self._object_field_duplicate_registrations_skipped = 0
        self._projection_seed_fields: set[tuple[str, str, str]] = set()
        self._projection_seed_candidates = 0
        self._projection_seed_skipped_without_source = 0
        self._projection_seed_skipped_without_sink = 0
        self._projection_forward_bindings: dict[str, list[ObjectBinding]] = defaultdict(list)
        self._projection_reverse_bindings: dict[str, list[ObjectBinding]] = defaultdict(list)
        self._projection_build_root_by_result: dict[str, str] = {}
        self._projection_builder_fields_by_root: dict[str, set[str]] = defaultdict(set)
        self._projection_containers_by_root: dict[str, list[ContainerBinding]] = defaultdict(list)
        self._projection_source_cache: dict[tuple[str, str], bool] = {}
        self._projection_sink_cache: dict[tuple[str, str], bool] = {}
        self._projected_field_cache: dict[tuple[str, str], str] = {}
        self._builder_projection_cache: dict[tuple[str, str, str], str] = {}
        self._observed_builder_boundary_field_count = 0
        self._interface_implementation_binding_count = 0
        self._external_response_property_observation_count = 0
        self._external_response_property_object_visit_count = 0
        self._external_response_property_cache_hits = 0
        self._external_response_property_cache: dict[
            str, tuple[tuple[str, str, dict[str, Any], tuple[str, ...], tuple[str, ...]], ...]
        ] = {}
        self._build_indexes()
        self.projection_enabled = self._has_projection_field_source()
        self.projection_method_ids = self._select_projection_methods()

    @staticmethod
    def _infer_repository_root(contexts: list[JavaFileContext]) -> Path | None:
        paths = [str(c.path.resolve().parent) for c in contexts]
        if not paths:
            return None
        try:
            return Path(os.path.commonpath(paths)).resolve()
        except ValueError:
            return None

    def _file_key(self, ctx: JavaFileContext) -> str:
        cached = self._file_key_cache.get(ctx.path)
        if cached is not None:
            return cached
        resolved = ctx.path.resolve()
        if self.repository_root is not None:
            try:
                value = str(resolved.relative_to(self.repository_root)).replace("\\", "/")
            except ValueError:
                value = ctx.path.name
        else:
            value = ctx.path.name
        self._file_key_cache[ctx.path] = value
        return value

    def _builder_find(self, key: str) -> str:
        parent = self._builder_parent.setdefault(key, key)
        if parent != key:
            self._builder_parent[key] = self._builder_find(parent)
        return self._builder_parent[key]

    def _builder_union(self, left: str, right: str) -> str:
        lroot = self._builder_find(left)
        rroot = self._builder_find(right)
        if lroot == rroot:
            return lroot
        # Stable representative keeps generated evidence IDs deterministic.
        root, child = sorted((lroot, rroot))
        self._builder_parent[child] = root
        return root

    @staticmethod
    def _built_type_from_builder_type(value: str | None) -> str:
        typ = _simple_type(value)
        for suffix in ("BuilderImpl", "Builder"):
            if typ.endswith(suffix) and len(typ) > len(suffix):
                return typ[:-len(suffix)]
        return "unknown"

    @staticmethod
    def _primitive_type(value: str | None) -> bool:
        return _simple_type(value) in {
            "void", "boolean", "byte", "short", "int", "long", "float", "double", "char",
            "Boolean", "Byte", "Short", "Integer", "Long", "Float", "Double", "Character",
            "String", "BigDecimal", "BigInteger", "UUID", "LocalDate", "LocalDateTime", "Instant",
        }

    def _object_label(self, occurrence_id: str) -> str:
        item = self.occurrences.get(occurrence_id, {})
        return str(item.get("field_path") or item.get("symbol") or item.get("expression_text") or occurrence_id)

    def _register_object_field(self, object_id: str | None, field_tail: str | None, occurrence_id: str | None) -> None:
        if not object_id or not field_tail or not occurrence_id:
            return
        tail = str(field_tail).strip(".")
        if not tail:
            return
        self._object_fields[object_id].setdefault(tail, occurrence_id)
        occurrence_ids = self._object_field_occurrence_ids[object_id][tail]
        if occurrence_id in occurrence_ids:
            self._object_field_duplicate_registrations_skipped += 1
            return
        occurrence_ids.add(occurrence_id)
        self._object_field_occurrences[object_id][tail].append(occurrence_id)

    def _record_object_binding(
        self,
        source_id: str,
        target_id: str,
        *,
        kind: str,
        ctx: JavaFileContext,
        method: MethodInfo,
        basis: Node,
    ) -> None:
        if not self._projection_active(method):
            return
        key = (source_id, target_id, kind, basis.start_byte)
        if key in self._object_binding_keys:
            return
        self._object_binding_keys.add(key)
        self._object_bindings.append(ObjectBinding(source_id, target_id, kind, ctx, method, basis))

    def _record_container_binding(
        self,
        source_id: str,
        target_id: str,
        *,
        target_field_tail: str,
        target_builder_key: str | None,
        target_receiver_id: str | None,
        ctx: JavaFileContext,
        method: MethodInfo,
        basis: Node,
    ) -> None:
        if not self._projection_active(method):
            return
        key = (source_id, target_id, target_field_tail, basis.start_byte)
        if key in self._container_binding_keys:
            return
        self._container_binding_keys.add(key)
        self._container_bindings.append(ContainerBinding(
            source_id=source_id,
            target_id=target_id,
            target_field_tail=target_field_tail,
            target_builder_key=target_builder_key,
            target_receiver_id=target_receiver_id,
            ctx=ctx,
            method=method,
            basis=basis,
        ))

    def _register_builder_field(
        self,
        *,
        builder_key: str,
        field_tail: str,
        occurrence_id: str,
        label: str,
        ctx: JavaFileContext,
        method: MethodInfo,
        basis: Node,
    ) -> None:
        if not self._projection_active(method):
            return
        key = (builder_key, field_tail, occurrence_id)
        if key in self._builder_field_keys:
            return
        self._builder_field_keys.add(key)
        self._builder_find(builder_key)
        self._builder_fields.append(BuilderFieldObservation(builder_key, field_tail, occurrence_id, label, ctx, method, basis))

    def _register_builder_build(
        self,
        *,
        builder_key: str,
        result_occurrence_id: str,
        label: str,
        built_type: str,
        ctx: JavaFileContext,
        method: MethodInfo,
        basis: Node,
    ) -> None:
        if not self._projection_active(method):
            return
        key = (builder_key, result_occurrence_id)
        if key in self._builder_build_keys:
            return
        self._builder_build_keys.add(key)
        self._builder_find(builder_key)
        self._builder_builds.append(BuilderBuildObservation(builder_key, result_occurrence_id, label, built_type, ctx, method, basis))

    def _occurrence(self, *, ctx: JavaFileContext, node: Node, method: MethodInfo | None, kind: str, symbol: str | None = None,
                    field_path: str | None = None, declared_type: str | None = None, expression_text: str | None = None,
                    resolution_status: str = "resolved", extra: dict[str, Any] | None = None) -> str:
        method_id = method.method_id if method else None
        relative_file = self._file_key(ctx)
        key = (self.repository_id, relative_file, method_id, node.start_byte, node.end_byte, kind, field_path or symbol or expression_text or "")
        oid = _stable_id("fo", *key)
        self._occurrence_origins.setdefault(oid, (ctx, node, method))
        if oid not in self.occurrences:
            item: dict[str, Any] = {
                "occurrence_id": oid,
                "repository_id": self.repository_id,
                "file": str(ctx.path),
                "relative_file": relative_file,
                "type_name": method.type_name if method else None,
                "method_id": method_id,
                "operation": f"{method.type_name}.{method.name}" if method else None,
                "occurrence_kind": kind,
                "symbol": symbol,
                "field_path": field_path,
                "declared_type": declared_type,
                "expression_text": (expression_text if expression_text is not None else ctx.text(node))[:1000],
                "resolution_status": resolution_status,
                "ast_node": ctx.location(node),
            }
            if extra:
                item.update(extra)
            self.occurrences[oid] = {k: v for k, v in item.items() if v is not None}
        return oid

    def _edge(self, source_id: str, target_id: str, *, ctx: JavaFileContext, basis: Node, kind: str,
              method: MethodInfo | None, resolution_status: str = "resolved", extra: dict[str, Any] | None = None) -> str:
        guards = self._guards(ctx, basis)
        relative_file = self._file_key(ctx)
        eid = _stable_id("fe", self.repository_id, source_id, target_id, kind, relative_file, basis.start_byte, basis.end_byte)
        if eid not in self.edges:
            item: dict[str, Any] = {
                "edge_id": eid,
                "repository_id": self.repository_id,
                "source_occurrence_id": source_id,
                "target_occurrence_id": target_id,
                "edge_kind": kind,
                "basis_node_type": basis.type,
                "file": str(ctx.path),
                "relative_file": relative_file,
                "method_id": method.method_id if method else None,
                "operation": f"{method.type_name}.{method.name}" if method else None,
                "resolution_status": resolution_status,
                "guards": guards,
                "ast_node": ctx.location(basis),
            }
            if extra:
                item.update(extra)
            stored = {k: v for k, v in item.items() if v is not None}
            self.edges[eid] = stored
            self._incoming_edges_by_target[target_id].append(stored)
            self._outgoing_occurrence_ids[source_id].append(target_id)
            # These caches are normally populated only after local extraction.
            # Clear them only when already in use so ordinary edge creation stays
            # O(1) and later boundary additions cannot leave stale answers.
            if self._resolved_occurrence_type_cache:
                self._resolved_occurrence_type_cache.clear()
            if self._occurrence_path_cache:
                self._occurrence_path_cache.clear()
        return eid

    def _guards(self, ctx: JavaFileContext, node: Node) -> list[dict[str, Any]]:
        guards: list[dict[str, Any]] = []
        child = node
        for parent in named_ancestors(node):
            if parent.type == "if_statement":
                cond = _node_field(parent, "condition")
                consequence = _node_field(parent, "consequence")
                alternative = _node_field(parent, "alternative")
                branch = "consequence"
                if alternative is not None and alternative.start_byte <= child.start_byte < alternative.end_byte:
                    branch = "alternative"
                elif consequence is not None and not (consequence.start_byte <= child.start_byte < consequence.end_byte):
                    child = parent
                    continue
                guards.append({
                    "node_type": cond.type if cond else "unknown",
                    "expression_text": ctx.text(cond)[:500] if cond else "",
                    "branch": branch,
                    "ast_node": ctx.location(cond) if cond else ctx.location(parent),
                })
            child = parent
            if parent.type in METHOD_DECLARATIONS:
                break
        return list(reversed(guards))

    def _build_indexes(self) -> None:
        for ctx in self.contexts:
            for parsed_class in ctx.parsed.classes:
                for interface_name in parsed_class.implements:
                    self.implementations_by_interface[_simple_type(interface_name)].add(_simple_type(parsed_class.name))
            methods: list[MethodInfo] = []
            fields: dict[str, tuple[str, Node]] = {}
            for type_node in iter_named(ctx.root, *TYPE_DECLARATIONS):
                type_name = _declaration_name(ctx, type_node)
                body = _node_field(type_node, "body")
                if body is None:
                    continue
                for member in body.named_children:
                    if member.type == "field_declaration":
                        declared_type = _type_name(ctx, _node_field(member, "type"))
                        for declarator in [n for n in member.named_children if n.type == "variable_declarator"]:
                            name = ctx.text(_node_field(declarator, "name"))
                            if name:
                                fields[name] = (declared_type, declarator)
                    elif member.type in METHOD_DECLARATIONS:
                        method = MethodInfo(
                            method_id=_method_id(ctx, type_name, member, self._file_key(ctx)),
                            type_name=type_name,
                            name=_declaration_name(ctx, member),
                            return_type=_type_name(ctx, _node_field(member, "type")) if member.type == "method_declaration" else type_name,
                            node=member,
                            body=_node_field(member, "body"),
                        )
                        params_node = _node_field(member, "parameters")
                        if params_node is not None:
                            for pos, p in enumerate(n for n in params_node.named_children if n.type in {"formal_parameter", "spread_parameter", "receiver_parameter"}):
                                name_node = _node_field(p, "name")
                                name = ctx.text(name_node)
                                if not name:
                                    continue
                                typ = _type_name(ctx, _node_field(p, "type"))
                                occ = self._occurrence(ctx=ctx, node=p, method=method, kind="method_parameter", symbol=name,
                                                       declared_type=typ, extra={"parameter_position": pos})
                                scope = method.body or member
                                sym = Symbol(_stable_id("js", method.method_id, name, p.start_byte), name, typ, "parameter", p, scope, method.method_id, occ)
                                method.params.append(sym)
                                method.symbols.append(sym)
                        if method.body is not None:
                            for local in iter_named(method.body, "local_variable_declaration"):
                                typ = _type_name(ctx, _node_field(local, "type"))
                                for declarator in [n for n in local.named_children if n.type == "variable_declarator"]:
                                    name_node = _node_field(declarator, "name")
                                    name = ctx.text(name_node)
                                    if not name:
                                        continue
                                    scope = next((a for a in named_ancestors(declarator) if a.type in SCOPE_NODES), method.body)
                                    occ = self._occurrence(ctx=ctx, node=declarator, method=method, kind="local_variable", symbol=name, declared_type=typ)
                                    method.symbols.append(Symbol(_stable_id("js", method.method_id, name, declarator.start_byte), name, typ, "local_variable", declarator, scope, method.method_id, occ))
                            # Lambda parameters are ordinary lexical symbols for
                            # every getter/builder observation inside the lambda.
                            # Tree-sitter already parsed both the invocation and
                            # the declared collection type, so no source-text or
                            # secondary parser fallback is needed.
                            for lambda_node in iter_named(method.body, "lambda_expression"):
                                invocation = next(
                                    (ancestor for ancestor in named_ancestors(lambda_node) if ancestor.type == "method_invocation"),
                                    None,
                                )
                                receiver: Node | None = None
                                operation = "lambda"
                                inferred_element_type = "unknown"
                                if invocation is not None:
                                    receiver, operation, _ = self._invocation_parts(ctx, invocation)
                                    if operation in COLLECTION_LAMBDA_OPERATIONS:
                                        inferred_element_type = self._collection_element_type_for_receiver(
                                            ctx, method, receiver
                                        )
                                for position, parameter in enumerate(self._lambda_parameter_nodes(lambda_node)):
                                    if parameter.type == "formal_parameter":
                                        name_node = _node_field(parameter, "name")
                                        declared_type = _type_name(ctx, _node_field(parameter, "type"))
                                        type_basis = "explicit_lambda_parameter_type"
                                    else:
                                        name_node = parameter
                                        declared_type = inferred_element_type if position == 0 else "unknown"
                                        type_basis = (
                                            "declared_collection_generic_argument"
                                            if declared_type != "unknown"
                                            else "unresolved_lambda_parameter_type"
                                        )
                                    name = ctx.text(name_node)
                                    if not name:
                                        continue
                                    occurrence = self._occurrence(
                                        ctx=ctx,
                                        node=parameter,
                                        method=method,
                                        kind="lambda_parameter",
                                        symbol=name,
                                        declared_type=declared_type,
                                        extra={
                                            "parameter_position": position,
                                            "lambda_operation": operation,
                                            "parameter_type_basis": type_basis,
                                        },
                                    )
                                    method.symbols.append(Symbol(
                                        _stable_id("js", method.method_id, "lambda", name, parameter.start_byte),
                                        name,
                                        declared_type,
                                        "lambda_parameter",
                                        parameter,
                                        lambda_node,
                                        method.method_id,
                                        occurrence,
                                    ))
                        methods.append(method)
            index = FileIndex(ctx=ctx, methods=methods, fields=fields)
            self.file_indexes.append(index)
            for method in methods:
                self.method_to_file[method.method_id] = index
                self.methods_by_type_name_arity[(method.type_name, method.name, method.arity)].append(method)
                self.methods_by_name_arity[(method.name, method.arity)].append(method)
                self.known_type_names.add(method.type_name)

    def _projection_active(self, method: MethodInfo) -> bool:
        return self.projection_enabled and method.method_id in self.projection_method_ids

    def _has_projection_field_source(self) -> bool:
        """Return whether a boundary can create field-level projection demand.

        Request and response contracts are considered independently.  This is a
        cheap pre-check over the cached Tree-sitter index; it does not parse Java
        again and avoids enabling projection for repositories with no usable
        boundary fields.
        """
        for interface in self.interfaces:
            if self._interface_direction(interface) != "outbound":
                continue
            operation = str(interface.operation or "")
            request_type = self._request_payload_type(interface)
            response_type = self._response_payload_type(interface)
            boundary_role = self._boundary_role(interface)
            request_schema = self.schemas_by_name.get(request_type)
            response_schema = self.schemas_by_name.get(response_type)
            for index in self.file_indexes:
                for method in index.methods:
                    if f"{method.type_name}.{method.name}" != operation:
                        continue
                    if request_type not in {"", "unknown", "Object"}:
                        if request_schema is None or request_schema.fields:
                            if self._payload_symbols(index, method, interface=interface, payload_type=request_type):
                                return True
                    if boundary_role not in {"http_outbound", "rest_response"}:
                        continue
                    if response_schema is not None and response_schema.fields:
                        return True
                    # An external HTTP response DTO may have no local schema,
                    # yet its concrete getter/field uses and object bindings are
                    # still valid Tree-sitter evidence. Enable the bounded
                    # boundary method slice so those relations are recorded.
                    if boundary_role == "http_outbound" and response_type not in {"", "unknown", "Object"}:
                        return True
                    body_text = index.ctx.text(method.body) if method.body is not None else ""
                    if re.search(r"\b(?:serialize|writeValueAsString|toJson)\s*\(", body_text):
                        return True
        return False

    def _call_graph_callee_from_syntax(self, index: FileIndex, method: MethodInfo, call: Any) -> MethodInfo | None:
        """Resolve a cached Tree-sitter ``JavaCall`` without walking the AST again."""
        receiver_text = str(call.receiver or "").strip()
        receiver_type: str | None
        if not receiver_text or receiver_text in {"this", "super"}:
            receiver_type = method.type_name
        elif receiver_text.isidentifier():
            candidates = [
                symbol
                for symbol in method.symbols
                if symbol.name == receiver_text
                and symbol.node.start_byte <= call.start_byte
                and symbol.scope.start_byte <= call.start_byte <= symbol.scope.end_byte
            ]
            if candidates:
                candidates.sort(key=lambda item: (item.scope.end_byte - item.scope.start_byte, -item.node.start_byte))
                receiver_type = candidates[0].declared_type
            elif receiver_text in index.fields:
                receiver_type = index.fields[receiver_text][0]
            elif receiver_text in self.known_type_names:
                receiver_type = receiver_text
            else:
                receiver_type = None
        else:
            receiver_type = None

        arity = len(call.args)
        simple_receiver_type = _simple_type(receiver_type)
        exact = self.methods_by_type_name_arity.get((simple_receiver_type, call.method, arity), []) if simple_receiver_type != "unknown" else []
        if len(exact) == 1:
            return exact[0]
        fallback = self.methods_by_name_arity.get((call.method, arity), [])
        return fallback[0] if len(fallback) == 1 else None

    def _select_projection_methods(
        self,
        *,
        max_forward_distance: int = 5,
        max_reverse_distance: int = 3,
        max_ingress_distance: int = 8,
    ) -> set[str]:
        """Select methods needed to connect observed boundaries through code.

        The primary slice remains outbound-demand-driven: walk backwards from
        concrete outbound operations to their small caller slice, then forwards
        into helpers.  A second bounded step adds only inbound boundary methods
        lying on a directed call path to that already selected slice.  This
        admits controller -> interface -> unique implementation bridges without
        turning the graph into an undirected repository-wide component.
        """
        if not self.projection_enabled:
            return set()

        boundary_operations: set[str] = set()
        explicit_operations: set[str] = set()
        inbound_operations: set[str] = set()
        for interface in self.interfaces:
            direction = self._interface_direction(interface)
            if direction == "inbound":
                request_type = self._request_payload_type(interface)
                if request_type not in {"", "unknown", "Object"} and interface.operation:
                    inbound_operations.add(str(interface.operation))
                continue
            if direction != "outbound":
                continue
            request_type = self._request_payload_type(interface)
            response_type = self._response_payload_type(interface)
            boundary_role = self._boundary_role(interface)
            has_request_demand = request_type not in {"", "unknown", "Object"}
            has_response_demand = (
                boundary_role in {"http_outbound", "rest_response"}
                and (
                    response_type not in {"", "unknown", "Object"}
                    or bool((interface.properties or {}).get("response_field_bindings"))
                )
            )
            if not has_request_demand and not has_response_demand:
                continue
            if interface.operation:
                operation = str(interface.operation)
                boundary_operations.add(operation)
                explicit_operations.add(operation)
            props = interface.properties or {}
            for operation in props.get("local_caller_operations") or []:
                explicit_operations.add(str(operation))
            for item in props.get("local_call_chain_candidates") or []:
                if isinstance(item, dict) and item.get("caller_operation"):
                    explicit_operations.add(str(item["caller_operation"]))
            if props.get("helper_operation"):
                explicit_operations.add(str(props["helper_operation"]))

        boundary_seeds: set[str] = set()
        explicit_seeds: set[str] = set()
        inbound_boundary_seeds: set[str] = set()
        for index in self.file_indexes:
            for method in index.methods:
                operation = f"{method.type_name}.{method.name}"
                if operation in boundary_operations:
                    boundary_seeds.add(method.method_id)
                if operation in explicit_operations:
                    explicit_seeds.add(method.method_id)
                if operation in inbound_operations:
                    inbound_boundary_seeds.add(method.method_id)
        if not explicit_seeds:
            return set()

        forward: dict[str, set[str]] = defaultdict(set)
        reverse: dict[str, set[str]] = defaultdict(set)

        def add_call(caller_id: str, callee_id: str) -> None:
            if caller_id == callee_id:
                return
            forward[caller_id].add(callee_id)
            reverse[callee_id].add(caller_id)

        # ``JavaSyntaxFile.methods[*].calls`` is already derived from the same
        # Tree-sitter parse and cached by the shared syntax provider. Reusing it
        # avoids a second full AST walk solely for projection scoping.
        for index in self.file_indexes:
            methods_by_source_key: dict[tuple[str, str, int, int], MethodInfo] = {
                (method.type_name, method.name, method.arity, int(method.node.start_point[0]) + 1): method
                for method in index.methods
            }
            for parsed_class in index.ctx.parsed.classes:
                for parsed_method in parsed_class.methods:
                    method = methods_by_source_key.get((
                        _simple_type(parsed_method.class_name),
                        parsed_method.name,
                        len(parsed_method.params),
                        parsed_method.line_start,
                    ))
                    if method is None:
                        candidates = self.methods_by_type_name_arity.get((
                            _simple_type(parsed_method.class_name), parsed_method.name, len(parsed_method.params)
                        ), [])
                        method = candidates[0] if len(candidates) == 1 else None
                    if method is None:
                        continue
                    for call in parsed_method.calls:
                        callee = self._call_graph_callee_from_syntax(index, method, call)
                        if callee is not None:
                            add_call(method.method_id, callee.method_id)

        # A call typed to an interface reaches its unique local implementation.
        # Keeping this edge directional lets reverse traversal discover the
        # service caller while avoiding a repository-wide connected component.
        for interface_name, implementation_names in self.implementations_by_interface.items():
            for (type_name, method_name, arity), interface_methods in self.methods_by_type_name_arity.items():
                if type_name != interface_name:
                    continue
                implementation_methods = [
                    method
                    for implementation_name in implementation_names
                    for method in self.methods_by_type_name_arity.get((implementation_name, method_name, arity), [])
                ]
                if len(interface_methods) == 1 and len(implementation_methods) == 1:
                    add_call(interface_methods[0].method_id, implementation_methods[0].method_id)

        # Structural-only/synthetic boundaries do not carry enrichment caller
        # hints.  A short reverse walk from the exact boundary operation finds
        # those callers, but does not reverse-expand from arbitrary helpers.
        caller_slice = set(boundary_seeds)
        queue: deque[tuple[str, int]] = deque((method_id, 0) for method_id in sorted(boundary_seeds))
        while queue:
            method_id, distance = queue.popleft()
            if distance >= max_reverse_distance:
                continue
            for caller_id in reverse.get(method_id, set()):
                if caller_id in caller_slice:
                    continue
                caller_slice.add(caller_id)
                queue.append((caller_id, distance + 1))

        selected = set(explicit_seeds) | caller_slice
        queue = deque((method_id, 0) for method_id in sorted(selected))
        while queue:
            method_id, distance = queue.popleft()
            if distance >= max_forward_distance:
                continue
            for callee_id in forward.get(method_id, set()):
                if callee_id in selected:
                    continue
                selected.add(callee_id)
                queue.append((callee_id, distance + 1))

        # Compute bounded distance *to* the selected outbound slice, then add
        # only directed ingress paths whose starting method is an actual inbound
        # boundary operation. Tests or unrelated callers may also reach the
        # slice, but they are not included unless they are themselves boundary
        # seeds, preventing reverse-call fan-out.
        distance_to_selected: dict[str, int] = {method_id: 0 for method_id in selected}
        queue = deque(sorted(selected))
        while queue:
            method_id = queue.popleft()
            distance = distance_to_selected[method_id]
            if distance >= max_ingress_distance:
                continue
            for caller_id in sorted(reverse.get(method_id, set())):
                candidate_distance = distance + 1
                previous = distance_to_selected.get(caller_id)
                if previous is not None and previous <= candidate_distance:
                    continue
                distance_to_selected[caller_id] = candidate_distance
                queue.append(caller_id)

        ingress_queue = deque(
            sorted(method_id for method_id in inbound_boundary_seeds if method_id in distance_to_selected)
        )
        ingress_seen: set[str] = set()
        while ingress_queue:
            method_id = ingress_queue.popleft()
            if method_id in ingress_seen:
                continue
            ingress_seen.add(method_id)
            selected.add(method_id)
            distance = distance_to_selected.get(method_id, 0)
            if distance <= 0:
                continue
            for callee_id in sorted(forward.get(method_id, set())):
                if distance_to_selected.get(callee_id) == distance - 1:
                    ingress_queue.append(callee_id)
        return selected

    def _process_interface_implementation_bindings(self) -> None:
        """Bind declaration parameters/returns to a unique local implementation.

        Calls through an interface are resolved to the declared method by the
        caller's receiver type.  When the repository contains exactly one
        matching implementation method, Tree-sitter declarations provide an
        explicit bridge to that implementation.  Multiple implementations are
        intentionally left unresolved.
        """
        for interface_name, implementation_names in sorted(self.implementations_by_interface.items()):
            interface_methods = [
                method
                for (type_name, _, _), methods in self.methods_by_type_name_arity.items()
                if type_name == interface_name
                for method in methods
            ]
            for interface_method in interface_methods:
                candidates = [
                    method
                    for implementation_name in sorted(implementation_names)
                    for method in self.methods_by_type_name_arity.get(
                        (implementation_name, interface_method.name, interface_method.arity), []
                    )
                ]
                if len(candidates) != 1:
                    if len(candidates) > 1:
                        self.diagnostics.append({
                            "kind": "ambiguous_interface_implementation",
                            "interface_method_id": interface_method.method_id,
                            "interface_operation": f"{interface_method.type_name}.{interface_method.name}",
                            "candidate_method_ids": [item.method_id for item in candidates],
                        })
                    continue
                implementation = candidates[0]
                if not (
                    interface_method.method_id in self.projection_method_ids
                    or implementation.method_id in self.projection_method_ids
                ):
                    continue
                implementation_index = self.method_to_file[implementation.method_id]
                for position, (source_param, target_param) in enumerate(zip(interface_method.params, implementation.params)):
                    self._edge(
                        source_param.occurrence_id,
                        target_param.occurrence_id,
                        ctx=implementation_index.ctx,
                        basis=implementation.node,
                        kind="interface_implementation_parameter_binding",
                        method=implementation,
                        extra={
                            "interface_method_id": interface_method.method_id,
                            "implementation_method_id": implementation.method_id,
                            "parameter_position": position,
                            "resolution_basis": "unique_local_implements_declaration_and_exact_method_name_arity",
                        },
                    )
                    self._record_object_binding(
                        source_param.occurrence_id,
                        target_param.occurrence_id,
                        kind="interface_implementation_parameter_binding",
                        ctx=implementation_index.ctx,
                        method=implementation,
                        basis=implementation.node,
                    )
                    self._interface_implementation_binding_count += 1
                if interface_method.return_type not in {"void", "unknown"} and implementation.return_type not in {"void", "unknown"}:
                    interface_index = self.method_to_file[interface_method.method_id]
                    implementation_return = self._method_return_occurrence(implementation_index, implementation)
                    interface_return = self._method_return_occurrence(interface_index, interface_method)
                    self._edge(
                        implementation_return,
                        interface_return,
                        ctx=implementation_index.ctx,
                        basis=implementation.node,
                        kind="implementation_return_to_interface",
                        method=implementation,
                        extra={
                            "interface_method_id": interface_method.method_id,
                            "implementation_method_id": implementation.method_id,
                            "resolution_basis": "unique_local_implements_declaration_and_exact_method_name_arity",
                        },
                    )
                    self._record_object_binding(
                        implementation_return,
                        interface_return,
                        kind="implementation_return_to_interface",
                        ctx=implementation_index.ctx,
                        method=implementation,
                        basis=implementation.node,
                    )
                    self._interface_implementation_binding_count += 1

    def _method_for_node(self, index: FileIndex, node: Node) -> MethodInfo | None:
        enclosing = _enclosing(node, METHOD_DECLARATIONS)
        if enclosing is None:
            return None
        return next((m for m in index.methods if m.node.start_byte == enclosing.start_byte and m.node.end_byte == enclosing.end_byte), None)

    @staticmethod
    def _is_scope_ancestor(scope: Node, node: Node) -> bool:
        return scope.start_byte <= node.start_byte and node.end_byte <= scope.end_byte

    def _resolve_method_symbol(self, method: MethodInfo, name: str, use_node: Node) -> Symbol | None:
        candidates = [
            symbol
            for symbol in method.symbols
            if symbol.name == name
            and symbol.node.start_byte <= use_node.start_byte
            and self._is_scope_ancestor(symbol.scope, use_node)
        ]
        if not candidates:
            return None
        candidates.sort(key=lambda symbol: (symbol.scope.end_byte - symbol.scope.start_byte, -symbol.node.start_byte))
        return candidates[0]

    def _resolve_symbol(self, index: FileIndex, method: MethodInfo, name: str, use_node: Node) -> Symbol | None:
        resolved = self._resolve_method_symbol(method, name, use_node)
        if resolved is not None:
            return resolved
        if name in index.fields:
            typ, decl = index.fields[name]
            oid = self._occurrence(ctx=index.ctx, node=decl, method=method, kind="object_field", symbol=name,
                                   field_path=f"this.{name}", declared_type=typ)
            return Symbol(_stable_id("jsf", method.type_name, name), name, typ, "field", decl, method.node, method.method_id, oid)
        return None

    @staticmethod
    def _declared_type_node(symbol: Symbol) -> Node | None:
        node = symbol.node
        if node.type in {"formal_parameter", "spread_parameter", "receiver_parameter"}:
            return _node_field(node, "type")
        if node.type == "variable_declarator" and node.parent is not None:
            return _node_field(node.parent, "type")
        return None

    def _collection_element_type_for_receiver(
        self,
        ctx: JavaFileContext,
        method: MethodInfo,
        receiver: Node | None,
    ) -> str:
        if receiver is None:
            return "unknown"
        while receiver.type in WRAPPER_NODES and receiver.named_child_count:
            receiver = receiver.named_children[-1]
        if receiver.type == "identifier":
            symbol = self._resolve_method_symbol(method, ctx.text(receiver), receiver)
            if symbol is None:
                return "unknown"
            type_node = self._declared_type_node(symbol)
            return _first_generic_type_argument(ctx, type_node)
        if receiver.type == "method_invocation":
            nested_receiver, name, args = self._invocation_parts(ctx, receiver)
            if name in {"stream", "parallelStream"} and not args:
                return self._collection_element_type_for_receiver(ctx, method, nested_receiver)
        return "unknown"

    @staticmethod
    def _lambda_parameter_nodes(lambda_node: Node) -> list[Node]:
        parameters = _node_field(lambda_node, "parameters")
        if parameters is None:
            candidates = [
                child
                for child in lambda_node.named_children
                if child.type in {"identifier", "formal_parameter", "inferred_parameters"}
            ]
            parameters = candidates[0] if candidates else None
        if parameters is None:
            return []
        if parameters.type in {"identifier", "formal_parameter"}:
            return [parameters]
        return [
            child
            for child in parameters.named_children
            if child.type in {"identifier", "formal_parameter"}
        ]

    def _lambda_symbols(self, method: MethodInfo, lambda_node: Node) -> list[Symbol]:
        symbols = [
            symbol
            for symbol in method.symbols
            if symbol.kind == "lambda_parameter"
            and symbol.scope.start_byte == lambda_node.start_byte
            and symbol.scope.end_byte == lambda_node.end_byte
        ]
        return sorted(symbols, key=lambda symbol: symbol.node.start_byte)

    def _receiver_type(self, index: FileIndex, method: MethodInfo, receiver: Node | None) -> str | None:
        if receiver is None:
            return method.type_name
        if receiver.type == "identifier":
            name = index.ctx.text(receiver)
            if name in {"this", "super"}:
                return method.type_name
            sym = self._resolve_symbol(index, method, name, receiver)
            return sym.declared_type if sym else None
        if receiver.type == "object_creation_expression":
            return _type_name(index.ctx, _node_field(receiver, "type"))
        return None

    def _is_collection_receiver(self, index: FileIndex, method: MethodInfo, receiver: Node | None) -> bool:
        if receiver is None:
            return False
        while receiver.type in WRAPPER_NODES and receiver.named_child_count:
            receiver = receiver.named_children[-1]
        receiver_type = _simple_type(self._receiver_type(index, method, receiver))
        if receiver_type in COLLECTION_TYPES:
            return True
        if receiver.type == "method_invocation":
            nested_receiver, name, args = self._invocation_parts(index.ctx, receiver)
            if name in {"stream", "parallelStream"} and not args:
                return self._is_collection_receiver(index, method, nested_receiver)
        return False

    def _invocation_parts(self, ctx: JavaFileContext, node: Node) -> tuple[Node | None, str, list[Node]]:
        receiver = _node_field(node, "object")
        name = ctx.text(_node_field(node, "name"))
        args_node = _node_field(node, "arguments")
        args = list(args_node.named_children) if args_node is not None else []
        return receiver, name, args

    def _argument_type(self, index: FileIndex, method: MethodInfo, node: Node) -> str | None:
        while node.type in WRAPPER_NODES and node.named_child_count:
            node = node.named_children[-1]
        if node.type == "identifier":
            sym = self._resolve_symbol(index, method, index.ctx.text(node), node)
            return sym.declared_type if sym else None
        if node.type == "object_creation_expression":
            return _type_name(index.ctx, _node_field(node, "type"))
        if node.type == "cast_expression":
            return _type_name(index.ctx, _node_field(node, "type"))
        if node.type == "string_literal":
            return "String"
        if node.type in {"decimal_integer_literal", "hex_integer_literal", "octal_integer_literal", "binary_integer_literal"}:
            return "int"
        if node.type in {"true", "false"}:
            return "boolean"
        return None

    def _receiver_label(self, ctx: JavaFileContext, node: Node | None) -> str:
        if node is None:
            return ""
        if node.type in {"identifier", "this", "super", "type_identifier"}:
            return ctx.text(node)
        if node.type == "object_creation_expression":
            return f"new {_type_name(ctx, _node_field(node, 'type'))}"
        if node.type == "method_invocation":
            obj, name, _ = self._invocation_parts(ctx, node)
            base = self._receiver_label(ctx, obj)
            if name == "builder":
                return f"{base}.builder" if base else "builder"
            return base or name
        if node.type == "field_access":
            return ctx.text(node)
        return ctx.text(node)[:160]

    def _builder_identity(
        self,
        index: FileIndex,
        method: MethodInfo,
        node: Node | None,
    ) -> tuple[str, str, str] | None:
        if node is None:
            return None
        while node.type in WRAPPER_NODES and node.named_child_count:
            node = node.named_children[-1]
        ctx = index.ctx
        if node.type == "identifier":
            sym = self._resolve_symbol(index, method, ctx.text(node), node)
            if sym is None:
                return None
            existing = self._builder_key_by_object_occurrence.get(sym.occurrence_id)
            built_type = self._built_type_from_builder_type(sym.declared_type)
            if existing or built_type != "unknown":
                key = existing or f"builder-object:{sym.occurrence_id}"
                self._builder_key_by_object_occurrence[sym.occurrence_id] = key
                self._builder_find(key)
                return key, sym.name, built_type
            return None
        if node.type == "field_access":
            text = ctx.text(node)
            if text.endswith("Builder"):
                key = _stable_id("jb", self.repository_id, self._file_key(ctx), method.method_id, node.start_byte, text)
                self._builder_find(key)
                return key, text, self._built_type_from_builder_type(text)
            return None
        if node.type != "method_invocation":
            return None
        receiver, name, args = self._invocation_parts(ctx, node)
        if name in {"builder", "toBuilder"} and not args:
            label_base = self._receiver_label(ctx, receiver)
            label = f"{label_base}.{name}" if label_base else name
            built_type = _simple_type(label_base) if name == "builder" else (_simple_type(self._receiver_type(index, method, receiver)) if receiver is not None else "unknown")
            key = _stable_id("jb", self.repository_id, self._file_key(ctx), method.method_id, node.start_byte, name, label_base)
            self._builder_find(key)
            return key, label, built_type
        parent = self._builder_identity(index, method, receiver)
        if parent is not None and name != "build":
            return parent
        return None

    def _bind_builder_objects(self, source_id: str, target_id: str) -> None:
        source_key = self._builder_key_by_object_occurrence.get(source_id)
        target_key = self._builder_key_by_object_occurrence.get(target_id)
        if source_key and target_key:
            self._builder_union(source_key, target_key)

    def _resolve_call(self, index: FileIndex, method: MethodInfo, node: Node) -> tuple[MethodInfo | None, list[MethodInfo], str]:
        receiver, name, args = self._invocation_parts(index.ctx, node)
        receiver_type = self._receiver_type(index, method, receiver)
        candidates: list[MethodInfo] = []
        if receiver_type:
            candidates = list(self.methods_by_type_name_arity.get((receiver_type, name, len(args)), []))
        if not candidates and receiver is None:
            candidates = list(self.methods_by_type_name_arity.get((method.type_name, name, len(args)), []))
        # Do not guess across unrelated types. A name/arity-only match is safe only
        # for an unqualified call in the current declaring type.
        if not candidates and receiver is None:
            candidates = list(self.methods_by_type_name_arity.get((method.type_name, name, len(args)), []))
        if len(candidates) > 1:
            argument_types = [self._argument_type(index, method, arg) for arg in args]
            filtered: list[MethodInfo] = []
            for candidate in candidates:
                compatible = True
                for arg_type, param in zip(argument_types, candidate.params):
                    if not arg_type or arg_type == "unknown" or param.declared_type in {"unknown", "Object"}:
                        continue
                    if _simple_type(arg_type) != _simple_type(param.declared_type):
                        compatible = False
                        break
                if compatible:
                    filtered.append(candidate)
            if filtered:
                candidates = filtered
        if len(candidates) == 1:
            return candidates[0], candidates, "resolved"
        return None, candidates, "ambiguous" if candidates else "external_or_unresolved"

    def _expression(self, index: FileIndex, method: MethodInfo, node: Node, *, role: str = "expression") -> str:
        while node.type in WRAPPER_NODES and node.named_child_count:
            node = node.named_children[-1]
        cache_key = (method.method_id, node.start_byte, node.end_byte, role)
        cached = self._expression_occurrence_cache.get(cache_key)
        if cached is not None:
            self._expression_cache_hits += 1
            return cached
        self._expression_cache_misses += 1
        if cache_key in self._expression_in_progress:
            # Tree-sitter expressions should recurse only into strict subtrees.
            # Keep malformed/recovered ASTs bounded instead of re-entering the
            # same node indefinitely.
            self._expression_cycle_preventions += 1
            return self._occurrence(
                ctx=index.ctx,
                node=node,
                method=method,
                kind=role,
                resolution_status="partially_resolved",
                extra={"diagnostic": "expression_cycle_prevented"},
            )
        self._expression_in_progress.add(cache_key)
        try:
            result = self._expression_uncached(index, method, node, role=role)
            self._expression_occurrence_cache[cache_key] = result
            return result
        finally:
            self._expression_in_progress.discard(cache_key)

    def _expression_uncached(self, index: FileIndex, method: MethodInfo, node: Node, *, role: str = "expression") -> str:
        ctx = index.ctx
        if node.type == "identifier":
            name = ctx.text(node)
            sym = self._resolve_symbol(index, method, name, node)
            if sym:
                return sym.occurrence_id
            return self._occurrence(ctx=ctx, node=node, method=method, kind="unresolved_identifier", symbol=name,
                                    resolution_status="unresolved")
        if node.type == "field_access":
            obj = _node_field(node, "object")
            field_node = _node_field(node, "field")
            base_id = self._expression(index, method, obj, role="field_receiver") if obj is not None else None
            base_path = self.occurrences.get(base_id or "", {}).get("field_path") or self.occurrences.get(base_id or "", {}).get("symbol") or ctx.text(obj)
            field_name = ctx.text(field_node)
            path = f"{base_path}.{field_name}" if base_path else field_name
            occurrence_id = self._occurrence(
                ctx=ctx,
                node=node,
                method=method,
                kind="local_field",
                field_path=path,
                extra={
                    "property_name": field_name,
                    "property_name_basis": "direct_field_access",
                    "accessor_kind": "field_access",
                },
            )
            self._register_object_field(base_id, field_name, occurrence_id)
            return occurrence_id
        if node.type == "method_invocation":
            receiver, name, args = self._invocation_parts(ctx, node)
            prop = _property_from_accessor(name)
            if prop and (name.startswith("get") or name.startswith("is")) and not args:
                base_id = self._expression(index, method, receiver, role="getter_receiver") if receiver is not None else None
                base_path = self.occurrences.get(base_id or "", {}).get("field_path") or self.occurrences.get(base_id or "", {}).get("symbol") or ctx.text(receiver)
                path = f"{base_path}.{prop}" if base_path else prop
                occurrence_id = self._occurrence(
                    ctx=ctx,
                    node=node,
                    method=method,
                    kind="local_field",
                    field_path=path,
                    extra={
                        "property_name": prop,
                        "property_name_basis": "java_beans_getter",
                        "accessor_method_name": name,
                        "accessor_kind": "getter",
                    },
                )
                self._register_object_field(base_id, prop, occurrence_id)
                return occurrence_id

            projection_active = self._projection_active(method)
            builder = self._builder_identity(index, method, node) if projection_active else None
            receiver_builder = self._builder_identity(index, method, receiver) if projection_active else None
            if name in {"builder", "toBuilder"} and not args and builder is not None:
                builder_key, label, built_type = builder
                invocation_id = self._occurrence(
                    ctx=ctx,
                    node=node,
                    method=method,
                    kind="builder_factory",
                    field_path=label,
                    declared_type=f"{built_type}Builder" if built_type != "unknown" else None,
                    extra={"builder_identity": builder_key, "built_type": built_type},
                )
                self._builder_key_by_object_occurrence[invocation_id] = builder_key
                return invocation_id
            if name == "build" and not args and receiver_builder is not None:
                builder_key, label, built_type = receiver_builder
                invocation_id = self._occurrence(
                    ctx=ctx,
                    node=node,
                    method=method,
                    kind="built_object",
                    field_path=f"{label}.build()",
                    declared_type=built_type if built_type != "unknown" else None,
                    extra={"builder_identity": builder_key, "built_type": built_type},
                )
                self._register_builder_build(
                    builder_key=builder_key,
                    result_occurrence_id=invocation_id,
                    label=label,
                    built_type=built_type,
                    ctx=ctx,
                    method=method,
                    basis=node,
                )
                return invocation_id
            if receiver_builder is not None and len(args) == 1:
                builder_key, label, built_type = receiver_builder
                source = self._expression(index, method, args[0], role="method_argument")
                invocation_id = self._occurrence(
                    ctx=ctx,
                    node=node,
                    method=method,
                    kind="builder_invocation",
                    field_path=label,
                    declared_type=f"{built_type}Builder" if built_type != "unknown" else None,
                    extra={"builder_identity": builder_key, "built_type": built_type},
                )
                self._builder_key_by_object_occurrence[invocation_id] = builder_key
                target = self._occurrence(
                    ctx=ctx,
                    node=node,
                    method=method,
                    kind="builder_target",
                    field_path=f"{label}.{name}",
                    extra={
                        "builder_identity": builder_key,
                        "builder_field_tail": name,
                        "builder_label": label,
                    },
                )
                self._edge(source, target, ctx=ctx, basis=node, kind="builder_argument", method=method)
                self._register_builder_field(
                    builder_key=builder_key,
                    field_tail=name,
                    occurrence_id=target,
                    label=label,
                    ctx=ctx,
                    method=method,
                    basis=node,
                )
                self._record_container_binding(
                    source,
                    target,
                    target_field_tail=name,
                    target_builder_key=builder_key,
                    target_receiver_id=None,
                    ctx=ctx,
                    method=method,
                    basis=node,
                )
                return invocation_id

            if prop and name.startswith("set") and len(args) == 1:
                source = self._expression(index, method, args[0], role="method_argument")
                receiver_id = self._expression(index, method, receiver, role="target_receiver") if receiver is not None else None
                receiver_path = self._object_label(receiver_id) if receiver_id else self._receiver_label(ctx, receiver)
                target = self._occurrence(
                    ctx=ctx,
                    node=node,
                    method=method,
                    kind="setter_target",
                    field_path=f"{receiver_path}.{prop}" if receiver_path else prop,
                    extra={"receiver_occurrence_id": receiver_id, "setter_field_tail": prop},
                )
                self._edge(source, target, ctx=ctx, basis=node, kind="setter_argument", method=method)
                self._register_object_field(receiver_id, prop, target)
                self._record_container_binding(
                    source,
                    target,
                    target_field_tail=prop,
                    target_builder_key=None,
                    target_receiver_id=receiver_id,
                    ctx=ctx,
                    method=method,
                    basis=node,
                )
            # Preserve the exact result used as a receiver by a chained invocation.
            # This is needed not only for a direct getter such as
            # ``user.getBirthdate().format(...)`` but also for longer mechanical
            # chains such as ``request.getScopes().stream().map(...).collect(...)``.
            # Recursing through the Tree-sitter receiver node emits only observed
            # value transfer (getter -> stream -> map -> collect); it does not infer
            # collection semantics, match fields by name/type, or guess helper
            # returns.  Every recursive step is a strict subtree of ``node``.
            receiver_value_id = None
            if receiver is not None and receiver.type == "method_invocation":
                receiver_value_id = self._expression(
                    index, method, receiver, role="chained_invocation_receiver"
                )

            callee, candidates, status = self._resolve_call(index, method, node)
            receiver_text = ctx.text(receiver) if receiver is not None else method.type_name
            invocation_id = self._occurrence(ctx=ctx, node=node, method=method, kind="method_invocation",
                                             field_path=f"{receiver_text}.{name}()", declared_type=callee.return_type if callee else None,
                                             resolution_status=status,
                                             extra={"callee_method_id": callee.method_id if callee else None,
                                                    "candidate_method_ids": [c.method_id for c in candidates] or None})
            if receiver_value_id is not None:
                self._edge(
                    receiver_value_id,
                    invocation_id,
                    ctx=ctx,
                    basis=node,
                    kind="invocation_receiver",
                    method=method,
                    resolution_status=status,
                )
            for pos, arg in enumerate(args):
                source = self._expression(index, method, arg, role="method_argument")
                self._edge(source, invocation_id, ctx=ctx, basis=node, kind="invocation_argument", method=method,
                           resolution_status=status, extra={"argument_position": pos, "callee_method_id": callee.method_id if callee else None})
            if callee is not None:
                callee_index = self.method_to_file.get(callee.method_id)
                if callee_index is not None:
                    return_occ = self._method_return_occurrence(callee_index, callee)
                    self._edge(return_occ, invocation_id, ctx=ctx, basis=node, kind="return_to_caller", method=method,
                               extra={"callee_method_id": callee.method_id})
                    self._record_object_binding(return_occ, invocation_id, kind="return_to_caller", ctx=ctx, method=method, basis=node)
            return invocation_id
        if node.type == "object_creation_expression":
            typ = _type_name(ctx, _node_field(node, "type"))
            oid = self._occurrence(ctx=ctx, node=node, method=method, kind="object_creation", field_path=f"new {typ}", declared_type=typ)
            args_node = _node_field(node, "arguments")
            args = list(args_node.named_children) if args_node is not None else []
            candidates = self.methods_by_type_name_arity.get((typ, typ, len(args)), [])
            callee = candidates[0] if len(candidates) == 1 else None
            status = "resolved" if callee else ("ambiguous" if candidates else "external_or_unresolved")
            for pos, arg in enumerate(args):
                source = self._expression(index, method, arg, role="constructor_argument")
                arg_occ = self._occurrence(ctx=ctx, node=arg, method=method, kind="constructor_argument", field_path=f"{typ}.<init>.argument[{pos}]",
                                           resolution_status=status, extra={"constructor_method_id": callee.method_id if callee else None, "argument_position": pos})
                self._edge(source, arg_occ, ctx=ctx, basis=node, kind="constructor_argument", method=method, resolution_status=status)
                if callee and pos < len(callee.params):
                    self._edge(arg_occ, callee.params[pos].occurrence_id, ctx=ctx, basis=node, kind="method_argument_binding", method=method,
                               extra={"callee_method_id": callee.method_id, "parameter_position": pos})
            return oid
        if node.type in LITERAL_NODES:
            return self._occurrence(ctx=ctx, node=node, method=method, kind="literal", expression_text=ctx.text(node))
        if node.type == "ternary_expression":
            conditional_id = self._occurrence(ctx=ctx, node=node, method=method, kind="conditional_expression")
            condition = _node_field(node, "condition")
            consequence = _node_field(node, "consequence")
            alternative = _node_field(node, "alternative")
            for branch_name, branch_node in (("consequence", consequence), ("alternative", alternative)):
                if branch_node is None:
                    continue
                source = self._expression(index, method, branch_node, role="conditional_branch")
                self._edge(
                    source, conditional_id, ctx=ctx, basis=node, kind="conditional_branch", method=method,
                    extra={
                        "conditional_branch": branch_name,
                        "conditional_expression": ctx.text(condition)[:500] if condition is not None else None,
                    },
                )
            return conditional_id
        oid = self._occurrence(ctx=ctx, node=node, method=method, kind=role, resolution_status="partially_resolved")
        for child in node.named_children:
            if child.type in {"identifier", "field_access", "method_invocation"}:
                source = self._expression(index, method, child, role="expression_component")
                self._edge(source, oid, ctx=ctx, basis=node, kind="expression_component", method=method, resolution_status="partially_resolved")
        return oid

    def _target(self, index: FileIndex, method: MethodInfo, node: Node, *, kind: str = "assignment_target") -> str:
        if node.type == "identifier":
            sym = self._resolve_symbol(index, method, index.ctx.text(node), node)
            if sym:
                return sym.occurrence_id
        if node.type == "field_access":
            return self._expression(index, method, node, role=kind)
        return self._occurrence(ctx=index.ctx, node=node, method=method, kind=kind, resolution_status="partially_resolved")

    def _process_local_flows(self, index: FileIndex, method: MethodInfo) -> None:
        if method.body is None:
            return
        ctx = index.ctx
        for declarator in iter_named(method.body, "variable_declarator"):
            value = _node_field(declarator, "value")
            name_node = _node_field(declarator, "name")
            if value is None or name_node is None:
                continue
            source = self._expression(index, method, value)
            target = self._target(index, method, name_node)
            self._edge(source, target, ctx=ctx, basis=declarator, kind="variable_initializer", method=method)
            self._record_object_binding(source, target, kind="variable_initializer", ctx=ctx, method=method, basis=declarator)
            source_builder = self._builder_key_by_object_occurrence.get(source)
            target_symbol = next((s for s in method.symbols if s.occurrence_id == target), None)
            if self._projection_active(method) and target_symbol is not None and self._built_type_from_builder_type(target_symbol.declared_type) != "unknown":
                target_builder = self._builder_key_by_object_occurrence.setdefault(target, f"builder-object:{target}")
                self._builder_find(target_builder)
                if source_builder:
                    self._builder_union(source_builder, target_builder)
            if value.type == "method_invocation":
                callee, _, status = self._resolve_call(index, method, value)
                if callee:
                    return_occ = self._method_return_occurrence(self.method_to_file[callee.method_id], callee)
                    self._edge(return_occ, target, ctx=ctx, basis=declarator, kind="return_to_caller", method=method,
                               resolution_status=status, extra={"callee_method_id": callee.method_id})
                    self._record_object_binding(return_occ, target, kind="return_to_caller", ctx=ctx, method=method, basis=declarator)
        for assignment in iter_named(method.body, "assignment_expression"):
            left = _node_field(assignment, "left")
            right = _node_field(assignment, "right")
            if left is None or right is None:
                continue
            source = self._expression(index, method, right)
            target = self._target(index, method, left)
            self._edge(source, target, ctx=ctx, basis=assignment, kind="assignment_expression", method=method)
            self._record_object_binding(source, target, kind="assignment_expression", ctx=ctx, method=method, basis=assignment)
        for invocation in iter_named(method.body, "method_invocation"):
            receiver, name, args = self._invocation_parts(ctx, invocation)
            lambda_args = [arg for arg in args if arg.type == "lambda_expression"]
            if (
                name in COLLECTION_LAMBDA_OPERATIONS
                and receiver is not None
                and len(lambda_args) == 1
                and self._is_collection_receiver(index, method, receiver)
            ):
                lambda_symbols = self._lambda_symbols(method, lambda_args[0])
                if len(lambda_symbols) == 1:
                    source = self._expression(index, method, receiver, role="collection_receiver")
                    target = lambda_symbols[0].occurrence_id
                    self._edge(
                        source,
                        target,
                        ctx=ctx,
                        basis=invocation,
                        kind="collection_element_to_lambda_parameter",
                        method=method,
                        extra={
                            "collection_operation": name,
                            "lambda_parameter_position": 0,
                            "collection_element_type": lambda_symbols[0].declared_type,
                            "binding_basis": "tree_sitter_collection_invocation_and_lambda_parameter",
                        },
                    )
                    self._record_object_binding(
                        source,
                        target,
                        kind="collection_element_to_lambda_parameter",
                        ctx=ctx,
                        method=method,
                        basis=invocation,
                    )
                elif lambda_symbols:
                    self.diagnostics.append({
                        "kind": "unsupported_collection_lambda_arity",
                        "file": str(ctx.path),
                        "operation": f"{method.type_name}.{method.name}",
                        "expression": ctx.text(invocation)[:500],
                        "lambda_parameter_count": len(lambda_symbols),
                        "ast_node": ctx.location(invocation),
                    })

            if (
                name in COLLECTION_ELEMENT_MUTATIONS
                and receiver is not None
                and len(args) == 1
                and self._is_collection_receiver(index, method, receiver)
            ):
                source = self._expression(index, method, args[0], role="collection_element")
                target = self._expression(index, method, receiver, role="collection_receiver")
                self._edge(
                    source,
                    target,
                    ctx=ctx,
                    basis=invocation,
                    kind="collection_element_addition",
                    method=method,
                    extra={
                        "collection_operation": name,
                        "binding_basis": "tree_sitter_collection_mutation_invocation",
                    },
                )
                self._record_object_binding(
                    source,
                    target,
                    kind="collection_element_addition",
                    ctx=ctx,
                    method=method,
                    basis=invocation,
                )

            prop = _property_from_accessor(name)
            is_setter_call = bool(prop and name.startswith("set") and len(args) == 1)
            receiver_text = ctx.text(receiver) if receiver is not None else ""
            receiver_type = self._receiver_type(index, method, receiver) if receiver is not None else None
            is_simple_builder_call = bool(
                not is_setter_call
                and len(args) == 1
                and receiver is not None
                and ("builder" in receiver_text.lower() or str(receiver_type or "").lower().endswith("builder"))
            )
            if self._projection_active(method):
                # Force observation of standalone setters/builders/build() calls.
                # Calls already seen through an initializer/return reuse stable IDs.
                receiver_builder = self._builder_identity(index, method, receiver)
                is_builder_call = (
                    (name in {"builder", "toBuilder"} and not args)
                    or (name == "build" and receiver_builder is not None)
                    or (receiver_builder is not None and len(args) == 1)
                )
                if is_builder_call or is_setter_call:
                    self._expression(index, method, invocation, role="method_invocation")
            elif is_setter_call or is_simple_builder_call:
                source = self._expression(index, method, args[0], role="method_argument")
                receiver_id = self._expression(index, method, receiver, role="target_receiver") if receiver is not None else None
                receiver_path = (
                    self.occurrences.get(receiver_id or "", {}).get("field_path")
                    or self.occurrences.get(receiver_id or "", {}).get("symbol")
                    or self._receiver_label(ctx, receiver)
                )
                if is_simple_builder_call:
                    receiver_path = self._receiver_label(ctx, receiver) or receiver_path
                target_field = prop if is_setter_call else name
                target = self._occurrence(
                    ctx=ctx,
                    node=invocation,
                    method=method,
                    kind="setter_target" if is_setter_call else "builder_target",
                    field_path=f"{receiver_path}.{target_field}" if receiver_path else target_field,
                )
                self._edge(
                    source,
                    target,
                    ctx=ctx,
                    basis=invocation,
                    kind="setter_argument" if is_setter_call else "builder_argument",
                    method=method,
                )
            if not args:
                continue
            callee, candidates, status = self._resolve_call(index, method, invocation)
            if callee:
                for pos, arg in enumerate(args):
                    if pos >= len(callee.params):
                        break
                    source = self._expression(index, method, arg, role="method_argument")
                    self._edge(source, callee.params[pos].occurrence_id, ctx=ctx, basis=invocation, kind="method_argument_binding", method=method,
                               resolution_status=status, extra={"callee_method_id": callee.method_id, "parameter_position": pos})
                    self._record_object_binding(source, callee.params[pos].occurrence_id, kind="method_argument_binding", ctx=ctx, method=method, basis=invocation)
                    source_builder = self._builder_key_by_object_occurrence.get(source)
                    param = callee.params[pos]
                    if self._projection_active(method) and self._built_type_from_builder_type(param.declared_type) != "unknown":
                        param_builder = self._builder_key_by_object_occurrence.setdefault(param.occurrence_id, f"builder-object:{param.occurrence_id}")
                        self._builder_find(param_builder)
                        if source_builder:
                            self._builder_union(source_builder, param_builder)
            elif candidates:
                self.diagnostics.append({
                    "kind": "ambiguous_method_call",
                    "file": str(ctx.path),
                    "operation": f"{method.type_name}.{method.name}",
                    "expression": ctx.text(invocation)[:500],
                    "candidate_method_ids": [c.method_id for c in candidates],
                    "ast_node": ctx.location(invocation),
                })
        for ret in iter_named(method.body, "return_statement"):
            expr = ret.named_children[0] if ret.named_children else None
            if expr is None:
                continue
            source = self._expression(index, method, expr, role="return_expression")
            target = self._method_return_occurrence(index, method)
            self._edge(source, target, ctx=ctx, basis=ret, kind="method_return", method=method)
            self._record_object_binding(source, target, kind="method_return", ctx=ctx, method=method, basis=ret)

    def _builder_key_for_occurrence(self, occurrence_id: str) -> str | None:
        existing = self._builder_key_by_object_occurrence.get(occurrence_id)
        if existing:
            return existing
        item = self.occurrences.get(occurrence_id, {})
        if self._built_type_from_builder_type(item.get("declared_type")) == "unknown":
            return None
        key = f"builder-object:{occurrence_id}"
        self._builder_key_by_object_occurrence[occurrence_id] = key
        self._builder_find(key)
        return key

    def _ensure_object_field(
        self,
        object_id: str,
        field_tail: str,
        *,
        ctx: JavaFileContext,
        method: MethodInfo,
        basis: Node,
        projection_basis: str,
        anchor_on_object: bool = False,
    ) -> tuple[str, bool]:
        tail = field_tail.strip(".")
        existing = self._object_fields.get(object_id, {}).get(tail)
        if existing:
            return existing, False
        # Ordinary projection may reuse a concrete nested getter occurrence.
        # Parent-path lifting instead needs a distinct field anchor owned by the
        # parent DTO so the full dotted path can cross method/object bindings.
        if not anchor_on_object:
            observed = self._observed_object_field(object_id, tail)
            if observed:
                return observed, False
        cache_key = (object_id, tail)
        cached = self._projected_field_cache.get(cache_key)
        if cached:
            self._register_object_field(object_id, tail, cached)
            return cached, False
        base = self._object_label(object_id)
        object_item = self.occurrences.get(object_id, {})
        occurrence_id = self._occurrence(
            ctx=ctx,
            node=basis,
            method=method,
            kind="projected_object_field",
            field_path=f"{base}.{tail}" if base else tail,
            extra={
                "object_occurrence_id": object_id,
                "projected_field_tail": tail,
                "projection_basis": projection_basis,
                "object_declared_type": object_item.get("declared_type"),
            },
        )
        self._projected_field_cache[cache_key] = occurrence_id
        self._register_object_field(object_id, tail, occurrence_id)
        return occurrence_id, True

    def _ensure_builder_field(
        self,
        *,
        builder_key: str,
        field_tail: str,
        label: str,
        ctx: JavaFileContext,
        method: MethodInfo,
        basis: Node,
        projection_basis: str,
    ) -> tuple[BuilderFieldObservation, bool]:
        root = self._builder_find(builder_key)
        cache_key = (root, field_tail, projection_basis)
        cached = self._builder_projection_cache.get(cache_key)
        if cached:
            obs = next(
                (item for item in self._builder_fields if item.occurrence_id == cached),
                BuilderFieldObservation(root, field_tail, cached, label, ctx, method, basis),
            )
            return obs, False
        occurrence_id = self._occurrence(
            ctx=ctx,
            node=basis,
            method=method,
            kind="builder_nested_field",
            field_path=f"{label}.{field_tail}" if label else field_tail,
            extra={
                "builder_identity": root,
                "builder_field_tail": field_tail,
                "builder_label": label,
                "projection_basis": projection_basis,
            },
        )
        self._builder_projection_cache[cache_key] = occurrence_id
        obs = BuilderFieldObservation(root, field_tail, occurrence_id, label, ctx, method, basis)
        self._builder_fields.append(obs)
        return obs, True

    def _finalize_object_field_bindings(self) -> dict[str, int]:
        # Builder aliases are based only on explicit assignment/argument/return
        # bindings. Matching by field name or type alone is deliberately absent.
        self._finalize_builder_aliases()

        builder_fields_by_root: dict[str, dict[str, list[BuilderFieldObservation]]] = defaultdict(lambda: defaultdict(list))
        builds_by_result: dict[str, tuple[str, BuilderBuildObservation]] = {}
        for item in self._builder_fields:
            builder_fields_by_root[self._builder_find(item.builder_key)][item.field_tail].append(item)
        for item in self._builder_builds:
            root = self._builder_find(item.builder_key)
            builds_by_result[item.result_occurrence_id] = (root, item)

        forward_bindings: dict[str, list[ObjectBinding]] = defaultdict(list)
        reverse_bindings: dict[str, list[ObjectBinding]] = defaultdict(list)
        for binding in self._object_bindings:
            source_item = self.occurrences.get(binding.source_id, {})
            target_item = self.occurrences.get(binding.target_id, {})
            if source_item.get("occurrence_kind") == "literal" or target_item.get("occurrence_kind") == "literal":
                continue
            # Collection element identity is published as its own causal edge
            # and is also available to the bounded external-response traversal.
            # Do not feed it into generic DTO field projection: doing so would
            # replicate every observed element field through unrelated generic
            # return/caller wrappers without adding evidence to collection
            # container or nested response paths.
            if binding.kind in {
                "collection_element_to_lambda_parameter", "collection_element_addition",
            }:
                continue
            forward_bindings[binding.source_id].append(binding)
            if binding.kind in {
                "variable_initializer", "assignment_expression", "method_argument_binding",
                "method_return", "return_to_caller", "interface_implementation_parameter_binding",
                "implementation_return_to_interface",
            }:
                reverse_bindings[binding.target_id].append(binding)

        containers_by_builder: dict[str, list[ContainerBinding]] = defaultdict(list)
        for binding in self._container_bindings:
            if binding.target_builder_key:
                containers_by_builder[self._builder_find(binding.target_builder_key)].append(binding)

        field_owners: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for object_id, fields in self._object_field_occurrences.items():
            for field_tail, occurrence_ids in fields.items():
                for occurrence_id in occurrence_ids:
                    field_owners[occurrence_id].append((object_id, field_tail))
        incoming_value_edges: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for edge in self.edges.values():
            if edge.get("edge_kind") in {"builder_argument", "setter_argument"}:
                incoming_value_edges[str(edge["target_occurrence_id"])].append(edge)

        # Publish a bounded whole-object dependency when concrete fields owned
        # by an observed source object are passed into a concrete builder and
        # that builder produces an object.  This does not assert object
        # equivalence: it records only that the source object contributed one
        # or more observed values to the built result.  There is deliberately
        # no type/name matching and no expansion beyond actual builder edges.
        object_contribution_edges = 0
        for build_result_id, (builder_root, build) in builds_by_result.items():
            contributions: dict[str, dict[str, set[str]]] = defaultdict(
                lambda: {"builder_fields": set(), "source_fields": set(), "source_occurrences": set()}
            )
            for builder_field_tail, observations in builder_fields_by_root.get(builder_root, {}).items():
                for observation in observations:
                    for value_edge in incoming_value_edges.get(observation.occurrence_id, []):
                        source_id = str(value_edge["source_occurrence_id"])
                        for object_id, source_field_tail in field_owners.get(source_id, []):
                            contribution = contributions[object_id]
                            contribution["builder_fields"].add(builder_field_tail)
                            contribution["source_fields"].add(source_field_tail)
                            contribution["source_occurrences"].add(source_id)
            for object_id, contribution in contributions.items():
                before = len(self.edges)
                self._edge(
                    object_id,
                    build_result_id,
                    ctx=build.ctx,
                    basis=build.basis,
                    kind="object_field_contribution_to_built_object",
                    method=build.method,
                    extra={
                        "builder_identity": builder_root,
                        "built_type": build.built_type,
                        "contribution_basis": "observed_builder_argument_field_owner",
                        "contributed_builder_fields": sorted(contribution["builder_fields"]),
                        "contributor_field_paths": sorted(contribution["source_fields"]),
                        "contributor_field_occurrence_ids": sorted(contribution["source_occurrences"]),
                    },
                )
                object_contribution_edges += len(self.edges) - before

        object_queue = deque(
            (object_id, tail, field_occurrence, False)
            for object_id, tail, field_occurrence in self._projection_seed_fields
        )
        seen_events: set[tuple[str, str, str, bool]] = set()
        projected_fields = 0
        projection_edges = 0
        operations = 0
        operation_budget = max(5_000, len(self._projection_seed_fields) * max(40, len(self._object_bindings) // 4))

        def add_edge(source: str, target: str, *, ctx: JavaFileContext, method: MethodInfo, basis: Node, kind: str, extra: dict[str, Any]) -> None:
            nonlocal projection_edges
            before = len(self.edges)
            self._edge(source, target, ctx=ctx, basis=basis, kind=kind, method=method, extra=extra)
            projection_edges += len(self.edges) - before

        def enqueue_occurrence_demand(occurrence_id: str, *, reverse_only: bool = False) -> None:
            for object_id, field_tail in field_owners.get(occurrence_id, []):
                object_queue.append((object_id, field_tail, occurrence_id, reverse_only))
            for edge in incoming_value_edges.get(occurrence_id, []):
                source_id = str(edge["source_occurrence_id"])
                for object_id, field_tail in field_owners.get(source_id, []):
                    object_queue.append((object_id, field_tail, source_id, reverse_only))

        while object_queue and operations < operation_budget:
            object_id, tail, field_occurrence, reverse_only = object_queue.popleft()
            event = (object_id, tail, field_occurrence, reverse_only)
            if event in seen_events:
                continue
            seen_events.add(event)
            operations += 1

            # A value such as ``request.getProfile().getPhone()`` is an
            # AST-observed object field.  When a demanded child field reaches
            # that object (``phone.phoneNumber``), lift it to the mechanically
            # composed parent path (``request.profile.phone.phoneNumber``).
            # This is bounded by the demand queue and concrete field ownership;
            # no type/name join or DTO-wide expansion is performed.
            for parent_object_id, parent_field_tail in field_owners.get(object_id, []):
                if parent_object_id == object_id or not parent_field_tail:
                    continue
                origin = self._occurrence_origins.get(object_id)
                if origin is None:
                    continue
                origin_ctx, origin_node, origin_method = origin
                if origin_method is None:
                    continue
                parent_tail = f"{parent_field_tail}.{tail}" if tail else parent_field_tail
                parent_field, created = self._ensure_object_field(
                    parent_object_id,
                    parent_tail,
                    ctx=origin_ctx,
                    method=origin_method,
                    basis=origin_node,
                    projection_basis="observed_nested_object_parent_demand",
                    anchor_on_object=True,
                )
                if created:
                    projected_fields += 1
                # The lifted path exists to discover the upstream container
                # (ultimately an ingress payload). Continue demand backwards;
                # forwarding it again through return/caller aliases duplicates
                # the already-known child-to-sink path.
                object_queue.append((parent_object_id, parent_tail, parent_field, True))
                add_edge(
                    parent_field,
                    field_occurrence,
                    ctx=origin_ctx,
                    method=origin_method,
                    basis=origin_node,
                    kind="observed_nested_object_field_projection",
                    extra={
                        "parent_object_occurrence_id": parent_object_id,
                        "observed_child_object_occurrence_id": object_id,
                        "parent_field_tail": parent_field_tail,
                        "child_field_tail": tail,
                        "projected_field_tail": parent_tail,
                        "projection_basis": "tree_sitter_observed_property_ownership_and_sink_demand",
                    },
                )

            # Follow the actual direction of value transfer. A path lifted
            # from an observed nested object is a source-discovery branch and
            # must not be fanned forward again through caller/return aliases.
            if not reverse_only:
                for binding in forward_bindings.get(object_id, []):
                    target, created = self._ensure_object_field(
                        binding.target_id,
                        tail,
                        ctx=binding.ctx,
                        method=binding.method,
                        basis=binding.basis,
                        projection_basis=binding.kind,
                    )
                    if created:
                        projected_fields += 1
                    object_queue.append((binding.target_id, tail, target, False))
                    add_edge(
                        field_occurrence,
                        target,
                        ctx=binding.ctx,
                        method=binding.method,
                        basis=binding.basis,
                        kind=f"{binding.kind}_field_projection",
                        extra={
                            "object_binding_kind": binding.kind,
                            "projection_direction": "forward",
                            "projected_field_tail": tail,
                        },
                    )

            # Demand can travel backwards to discover the source, while the
            # emitted edge still keeps the real source -> target direction.
            for binding in reverse_bindings.get(object_id, []):
                source, created = self._ensure_object_field(
                    binding.source_id,
                    tail,
                    ctx=binding.ctx,
                    method=binding.method,
                    basis=binding.basis,
                    projection_basis=f"reverse-demand:{binding.kind}",
                )
                if created:
                    projected_fields += 1
                object_queue.append((binding.source_id, tail, source, reverse_only))
                add_edge(
                    source,
                    field_occurrence,
                    ctx=binding.ctx,
                    method=binding.method,
                    basis=binding.basis,
                    kind=f"{binding.kind}_field_projection",
                    extra={
                        "object_binding_kind": binding.kind,
                        "projection_direction": "forward_discovered_from_target",
                        "projected_field_tail": tail,
                    },
                )

            build_entry = builds_by_result.get(object_id)
            if build_entry is None:
                continue
            builder_root, build = build_entry

            # Direct scalar/object field written on this builder.
            for source_field in builder_fields_by_root.get(builder_root, {}).get(tail, []):
                # A demanded builder field also demands the concrete expression
                # passed to that setter.  When that expression is a field on a
                # helper parameter, this activates the already observed
                # caller-argument -> callee-parameter object binding without
                # expanding unrelated fields.
                enqueue_occurrence_demand(
                    source_field.occurrence_id,
                    reverse_only=reverse_only,
                )
                add_edge(
                    source_field.occurrence_id,
                    field_occurrence,
                    ctx=build.ctx,
                    method=build.method,
                    basis=build.basis,
                    kind="builder_field_to_built_object",
                    extra={
                        "builder_identity": builder_root,
                        "builder_field_tail": tail,
                        "built_type": build.built_type,
                    },
                )

            # Nested object assigned to a parent builder field. A demand for
            # parent.child is projected only into the concrete child field;
            # no Cartesian expansion of all child DTO fields is performed.
            for container in containers_by_builder.get(builder_root, []):
                prefix = container.target_field_tail
                if not tail.startswith(prefix + "."):
                    continue
                child_tail = tail[len(prefix) + 1:]
                child_field, created = self._ensure_object_field(
                    container.source_id,
                    child_tail,
                    ctx=container.ctx,
                    method=container.method,
                    basis=container.basis,
                    projection_basis=f"nested-demand:{container.target_id}",
                )
                if created:
                    projected_fields += 1
                object_queue.append((container.source_id, child_tail, child_field, reverse_only))

                target_item = self.occurrences.get(container.target_id, {})
                label = str(target_item.get("builder_label") or self._object_label(container.target_id).rsplit(".", 1)[0])
                nested, nested_created = self._ensure_builder_field(
                    builder_key=builder_root,
                    field_tail=tail,
                    label=label,
                    ctx=container.ctx,
                    method=container.method,
                    basis=container.basis,
                    projection_basis=f"container:{container.target_id}",
                )
                if nested_created:
                    projected_fields += 1
                    builder_fields_by_root[builder_root][tail].append(nested)
                add_edge(
                    child_field,
                    nested.occurrence_id,
                    ctx=container.ctx,
                    method=container.method,
                    basis=container.basis,
                    kind="nested_object_field_projection",
                    extra={
                        "container_field": prefix,
                        "nested_field_tail": child_tail,
                        "projected_field_tail": tail,
                    },
                )
                add_edge(
                    nested.occurrence_id,
                    field_occurrence,
                    ctx=build.ctx,
                    method=build.method,
                    basis=build.basis,
                    kind="builder_field_to_built_object",
                    extra={
                        "builder_identity": builder_root,
                        "builder_field_tail": tail,
                        "built_type": build.built_type,
                    },
                )

        if operations >= operation_budget and object_queue:
            self.diagnostics.append({
                "kind": "field_projection_budget_reached",
                "operation_budget": operation_budget,
                "remaining_object_events": len(object_queue),
            })
        return {
            "mode": "boundary_seeded_demand_driven",
            "projection_seed_fields": len(self._projection_seed_fields),
            "projection_seed_candidates": self._projection_seed_candidates,
            "projection_seed_skipped_without_source": self._projection_seed_skipped_without_source,
            "projection_seed_skipped_without_sink": self._projection_seed_skipped_without_sink,
            "object_bindings_observed": len(self._object_bindings),
            "container_bindings_observed": len(self._container_bindings),
            "builder_fields_observed": len(self._builder_fields),
            "builder_builds_observed": len(self._builder_builds),
            "object_contribution_edges_created": object_contribution_edges,
            "projection_methods_selected": len(self.projection_method_ids),
            "projected_fields_created": projected_fields,
            "projection_edges_created": projection_edges,
            "projection_operations": operations,
            "projection_operation_budget": operation_budget,
        }

    def _finalize_builder_aliases(self) -> None:
        for binding in self._object_bindings:
            source_key = self._builder_key_for_occurrence(binding.source_id)
            target_key = self._builder_key_for_occurrence(binding.target_id)
            if source_key and target_key:
                self._builder_union(source_key, target_key)

    def _observed_builder_field_paths(self, payload_type: str, *, max_depth: int = 5, max_paths: int = 256) -> list[str]:
        """Return concrete Java builder field paths observed for a payload type.

        This is a Tree-sitter-derived fallback for DTOs supplied only by an
        external dependency.  Paths are assembled solely from observed
        ``builder()/setter/build()`` object relations; no source text parsing or
        same-name/type guessing is used.
        """
        wanted = _simple_type(payload_type)
        if wanted in {"", "unknown", "Object"}:
            return []

        fields_by_root: dict[str, set[str]] = defaultdict(set)
        for item in self._builder_fields:
            fields_by_root[self._builder_find(item.builder_key)].add(item.field_tail)

        build_root_by_result: dict[str, str] = {}
        roots: set[str] = set()
        for item in self._builder_builds:
            root = self._builder_find(item.builder_key)
            build_root_by_result[item.result_occurrence_id] = root
            if _simple_type(item.built_type) == wanted:
                roots.add(root)
        if not roots:
            return []

        object_neighbors: dict[str, set[str]] = defaultdict(set)
        for binding in self._object_bindings:
            if binding.kind not in {
                "variable_initializer", "assignment_expression", "method_argument_binding",
                "method_return", "return_to_caller", "collection_element_to_lambda_parameter",
                "collection_element_addition",
            }:
                continue
            object_neighbors[binding.source_id].add(binding.target_id)
            object_neighbors[binding.target_id].add(binding.source_id)

        def reachable_build_root(object_id: str) -> str | None:
            if object_id in build_root_by_result:
                return build_root_by_result[object_id]
            queue: deque[tuple[str, int]] = deque([(object_id, 0)])
            visited = {object_id}
            while queue:
                current, distance = queue.popleft()
                if distance >= 8:
                    continue
                for nxt in object_neighbors.get(current, set()):
                    if nxt in visited:
                        continue
                    if nxt in build_root_by_result:
                        return build_root_by_result[nxt]
                    visited.add(nxt)
                    queue.append((nxt, distance + 1))
            return None

        containers_by_root: dict[str, list[ContainerBinding]] = defaultdict(list)
        for binding in self._container_bindings:
            if binding.target_builder_key:
                containers_by_root[self._builder_find(binding.target_builder_key)].append(binding)

        paths: set[str] = set()

        def collect(root: str, prefix: str, depth: int, visited_roots: tuple[str, ...]) -> None:
            if depth > max_depth or root in visited_roots or len(paths) >= max_paths:
                return
            next_visited = (*visited_roots, root)
            for field_tail in sorted(fields_by_root.get(root, set())):
                path = f"{prefix}.{field_tail}" if prefix else field_tail
                paths.add(path)
                if len(paths) >= max_paths:
                    return
            for binding in containers_by_root.get(root, []):
                container_path = f"{prefix}.{binding.target_field_tail}" if prefix else binding.target_field_tail
                paths.add(container_path)
                child_root = reachable_build_root(binding.source_id)
                if child_root is not None:
                    collect(child_root, container_path, depth + 1, next_visited)
                if len(paths) >= max_paths:
                    return

        for root in sorted(roots):
            collect(root, "", 0, ())
            if len(paths) >= max_paths:
                break
        return sorted(paths)

    def _method_return_occurrence(self, index: FileIndex, method: MethodInfo) -> str:
        return self._occurrence(ctx=index.ctx, node=method.node, method=method, kind="method_return",
                                field_path=f"{method.type_name}.{method.name}.return", declared_type=method.return_type)

    @staticmethod
    def _interface_kind(interface: InterfaceInfo) -> str:
        return getattr(interface.kind, "value", str(interface.kind)).lower()

    @staticmethod
    def _interface_direction(interface: InterfaceInfo) -> str:
        return getattr(interface.direction, "value", str(interface.direction)).lower()

    def _request_payload_type(self, interface: InterfaceInfo) -> str:
        props = interface.properties or {}
        value = props.get("request_payload_type") or props.get("message_payload_type")
        if not value and self._interface_kind(interface) == "kafka":
            value = interface.schema_ref
        if not value and self._interface_direction(interface) == "inbound":
            value = interface.schema_ref
        return _simple_type(str(value or ""))

    def _response_payload_type(self, interface: InterfaceInfo) -> str:
        props = interface.properties or {}
        value = props.get("response_payload_type")
        boundary_role = str(props.get("boundary_role") or "").lower()
        if not value and boundary_role in {"rest_response", "http_outbound", "grpc_response", "framework_callback_response"}:
            value = interface.schema_ref
        return _simple_type(str(value or ""))

    @staticmethod
    def _boundary_role(interface: InterfaceInfo) -> str:
        return str((interface.properties or {}).get("boundary_role") or "").lower()

    @staticmethod
    def _type_mentions_payload(type_text: str | None, payload_type: str) -> bool:
        if not type_text or payload_type in {"", "unknown", "Object"}:
            return False
        return payload_type in {
            _simple_type(token)
            for token in re.findall(r"[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*", str(type_text))
        }

    def _resolved_occurrence_type(self, occurrence_id: str, *, max_depth: int = 6) -> str:
        cache_key = (occurrence_id, max_depth)
        cached = self._resolved_occurrence_type_cache.get(cache_key)
        if cached is not None:
            return cached
        queue: deque[tuple[str, int]] = deque([(occurrence_id, 0)])
        seen: set[str] = set()
        while queue:
            current, depth = queue.popleft()
            if current in seen or depth > max_depth:
                continue
            seen.add(current)
            item = self.occurrences.get(current, {})
            declared = _simple_type(str(item.get("declared_type") or ""))
            if declared not in {"", "unknown", "var", "T", "K", "Object"}:
                self._resolved_occurrence_type_cache[cache_key] = declared
                return declared
            for edge in self._incoming_edges_by_target.get(current, []):
                if edge.get("edge_kind") in {
                    "variable_initializer", "assignment_expression", "return_to_caller",
                    "implementation_return_to_interface", "method_argument_binding",
                    "collection_element_to_lambda_parameter", "collection_element_addition",
                }:
                    source_id = str(edge.get("source_occurrence_id") or "")
                    if source_id:
                        queue.append((source_id, depth + 1))
        self._resolved_occurrence_type_cache[cache_key] = "unknown"
        return "unknown"

    def _has_occurrence_path(self, source_id: str, target_id: str, *, max_depth: int = 10) -> bool:
        cache_key = (source_id, target_id, max_depth)
        cached = self._occurrence_path_cache.get(cache_key)
        if cached is not None:
            return cached
        if source_id == target_id:
            self._occurrence_path_cache[cache_key] = True
            return True
        queue: deque[tuple[str, int]] = deque([(source_id, 0)])
        seen = {source_id}
        while queue:
            current, depth = queue.popleft()
            if depth >= max_depth:
                continue
            for nxt in self._outgoing_occurrence_ids.get(current, []):
                if not nxt or nxt in seen:
                    continue
                if nxt == target_id:
                    self._occurrence_path_cache[cache_key] = True
                    return True
                seen.add(nxt)
                queue.append((nxt, depth + 1))
        self._occurrence_path_cache[cache_key] = False
        return False

    def _serializer_response_candidates(
        self,
        index: FileIndex,
        method: MethodInfo,
    ) -> list[tuple[str, Node, str, str, str]]:
        """Return explicitly serialized response objects in the endpoint method.

        Candidates are derived only from Tree-sitter occurrences and directed
        field-flow edges already extracted from the same parse.  The serialized
        value must reach the endpoint method return, which excludes logging-only
        serialization calls.
        """
        method_return_id = self._method_return_occurrence(index, method)
        invocation_ids = {
            oid
            for oid, item in self.occurrences.items()
            if item.get("method_id") == method.method_id
            and item.get("occurrence_kind") == "method_invocation"
            and re.search(
                r"(?:^|\.)(?:serialize|writeValueAsString|toJson)\(\)$",
                str(item.get("field_path") or item.get("expression_text") or ""),
            )
            and self._has_occurrence_path(oid, method_return_id)
        }
        out: list[tuple[str, Node, str, str, str]] = []
        seen: set[tuple[str, str]] = set()
        for edge in self.edges.values():
            if edge.get("target_occurrence_id") not in invocation_ids:
                continue
            if edge.get("edge_kind") not in {"invocation_argument", "method_argument_binding"}:
                continue
            source_id = str(edge.get("source_occurrence_id") or "")
            source = self.occurrences.get(source_id, {})
            payload_type = self._resolved_occurrence_type(source_id)
            if payload_type in {"", "unknown", "var", "String", "Object"}:
                continue
            schema = self.schemas_by_name.get(payload_type)
            if schema is None or not schema.fields:
                continue
            key = (source_id, payload_type)
            if key in seen:
                continue
            seen.add(key)
            label = str(source.get("field_path") or source.get("symbol") or payload_type)
            node = next(
                (
                    symbol.node
                    for symbol in method.symbols
                    if symbol.occurrence_id == source_id
                ),
                method.node,
            )
            out.append((source_id, node, label, payload_type, "explicit_serializer_argument_reaching_response"))
        return out

    def _response_object_candidates(
        self,
        index: FileIndex,
        method: MethodInfo,
        interface: InterfaceInfo,
    ) -> list[tuple[str, Node, str, str, str]]:
        boundary_role = self._boundary_role(interface)
        payload_type = self._response_payload_type(interface)
        declared_return_text = (
            index.ctx.text(_node_field(method.node, "type"))
            if method.node.type == "method_declaration"
            else method.return_type
        )
        out: list[tuple[str, Node, str, str, str]] = []
        seen: set[tuple[str, str]] = set()

        def add(object_id: str, node: Node, label: str, resolved_type: str, basis: str) -> None:
            key = (object_id, resolved_type)
            if resolved_type in {"", "unknown", "Object", "HttpResponse", "ResponseEntity"} or key in seen:
                return
            seen.add(key)
            out.append((object_id, node, label, resolved_type, basis))

        # A client response is represented by the concrete local DTO produced by
        # the HTTP call.  It is intentionally not treated as an outbound return.
        if boundary_role == "http_outbound":
            for symbol in method.symbols:
                resolved = self._resolved_occurrence_type(symbol.occurrence_id)
                if resolved == payload_type:
                    add(symbol.occurrence_id, symbol.node, symbol.name, resolved, "typed_http_client_response_symbol")
            # Prefer the concrete deserialized local object.  Its ordinary
            # return/assignment bindings already propagate fields to callers.
            # Falling back to the method return only when no such symbol exists
            # avoids materializing the same response contract for every alias.
            if not out and self._type_mentions_payload(declared_return_text, payload_type):
                ret = self._method_return_occurrence(index, method)
                add(ret, method.node, f"{method.type_name}.{method.name}.return", payload_type, "typed_http_client_method_return")
            return out

        # Server responses may expose the DTO directly (including a generic
        # future wrapper) or serialize a DTO manually into HttpResponse.
        if payload_type not in {"", "unknown", "Object", "HttpResponse", "ResponseEntity"}:
            for symbol in method.symbols:
                resolved = self._resolved_occurrence_type(symbol.occurrence_id)
                if resolved == payload_type:
                    add(symbol.occurrence_id, symbol.node, symbol.name, resolved, "typed_server_response_symbol")
            if not out and self._type_mentions_payload(declared_return_text, payload_type):
                ret = self._method_return_occurrence(index, method)
                add(ret, method.node, f"{method.type_name}.{method.name}.return", payload_type, "declared_server_response_type")

        for candidate in self._serializer_response_candidates(index, method):
            add(*candidate)
        return out

    def _payload_symbols(
        self,
        index: FileIndex,
        method: MethodInfo,
        *,
        interface: InterfaceInfo,
        payload_type: str,
    ) -> list[tuple[Symbol, str]]:
        if payload_type in {"", "unknown", "Object"}:
            return []
        props = interface.properties or {}
        direction = self._interface_direction(interface)
        expression = str(
            props.get("request_payload_expression")
            or props.get("message_payload_expression")
            or props.get("payload_expression")
            or ""
        )
        exact = [symbol for symbol in method.symbols if _simple_type(symbol.declared_type) == payload_type]
        observed: list[tuple[Symbol, str]] = []
        for symbol in exact:
            if symbol.kind == "parameter":
                if direction == "inbound":
                    observed.append((symbol, "typed_boundary_method_parameter"))
                elif re.search(rf"\b{re.escape(symbol.name)}\b", index.ctx.text(method.body) if method.body else expression):
                    observed.append((symbol, "typed_payload_symbol_used_in_boundary_operation"))
                continue
            value = _node_field(symbol.node, "value")
            value_text = index.ctx.text(value) if value is not None else ""
            if direction == "inbound":
                has_deserializer = bool(re.search(r"\b(deserialize|readValue|fromJson)\s*\(", value_text))
                has_class_literal = bool(re.search(rf"\b{re.escape(payload_type)}\s*\.\s*class\b", value_text))
                if has_deserializer and has_class_literal:
                    observed.append((symbol, "explicit_deserializer_result_type"))
            elif symbol.name and re.search(rf"\b{re.escape(symbol.name)}\b", expression):
                observed.append((symbol, "payload_expression_symbol"))
        if observed:
            return observed
        # An outbound scanner may resolve the payload through a wrapper such as
        # HttpEntity<T>.  In that case the concrete T symbol is still observable
        # in the same boundary operation.  Use it only when the type match is unique.
        if direction == "outbound" and len(exact) == 1:
            return [(exact[0], "unique_payload_type_symbol_in_boundary_operation")]
        return []

    def _schema_field_paths(
        self,
        schema: SchemaInfo,
        *,
        java_prefix: str = "",
        wire_prefix: str = "",
        visited: tuple[str, ...] = (),
        depth: int = 0,
        max_depth: int = 5,
    ) -> Iterable[tuple[str, str, Any, int]]:
        schema_name = _simple_type(schema.name)
        if depth > max_depth or schema_name in visited:
            return
        next_visited = (*visited, schema_name)
        for field in schema.fields:
            java_name = str(field.name or "").strip()
            if not java_name:
                continue
            wire_name = str(field.serialized_name or java_name).strip()
            java_path = f"{java_prefix}.{java_name}" if java_prefix else java_name
            wire_path = f"{wire_prefix}.{wire_name}" if wire_prefix else wire_name
            yield java_path, wire_path, field, depth

            nested_type = str(field.nested_type or "").strip()
            if not nested_type:
                raw_type = str(field.type or "")
                generic_types = re.findall(r"[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*", raw_type)
                candidates = [x for x in generic_types if _simple_type(x) not in {"List", "Set", "Collection", "Iterable", "Map", "Optional"}]
                nested_type = candidates[-1] if candidates else raw_type
            nested_schema = self.schemas_by_name.get(_simple_type(nested_type))
            if nested_schema is None:
                continue
            yield from self._schema_field_paths(
                nested_schema,
                java_prefix=java_path,
                wire_prefix=wire_path,
                visited=next_visited,
                depth=depth + 1,
                max_depth=max_depth,
            )

    def _prepare_projection_source_index(self) -> None:
        traversable_kinds = {
            "variable_initializer", "assignment_expression", "method_argument_binding",
            "method_return", "return_to_caller", "interface_implementation_parameter_binding",
            "implementation_return_to_interface", "collection_element_to_lambda_parameter",
            "collection_element_addition",
        }
        self._projection_forward_bindings.clear()
        self._projection_reverse_bindings.clear()
        for binding in self._object_bindings:
            if binding.kind in traversable_kinds:
                self._projection_forward_bindings[binding.source_id].append(binding)
                self._projection_reverse_bindings[binding.target_id].append(binding)

        self._projection_build_root_by_result.clear()
        self._projection_builder_fields_by_root.clear()
        self._projection_containers_by_root.clear()
        for item in self._builder_fields:
            self._projection_builder_fields_by_root[self._builder_find(item.builder_key)].add(item.field_tail)
        for item in self._builder_builds:
            self._projection_build_root_by_result[item.result_occurrence_id] = self._builder_find(item.builder_key)
        for binding in self._container_bindings:
            if binding.target_builder_key:
                self._projection_containers_by_root[self._builder_find(binding.target_builder_key)].append(binding)
        self._projection_source_cache.clear()
        self._projection_sink_cache.clear()

    def _observed_object_field(self, object_id: str, field_tail: str) -> str | None:
        """Return an AST-observed field occurrence reachable from ``object_id``.

        Dotted paths are followed through concrete getter/field-access
        occurrences (``response.phone.phoneNumber``), never by matching field
        names or declared types across unrelated objects. Contract-generated
        payload fields and previously projected placeholders are deliberately
        excluded: this helper is used to decide whether a client response field
        has a real downstream consumer before activating field projection.
        """
        tail = field_tail.strip(".")
        if not tail:
            return None
        fields = self._object_fields.get(object_id, {})
        direct_candidates = self._object_field_occurrences.get(object_id, {}).get(tail, [])
        if not direct_candidates and fields.get(tail):
            direct_candidates = [fields[tail]]
        for direct in direct_candidates:
            kind = str(self.occurrences.get(direct, {}).get("occurrence_kind") or "")
            if kind not in {"payload_field", "projected_object_field"}:
                return direct

        head, separator, remainder = tail.partition(".")
        if not separator:
            return None
        child_candidates = self._object_field_occurrences.get(object_id, {}).get(head, [])
        if not child_candidates and fields.get(head):
            child_candidates = [fields[head]]
        for child in child_candidates:
            child_kind = str(self.occurrences.get(child, {}).get("occurrence_kind") or "")
            if child_kind in {"payload_field", "projected_object_field"}:
                continue
            observed = self._observed_object_field(child, remainder)
            if observed:
                return observed
        return None

    def _projection_sink_available(self, object_id: str, field_tail: str, *, max_events: int = 512) -> bool:
        """Check whether a response field is consumed downstream.

        The lookup follows only explicit object-value bindings already derived
        from the Tree-sitter AST (assignment, argument/parameter, return, and
        interface/implementation bindings). It is bounded and cached so adding
        client-response projection does not turn every response DTO field into
        an interprocedural graph expansion.
        """
        cache_key = (object_id, field_tail)
        cached = self._projection_sink_cache.get(cache_key)
        if cached is not None:
            return cached

        queue: deque[str] = deque([object_id])
        seen: set[str] = set()
        events = 0
        while queue and events < max_events:
            current_id = queue.popleft()
            if current_id in seen:
                continue
            seen.add(current_id)
            events += 1

            if self._observed_object_field(current_id, field_tail):
                self._projection_sink_cache[cache_key] = True
                return True

            for binding in self._projection_forward_bindings.get(current_id, []):
                queue.append(binding.target_id)

        self._projection_sink_cache[cache_key] = False
        return False

    def _projection_source_available(self, object_id: str, field_tail: str, *, max_events: int = 512) -> bool:
        """Check for an observed producer before materializing a field path.

        This is a bounded graph lookup over relations already extracted from the
        Tree-sitter AST.  It never matches objects by field name or type alone.
        Contract fields remain published even when this returns ``False``; only
        the expensive backwards field projection is skipped.
        """
        cache_key = (object_id, field_tail)
        cached = self._projection_source_cache.get(cache_key)
        if cached is not None:
            return cached

        queue: deque[tuple[str, str]] = deque([cache_key])
        seen: set[tuple[str, str]] = set()
        events = 0
        while queue and events < max_events:
            current_id, tail = queue.popleft()
            event = (current_id, tail)
            if event in seen:
                continue
            seen.add(event)
            events += 1

            if tail in self._object_fields.get(current_id, {}):
                self._projection_source_cache[cache_key] = True
                return True

            builder_root = self._projection_build_root_by_result.get(current_id)
            if builder_root is not None:
                if tail in self._projection_builder_fields_by_root.get(builder_root, set()):
                    self._projection_source_cache[cache_key] = True
                    return True
                for container in self._projection_containers_by_root.get(builder_root, []):
                    prefix = container.target_field_tail
                    if tail == prefix:
                        self._projection_source_cache[cache_key] = True
                        return True
                    if tail.startswith(prefix + "."):
                        queue.append((container.source_id, tail[len(prefix) + 1:]))

            for binding in self._projection_reverse_bindings.get(current_id, []):
                queue.append((binding.source_id, tail))

        self._projection_source_cache[cache_key] = False
        return False

    def _process_request_field_bindings(self, index: FileIndex, method: MethodInfo, interface: InterfaceInfo) -> None:
        direction = self._interface_direction(interface)
        kind = self._interface_kind(interface)
        if direction not in {"inbound", "outbound"} or kind not in {"rest", "kafka", "grpc", "callback"}:
            return
        payload_type = self._request_payload_type(interface)
        schema = self.schemas_by_name.get(payload_type)
        symbols = self._payload_symbols(index, method, interface=interface, payload_type=payload_type)
        if not symbols:
            return
        role = "message" if kind == "kafka" else "request"
        field_specs: list[tuple[str, str, str | None, str, str | None, int, str]] = []
        if schema is not None:
            field_specs = [
                (
                    java_name,
                    wire_name,
                    str(field.type or "unknown"),
                    field.serialized_name_basis or "java_field_name_default",
                    field.serialization_library,
                    field_depth,
                    "local_schema_contract",
                )
                for java_name, wire_name, field, field_depth in self._schema_field_paths(schema)
            ]
        elif direction == "outbound":
            field_specs = [
                (
                    path,
                    path,
                    None,
                    "source_observed_builder_java_name_wire_alias_unverified",
                    None,
                    path.count("."),
                    "tree_sitter_observed_builder_object_path",
                )
                for path in self._observed_builder_field_paths(payload_type)
            ]
        if not field_specs:
            return
        schema_backed = schema is not None
        binding_kind = (
            f"{kind}_{role}_serialization_field"
            if direction == "outbound" and schema_backed
            else f"{kind}_{role}_deserialization_field"
            if direction == "inbound"
            else f"{kind}_{role}_observed_object_field"
        )
        for symbol, symbol_basis in symbols:
            for java_name, wire_name, field_type, serialized_name_basis, serialization_library, field_depth, path_basis in field_specs:
                if not schema_backed:
                    self._observed_builder_boundary_field_count += 1
                source_available = (
                    direction == "outbound"
                    and self._projection_source_available(symbol.occurrence_id, java_name)
                )
                local_field = self._occurrence(
                    ctx=index.ctx,
                    node=symbol.node,
                    method=method,
                    kind="payload_field",
                    symbol=symbol.name,
                    field_path=f"{symbol.name}.{java_name}",
                    declared_type=field_type,
                    extra={
                        "payload_type": payload_type,
                        "payload_role": role,
                        "java_field_name": java_name,
                        "wire_field_path": wire_name,
                        "serialized_name_basis": serialized_name_basis,
                        "serialization_library": serialization_library,
                        "field_binding_basis": symbol_basis,
                        "field_path_basis": path_basis,
                        "wire_alias_resolution_status": "resolved_from_local_schema" if schema_backed else "unverified_external_contract",
                        "field_path_depth": field_depth,
                    },
                )
                self._register_object_field(symbol.occurrence_id, java_name, local_field)
                # Projection is demand-driven in both directions. Outbound fields
                # require an observed producer. Inbound fields are seeded only when
                # the exact payload object reaches an AST-observed consumer of this
                # exact field through explicit object bindings. This avoids expanding
                # entire DTO contracts while preserving transformed inputs whose
                # source is not reachable by reverse builder demand (for example a
                # collection getter inside stream/map/collect).
                if direction == "outbound":
                    self._projection_seed_candidates += 1
                    if source_available:
                        self._projection_seed_fields.add((symbol.occurrence_id, java_name, local_field))
                    else:
                        self._projection_seed_skipped_without_source += 1
                elif direction == "inbound":
                    self._projection_seed_candidates += 1
                    if self._projection_sink_available(symbol.occurrence_id, java_name):
                        self._projection_seed_fields.add((symbol.occurrence_id, java_name, local_field))
                    else:
                        self._projection_seed_skipped_without_sink += 1
                boundary_field = self._occurrence(
                    ctx=index.ctx,
                    node=method.node,
                    method=method,
                    kind="boundary_field",
                    field_path=f"boundary:{kind}:{interface.path or interface.name}:{role}.{wire_name}",
                    declared_type=field_type,
                    extra={
                        "boundary_direction": direction,
                        "boundary_kind": kind,
                        "boundary_name": interface.name,
                        "boundary_path": interface.path,
                        "payload_type": payload_type,
                        "payload_role": role,
                        "java_field_name": java_name,
                        "wire_field_path": wire_name,
                        "serialized_name_basis": serialized_name_basis,
                        "serialization_library": serialization_library,
                        "field_binding_kind": binding_kind,
                        "field_binding_basis": symbol_basis,
                        "field_path_basis": path_basis,
                        "wire_alias_resolution_status": "resolved_from_local_schema" if schema_backed else "unverified_external_contract",
                        "field_path_depth": field_depth,
                    },
                )
                extra = {
                    "boundary_direction": direction,
                    "boundary_kind": kind,
                    "boundary_name": interface.name,
                    "boundary_path": interface.path,
                    "payload_type": payload_type,
                    "payload_role": role,
                    "java_field_name": java_name,
                    "wire_field_path": wire_name,
                    "serialized_name_basis": serialized_name_basis,
                    "serialization_library": serialization_library,
                    "field_binding_basis": symbol_basis,
                    "field_path_basis": path_basis,
                    "wire_alias_resolution_status": "resolved_from_local_schema" if schema_backed else "unverified_external_contract",
                    "field_path_depth": field_depth,
                }
                if direction == "outbound":
                    self._edge(local_field, boundary_field, ctx=index.ctx, basis=symbol.node, kind=binding_kind, method=method, extra=extra)
                else:
                    self._edge(boundary_field, local_field, ctx=index.ctx, basis=symbol.node, kind=binding_kind, method=method, extra=extra)

    def _reachable_external_response_properties(
        self,
        object_id: str,
        *,
        max_events: int = 512,
        max_depth: int = 16,
    ) -> list[tuple[str, str, dict[str, Any], list[str], list[str]]]:
        """Return observed property paths reachable through explicit value bindings.

        Nested paths are assembled only by following an AST-observed property
        value and then explicit object bindings from that value.  This covers
        collection element lambdas and helper aliases without joining objects by
        type or field name.  For example, an observed path can be
        ``shippingAddresses.address.line3`` only when the parse contains the
        corresponding getter/property chain and value bindings.
        """
        cached = self._external_response_property_cache.get(object_id)
        if cached is not None:
            self._external_response_property_cache_hits += 1
            return [
                (name, occurrence_id, local, list(relation_path), list(object_path))
                for name, occurrence_id, local, relation_path, object_path in cached
            ]

        queue: deque[tuple[str, str, tuple[str, ...], tuple[str, ...], int]] = deque([
            (object_id, "", (), (object_id,), 0)
        ])
        seen: set[tuple[str, str]] = set()
        results: list[tuple[str, str, dict[str, Any], list[str], list[str]]] = []
        result_keys: set[tuple[str, str]] = set()
        events = 0
        while queue and events < max_events:
            current_id, prefix, relation_path, object_path, depth = queue.popleft()
            event_key = (current_id, prefix)
            if event_key in seen:
                continue
            seen.add(event_key)
            events += 1
            self._external_response_property_object_visit_count += 1

            for property_name, occurrence_ids in sorted(
                self._object_field_occurrences.get(current_id, {}).items()
            ):
                # Dotted entries are projections created for other boundary
                # demands.  External response observations are constructed from
                # concrete direct getter/field-access steps only.
                if not property_name or "." in property_name:
                    continue
                property_path = f"{prefix}.{property_name}" if prefix else property_name
                for local_field in sorted(set(occurrence_ids)):
                    local = self.occurrences.get(local_field) or {}
                    if local.get("occurrence_kind") in {"payload_field", "projected_object_field"}:
                        continue
                    key = (property_path, local_field)
                    if key not in result_keys:
                        result_keys.add(key)
                        results.append((
                            property_path,
                            local_field,
                            local,
                            list(relation_path),
                            list(object_path),
                        ))
                    if depth < max_depth:
                        queue.append((
                            local_field,
                            property_path,
                            (*relation_path, "observed_property_value"),
                            (*object_path, local_field),
                            depth + 1,
                        ))

            if depth >= max_depth:
                continue
            for binding in self._projection_forward_bindings.get(current_id, []):
                next_key = (binding.target_id, prefix)
                if next_key in seen:
                    continue
                queue.append((
                    binding.target_id,
                    prefix,
                    (*relation_path, binding.kind),
                    (*object_path, binding.target_id),
                    depth + 1,
                ))
        self._external_response_property_cache[object_id] = tuple(
            (name, occurrence_id, local, tuple(relation_path), tuple(object_path))
            for name, occurrence_id, local, relation_path, object_path in results
        )
        return results

    def _process_external_response_property_observations(
        self,
        index: FileIndex,
        method: MethodInfo,
        interface: InterfaceInfo,
        candidates: list[tuple[str, Node, str, str, str]],
    ) -> None:
        """Publish observed Java properties on external HTTP response DTOs.

        The DTO source/JSON contract may be unavailable.  We therefore publish
        only mechanical JavaBeans getter/direct-field observations reachable
        from the concrete HTTP response object through explicit Tree-sitter
        object bindings.  The relation is correspondence, not deserialization
        or semantic identity, and carries an explicitly unverified wire alias.
        """
        for object_id, node, _label, payload_type, symbol_basis in candidates:
            for property_name, local_field, local, relation_path, object_path in (
                self._reachable_external_response_properties(object_id)
            ):
                property_basis = str(local.get("property_name_basis") or "observed_java_property")
                boundary_field = self._occurrence(
                    ctx=index.ctx,
                    node=node,
                    method=method,
                    kind="boundary_field",
                    field_path=f"boundary:rest:{interface.path or interface.name}:response.{property_name}",
                    declared_type=local.get("declared_type"),
                    extra={
                        "boundary_direction": "inbound",
                        "interaction_direction": "outbound",
                        "boundary_kind": "rest",
                        "boundary_name": interface.name,
                        "boundary_path": interface.path,
                        "payload_type": payload_type,
                        "payload_role": "response",
                        "java_field_name": property_name,
                        "wire_field_path": property_name,
                        "serialized_name_basis": property_basis,
                        "field_binding_kind": "rest_response_observed_getter_property",
                        "field_binding_basis": "property_reachable_from_http_response_via_object_bindings",
                        "field_path_basis": "observed_java_property",
                        "wire_alias_resolution_status": "unverified_external_contract",
                        "property_name": property_name.rsplit(".", 1)[-1],
                        "property_path": property_name,
                        "property_path_depth": property_name.count("."),
                        "property_name_basis": property_basis,
                        "accessor_method_name": local.get("accessor_method_name"),
                        "accessor_kind": local.get("accessor_kind"),
                        "object_binding_path": relation_path,
                        "reachable_object_occurrence_ids": object_path,
                        "observed_property_occurrence_id": local_field,
                    },
                )
                self._edge(
                    boundary_field,
                    local_field,
                    ctx=index.ctx,
                    basis=node,
                    kind="response_property_correspondence",
                    method=method,
                    extra={
                        "relation_class": "correspondence",
                        "correspondence_kind": "external_response_java_property",
                        "property_path": property_name,
                        "property_path_depth": property_name.count("."),
                        "same_normalized_property_path": True,
                        "payload_role": "response",
                        "payload_type": payload_type,
                        "wire_alias_verified": False,
                        "property_name_basis": property_basis,
                        "field_binding_basis": symbol_basis,
                        "object_binding_path": relation_path,
                        "reachable_object_occurrence_ids": object_path,
                        "observed_property_occurrence_id": local_field,
                    },
                )
                self._external_response_property_observation_count += 1

    def _process_response_field_bindings(self, index: FileIndex, method: MethodInfo, interface: InterfaceInfo) -> None:
        kind = self._interface_kind(interface)
        if kind not in {"rest", "grpc", "callback"}:
            return
        boundary_role = self._boundary_role(interface)
        if boundary_role not in {"http_outbound", "rest_response", "grpc_response", "framework_callback_response"}:
            return
        candidates = self._response_object_candidates(index, method, interface)
        if not candidates:
            return
        is_client_response = boundary_role == "http_outbound"
        binding_kind = (
            "rest_response_deserialization_field"
            if is_client_response
            else f"{kind}_response_serialization_field"
        )
        if is_client_response and not any(
            (self.schemas_by_name.get(payload_type) is not None and self.schemas_by_name[payload_type].fields)
            for _object_id, _node, _label, payload_type, _symbol_basis in candidates
        ):
            self._process_external_response_property_observations(index, method, interface, candidates)
        for object_id, node, label, payload_type, symbol_basis in candidates:
            schema = self.schemas_by_name.get(payload_type)
            if schema is None or not schema.fields:
                continue
            for java_name, wire_name, field, field_depth in self._schema_field_paths(schema):
                field_type = str(field.type or "unknown")
                serialized_name_basis = field.serialized_name_basis or "java_field_name_default"
                serialization_library = field.serialization_library
                # For a client response, field projection should continue only
                # when the returned object (or an explicitly bound alias/helper
                # parameter) has an AST-observed consumer for this exact field.
                # Evaluate this before registering the contract-generated local
                # payload field, otherwise every schema field would look used.
                downstream_sink = (
                    self._projection_sink_available(object_id, java_name)
                    if is_client_response
                    else False
                )
                local_field = self._occurrence(
                    ctx=index.ctx,
                    node=node,
                    method=method,
                    kind="payload_field",
                    field_path=f"{label}.{java_name}",
                    declared_type=field_type,
                    extra={
                        "object_occurrence_id": object_id,
                        "payload_type": payload_type,
                        "payload_role": "response",
                        "java_field_name": java_name,
                        "wire_field_path": wire_name,
                        "serialized_name_basis": serialized_name_basis,
                        "serialization_library": serialization_library,
                        "field_binding_basis": symbol_basis,
                        "field_path_basis": "local_schema_contract",
                        "wire_alias_resolution_status": "resolved_from_local_schema",
                        "field_path_depth": field_depth,
                    },
                )
                self._register_object_field(object_id, java_name, local_field)
                self._projection_seed_candidates += 1
                if is_client_response:
                    if downstream_sink:
                        self._projection_seed_fields.add((object_id, java_name, local_field))
                    else:
                        self._projection_seed_skipped_without_sink += 1
                else:
                    if self._projection_source_available(object_id, java_name):
                        self._projection_seed_fields.add((object_id, java_name, local_field))
                    else:
                        self._projection_seed_skipped_without_source += 1
                boundary_field = self._occurrence(
                    ctx=index.ctx,
                    node=method.node,
                    method=method,
                    kind="boundary_field",
                    field_path=f"boundary:{kind}:{interface.path or interface.name}:response.{wire_name}",
                    declared_type=field_type,
                    extra={
                        "boundary_direction": "inbound" if is_client_response else "outbound",
                        "interaction_direction": self._interface_direction(interface),
                        "boundary_kind": kind,
                        "boundary_name": interface.name,
                        "boundary_path": interface.path,
                        "payload_type": payload_type,
                        "payload_role": "response",
                        "java_field_name": java_name,
                        "wire_field_path": wire_name,
                        "serialized_name_basis": serialized_name_basis,
                        "serialization_library": serialization_library,
                        "field_binding_kind": binding_kind,
                        "field_binding_basis": symbol_basis,
                        "field_path_basis": "local_schema_contract",
                        "wire_alias_resolution_status": "resolved_from_local_schema",
                        "field_path_depth": field_depth,
                    },
                )
                extra = {
                    "boundary_direction": "inbound" if is_client_response else "outbound",
                    "interaction_direction": self._interface_direction(interface),
                    "boundary_kind": kind,
                    "boundary_name": interface.name,
                    "boundary_path": interface.path,
                    "payload_type": payload_type,
                    "payload_role": "response",
                    "java_field_name": java_name,
                    "wire_field_path": wire_name,
                    "serialized_name_basis": serialized_name_basis,
                    "serialization_library": serialization_library,
                    "field_binding_basis": symbol_basis,
                    "field_path_basis": "local_schema_contract",
                    "wire_alias_resolution_status": "resolved_from_local_schema",
                    "field_path_depth": field_depth,
                }
                if is_client_response:
                    self._edge(boundary_field, local_field, ctx=index.ctx, basis=node, kind=binding_kind, method=method, extra=extra)
                else:
                    self._edge(local_field, boundary_field, ctx=index.ctx, basis=node, kind=binding_kind, method=method, extra=extra)

    def _process_boundaries(self, index: FileIndex, method: MethodInfo) -> None:
        ctx = index.ctx
        operation = f"{method.type_name}.{method.name}"
        matches = [i for i in self.interfaces if str(i.operation or "") == operation]
        for interface in matches:
            direction = self._interface_direction(interface)
            schema = _simple_type(interface.schema_ref)
            boundary_role = self._boundary_role(interface)
            if direction == "inbound":
                for param in method.params:
                    if schema not in {"unknown", param.declared_type}:
                        continue
                    boundary = self._occurrence(
                        ctx=ctx,
                        node=method.node,
                        method=method,
                        kind="inbound_payload",
                        field_path=f"boundary:{self._interface_kind(interface)}:{interface.path or interface.name}:request",
                        declared_type=param.declared_type,
                        extra={
                            "boundary_direction": "inbound",
                            "boundary_kind": self._interface_kind(interface),
                            "boundary_name": interface.name,
                            "boundary_path": interface.path,
                            "payload_role": "request",
                        },
                    )
                    self._edge(boundary, param.occurrence_id, ctx=ctx, basis=method.node, kind="boundary_payload_binding", method=method)
            elif direction == "outbound" and boundary_role == "http_outbound":
                # The operation sends a request but receives its return value from
                # the remote system.  Preserve that response direction instead of
                # treating the client method return as an outbound server payload.
                response_candidates = self._response_object_candidates(index, method, interface)
                response_type = self._response_payload_type(interface)
                response_boundary = self._occurrence(
                    ctx=ctx,
                    node=method.node,
                    method=method,
                    kind="inbound_payload",
                    field_path=f"boundary:{self._interface_kind(interface)}:{interface.path or interface.name}:response",
                    declared_type=response_type,
                    extra={
                        "boundary_direction": "inbound",
                        "interaction_direction": "outbound",
                        "boundary_kind": self._interface_kind(interface),
                        "boundary_name": interface.name,
                        "boundary_path": interface.path,
                        "payload_role": "response",
                    },
                )
                for object_id, node, _label, payload_type, basis in response_candidates:
                    self._edge(
                        response_boundary,
                        object_id,
                        ctx=ctx,
                        basis=node,
                        kind="boundary_response_payload_binding",
                        method=method,
                        extra={
                            "payload_type": payload_type,
                            "payload_role": "response",
                            "field_binding_basis": basis,
                            "boundary_direction": "inbound",
                            "interaction_direction": "outbound",
                            "boundary_name": interface.name,
                            "boundary_path": interface.path,
                        },
                    )
            elif direction == "outbound" and method.return_type not in {"void", "unknown"}:
                boundary = self._occurrence(
                    ctx=ctx,
                    node=method.node,
                    method=method,
                    kind="outbound_payload",
                    field_path=f"boundary:{self._interface_kind(interface)}:{interface.path or interface.name}:response",
                    declared_type=method.return_type,
                    extra={
                        "boundary_direction": "outbound",
                        "boundary_kind": self._interface_kind(interface),
                        "boundary_name": interface.name,
                        "boundary_path": interface.path,
                        "payload_role": "response",
                    },
                )
                ret = self._method_return_occurrence(index, method)
                self._edge(ret, boundary, ctx=ctx, basis=method.node, kind="boundary_payload_binding", method=method)
            self._process_request_field_bindings(index, method, interface)
            self._process_response_field_bindings(index, method, interface)

    def build(self) -> tuple[list[Fact], dict[str, Any]]:
        for index in self.file_indexes:
            for method in index.methods:
                self._process_local_flows(index, method)
        self._process_interface_implementation_bindings()
        # Boundary demand must be created only after all Tree-sitter local and
        # interprocedural object relations are known.  This enables external DTO
        # fallback from observed builders without reparsing Java sources.
        self._finalize_builder_aliases()
        self._prepare_projection_source_index()
        for index in self.file_indexes:
            for method in index.methods:
                self._process_boundaries(index, method)
        projection_status = self._finalize_object_field_bindings()
        projection_status["observed_builder_boundary_fields"] = self._observed_builder_boundary_field_count
        projection_status["interface_implementation_bindings"] = self._interface_implementation_binding_count
        projection_status["external_response_property_observations"] = self._external_response_property_observation_count
        projection_status["external_response_property_objects_visited"] = self._external_response_property_object_visit_count
        projection_status["external_response_property_cache_hits"] = self._external_response_property_cache_hits
        facts: list[Fact] = []
        for item in sorted(self.occurrences.values(), key=lambda x: x["occurrence_id"]):
            loc = item.get("ast_node") or {}
            facts.append(Fact(
                fact_type="field_occurrence",
                name=item.get("field_path") or item.get("symbol") or item["occurrence_id"],
                properties=item,
                evidence=[EvidenceRef(file_path=item["file"], line_start=(loc.get("start_point") or [None])[0],
                                      line_end=(loc.get("end_point") or [None])[0], snippet=item.get("expression_text"), extractor="java_tree_sitter_field_flow")],
            ))
        for item in sorted(self.edges.values(), key=lambda x: x["edge_id"]):
            loc = item.get("ast_node") or {}
            facts.append(Fact(
                fact_type="field_flow_edge",
                name=f"{item['source_occurrence_id']} -> {item['target_occurrence_id']}",
                properties=item,
                evidence=[EvidenceRef(file_path=item["file"], line_start=(loc.get("start_point") or [None])[0],
                                      line_end=(loc.get("end_point") or [None])[0], extractor="java_tree_sitter_field_flow")],
            ))
        status = {
            "requested": True,
            "parser": "tree-sitter-java",
            "syntax_provider": "tree_sitter",
            "extractor": "java_tree_sitter_field_flow",
            "java_files_parsed": len(self.contexts),
            "java_files_with_parse_errors": sum(1 for c in self.contexts if c.parse_error),
            "syntax_cache": java_syntax_cache_stats(),
            "methods_indexed": sum(len(i.methods) for i in self.file_indexes),
            "field_occurrences_extracted": len(self.occurrences),
            "field_flow_edges_extracted": len(self.edges),
            "edge_kind_counts": dict(sorted(_counts(x.get("edge_kind") for x in self.edges.values()).items())),
            "occurrence_kind_counts": dict(sorted(_counts(x.get("occurrence_kind") for x in self.occurrences.values()).items())),
            "diagnostics_count": len(self.diagnostics),
            "diagnostics": self.diagnostics[:500],
            "object_field_projection": projection_status,
            "expression_memoization": {
                "entries": len(self._expression_occurrence_cache),
                "hits": self._expression_cache_hits,
                "misses": self._expression_cache_misses,
                "cycle_preventions": self._expression_cycle_preventions,
            },
            "object_field_registration": {
                "duplicate_registrations_skipped": self._object_field_duplicate_registrations_skipped,
            },
            "limitations": [
                "No whole-program Java semantic analysis",
                "Ambiguous overloads are not guessed",
                "Collection lambda support is bounded to explicit standard collection iteration/mutation calls; arbitrary callbacks, reflection and generated implementations are not expanded",
                "Tree-sitter is the only Java syntax parser used by this builder",
            ],
        }
        return facts, status


def _counts(values: Iterable[str | None]) -> dict[str, int]:
    out: dict[str, int] = defaultdict(int)
    for value in values:
        if value:
            out[value] += 1
    return dict(out)


def build_java_field_flow_facts(
    files: list[Path],
    *,
    interfaces: Iterable[InterfaceInfo] = (),
    schemas: Iterable[SchemaInfo] = (),
    repository_id: str | None = None,
    repository_root: Path | None = None,
) -> tuple[list[Fact], dict[str, Any]]:
    workspace = parse_java_workspace(files)
    contexts = [JavaFileContext(parsed) for parsed in workspace.parsed_files]
    return FieldFlowBuilder(
        contexts,
        interfaces=interfaces,
        schemas=schemas,
        repository_id=repository_id,
        repository_root=repository_root,
    ).build()
