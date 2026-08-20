from __future__ import annotations

import re
from pathlib import Path
from typing import Any

try:
    import yaml
except Exception:  # pragma: no cover
    yaml = None  # type: ignore[assignment]

from code_analyzer_core.utils import normalize_name, read_text, line_number_for_offset


def _hash(value: str, n: int = 12) -> str:
    import hashlib
    return hashlib.sha256(value.encode("utf-8", errors="ignore")).hexdigest()[:n]


def _rel(repo: Path, path: Path) -> str:
    try:
        return str(path.relative_to(repo)).replace("\\", "/")
    except Exception:
        return str(path).replace("\\", "/")


def _source_set_for_path(path: Path) -> str:
    normalized = "/" + str(path).replace("\\", "/").strip("/").lower() + "/"
    if any(token in normalized for token in ("/src/test/", "/tests/", "/test/")):
        return "test"
    path_segments = [segment for segment in normalized.strip("/").split("/") if segment]
    if any(token in normalized for token in ("/db/migration/", "/migrations/", "/migration/", "/liquibase/", "/flyway/")) \
            or any(segment.startswith(("migration", "liquibase", "flyway")) for segment in path_segments):
        return "migration"
    if any(token in normalized for token in ("/fixture/", "/fixtures/")):
        return "fixture"
    if any(token in normalized for token in ("/example/", "/examples/", "/sample/", "/samples/")):
        return "example_sample"
    if any(token in normalized for token in ("/generated/", "/target/generated/", "/build/generated/")):
        return "generated"
    if any(token in normalized for token in ("/docs/", "/documentation/")):
        return "documentation"
    if "/src/main/" in normalized:
        return "production"
    return "unknown"


def _is_test_source_path(path: Path) -> bool:
    return _source_set_for_path(path) == 'test'


_SQL_EFFECTIVE_SOURCE_SCOPES = {"forward_migration", "production", "unknown"}


def _sql_source_scope_for_path(repo: Path, path: Path) -> tuple[str, str]:
    """Return a mechanical SQL source role and the observed path rule.

    The role is not a semantic verdict. It records how the file is placed in the
    repository and controls whether its DDL mutates the effective physical model.
    Facts from non-effective scopes are still published separately.
    """
    rel = _rel(repo, path).lower()
    segments = [segment for segment in rel.replace("\\", "/").split("/") if segment]
    segment_set = set(segments)

    if "src" in segment_set and "test" in segment_set:
        return "test", "path_contains_src_test"
    if any(segment in {"test", "tests", "test-resources", "testdata", "test-data"}
           or segment.endswith("-tests") or segment.startswith("tests-") for segment in segments):
        return "test", "path_contains_test_module_or_directory"
    if any(segment == "rollback" or segment.startswith("rollback_") or segment.startswith("rollback-")
           or segment in {"undo", "downgrade"} for segment in segments):
        return "rollback", "path_contains_rollback_directory"
    if any(segment == "manual" or segment.startswith("manual_") or segment.startswith("manual-")
           for segment in segments):
        return "manual", "path_contains_manual_directory"
    if any(segment in {"fixture", "fixtures"} or "fixture" in segment for segment in segments):
        return "fixture", "path_contains_fixture_directory"
    if any(segment in {"demo", "example", "examples", "sample", "samples"}
           or segment.startswith(("demo-", "example-", "sample-"))
           or segment.endswith(("-demo", "-example", "-sample"))
           or "-example-" in segment or "-demo-" in segment or "-sample-" in segment
           for segment in segments):
        return "demo", "path_contains_demo_example_or_sample"
    if any(segment in {"docs", "documentation"} for segment in segments):
        return "documentation", "path_contains_documentation_directory"
    if any(segment == "generated" or segment.startswith("generated-") for segment in segments):
        return "generated", "path_contains_generated_directory"
    if any(segment.startswith(("migration", "flyway", "liquibase"))
           or segment in {"migrations", "changelog", "changelogs"} for segment in segments):
        return "forward_migration", "path_contains_forward_migration_directory"
    if "/src/main/" in f"/{rel.strip('/')} /".replace(" /", "/"):
        return "production", "path_contains_src_main"
    return "unknown", "no_known_sql_source_role_marker"


def _annotate_sql_source_scope(repo: Path, item: dict[str, Any]) -> None:
    rel = item.get("file")
    path = repo / str(rel) if rel else repo
    scope, basis = _sql_source_scope_for_path(repo, path)
    item.setdefault("source_scope", scope)
    item.setdefault("source_scope_basis", basis)
    included = scope in _SQL_EFFECTIVE_SOURCE_SCOPES
    item.setdefault("effective_model_included", included)
    if not included:
        item.setdefault("effective_model_exclusion_basis", f"source_scope:{scope}")


def _split_sql_effective_schema(
    repo: Path,
    schema: dict[str, list[dict[str, Any]]],
) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    effective: dict[str, list[dict[str, Any]]] = {}
    excluded_facts: list[dict[str, Any]] = []
    excluded_changes: list[dict[str, Any]] = []
    scope_counts: dict[str, int] = {}
    group_scope_counts: dict[str, dict[str, int]] = {}

    for group, rows in schema.items():
        if not isinstance(rows, list):
            effective[group] = rows
            continue
        kept: list[dict[str, Any]] = []
        for raw in rows:
            item = dict(raw)
            _annotate_sql_source_scope(repo, item)
            scope = str(item.get("source_scope") or "unknown")
            scope_counts[scope] = scope_counts.get(scope, 0) + 1
            by_scope = group_scope_counts.setdefault(group, {})
            by_scope[scope] = by_scope.get(scope, 0) + 1
            if item.get("effective_model_included"):
                kept.append(item)
                continue
            snapshot = dict(item)
            snapshot["schema_fact_group"] = group
            if group == "schema_changes":
                excluded_changes.append(snapshot)
            else:
                excluded_facts.append(snapshot)
        effective[group] = kept

    summary = {
        "policy": "only forward_migration, production, and unknown SQL source scopes mutate the effective physical model; excluded facts remain observable",
        "effective_source_scopes": sorted(_SQL_EFFECTIVE_SOURCE_SCOPES),
        "counts_by_source_scope": dict(sorted(scope_counts.items())),
        "counts_by_group_and_source_scope": {
            group: dict(sorted(counts.items())) for group, counts in sorted(group_scope_counts.items())
        },
        "excluded_schema_fact_count": len(excluded_facts),
        "excluded_schema_change_count": len(excluded_changes),
    }
    return effective, excluded_facts, excluded_changes, summary


def _simple_schema_identifier(value: str | None) -> str | None:
    text = str(value or "").strip().strip('"').strip("'")
    text = text.rstrip(",")
    if not text or any(token in text for token in ("${", "{{", "}}", "<%", "%>")):
        return None
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_$]*", text):
        return None
    return text.lower()


def _schema_resolution_observation(
    *, repo: Path, path: Path, kind: str, raw_value: str, line_start: int,
    placeholder_name: str | None = None,
) -> dict[str, Any]:
    exact = _simple_schema_identifier(raw_value)
    return {
        "schema_resolution_observation_id": f"schema_resolution_{_hash(_rel(repo, path) + ':' + str(line_start) + ':' + kind + ':' + str(placeholder_name or '') + ':' + raw_value)}",
        "fact_type": "schema_resolution_observation",
        "observation_kind": kind,
        "placeholder_name": placeholder_name.lower() if placeholder_name else None,
        "raw_value": raw_value.strip(),
        "resolved_schema_name": exact,
        "value_is_exact_identifier": exact is not None,
        "file": _rel(repo, path),
        "line_start": line_start,
        "module_name": _module_name_for_path(repo, path),
        "evidence": [{"file": _rel(repo, path), "line_start": line_start, "kind": kind}],
    }


def _scan_schema_resolution_observations(repo: Path, files: list[Path]) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    supported = {".sql", ".conf", ".properties", ".yml", ".yaml", ".xml", ".env"}
    placeholder_rx = re.compile(
        r"(?P<prefix>(?:flyway\.)?placeholders)[._](?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*[:=]\s*(?P<value>[^\s,\]\}]+)",
        re.IGNORECASE,
    )
    default_patterns = [
        ("flyway_default_schema", re.compile(r"\bflyway_default_schema\s*:\s*[\"']?(?P<value>[^\"'\n#]+)", re.IGNORECASE)),
        ("flyway_default_schema", re.compile(r"\bflyway\.defaultSchema\s*[:=]\s*[\"']?(?P<value>[^\"'\n#]+)", re.IGNORECASE)),
        ("spring_flyway_default_schema", re.compile(r"\bspring\.flyway\.(?:default-schema|defaultSchema)\s*[:=]\s*[\"']?(?P<value>[^\"'\n#]+)", re.IGNORECASE)),
        ("flyway_schemas", re.compile(r"\bflyway\.schemas\s*[:=]\s*[\"']?(?P<value>[^\"'\n#]+)", re.IGNORECASE)),
    ]
    current_schema_rx = re.compile(r"[?&]currentSchema=(?P<value>[A-Za-z_][A-Za-z0-9_$]*)", re.IGNORECASE)
    search_path_rx = re.compile(r"\bset\s+(?:local\s+)?search_path\s*(?:to|=)\s*(?P<value>[A-Za-z_][A-Za-z0-9_$]*)", re.IGNORECASE)

    for path in sorted(files):
        if not path.is_file() or path.suffix.lower() not in supported:
            continue
        text = read_text(path)
        for match in placeholder_rx.finditer(text):
            observations.append(_schema_resolution_observation(
                repo=repo, path=path, kind="flyway_placeholder_value",
                placeholder_name=match.group("name"), raw_value=match.group("value"),
                line_start=line_number_for_offset(text, match.start()),
            ))
        for kind, rx in default_patterns:
            for match in rx.finditer(text):
                raw_value = match.group("value").strip()
                # A comma-separated flyway.schemas list is not one exact default schema.
                observations.append(_schema_resolution_observation(
                    repo=repo, path=path, kind=kind, raw_value=raw_value,
                    line_start=line_number_for_offset(text, match.start()),
                ))
        for match in current_schema_rx.finditer(text):
            observations.append(_schema_resolution_observation(
                repo=repo, path=path, kind="jdbc_current_schema", raw_value=match.group("value"),
                line_start=line_number_for_offset(text, match.start()),
            ))
        if path.suffix.lower() == ".sql":
            for match in search_path_rx.finditer(text):
                observations.append(_schema_resolution_observation(
                    repo=repo, path=path, kind="sql_search_path", raw_value=match.group("value"),
                    line_start=line_number_for_offset(text, match.start()),
                ))
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for item in observations:
        key = (str(item.get("observation_kind")), str(item.get("placeholder_name")), str(item.get("raw_value")), str(item.get("file")))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _unique_exact_schema_candidates(
    observations: list[dict[str, Any]], *, kinds: set[str], placeholder_name: str | None = None,
    module_name: str | None = None,
) -> list[str]:
    values: set[str] = set()
    for item in observations:
        if str(item.get("observation_kind")) not in kinds:
            continue
        if placeholder_name is not None and str(item.get("placeholder_name") or "").lower() != placeholder_name.lower():
            continue
        if module_name is not None and item.get("module_name") != module_name:
            continue
        value = item.get("resolved_schema_name")
        if value:
            values.add(str(value))
    return sorted(values)


def _resolve_one_schema_identity(
    item: dict[str, Any], *, repo: Path, observations: list[dict[str, Any]],
    schema_field: str, table_field: str, qualified_field: str, basis_field: str,
    placeholder_field: str,
) -> None:
    table_name = item.get(table_field)
    if not table_name:
        return
    rel = item.get("file")
    module_name = _module_name_for_path(repo, repo / str(rel)) if rel else None
    schema_name = item.get(schema_field)
    basis = str(item.get(basis_field) or "")
    placeholder_name = item.get(placeholder_field)
    if not placeholder_name and basis == "placeholder_reference":
        placeholder_name = schema_name
    if placeholder_name:
        placeholder_name = str(placeholder_name).lower()
        same_module = _unique_exact_schema_candidates(
            observations, kinds={"flyway_placeholder_value"}, placeholder_name=placeholder_name, module_name=module_name,
        )
        candidates = same_module or _unique_exact_schema_candidates(
            observations, kinds={"flyway_placeholder_value"}, placeholder_name=placeholder_name,
        )
        item["declared_schema_reference"] = f"${{{placeholder_name}}}"
        item[placeholder_field] = placeholder_name
        if len(candidates) == 1:
            schema_name = candidates[0]
            item[basis_field] = "flyway_placeholder_exact_config"
            item["schema_resolution_status"] = "resolved_exact"
            item["schema_resolution_candidates"] = candidates
        else:
            schema_name = None
            item[basis_field] = "unresolved_placeholder_reference"
            item["schema_resolution_status"] = "unresolved" if not candidates else "ambiguous"
            item["schema_resolution_candidates"] = candidates
    elif schema_name:
        item.setdefault(basis_field, "explicit_sql_schema")
        item.setdefault("schema_resolution_status", "declared_explicit")
    else:
        default_kinds = {"flyway_default_schema", "spring_flyway_default_schema", "flyway_schemas", "jdbc_current_schema", "sql_search_path"}
        same_module = _unique_exact_schema_candidates(observations, kinds=default_kinds, module_name=module_name)
        candidates = same_module or _unique_exact_schema_candidates(observations, kinds=default_kinds)
        if len(candidates) == 1:
            schema_name = candidates[0]
            item[basis_field] = "exact_default_schema_config"
            item["schema_resolution_status"] = "resolved_exact"
            item["schema_resolution_candidates"] = candidates
        else:
            schema_name = None
            item[basis_field] = "unresolved_unqualified_sql"
            item["schema_resolution_status"] = "unresolved" if not candidates else "ambiguous"
            item["schema_resolution_candidates"] = candidates
    item[schema_field] = schema_name
    item[qualified_field] = _qualified_table_name(schema_name, table_name)


def _resolve_sql_schema_identities(
    repo: Path, schema: dict[str, list[dict[str, Any]]], observations: list[dict[str, Any]], *, repo_id: str,
) -> None:
    for group, rows in schema.items():
        if not isinstance(rows, list):
            continue
        for item in rows:
            if not isinstance(item, dict):
                continue
            if group in {"relationships", "triggers"}:
                _resolve_one_schema_identity(
                    item, repo=repo, observations=observations,
                    schema_field="source_schema", table_field="source_table", qualified_field="source_qualified_table_name",
                    basis_field="source_schema_name_basis", placeholder_field="source_schema_reference_placeholder",
                )
                if group == "relationships" and item.get("target_table"):
                    _resolve_one_schema_identity(
                        item, repo=repo, observations=observations,
                        schema_field="target_schema", table_field="target_table", qualified_field="target_qualified_table_name",
                        basis_field="target_schema_name_basis", placeholder_field="target_schema_reference_placeholder",
                    )
            elif group == "partitioning" and item.get("partition_fact_kind") == "child_partition":
                _resolve_one_schema_identity(
                    item, repo=repo, observations=observations,
                    schema_field="schema_name", table_field="table_name", qualified_field="qualified_table_name",
                    basis_field="schema_name_basis", placeholder_field="schema_reference_placeholder",
                )
                _resolve_one_schema_identity(
                    item, repo=repo, observations=observations,
                    schema_field="partition_schema_name", table_field="partition_table_name", qualified_field="qualified_partition_table_name",
                    basis_field="partition_schema_name_basis", placeholder_field="partition_schema_reference_placeholder",
                )
                item["parent_schema_name"] = item.get("schema_name")
                item["parent_qualified_table_name"] = item.get("qualified_table_name")
            elif item.get("table_name"):
                _resolve_one_schema_identity(
                    item, repo=repo, observations=observations,
                    schema_field="schema_name", table_field="table_name", qualified_field="qualified_table_name",
                    basis_field="schema_name_basis", placeholder_field="schema_reference_placeholder",
                )
            _refresh_schema_fact_id(group, item, repo_id)


def _module_name_for_path(repo: Path, path: Path) -> str | None:
    rel = _rel(repo, path)
    parts = [x for x in rel.split('/') if x]
    if not parts:
        return None
    if parts[0] in {'src', 'target', 'build'}:
        return None
    return parts[0]


def _domain_hint_from_module(module_name: str | None) -> str | None:
    if not module_name:
        return None
    name = module_name.lower()
    for suffix in ['-db-migrations', '-data-access', '-common']:
        if name.endswith(suffix):
            name = name[:-len(suffix)]
    return name.replace('-', '_') or None


def _sql_identifier_parts(value: str | None) -> tuple[str | None, str]:
    text = (value or '').strip().strip(';').strip()
    text = re.sub(r'^if\s+not\s+exists\s+', '', text, flags=re.IGNORECASE).strip()
    if not text:
        return None, ''
    parts = []
    cur = []
    in_quote = False
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == '"':
            in_quote = not in_quote
            cur.append(ch)
        elif ch == '.' and not in_quote:
            parts.append(''.join(cur).strip())
            cur = []
        else:
            cur.append(ch)
        i += 1
    parts.append(''.join(cur).strip())
    clean_parts = []
    for part in parts:
        part = re.sub(r'^\$\{([^}]+)\}$', r'\1', part.strip())
        part = part.strip().strip('"').strip()
        if part:
            clean_parts.append(part.lower())
    if not clean_parts:
        return None, ''
    if len(clean_parts) >= 2:
        return clean_parts[-2], clean_parts[-1]
    return None, clean_parts[-1]


def _sql_schema_reference_basis(value: str | None) -> str | None:
    text = str(value or "").strip()
    if re.match(r"^\$\{[^}]+\}\s*\.", text):
        return "placeholder_reference"
    return None


def _qualified_table_name(schema_name: str | None, table_name: str | None) -> str:
    table = normalize_name(table_name or '')
    schema = normalize_name(schema_name or '')
    return f'{schema}.{table}' if schema and table else table


def _attach_schema_identity(item: dict[str, Any], *, repo: Path, path: Path, table_key: str = 'table_name') -> None:
    schema = item.get('schema_name') or item.get('source_schema') or item.get('target_schema')
    table = item.get(table_key)
    if not schema:
        item.setdefault('schema_name_basis', 'unresolved_unqualified_sql')
        item.setdefault('schema_resolution_status', 'unresolved')
    if table:
        qualified = _qualified_table_name(item.get('schema_name'), table)
        if not item.get('qualified_table_name') or (item.get('schema_name') and '.' not in str(item.get('qualified_table_name') or '')):
            item['qualified_table_name'] = qualified
    item.setdefault('source_set', _source_set_for_path(path))
    item.setdefault('is_test_source', _is_test_source_path(path))
    item.setdefault('module_name', _module_name_for_path(repo, path))


def _unescape_java_string(value: str | None) -> str | None:
    if value is None:
        return None
    # Most generated jOOQ sources store comments as normal UTF-8 Java strings.
    # Do not decode the whole string with unicode_escape: it corrupts Cyrillic and
    # other non-ASCII text. Only unescape common Java string escapes conservatively.
    return (
        value
        .replace('\\"', '"')
        .replace('\\n', '\n')
        .replace('\\r', '\r')
        .replace('\\t', '\t')
        .replace('\\\\', '\\')
    )


def _java_string_literal_re(name: str) -> str:
    return rf'{name}\s*\(\s*"(?P<{name}>[^"\\]*(?:\\.[^"\\]*)*)"\s*\)'


def _field_refs(body: str) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for m in re.finditer(r"([A-Z][A-Za-z0-9_]*)\.([A-Z0-9_]+)\.([A-Z0-9_]+)", body or ""):
        out.append({"table_class": m.group(1), "table_constant": m.group(2), "field_constant": m.group(3)})
    return out


def _field_ref_columns(body: str, *, table_by_constant: dict[str, str], column_by_ref: dict[tuple[str, str], str]) -> list[str]:
    cols: list[str] = []
    for ref in _field_refs(body):
        table_name = table_by_constant.get(ref["table_constant"]) or table_by_constant.get(ref["table_class"].upper())
        col = column_by_ref.get((ref["table_constant"], ref["field_constant"]))
        if not col:
            col = ref["field_constant"].lower()
        cols.append(col)
    return cols


def _extract_sql_type(type_expr: str) -> str:
    text = " ".join((type_expr or "").split())
    m = re.search(r"SQLDataType\.([A-Z0-9_]+(?:\([^)]*\))?)", text)
    if m:
        return m.group(1)
    m = re.search(r"DefaultDataType\.getDefaultDataType\(\s*\"([^\"]+)\"\s*\)", text)
    if m:
        return m.group(1)
    return text[:220] or "unknown"


def _extract_default(type_expr: str) -> str | None:
    text = " ".join((type_expr or "").split())
    m = re.search(r"\.defaultValue\((.*?)\)", text)
    if m:
        return m.group(1)[:240]
    return None


def _scan_jooq_table_file(repo: Path, path: Path, *, repo_id: str, project_code: str, system_name: str) -> tuple[dict[str, Any] | None, list[dict[str, Any]], dict[str, str], dict[tuple[str, str], str]]:
    text = read_text(path)
    rel = _rel(repo, path)
    if "extends TableImpl" not in text or "createField" not in text:
        return None, [], {}, {}
    class_m = re.search(r"public\s+class\s+(?P<class>[A-Za-z0-9_]+)\s+extends\s+TableImpl\s*<\s*(?P<record>[A-Za-z0-9_]+)\s*>", text)
    if not class_m:
        return None, [], {}, {}
    class_name = class_m.group("class")
    record_type = class_m.group("record")
    const_m = re.search(rf"public\s+static\s+final\s+{re.escape(class_name)}\s+(?P<const>[A-Z0-9_]+)\s*=\s*new\s+{re.escape(class_name)}\s*\(", text)
    table_constant = const_m.group("const") if const_m else normalize_name(class_name).upper()
    table_m = re.search(r"this\s*\(\s*DSL\.name\(\s*\"(?P<table>[^\"]+)\"\s*\)\s*,\s*null\s*\)", text)
    table_name = table_m.group("table") if table_m else table_constant.lower()
    schema_m = re.search(r"return\s+([A-Za-z0-9_]+)\.([A-Z0-9_]+)\s*;", text)
    schema_name = schema_m.group(2).lower() if schema_m else None
    comment_m = re.search(r"DSL\.comment\(\s*\"(?P<comment>[^\"\\]*(?:\\.[^\"\\]*)*)\"\s*\)", text)
    description = _unescape_java_string(comment_m.group("comment")) if comment_m else None
    table_line = line_number_for_offset(text, class_m.start())
    table = {
        "db_schema_table_id": f"db_schema_table_{repo_id}_{_hash(table_name)}",
        "fact_type": "db_schema_table",
        "repo_id": repo_id,
        "project_code": project_code,
        "system_name": system_name,
        "table_name": table_name,
        "normalized_table_name": normalize_name(table_name),
        "schema_name": schema_name,
        "table_class": class_name,
        "table_constant": table_constant,
        "record_type": record_type,
        "description": description,
        "source_type": "jooq_generated_table_class",
        "file": rel,
        "line_start": table_line,
        "evidence_maturity_level": "confirmed",
        "evidence": [{"file": rel, "line_start": table_line, "kind": "jooq_table_class"}],
    }
    cols: list[dict[str, Any]] = []
    const_to_table = {table_constant: table_name, class_name.upper(): table_name}
    col_ref: dict[tuple[str, str], str] = {}
    field_rx = re.compile(
        r"public\s+final\s+TableField\s*<\s*[^,>]+\s*,\s*(?P<java_type>[^>]+?)\s*>\s+"
        r"(?P<field_const>[A-Z0-9_]+)\s*=\s*createField\s*\(\s*DSL\.name\(\s*\"(?P<column>[^\"]+)\"\s*\)\s*,\s*"
        r"(?P<type_expr>.*?)\s*,\s*this\s*,\s*\"(?P<comment>[^\"\\]*(?:\\.[^\"\\]*)*)\"\s*\)\s*;",
        re.DOTALL,
    )
    for m in field_rx.finditer(text):
        col_name = m.group("column")
        field_const = m.group("field_const")
        type_expr = " ".join(m.group("type_expr").split())
        nullable = False if ".nullable(false)" in type_expr else True if ".nullable(true)" in type_expr else None
        line = line_number_for_offset(text, m.start())
        col = {
            "db_schema_column_id": f"db_schema_column_{repo_id}_{_hash(table_name + '.' + col_name)}",
            "fact_type": "db_schema_column",
            "repo_id": repo_id,
            "project_code": project_code,
            "system_name": system_name,
            "table_name": table_name,
            "normalized_table_name": normalize_name(table_name),
            "column_name": col_name,
            "normalized_column_name": normalize_name(col_name),
            "field_constant": field_const,
            "java_type": m.group("java_type").strip(),
            "sql_type": _extract_sql_type(type_expr),
            "sql_type_expression": type_expr[:500],
            "nullable": nullable,
            "default_value": _extract_default(type_expr),
            "description": _unescape_java_string(m.group("comment")),
            "source_type": "jooq_generated_table_class",
            "file": rel,
            "line_start": line,
            "evidence_maturity_level": "confirmed",
            "evidence": [{"file": rel, "line_start": line, "kind": "jooq_table_field"}],
        }
        cols.append(col)
        col_ref[(table_constant, field_const)] = col_name
    # Table-level key/index references declared in table class methods.
    pk_m = re.search(r"getPrimaryKey\s*\(\s*\).*?return\s+Keys\.([A-Z0-9_]+)\s*;", text, re.DOTALL)
    if pk_m:
        table["primary_key_constant"] = pk_m.group(1)
    idx_m = re.search(r"getIndexes\s*\(\s*\).*?return\s+Arrays\.[^;]+?asList\((?P<body>.*?)\)\s*;", text, re.DOTALL)
    if idx_m:
        table["index_constants"] = re.findall(r"Indexes\.([A-Z0-9_]+)", idx_m.group("body"))
    return table, cols, const_to_table, col_ref


def _scan_jooq_keys(repo: Path, files: list[Path], *, repo_id: str, project_code: str, system_name: str, table_by_constant: dict[str, str], column_by_ref: dict[tuple[str, str], str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    keys: list[dict[str, Any]] = []
    relationships: list[dict[str, Any]] = []
    key_by_const: dict[str, dict[str, Any]] = {}
    key_files = [p for p in files if p.name == "Keys.java" and "generated" in str(p).replace("\\", "/")]
    for path in key_files:
        text = read_text(path)
        rel = _rel(repo, path)
        uk_rx = re.compile(
            r"public\s+static\s+final\s+UniqueKey\s*<[^>]+>\s+(?P<const>[A-Z0-9_]+)\s*=\s*Internal\.createUniqueKey\s*\(\s*"
            r"(?P<table_ref>[A-Za-z0-9_]+\.[A-Z0-9_]+)\s*,\s*\"(?P<name>[^\"]+)\"\s*,\s*new\s+TableField\[\]\s*\{(?P<fields>.*?)\}\s*,\s*(?P<flag>true|false)\s*\)\s*;",
            re.DOTALL,
        )
        for m in uk_rx.finditer(text):
            const = m.group("const")
            table_const = m.group("table_ref").split(".")[-1]
            table_name = table_by_constant.get(table_const) or table_const.lower()
            columns = _field_ref_columns(m.group("fields"), table_by_constant=table_by_constant, column_by_ref=column_by_ref)
            kind = "primary_key" if const.startswith("PK_") or m.group("name").lower().startswith("pk") else "unique_key"
            line = line_number_for_offset(text, m.start())
            item = {
                "db_schema_key_id": f"db_schema_key_{repo_id}_{_hash(table_name + '.' + m.group('name'))}",
                "fact_type": "db_schema_key",
                "repo_id": repo_id,
                "project_code": project_code,
                "system_name": system_name,
                "key_constant": const,
                "constraint_name": m.group("name"),
                "constraint_kind": kind,
                "table_name": table_name,
                "columns": columns,
                "source_type": "jooq_generated_keys",
                "file": rel,
                "line_start": line,
                "evidence_maturity_level": "confirmed",
                "evidence": [{"file": rel, "line_start": line, "kind": "jooq_unique_key"}],
            }
            keys.append(item)
            key_by_const[const] = item
        fk_rx = re.compile(
            r"public\s+static\s+final\s+ForeignKey\s*<[^>]+>\s+(?P<const>[A-Z0-9_]+)\s*=\s*Internal\.createForeignKey\s*\(\s*Keys\.(?P<target_key>[A-Z0-9_]+)\s*,\s*"
            r"(?P<src_table_ref>[A-Za-z0-9_]+\.[A-Z0-9_]+)\s*,\s*\"(?P<name>[^\"]+)\"\s*,\s*new\s+TableField\[\]\s*\{(?P<src_fields>.*?)\}\s*,\s*(?P<flag>true|false)\s*\)\s*;",
            re.DOTALL,
        )
        for m in fk_rx.finditer(text):
            src_const = m.group("src_table_ref").split(".")[-1]
            source_table = table_by_constant.get(src_const) or src_const.lower()
            source_columns = _field_ref_columns(m.group("src_fields"), table_by_constant=table_by_constant, column_by_ref=column_by_ref)
            target_key = key_by_const.get(m.group("target_key"))
            target_table = target_key.get("table_name") if target_key else None
            target_columns = target_key.get("columns") if target_key else []
            line = line_number_for_offset(text, m.start())
            relationships.append({
                "db_schema_relationship_id": f"db_schema_relationship_{repo_id}_{_hash(source_table + '.' + m.group('name'))}",
                "fact_type": "db_schema_relationship",
                "repo_id": repo_id,
                "project_code": project_code,
                "system_name": system_name,
                "relationship_constant": m.group("const"),
                "constraint_name": m.group("name"),
                "relationship_kind": "foreign_key",
                "source_table": source_table,
                "source_columns": source_columns,
                "target_table": target_table,
                "target_columns": target_columns,
                "target_key_constant": m.group("target_key"),
                "source_type": "jooq_generated_keys",
                "file": rel,
                "line_start": line,
                "evidence_maturity_level": "confirmed" if target_table else "unresolved",
                "evidence": [{"file": rel, "line_start": line, "kind": "jooq_foreign_key"}],
            })
    return keys, relationships


def _scan_jooq_indexes(repo: Path, files: list[Path], *, repo_id: str, project_code: str, system_name: str, table_by_constant: dict[str, str], column_by_ref: dict[tuple[str, str], str]) -> list[dict[str, Any]]:
    indexes: list[dict[str, Any]] = []
    idx_files = [p for p in files if p.name == "Indexes.java" and "generated" in str(p).replace("\\", "/")]
    idx_rx = re.compile(
        r"public\s+static\s+(?:final\s+)?Index\s+(?P<const>[A-Z0-9_]+)\s*=\s*Internal\.createIndex\s*\(\s*\"(?P<name>[^\"]+)\"\s*,\s*"
        r"(?P<table_ref>[A-Za-z0-9_]+\.[A-Z0-9_]+)\s*,\s*new\s+OrderField\[\]\s*\{(?P<fields>.*?)\}\s*,\s*(?P<unique>true|false)\s*\)\s*;",
        re.DOTALL,
    )
    for path in idx_files:
        text = read_text(path)
        rel = _rel(repo, path)
        for m in idx_rx.finditer(text):
            table_const = m.group("table_ref").split(".")[-1]
            table_name = table_by_constant.get(table_const) or table_const.lower()
            columns = _field_ref_columns(m.group("fields"), table_by_constant=table_by_constant, column_by_ref=column_by_ref)
            line = line_number_for_offset(text, m.start())
            indexes.append({
                "db_schema_index_id": f"db_schema_index_{repo_id}_{_hash(table_name + '.' + m.group('name'))}",
                "fact_type": "db_schema_index",
                "repo_id": repo_id,
                "project_code": project_code,
                "system_name": system_name,
                "index_constant": m.group("const"),
                "index_name": m.group("name"),
                "table_name": table_name,
                "columns": columns,
                "unique": m.group("unique") == "true",
                "source_type": "jooq_generated_indexes",
                "file": rel,
                "line_start": line,
                "evidence_maturity_level": "confirmed",
                "evidence": [{"file": rel, "line_start": line, "kind": "jooq_index"}],
            })
    return indexes





def _scan_jooq_sequences(repo: Path, files: list[Path], *, repo_id: str, project_code: str, system_name: str) -> list[dict[str, Any]]:
    sequences: list[dict[str, Any]] = []
    seq_files = [p for p in files if p.name == "Sequences.java" and "generated" in str(p).replace("\\", "/")]
    seq_rx = re.compile(
        r"public\s+static\s+final\s+Sequence\s*<\s*(?P<java_type>[^>]+?)\s*>\s+(?P<const>[A-Z0-9_]+)\s*=\s*Internal\.createSequence\s*\(\s*\"(?P<name>[^\"]+)\"\s*,\s*(?P<schema_ref>[A-Za-z0-9_]+\.[A-Z0-9_]+|null)\s*,\s*(?P<type_expr>.*?)\)\s*;",
        re.DOTALL,
    )
    for path in seq_files:
        text = read_text(path)
        rel = _rel(repo, path)
        for m in seq_rx.finditer(text):
            seq_name = m.group("name")
            schema_ref = m.group("schema_ref")
            schema_name = schema_ref.split(".")[-1].lower() if schema_ref and schema_ref != "null" else None
            line = line_number_for_offset(text, m.start())
            sequences.append({
                "db_schema_sequence_id": f"db_schema_sequence_{repo_id}_{_hash(seq_name)}",
                "fact_type": "db_schema_sequence",
                "repo_id": repo_id,
                "project_code": project_code,
                "system_name": system_name,
                "sequence_constant": m.group("const"),
                "sequence_name": seq_name,
                "normalized_sequence_name": normalize_name(seq_name),
                "schema_name": schema_name,
                "java_type": m.group("java_type").strip(),
                "sql_type": _extract_sql_type(m.group("type_expr")),
                "source_type": "jooq_generated_sequences",
                "file": rel,
                "line_start": line,
                "evidence_maturity_level": "confirmed",
                "evidence": [{"file": rel, "line_start": line, "kind": "jooq_sequence"}],
            })
    return sequences


def _scan_jooq_check_constraints(repo: Path, files: list[Path], *, repo_id: str, project_code: str, system_name: str, table_by_constant: dict[str, str]) -> list[dict[str, Any]]:
    constraints: list[dict[str, Any]] = []
    table_files = [
        p for p in files
        if p.is_file() and p.suffix.lower() == ".java" and "/generated/tables/" in str(p).replace("\\", "/") and "/records/" not in str(p).replace("\\", "/")
    ]
    check_rx = re.compile(
        r"Internal\.createCheck\s*\(\s*this\s*,\s*DSL\.name\(\s*\"(?P<name>[^\"]+)\"\s*\)\s*,\s*\"(?P<expr>[^\"\\]*(?:\\.[^\"\\]*)*)\"\s*,\s*(?P<enforced>true|false)\s*\)",
        re.DOTALL,
    )
    for path in table_files:
        text = read_text(path)
        rel = _rel(repo, path)
        class_m = re.search(r"public\s+class\s+(?P<class>[A-Za-z0-9_]+)\s+extends\s+TableImpl", text)
        const_m = None
        if class_m:
            class_name = class_m.group("class")
            const_m = re.search(rf"public\s+static\s+final\s+{re.escape(class_name)}\s+(?P<const>[A-Z0-9_]+)\s*=", text)
        table_const = const_m.group("const") if const_m else (class_m.group("class").upper() if class_m else "")
        table_name = table_by_constant.get(table_const) or normalize_name(class_m.group("class") if class_m else path.stem)
        for m in check_rx.finditer(text):
            name = m.group("name")
            line = line_number_for_offset(text, m.start())
            constraints.append({
                "db_schema_constraint_id": f"db_schema_constraint_{repo_id}_{_hash(table_name + '.' + name)}",
                "fact_type": "db_schema_constraint",
                "repo_id": repo_id,
                "project_code": project_code,
                "system_name": system_name,
                "constraint_name": name,
                "constraint_kind": "check",
                "table_name": table_name,
                "expression": _unescape_java_string(m.group("expr")),
                "enforced": m.group("enforced") == "true",
                "source_type": "jooq_generated_table_class",
                "file": rel,
                "line_start": line,
                "evidence_maturity_level": "confirmed",
                "evidence": [{"file": rel, "line_start": line, "kind": "jooq_check_constraint"}],
            })
    return constraints

def _strip_sql_line_comments(sql: str) -> str:
    """Remove SQL -- comments while preserving line count for diagnostics."""
    out_lines: list[str] = []
    for line in (sql or "").splitlines():
        in_single = False
        i = 0
        cut = len(line)
        while i < len(line) - 1:
            ch = line[i]
            if ch == "'":
                # SQL escapes a single quote inside a string by doubling it.
                if in_single and i + 1 < len(line) and line[i + 1] == "'":
                    i += 2
                    continue
                in_single = not in_single
            if not in_single and line[i:i + 2] == "--":
                cut = i
                break
            i += 1
        out_lines.append(line[:cut])
    return "\n".join(out_lines)


def _clean_sql_identifier(value: str | None) -> str:
    text = (value or "").strip().strip('"')
    text = re.sub(r"^\$\{[^}]+\}\.", "", text)
    if "." in text:
        text = text.split(".")[-1]
    return text.strip().strip('"')


def _sql_column_list(value: str | None) -> list[str]:
    cols: list[str] = []
    for raw in _split_top_level_commas((value or "").strip().strip("()")):
        col = _clean_sql_identifier(re.sub(r"\s+(asc|desc|nulls\s+first|nulls\s+last)\b.*$", "", raw.strip(), flags=re.IGNORECASE))
        if col:
            cols.append(col.lower())
    return cols


def _split_top_level_commas(value: str) -> list[str]:
    parts: list[str] = []
    start = 0
    depth = 0
    in_single = False
    i = 0
    while i < len(value):
        ch = value[i]
        if ch == "'":
            if in_single and i + 1 < len(value) and value[i + 1] == "'":
                i += 2
                continue
            in_single = not in_single
        elif not in_single:
            if ch == "(":
                depth += 1
            elif ch == ")" and depth > 0:
                depth -= 1
            elif ch == "," and depth == 0:
                part = value[start:i].strip()
                if part:
                    parts.append(part)
                start = i + 1
        i += 1
    tail = value[start:].strip()
    if tail:
        parts.append(tail)
    return parts


def _find_matching_paren(text: str, open_idx: int) -> int:
    depth = 0
    in_single = False
    i = open_idx
    while i < len(text):
        ch = text[i]
        if ch == "'":
            if in_single and i + 1 < len(text) and text[i + 1] == "'":
                i += 2
                continue
            in_single = not in_single
        elif not in_single:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    return i
        i += 1
    return -1


def _iter_create_table_blocks(sql: str):
    rx = re.compile(
        r"\bcreate\s+table\s+(?:if\s+not\s+exists\s+)?(?P<table>(?:(?:\$\{[^}]+\}|[A-Za-z0-9_\"]+)\.)?[A-Za-z0-9_\"]+)\s*\(",
        re.IGNORECASE,
    )
    for m in rx.finditer(sql):
        open_idx = sql.find("(", m.end() - 1)
        if open_idx < 0:
            continue
        close_idx = _find_matching_paren(sql, open_idx)
        if close_idx < 0:
            continue
        table_raw = m.group("table")
        schema_name, table_name = _sql_identifier_parts(table_raw)
        yield m, table_name, schema_name, sql[open_idx + 1:close_idx], close_idx




def _mask_sql_literal_bodies(sql: str) -> str:
    """Mask quoted SQL bodies while preserving offsets and line structure.

    Static partition DDL must not be extracted from strings passed to EXECUTE/format
    or from dollar-quoted function bodies. Double-quoted identifiers remain visible.
    """
    chars = list(sql or "")
    i = 0
    single_quote = False
    dollar_tag: str | None = None
    while i < len(chars):
        if dollar_tag is not None:
            if (sql or "").startswith(dollar_tag, i):
                for j in range(i, min(len(chars), i + len(dollar_tag))):
                    if chars[j] != "\n":
                        chars[j] = " "
                i += len(dollar_tag)
                dollar_tag = None
                continue
            if chars[i] != "\n":
                chars[i] = " "
            i += 1
            continue
        if single_quote:
            if chars[i] == "'":
                if i + 1 < len(chars) and chars[i + 1] == "'":
                    chars[i] = chars[i + 1] = " "
                    i += 2
                    continue
                chars[i] = " "
                single_quote = False
                i += 1
                continue
            if chars[i] != "\n":
                chars[i] = " "
            i += 1
            continue
        if chars[i] == "'":
            chars[i] = " "
            single_quote = True
            i += 1
            continue
        if chars[i] == "$":
            tag_m = re.match(r"\$[A-Za-z_][A-Za-z0-9_]*\$|\$\$", (sql or "")[i:])
            if tag_m:
                dollar_tag = tag_m.group(0)
                for j in range(i, min(len(chars), i + len(dollar_tag))):
                    if chars[j] != "\n":
                        chars[j] = " "
                i += len(dollar_tag)
                continue
        i += 1
    return "".join(chars)


def _extract_sql_child_partitions(
    sql: str,
    *,
    repo: Path,
    path: Path,
    repo_id: str,
    project_code: str,
    system_name: str,
) -> list[dict[str, Any]]:
    """Extract static PostgreSQL CREATE TABLE ... PARTITION OF facts.

    Child partitions are physical storage objects, not independent conceptual
    entities. The fact is attached to the parent table and preserves the child
    object's own qualified identity and declared partition bound.
    """
    out: list[dict[str, Any]] = []
    rel = _rel(repo, path)
    masked = _mask_sql_literal_bodies(sql or "")
    ident = r"(?:(?:\$\{[^}]+\}|[A-Za-z0-9_\"]+)\.)?[A-Za-z0-9_\"]+"
    rx = re.compile(
        rf"\bcreate\s+table\s+(?:if\s+not\s+exists\s+)?(?P<child>{ident})\s+"
        rf"partition\s+of\s+(?P<parent>{ident})(?P<tail>[^;]*);",
        re.IGNORECASE | re.DOTALL,
    )
    for m in rx.finditer(masked):
        child_schema, child_name = _sql_identifier_parts(m.group("child"))
        parent_schema, parent_name = _sql_identifier_parts(m.group("parent"))
        if not child_name or not parent_name:
            continue
        original_tail = (sql or "")[m.start("tail"):m.end("tail")]
        normalized_tail = " ".join(original_tail.split())
        bound_kind: str | None = None
        bound_expression: str | None = None
        if re.search(r"\bdefault\b", normalized_tail, re.IGNORECASE):
            bound_kind = "default"
            bound_expression = "default"
        else:
            bound_m = re.search(
                r"\bfor\s+values\s+(?P<bound>(?:from\s*\(.*?\)\s+to\s*\(.*?\)|in\s*\(.*?\)|with\s*\(.*?\)))"
                r"(?=\s+tablespace\b|\s+with\s*\(|$)",
                normalized_tail,
                re.IGNORECASE | re.DOTALL,
            )
            if bound_m:
                bound_expression = " ".join(bound_m.group("bound").split())
                low = bound_expression.lower()
                if low.startswith("from"):
                    bound_kind = "range"
                elif low.startswith("in"):
                    bound_kind = "list"
                elif low.startswith("with"):
                    bound_kind = "hash"
        tablespace_m = re.search(r"\btablespace\s+(?P<name>[^\s;]+)", normalized_tail, re.IGNORECASE)
        line = line_number_for_offset(sql or "", m.start())
        child_qtn = _qualified_table_name(child_schema, child_name)
        parent_qtn = _qualified_table_name(parent_schema, parent_name)
        out.append({
            "db_schema_partitioning_id": f"db_schema_partitioning_{repo_id}_{_hash(child_qtn + '.partition_of.' + parent_qtn)}",
            "fact_type": "db_schema_partitioning",
            "partition_fact_kind": "child_partition",
            "repo_id": repo_id,
            "project_code": project_code,
            "system_name": system_name,
            "table_name": parent_name,
            "schema_name": parent_schema,
            "parent_table_name": parent_name,
            "parent_schema_name": parent_schema,
            "parent_qualified_table_name": parent_qtn,
            "schema_name_basis": _sql_schema_reference_basis(m.group("parent")) or ("explicit_sql_schema" if parent_schema else None),
            "schema_reference_placeholder": (parent_schema if _sql_schema_reference_basis(m.group("parent")) == "placeholder_reference" else None),
            "partition_table_name": child_name,
            "partition_schema_name": child_schema,
            "partition_schema_name_basis": _sql_schema_reference_basis(m.group("child")) or ("explicit_sql_schema" if child_schema else None),
            "partition_schema_reference_placeholder": (child_schema if _sql_schema_reference_basis(m.group("child")) == "placeholder_reference" else None),
            "qualified_partition_table_name": child_qtn,
            "partition_bound_kind": bound_kind,
            "partition_bound_expression": bound_expression,
            "tablespace": tablespace_m.group("name") if tablespace_m else None,
            "source_type": "liquibase_sql_ddl",
            "file": rel,
            "line_start": line,
            "evidence_maturity_level": "confirmed",
            "evidence": [{"file": rel, "line_start": line, "kind": "sql_create_partition_of"}],
        })
    return out




def _ctas_output_column(expression: str) -> tuple[str | None, str | None]:
    """Return (output_column, direct_source_column) for a direct CTAS select item.

    This is syntax-only evidence. Expressions without an explicit alias are emitted
    only when they are a direct identifier reference. No type or semantic inference
    is made here.
    """
    raw = " ".join((expression or "").strip().split())
    if not raw:
        return None, None
    alias_m = re.search(r"\s+as\s+(?P<alias>[A-Za-z0-9_\"]+)\s*$", raw, re.IGNORECASE)
    alias: str | None = None
    source_expr = raw
    if alias_m:
        alias = _clean_sql_identifier(alias_m.group("alias")).lower() or None
        source_expr = raw[:alias_m.start()].strip()
    direct_m = re.fullmatch(
        r"(?:(?:\$\{[^}]+\}|[A-Za-z0-9_\"]+)\.)?(?P<column>[A-Za-z0-9_\"]+)",
        source_expr,
        re.IGNORECASE,
    )
    source_column = _clean_sql_identifier(direct_m.group("column")).lower() if direct_m else None
    return alias or source_column, source_column


def _extract_sql_create_table_as_select(
    sql: str,
    *,
    repo: Path,
    path: Path,
    repo_id: str,
    project_code: str,
    system_name: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Extract direct CREATE TABLE ... AS SELECT declarations and output columns."""
    tables: list[dict[str, Any]] = []
    columns: list[dict[str, Any]] = []
    rel = _rel(repo, path)
    masked = _mask_sql_literal_bodies(sql or "")
    ident = r"(?:(?:\$\{[^}]+\}|[A-Za-z0-9_\"]+)\.)?[A-Za-z0-9_\"]+"
    rx = re.compile(
        rf"\bcreate\s+table\s+(?:if\s+not\s+exists\s+)?(?P<table>{ident})\s+as\s+"
        rf"select\s+(?P<select>.*?)\s+from\s+(?P<source>{ident})(?P<tail>.*?);",
        re.IGNORECASE | re.DOTALL,
    )
    for match in rx.finditer(masked):
        schema_name, table_name = _sql_identifier_parts(match.group("table"))
        source_schema, source_table = _sql_identifier_parts(match.group("source"))
        if not table_name or not source_table:
            continue
        table_name = table_name.lower()
        schema_name = schema_name.lower() if schema_name else None
        source_table = source_table.lower()
        source_schema = source_schema.lower() if source_schema else None
        line = line_number_for_offset(sql or "", match.start())
        generation_id = f"sql_table_generation_{repo_id}_{_hash(rel + ':' + str(line) + ':' + _qualified_table_name(schema_name, table_name))}"
        tables.append({
            "db_schema_table_id": f"db_schema_table_{repo_id}_{_hash(_qualified_table_name(schema_name, table_name))}",
            "fact_type": "db_schema_table",
            "repo_id": repo_id,
            "project_code": project_code,
            "system_name": system_name,
            "table_name": table_name,
            "normalized_table_name": normalize_name(table_name),
            "schema_name": schema_name,
            "qualified_table_name": _qualified_table_name(schema_name, table_name),
            "table_creation_kind": "create_table_as_select",
            "derived_source_table": source_table,
            "derived_source_schema": source_schema,
            "derived_source_qualified_table_name": _qualified_table_name(source_schema, source_table),
            "schema_generation_id": generation_id,
            "source_type": "liquibase_sql_ddl",
            "file": rel,
            "line_start": line,
            "evidence_maturity_level": "confirmed",
            "evidence": [{"file": rel, "line_start": line, "kind": "sql_create_table_as_select"}],
        })
        original_select = (sql or "")[match.start("select"):match.end("select")]
        for index, raw_item in enumerate(_split_top_level_commas(original_select), start=1):
            output_column, source_column = _ctas_output_column(raw_item)
            if not output_column:
                continue
            col_line = line_number_for_offset(sql or "", match.start("select"))
            columns.append({
                "db_schema_column_id": f"db_schema_column_{repo_id}_{_hash(_qualified_table_name(schema_name, table_name) + '.' + output_column)}",
                "fact_type": "db_schema_column",
                "repo_id": repo_id,
                "project_code": project_code,
                "system_name": system_name,
                "table_name": table_name,
                "schema_name": schema_name,
                "qualified_table_name": _qualified_table_name(schema_name, table_name),
                "normalized_table_name": normalize_name(table_name),
                "column_name": output_column,
                "normalized_column_name": normalize_name(output_column),
                "column_ordinal": index,
                "source_expression": " ".join(raw_item.strip().split()),
                "derived_source_table": source_table,
                "derived_source_schema": source_schema,
                "derived_source_qualified_table_name": _qualified_table_name(source_schema, source_table),
                "derived_source_column": source_column,
                "schema_generation_id": generation_id,
                "source_type": "liquibase_sql_ddl",
                "file": rel,
                "line_start": col_line,
                "evidence_maturity_level": "confirmed",
                "evidence": [{"file": rel, "line_start": col_line, "kind": "sql_create_table_as_select_column"}],
            })
    return tables, columns


def _extract_sql_table_lifecycle_events(
    sql: str,
    *,
    repo: Path,
    path: Path,
    repo_id: str,
    project_code: str,
    system_name: str,
    created_tables: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Publish direct table lifecycle observations in source order."""
    events: list[dict[str, Any]] = []
    rel = _rel(repo, path)
    for table in created_tables:
        if str(table.get("file") or "") != rel:
            continue
        schema_name = table.get("schema_name")
        table_name = table.get("table_name")
        line = int(table.get("line_start") or 0)
        if not table_name:
            continue
        events.append({
            "db_schema_change_id": f"db_schema_change_{repo_id}_{_hash(rel + ':' + str(line) + ':create:' + _qualified_table_name(schema_name, table_name))}",
            "fact_type": "db_schema_change",
            "repo_id": repo_id,
            "project_code": project_code,
            "system_name": system_name,
            "schema_change_kind": "create_table_as_select" if table.get("table_creation_kind") == "create_table_as_select" else "create_table",
            "table_name": table_name,
            "schema_name": schema_name,
            "schema_name_basis": table.get("schema_name_basis"),
            "schema_reference_placeholder": table.get("schema_reference_placeholder"),
            "declared_schema_reference": table.get("declared_schema_reference"),
            "qualified_table_name": _qualified_table_name(schema_name, table_name),
            "schema_generation_id": table.get("schema_generation_id"),
            "file": rel,
            "line_start": line,
            "source_type": "liquibase_sql_ddl",
            "evidence": list(table.get("evidence") or []),
        })

    masked = _mask_sql_literal_bodies(sql or "")
    ident = r"(?:(?:\$\{[^}]+\}|[A-Za-z0-9_\"]+)\.)?[A-Za-z0-9_\"]+"
    drop_rx = re.compile(
        rf"\bdrop\s+table\s+(?:if\s+exists\s+)?(?P<table>{ident})(?:\s+(?:cascade|restrict))?\s*;",
        re.IGNORECASE,
    )
    for match in drop_rx.finditer(masked):
        schema_name, table_name = _sql_identifier_parts(match.group("table"))
        if not table_name:
            continue
        line = line_number_for_offset(sql or "", match.start())
        events.append({
            "db_schema_change_id": f"db_schema_change_{repo_id}_{_hash(rel + ':' + str(line) + ':drop:' + _qualified_table_name(schema_name, table_name))}",
            "fact_type": "db_schema_change",
            "repo_id": repo_id,
            "project_code": project_code,
            "system_name": system_name,
            "schema_change_kind": "drop_table",
            "table_name": table_name.lower(),
            "schema_name": schema_name.lower() if schema_name else None,
            "schema_name_basis": _sql_schema_reference_basis(match.group("table")) or ("explicit_sql_schema" if schema_name else None),
            "schema_reference_placeholder": (schema_name.lower() if schema_name and _sql_schema_reference_basis(match.group("table")) == "placeholder_reference" else None),
            "qualified_table_name": _qualified_table_name(schema_name, table_name),
            "file": rel,
            "line_start": line,
            "source_type": "liquibase_sql_ddl",
            "evidence": [{"file": rel, "line_start": line, "kind": "sql_drop_table"}],
        })

    rename_rx = re.compile(
        rf"\balter\s+table\s+(?P<source>{ident})\s+rename\s+to\s+(?P<target>{ident})\s*;",
        re.IGNORECASE,
    )
    for match in rename_rx.finditer(masked):
        source_schema, source_table = _sql_identifier_parts(match.group("source"))
        target_schema, target_table = _sql_identifier_parts(match.group("target"))
        if not source_table or not target_table:
            continue
        if not target_schema:
            target_schema = source_schema
        line = line_number_for_offset(sql or "", match.start())
        events.append({
            "db_schema_change_id": f"db_schema_change_{repo_id}_{_hash(rel + ':' + str(line) + ':rename:' + _qualified_table_name(source_schema, source_table) + '->' + _qualified_table_name(target_schema, target_table))}",
            "fact_type": "db_schema_change",
            "repo_id": repo_id,
            "project_code": project_code,
            "system_name": system_name,
            "schema_change_kind": "rename_table",
            "table_name": source_table.lower(),
            "schema_name": source_schema.lower() if source_schema else None,
            "schema_name_basis": _sql_schema_reference_basis(match.group("source")) or ("explicit_sql_schema" if source_schema else None),
            "schema_reference_placeholder": (source_schema.lower() if source_schema and _sql_schema_reference_basis(match.group("source")) == "placeholder_reference" else None),
            "qualified_table_name": _qualified_table_name(source_schema, source_table),
            "target_table_name": target_table.lower(),
            "target_schema_name": target_schema.lower() if target_schema else None,
            "target_schema_name_basis": _sql_schema_reference_basis(match.group("target")) or ("explicit_sql_schema" if target_schema and target_schema != source_schema else None),
            "target_schema_reference_placeholder": (target_schema.lower() if target_schema and _sql_schema_reference_basis(match.group("target")) == "placeholder_reference" else None),
            "target_qualified_table_name": _qualified_table_name(target_schema, target_table),
            "file": rel,
            "line_start": line,
            "source_type": "liquibase_sql_ddl",
            "evidence": [{"file": rel, "line_start": line, "kind": "sql_alter_table_rename"}],
        })
    return events


def _schema_fact_table_identity(group: str, item: dict[str, Any]) -> tuple[str | None, str | None]:
    if group in {"relationships", "triggers"}:
        return item.get("source_schema") or item.get("schema_name"), item.get("source_table") or item.get("table_name")
    return item.get("schema_name"), item.get("table_name")


def _set_schema_fact_table_identity(group: str, item: dict[str, Any], schema_name: str | None, table_name: str) -> None:
    if group in {"relationships", "triggers"}:
        item.setdefault("declared_source_table", item.get("source_table") or item.get("table_name"))
        item["source_schema"] = schema_name
        item["source_table"] = table_name
        item["source_qualified_table_name"] = _qualified_table_name(schema_name, table_name)
    else:
        item.setdefault("declared_table_name", item.get("table_name"))
        item["schema_name"] = schema_name
        item["table_name"] = table_name
        item["normalized_table_name"] = normalize_name(table_name)
        item["qualified_table_name"] = _qualified_table_name(schema_name, table_name)


def _refresh_schema_fact_id(group: str, item: dict[str, Any], repo_id: str) -> None:
    schema_name, table_name = _schema_fact_table_identity(group, item)
    qtn = _qualified_table_name(schema_name, table_name)
    if not qtn:
        return
    if group == "tables":
        item["db_schema_table_id"] = f"db_schema_table_{repo_id}_{_hash(qtn)}"
    elif group == "columns":
        item["db_schema_column_id"] = f"db_schema_column_{repo_id}_{_hash(qtn + '.' + str(item.get('column_name') or ''))}"
    elif group == "keys":
        item["db_schema_key_id"] = f"db_schema_key_{repo_id}_{_hash(qtn + '.' + str(item.get('constraint_name') or ''))}"
    elif group == "relationships":
        item["db_schema_relationship_id"] = f"db_schema_relationship_{repo_id}_{_hash(qtn + '.' + str(item.get('constraint_name') or ''))}"
    elif group == "indexes":
        item["db_schema_index_id"] = f"db_schema_index_{repo_id}_{_hash(qtn + '.' + str(item.get('index_name') or ''))}"
    elif group == "constraints":
        item["db_schema_constraint_id"] = f"db_schema_constraint_{repo_id}_{_hash(qtn + '.' + str(item.get('constraint_name') or ''))}"
    elif group == "partitioning":
        item["db_schema_partitioning_id"] = f"db_schema_partitioning_{repo_id}_{_hash(qtn + '.' + str(item.get('partition_fact_kind') or '') + '.' + str(item.get('partition_table_name') or ''))}"
    elif group == "triggers":
        item["db_schema_trigger_id"] = f"db_schema_trigger_{repo_id}_{_hash(qtn + '.' + str(item.get('trigger_name') or ''))}"


def _sql_migration_order_key(item: dict[str, Any]) -> tuple[Any, ...]:
    return (*_schema_source_order_key(item), int(item.get("line_start") or 0))


def _normalize_sql_migration_state(
    repo: Path,
    schema: dict[str, list[dict[str, Any]]],
    *,
    repo_id: str,
) -> dict[str, list[dict[str, Any]]]:
    """Normalize direct SQL DDL into active table generations.

    Raw lifecycle observations remain in ``schema_changes`` and replaced table
    snapshots are retained in ``historical_tables``. Final schema groups contain
    only facts assigned to a generation that is active after the observed migration
    sequence, plus unbound facts for tables whose CREATE statement is outside the
    scanned repository.
    """
    groups = ["tables", "columns", "keys", "relationships", "indexes", "constraints", "partitioning", "triggers"]
    changes = list(schema.get("schema_changes") or [])
    if not changes:
        schema.setdefault("historical_tables", [])
        return schema

    for item in changes:
        rel = item.get("file")
        path = repo / str(rel) if rel else repo
        # Migration-state matching uses only explicitly declared SQL identity.
        # Module-derived schemas are weak convenience hints and are attached only
        # after cross-source merging, otherwise an unqualified SQL table cannot
        # merge with a generated/JPA table that has an explicit schema.
        item.setdefault("source_set", _source_set_for_path(path))
        item.setdefault("is_test_source", _is_test_source_path(path))
        item.setdefault("module_name", _module_name_for_path(repo, path))
        item["qualified_table_name"] = _qualified_table_name(item.get("schema_name"), item.get("table_name"))
        if item.get("target_table_name"):
            target_schema = item.get("target_schema_name")
            if not target_schema:
                target_schema = item.get("schema_name")
                item["target_schema_name"] = target_schema
            item["target_qualified_table_name"] = _qualified_table_name(target_schema, item.get("target_table_name"))

    facts: list[tuple[tuple[Any, ...], int, str, dict[str, Any]]] = []
    for group in groups:
        for item in schema.get(group) or []:
            facts.append((_sql_migration_order_key(item), 1, group, item))
    for event in changes:
        kind = str(event.get("schema_change_kind") or "")
        priority = 0 if kind.startswith("create_table") else 2
        facts.append((_sql_migration_order_key(event), priority, "schema_changes", event))
    facts.sort(key=lambda entry: (entry[0], entry[1], str(entry[2])))

    current_generation: dict[str, str] = {}
    generation_final_qtn: dict[str, str] = {}
    generation_rename_chain: dict[str, list[dict[str, Any]]] = {}
    active_generations: set[str] = set()
    generation_columns: dict[tuple[str, str], dict[str, Any]] = {}

    for _order, _priority, group, item in facts:
        if group == "schema_changes":
            kind = str(item.get("schema_change_kind") or "")
            qtn = str(item.get("qualified_table_name") or "")
            if kind.startswith("create_table"):
                generation_id = str(item.get("schema_generation_id") or f"sql_table_generation_{repo_id}_{_hash(str(item.get('file')) + ':' + str(item.get('line_start')) + ':' + qtn)}")
                item["schema_generation_id"] = generation_id
                current_generation[qtn] = generation_id
                generation_final_qtn[generation_id] = qtn
                active_generations.add(generation_id)
            elif kind == "drop_table":
                generation_id = current_generation.pop(qtn, None)
                if generation_id:
                    active_generations.discard(generation_id)
                    item["affected_schema_generation_id"] = generation_id
            elif kind == "rename_table":
                target_qtn = str(item.get("target_qualified_table_name") or "")
                generation_id = current_generation.pop(qtn, None)
                if generation_id:
                    current_generation[target_qtn] = generation_id
                    generation_final_qtn[generation_id] = target_qtn
                    active_generations.add(generation_id)
                    item["affected_schema_generation_id"] = generation_id
                    generation_rename_chain.setdefault(generation_id, []).append({
                        "from": qtn,
                        "to": target_qtn,
                        "file": item.get("file"),
                        "line_start": item.get("line_start"),
                    })
            continue

        schema_name, table_name = _schema_fact_table_identity(group, item)
        qtn = _qualified_table_name(schema_name, table_name)
        generation_id = current_generation.get(qtn)
        if generation_id:
            item["schema_generation_id"] = generation_id
            if group == "columns" and item.get("column_name"):
                source_qtn = str(item.get("derived_source_qualified_table_name") or "")
                source_col = str(item.get("derived_source_column") or "")
                source_generation = current_generation.get(source_qtn) if source_qtn else None
                source_definition = generation_columns.get((source_generation or "", source_col)) if source_col else None
                if source_definition:
                    for key in ("sql_type", "nullable", "default_value", "description"):
                        if key not in item and key in source_definition:
                            item[key] = source_definition.get(key)
                    item["derived_column_definition_basis"] = "direct_ctas_source_column"
                generation_columns[(generation_id, str(item.get("column_name") or ""))] = dict(item)

    historical_tables: list[dict[str, Any]] = []
    historical_schema_facts: list[dict[str, Any]] = []
    for table in schema.get("tables") or []:
        generation_id = str(table.get("schema_generation_id") or "")
        if generation_id and generation_id not in active_generations:
            snapshot = dict(table)
            snapshot["migration_state"] = "superseded_or_dropped"
            historical_tables.append(snapshot)

    for group in groups:
        normalized: list[dict[str, Any]] = []
        for item in schema.get(group) or []:
            generation_id = str(item.get("schema_generation_id") or "")
            if generation_id and generation_id not in active_generations:
                snapshot = dict(item)
                snapshot["schema_fact_group"] = group
                snapshot["migration_state"] = "superseded_or_dropped"
                historical_schema_facts.append(snapshot)
                continue
            final_qtn = generation_final_qtn.get(generation_id) if generation_id else None
            if final_qtn:
                final_schema, final_table = _sql_identifier_parts(final_qtn)
                original_schema, original_table = _schema_fact_table_identity(group, item)
                original_qtn = _qualified_table_name(original_schema, original_table)
                if final_table and final_qtn != original_qtn:
                    _set_schema_fact_table_identity(group, item, final_schema, final_table)
                    item["renamed_from_qualified_table_name"] = original_qtn
                    item["table_rename_chain"] = list(generation_rename_chain.get(generation_id) or [])
                    _refresh_schema_fact_id(group, item, repo_id)
                item["migration_state"] = "active"
            elif generation_id:
                item["migration_state"] = "active"
            else:
                item.setdefault("migration_state", "unbound_to_observed_create")
            normalized.append(item)
        schema[group] = normalized

    schema["schema_changes"] = sorted(changes, key=_sql_migration_order_key)
    schema["historical_tables"] = sorted(historical_tables, key=_sql_migration_order_key)
    schema["historical_schema_facts"] = sorted(
        historical_schema_facts,
        key=lambda item: (_sql_migration_order_key(item), str(item.get("schema_fact_group") or "")),
    )
    return schema



def _materialize_explicit_partition_tables(
    schema: dict[str, list[dict[str, Any]]], *, repo_id: str,
) -> dict[str, list[dict[str, Any]]]:
    """Publish statically declared PostgreSQL partition children as tables.

    Only direct ``CREATE TABLE ... PARTITION OF ...`` observations are
    materialized. SQL assembled inside strings/procedural bodies remains an
    observation about a dynamic creation mechanism and never becomes an
    invented physical table.
    """
    tables = list(schema.get("tables") or [])
    columns = list(schema.get("columns") or [])
    children = [
        item for item in schema.get("partitioning") or []
        if item.get("partition_fact_kind") == "child_partition"
    ]
    if not children:
        return schema

    parent_tables_by_qtn: dict[str, list[dict[str, Any]]] = {}
    parent_columns_by_qtn: dict[str, list[dict[str, Any]]] = {}
    for table in tables:
        qtn = str(table.get("qualified_table_name") or table.get("table_name") or "")
        if qtn:
            parent_tables_by_qtn.setdefault(qtn, []).append(table)
    for column in columns:
        qtn = str(column.get("qualified_table_name") or column.get("table_name") or "")
        if qtn:
            parent_columns_by_qtn.setdefault(qtn, []).append(column)

    materialized_tables: list[dict[str, Any]] = []
    inherited_columns: list[dict[str, Any]] = []
    for child in children:
        child_name = str(child.get("partition_table_name") or "").strip()
        child_qtn = str(child.get("qualified_partition_table_name") or child_name).strip()
        parent_name = str(child.get("parent_table_name") or child.get("table_name") or "").strip()
        parent_qtn = str(
            child.get("parent_qualified_table_name")
            or child.get("qualified_table_name")
            or parent_name
        ).strip()
        if not child_name or not child_qtn or not parent_name or not parent_qtn:
            continue

        parent_matches = parent_tables_by_qtn.get(parent_qtn) or []
        parent_resolution_status = (
            "observed_exact" if len(parent_matches) == 1
            else "missing_parent_table_fact" if not parent_matches
            else "ambiguous_parent_table_fact"
        )
        parent_table = parent_matches[0] if len(parent_matches) == 1 else None
        child_generation_id = f"sql_partition_generation_{repo_id}_{_hash(child_qtn + '.partition_of.' + parent_qtn)}"
        table = {
            "db_schema_table_id": f"db_schema_table_{repo_id}_{_hash(child_qtn)}",
            "fact_type": "db_schema_table",
            "repo_id": child.get("repo_id"),
            "project_code": child.get("project_code"),
            "system_name": child.get("system_name"),
            "table_name": child_name,
            "normalized_table_name": normalize_name(child_name),
            "schema_name": child.get("partition_schema_name"),
            "qualified_table_name": child_qtn,
            "schema_name_basis": child.get("partition_schema_name_basis"),
            "schema_reference_placeholder": child.get("partition_schema_reference_placeholder"),
            "declared_schema_reference": (
                f"${{{child.get('partition_schema_reference_placeholder')}}}"
                if child.get("partition_schema_reference_placeholder") else None
            ),
            "schema_resolution_status": child.get("schema_resolution_status"),
            "schema_resolution_candidates": list(child.get("schema_resolution_candidates") or []),
            "table_kind": "partition",
            "physical_table_kind": "explicit_partition_child",
            "is_partition": True,
            "partition_parent_table_name": parent_name,
            "partition_parent_schema_name": child.get("parent_schema_name") or child.get("schema_name"),
            "partition_parent_qualified_table_name": parent_qtn,
            "partition_parent_table_id": parent_table.get("db_schema_table_id") if parent_table else None,
            "partition_parent_resolution_status": parent_resolution_status,
            "partition_bound_kind": child.get("partition_bound_kind"),
            "partition_bound_expression": child.get("partition_bound_expression"),
            "tablespace": child.get("tablespace"),
            "schema_generation_id": child_generation_id,
            "parent_schema_generation_id": child.get("schema_generation_id"),
            "migration_state": child.get("migration_state") or "active",
            "source_type": child.get("source_type"),
            "source_scope": child.get("source_scope"),
            "source_scope_basis": child.get("source_scope_basis"),
            "effective_model_included": child.get("effective_model_included", True),
            "file": child.get("file"),
            "line_start": child.get("line_start"),
            "evidence_maturity_level": "confirmed",
            "evidence": list(child.get("evidence") or []),
            "materialization_basis": "direct_postgresql_create_table_partition_of",
        }
        materialized_tables.append({k: v for k, v in table.items() if v is not None})

        if parent_resolution_status != "observed_exact":
            child["partition_parent_resolution_status"] = parent_resolution_status
            child["materialized_partition_table_id"] = table["db_schema_table_id"]
            continue

        inherited_count = 0
        for parent_column in parent_columns_by_qtn.get(parent_qtn) or []:
            column_name = str(parent_column.get("column_name") or "").strip()
            if not column_name:
                continue
            inherited = dict(parent_column)
            inherited.update({
                "db_schema_column_id": f"db_schema_column_{repo_id}_{_hash(child_qtn + '.' + column_name)}",
                "repo_id": child.get("repo_id") or parent_column.get("repo_id"),
                "project_code": child.get("project_code") or parent_column.get("project_code"),
                "system_name": child.get("system_name") or parent_column.get("system_name"),
                "table_name": child_name,
                "schema_name": child.get("partition_schema_name"),
                "qualified_table_name": child_qtn,
                "schema_name_basis": child.get("partition_schema_name_basis"),
                "schema_reference_placeholder": child.get("partition_schema_reference_placeholder"),
                "schema_generation_id": child_generation_id,
                "migration_state": child.get("migration_state") or "active",
                "column_origin": "inherited_from_partition_parent",
                "inherited_from_table_id": parent_table.get("db_schema_table_id"),
                "inherited_from_table_name": parent_name,
                "inherited_from_qualified_table_name": parent_qtn,
                "inherited_from_column_id": parent_column.get("db_schema_column_id"),
                "partition_declaration_file": child.get("file"),
                "partition_declaration_line_start": child.get("line_start"),
                "source_type": "postgres_partition_column_inheritance",
                "file": child.get("file"),
                "line_start": child.get("line_start"),
                "evidence_maturity_level": "confirmed",
                "evidence": [
                    *list(parent_column.get("evidence") or []),
                    *list(child.get("evidence") or []),
                ],
                "materialization_basis": "postgresql_partition_inherits_parent_columns",
            })
            inherited.pop("source_occurrences", None)
            inherited.pop("source_sets", None)
            inherited.pop("has_non_test_source", None)
            inherited_columns.append({k: v for k, v in inherited.items() if v is not None})
            inherited_count += 1
        table["inherited_column_count"] = inherited_count
        # update the already appended copy
        materialized_tables[-1]["inherited_column_count"] = inherited_count
        child["partition_parent_resolution_status"] = parent_resolution_status
        child["materialized_partition_table_id"] = table["db_schema_table_id"]
        child["inherited_column_count"] = inherited_count

    schema["tables"] = _merge_schema_items(tables, materialized_tables, ["schema_name", "table_name"])
    schema["columns"] = _merge_schema_items(columns, inherited_columns, ["schema_name", "table_name", "column_name"])
    return schema

def _top_level_clause_offset(text: str, *, start: int, clauses: tuple[str, ...]) -> int | None:
    depth = 0
    in_single = False
    in_double = False
    i = start
    low = text.lower()
    while i < len(text):
        ch = text[i]
        if in_single:
            if ch == "'":
                if i + 1 < len(text) and text[i + 1] == "'":
                    i += 2
                    continue
                in_single = False
            i += 1
            continue
        if in_double:
            if ch == '"':
                in_double = False
            i += 1
            continue
        if ch == "'":
            in_single = True
            i += 1
            continue
        if ch == '"':
            in_double = True
            i += 1
            continue
        if ch == "(":
            depth += 1
            i += 1
            continue
        if ch == ")":
            depth = max(0, depth - 1)
            i += 1
            continue
        if depth == 0 and (i == 0 or text[i - 1].isspace()):
            for clause in clauses:
                if low.startswith(clause, i):
                    end = i + len(clause)
                    if end == len(text) or text[end].isspace() or text[end] == "(":
                        return i
        i += 1
    return None


def _extract_column_default_value(text: str | None) -> str | None:
    raw = str(text or "")
    match = re.search(r"\bdefault\b", raw, re.IGNORECASE)
    if not match:
        return None
    start = match.end()
    while start < len(raw) and raw[start].isspace():
        start += 1
    end = _top_level_clause_offset(
        raw,
        start=start,
        clauses=("check", "constraint", "not null", "primary key", "unique", "references"),
    )
    value = raw[start:end].strip() if end is not None else raw[start:].strip()
    return value[:240] if value else None


def _extract_check_expression(text: str) -> str | None:
    m = re.search(r"\bcheck\s*\(", text or "", re.IGNORECASE)
    if not m:
        return None
    open_idx = (text or "").find("(", m.start())
    close_idx = _find_matching_paren(text or "", open_idx)
    if open_idx < 0 or close_idx < 0:
        return None
    return " ".join((text or "")[open_idx + 1:close_idx].split())

def _check_literal(value: str) -> dict[str, Any] | None:
    token = value.strip()
    if not token:
        return None
    if len(token) >= 2 and token[0] == token[-1] == "'":
        return {"value": token[1:-1].replace("''", "'"), "literal_kind": "string"}
    low = token.lower()
    if low in {"true", "false"}:
        return {"value": low == "true", "literal_kind": "boolean"}
    if low == "null":
        return {"value": None, "literal_kind": "null"}
    if re.fullmatch(r"[-+]?\d+", token):
        try:
            return {"value": int(token), "literal_kind": "integer"}
        except ValueError:
            pass
    if re.fullmatch(r"[-+]?(?:\d+\.\d*|\d*\.\d+)", token):
        try:
            return {"value": float(token), "literal_kind": "number"}
        except ValueError:
            pass
    return None


def _extract_check_literal_values(expression: str | None) -> list[dict[str, Any]]:
    if not expression:
        return []
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for match in re.finditer(r"\bin\s*\((?P<body>[^()]*)\)", expression, re.IGNORECASE | re.DOTALL):
        for raw in _split_top_level_commas(match.group("body")):
            item = _check_literal(raw)
            if item is None:
                continue
            key = (item["literal_kind"], repr(item.get("value")))
            if key in seen:
                continue
            seen.add(key)
            out.append(item)
    return out


def _extract_sql_table_comments(sql: str) -> tuple[dict[str, str], dict[tuple[str, str], str]]:
    table_comments: dict[str, str] = {}
    column_comments: dict[tuple[str, str], str] = {}
    str_lit = r"'(?P<comment>(?:''|[^'])*)'"
    table_rx = re.compile(
        r"\bcomment\s+on\s+table\s+(?P<table>(?:\$\{[^}]+\}\.)?[A-Za-z0-9_\"]+)\s+is\s+" + str_lit,
        re.IGNORECASE | re.DOTALL,
    )
    col_rx = re.compile(
        r"\bcomment\s+on\s+column\s+(?P<table>(?:\$\{[^}]+\}\.)?[A-Za-z0-9_\"]+)\.(?P<column>[A-Za-z0-9_\"]+)\s+is\s+" + str_lit,
        re.IGNORECASE | re.DOTALL,
    )
    for m in table_rx.finditer(sql):
        table_comments[_clean_sql_identifier(m.group("table")).lower()] = m.group("comment").replace("''", "'")
    for m in col_rx.finditer(sql):
        table = _clean_sql_identifier(m.group("table")).lower()
        col = _clean_sql_identifier(m.group("column")).lower()
        column_comments[(table, col)] = m.group("comment").replace("''", "'")
    return table_comments, column_comments



def _extract_sql_triggers(sql: str, *, repo: Path, path: Path, repo_id: str, project_code: str, system_name: str) -> list[dict[str, Any]]:
    triggers: list[dict[str, Any]] = []
    rel = _rel(repo, path)
    trigger_rx = re.compile(
        r"\bcreate\s+(?:or\s+replace\s+)?trigger\s+(?P<name>[A-Za-z0-9_\".]+)\s+"
        r"(?P<timing>before|after|instead\s+of)\s+(?P<events>.*?)\s+on\s+"
        r"(?P<table>(?:\$\{[^}]+\}\.)?[A-Za-z0-9_\"]+)\s+"
        r"(?P<body>.*?)(?:;|--rollback|\Z)",
        re.IGNORECASE | re.DOTALL,
    )
    for m in trigger_rx.finditer(sql or ""):
        name = _clean_sql_identifier(m.group("name")).lower()
        table_name = _clean_sql_identifier(m.group("table")).lower()
        events_text = " ".join((m.group("events") or "").split()).lower()
        events = [ev for ev in ["insert", "update", "delete", "truncate"] if re.search(rf"\b{ev}\b", events_text)]
        body = m.group("body") or ""
        proc_m = re.search(r"execute\s+(?:function|procedure)\s+(?P<proc>(?:\$\{[^}]+\}\.)?[A-Za-z0-9_\"]+)\s*\(", body, re.IGNORECASE)
        proc = _clean_sql_identifier(proc_m.group("proc")).lower() if proc_m else None
        # Conservative target table extraction from the referenced procedure/function body in the same SQL file.
        target_tables: list[str] = []
        search_region = sql
        if proc:
            base_proc = proc.split(".")[-1]
            fn_m = re.search(r"create\s+(?:or\s+replace\s+)?function\s+(?:\$\{[^}]+\}\.)?" + re.escape(base_proc) + r"\s*\(\).*?(?=create\s+trigger|\Z)", sql or "", re.IGNORECASE | re.DOTALL)
            if fn_m:
                search_region = fn_m.group(0)
        for tm in re.finditer(r"\binsert\s+into\s+(?P<table>(?:\$\{[^}]+\}\.)?[A-Za-z0-9_\"]+)", search_region, re.IGNORECASE):
            t = _clean_sql_identifier(tm.group("table")).lower()
            if t and t not in target_tables:
                target_tables.append(t)
        line = line_number_for_offset(sql, m.start())
        triggers.append({
            "db_schema_trigger_id": f"db_schema_trigger_{repo_id}_{_hash(table_name + '.' + name)}",
            "fact_type": "db_schema_trigger",
            "repo_id": repo_id,
            "project_code": project_code,
            "system_name": system_name,
            "trigger_name": name,
            "source_table": table_name,
            "trigger_timing": " ".join((m.group("timing") or "").split()).lower(),
            "trigger_events": events,
            "procedure_name": proc,
            "target_tables": target_tables,
            "source_type": "liquibase_sql_ddl",
            "file": rel,
            "line_start": line,
            "evidence_maturity_level": "confirmed",
            "evidence": [{"file": rel, "line_start": line, "kind": "sql_create_trigger"}],
        })
    return triggers

def _scan_liquibase_sql_schema(repo: Path, files: list[Path], *, repo_id: str, project_code: str, system_name: str) -> dict[str, list[dict[str, Any]]]:
    """Extract direct schema facts from Liquibase formatted SQL / DDL files.

    This is intentionally conservative. It treats direct CREATE TABLE / CREATE INDEX /
    COMMENT ON statements as physical schema evidence and ignores procedural SQL bodies
    unless they contain those direct DDL forms.
    """
    tables: list[dict[str, Any]] = []
    columns: list[dict[str, Any]] = []
    keys: list[dict[str, Any]] = []
    relationships: list[dict[str, Any]] = []
    indexes: list[dict[str, Any]] = []
    sequences: list[dict[str, Any]] = []
    constraints: list[dict[str, Any]] = []
    partitioning: list[dict[str, Any]] = []
    triggers: list[dict[str, Any]] = []
    schema_changes: list[dict[str, Any]] = []
    historical_tables: list[dict[str, Any]] = []
    sql_files = [p for p in files if p.is_file() and p.suffix.lower() == ".sql"]
    for path in sorted(sql_files):
        file_table_start = len(tables)
        raw = read_text(path)
        sql = _strip_sql_line_comments(raw)
        rel = _rel(repo, path)
        table_comments, column_comments = _extract_sql_table_comments(sql)
        triggers.extend(_extract_sql_triggers(sql, repo=repo, path=path, repo_id=repo_id, project_code=project_code, system_name=system_name))
        partitioning.extend(_extract_sql_child_partitions(
            sql, repo=repo, path=path, repo_id=repo_id, project_code=project_code, system_name=system_name
        ))
        ctas_tables, ctas_columns = _extract_sql_create_table_as_select(
            sql, repo=repo, path=path, repo_id=repo_id, project_code=project_code, system_name=system_name
        )
        tables.extend(ctas_tables)
        columns.extend(ctas_columns)
        for m, table_name_raw, schema_name_raw, body, close_idx in _iter_create_table_blocks(sql):
            if not table_name_raw:
                continue
            table_name = table_name_raw.lower()
            schema_name = schema_name_raw.lower() if schema_name_raw else None
            line = line_number_for_offset(sql, m.start())
            generation_id = f"sql_table_generation_{repo_id}_{_hash(rel + ':' + str(line) + ':' + _qualified_table_name(schema_name, table_name))}"
            table = {
                "db_schema_table_id": f"db_schema_table_{repo_id}_{_hash(_qualified_table_name(schema_name, table_name))}",
                "fact_type": "db_schema_table",
                "repo_id": repo_id,
                "project_code": project_code,
                "system_name": system_name,
                "table_name": table_name,
                "normalized_table_name": normalize_name(table_name),
                "schema_name": schema_name,
                "schema_name_basis": _sql_schema_reference_basis(m.group("table")) or ("explicit_sql_schema" if schema_name else None),
                "schema_reference_placeholder": (schema_name if _sql_schema_reference_basis(m.group("table")) == "placeholder_reference" else None),
                "description": table_comments.get(table_name),
                "table_creation_kind": "create_table",
                "schema_generation_id": generation_id,
                "source_type": "liquibase_sql_ddl",
                "file": rel,
                "line_start": line,
                "evidence_maturity_level": "confirmed",
                "evidence": [{"file": rel, "line_start": line, "kind": "sql_create_table"}],
            }
            tables.append(table)
            child_starts = {
                "columns": len(columns),
                "keys": len(keys),
                "relationships": len(relationships),
                "constraints": len(constraints),
                "partitioning": len(partitioning),
            }
            tail = sql[close_idx + 1: sql.find(";", close_idx) if sql.find(";", close_idx) != -1 else min(len(sql), close_idx + 500)]
            part_m = re.search(r"\bpartition\s+by\s+(?P<strategy>[A-Za-z0-9_]+)\s*\((?P<cols>[^)]*)\)", tail, re.IGNORECASE | re.DOTALL)
            if part_m:
                part_line = line_number_for_offset(sql, close_idx + 1 + part_m.start())
                partitioning.append({
                    "db_schema_partitioning_id": f"db_schema_partitioning_{repo_id}_{_hash(_qualified_table_name(schema_name, table_name) + '.partitioning')}",
                    "fact_type": "db_schema_partitioning",
                    "partition_fact_kind": "parent_partitioning",
                    "repo_id": repo_id,
                    "project_code": project_code,
                    "system_name": system_name,
                    "table_name": table_name,
                    "partition_strategy": part_m.group("strategy").lower(),
                    "partition_columns": _sql_column_list(part_m.group("cols")),
                    "source_type": "liquibase_sql_ddl",
                    "file": rel,
                    "line_start": part_line,
                    "evidence_maturity_level": "confirmed",
                    "evidence": [{"file": rel, "line_start": part_line, "kind": "sql_partition_by"}],
                })
            for part in _split_top_level_commas(body):
                part_clean = " ".join(part.strip().split())
                part_lower = part_clean.lower()
                constraint_name: str | None = None
                cons_m = re.match(r"constraint\s+(?P<name>[A-Za-z0-9_\"]+)\s+(?P<body>.*)$", part_clean, re.IGNORECASE | re.DOTALL)
                cons_body = part_clean
                if cons_m:
                    constraint_name = _clean_sql_identifier(cons_m.group("name")).lower()
                    cons_body = cons_m.group("body").strip()
                    part_lower = cons_body.lower()
                pk_m = re.search(r"\bprimary\s+key\s*\((?P<cols>[^)]*)\)", cons_body, re.IGNORECASE | re.DOTALL)
                if pk_m:
                    cols = _sql_column_list(pk_m.group("cols"))
                    name = constraint_name or f"pk_{table_name}"
                    keys.append({
                        "db_schema_key_id": f"db_schema_key_{repo_id}_{_hash(table_name + '.' + name)}",
                        "fact_type": "db_schema_key",
                        "repo_id": repo_id,
                        "project_code": project_code,
                        "system_name": system_name,
                        "constraint_name": name,
                        "constraint_kind": "primary_key",
                        "table_name": table_name,
                        "columns": cols,
                        "source_type": "liquibase_sql_ddl",
                        "file": rel,
                        "line_start": line_number_for_offset(sql, sql.find(part, m.start())),
                        "evidence_maturity_level": "confirmed",
                        "evidence": [{"file": rel, "line_start": line_number_for_offset(sql, sql.find(part, m.start())), "kind": "sql_primary_key"}],
                    })
                    continue
                uq_m = re.search(r"\bunique\s*\((?P<cols>[^)]*)\)", cons_body, re.IGNORECASE | re.DOTALL)
                if uq_m:
                    cols = _sql_column_list(uq_m.group("cols"))
                    name = constraint_name or f"uk_{table_name}_{'_'.join(cols)}"
                    keys.append({
                        "db_schema_key_id": f"db_schema_key_{repo_id}_{_hash(table_name + '.' + name)}",
                        "fact_type": "db_schema_key",
                        "repo_id": repo_id,
                        "project_code": project_code,
                        "system_name": system_name,
                        "constraint_name": name,
                        "constraint_kind": "unique_key",
                        "table_name": table_name,
                        "columns": cols,
                        "source_type": "liquibase_sql_ddl",
                        "file": rel,
                        "line_start": line_number_for_offset(sql, sql.find(part, m.start())),
                        "evidence_maturity_level": "confirmed",
                        "evidence": [{"file": rel, "line_start": line_number_for_offset(sql, sql.find(part, m.start())), "kind": "sql_unique_key"}],
                    })
                    continue
                fk_m = re.search(
                    r"\bforeign\s+key\s*\((?P<src>[^)]*)\)\s*references\s+(?P<tgt>(?:\$\{[^}]+\}\.)?[A-Za-z0-9_\"]+)(?:\s*\((?P<tgt_cols>[^)]*)\))?",
                    cons_body,
                    re.IGNORECASE | re.DOTALL,
                )
                if fk_m:
                    src_cols = _sql_column_list(fk_m.group("src"))
                    target_schema, target_table = _sql_identifier_parts(fk_m.group("tgt"))
                    target_schema = target_schema.lower() if target_schema else None
                    target_table = target_table.lower()
                    tgt_cols = _sql_column_list(fk_m.group("tgt_cols"))
                    name = constraint_name or f"fk_{table_name}_{'_'.join(src_cols)}"
                    relationships.append({
                        "db_schema_relationship_id": f"db_schema_relationship_{repo_id}_{_hash(table_name + '.' + name)}",
                        "fact_type": "db_schema_relationship",
                        "repo_id": repo_id,
                        "project_code": project_code,
                        "system_name": system_name,
                        "constraint_name": name,
                        "relationship_kind": "foreign_key",
                        "source_table": table_name,
                        "source_columns": src_cols,
                        "target_table": target_table,
                        "target_schema": target_schema,
                        "target_columns": tgt_cols,
                        "target_columns_declared": bool(tgt_cols),
                        "source_type": "liquibase_sql_ddl",
                        "file": rel,
                        "line_start": line_number_for_offset(sql, sql.find(part, m.start())),
                        "evidence_maturity_level": "confirmed",
                        "evidence": [{"file": rel, "line_start": line_number_for_offset(sql, sql.find(part, m.start())), "kind": "sql_foreign_key"}],
                    })
                    continue
                check_expr = _extract_check_expression(cons_body)
                if check_expr and (constraint_name or part_lower.startswith("check ")):
                    name = constraint_name or f"ck_{table_name}_{len(constraints)+1:04d}"
                    check_line = line_number_for_offset(sql, sql.find(part, m.start()))
                    constraints.append({
                        "db_schema_constraint_id": f"db_schema_constraint_{repo_id}_{_hash(table_name + '.' + name)}",
                        "fact_type": "db_schema_constraint",
                        "repo_id": repo_id,
                        "project_code": project_code,
                        "system_name": system_name,
                        "constraint_name": name,
                        "constraint_kind": "check",
                        "table_name": table_name,
                        "expression": check_expr,
                        "literal_values": _extract_check_literal_values(check_expr),
                        "source_type": "liquibase_sql_ddl",
                        "file": rel,
                        "line_start": check_line,
                        "evidence_maturity_level": "confirmed",
                        "evidence": [{"file": rel, "line_start": check_line, "kind": "sql_check_constraint"}],
                    })
                    continue
                if part_lower.startswith(("constraint ", "primary key", "foreign key", "unique", "check ")):
                    continue
                col_m = re.match(r"(?P<name>[A-Za-z0-9_\"]+)\s+(?P<rest>.+)$", part_clean, re.IGNORECASE | re.DOTALL)
                if not col_m:
                    continue
                col_name = _clean_sql_identifier(col_m.group("name")).lower()
                if not col_name or col_name in {"constraint", "primary", "foreign", "unique", "check"}:
                    continue
                rest = col_m.group("rest")
                type_match = re.match(r"(?P<type>.*?)(?:\s+not\s+null|\s+null\b|\s+default\b|\s+constraint\b|\s+primary\s+key\b|\s+references\b|$)", rest, re.IGNORECASE | re.DOTALL)
                sql_type = " ".join((type_match.group("type") if type_match else rest).split())
                default_m = re.search(r"\bdefault\s+(?P<default>.*?)(?:\s+constraint\b|\s+not\s+null\b|\s+null\b|$)", rest, re.IGNORECASE | re.DOTALL)
                col_line = line_number_for_offset(sql, sql.find(part, m.start()))
                columns.append({
                    "db_schema_column_id": f"db_schema_column_{repo_id}_{_hash(table_name + '.' + col_name)}",
                    "fact_type": "db_schema_column",
                    "repo_id": repo_id,
                    "project_code": project_code,
                    "system_name": system_name,
                    "table_name": table_name,
                    "normalized_table_name": normalize_name(table_name),
                    "column_name": col_name,
                    "normalized_column_name": normalize_name(col_name),
                    "sql_type": sql_type or "unknown",
                    "nullable": False if re.search(r"\bnot\s+null\b", rest, re.IGNORECASE) else None,
                    "default_value": (default_m.group("default").strip()[:240] if default_m else None),
                    "description": column_comments.get((table_name, col_name)),
                    "source_type": "liquibase_sql_ddl",
                    "file": rel,
                    "line_start": col_line,
                    "evidence_maturity_level": "confirmed",
                    "evidence": [{"file": rel, "line_start": col_line, "kind": "sql_column_definition"}],
                })
                if re.search(r"\bprimary\s+key\b", rest, re.IGNORECASE):
                    name = f"pk_{table_name}"
                    keys.append({
                        "db_schema_key_id": f"db_schema_key_{repo_id}_{_hash(table_name + '.' + name)}",
                        "fact_type": "db_schema_key",
                        "repo_id": repo_id,
                        "project_code": project_code,
                        "system_name": system_name,
                        "constraint_name": name,
                        "constraint_kind": "primary_key",
                        "table_name": table_name,
                        "columns": [col_name],
                        "source_type": "liquibase_sql_ddl",
                        "file": rel,
                        "line_start": col_line,
                        "evidence_maturity_level": "confirmed",
                        "evidence": [{"file": rel, "line_start": col_line, "kind": "sql_inline_primary_key"}],
                    })
                elif re.search(r"\bunique\b", rest, re.IGNORECASE):
                    name = f"uk_{table_name}_{col_name}"
                    keys.append({
                        "db_schema_key_id": f"db_schema_key_{repo_id}_{_hash(table_name + '.' + name)}",
                        "fact_type": "db_schema_key",
                        "repo_id": repo_id,
                        "project_code": project_code,
                        "system_name": system_name,
                        "constraint_name": name,
                        "constraint_kind": "unique_key",
                        "table_name": table_name,
                        "columns": [col_name],
                        "source_type": "liquibase_sql_ddl",
                        "file": rel,
                        "line_start": col_line,
                        "evidence_maturity_level": "confirmed",
                        "evidence": [{"file": rel, "line_start": col_line, "kind": "sql_inline_unique_key"}],
                    })
                inline_fk_m = re.search(r"\breferences\s+(?P<tgt>(?:\$\{[^}]+\}\.)?[A-Za-z0-9_\"]+)(?:\s*\((?P<tgt_cols>[^)]*)\))?", rest, re.IGNORECASE | re.DOTALL)
                if inline_fk_m:
                    target_schema, target_table = _sql_identifier_parts(inline_fk_m.group("tgt"))
                    target_schema = target_schema.lower() if target_schema else None
                    target_table = target_table.lower()
                    tgt_cols = _sql_column_list(inline_fk_m.group("tgt_cols"))
                    name = f"fk_{table_name}_{col_name}"
                    relationships.append({
                        "db_schema_relationship_id": f"db_schema_relationship_{repo_id}_{_hash(table_name + '.' + name)}",
                        "fact_type": "db_schema_relationship",
                        "repo_id": repo_id,
                        "project_code": project_code,
                        "system_name": system_name,
                        "constraint_name": name,
                        "relationship_kind": "foreign_key",
                        "source_table": table_name,
                        "source_columns": [col_name],
                        "target_table": target_table,
                        "target_schema": target_schema,
                        "target_columns": tgt_cols,
                        "target_columns_declared": bool(tgt_cols),
                        "source_type": "liquibase_sql_ddl",
                        "file": rel,
                        "line_start": col_line,
                        "evidence_maturity_level": "confirmed",
                        "evidence": [{"file": rel, "line_start": col_line, "kind": "sql_inline_foreign_key"}],
                    })
                inline_check_expr = _extract_check_expression(rest)
                if inline_check_expr:
                    name = f"ck_{table_name}_{col_name}"
                    constraints.append({
                        "db_schema_constraint_id": f"db_schema_constraint_{repo_id}_{_hash(table_name + '.' + name)}",
                        "fact_type": "db_schema_constraint",
                        "repo_id": repo_id,
                        "project_code": project_code,
                        "system_name": system_name,
                        "constraint_name": name,
                        "constraint_kind": "check",
                        "table_name": table_name,
                        "column_name": col_name,
                        "expression": inline_check_expr,
                        "literal_values": _extract_check_literal_values(inline_check_expr),
                        "source_type": "liquibase_sql_ddl",
                        "file": rel,
                        "line_start": col_line,
                        "evidence_maturity_level": "confirmed",
                        "evidence": [{"file": rel, "line_start": col_line, "kind": "sql_inline_check_constraint"}],
                    })
            table_schema_basis = _sql_schema_reference_basis(m.group("table")) or ("explicit_sql_schema" if schema_name else None)
            table_schema_placeholder = schema_name if table_schema_basis == "placeholder_reference" else None
            for child in columns[child_starts["columns"]:]:
                child.setdefault("schema_name", schema_name)
                child.setdefault("schema_name_basis", table_schema_basis)
                child.setdefault("schema_reference_placeholder", table_schema_placeholder)
            for child in keys[child_starts["keys"]:]:
                child.setdefault("schema_name", schema_name)
                child.setdefault("schema_name_basis", table_schema_basis)
                child.setdefault("schema_reference_placeholder", table_schema_placeholder)
            for child in constraints[child_starts["constraints"]:]:
                child.setdefault("schema_name", schema_name)
                child.setdefault("schema_name_basis", table_schema_basis)
                child.setdefault("schema_reference_placeholder", table_schema_placeholder)
            for child in partitioning[child_starts["partitioning"]:]:
                child.setdefault("schema_name", schema_name)
                child.setdefault("schema_name_basis", table_schema_basis)
                child.setdefault("schema_reference_placeholder", table_schema_placeholder)
            for child in relationships[child_starts["relationships"]:]:
                child.setdefault("source_schema", schema_name)
                child.setdefault("source_schema_name_basis", table_schema_basis)
                child.setdefault("source_schema_reference_placeholder", table_schema_placeholder)
        seq_rx = re.compile(
            r"\bcreate\s+sequence\s+(?:if\s+not\s+exists\s+)?(?P<name>(?:(?:\$\{[^}]+\}|[A-Za-z0-9_\"]+)\.)?[A-Za-z0-9_\"]+)\b(?P<body>.*?)(?=;|\bcreate\b|\balter\b|\bcomment\b|$)",
            re.IGNORECASE | re.DOTALL,
        )
        for sm in seq_rx.finditer(sql):
            seq_name = _clean_sql_identifier(sm.group("name")).lower()
            line = line_number_for_offset(sql, sm.start())
            body = " ".join((sm.group("body") or "").split())
            sequences.append({
                "db_schema_sequence_id": f"db_schema_sequence_{repo_id}_{_hash(seq_name)}",
                "fact_type": "db_schema_sequence",
                "repo_id": repo_id,
                "project_code": project_code,
                "system_name": system_name,
                "sequence_name": seq_name,
                "normalized_sequence_name": normalize_name(seq_name),
                "definition_tail": body[:500] or None,
                "source_type": "liquibase_sql_ddl",
                "file": rel,
                "line_start": line,
                "evidence_maturity_level": "confirmed",
                "evidence": [{"file": rel, "line_start": line, "kind": "sql_create_sequence"}],
            })

        alter_add_column_rx = re.compile(
            r"\balter\s+table\s+(?P<table>(?:(?:\$\{[^}]+\}|[A-Za-z0-9_\"]+)\.)?[A-Za-z0-9_\"]+)\s+add\s+(?!(?:constraint|primary\s+key|unique|foreign\s+key|check)\b)(?:column\s+)?(?:if\s+not\s+exists\s+)?(?P<column>[A-Za-z0-9_\"]+)\s+(?P<rest>.*?)(?=;|$)",
            re.IGNORECASE | re.DOTALL,
        )
        for am in alter_add_column_rx.finditer(sql):
            schema_name, table_name = _sql_identifier_parts(am.group("table"))
            schema_name = schema_name.lower() if schema_name else None
            table_name = table_name.lower()
            col_name = _clean_sql_identifier(am.group("column")).lower()
            rest = " ".join((am.group("rest") or "").split())
            if not table_name or not col_name:
                continue
            type_match = re.match(r"(?P<type>.*?)(?:\s+not\s+null|\s+null\b|\s+default\b|\s+check\b|$)", rest, re.IGNORECASE | re.DOTALL)
            default_value = _extract_column_default_value(rest)
            check_expr = _extract_check_expression(rest)
            line = line_number_for_offset(sql, am.start())
            schema_basis = _sql_schema_reference_basis(am.group("table"))
            columns.append({
                "db_schema_column_id": f"db_schema_column_{repo_id}_{_hash(table_name + '.' + col_name)}",
                "fact_type": "db_schema_column",
                "repo_id": repo_id,
                "project_code": project_code,
                "system_name": system_name,
                "table_name": table_name,
                "schema_name": schema_name,
                "normalized_table_name": normalize_name(table_name),
                "column_name": col_name,
                "normalized_column_name": normalize_name(col_name),
                "sql_type": " ".join((type_match.group("type") if type_match else rest).split()) or "unknown",
                "nullable": False if re.search(r"\bnot\s+null\b", rest, re.IGNORECASE) else None,
                "default_value": default_value,
                "schema_name_basis": schema_basis,
                "source_type": "liquibase_sql_ddl",
                "file": rel,
                "line_start": line,
                "evidence_maturity_level": "confirmed",
                "evidence": [{"file": rel, "line_start": line, "kind": "sql_alter_table_add_column"}],
            })
            if check_expr:
                constraint_name = f"ck_{table_name}_{col_name}"
                constraints.append({
                    "db_schema_constraint_id": f"db_schema_constraint_{repo_id}_{_hash(_qualified_table_name(schema_name, table_name) + '.' + constraint_name)}",
                    "fact_type": "db_schema_constraint",
                    "repo_id": repo_id,
                    "project_code": project_code,
                    "system_name": system_name,
                    "constraint_name": constraint_name,
                    "constraint_name_basis": "generated_from_inline_column_check",
                    "constraint_kind": "check",
                    "table_name": table_name,
                    "schema_name": schema_name,
                    "schema_name_basis": schema_basis,
                    "columns": [col_name],
                    "expression": check_expr,
                    "literal_values": _extract_check_literal_values(check_expr),
                    "source_type": "liquibase_sql_ddl",
                    "file": rel,
                    "line_start": line,
                    "evidence_maturity_level": "confirmed",
                    "evidence": [{"file": rel, "line_start": line, "kind": "sql_alter_table_add_column_check"}],
                })

        alter_column_state_rx = re.compile(
            r"\balter\s+table\s+(?P<table>(?:(?:\$\{[^}]+\}|[A-Za-z0-9_\"]+)\.)?[A-Za-z0-9_\"]+)\s+"
            r"alter\s+(?:column\s+)?(?P<column>[A-Za-z0-9_\"]+)\s+"
            r"(?P<operation>set\s+default\s+.*?|drop\s+default|set\s+not\s+null|drop\s+not\s+null)(?=;|$)",
            re.IGNORECASE | re.DOTALL,
        )
        for state_m in alter_column_state_rx.finditer(sql):
            schema_name, table_name = _sql_identifier_parts(state_m.group("table"))
            schema_name = schema_name.lower() if schema_name else None
            table_name = table_name.lower()
            column_name = _clean_sql_identifier(state_m.group("column")).lower()
            operation = " ".join((state_m.group("operation") or "").split())
            operation_lower = operation.lower()
            line = line_number_for_offset(sql, state_m.start())
            item = {
                "db_schema_column_id": f"db_schema_column_{repo_id}_{_hash(_qualified_table_name(schema_name, table_name) + '.' + column_name)}",
                "fact_type": "db_schema_column",
                "repo_id": repo_id,
                "project_code": project_code,
                "system_name": system_name,
                "table_name": table_name,
                "schema_name": schema_name,
                "normalized_table_name": normalize_name(table_name),
                "column_name": column_name,
                "normalized_column_name": normalize_name(column_name),
                "schema_change_kind": "alter_column_state",
                "source_type": "liquibase_sql_ddl",
                "file": rel,
                "line_start": line,
                "evidence_maturity_level": "confirmed",
                "evidence": [{"file": rel, "line_start": line, "kind": "sql_alter_column_state"}],
            }
            if operation_lower.startswith("set default"):
                item["default_value"] = operation[len("set default"):].strip()[:240]
                item["default_state"] = "set"
            elif operation_lower == "drop default":
                item["default_value"] = None
                item["default_state"] = "dropped"
            elif operation_lower == "set not null":
                item["nullable"] = False
                item["nullable_state"] = "not_null"
            elif operation_lower == "drop not null":
                item["nullable"] = True
                item["nullable_state"] = "nullable"
            columns.append(item)

        alter_add_unnamed_constraint_rx = re.compile(
            r"\balter\s+table\s+(?P<table>(?:(?:\$\{[^}]+\}|[A-Za-z0-9_\"]+)\.)?[A-Za-z0-9_\"]+)\s+add\s+"
            r"(?P<body>(?:primary\s+key|unique|foreign\s+key|check)\b.*?)(?=;|$)",
            re.IGNORECASE | re.DOTALL,
        )
        for acm in alter_add_unnamed_constraint_rx.finditer(sql):
            schema_name, table_name = _sql_identifier_parts(acm.group("table"))
            schema_name = schema_name.lower() if schema_name else None
            table_name = table_name.lower()
            body = " ".join((acm.group("body") or "").split())
            line = line_number_for_offset(sql, acm.start())
            pk_m = re.search(r"\bprimary\s+key\s*\((?P<cols>[^)]*)\)", body, re.IGNORECASE | re.DOTALL)
            uq_m = re.search(r"\bunique\s*\((?P<cols>[^)]*)\)", body, re.IGNORECASE | re.DOTALL)
            fk_m = re.search(
                r"\bforeign\s+key\s*\((?P<src>[^)]*)\)\s*references\s+"
                r"(?P<tgt>(?:(?:\$\{[^}]+\}|[A-Za-z0-9_\"]+)\.)?[A-Za-z0-9_\"]+)"
                r"(?:\s*\((?P<tgt_cols>[^)]*)\))?",
                body,
                re.IGNORECASE | re.DOTALL,
            )
            check_expr = _extract_check_expression(body)
            if pk_m or uq_m:
                cols = _sql_column_list((pk_m or uq_m).group("cols"))
                kind = "primary_key" if pk_m else "unique_key"
                prefix = "pk" if pk_m else "uk"
                name = f"{prefix}_{table_name}_{'_'.join(cols)}"
                keys.append({
                    "db_schema_key_id": f"db_schema_key_{repo_id}_{_hash(table_name + '.' + name)}",
                    "fact_type": "db_schema_key",
                    "repo_id": repo_id,
                    "project_code": project_code,
                    "system_name": system_name,
                    "constraint_name": name,
                    "constraint_name_basis": "generated_from_unnamed_declaration",
                    "constraint_kind": kind,
                    "table_name": table_name,
                    "schema_name": schema_name,
                    "schema_name_basis": _sql_schema_reference_basis(acm.group("table")),
                    "columns": cols,
                    "source_type": "liquibase_sql_ddl",
                    "file": rel,
                    "line_start": line,
                    "evidence_maturity_level": "confirmed",
                    "evidence": [{"file": rel, "line_start": line, "kind": "sql_alter_table_add_unnamed_constraint"}],
                })
            elif fk_m:
                src_cols = _sql_column_list(fk_m.group("src"))
                target_schema, target_table = _sql_identifier_parts(fk_m.group("tgt"))
                target_schema = target_schema.lower() if target_schema else None
                target_table = target_table.lower()
                target_columns = _sql_column_list(fk_m.group("tgt_cols"))
                name = f"fk_{table_name}_{'_'.join(src_cols)}"
                relationships.append({
                    "db_schema_relationship_id": f"db_schema_relationship_{repo_id}_{_hash(table_name + '.' + name)}",
                    "fact_type": "db_schema_relationship",
                    "repo_id": repo_id,
                    "project_code": project_code,
                    "system_name": system_name,
                    "constraint_name": name,
                    "constraint_name_basis": "generated_from_unnamed_declaration",
                    "relationship_kind": "foreign_key",
                    "source_table": table_name,
                    "source_schema": schema_name,
                    "source_columns": src_cols,
                    "target_table": target_table,
                    "target_schema": target_schema,
                    "target_columns": target_columns,
                    "target_columns_declared": bool(target_columns),
                    "source_type": "liquibase_sql_ddl",
                    "file": rel,
                    "line_start": line,
                    "evidence_maturity_level": "confirmed",
                    "evidence": [{"file": rel, "line_start": line, "kind": "sql_alter_table_add_unnamed_foreign_key"}],
                })
            elif check_expr:
                name = f"ck_{table_name}_{len(constraints)+1:04d}"
                constraints.append({
                    "db_schema_constraint_id": f"db_schema_constraint_{repo_id}_{_hash(table_name + '.' + name)}",
                    "fact_type": "db_schema_constraint",
                    "repo_id": repo_id,
                    "project_code": project_code,
                    "system_name": system_name,
                    "constraint_name": name,
                    "constraint_name_basis": "generated_from_unnamed_declaration",
                    "constraint_kind": "check",
                    "table_name": table_name,
                    "schema_name": schema_name,
                    "expression": check_expr,
                    "literal_values": _extract_check_literal_values(check_expr),
                    "source_type": "liquibase_sql_ddl",
                    "file": rel,
                    "line_start": line,
                    "evidence_maturity_level": "confirmed",
                    "evidence": [{"file": rel, "line_start": line, "kind": "sql_alter_table_add_unnamed_check"}],
                })

        alter_add_constraint_rx = re.compile(
            r"\balter\s+table\s+(?P<table>(?:(?:\$\{[^}]+\}|[A-Za-z0-9_\"]+)\.)?[A-Za-z0-9_\"]+)\s+add\s+constraint\s+(?P<name>[A-Za-z0-9_\"]+)\s+(?P<body>.*?)(?=;|$)",
            re.IGNORECASE | re.DOTALL,
        )
        for acm in alter_add_constraint_rx.finditer(sql):
            schema_name, table_name = _sql_identifier_parts(acm.group("table"))
            schema_name = schema_name.lower() if schema_name else None
            table_name = table_name.lower()
            name = _clean_sql_identifier(acm.group("name")).lower()
            body = " ".join((acm.group("body") or "").split())
            line = line_number_for_offset(sql, acm.start())
            pk_m = re.search(r"\bprimary\s+key\s*\((?P<cols>[^)]*)\)", body, re.IGNORECASE | re.DOTALL)
            uq_m = re.search(r"\bunique\s*\((?P<cols>[^)]*)\)", body, re.IGNORECASE | re.DOTALL)
            fk_m = re.search(r"\bforeign\s+key\s*\((?P<src>[^)]*)\)\s*references\s+(?P<tgt>(?:(?:\$\{[^}]+\}|[A-Za-z0-9_\"]+)\.)?[A-Za-z0-9_\"]+)(?:\s*\((?P<tgt_cols>[^)]*)\))?", body, re.IGNORECASE | re.DOTALL)
            check_expr = _extract_check_expression(body)
            if pk_m or uq_m:
                cols = _sql_column_list((pk_m or uq_m).group("cols"))
                kind = "primary_key" if pk_m else "unique_key"
                keys.append({
                    "db_schema_key_id": f"db_schema_key_{repo_id}_{_hash(table_name + '.' + name)}",
                    "fact_type": "db_schema_key",
                    "repo_id": repo_id,
                    "project_code": project_code,
                    "system_name": system_name,
                    "constraint_name": name,
                    "constraint_kind": kind,
                    "table_name": table_name,
                    "schema_name": schema_name,
                    "schema_name_basis": _sql_schema_reference_basis(acm.group("table")),
                    "columns": cols,
                    "source_type": "liquibase_sql_ddl",
                    "file": rel,
                    "line_start": line,
                    "evidence_maturity_level": "confirmed",
                    "evidence": [{"file": rel, "line_start": line, "kind": "sql_alter_table_add_constraint"}],
                })
            elif fk_m:
                src_cols = _sql_column_list(fk_m.group("src"))
                target_schema, target_table = _sql_identifier_parts(fk_m.group("tgt"))
                target_schema = target_schema.lower() if target_schema else None
                target_table = target_table.lower()
                relationships.append({
                    "db_schema_relationship_id": f"db_schema_relationship_{repo_id}_{_hash(table_name + '.' + name)}",
                    "fact_type": "db_schema_relationship",
                    "repo_id": repo_id,
                    "project_code": project_code,
                    "system_name": system_name,
                    "constraint_name": name,
                    "relationship_kind": "foreign_key",
                    "source_table": table_name,
                    "source_schema": schema_name,
                    "source_columns": src_cols,
                    "target_table": target_table,
                    "target_schema": target_schema,
                    "target_columns": _sql_column_list(fk_m.group("tgt_cols")),
                    "target_columns_declared": bool(_sql_column_list(fk_m.group("tgt_cols"))),
                    "source_type": "liquibase_sql_ddl",
                    "file": rel,
                    "line_start": line,
                    "evidence_maturity_level": "confirmed",
                    "evidence": [{"file": rel, "line_start": line, "kind": "sql_alter_table_add_foreign_key"}],
                })
            elif check_expr:
                constraints.append({
                    "db_schema_constraint_id": f"db_schema_constraint_{repo_id}_{_hash(table_name + '.' + name)}",
                    "fact_type": "db_schema_constraint",
                    "repo_id": repo_id,
                    "project_code": project_code,
                    "system_name": system_name,
                    "constraint_name": name,
                    "constraint_kind": "check",
                    "table_name": table_name,
                    "schema_name": schema_name,
                    "expression": check_expr,
                    "literal_values": _extract_check_literal_values(check_expr),
                    "source_type": "liquibase_sql_ddl",
                    "file": rel,
                    "line_start": line,
                    "evidence_maturity_level": "confirmed",
                    "evidence": [{"file": rel, "line_start": line, "kind": "sql_alter_table_add_check"}],
                })

        idx_rx = re.compile(
            r"\bcreate\s+(?P<unique>unique\s+)?index\s+(?:if\s+not\s+exists\s+)?(?P<name>[A-Za-z0-9_\"]+)\s+on\s+(?P<table>(?:\$\{[^}]+\}\.)?[A-Za-z0-9_\"]+)\s*\((?P<cols>[^;)]*(?:\([^)]*\)[^;)]*)*)\)",
            re.IGNORECASE | re.DOTALL,
        )
        for m in idx_rx.finditer(sql):
            schema_name, table_name = _sql_identifier_parts(m.group("table"))
            schema_name = schema_name.lower() if schema_name else None
            table_name = table_name.lower()
            idx_name = _clean_sql_identifier(m.group("name")).lower()
            line = line_number_for_offset(sql, m.start())
            indexes.append({
                "db_schema_index_id": f"db_schema_index_{repo_id}_{_hash(table_name + '.' + idx_name)}",
                "fact_type": "db_schema_index",
                "repo_id": repo_id,
                "project_code": project_code,
                "system_name": system_name,
                "index_name": idx_name,
                "table_name": table_name,
                "schema_name": schema_name,
                "schema_name_basis": _sql_schema_reference_basis(m.group("table")),
                "columns": _sql_column_list(m.group("cols")),
                "unique": bool(m.group("unique")),
                "source_type": "liquibase_sql_ddl",
                "file": rel,
                "line_start": line,
                "evidence_maturity_level": "confirmed",
                "evidence": [{"file": rel, "line_start": line, "kind": "sql_create_index"}],
            })
        schema_changes.extend(_extract_sql_table_lifecycle_events(
            sql, repo=repo, path=path, repo_id=repo_id, project_code=project_code, system_name=system_name,
            created_tables=tables[file_table_start:],
        ))

    schema_resolution_observations = _scan_schema_resolution_observations(repo, files)
    observed_schema = {
        "tables": tables,
        "columns": columns,
        "keys": keys,
        "relationships": relationships,
        "indexes": indexes,
        "sequences": sequences,
        "constraints": constraints,
        "partitioning": partitioning,
        "triggers": triggers,
        "schema_changes": schema_changes,
        "historical_tables": historical_tables,
    }
    _resolve_sql_schema_identities(repo, observed_schema, schema_resolution_observations, repo_id=repo_id)
    effective_schema, excluded_facts, excluded_changes, scope_summary = _split_sql_effective_schema(
        repo, observed_schema
    )
    normalized = _normalize_sql_migration_state(repo, effective_schema, repo_id=repo_id)
    normalized = _materialize_explicit_partition_tables(normalized, repo_id=repo_id)
    normalized["excluded_schema_facts"] = sorted(
        excluded_facts,
        key=lambda item: (str(item.get("file") or ""), int(item.get("line_start") or 0), str(item.get("schema_fact_group") or "")),
    )
    normalized["excluded_schema_changes"] = sorted(excluded_changes, key=_sql_migration_order_key)
    normalized["sql_source_scope_summary"] = scope_summary
    normalized["schema_resolution_observations"] = schema_resolution_observations
    return normalized


def _yaml_changesets(data: Any) -> list[dict[str, Any]]:
    if not isinstance(data, dict):
        return []
    out: list[dict[str, Any]] = []
    for entry in data.get('databaseChangeLog') or []:
        if not isinstance(entry, dict):
            continue
        cs = entry.get('changeSet')
        if isinstance(cs, dict):
            out.append(cs)
    return out


def _yaml_columns(change: dict[str, Any]) -> list[dict[str, Any]]:
    cols: list[dict[str, Any]] = []
    for item in change.get('columns') or []:
        if isinstance(item, dict) and isinstance(item.get('column'), dict):
            cols.append(item['column'])
    return cols


def _yaml_constraint_bool(col: dict[str, Any], name: str) -> bool | None:
    cons = col.get('constraints')
    if not isinstance(cons, dict) or name not in cons:
        return None
    return bool(cons.get(name))


def _yaml_declared_value(column: dict[str, Any]) -> tuple[Any, str | None]:
    for key in (
        'value', 'valueNumeric', 'valueBoolean', 'valueDate', 'valueComputed',
        'valueBlobFile', 'valueClobFile', 'valueSequenceNext', 'valueSequenceCurrent',
    ):
        if key in column:
            return column.get(key), key
    return None, None


def _scan_liquibase_yaml_schema(repo: Path, files: list[Path], *, repo_id: str, project_code: str, system_name: str) -> dict[str, list[dict[str, Any]]]:
    tables: list[dict[str, Any]] = []
    columns: list[dict[str, Any]] = []
    keys: list[dict[str, Any]] = []
    relationships: list[dict[str, Any]] = []
    indexes: list[dict[str, Any]] = []
    constraints: list[dict[str, Any]] = []
    literal_data_writes: list[dict[str, Any]] = []
    if yaml is None:
        return {'tables': tables, 'columns': columns, 'keys': keys, 'relationships': relationships, 'indexes': indexes, 'constraints': constraints, 'literal_data_writes': literal_data_writes}
    yaml_files = [p for p in files if p.is_file() and p.suffix.lower() in {'.yaml', '.yml'}]
    for path in sorted(yaml_files):
        raw = read_text(path)
        if 'databaseChangeLog' not in raw:
            continue
        try:
            data = yaml.safe_load(raw)
        except Exception:
            continue
        rel = _rel(repo, path)
        for cs in _yaml_changesets(data):
            cs_id = str(cs.get('id') or '')
            for change_item in cs.get('changes') or []:
                if not isinstance(change_item, dict):
                    continue
                if 'createTable' in change_item and isinstance(change_item['createTable'], dict):
                    ch = change_item['createTable']
                    table = str(ch.get('tableName') or '').lower()
                    schema = str(ch.get('schemaName') or '').lower() or None
                    if not table:
                        continue
                    line = line_number_for_offset(raw, raw.find('createTable'))
                    table_item = {
                        'db_schema_table_id': f"db_schema_table_{repo_id}_{_hash(_qualified_table_name(schema, table))}",
                        'fact_type': 'db_schema_table',
                        'repo_id': repo_id,
                        'project_code': project_code,
                        'system_name': system_name,
                        'table_name': table,
                        'normalized_table_name': normalize_name(table),
                        'schema_name': schema,
                        'qualified_table_name': _qualified_table_name(schema, table),
                        'description': ch.get('remarks'),
                        'source_type': 'liquibase_yaml_ddl',
                        'change_set_id': cs_id,
                        'file': rel,
                        'line_start': line,
                        'observation_status': 'extracted',
                        'evidence': [{'file': rel, 'line_start': line, 'kind': 'liquibase_yaml_create_table'}],
                    }
                    _attach_schema_identity(table_item, repo=repo, path=path)
                    tables.append(table_item)
                    for col in _yaml_columns(ch):
                        col_name = str(col.get('name') or '').lower()
                        if not col_name:
                            continue
                        nullable = None
                        cons = col.get('constraints') if isinstance(col.get('constraints'), dict) else {}
                        if 'nullable' in cons:
                            nullable = bool(cons.get('nullable'))
                        col_item = {
                            'db_schema_column_id': f"db_schema_column_{repo_id}_{_hash(_qualified_table_name(schema, table) + '.' + col_name)}",
                            'fact_type': 'db_schema_column',
                            'repo_id': repo_id,
                            'project_code': project_code,
                            'system_name': system_name,
                            'table_name': table,
                            'normalized_table_name': normalize_name(table),
                            'schema_name': schema,
                            'qualified_table_name': _qualified_table_name(schema, table),
                            'column_name': col_name,
                            'normalized_column_name': normalize_name(col_name),
                            'sql_type': col.get('type'),
                            'nullable': nullable,
                            'description': col.get('remarks'),
                            'source_type': 'liquibase_yaml_ddl',
                            'change_set_id': cs_id,
                            'file': rel,
                            'line_start': line,
                            'observation_status': 'extracted',
                            'evidence': [{'file': rel, 'line_start': line, 'kind': 'liquibase_yaml_column'}],
                        }
                        columns.append(col_item)
                        if _yaml_constraint_bool(col, 'primaryKey'):
                            pk_name = (cons or {}).get('primaryKeyName') or f'pk_{table}'
                            keys.append({
                                'db_schema_key_id': f"db_schema_key_{repo_id}_{_hash(_qualified_table_name(schema, table) + '.' + str(pk_name))}",
                                'fact_type': 'db_schema_key',
                                'repo_id': repo_id,
                                'project_code': project_code,
                                'system_name': system_name,
                                'constraint_name': str(pk_name).lower(),
                                'constraint_kind': 'primary_key',
                                'table_name': table,
                                'schema_name': schema,
                                'qualified_table_name': _qualified_table_name(schema, table),
                                'columns': [col_name],
                                'source_type': 'liquibase_yaml_ddl',
                                'change_set_id': cs_id,
                                'file': rel,
                                'line_start': line,
                                'observation_status': 'extracted',
                                'evidence': [{'file': rel, 'line_start': line, 'kind': 'liquibase_yaml_primary_key'}],
                            })
                if 'addColumn' in change_item and isinstance(change_item['addColumn'], dict):
                    ch = change_item['addColumn']
                    table = str(ch.get('tableName') or '').lower()
                    schema = str(ch.get('schemaName') or '').lower() or None
                    line = line_number_for_offset(raw, raw.find('addColumn'))
                    for col in _yaml_columns(ch):
                        col_name = str(col.get('name') or '').lower()
                        if not table or not col_name:
                            continue
                        columns.append({
                            'db_schema_column_id': f"db_schema_column_{repo_id}_{_hash(_qualified_table_name(schema, table) + '.' + col_name)}",
                            'fact_type': 'db_schema_column',
                            'repo_id': repo_id,
                            'project_code': project_code,
                            'system_name': system_name,
                            'table_name': table,
                            'normalized_table_name': normalize_name(table),
                            'schema_name': schema,
                            'qualified_table_name': _qualified_table_name(schema, table),
                            'column_name': col_name,
                            'normalized_column_name': normalize_name(col_name),
                            'sql_type': col.get('type'),
                            'description': col.get('remarks'),
                            'source_type': 'liquibase_yaml_ddl',
                            'schema_change_kind': 'add_column',
                            'change_set_id': cs_id,
                            'file': rel,
                            'line_start': line,
                            'observation_status': 'extracted',
                            'evidence': [{'file': rel, 'line_start': line, 'kind': 'liquibase_yaml_add_column'}],
                        })
                if 'renameColumn' in change_item and isinstance(change_item['renameColumn'], dict):
                    ch = change_item['renameColumn']
                    table = str(ch.get('tableName') or '').lower()
                    schema = str(ch.get('schemaName') or '').lower() or None
                    old_col = str(ch.get('oldColumnName') or '').lower()
                    new_col = str(ch.get('newColumnName') or '').lower()
                    line = line_number_for_offset(raw, raw.find('renameColumn'))
                    if table and new_col:
                        columns.append({
                            'db_schema_column_id': f"db_schema_column_{repo_id}_{_hash(_qualified_table_name(schema, table) + '.' + new_col)}",
                            'fact_type': 'db_schema_column',
                            'repo_id': repo_id,
                            'project_code': project_code,
                            'system_name': system_name,
                            'table_name': table,
                            'schema_name': schema,
                            'qualified_table_name': _qualified_table_name(schema, table),
                            'column_name': new_col,
                            'normalized_column_name': normalize_name(new_col),
                            'renamed_from_column': old_col or None,
                            'description': ch.get('remarks'),
                            'source_type': 'liquibase_yaml_ddl',
                            'schema_change_kind': 'rename_column',
                            'change_set_id': cs_id,
                            'file': rel,
                            'line_start': line,
                            'observation_status': 'extracted',
                            'evidence': [{'file': rel, 'line_start': line, 'kind': 'liquibase_yaml_rename_column'}],
                        })
                if 'addUniqueConstraint' in change_item and isinstance(change_item['addUniqueConstraint'], dict):
                    ch = change_item['addUniqueConstraint']
                    table = str(ch.get('tableName') or '').lower()
                    schema = str(ch.get('schemaName') or '').lower() or None
                    cols = [c.strip().lower() for c in str(ch.get('columnNames') or '').split(',') if c.strip()]
                    name = str(ch.get('constraintName') or f"uk_{table}_{'_'.join(cols)}").lower()
                    line = line_number_for_offset(raw, raw.find('addUniqueConstraint'))
                    if table and cols:
                        keys.append({
                            'db_schema_key_id': f"db_schema_key_{repo_id}_{_hash(_qualified_table_name(schema, table) + '.' + name)}",
                            'fact_type': 'db_schema_key',
                            'repo_id': repo_id,
                            'project_code': project_code,
                            'system_name': system_name,
                            'constraint_name': name,
                            'constraint_kind': 'unique_key',
                            'table_name': table,
                            'schema_name': schema,
                            'qualified_table_name': _qualified_table_name(schema, table),
                            'columns': cols,
                            'source_type': 'liquibase_yaml_ddl',
                            'change_set_id': cs_id,
                            'file': rel,
                            'line_start': line,
                            'observation_status': 'extracted',
                            'evidence': [{'file': rel, 'line_start': line, 'kind': 'liquibase_yaml_add_unique_constraint'}],
                        })
                if 'createIndex' in change_item and isinstance(change_item['createIndex'], dict):
                    ch = change_item['createIndex']
                    table = str(ch.get('tableName') or '').lower()
                    schema = str(ch.get('schemaName') or '').lower() or None
                    idx_name = str(ch.get('indexName') or '').lower()
                    cols = [str(c.get('column', {}).get('name') or '').lower() for c in (ch.get('columns') or []) if isinstance(c, dict)]
                    cols = [c for c in cols if c]
                    line = line_number_for_offset(raw, raw.find('createIndex'))
                    if table and idx_name:
                        indexes.append({
                            'db_schema_index_id': f"db_schema_index_{repo_id}_{_hash(_qualified_table_name(schema, table) + '.' + idx_name)}",
                            'fact_type': 'db_schema_index',
                            'repo_id': repo_id,
                            'project_code': project_code,
                            'system_name': system_name,
                            'index_name': idx_name,
                            'table_name': table,
                            'schema_name': schema,
                            'qualified_table_name': _qualified_table_name(schema, table),
                            'columns': cols,
                            'unique': bool(ch.get('unique')),
                            'source_type': 'liquibase_yaml_ddl',
                            'change_set_id': cs_id,
                            'file': rel,
                            'line_start': line,
                            'observation_status': 'extracted',
                            'evidence': [{'file': rel, 'line_start': line, 'kind': 'liquibase_yaml_create_index'}],
                        })
                for op_name in ['insert', 'update']:
                    if op_name in change_item and isinstance(change_item[op_name], dict):
                        ch = change_item[op_name]
                        table = str(ch.get('tableName') or '').lower()
                        schema = str(ch.get('schemaName') or '').lower() or None
                        values = {}
                        for col in _yaml_columns(ch):
                            name = col.get('name')
                            if name:
                                declared_value, declared_value_kind = _yaml_declared_value(col)
                                values[str(name)] = {'value': declared_value, 'value_kind': declared_value_kind}
                        if table:
                            line = line_number_for_offset(raw, raw.find(op_name + ':'))
                            literal_data_writes.append({
                                'literal_data_write_id': f"literal_data_write_{repo_id}_{_hash(_qualified_table_name(schema, table) + '.' + cs_id + '.' + op_name)}",
                                'fact_type': 'literal_data_write',
                                'repo_id': repo_id,
                                'project_code': project_code,
                                'system_name': system_name,
                                'table_name': table,
                                'schema_name': schema,
                                'qualified_table_name': _qualified_table_name(schema, table),
                                'operation': op_name,
                                'columns': sorted(values),
                                'values': values,
                                'values_are_literal_or_declared_expression': True,
                                'parameterized': False,
                                'write_expression_kind': 'liquibase_structured_change',
                                'source_type': 'liquibase_yaml_data_change',
                                'change_set_id': cs_id,
                                'file': rel,
                                'line_start': line,
                                'observation_status': 'extracted',
                                'evidence': [{'file': rel, 'line_start': line, 'kind': f'liquibase_yaml_{op_name}'}],
                            })
                if 'sql' in change_item and isinstance(change_item['sql'], dict):
                    sql_text = str(change_item['sql'].get('sql') or '')
                    # Extract structural facts from inline SQL without classifying the written data.
                    if sql_text:
                        for m in re.finditer(r"\binsert\s+into\s+(?P<table>[A-Za-z0-9_\".]+)\s*\((?P<cols>[^)]*)\)", sql_text, re.IGNORECASE):
                            schema, table = _sql_identifier_parts(m.group('table'))
                            cols = _sql_column_list(m.group('cols'))
                            literal_data_writes.append({
                                'literal_data_write_id': f"literal_data_write_{repo_id}_{_hash(_qualified_table_name(schema, table) + '.' + cs_id + '.sql_insert.' + str(m.start()))}",
                                'fact_type': 'literal_data_write',
                                'repo_id': repo_id,
                                'project_code': project_code,
                                'system_name': system_name,
                                'table_name': table,
                                'schema_name': schema,
                                'qualified_table_name': _qualified_table_name(schema, table),
                                'operation': 'insert',
                                'columns': cols,
                                'values_are_literal_or_declared_expression': bool(re.search(r"\bvalues\b", sql_text, re.IGNORECASE)),
                                'parameterized': bool(re.search(r"[:?$][A-Za-z0-9_]*", sql_text)),
                                'write_expression_kind': 'liquibase_inline_sql',
                                'sql_expression': sql_text[:4000],
                                'source_type': 'liquibase_yaml_inline_sql_data_change',
                                'change_set_id': cs_id,
                                'file': rel,
                                'line_start': line_number_for_offset(raw, raw.find('sql:')),
                                'observation_status': 'extracted',
                                'evidence': [{'file': rel, 'line_start': line_number_for_offset(raw, raw.find('sql:')), 'kind': 'liquibase_yaml_inline_sql_insert'}],
                            })
    return {'tables': tables, 'columns': columns, 'keys': keys, 'relationships': relationships, 'indexes': indexes, 'constraints': constraints, 'literal_data_writes': literal_data_writes}


def _schema_source_rank(item: dict[str, Any]) -> int:
    source_set = str(item.get("source_set") or "").strip().lower()
    if bool(item.get("is_test_source")) or source_set in {"test", "fixture", "example_sample", "documentation"}:
        return 0
    if source_set in {"production", "migration", "generated", "main"}:
        return 3
    return 2


def _schema_source_order_key(item: dict[str, Any]) -> tuple[Any, ...]:
    file_name = str(item.get("file") or "").replace("\\", "/")
    base_name = file_name.rsplit("/", 1)[-1]
    version_m = re.search(r"(?:^|[^A-Za-z0-9])V(?P<version>\d+(?:[._]\d+)*)__", base_name, re.IGNORECASE)
    if version_m:
        version = tuple(int(part) for part in re.split(r"[._]", version_m.group("version")))
        return (2, version, file_name.lower(), int(item.get("line_start") or 0))
    return (1, file_name.lower(), int(item.get("line_start") or 0))


def _schema_definition_snapshot(item: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "constraint_name", "constraint_kind", "relationship_kind", "index_name", "unique",
        "columns", "source_columns", "target_schema", "target_table", "target_columns",
        "target_columns_declared", "expression", "partition_fact_kind", "partition_strategy",
        "partition_columns", "partition_table_name", "qualified_partition_table_name",
        "partition_bound_kind", "partition_bound_expression", "sql_type", "nullable",
        "default_value",
    )
    return {key: item.get(key) for key in keys if item.get(key) not in (None, "", [], {})}


def _schema_source_occurrence(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "file": item.get("file"),
        "line_start": item.get("line_start"),
        "source_set": item.get("source_set"),
        "is_test_source": bool(item.get("is_test_source")),
        "source_type": item.get("source_type"),
        "schema_name": item.get("schema_name") or item.get("source_schema"),
        "table_name": item.get("table_name") or item.get("source_table"),
        "source_order_key": list(_schema_source_order_key(item)),
        "definition": _schema_definition_snapshot(item),
    }


def _merge_schema_occurrence(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    existing_occurrences = list(existing.get("source_occurrences") or [_schema_source_occurrence(existing)])
    incoming_occurrences = list(incoming.get("source_occurrences") or [_schema_source_occurrence(incoming)])
    occurrences: list[dict[str, Any]] = []
    seen_occurrences: set[tuple[str, str, str, str]] = set()
    for occurrence in existing_occurrences + incoming_occurrences:
        key = (
            str(occurrence.get("file") or ""),
            str(occurrence.get("line_start") or ""),
            str(occurrence.get("schema_name") or ""),
            str(occurrence.get("table_name") or ""),
        )
        if key in seen_occurrences:
            continue
        seen_occurrences.add(key)
        occurrences.append(occurrence)

    existing_rank = _schema_source_rank(existing)
    incoming_rank = _schema_source_rank(incoming)
    incoming_is_preferred = incoming_rank > existing_rank or (
        incoming_rank == existing_rank
        and _schema_source_order_key(incoming) >= _schema_source_order_key(existing)
    )
    preferred = incoming if incoming_is_preferred else existing
    secondary = existing if incoming_is_preferred else incoming
    # Preserve fields that are not repeated by incremental ALTER observations,
    # while letting the representative (newer / stronger-scope) occurrence
    # override every field it actually publishes.
    merged = dict(secondary)
    merged.update(preferred)
    merged["representative_source_basis"] = (
        "higher_source_scope_rank" if incoming_rank != existing_rank else "latest_observed_source_order"
    )
    evidence: list[dict[str, Any]] = []
    seen_evidence: set[tuple[str, str, str]] = set()
    for item in (existing, incoming):
        for ref in item.get("evidence") or []:
            if not isinstance(ref, dict):
                continue
            key = (str(ref.get("file") or ""), str(ref.get("line_start") or ""), str(ref.get("kind") or ""))
            if key in seen_evidence:
                continue
            seen_evidence.add(key)
            evidence.append(ref)
    if evidence:
        merged["evidence"] = evidence
    placeholder_refs: set[str] = set()
    for item in (existing, incoming):
        placeholder_refs.update(str(x).lower() for x in item.get("placeholder_schema_references") or [] if x)
        ref = item.get("schema_reference_placeholder")
        if ref:
            placeholder_refs.add(str(ref).lower())
    if placeholder_refs:
        merged["placeholder_schema_references"] = sorted(placeholder_refs)
    merged["source_occurrences"] = occurrences
    merged["source_sets"] = sorted({str(x.get("source_set") or "unknown") for x in occurrences})
    merged["has_non_test_source"] = any(
        not bool(x.get("is_test_source")) and str(x.get("source_set") or "").lower() not in {"test", "fixture", "example_sample", "documentation"}
        for x in occurrences
    )
    return merged


def _annotate_schema_source_metadata(repo: Path, items_by_group: dict[str, list[dict[str, Any]]]) -> None:
    for items in items_by_group.values():
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            rel = item.get("file")
            path = repo / str(rel) if rel else repo
            item.setdefault("source_set", _source_set_for_path(path))
            item.setdefault("is_test_source", _is_test_source_path(path))
            item.setdefault("module_name", _module_name_for_path(repo, path))
            item.setdefault("source_occurrences", [_schema_source_occurrence(item)])
            item.setdefault("source_sets", [str(item.get("source_set") or "unknown")])
            item.setdefault("has_non_test_source", _schema_source_rank(item) > 0)


def _dedupe_schema_items(items: list[dict[str, Any]], key_fields: list[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    key_to_index: dict[tuple[str, ...], int] = {}
    for item in items:
        key = tuple(str(item.get(f) or "").lower() for f in key_fields)
        if key in key_to_index:
            idx = key_to_index[key]
            out[idx] = _merge_schema_occurrence(out[idx], item)
            continue
        key_to_index[key] = len(out)
        out.append(item)
    return out


def _merge_schema_items(primary: list[dict[str, Any]], secondary: list[dict[str, Any]], key_fields: list[str]) -> list[dict[str, Any]]:
    out = _dedupe_schema_items(primary, key_fields)
    key_to_index = {tuple(str(item.get(f) or "").lower() for f in key_fields): idx for idx, item in enumerate(out)}
    tail_to_indices: dict[tuple[str, ...], list[int]] = {}
    if key_fields and key_fields[0] in {"schema_name", "source_schema"}:
        for idx, item in enumerate(out):
            tail = tuple(str(item.get(f) or "").lower() for f in key_fields[1:])
            tail_to_indices.setdefault(tail, []).append(idx)

    for item in secondary:
        key = tuple(str(item.get(f) or "").lower() for f in key_fields)
        if key in key_to_index:
            idx = key_to_index[key]
            out[idx] = _merge_schema_occurrence(out[idx], item)
            continue

        if key_fields and key_fields[0] in {"schema_name", "source_schema"} and not str(item.get(key_fields[0]) or "").strip():
            tail_key = tuple(str(item.get(f) or "").lower() for f in key_fields[1:])
            matching = tail_to_indices.get(tail_key) or []
            if matching:
                best_existing_rank = max(_schema_source_rank(out[idx]) for idx in matching)
                if _schema_source_rank(item) <= best_existing_rank:
                    best_idx = max(matching, key=lambda idx: _schema_source_rank(out[idx]))
                    out[best_idx] = _merge_schema_occurrence(out[best_idx], item)
                    continue

        key_to_index[key] = len(out)
        out.append(item)
        if key_fields and key_fields[0] in {"schema_name", "source_schema"}:
            tail_key = tuple(str(item.get(f) or "").lower() for f in key_fields[1:])
            tail_to_indices.setdefault(tail_key, []).append(len(out) - 1)
    return out


def _schema_semantic_identity(group: str, item: dict[str, Any]) -> tuple[Any, ...] | None:
    table_name = str(item.get("table_name") or item.get("source_table") or "").strip().lower()
    if not table_name:
        return None
    if group == "keys":
        return (table_name, str(item.get("constraint_kind") or "").lower(), tuple(str(x).lower() for x in item.get("columns") or []))
    if group == "indexes":
        return (table_name, str(item.get("index_name") or "").lower(), tuple(str(x).lower() for x in item.get("columns") or []), bool(item.get("unique")))
    return None


def _coalesce_placeholder_schema_occurrences(items: list[dict[str, Any]], *, group: str) -> list[dict[str, Any]]:
    bound_by_identity: dict[tuple[Any, ...], list[int]] = {}
    for idx, item in enumerate(items):
        if str(item.get("schema_name_basis") or "") in {"placeholder_reference", "unresolved_placeholder_reference"}:
            continue
        identity = _schema_semantic_identity(group, item)
        if identity is not None and (item.get("schema_generation_id") or item.get("migration_state") == "active"):
            bound_by_identity.setdefault(identity, []).append(idx)

    removed: set[int] = set()
    for idx, item in enumerate(items):
        if str(item.get("schema_name_basis") or "") not in {"placeholder_reference", "unresolved_placeholder_reference"}:
            continue
        identity = _schema_semantic_identity(group, item)
        matches = bound_by_identity.get(identity or ()) or []
        if len(matches) != 1:
            continue
        bound_idx = matches[0]
        bound = items[bound_idx]
        merged = _merge_schema_occurrence(bound, item)
        # Preserve the identity of the table generation that was actually observed
        # in CREATE TABLE evidence. The placeholder declaration remains available
        # through source_occurrences.
        for key in (
            "schema_name", "qualified_table_name", "schema_generation_id", "migration_state",
            "schema_name_basis", "db_schema_key_id", "db_schema_index_id",
        ):
            if key in bound:
                merged[key] = bound.get(key)
            else:
                merged.pop(key, None)
        placeholder_refs = list(bound.get("placeholder_schema_references") or [])
        ref = str(item.get("schema_reference_placeholder") or item.get("schema_name") or "").strip()
        if ref and ref not in placeholder_refs:
            placeholder_refs.append(ref)
        if placeholder_refs:
            merged["placeholder_schema_references"] = sorted(placeholder_refs)
        merged["representative_source_basis"] = "observed_table_generation_with_placeholder_redeclaration"
        items[bound_idx] = merged
        removed.add(idx)
    return [item for idx, item in enumerate(items) if idx not in removed]


def _postprocess_schema_identity(repo: Path, items_by_group: dict[str, list[dict[str, Any]]]) -> None:
    for group, items in items_by_group.items():
        for item in items or []:
            rel = item.get('file')
            path = repo / str(rel) if rel else repo
            if group == 'relationships':
                if item.get('source_table'):
                    item.setdefault('source_qualified_table_name', _qualified_table_name(item.get('source_schema') or item.get('schema_name'), item.get('source_table')))
                if item.get('target_table'):
                    item.setdefault('target_qualified_table_name', _qualified_table_name(item.get('target_schema'), item.get('target_table')))
            elif group == 'triggers':
                if item.get('source_table'):
                    item.setdefault('source_qualified_table_name', _qualified_table_name(item.get('source_schema') or item.get('schema_name'), item.get('source_table')))
            else:
                table_key = 'table_name' if item.get('table_name') else None
                if table_key:
                    _attach_schema_identity(item, repo=repo, path=path, table_key=table_key)
                if group == 'partitioning' and item.get('partition_fact_kind') == 'child_partition':
                    item['parent_table_name'] = item.get('table_name')
                    item['parent_schema_name'] = item.get('schema_name')
                    item['parent_qualified_table_name'] = item.get('qualified_table_name')
                    child_schema = item.get('partition_schema_name')
                    if not child_schema:
                        item.setdefault('partition_schema_name_basis', 'unresolved_unqualified_sql')
                        item.setdefault('partition_schema_resolution_status', 'unresolved')
                    item['qualified_partition_table_name'] = _qualified_table_name(
                        item.get('partition_schema_name'), item.get('partition_table_name')
                    )
            item.setdefault('source_set', _source_set_for_path(path))
            item.setdefault('is_test_source', _is_test_source_path(path))
            item.setdefault('module_name', _module_name_for_path(repo, path))


def scan_database_schema(repo: Path, files: list[Path], *, repo_id: str, project_code: str, system_name: str) -> dict[str, Any]:
    """Extract physical DB model from schema-bearing generated Java sources.

    The first supported source is jOOQ generated code. It is intentionally regex-based
    and read-only: the extractor does not compile project code and does not execute DDL.
    """
    java_files = [p for p in files if p.is_file() and p.suffix.lower() == ".java"]
    jooq_table_files = [
        p for p in java_files
        if "/generated/tables/" in str(p).replace("\\", "/") and "/records/" not in str(p).replace("\\", "/")
    ]
    tables: list[dict[str, Any]] = []
    columns: list[dict[str, Any]] = []
    table_by_constant: dict[str, str] = {}
    column_by_ref: dict[tuple[str, str], str] = {}
    for path in sorted(jooq_table_files):
        table, cols, const_map, col_map = _scan_jooq_table_file(repo, path, repo_id=repo_id, project_code=project_code, system_name=system_name)
        if table:
            tables.append(table)
            table_by_constant.update(const_map)
            column_by_ref.update(col_map)
        columns.extend(cols)
    keys, relationships = _scan_jooq_keys(repo, java_files, repo_id=repo_id, project_code=project_code, system_name=system_name, table_by_constant=table_by_constant, column_by_ref=column_by_ref)
    indexes = _scan_jooq_indexes(repo, java_files, repo_id=repo_id, project_code=project_code, system_name=system_name, table_by_constant=table_by_constant, column_by_ref=column_by_ref)
    sequences = _scan_jooq_sequences(repo, java_files, repo_id=repo_id, project_code=project_code, system_name=system_name)
    constraints = _scan_jooq_check_constraints(repo, java_files, repo_id=repo_id, project_code=project_code, system_name=system_name, table_by_constant=table_by_constant)
    partitioning: list[dict[str, Any]] = []
    triggers: list[dict[str, Any]] = []

    sql_schema = _scan_liquibase_sql_schema(repo, files, repo_id=repo_id, project_code=project_code, system_name=system_name)
    yaml_schema = _scan_liquibase_yaml_schema(repo, files, repo_id=repo_id, project_code=project_code, system_name=system_name)
    jooq_counts = {
        "tables": len(tables),
        "columns": len(columns),
        "keys": len(keys),
        "relationships": len(relationships),
        "indexes": len(indexes),
        "sequences": len(sequences),
        "constraints": len(constraints),
        "partitioning": len(partitioning),
        "triggers": len(triggers),
        "jooq_table_files": len(jooq_table_files),
    }
    sql_counts = {k: len(sql_schema.get(k) or []) for k in [
        "tables", "columns", "keys", "relationships", "indexes", "sequences",
        "constraints", "partitioning", "triggers", "schema_changes",
        "historical_tables", "historical_schema_facts", "excluded_schema_facts",
        "excluded_schema_changes", "schema_resolution_observations",
    ]}
    yaml_counts = {k: len(yaml_schema.get(k) or []) for k in ["tables", "columns", "keys", "relationships", "indexes", "constraints", "literal_data_writes"]}

    _annotate_schema_source_metadata(repo, {
        "tables": tables, "columns": columns, "keys": keys, "relationships": relationships,
        "indexes": indexes, "sequences": sequences, "constraints": constraints,
        "partitioning": partitioning, "triggers": triggers,
    })
    _annotate_schema_source_metadata(repo, sql_schema)
    _annotate_schema_source_metadata(repo, yaml_schema)

    tables = _merge_schema_items(tables, sql_schema.get("tables") or [], ["schema_name", "table_name"])
    tables = _merge_schema_items(tables, yaml_schema.get("tables") or [], ["schema_name", "table_name"])
    columns = _merge_schema_items(columns, sql_schema.get("columns") or [], ["schema_name", "table_name", "column_name"])
    columns = _merge_schema_items(columns, yaml_schema.get("columns") or [], ["schema_name", "table_name", "column_name"])
    keys = _merge_schema_items(keys, sql_schema.get("keys") or [], ["schema_name", "table_name", "constraint_name"])
    keys = _merge_schema_items(keys, yaml_schema.get("keys") or [], ["schema_name", "table_name", "constraint_name"])
    relationships = _merge_schema_items(relationships, sql_schema.get("relationships") or [], ["source_schema", "source_table", "constraint_name"])
    relationships = _merge_schema_items(relationships, yaml_schema.get("relationships") or [], ["source_schema", "source_table", "constraint_name"])
    indexes = _merge_schema_items(indexes, sql_schema.get("indexes") or [], ["schema_name", "table_name", "index_name"])
    indexes = _merge_schema_items(indexes, yaml_schema.get("indexes") or [], ["schema_name", "table_name", "index_name"])
    sequences = _merge_schema_items(sequences, sql_schema.get("sequences") or [], ["schema_name", "sequence_name"])
    constraints = _merge_schema_items(constraints, sql_schema.get("constraints") or [], ["schema_name", "table_name", "constraint_name"])
    constraints = _merge_schema_items(constraints, yaml_schema.get("constraints") or [], ["schema_name", "table_name", "constraint_name"])
    partitioning = _merge_schema_items(
        partitioning,
        sql_schema.get("partitioning") or [],
        [
            "partition_fact_kind",
            "schema_name",
            "table_name",
            "partition_schema_name",
            "partition_table_name",
            "partition_strategy",
            "partition_columns",
            "partition_bound_expression",
        ],
    )
    triggers = _merge_schema_items(triggers, sql_schema.get("triggers") or [], ["source_schema", "source_table", "trigger_name"])
    schema_changes = list(sql_schema.get("schema_changes") or [])
    historical_tables = list(sql_schema.get("historical_tables") or [])
    historical_schema_facts = list(sql_schema.get("historical_schema_facts") or [])
    excluded_schema_facts = list(sql_schema.get("excluded_schema_facts") or [])
    excluded_schema_changes = list(sql_schema.get("excluded_schema_changes") or [])
    sql_source_scope_summary = dict(sql_schema.get("sql_source_scope_summary") or {})
    schema_resolution_observations = list(sql_schema.get("schema_resolution_observations") or [])
    literal_data_writes = _dedupe_schema_items(yaml_schema.get("literal_data_writes") or [], ["schema_name", "table_name", "change_set_id", "operation", "line_start"])
    _postprocess_schema_identity(repo, {
        "tables": tables, "columns": columns, "keys": keys, "relationships": relationships,
        "indexes": indexes, "sequences": sequences, "constraints": constraints, "partitioning": partitioning,
        "triggers": triggers, "literal_data_writes": literal_data_writes,
        "schema_changes": schema_changes, "historical_tables": historical_tables,
        "historical_schema_facts": historical_schema_facts,
        "excluded_schema_facts": excluded_schema_facts,
        "excluded_schema_changes": excluded_schema_changes,
        "schema_resolution_observations": schema_resolution_observations,
    })
    keys = _coalesce_placeholder_schema_occurrences(keys, group="keys")
    indexes = _coalesce_placeholder_schema_occurrences(indexes, group="indexes")

    # Keep relationships, keys and indexes as declared structural facts.
    # Cardinality, purpose and confidence are semantic interpretations for the LLM layer.
    for rel in relationships:
        rel["relationship_evidence_kind"] = "declared_foreign_key"

    by_table: dict[str, dict[str, Any]] = {str(t.get("qualified_table_name") or t.get("table_name")): t for t in tables}
    for table in by_table.values():
        table_name = table.get("table_name")
        qtn = table.get("qualified_table_name")
        table["column_count"] = sum(1 for c in columns if (c.get("qualified_table_name") or c.get("table_name")) == qtn)
        table["primary_keys"] = [k for k in keys if (k.get("qualified_table_name") or k.get("table_name")) == qtn and k.get("constraint_kind") == "primary_key"]
        table["foreign_keys_out"] = [r for r in relationships if (r.get("source_qualified_table_name") or r.get("source_table")) == qtn]
        table["foreign_keys_in_count"] = sum(1 for r in relationships if (r.get("target_qualified_table_name") or r.get("target_table")) == qtn)
        table["indexes"] = [i for i in indexes if (i.get("qualified_table_name") or i.get("table_name")) == qtn]
        table["constraints"] = [c for c in constraints if (c.get("qualified_table_name") or c.get("table_name")) == qtn]
        table["partitioning"] = [
            p for p in partitioning
            if (p.get("qualified_table_name") or p.get("table_name")) == qtn
            or (p.get("qualified_partition_table_name") or p.get("partition_table_name")) == qtn
        ]
        table["triggers"] = [t for t in triggers if (t.get("source_qualified_table_name") or t.get("source_table")) == qtn]
        sources = {str(table.get("source_type") or "")}
        sources.update(str(c.get("source_type") or "") for c in columns if (c.get("qualified_table_name") or c.get("table_name")) == qtn)
        sources.update(str(k.get("source_type") or "") for k in keys if (k.get("qualified_table_name") or k.get("table_name")) == qtn)
        sources.update(str(r.get("source_type") or "") for r in relationships if (r.get("source_qualified_table_name") or r.get("source_table")) == qtn or (r.get("target_qualified_table_name") or r.get("target_table")) == qtn)
        sources.update(str(i.get("source_type") or "") for i in indexes if (i.get("qualified_table_name") or i.get("table_name")) == qtn)
        sources.update(str(c.get("source_type") or "") for c in constraints if (c.get("qualified_table_name") or c.get("table_name")) == qtn)
        sources.update(
            str(p.get("source_type") or "") for p in partitioning
            if (p.get("qualified_table_name") or p.get("table_name")) == qtn
            or (p.get("qualified_partition_table_name") or p.get("partition_table_name")) == qtn
        )
        sources.update(str(t.get("source_type") or "") for t in triggers if (t.get("source_qualified_table_name") or t.get("source_table")) == qtn)
        table["evidence_sources"] = sorted(x for x in sources if x)
    overview = {
        "artifact": "db_schema_overview",
        "repo_id": repo_id,
        "project_code": project_code,
        "system_name": system_name,
        "source_policy": "schema-bearing generated Java classes and Liquibase SQL DDL are treated as confirmed physical DB model evidence; SQL usage may complement this model but code/usage heuristics remain candidate-only",
        "counts": {
            "tables": len(tables),
            "explicit_partition_tables": sum(1 for t in tables if t.get("table_kind") == "partition"),
            "columns": len(columns),
            "inherited_partition_columns": sum(1 for c in columns if c.get("column_origin") == "inherited_from_partition_parent"),
            "keys": len(keys),
            "relationships": len(relationships),
            "indexes": len(indexes),
            "sequences": len(sequences),
            "constraints": len(constraints),
            "partitioning": len(partitioning),
            "triggers": len(triggers),
            "schema_changes": len(schema_changes),
            "historical_tables": len(historical_tables),
            "historical_schema_facts": len(historical_schema_facts),
            "excluded_schema_facts": len(excluded_schema_facts),
            "excluded_schema_changes": len(excluded_schema_changes),
            "schema_resolution_observations": len(schema_resolution_observations),
            "jooq_table_files": len(jooq_table_files),
            "jooq_extracted": jooq_counts,
            "liquibase_sql_ddl_extracted": sql_counts,
            "liquibase_sql_files": len([p for p in files if p.is_file() and p.suffix.lower() == ".sql"]),
            "liquibase_yaml_ddl_extracted": yaml_counts,
            "liquibase_yaml_files": len([p for p in files if p.is_file() and p.suffix.lower() in {".yaml", ".yml"}]),
            "literal_data_writes": len(literal_data_writes),
        },
        "sql_source_scope_summary": sql_source_scope_summary,
        "schema_resolution_observations": schema_resolution_observations,
        "source_mix": {
            "tables_from_jooq_or_primary": jooq_counts["tables"],
            "tables_added_from_liquibase_sql_ddl": max(0, len(tables) - jooq_counts["tables"]),
            "relationships_added_from_liquibase_sql_ddl": sum(1 for r in relationships if r.get("source_type") == "liquibase_sql_ddl"),
            "indexes_added_from_liquibase_sql_ddl": sum(1 for i in indexes if i.get("source_type") == "liquibase_sql_ddl"),
            "sequences_added_from_liquibase_sql_ddl": sum(1 for seq in sequences if seq.get("source_type") == "liquibase_sql_ddl"),
            "constraints_added_from_liquibase_sql_ddl": sum(1 for c in constraints if c.get("source_type") == "liquibase_sql_ddl"),
            "partitioning_added_from_liquibase_sql_ddl": sum(1 for p in partitioning if p.get("source_type") == "liquibase_sql_ddl"),
            "triggers_added_from_liquibase_sql_ddl": sum(1 for t in triggers if t.get("source_type") == "liquibase_sql_ddl"),
            "tables_added_from_liquibase_yaml_ddl": sum(1 for t in tables if t.get("source_type") == "liquibase_yaml_ddl"),
            "columns_added_from_liquibase_yaml_ddl": sum(1 for c in columns if c.get("source_type") == "liquibase_yaml_ddl"),
            "literal_data_writes_from_liquibase_yaml": len(literal_data_writes),
        },
        "top_tables": [
            {"table_name": t.get("table_name"), "qualified_table_name": t.get("qualified_table_name"), "schema_name": t.get("schema_name"), "description": t.get("description"), "column_count": t.get("column_count"), "constraints_count": len(t.get("constraints") or []), "partitioning_count": len(t.get("partitioning") or []), "triggers_count": len(t.get("triggers") or []), "file": t.get("file"), "evidence_sources": t.get("evidence_sources")}
            for t in sorted(tables, key=lambda x: str(x.get("table_name")))[:100]
        ],
    }
    return {
        "overview": overview,
        "tables": sorted(tables, key=lambda x: str(x.get("table_name"))),
        "columns": sorted(columns, key=lambda x: (str(x.get("table_name")), str(x.get("column_name")))),
        "keys": sorted(keys, key=lambda x: (str(x.get("table_name")), str(x.get("constraint_name")))),
        "relationships": sorted(relationships, key=lambda x: (str(x.get("source_table")), str(x.get("constraint_name")))),
        "indexes": sorted(indexes, key=lambda x: (str(x.get("table_name")), str(x.get("index_name")))),
        "sequences": sorted(sequences, key=lambda x: str(x.get("sequence_name"))),
        "constraints": sorted(constraints, key=lambda x: (str(x.get("table_name")), str(x.get("constraint_name")))),
        "partitioning": sorted(
            partitioning,
            key=lambda x: (
                str(x.get("table_name") or ""),
                str(x.get("partition_fact_kind") or ""),
                str(x.get("partition_table_name") or ""),
            ),
        ),
        "triggers": sorted(triggers, key=lambda x: (str(x.get("source_table")), str(x.get("trigger_name")))),
        "schema_changes": sorted(schema_changes, key=_sql_migration_order_key),
        "historical_tables": sorted(historical_tables, key=_sql_migration_order_key),
        "historical_schema_facts": sorted(
            historical_schema_facts,
            key=lambda x: (_sql_migration_order_key(x), str(x.get("schema_fact_group") or "")),
        ),
        "excluded_schema_facts": sorted(
            excluded_schema_facts,
            key=lambda x: (str(x.get("file") or ""), int(x.get("line_start") or 0), str(x.get("schema_fact_group") or "")),
        ),
        "excluded_schema_changes": sorted(excluded_schema_changes, key=_sql_migration_order_key),
        "sql_source_scope_summary": sql_source_scope_summary,
        "schema_resolution_observations": schema_resolution_observations,
        "literal_data_writes": sorted(literal_data_writes, key=lambda x: (str(x.get("qualified_table_name")), str(x.get("line_start")))),
    }
