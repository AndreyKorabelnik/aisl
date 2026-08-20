from __future__ import annotations

from pathlib import Path
from typing import Any
import hashlib
import json
import re
import xml.etree.ElementTree as ET

import yaml
from yaml.nodes import MappingNode, Node, ScalarNode, SequenceNode

from code_analyzer_core.models import Fact, EvidenceRef
from code_analyzer_core.utils import read_text
from code_analyzer_core.scanners.java_syntax import parse_java_files

_CONFIG_SUFFIXES = {".yml", ".yaml", ".properties", ".json", ".xml"}
_INTERACTION_TOKENS = {
    "kafka", "topic", "url", "datasource", "jdbc", "schema", "consumer",
    "producer", "group", "endpoint", "path",
}
_JAVA_TYPE_RE = re.compile(r"^(?:[A-Za-z_$][\w$]*\.){2,}[A-Z_$][\w$]*(?:\[\])?$")
_JAVA_MEMBER_RE = re.compile(
    r"^(?P<owner>(?:[A-Za-z_$][\w$]*\.){2,}[A-Z_$][\w$]*):(?P<member>[A-Za-z_$][\w$]*)$"
)
_QUALIFIED_NAME_RE = re.compile(r"^(?:[A-Za-z_$][\w$]*\.){2,}[A-Za-z_$][\w$]*$")
_TEMPLATE_REF_RE = re.compile(r"\$\{(?P<name>[^{}]+)\}")


def _node_kind(value: Any) -> str:
    if isinstance(value, dict):
        return "mapping"
    if isinstance(value, list):
        return "list"
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    return "string"


def _path_key(path: str) -> str | None:
    if path == "$":
        return None
    leaf = re.sub(r"\[\d+\]$", "", path.split(".")[-1])
    return leaf or None


def _path_segments(path: str) -> list[str | int]:
    if path == "$":
        return []
    segments: list[str | int] = []
    for part in path.split("."):
        cursor = 0
        for match in re.finditer(r"([^\[]+)|\[(\d+)\]", part):
            if match.group(1) is not None:
                segments.append(match.group(1))
            elif match.group(2) is not None:
                segments.append(int(match.group(2)))
            cursor = match.end()
        if cursor < len(part):
            segments.append(part[cursor:])
    return segments


def _stable_id(prefix: str, *parts: Any) -> str:
    payload = "\u001f".join(str(part) for part in parts)
    return f"{prefix}_{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:24]}"


def _flatten_nodes(
    prefix: str,
    obj: Any,
    out: list[dict[str, Any]],
    *,
    parent_path: str | None = None,
    list_index: int | None = None,
    line_start: int | None = None,
    line_end: int | None = None,
    raw_snippet: str | None = None,
) -> None:
    current_path = prefix or "$"
    out.append({
        "path": current_path,
        "parent_path": parent_path,
        "node_kind": _node_kind(obj),
        "value": obj if not isinstance(obj, (dict, list)) else None,
        "list_index": list_index,
        "child_count": len(obj) if isinstance(obj, (dict, list)) else 0,
        "line_start": line_start,
        "line_end": line_end,
        "raw_snippet": raw_snippet,
    })
    if isinstance(obj, dict):
        for key, value in obj.items():
            child = f"{prefix}.{key}" if prefix else str(key)
            _flatten_nodes(child, value, out, parent_path=current_path)
    elif isinstance(obj, list):
        for index, value in enumerate(obj):
            child = f"{prefix}[{index}]" if prefix else f"[{index}]"
            _flatten_nodes(child, value, out, parent_path=current_path, list_index=index)


def _yaml_key_value(key_node: Node) -> Any:
    if not isinstance(key_node, ScalarNode):
        return str(getattr(key_node, "value", ""))
    try:
        return yaml.safe_load(key_node.value)
    except Exception:
        return key_node.value


def _yaml_snippet(lines: list[str], node: Node) -> str | None:
    start = int(node.start_mark.line)
    end = max(start + 1, int(node.end_mark.line) + 1)
    snippet = "\n".join(lines[start:end]).strip()
    return snippet[:500] if snippet else None


def _flatten_yaml_node(
    node: Node,
    obj: Any,
    out: list[dict[str, Any]],
    lines: list[str],
    *,
    prefix: str = "",
    parent_path: str | None = None,
    list_index: int | None = None,
) -> None:
    current_path = prefix or "$"
    out.append({
        "path": current_path,
        "parent_path": parent_path,
        "node_kind": _node_kind(obj),
        "value": obj if not isinstance(obj, (dict, list)) else None,
        "list_index": list_index,
        "child_count": len(obj) if isinstance(obj, (dict, list)) else 0,
        "line_start": int(node.start_mark.line) + 1,
        "line_end": max(int(node.start_mark.line) + 1, int(node.end_mark.line) + 1),
        "raw_snippet": _yaml_snippet(lines, node),
    })
    if isinstance(node, MappingNode) and isinstance(obj, dict):
        for key_node, value_node in node.value:
            key_obj = _yaml_key_value(key_node)
            child_obj = obj.get(key_obj)
            key = str(key_obj)
            child = f"{prefix}.{key}" if prefix else key
            _flatten_yaml_node(
                value_node,
                child_obj,
                out,
                lines,
                prefix=child,
                parent_path=current_path,
            )
    elif isinstance(node, SequenceNode) and isinstance(obj, list):
        for index, value_node in enumerate(node.value):
            child_obj = obj[index] if index < len(obj) else None
            child = f"{prefix}[{index}]" if prefix else f"[{index}]"
            _flatten_yaml_node(
                value_node,
                child_obj,
                out,
                lines,
                prefix=child,
                parent_path=current_path,
                list_index=index,
            )


def _yaml_nodes(text: str) -> tuple[Any, list[dict[str, Any]]]:
    loaded = yaml.safe_load(text) if text.strip() else {}
    root = yaml.compose(text, Loader=yaml.SafeLoader) if text.strip() else None
    nodes: list[dict[str, Any]] = []
    if root is None:
        _flatten_nodes("", loaded if loaded is not None else {}, nodes)
    else:
        _flatten_yaml_node(root, loaded, nodes, text.splitlines())
    return loaded, nodes


def _xml_to_object(node: ET.Element) -> Any:
    children = list(node)
    attributes = {f"@{key}": value for key, value in node.attrib.items()}
    text = (node.text or "").strip()
    if not children:
        if attributes:
            if text:
                attributes["#text"] = text
            return attributes
        return text
    grouped: dict[str, list[Any]] = {}
    for child in children:
        tag = child.tag.split("}")[-1]
        grouped.setdefault(tag, []).append(_xml_to_object(child))
    result: dict[str, Any] = dict(attributes)
    for tag, values in grouped.items():
        result[tag] = values[0] if len(values) == 1 else values
    if text:
        result["#text"] = text
    return result


def _properties_object(text: str) -> dict[str, Any]:
    loaded: dict[str, Any] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", "!")):
            continue
        if "=" in stripped:
            key, value = stripped.split("=", 1)
        elif ":" in stripped:
            key, value = stripped.split(":", 1)
        else:
            continue
        loaded[key.strip()] = value.strip()
    return loaded


def _parameter_catalog_defaults(loaded: Any) -> list[tuple[str, Any]]:
    if not isinstance(loaded, dict) or not isinstance(loaded.get("parameters"), list):
        return []
    out: list[tuple[str, Any]] = []
    for entry in loaded.get("parameters") or []:
        if not isinstance(entry, dict):
            continue
        for key, spec in entry.items():
            if not isinstance(spec, dict):
                continue
            for type_key, value_spec in spec.items():
                if str(type_key).endswith("Value") and isinstance(value_spec, dict) and "default" in value_spec:
                    out.append((str(key), value_spec.get("default")))
    return out


def _line_for_path(text: str, path: str, value: Any) -> int | None:
    leaf = re.sub(r"\[\d+\]$", "", str(path).split(".")[-1])
    candidates = [leaf]
    if value is not None and str(value):
        candidates.insert(0, str(value))
    for candidate in candidates:
        match = re.search(re.escape(candidate), text)
        if match:
            return text.count("\n", 0, match.start()) + 1
    return None


def _interaction_relevant(path: str, value: Any) -> bool:
    probe = f"{path} {value}".lower()
    return any(token in probe for token in _INTERACTION_TOKENS)


def _scalar_shape(value: Any) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    if _JAVA_MEMBER_RE.fullmatch(value):
        return "qualified_member_reference"
    if _JAVA_TYPE_RE.fullmatch(value):
        return "java_type_reference"
    if _TEMPLATE_REF_RE.search(value):
        return "templated_string"
    if _QUALIFIED_NAME_RE.fullmatch(value):
        return "qualified_name"
    return None


def _reference_observations(path: Path, node: dict[str, Any]) -> list[Fact]:
    value = node.get("value")
    if not isinstance(value, str) or not value:
        return []
    config_path = str(node["path"])
    line_start = node.get("line_start")
    line_end = node.get("line_end")
    snippet = node.get("raw_snippet") or value[:300]
    refs: list[dict[str, Any]] = []
    member_match = _JAVA_MEMBER_RE.fullmatch(value)
    if member_match:
        refs.append({
            "reference_kind": "qualified_member_reference",
            "reference_value": value,
            "owner_qualified_name": member_match.group("owner"),
            "member_name": member_match.group("member"),
        })
    elif _JAVA_TYPE_RE.fullmatch(value):
        refs.append({"reference_kind": "java_type_reference", "reference_value": value})
    elif _QUALIFIED_NAME_RE.fullmatch(value):
        refs.append({"reference_kind": "qualified_name", "reference_value": value})
    for match in _TEMPLATE_REF_RE.finditer(value):
        refs.append({
            "reference_kind": "template_variable_reference",
            "reference_value": match.group(0),
            "template_variable": match.group("name"),
        })
    facts: list[Fact] = []
    for index, ref in enumerate(refs):
        observation_id = _stable_id(
            "config_ref",
            path,
            config_path,
            ref["reference_kind"],
            ref["reference_value"],
            index,
        )
        properties = {
            "observation_id": observation_id,
            "configuration_path": config_path,
            "container_path": node.get("parent_path"),
            "source_path": str(path),
            "path_segments": _path_segments(config_path),
            "key": _path_key(config_path),
            "observation_policy": "lexical reference shape only; no target resolution or domain semantics",
            **ref,
        }
        facts.append(Fact(
            fact_type="configuration_reference_observation",
            name=f"{path.name}:{config_path}:{ref['reference_kind']}",
            properties={key: item for key, item in properties.items() if item is not None},
            evidence=[EvidenceRef(
                file_path=str(path),
                line_start=line_start,
                line_end=line_end,
                snippet=str(snippet)[:500],
                extractor="structured_config_reference",
            )],
        ))
    return facts


def _object_observations(path: Path, nodes: list[dict[str, Any]]) -> list[Fact]:
    children_by_parent: dict[str, list[dict[str, Any]]] = {}
    for node in nodes:
        parent = node.get("parent_path")
        if parent:
            children_by_parent.setdefault(str(parent), []).append(node)
    facts: list[Fact] = []
    for node in nodes:
        if node.get("node_kind") != "mapping":
            continue
        config_path = str(node["path"])
        children = children_by_parent.get(config_path, [])
        scalar_children = [
            child for child in children
            if child.get("node_kind") not in {"mapping", "list"}
        ]
        if not scalar_children:
            continue
        scalar_fields = {
            str(_path_key(str(child["path"]))): child.get("value")
            for child in scalar_children
            if _path_key(str(child["path"])) is not None
        }
        referenced_values = [
            {
                "field": _path_key(str(child["path"])),
                "value": child.get("value"),
                "scalar_shape": _scalar_shape(child.get("value")),
            }
            for child in scalar_children
            if _scalar_shape(child.get("value")) is not None
        ]
        object_id = _stable_id("config_object", path, config_path, json.dumps(scalar_fields, sort_keys=True, default=str))
        properties = {
            "observation_id": object_id,
            "configuration_path": config_path,
            "parent_path": node.get("parent_path"),
            "list_index": node.get("list_index"),
            "source_path": str(path),
            "path_segments": _path_segments(config_path),
            "scalar_fields": scalar_fields,
            "referenced_values": referenced_values,
            "child_paths": sorted(str(child["path"]) for child in children),
            "observation_policy": "immediate mapping structure only; no registration, publication, key, or relationship verdict",
        }
        facts.append(Fact(
            fact_type="configuration_object_observation",
            name=f"{path.name}:{config_path}",
            properties={key: value for key, value in properties.items() if value is not None},
            evidence=[EvidenceRef(
                file_path=str(path),
                line_start=node.get("line_start"),
                line_end=node.get("line_end"),
                snippet=str(node.get("raw_snippet") or "")[:500] or None,
                extractor="structured_config_object",
            )],
        ))
    return facts


def _split_yaml_comment(line: str) -> tuple[str, str] | None:
    single = False
    double = False
    escaped = False
    for index, char in enumerate(line):
        if escaped:
            escaped = False
            continue
        if char == "\\" and double:
            escaped = True
            continue
        if char == "'" and not double:
            single = not single
            continue
        if char == '"' and not single:
            double = not double
            continue
        if char == "#" and not single and not double:
            return line[:index], line[index + 1 :]
    return None


def _yaml_comment_observations(path: Path, text: str, nodes: list[dict[str, Any]]) -> list[Fact]:
    positioned = [node for node in nodes if node.get("line_start")]
    facts: list[Fact] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        split = _split_yaml_comment(line)
        if split is None:
            continue
        before, comment = split
        comment = comment.strip()
        if not comment:
            continue
        indent = len(line) - len(line.lstrip(" "))
        association_kind = "inline" if before.strip() else "preceding_comment"
        associated: dict[str, Any] | None = None
        if association_kind == "inline":
            same_line = [node for node in positioned if node.get("line_start") == line_no]
            if same_line:
                associated = max(same_line, key=lambda item: len(str(item.get("path") or "")))
        else:
            following = [node for node in positioned if int(node.get("line_start") or 0) > line_no]
            if following:
                associated = min(following, key=lambda item: int(item.get("line_start") or 0))
        associated_path = str(associated.get("path")) if associated else None
        observation_id = _stable_id("config_comment", path, line_no, comment)
        properties = {
            "observation_id": observation_id,
            "comment_text": comment,
            "comment_kind": association_kind,
            "indentation": indent,
            "associated_configuration_path": associated_path,
            "association_policy": "same-line deepest node or nearest following structured node",
            "source_path": str(path),
            "observation_policy": "source comment only; no semantic classification",
        }
        facts.append(Fact(
            fact_type="configuration_comment_observation",
            name=f"{path.name}:comment:{line_no}",
            properties={key: value for key, value in properties.items() if value is not None},
            evidence=[EvidenceRef(
                file_path=str(path),
                line_start=line_no,
                line_end=line_no,
                snippet=line.strip()[:500],
                extractor="structured_config_comment",
            )],
        ))
    return facts



def _resolve_configuration_references(files: list[Path], facts: list[Fact]) -> list[Fact]:
    references = [fact for fact in facts if fact.fact_type == "configuration_reference_observation"]
    if not references:
        return []
    java_files = [path for path in files if path.suffix.lower() == ".java"]
    if not java_files:
        return []
    parsed_files, warnings = parse_java_files(java_files)
    classes_by_fqcn: dict[str, list[Any]] = {}
    fields_by_owner: dict[str, dict[str, list[Any]]] = {}
    for parsed in parsed_files:
        for cls in parsed.classes:
            fqcn = f"{cls.package}.{cls.name}" if cls.package else cls.name
            classes_by_fqcn.setdefault(fqcn, []).append(cls)
            owner_fields = fields_by_owner.setdefault(fqcn, {})
            for field in cls.fields:
                owner_fields.setdefault(field.name, []).append((field, parsed.file))

    resolved: list[Fact] = []
    for ref in references:
        props = ref.properties
        kind = props.get("reference_kind")
        if kind not in {"java_type_reference", "qualified_member_reference"}:
            continue
        owner = props.get("owner_qualified_name") or props.get("reference_value")
        owner = str(owner or "").removesuffix("[]")
        class_matches = classes_by_fqcn.get(owner, [])
        member = props.get("member_name")
        member_matches = fields_by_owner.get(owner, {}).get(str(member), []) if member else []
        if member:
            matches = member_matches
            target_kind = "java_field"
        else:
            matches = class_matches
            target_kind = "java_type"
        if len(matches) == 1:
            status = "resolved_unique"
        elif len(matches) > 1:
            status = "ambiguous_multiple"
        else:
            status = "unresolved"
        candidates=[]
        for item in matches:
            if target_kind == "java_field":
                target, target_file = item
            else:
                target, target_file = item, item.file
            candidates.append({
                "target_kind": target_kind,
                "qualified_name": owner,
                "member_name": member,
                "source_path": str(target_file),
                "line_start": target.line_start,
                "line_end": target.line_end,
            })
        observation_id = _stable_id("config_resolution", props.get("observation_id"), status, target_kind)
        resolution_props = {
            "observation_id": observation_id,
            "source_reference_observation_id": props.get("observation_id"),
            "configuration_path": props.get("configuration_path"),
            "reference_kind": kind,
            "reference_value": props.get("reference_value"),
            "target_kind": target_kind,
            "resolution_status": status,
            "candidate_count": len(candidates),
            "candidates": candidates,
            "java_parse_warning_count": len(warnings),
            "resolution_policy": "exact fully-qualified type name and exact declared field name only; no domain semantics",
        }
        resolved.append(Fact(
            fact_type="configuration_reference_resolution_observation",
            name=f"{ref.name}:{status}",
            properties={k:v for k,v in resolution_props.items() if v is not None},
            evidence=list(ref.evidence),
        ))
    return resolved

def scan_config_files(files: list[Path]) -> list[Fact]:
    facts: list[Fact] = []
    for path in files:
        suffix = path.suffix.lower()
        if suffix not in _CONFIG_SUFFIXES or path.name == "pom.xml":
            # Maven coordinates have a dedicated source-only scanner. Keeping POM
            # XML out of generic config facts prevents duplicate, very large trees.
            continue
        text = read_text(path)
        canonical_entries: list[tuple[str, Any]] = []
        nodes: list[dict[str, Any]] = []
        try:
            if suffix in {".yml", ".yaml"}:
                loaded, nodes = _yaml_nodes(text)
            elif suffix == ".json":
                loaded = json.loads(text) if text.strip() else {}
                canonical_entries = _parameter_catalog_defaults(loaded)
                _flatten_nodes("", loaded if loaded is not None else {}, nodes)
            elif suffix == ".xml":
                root = ET.fromstring(text)
                loaded = {root.tag.split("}")[-1]: _xml_to_object(root)}
                _flatten_nodes("", loaded if loaded is not None else {}, nodes)
            else:
                loaded = _properties_object(text)
                _flatten_nodes("", loaded if loaded is not None else {}, nodes)
        except Exception as exc:
            facts.append(Fact(
                fact_type="config_parse_warning",
                name=str(path),
                properties={"error": str(exc), "configuration_format": suffix.lstrip(".")},
                evidence=[EvidenceRef(file_path=str(path), extractor="structured_config")],
            ))
            continue

        for node in nodes:
            config_path = str(node["path"])
            line = node.get("line_start") or _line_for_path(text, config_path, node.get("value"))
            line_end = node.get("line_end") or line
            scalar_shape = _scalar_shape(node.get("value"))
            props = {
                "configuration_format": suffix.lstrip("."),
                "configuration_path": config_path,
                "parent_path": node.get("parent_path"),
                "node_kind": node.get("node_kind"),
                "value": node.get("value"),
                "list_index": node.get("list_index"),
                "child_count": node.get("child_count"),
                "source_path": str(path),
                "path_segments": _path_segments(config_path),
                "key": _path_key(config_path),
                "scalar_shape": scalar_shape,
                "observation_policy": "structured syntax only; no project-specific interpretation",
            }
            facts.append(Fact(
                fact_type="configuration_entry",
                name=f"{path.name}:{config_path}",
                properties={key: value for key, value in props.items() if value is not None},
                evidence=[EvidenceRef(
                    file_path=str(path),
                    line_start=line,
                    line_end=line_end,
                    snippet=(str(node.get("raw_snippet") or node.get("value"))[:500] if node.get("value") is not None or node.get("raw_snippet") else None),
                    extractor="structured_config",
                )],
            ))
            facts.extend(_reference_observations(path, node))
            # Retain the historical config_property contract for interaction-oriented
            # consumers, while the complete tree is available as configuration_entry.
            if node.get("node_kind") not in {"mapping", "list"} and _interaction_relevant(config_path, node.get("value")):
                facts.append(Fact(
                    fact_type="config_property",
                    name=config_path,
                    properties={"value": node.get("value"), "configuration_structure": "structured_entry"},
                    evidence=[EvidenceRef(
                        file_path=str(path),
                        line_start=line,
                        line_end=line_end,
                        snippet=str(node.get("value"))[:300],
                        extractor="config",
                    )],
                ))

        facts.extend(_object_observations(path, nodes))
        if suffix in {".yml", ".yaml"}:
            facts.extend(_yaml_comment_observations(path, text, nodes))

        for key, value in canonical_entries:
            if not _interaction_relevant(key, value):
                continue
            line = _line_for_path(text, key, value)
            facts.append(Fact(
                fact_type="config_property",
                name=key,
                properties={"value": value, "configuration_structure": "parameter_catalog_default"},
                evidence=[EvidenceRef(
                    file_path=str(path),
                    line_start=line,
                    line_end=line,
                    snippet=str(value)[:300],
                    extractor="config_parameter_catalog",
                )],
            ))
    facts.extend(_resolve_configuration_references(files, facts))
    return facts
