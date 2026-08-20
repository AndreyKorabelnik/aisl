from __future__ import annotations

import hashlib
import re
from typing import Any, Iterable, Mapping

from .er_correction import merge_er_section

_SAFE_ID = re.compile(r"[^A-Za-z0-9_]+")
_SAFE_WORD = re.compile(r"[^A-Za-z0-9_\-]+")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _safe_identifier(value: Any, *, prefix: str) -> str:
    source = _text(value) or prefix
    candidate = _SAFE_ID.sub("_", source).strip("_")
    if not candidate or not candidate[0].isalpha():
        candidate = f"{prefix}_{candidate}" if candidate else prefix
    digest = hashlib.sha1(source.encode("utf-8")).hexdigest()[:8]
    return f"{candidate}_{digest}"


def _safe_attribute_word(value: Any, *, fallback: str) -> str:
    source = _text(value)
    candidate = _SAFE_WORD.sub("_", source).strip("_")
    if not candidate:
        candidate = fallback
    if not candidate[0].isalpha():
        candidate = f"{fallback}_{candidate}"
    return candidate


def _safe_label(value: Any, *, fallback: str, limit: int = 180) -> str:
    source = re.sub(r"\s+", " ", _text(value)).strip() or fallback
    # Mermaid labels are data, not syntax. Replace the delimiters that may close
    # quoted node/edge labels or flowchart edge-label pipes.
    source = source.replace("\\", "/").replace('"', "'").replace("|", "/")
    return source[:limit].rstrip() or fallback


def _relationship_label(relation: Mapping[str, Any]) -> str:
    pairs = [
        f"{_text(item.get('from_column'))} = {_text(item.get('to_column'))}"
        for item in relation.get("column_pairs") or ()
        if isinstance(item, Mapping)
        and _text(item.get("from_column"))
        and _text(item.get("to_column"))
    ]
    if not pairs:
        left = [str(value) for value in relation.get("from_columns") or () if _text(value)]
        right = [str(value) for value in relation.get("to_columns") or () if _text(value)]
        pairs = [f"{a} = {b}" for a, b in zip(left, right)]
    label = ", ".join(pairs) or _text(relation.get("constraint_name")) or "declared FK"
    return _safe_label(label, fallback="declared FK")


def _logical_label(relation: Mapping[str, Any]) -> str:
    label = _text(relation.get("field")) or _text(relation.get("relation_kind")) or "relationship"
    return _safe_label(label, fallback="relationship")


def _entity_index(items: Iterable[Mapping[str, Any]], *, logical: bool) -> tuple[dict[str, str], list[tuple[str, Mapping[str, Any]]]]:
    index: dict[str, str] = {}
    ordered: list[tuple[str, Mapping[str, Any]]] = []
    for item in items:
        if not isinstance(item, Mapping):
            continue
        exact = _text(item.get("qualified_name" if logical else "qualified_name"))
        if not exact:
            exact = _text(item.get("name"))
        if not exact:
            continue
        identifier = _safe_identifier(exact, prefix="entity" if logical else "table")
        index[exact] = identifier
        # Some relationships use a short name while the node carries a qualified name.
        short = _text(item.get("name"))
        if short and short not in index:
            index[short] = identifier
        ordered.append((identifier, item))
    return index, ordered


def _physical_fk_columns(relationships: Iterable[Mapping[str, Any]]) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    for relation in relationships:
        if not isinstance(relation, Mapping):
            continue
        table = _text(relation.get("from_table"))
        if not table:
            continue
        result.setdefault(table, set()).update(_text(value) for value in relation.get("from_columns") or () if _text(value))
    return result


def _render_attributes(
    item: Mapping[str, Any],
    *,
    primary_key_field: str,
    key_flag_field: str | None = None,
    foreign_keys: set[str] | None = None,
) -> list[str]:
    foreign_keys = foreign_keys or set()
    primary_keys = {_text(value) for value in item.get(primary_key_field) or () if _text(value)}
    lines: list[str] = []
    used_names: set[str] = set()
    for position, attribute in enumerate(item.get("attributes") or (), start=1):
        if not isinstance(attribute, Mapping):
            continue
        raw_name = _text(attribute.get("name")) or f"attribute_{position}"
        name = _safe_attribute_word(raw_name, fallback=f"attribute_{position}")
        if name in used_names:
            name = f"{name}_{position}"
        used_names.add(name)
        type_word = _safe_attribute_word(attribute.get("type"), fallback="text")
        flags: list[str] = []
        is_pk = bool(attribute.get("primary_key")) or raw_name in primary_keys
        if key_flag_field and bool(attribute.get(key_flag_field)):
            is_pk = True
        if is_pk:
            flags.append("PK")
        if raw_name in foreign_keys:
            flags.append("FK")
        suffix = f" {', '.join(flags)}" if flags else ""
        lines.append(f"        {type_word} {name}{suffix}")
    return lines


def _render_physical(layer: Mapping[str, Any]) -> tuple[str, list[str]]:
    tables = [item for item in layer.get("tables") or () if isinstance(item, Mapping)]
    relationships = [item for item in layer.get("relationships") or () if isinstance(item, Mapping)]
    index, ordered = _entity_index(tables, logical=False)
    fk_columns = _physical_fk_columns(relationships)
    lines = ["erDiagram"]
    for relation in relationships:
        left_name = _text(relation.get("from_table"))
        right_name = _text(relation.get("to_table"))
        left = index.get(left_name)
        right = index.get(right_name)
        if left and right:
            # Conservative cardinality: a referenced row may have zero or many children;
            # an FK value may be absent unless nullability/uniqueness proves otherwise.
            lines.append(f'    {left} }}o--o| {right} : "{_relationship_label(relation)}"')
    mappings: list[str] = []
    for identifier, table in ordered:
        exact = _text(table.get("qualified_name")) or _text(table.get("name"))
        lines.append(f"    {identifier} {{")
        attributes = _render_attributes(
            table,
            primary_key_field="primary_key_columns",
            foreign_keys=fk_columns.get(exact, set()) | fk_columns.get(_text(table.get("name")), set()),
        )
        lines.extend(attributes or ["        text attributes_not_observed"])
        lines.append("    }")
        mappings.append(f"- `{identifier}` — `{exact}`")
    return "\n".join(lines), mappings


def _logical_relation_token(cardinality: Any) -> str:
    value = _text(cardinality).casefold().replace("-", "_").replace(" ", "_")
    if value in {"many", "collection", "list", "set", "one_to_many", "zero_or_more"}:
        return "||--o{"
    if value in {"optional", "zero_or_one", "nullable"}:
        return "||--o|"
    return "||--||"


def _render_logical(layer: Mapping[str, Any]) -> tuple[str, list[str]]:
    entities = [item for item in layer.get("entities") or () if isinstance(item, Mapping)]
    relationships = [item for item in layer.get("relationships") or () if isinstance(item, Mapping)]
    index, ordered = _entity_index(entities, logical=True)
    lines = ["erDiagram"]
    for relation in relationships:
        left = index.get(_text(relation.get("from")))
        right = index.get(_text(relation.get("to")))
        if left and right:
            lines.append(
                f'    {left} {_logical_relation_token(relation.get("cardinality"))} '
                f'{right} : "{_logical_label(relation)}"'
            )
    mappings: list[str] = []
    for identifier, entity in ordered:
        exact = _text(entity.get("qualified_name")) or _text(entity.get("name"))
        lines.append(f"    {identifier} {{")
        attributes = _render_attributes(
            entity,
            primary_key_field="primary_key_columns",
            key_flag_field="key",
        )
        lines.extend(attributes or ["        text attributes_not_observed"])
        lines.append("    }")
        mappings.append(f"- `{identifier}` — `{exact}`")
    return "\n".join(lines), mappings


def _observed_pair_label(relation: Mapping[str, Any]) -> str:
    pairs = relation.get("column_pairs") or ()
    rendered = []
    for pair in pairs:
        if not isinstance(pair, Mapping):
            continue
        left = _text(pair.get("left_column") or pair.get("from_column"))
        right = _text(pair.get("right_column") or pair.get("to_column"))
        if left and right:
            rendered.append(f"{left} = {right}")
    return _safe_label(", ".join(rendered) or relation.get("relation_kind"), fallback="observed join")


def _render_observed_usage(layer: Mapping[str, Any], *, limit: int = 30) -> str:
    relationships = [item for item in layer.get("relationships") or () if isinstance(item, Mapping)][:limit]
    if not relationships:
        return ""
    names: list[str] = []
    for relation in relationships:
        for key in ("left_table", "right_table"):
            value = _text(relation.get(key))
            if value and value not in names:
                names.append(value)
    index = {name: _safe_identifier(name, prefix="usage") for name in names}
    lines = ["flowchart LR"]
    for name in names:
        label = _safe_label(name, fallback="table")
        lines.append(f'    {index[name]}["{label}"]')
    for relation in relationships:
        left_name = _text(relation.get("left_table"))
        right_name = _text(relation.get("right_table"))
        if left_name in index and right_name in index:
            lines.append(
                f'    {index[left_name]} -->|"{_observed_pair_label(relation)}"| {index[right_name]}'
            )
    return "\n".join(lines)


def build_deterministic_er_section(dataset: Mapping[str, Any]) -> str:
    if _text(dataset.get("profile_id")) != "data-model-report/v1":
        return ""
    sections = dataset.get("sections") if isinstance(dataset.get("sections"), Mapping) else {}
    diagrams = sections.get("diagrams") if isinstance(sections, Mapping) else {}
    if not isinstance(diagrams, Mapping):
        return ""

    fragments = ["## ER-диаграммы"]
    mappings: list[str] = []
    logical = diagrams.get("logical_er") if isinstance(diagrams.get("logical_er"), Mapping) else {}
    physical = diagrams.get("physical_er") if isinstance(diagrams.get("physical_er"), Mapping) else {}
    observed = diagrams.get("observed_usage") if isinstance(diagrams.get("observed_usage"), Mapping) else {}

    if logical.get("status") == "observed" and logical.get("entities"):
        source, layer_mappings = _render_logical(logical)
        fragments.extend(["", "### Логическая ER-диаграмма", "", "```mermaid", source, "```"])
        mappings.extend(layer_mappings)

    if physical.get("status") == "observed" and physical.get("tables"):
        source, layer_mappings = _render_physical(physical)
        fragments.extend([
            "",
            "### Физическая ER-диаграмма (объявленные связи схемы)",
            "",
            "```mermaid",
            source,
            "```",
            "",
            "Кардинальности показаны консервативно: диаграмма не повышает статус сведений о nullable/unique, если они не доказаны dataset.",
        ])
        mappings.extend(layer_mappings)

    observed_source = _render_observed_usage(observed)
    if observed_source:
        fragments.extend([
            "",
            "### Наблюдаемые связи использования (SQL/JOOQ)",
            "",
            "Эти рёбра показывают наблюдаемые JOIN и не являются объявленными внешними ключами без отдельного доказательства.",
            "",
            "```mermaid",
            observed_source,
            "```",
        ])

    if mappings:
        fragments.extend(["", "### Идентификаторы на диаграммах", "", *dict.fromkeys(mappings)])

    if len(fragments) == 1:
        return ""
    return "\n".join(fragments).rstrip() + "\n"


def apply_deterministic_er_section(report: str, dataset: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
    fragment = build_deterministic_er_section(dataset)
    if not fragment:
        return report, {"applicable": False, "applied": False, "reason": "no_observed_er_layers"}
    merged = merge_er_section(report, fragment)
    return merged, {
        "applicable": True,
        "applied": merged != report,
        "generator": "deterministic-data-model-mermaid/v1",
        "fragment_chars": len(fragment),
    }
