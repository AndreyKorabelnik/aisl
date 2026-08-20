from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterable

from code_analyzer_core import __version__ as CORE_VERSION
from code_analyzer_core.scanners.java_source_observations import _resolve_type_name, _type_tokens
from code_analyzer_core.scanners.java_syntax import (
    JAVA_SYNTAX_EXTRACTOR,
    JavaAnnotation,
    JavaClass,
    JavaField,
    JavaSyntaxFile,
    parse_java_files,
)

CONTRACT_VERSION = "core_evidence_artifact_contract/v1"
ARTIFACT_KIND = "java-type-structure-evidence"
SCHEMA_VERSION = "java-type-structure-evidence/v1"
ANALYZER_ID = "java-type-structure-analyzer"
RELATIVE_PATH = "evidence/java-type-structure-evidence.json"


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _stable_id(prefix: str, *parts: object) -> str:
    payload = "\u001f".join(str(part or "") for part in parts)
    return f"{prefix}_{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:24]}"


def _relative(repository: Path, path: Path) -> str:
    return path.resolve().relative_to(repository.resolve()).as_posix()


def _source_set(relative_path: str) -> str:
    normalized = f"/{relative_path.replace('\\', '/').lower()}/"
    if "/src/test/" in normalized or "/test/" in normalized:
        return "test"
    if "/src/main/" in normalized or "/main/" in normalized:
        return "main"
    return "unknown"


def _source_ref(relative_path: str, line_start: int | None, line_end: int | None) -> dict[str, Any]:
    return {
        "repository_relative_path": relative_path,
        "line_start": int(line_start or 1),
        "line_end": int(line_end or line_start or 1),
        "extractor": JAVA_SYNTAX_EXTRACTOR,
    }


def _documentation(value: dict[str, Any] | None) -> dict[str, Any] | None:
    source = dict(value or {})
    if not source:
        return None
    # Raw comments are source evidence, but the artifact does not need to repeat
    # the entire declaration text. Keep normalized documentation fields only.
    result = {
        key: source.get(key)
        for key in ("summary", "display_name", "description", "tags", "line_start", "line_end")
        if source.get(key) not in (None, "", {}, [])
    }
    return result or None


def _modifier_tokens(field_or_type: JavaClass | JavaField) -> list[str]:
    explicit = list(getattr(field_or_type, "modifier_tokens", ()) or ())
    if explicit:
        return explicit
    return [part for part in str(getattr(field_or_type, "modifiers", "") or "").split() if part]


def _nested_type_parents(classes: list[JavaClass]) -> dict[tuple[str, int], JavaClass | None]:
    parents: dict[tuple[str, int], JavaClass | None] = {}
    for child in classes:
        candidates = [
            parent
            for parent in classes
            if parent is not child
            and parent.line_start <= child.line_start
            and parent.line_end >= child.line_end
            and (parent.line_start, parent.line_end) != (child.line_start, child.line_end)
        ]
        parents[(child.name, child.line_start)] = min(
            candidates,
            key=lambda item: (item.line_end - item.line_start, item.line_start),
            default=None,
        )
    return parents


def _type_identity_maps(parsed_files: list[JavaSyntaxFile], repository: Path) -> tuple[dict[tuple[str, str, int], str], dict[str, list[str]], dict[str, str]]:
    ids: dict[tuple[str, str, int], str] = {}
    fqcn_index: dict[str, list[str]] = {}
    id_to_fqcn: dict[str, str] = {}
    for parsed in parsed_files:
        relative = _relative(repository, parsed.file)
        parents = _nested_type_parents(list(parsed.classes))
        local_fqcn: dict[tuple[str, int], str] = {}
        ordered = sorted(parsed.classes, key=lambda item: (item.line_start, -item.line_end, item.name))
        for cls in ordered:
            parent = parents.get((cls.name, cls.line_start))
            if parent is not None:
                parent_fqcn = local_fqcn.get((parent.name, parent.line_start))
            else:
                parent_fqcn = None
            fqcn = f"{parent_fqcn}.{cls.name}" if parent_fqcn else (f"{parsed.package}.{cls.name}" if parsed.package else cls.name)
            type_id = _stable_id("java_type", relative, cls.line_start, cls.name, cls.kind)
            ids[(relative, cls.name, cls.line_start)] = type_id
            local_fqcn[(cls.name, cls.line_start)] = fqcn
            fqcn_index.setdefault(fqcn, []).append(type_id)
            id_to_fqcn[type_id] = fqcn
    return ids, fqcn_index, id_to_fqcn


def _local_simple_index(id_to_fqcn: dict[str, str]) -> dict[str, list[str]]:
    index: dict[str, list[str]] = {}
    for fqcn in id_to_fqcn.values():
        index.setdefault(fqcn.rsplit(".", 1)[-1], []).append(fqcn)
    return {key: sorted(dict.fromkeys(values)) for key, values in index.items()}


def _annotation_record(
    *,
    parsed: JavaSyntaxFile,
    annotation: JavaAnnotation,
    target_kind: str,
    target_id: str,
    relative_path: str,
    local_type_index: dict[str, list[str]],
) -> dict[str, Any]:
    resolution = _resolve_type_name(parsed, annotation.name, local_type_index)
    return {
        "annotation_id": _stable_id("java_annotation", relative_path, target_kind, target_id, annotation.line_start, annotation.text),
        "target_kind": target_kind,
        "target_id": target_id,
        "annotation_name": annotation.name,
        "arguments_raw": annotation.arguments,
        "structured_arguments": [dict(item) for item in annotation.structured_arguments],
        "resolution_status": resolution.get("resolution"),
        "resolved_annotation_type": resolution.get("resolved_fqcn"),
        "candidate_annotation_types": list(resolution.get("candidate_fqcns") or []),
        "source_ref": _source_ref(relative_path, annotation.line_start, annotation.line_end),
    }


def _resolution_ids(resolution: dict[str, Any], fqcn_index: dict[str, list[str]]) -> tuple[str | None, list[str]]:
    resolved_fqcn = resolution.get("resolved_fqcn")
    resolved_ids = list(fqcn_index.get(str(resolved_fqcn), [])) if resolved_fqcn else []
    candidates: list[str] = []
    for candidate in resolution.get("candidate_fqcns") or []:
        candidates.extend(fqcn_index.get(str(candidate), []))
    candidates = sorted(dict.fromkeys(candidates))
    return (resolved_ids[0] if len(resolved_ids) == 1 else None), candidates


def build_java_type_structure_evidence(
    *,
    repository: Path,
    files: list[Path],
    repo_id: str,
) -> dict[str, Any]:
    repository = repository.expanduser().resolve()
    java_files = sorted(
        [Path(path).resolve() for path in files if Path(path).suffix.lower() == ".java"],
        key=lambda path: _relative(repository, path),
    )
    parsed_files, parse_warnings = parse_java_files(java_files)
    parsed_by_path = {Path(item.file).resolve(): item for item in parsed_files}
    type_ids, fqcn_index, id_to_fqcn = _type_identity_maps(parsed_files, repository)
    local_type_index = _local_simple_index(id_to_fqcn)

    diagnostics: list[dict[str, Any]] = []
    source_units: list[dict[str, Any]] = []
    type_declarations: list[dict[str, Any]] = []
    field_declarations: list[dict[str, Any]] = []
    inheritance_declarations: list[dict[str, Any]] = []
    annotation_declarations: list[dict[str, Any]] = []
    type_reference_observations: list[dict[str, Any]] = []
    enum_constant_declarations: list[dict[str, Any]] = []

    source_entries: list[dict[str, Any]] = []
    unreadable_count = 0
    for path in java_files:
        relative = _relative(repository, path)
        try:
            raw = path.read_bytes()
            file_hash = hashlib.sha256(raw).hexdigest()
            file_bytes = len(raw)
        except OSError as exc:
            unreadable_count += 1
            file_hash = None
            file_bytes = None
            diagnostics.append({
                "code": "source_file_unreadable",
                "severity": "error",
                "message": str(exc),
                "source_refs": [_source_ref(relative, 1, 1)],
            })
        parsed = parsed_by_path.get(path)
        if parsed is None:
            parse_status = "failed"
            parse_error_count = 0
        elif parsed.parse_errors:
            parse_status = "partial"
            parse_error_count = int(parsed.parse_errors)
            diagnostics.append({
                "code": "java_parse_error",
                "severity": "warning",
                "message": f"Tree-sitter reported {parsed.parse_errors} parse error node(s).",
                "source_refs": [_source_ref(relative, 1, max(1, parsed.text.count(chr(10)) + 1))],
            })
        else:
            parse_status = "success"
            parse_error_count = 0
        source_unit_id = _stable_id("java_source_unit", relative)
        source_units.append({
            "source_unit_id": source_unit_id,
            "repository_relative_path": relative,
            "language": "java",
            "package_name": parsed.package if parsed is not None else None,
            "imports": list(parsed.imports) if parsed is not None else [],
            "parse_status": parse_status,
            "parse_error_count": parse_error_count,
            "source_set": _source_set(relative),
            "content_sha256": file_hash,
            "bytes": file_bytes,
        })
        source_entries.append({"path": relative, "sha256": file_hash, "bytes": file_bytes})

    for warning in sorted(parse_warnings):
        match = next((relative for relative in (item["repository_relative_path"] for item in source_units) if relative in warning), None)
        diagnostics.append({
            "code": "java_parse_error",
            "severity": "error",
            "message": warning,
            "source_refs": [_source_ref(match or "unknown", 1, 1)],
        })

    source_unit_ids = {item["repository_relative_path"]: item["source_unit_id"] for item in source_units}
    fqcn_seen: Counter[str] = Counter(id_to_fqcn.values())
    for fqcn, count in sorted(fqcn_seen.items()):
        if count > 1:
            matching = [type_id for type_id, value in id_to_fqcn.items() if value == fqcn]
            refs: list[dict[str, Any]] = []
            for parsed in parsed_files:
                relative = _relative(repository, parsed.file)
                for cls in parsed.classes:
                    type_id = type_ids[(relative, cls.name, cls.line_start)]
                    if type_id in matching:
                        refs.append(_source_ref(relative, cls.line_start, cls.line_end))
            diagnostics.append({
                "code": "duplicate_type_identity",
                "severity": "warning",
                "message": f"Multiple source declarations resolved to {fqcn}.",
                "source_refs": refs,
            })

    unresolved_count = 0
    ambiguous_count = 0
    for parsed in sorted(parsed_files, key=lambda item: _relative(repository, item.file)):
        relative = _relative(repository, parsed.file)
        source_unit_id = source_unit_ids[relative]
        parents = _nested_type_parents(list(parsed.classes))
        for cls in sorted(parsed.classes, key=lambda item: (item.line_start, item.name)):
            type_id = type_ids[(relative, cls.name, cls.line_start)]
            parent = parents.get((cls.name, cls.line_start))
            enclosing_type_id = (
                type_ids.get((relative, parent.name, parent.line_start)) if parent is not None else None
            )
            type_record = {
                "type_id": type_id,
                "source_unit_id": source_unit_id,
                "fully_qualified_name": id_to_fqcn[type_id],
                "simple_name": cls.name,
                "package_name": parsed.package,
                "type_kind": cls.kind,
                "modifier_tokens": _modifier_tokens(cls),
                "type_parameters": list(cls.type_parameters),
                "enclosing_type_id": enclosing_type_id,
                "documentation": _documentation(cls.documentation),
                "source_set": _source_set(relative),
                "source_ref": _source_ref(relative, cls.line_start, cls.line_end),
            }
            type_declarations.append(type_record)

            for annotation in cls.annotations:
                annotation_declarations.append(_annotation_record(
                    parsed=parsed,
                    annotation=annotation,
                    target_kind="type",
                    target_id=type_id,
                    relative_path=relative,
                    local_type_index=local_type_index,
                ))

            for relation_kind, expressions, arguments in (
                ("extends", [cls.extends] if cls.extends else [], [list(cls.extends_type_arguments)] if cls.extends else []),
                ("implements", list(cls.implements), [list(value) for value in cls.implements_type_arguments]),
            ):
                for index, expression in enumerate(expressions):
                    resolution = _resolve_type_name(parsed, str(expression), local_type_index)
                    resolved_type_id, candidate_type_ids = _resolution_ids(resolution, fqcn_index)
                    inheritance_id = _stable_id("java_inheritance", relative, type_id, relation_kind, expression)
                    inheritance_declarations.append({
                        "inheritance_id": inheritance_id,
                        "subtype_id": type_id,
                        "relation_kind": relation_kind,
                        "declared_supertype_expression": expression,
                        "resolution_status": resolution.get("resolution"),
                        "resolved_supertype_id": resolved_type_id,
                        "resolved_fqcn": resolution.get("resolved_fqcn"),
                        "candidate_supertype_ids": candidate_type_ids,
                        "candidate_fqcns": list(resolution.get("candidate_fqcns") or []),
                        "type_arguments": arguments[index] if index < len(arguments) else [],
                        "source_ref": _source_ref(relative, cls.line_start, cls.line_end),
                    })
                    for token in _type_tokens(str(expression)):
                        token_resolution = _resolve_type_name(parsed, token, local_type_index)
                        resolved_id, candidate_ids = _resolution_ids(token_resolution, fqcn_index)
                        type_reference_observations.append({
                            "type_reference_id": _stable_id("java_type_ref", relative, type_id, relation_kind, token, cls.line_start),
                            "owner_kind": "type",
                            "owner_id": type_id,
                            "reference_role": f"{relation_kind}_type",
                            "declared_type_expression": expression,
                            "referenced_type_token": token,
                            "resolution_status": token_resolution.get("resolution"),
                            "resolved_type_id": resolved_id,
                            "resolved_fqcn": token_resolution.get("resolved_fqcn"),
                            "candidate_type_ids": candidate_ids,
                            "candidate_fqcns": list(token_resolution.get("candidate_fqcns") or []),
                            "source_ref": _source_ref(relative, cls.line_start, cls.line_end),
                        })

            for field in sorted(cls.fields, key=lambda item: (item.line_start, item.name)):
                field_id = _stable_id("java_field", relative, type_id, field.name, field.line_start)
                modifiers = _modifier_tokens(field)
                field_declarations.append({
                    "field_id": field_id,
                    "owner_type_id": type_id,
                    "name": field.name,
                    "declared_type_expression": field.type,
                    "normalized_type_expression": re.sub(r"\s+", " ", str(field.type or "").strip()),
                    "modifier_tokens": modifiers,
                    "is_static": "static" in modifiers,
                    "is_final": "final" in modifiers,
                    "initializer_present": field.initializer is not None,
                    "documentation": _documentation(field.documentation),
                    "source_ref": _source_ref(relative, field.line_start, field.line_end),
                })
                for annotation in field.annotations:
                    annotation_declarations.append(_annotation_record(
                        parsed=parsed,
                        annotation=annotation,
                        target_kind="field",
                        target_id=field_id,
                        relative_path=relative,
                        local_type_index=local_type_index,
                    ))
                for token in _type_tokens(field.type):
                    resolution = _resolve_type_name(parsed, token, local_type_index)
                    resolved_id, candidate_ids = _resolution_ids(resolution, fqcn_index)
                    status = str(resolution.get("resolution") or "unresolved")
                    if status == "unresolved":
                        unresolved_count += 1
                        diagnostics.append({
                            "code": "unresolved_type_reference",
                            "severity": "warning",
                            "message": f"Could not resolve field type token {token} for {id_to_fqcn[type_id]}.{field.name}.",
                            "source_refs": [_source_ref(relative, field.line_start, field.line_end)],
                        })
                    elif status.startswith("ambiguous"):
                        ambiguous_count += 1
                        diagnostics.append({
                            "code": "ambiguous_type_reference",
                            "severity": "warning",
                            "message": f"Multiple source candidates for field type token {token} on {id_to_fqcn[type_id]}.{field.name}.",
                            "source_refs": [_source_ref(relative, field.line_start, field.line_end)],
                        })
                    type_reference_observations.append({
                        "type_reference_id": _stable_id("java_type_ref", relative, field_id, token, field.line_start),
                        "owner_kind": "field",
                        "owner_id": field_id,
                        "reference_role": "field_type",
                        "declared_type_expression": field.type,
                        "referenced_type_token": token,
                        "resolution_status": status,
                        "resolved_type_id": resolved_id,
                        "resolved_fqcn": resolution.get("resolved_fqcn"),
                        "candidate_type_ids": candidate_ids,
                        "candidate_fqcns": list(resolution.get("candidate_fqcns") or []),
                        "source_ref": _source_ref(relative, field.line_start, field.line_end),
                    })

            for constant in cls.enum_constants:
                enum_constant_declarations.append({
                    "enum_constant_id": _stable_id("java_enum_constant", relative, type_id, constant.name, constant.line_start),
                    "owner_type_id": type_id,
                    "name": constant.name,
                    "arguments_raw": list(constant.args),
                    "source_ref": _source_ref(relative, constant.line_start, constant.line_end),
                })

        # Tree-sitter currently exposes class/interface/record/enum declarations
        # through JavaSyntaxFile.classes. Annotation type declarations are
        # diagnosed explicitly rather than silently omitted from coverage.
        root = parsed.root_node
        if root is not None:
            stack = [root]
            while stack:
                node = stack.pop()
                if getattr(node, "type", None) == "annotation_type_declaration":
                    diagnostics.append({
                        "code": "unsupported_java_declaration",
                        "severity": "warning",
                        "message": "Java annotation type declaration is not yet materialized as a type record.",
                        "source_refs": [_source_ref(relative, int(node.start_point[0]) + 1, int(node.end_point[0]) + 1)],
                    })
                stack.extend(reversed(list(getattr(node, "named_children", []) or [])))

    sort_specs: list[tuple[list[dict[str, Any]], tuple[str, ...]]] = [
        (source_units, ("repository_relative_path", "source_unit_id")),
        (type_declarations, ("fully_qualified_name", "type_id")),
        (field_declarations, ("owner_type_id", "name", "field_id")),
        (inheritance_declarations, ("subtype_id", "relation_kind", "declared_supertype_expression", "inheritance_id")),
        (annotation_declarations, ("target_id", "annotation_name", "annotation_id")),
        (type_reference_observations, ("owner_id", "reference_role", "referenced_type_token", "type_reference_id")),
        (enum_constant_declarations, ("owner_type_id", "name", "enum_constant_id")),
    ]
    for records, keys in sort_specs:
        records.sort(key=lambda item, keys=keys: tuple(str(item.get(key) or "") for key in keys))
    diagnostics.sort(key=lambda item: (
        str(item.get("code") or ""),
        str(((item.get("source_refs") or [{}])[0]).get("repository_relative_path") or ""),
        int(((item.get("source_refs") or [{}])[0]).get("line_start") or 0),
        str(item.get("message") or ""),
    ))

    java_files_with_parse_errors = sum(1 for item in source_units if item["parse_error_count"] > 0)
    java_files_failed = sum(1 for item in source_units if item["parse_status"] == "failed")
    unsupported_count = sum(1 for item in diagnostics if item["code"] == "unsupported_java_declaration")
    if not java_files:
        coverage_status = "not_applicable"
    elif java_files_failed or java_files_with_parse_errors or unreadable_count or unsupported_count:
        coverage_status = "partial"
    else:
        coverage_status = "complete"

    source_snapshot_material = {
        "source_id": repo_id,
        "scope": "java_source_files",
        "files": source_entries,
    }
    source_snapshot = {
        "source_id": repo_id,
        "revision": None,
        "fingerprint": _fingerprint(source_snapshot_material),
        "scope": "java_source_files",
        "file_count": len(source_entries),
    }
    coverage = {
        "coverage_status": coverage_status,
        "java_files_discovered": len(java_files),
        "java_files_in_scope": len(java_files),
        "java_files_parsed": len(parsed_files),
        "java_files_failed": java_files_failed,
        "java_files_with_parse_errors": java_files_with_parse_errors,
        "type_declaration_count": len(type_declarations),
        "field_declaration_count": len(field_declarations),
        "inheritance_declaration_count": len(inheritance_declarations),
        "annotation_declaration_count": len(annotation_declarations),
        "type_reference_count": len(type_reference_observations),
        "enum_constant_declaration_count": len(enum_constant_declarations),
        "unresolved_type_reference_count": unresolved_count,
        "ambiguous_type_reference_count": ambiguous_count,
        "unsupported_declaration_count": unsupported_count,
    }
    payload = {
        "source_units": source_units,
        "type_declarations": type_declarations,
        "field_declarations": field_declarations,
        "inheritance_declarations": inheritance_declarations,
        "annotation_declarations": annotation_declarations,
        "type_reference_observations": type_reference_observations,
        "enum_constant_declarations": enum_constant_declarations,
    }
    artifact: dict[str, Any] = {
        "contract_version": CONTRACT_VERSION,
        "artifact_kind": ARTIFACT_KIND,
        "schema_version": SCHEMA_VERSION,
        "producer": {
            "component": "code-analyzer-core",
            "analyzer_id": ANALYZER_ID,
            "analyzer_version": CORE_VERSION,
        },
        "source_snapshot": source_snapshot,
        "foundation": {
            "used": False,
            "contract_version": None,
            "fingerprint": None,
            "sections": [],
        },
        "parameters": {
            "language": "java",
            "include_test_sources": True,
            "record_limit": None,
        },
        "coverage": coverage,
        "diagnostics": diagnostics,
        "provenance": {
            "parser_provider": "tree_sitter",
            "execution_runtime": "core_evidence_runtime/v1",
            "semantic_routing": "artifact_kind_plus_schema_version",
        },
        "payload": payload,
    }
    artifact["content_fingerprint"] = _fingerprint(artifact)
    artifact["artifact_id"] = f"java_type_structure_{artifact['content_fingerprint'][:24]}"
    return artifact
