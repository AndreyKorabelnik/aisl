from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Iterable, Mapping


def _json(value: Any, default: Any) -> Any:
    if value in (None, ""):
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value))
    except Exception:
        return default


def flatten_storage_alias(value: str) -> str:
    return str(value or "").strip().lower().replace("$", ".").replace(".", "_")


def relation_storage_identity(value: str) -> tuple[str, str]:
    """Return (flattened storage identity, representation) from a physical SQL relation.

    The schema part is intentionally ignored here: TSA storage aliases describe the
    physical object identity, while SQL schema is an independently bound runtime
    namespace.  Only an exact flattened alias match is accepted downstream.
    """
    tail = str(value or "").strip().lower().rsplit(".", 1)[-1]
    if tail.endswith("_hist"):
        return tail[:-5], "history"
    if tail.endswith("_delta"):
        return tail[:-6], "delta"
    return tail, "base"


def _walk_tree(node: Any) -> Iterable[Mapping[str, Any]]:
    if isinstance(node, Mapping):
        yield node
        for value in node.values():
            yield from _walk_tree(value)
    elif isinstance(node, list):
        for value in node:
            yield from _walk_tree(value)


def _tree_has_identifier(tree: Any, name: str) -> bool:
    want = name.lower()
    return any(
        str(node.get("node_type") or "").lower() == "identifier"
        and str(node.get("value") or "").lower() == want
        for node in _walk_tree(tree)
    )


def _tree_has_literal_value(tree: Any, literal: str) -> bool:
    return any(
        str(node.get("node_type") or "").lower() in {"string_fragment", "string_literal", "character_literal"}
        and literal in str(node.get("value") or "")
        for node in _walk_tree(tree)
    )


def _parent_key_shape_proven(payload: Mapping[str, Any]) -> bool:
    props = payload.get("properties") if isinstance(payload, Mapping) else {}
    props = props if isinstance(props, Mapping) else {}
    tree = props.get("storage_key_expression_tree")
    # Parent storage key must have an observed '_' prefix separator and one
    # non-literal value component.  We deliberately do not infer the field name.
    if not isinstance(tree, Mapping) or not _tree_has_literal_value(tree, "_"):
        return False
    nodes = list(_walk_tree(tree))
    return any(str(n.get("node_type") or "").lower() in {"method_invocation", "identifier", "field_access"} for n in nodes)


def _child_key_contains_parent_component(payload: Mapping[str, Any]) -> bool:
    props = payload.get("properties") if isinstance(payload, Mapping) else {}
    props = props if isinstance(props, Mapping) else {}
    tree = props.get("storage_key_expression_tree")
    return bool(
        isinstance(tree, Mapping)
        and _tree_has_identifier(tree, "parentKey")
        and _tree_has_literal_value(tree, ".")
    )


def _unquote_sql_literal(value: str) -> str:
    text = str(value or "").strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        text = text[1:-1]
    return text


def is_parent_key_identity_extraction(path: Any) -> bool:
    """Recognise the typed AST path extracting the value part from parentKey.

    Required shape is structural, not text/regex matching of a SQL expression:
      regexpsplit('.') -> [0] -> regexpsplit('_') -> [1]
    followed only by representation-neutral wrappers (cast/alias/etc.).
    """
    items = path if isinstance(path, list) else []
    if len(items) < 4 or not all(isinstance(x, Mapping) for x in items[:4]):
        return False
    a, b, c, d = items[:4]
    if str(a.get("operation") or "").lower() != "regexpsplit":
        return False
    dot = _unquote_sql_literal(str(a.get("secondary_expression") or ""))
    if dot.replace("\\\\", "\\") not in {".", "\\."}:
        return False
    if str(b.get("operation") or "").lower() != "bracket" or [str(x) for x in (b.get("index_expressions") or [])] != ["0"]:
        return False
    if str(c.get("operation") or "").lower() != "regexpsplit" or _unquote_sql_literal(str(c.get("secondary_expression") or "")) != "_":
        return False
    if str(d.get("operation") or "").lower() != "bracket" or [str(x) for x in (d.get("index_expressions") or [])] != ["1"]:
        return False
    neutral = {"alias", "cast", "trycast", "paren", "parentheses"}
    return all(str(item.get("operation") or "").lower() in neutral for item in items[4:])


@dataclass(frozen=True)
class ParentKeyLink:
    child_alias: str
    parent_alias: str
    child_key_field: str
    basis: str
    evidence_ids: tuple[str, ...]


class StorageKeySemanticIndex:
    """Evidence-backed storage key semantics used to normalise SQL value origins."""

    def __init__(self, connection: Any):
        self.aliases_by_flat: dict[str, tuple[str, ...]] = {}
        self.key_fields_by_alias: dict[str, tuple[str, ...]] = {}
        self.parent_links_by_child: dict[str, tuple[ParentKeyLink, ...]] = {}
        self.parent_shape_by_alias: dict[str, bool] = {}
        self._build(connection)

    def _build(self, c: Any) -> None:
        aliases: dict[str, set[str]] = defaultdict(set)
        key_fields: dict[str, set[str]] = defaultdict(set)
        parent_shapes: dict[str, bool] = defaultdict(bool)
        child_shapes: dict[str, bool] = defaultdict(bool)
        for alias, key_field, payload in c.execute(
            "SELECT storage_alias, storage_key_field, payload_json FROM model_storage_record ORDER BY storage_alias, observation_id"
        ).fetchall():
            a = str(alias or "").strip()
            if not a:
                continue
            aliases[flatten_storage_alias(a)].add(a)
            if key_field:
                key_fields[a].add(str(key_field))
            p = _json(payload, {})
            parent_shapes[a] = parent_shapes[a] or _parent_key_shape_proven(p)
            child_shapes[a] = child_shapes[a] or _child_key_contains_parent_component(p)

        links: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)

        # Explicit collection key-lineage fact is the strongest proof.
        table_names = {str(r[0]) for r in c.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='main'").fetchall()}
        if "model_storage_key_lineage" in table_names:
            for oid, parent, child, passed, payload in c.execute(
                "SELECT observation_id, source_alias, target_alias, source_key_passed_into_target_key, payload_json "
                "FROM model_storage_key_lineage WHERE source_key_passed_into_target_key=true ORDER BY observation_id"
            ).fetchall():
                parent = str(parent or "").strip(); child = str(child or "").strip()
                if not parent or not child or not passed or not child_shapes.get(child):
                    continue
                slot = links[child].setdefault(parent, {"bases": set(), "ids": set()})
                slot["bases"].add("model_storage_key_lineage.source_key_passed_into_target_key")
                slot["ids"].add(str(oid))

        # Scalar/reference records carry exact parameter binding evidence.  Accept
        # them only when the child key structurally consumes parentKey and the call
        # binding resolves the parentKey parameter exactly.
        if "model_storage_reference" in table_names:
            for oid, parent, child, key_field, payload in c.execute(
                "SELECT observation_id, source_alias, target_alias, target_storage_key_field, payload_json "
                "FROM model_storage_reference WHERE target_alias IS NOT NULL ORDER BY observation_id"
            ).fetchall():
                parent = str(parent or "").strip(); child = str(child or "").strip()
                if not parent or not child or not child_shapes.get(child):
                    continue
                p = _json(payload, {}); props = p.get("properties") if isinstance(p, Mapping) else {}
                props = props if isinstance(props, Mapping) else {}
                bindings = props.get("binding_path") if isinstance(props.get("binding_path"), list) else []
                exact = [b for b in bindings if isinstance(b, Mapping)
                         and str(b.get("callee_parameter") or "") == "parentKey"
                         and str(b.get("resolution") or "").startswith("exact_")
                         and str(b.get("resolved_expression") or "").strip()]
                if not exact:
                    continue
                slot = links[child].setdefault(parent, {"bases": set(), "ids": set()})
                slot["bases"].add("model_storage_reference.exact_parent_key_binding")
                slot["ids"].add(str(oid))
                if key_field:
                    key_fields[child].add(str(key_field))

        self.aliases_by_flat = {k: tuple(sorted(v)) for k, v in aliases.items()}
        self.key_fields_by_alias = {k: tuple(sorted(v)) for k, v in key_fields.items()}
        self.parent_shape_by_alias = dict(parent_shapes)
        out: dict[str, tuple[ParentKeyLink, ...]] = {}
        for child, by_parent in links.items():
            rows = []
            for parent, info in sorted(by_parent.items()):
                # Parent itself must have an observed key shape with '_' separator.
                if not parent_shapes.get(parent):
                    continue
                child_fields = sorted(key_fields.get(child) or {"key"})
                rows.append(ParentKeyLink(
                    child_alias=child,
                    parent_alias=parent,
                    child_key_field=child_fields[0],
                    basis="+".join(sorted(info["bases"])),
                    evidence_ids=tuple(sorted(info["ids"])),
                ))
            out[child] = tuple(rows)
        self.parent_links_by_child = out

    def resolve_relation_alias(self, relation_name: str) -> tuple[str | None, str, str]:
        flat, representation = relation_storage_identity(relation_name)
        candidates = self.aliases_by_flat.get(flat, ())
        if len(candidates) == 1:
            return candidates[0], representation, "unique_exact_flattened_storage_alias"
        if not candidates:
            return None, representation, "storage_alias_not_found"
        return None, representation, "storage_alias_ambiguous"

    def unique_parent_link(self, child_alias: str, source_column: str) -> tuple[ParentKeyLink | None, str]:
        links = [x for x in self.parent_links_by_child.get(child_alias, ()) if str(source_column or "").lower() == x.child_key_field.lower()]
        parents = {x.parent_alias for x in links}
        if len(parents) == 1:
            chosen = sorted(links, key=lambda x: (x.parent_alias, x.basis, x.evidence_ids))[0]
            ids = tuple(sorted({i for x in links for i in x.evidence_ids}))
            bases = "+".join(sorted({b for x in links for b in x.basis.split("+") if b}))
            return ParentKeyLink(chosen.child_alias, chosen.parent_alias, chosen.child_key_field, bases, ids), "matched"
        if not links:
            return None, "parent_key_link_not_found"
        return None, "parent_key_link_ambiguous"

    def ancestor_paths(self, child_alias: str, source_column: str, *, max_depth: int = 16) -> list[dict[str, Any]]:
        """Return all evidence-backed parent-key ancestor paths.

        A child key may embed an intermediate parent key which itself embeds another
        parent key.  SQL `split(key, '.')[0]` extracts the root component, so value
        normalisation must consider the whole observed storage-parent chain rather
        than assume the immediate parent is the value source.
        """
        first = [x for x in self.parent_links_by_child.get(child_alias, ()) if str(source_column or "").lower() == x.child_key_field.lower()]
        out: list[dict[str, Any]] = []
        queue: list[tuple[str,list[ParentKeyLink],set[str]]] = [(x.parent_alias,[x],{child_alias,x.parent_alias}) for x in first]
        while queue:
            alias,path,seen = queue.pop(0)
            out.append({
                "ancestor_alias": alias,
                "links": path,
                "basis": "+".join(sorted({b for link in path for b in link.basis.split("+") if b})),
                "evidence_ids": tuple(sorted({i for link in path for i in link.evidence_ids})),
            })
            if len(path) >= max_depth:
                continue
            for link in self.parent_links_by_child.get(alias, ()):
                if link.parent_alias in seen:
                    continue
                queue.append((link.parent_alias,path+[link],seen|{link.parent_alias}))
        # Deterministic de-duplication by ancestor + exact link chain.
        unique = {}
        for item in out:
            key=(item["ancestor_alias"],tuple((x.child_alias,x.parent_alias,x.child_key_field) for x in item["links"]))
            unique.setdefault(key,item)
        return [unique[k] for k in sorted(unique)]
