from __future__ import annotations

from contextlib import suppress
from collections import defaultdict
import json
import os
from pathlib import Path
from typing import Any, Mapping
import uuid

from prepared_knowledge_runtime.contracts import KnowledgeLayerManifest
from .cross_artifact_data_model_schema import (
    CROSS_ARTIFACT_DATABASE,
    CROSS_ARTIFACT_DDL,
    CROSS_ARTIFACT_SCHEMA_VERSION,
    CROSS_ARTIFACT_TABLES,
)
from prepared_knowledge_runtime.database import connect_database, initialize_schema
from prepared_knowledge_runtime.io import write_manifest
from .logical_physical_mapping_ingestion import resolve_knowledge_layer_input
from .metrics import canonical_json, utc_now
from prepared_knowledge_runtime.normalization import stable_id
from .publication import publish_directory_atomic, remove_path
from .sql_producer_lineage import ObservedMaterializationIndex, SqlProducerColumnTraversal
from .version import __version__


def _counts(connection: Any) -> dict[str, int]:
    return {t: int(connection.execute(f'SELECT count(*) FROM "{t}"').fetchone()[0]) for t in CROSS_ARTIFACT_TABLES}


def _flatten_qualified_name(value: str) -> str:
    return str(value or "").strip().lower().replace("$", ".").replace(".", "_")


def _base_sql_identity(value: str) -> tuple[str, str]:
    text = str(value or "").strip().lower()
    if text.endswith("_hist"):
        return text[:-5], "history"
    if text.endswith("_delta"):
        return text[:-6], "delta"
    return text, "base"


def _json_value(value: Any, default: Any) -> Any:
    if value in (None, ""):
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value))
    except Exception:
        return default


def _placeholder_tokens(text: str) -> list[str]:
    import re
    pattern = re.compile(
        r"\$\{\s*\$?(?P<braced>[^{}]+?)\s*\}|(?<![A-Za-z0-9$])\$(?P<bare>[A-Za-z_][A-Za-z0-9_.]*)"
    )
    return [str(m.group("braced") or m.group("bare") or "").strip().lstrip("$") for m in pattern.finditer(str(text or ""))]


def _replace_placeholder(text: str, name: str, value: str) -> str:
    import re
    escaped = re.escape(name)
    return re.sub(r"\$\{\s*\$?" + escaped + r"\s*\}|(?<![A-Za-z0-9$])\$" + escaped + r"\b", lambda _m: value, text)


def _strip_script_literal(value: str) -> str:
    text = str(value or "").strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        return text[1:-1]
    return text


def _resolve_script_expression(
    expression: str,
    *,
    script_file: str,
    before_line: int,
    local_bindings: Mapping[tuple[str, str], list[tuple[int, str]]],
    context_values: Mapping[str, list[str]],
    max_depth: int = 12,
) -> tuple[list[str], list[str]]:
    """Resolve only observed local/workflow bindings; leave unknown placeholders explicit."""
    variants = [_strip_script_literal(expression)]
    unresolved: set[str] = set()
    for _ in range(max_depth):
        next_variants: list[str] = []
        changed = False
        for variant in variants:
            names = _placeholder_tokens(variant)
            if not names:
                next_variants.append(variant)
                continue
            replaced = False
            for name in names:
                candidates: list[str] = []
                local = [item for item in local_bindings.get((script_file, name.lower()), ()) if item[0] <= before_line]
                if local:
                    candidates = [local[-1][1]]
                elif context_values.get(name):
                    candidates = list(context_values[name])
                if not candidates:
                    continue
                for candidate in candidates:
                    next_variants.append(_replace_placeholder(variant, name, _strip_script_literal(candidate)))
                changed = True
                replaced = True
                break
            if not replaced:
                next_variants.append(variant)
        variants = sorted(dict.fromkeys(next_variants))[:100]
        if not changed:
            break
    for variant in variants:
        unresolved.update(_placeholder_tokens(variant))
    return variants, sorted(unresolved)


def _match_sql_file_template(template: str, known_files: list[str], source_file: str) -> list[str]:
    """Exact path/suffix matching after observed binding substitution; no fuzzy similarity."""
    import re
    normalized = str(template or "").strip().replace("\\", "/").strip(" \t\r\n\"'`()[]{};,. ").lstrip("/")
    known = sorted(dict.fromkeys(str(item).replace("\\", "/").lstrip("/") for item in known_files if item))
    if normalized in known:
        return [normalized]
    # Unknown dynamic prefixes are allowed only before a literal repository-local suffix.
    matches = list(re.finditer(r"\$\{[^{}]+\}|(?<![A-Za-z0-9$])\$[A-Za-z_][A-Za-z0-9_.]*", normalized))
    suffix = normalized[matches[-1].end():].lstrip("/") if matches else normalized
    candidates = [item for item in known if suffix and (item == suffix or item.endswith("/" + suffix))]
    if not candidates:
        for anchor in ("wf/", "workflow/", "sql/", "dml/"):
            idx = normalized.find(anchor)
            if idx >= 0:
                tail = normalized[idx:]
                candidates = [item for item in known if item == tail or item.endswith("/" + tail)]
                if candidates:
                    break
    if len(candidates) <= 1:
        return candidates
    source_parts = str(source_file or "").replace("\\", "/").split("/")[:-1]
    def prefix_len(item: str) -> int:
        parts = item.split("/")[:-1]
        n = 0
        for a, b in zip(source_parts, parts):
            if a != b:
                break
            n += 1
        return n
    scores = {item: prefix_len(item) for item in candidates}
    best = max(scores.values(), default=0)
    narrowed = [item for item in candidates if scores[item] == best]
    return narrowed


def _workflow_identity_tokens(value: str) -> list[str]:
    """Extract exact workflow entity identities from observed trigger/entity expressions."""
    import re
    tokens: list[str] = []
    cleaned = re.sub(r"\$\{[^}]+\}", " ", str(value or ""))
    for match in re.finditer(r"[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*", cleaned):
        token = match.group(0).strip()
        if token.lower() in {"and", "or", "not", "true", "false"}:
            continue
        parts = token.split(".")
        # Workflow trigger stage/version suffixes such as `.2` identify the same
        # entity published by the producer's `entities` binding.
        if len(parts) > 1 and parts[-1].isdigit():
            token = ".".join(parts[:-1])
        if token:
            tokens.append(token)
    return sorted(dict.fromkeys(tokens))


def build_cross_artifact_data_model_mapping_knowledge_layer(
    logical_storage_item: Mapping[str, Any],
    code_declared_item: Mapping[str, Any],
    sql_item: Mapping[str, Any],
    physical_item: Mapping[str, Any],
    output: str | Path,
    *,
    scope_id: str,
    replace: bool = True,
    duckdb_memory_limit: str = "1GB",
    duckdb_threads: int = 1,
) -> dict[str, Any]:
    logical_storage = resolve_knowledge_layer_input(
        logical_storage_item,
        model_kind="logical-storage-model-mapping",
        schema_version="logical-storage-model-mapping/v2",
        source_materialization_id="logical-storage-mapping",
    )
    code = resolve_knowledge_layer_input(
        code_declared_item,
        model_kind="code-declared-data-model",
        schema_version="code-declared-data-model/v1",
        source_materialization_id="code-declared-data-model",
    )
    sql = resolve_knowledge_layer_input(
        sql_item,
        model_kind="sql-observed-data-usage",
        schema_version="knowledge_layer_sql/v2",
        source_materialization_id="sql-analysis",
    )
    physical = resolve_knowledge_layer_input(
        physical_item,
        model_kind="physical-data-model",
        schema_version="knowledge_layer_physical_model/v1",
        source_materialization_id="physical-model",
    )

    output_path = Path(output).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if (output_path.exists() or output_path.is_symlink()) and not replace:
        raise FileExistsError(output_path)
    staging = output_path.with_name(f".{output_path.name}.building-{os.getpid()}-{uuid.uuid4().hex[:12]}")
    remove_path(staging)
    staging.mkdir(parents=True)
    started = utc_now()
    build_id = stable_id(
        "cross_artifact_data_model_mapping_build",
        scope_id,
        logical_storage.input_item.get("content_fingerprint"),
        code.input_item.get("content_fingerprint"),
        sql.input_item.get("content_fingerprint"),
        physical.input_item.get("content_fingerprint"),
        __version__,
    )
    c = ls = cc = sc = pc = None
    transaction_started = False
    try:
        c = connect_database(staging / CROSS_ARTIFACT_DATABASE, memory_limit=duckdb_memory_limit, threads=duckdb_threads, preserve_insertion_order=False)
        initialize_schema(c, CROSS_ARTIFACT_DDL)
        # This materialization writes many observed cross-artifact rows. Keep the
        # whole build in one transaction so real repositories do not pay one
        # DuckDB commit/fsync cycle per inserted row.
        c.execute("BEGIN TRANSACTION")
        transaction_started = True
        c.execute(
            "INSERT INTO cross_artifact_mapping_build VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?)",
            [build_id, scope_id, __version__, CROSS_ARTIFACT_SCHEMA_VERSION, "building", started, canonical_json({}), canonical_json({})],
        )
        inputs = (("logical_storage", logical_storage), ("code_declared", code), ("sql", sql), ("physical", physical))
        for role, source in inputs:
            c.execute(
                "INSERT INTO cross_artifact_mapping_source VALUES (?, ?, ?, ?, ?, ?)",
                [
                    stable_id("cross_artifact_mapping_source", scope_id, role, source.input_item.get("artifact_id")),
                    scope_id,
                    role,
                    source.input_item.get("artifact_id"),
                    source.input_item.get("content_fingerprint"),
                    str(source.output_path),
                ],
            )

        ls = connect_database(logical_storage.database_path, read_only=True)
        cc = connect_database(code.database_path, read_only=True)
        sc = connect_database(sql.database_path, read_only=True)
        pc = connect_database(physical.database_path, read_only=True)

        alias_candidates: dict[str, list[dict[str, str]]] = defaultdict(list)
        for row in ls.execute(
            "SELECT DISTINCT storage_alias, logical_type_occurrence_id, logical_fully_qualified_name "
            "FROM logical_storage_entity_mapping WHERE mapping_status='matched' ORDER BY storage_alias"
        ).fetchall():
            alias = str(row[0])
            alias_candidates[_flatten_qualified_name(alias)].append(
                {"storage_alias": alias, "logical_type_occurrence_id": str(row[1] or ""), "logical_fqcn": str(row[2] or alias)}
            )

        # Keep observed storage identity variants separate from entity matching: one
        # storage alias can legitimately have multiple key expressions (for example,
        # POJO and JSON converters), while its logical identity remains unique.
        storage_key_variants_by_alias: dict[str, list[dict[str, str]]] = defaultdict(list)
        for row in ls.execute(
            "SELECT storage_alias, storage_key_expression, payload_json "
            "FROM logical_storage_entity_mapping WHERE mapping_status='matched' ORDER BY storage_alias, storage_observation_id"
        ).fetchall():
            payload = _json_value(row[2], {})
            properties = payload.get("properties") if isinstance(payload, Mapping) else {}
            properties = properties if isinstance(properties, Mapping) else {}
            key_field = str(properties.get("storage_key_field") or "").strip()
            if not key_field:
                continue
            item = {
                "storage_key_field": key_field,
                "storage_key_expression": str(row[1] or properties.get("storage_key_expression") or ""),
            }
            if item not in storage_key_variants_by_alias[str(row[0])]:
                storage_key_variants_by_alias[str(row[0])].append(item)

        # Resolve relation identities from exact file-local script bindings when
        # Core intentionally leaves a table placeholder in the SQL relation.
        relation_local_bindings: dict[tuple[str, str], list[tuple[int, str]]] = defaultdict(list)
        sql_input_tables = {str(r[0]) for r in sc.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='main'").fetchall()}
        if "sql_script_binding" in sql_input_tables:
            for r in sc.execute(
                "SELECT file, line_start, binding_name, scalar_value, value_expression FROM sql_script_binding ORDER BY file, line_start"
            ).fetchall():
                value = str(r[3] if r[3] is not None else r[4] or "").strip()
                if value and not _placeholder_tokens(value):
                    relation_local_bindings[(str(r[0]), str(r[2] or "").strip().lstrip("$").lower())].append((int(r[1] or 0), value))

        def resolved_relation_logical_name(relation_name: str, logical_name: str | None, file: str | None, line_start: int | None) -> tuple[str | None, str]:
            if logical_name:
                return str(logical_name), "core_logical_name"
            tail = str(relation_name or "").split(".")[-1].strip()
            import re
            match = re.fullmatch(r"\$\{\$?([A-Za-z_][A-Za-z0-9_.]*)\}|\$([A-Za-z_][A-Za-z0-9_.]*)", tail)
            if not match:
                return None, "unresolved_relation_identity"
            name = str(match.group(1) or match.group(2) or "").lower()
            candidates = [item for item in relation_local_bindings.get((str(file or ""), name), ()) if item[0] <= int(line_start or 0)]
            if not candidates:
                return None, "local_binding_missing"
            value = sorted(candidates, key=lambda x: x[0])[-1][1]
            return value.split(".")[-1], "file_local_script_binding"

        exact_base_present: set[str] = set()
        sql_relations_raw = sc.execute(
            "SELECT sql_relation_id, repo_id, relation_name, logical_name, usage_role, relation_kind, file, line_start "
            "FROM sql_relation WHERE relation_kind IN ('physical','physical_template') ORDER BY sql_relation_id"
        ).fetchall()
        sql_relations: list[tuple[Any, ...]] = []
        for row in sql_relations_raw:
            resolved_name, identity_basis = resolved_relation_logical_name(str(row[2] or ""), row[3], row[6], row[7])
            if not resolved_name:
                continue
            sql_relations.append((*row, resolved_name, identity_basis))
            base, variant = _base_sql_identity(resolved_name)
            if variant == "base" and len(alias_candidates.get(base, ())) == 1:
                exact_base_present.add(base)

        for row in sql_relations:
            sql_relation_id, repo_id, relation_name, logical_name, usage_role, relation_kind, file, line_start, resolved_logical_name, identity_basis = row
            base, variant = _base_sql_identity(str(resolved_logical_name))
            candidates = alias_candidates.get(base, ())
            if len(candidates) != 1:
                continue
            selected = candidates[0]
            if variant == "base":
                knowledge_class = "derived"
                basis = "unique_flattened_qualified_name"
            elif base in exact_base_present:
                knowledge_class = "derived"
                basis = "unique_flattened_qualified_name_plus_observed_representation_suffix"
            else:
                knowledge_class = "candidate"
                basis = "flattened_qualified_name_plus_unanchored_representation_suffix"
            if identity_basis == "file_local_script_binding":
                basis += "_plus_file_local_script_binding"
            c.execute(
                "INSERT INTO cross_artifact_storage_sql_mapping VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    stable_id("cross_artifact_storage_sql_mapping", sql_relation_id, selected["storage_alias"]),
                    selected["storage_alias"],
                    selected["logical_type_occurrence_id"] or None,
                    selected["logical_fqcn"],
                    str(sql_relation_id),
                    str(repo_id),
                    relation_name,
                    str(resolved_logical_name),
                    usage_role,
                    variant,
                    "matched",
                    knowledge_class,
                    basis,
                    canonical_json({
                        "logical_storage_artifact_id": logical_storage.input_item.get("artifact_id"),
                        "sql_artifact_id": sql.input_item.get("artifact_id"),
                        "sql_relation_kind": relation_kind,
                        "file": file,
                        "line_start": line_start,
                        "normalization": "lowercase_fqcn_dot_to_underscore",
                        "relation_identity_basis": identity_basis,
                    }),
                ],
            )

        # Logical effective fields -> observed SQL source-column usages.  This is an
        # endpoint correspondence only; it does not invent propagation through CTEs.
        fields_by_type: dict[str, dict[str, list[dict[str, str]]]] = defaultdict(lambda: defaultdict(list))
        for row in cc.execute(
            "SELECT effective_field_occurrence_id, effective_owner_type_occurrence_id, field_name "
            "FROM code_declared_effective_field ORDER BY effective_owner_type_occurrence_id, field_name"
        ).fetchall():
            fields_by_type[str(row[1])][str(row[2]).strip().lower()].append(
                {"effective_field_occurrence_id": str(row[0]), "field_name": str(row[2])}
            )

        mapped_relations: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in c.execute(
            "SELECT sql_relation_id, storage_alias, logical_type_occurrence_id, logical_fully_qualified_name, knowledge_class, mapping_basis "
            "FROM cross_artifact_storage_sql_mapping WHERE mapping_status='matched' ORDER BY sql_relation_id"
        ).fetchall():
            if row[2]:
                mapped_relations[str(row[0])].append({
                    "storage_alias": str(row[1]),
                    "type_id": str(row[2]),
                    "logical_fqcn": str(row[3] or ""),
                    "knowledge_class": str(row[4] or "derived"),
                    "mapping_basis": str(row[5] or ""),
                    "storage_key_variants": list(storage_key_variants_by_alias.get(str(row[1]), ())),
                })
        for row in sc.execute(
            "SELECT sql_column_usage_id, query_id, file, column_name, usage_role, relation_id, resolution_status "
            "FROM sql_column_usage WHERE relation_id IS NOT NULL AND column_name IS NOT NULL ORDER BY sql_column_usage_id"
        ).fetchall():
            usage_id, query_id, file, column_name, usage_role, relation_id, resolution_status = row
            for owner in mapped_relations.get(str(relation_id), ()):
                candidates = fields_by_type.get(owner["type_id"], {}).get(str(column_name).strip().lower(), ())
                if len(candidates) != 1:
                    continue
                field = candidates[0]
                c.execute(
                    "INSERT OR IGNORE INTO cross_artifact_logical_field_sql_usage VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [
                        stable_id("cross_artifact_logical_field_sql_usage", field["effective_field_occurrence_id"], usage_id),
                        owner["type_id"], owner["logical_fqcn"] or None,
                        field["effective_field_occurrence_id"], field["field_name"],
                        str(usage_id), str(relation_id), str(query_id), str(file), str(column_name), usage_role,
                        "matched", "derived", "unique_effective_field_name_to_observed_relation_column_casefold",
                        canonical_json({
                            "code_artifact_id": code.input_item.get("artifact_id"),
                            "logical_storage_artifact_id": logical_storage.input_item.get("artifact_id"),
                            "sql_artifact_id": sql.input_item.get("artifact_id"),
                            "sql_column_resolution_status": resolution_status,
                            "normalization": "unicode_casefold_equivalent_lowercase_only",
                        }),
                    ],
                )

        pdm_by_code: dict[str, list[dict[str, str]]] = defaultdict(list)
        for row in pc.execute(
            "SELECT physical_model_table_id, table_name, table_code FROM physical_model_table WHERE table_code IS NOT NULL ORDER BY physical_model_table_id"
        ).fetchall():
            pdm_by_code[str(row[2]).strip().lower()].append(
                {"id": str(row[0]), "name": str(row[1] or ""), "code": str(row[2])}
            )

        pdm_columns_by_table: dict[str, dict[str, list[dict[str, str]]]] = defaultdict(lambda: defaultdict(list))
        for row in pc.execute(
            "SELECT physical_model_column_id, physical_model_table_id, column_name, column_code "
            "FROM physical_model_column WHERE column_code IS NOT NULL ORDER BY physical_model_table_id, ordinal"
        ).fetchall():
            pdm_columns_by_table[str(row[1])][str(row[3]).strip().lower()].append({
                "id": str(row[0]), "name": str(row[2] or ""), "code": str(row[3]),
            })

        def add_sql_physical(kind: str, object_id: str, repo_id: str, name: str, context: str | None, provenance: Mapping[str, Any], basis: str) -> None:
            key = str(name or "").strip().lower()
            targets = pdm_by_code.get(key, ())
            if len(targets) != 1:
                return
            target = targets[0]
            c.execute(
                "INSERT OR IGNORE INTO cross_artifact_sql_physical_mapping VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    stable_id("cross_artifact_sql_physical_mapping", kind, object_id, target["id"]),
                    kind,
                    object_id,
                    repo_id,
                    name,
                    context,
                    target["id"],
                    target["name"],
                    target["code"],
                    "matched",
                    "derived",
                    basis,
                    canonical_json(dict(provenance)),
                ],
            )

        for row in sc.execute(
            "SELECT sql_relation_id, repo_id, logical_name, relation_name, usage_role, file, line_start "
            "FROM sql_relation WHERE logical_name IS NOT NULL AND relation_kind IN ('physical','physical_template') ORDER BY sql_relation_id"
        ).fetchall():
            add_sql_physical(
                "relation", str(row[0]), str(row[1]), str(row[2]), str(row[4] or ""),
                {"sql_artifact_id": sql.input_item.get("artifact_id"), "physical_artifact_id": physical.input_item.get("artifact_id"), "relation_name": row[3], "file": row[5], "line_start": row[6]},
                "unique_exact_sql_logical_name_to_pdm_table_code",
            )

        for row in sc.execute(
            "SELECT sql_write_target_id, repo_id, target_logical_name, target_relation_name, operation_kind, file, line_start "
            "FROM sql_write_target WHERE target_logical_name IS NOT NULL ORDER BY sql_write_target_id"
        ).fetchall():
            add_sql_physical(
                "write_target", str(row[0]), str(row[1]), str(row[2]), str(row[4] or ""),
                {"sql_artifact_id": sql.input_item.get("artifact_id"), "physical_artifact_id": physical.input_item.get("artifact_id"), "target_relation_name": row[3], "file": row[5], "line_start": row[6]},
                "unique_exact_write_target_logical_name_to_pdm_table_code",
            )

        for row in sc.execute(
            "SELECT sql_placeholder_binding_resolution_id, repo_id, resolved_value, placeholder, binding_name, binding_file, sql_file, resolution_status "
            "FROM sql_placeholder_binding_resolution WHERE resolved_value IS NOT NULL AND resolution_status='resolved' ORDER BY sql_placeholder_binding_resolution_id"
        ).fetchall():
            add_sql_physical(
                "resolved_binding", str(row[0]), str(row[1]), str(row[2]), f"{row[3]}:{row[4]}",
                {"sql_artifact_id": sql.input_item.get("artifact_id"), "physical_artifact_id": physical.input_item.get("artifact_id"), "placeholder": row[3], "binding_name": row[4], "binding_file": row[5], "sql_file": row[6]},
                "unique_exact_resolved_binding_value_to_pdm_table_code",
            )

        # Workflow-resolved transform-query projections -> declared PDM columns.
        # The SQL workflow context has already resolved dynamic script paths; we only
        # compose those observations with the root main-table binding and exact PDM codes.
        reference_by_id: dict[str, dict[str, Any]] = {}
        for row in sc.execute(
            "SELECT sql_workflow_file_reference_id, source_file, source_kind, source_fact_id, target_path_template, "
            "resolved_target_file, resolution_status, resolution_basis FROM sql_workflow_file_reference"
        ).fetchall():
            reference_by_id[str(row[0])] = {
                "source_file": row[1], "source_kind": row[2], "source_fact_id": row[3],
                "target_path_template": str(row[4] or ""), "resolved_file": row[5],
                "resolution_status": row[6], "resolution_basis": row[7],
            }

        main_table_by_workflow: dict[str, list[str]] = defaultdict(list)
        for row in sc.execute(
            "SELECT file, scalar_value, value_expression, resolution_status FROM sql_workflow_binding "
            "WHERE lower(binding_name)='main_table_name' ORDER BY file"
        ).fetchall():
            value = str(row[1] or row[2] or "").strip()
            if value and "$" not in value:
                main_table_by_workflow[str(row[0])].append(value)
        for key in list(main_table_by_workflow):
            main_table_by_workflow[key] = sorted(dict.fromkeys(main_table_by_workflow[key]))

        statement_by_file: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for row in sc.execute(
            "SELECT query_id, file, statement_type FROM sql_statement WHERE file IS NOT NULL ORDER BY file, line_start"
        ).fetchall():
            statement_by_file[str(row[1])].append((str(row[0]), str(row[2] or "")))

        for row in sc.execute(
            "SELECT workflow_context_file, reachable_file, context_reference_ids_json, resolution_status "
            "FROM sql_workflow_context_file WHERE reachable_file_kind='sql' AND resolution_status='resolved' "
            "ORDER BY workflow_context_file, context_hop_count, reachable_file"
        ).fetchall():
            workflow_file, reachable_file, refs_json, context_status = row
            main_values = main_table_by_workflow.get(str(workflow_file), ())
            if len(main_values) != 1:
                continue
            target_code = main_values[0]
            target_tables = pdm_by_code.get(target_code.strip().lower(), ())
            if len(target_tables) != 1:
                continue
            try:
                ref_ids = json.loads(refs_json or "[]")
            except Exception:
                ref_ids = []
            if not ref_ids:
                continue
            final_ref = reference_by_id.get(str(ref_ids[-1]))
            if not final_ref or final_ref.get("source_kind") != "script_invocation":
                continue
            template = str(final_ref.get("target_path_template") or "").lower()
            # The observed invocation itself must be parameterized by the root target identity.
            if "main_table_name" not in template:
                continue
            # The base file-reference may be unresolved before root workflow bindings are
            # applied.  sql_workflow_context_file is the contextual resolution result and
            # is therefore the authoritative evidence for the reached file here.
            target = target_tables[0]
            columns = pdm_columns_by_table.get(target["id"], {})
            for query_id, statement_type in statement_by_file.get(str(reachable_file), ()):
                if statement_type not in ("select", "query"):
                    continue
                root_scopes = [str(x[0]) for x in sc.execute(
                    "SELECT sql_select_scope_id FROM sql_select_scope WHERE query_id=? AND parent_scope_id IS NULL ORDER BY scope_ordinal",
                    [query_id],
                ).fetchall()]
                for root_scope in root_scopes:
                    for projection in sc.execute(
                        "SELECT sql_projection_id, output_name, expression, resolution_status FROM sql_projection "
                        "WHERE scope_id=? AND output_name IS NOT NULL AND is_wildcard=false ORDER BY projection_ordinal",
                        [root_scope],
                    ).fetchall():
                        projection_id, output_name, expression, projection_status = projection
                        candidates = columns.get(str(output_name).strip().lower(), ())
                        if len(candidates) != 1:
                            continue
                        column = candidates[0]
                        c.execute(
                            "INSERT OR IGNORE INTO cross_artifact_workflow_projection_physical_mapping VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                            [
                                stable_id("cross_artifact_workflow_projection_physical_mapping", workflow_file, query_id, projection_id, column["id"]),
                                str(workflow_file), target["code"], target["id"], column["id"], column["code"],
                                str(reachable_file), query_id, str(projection_id), str(output_name), expression,
                                "matched", "derived",
                                "resolved_workflow_transform_invocation_plus_main_table_binding_plus_exact_projection_to_pdm_column",
                                canonical_json({
                                    "sql_artifact_id": sql.input_item.get("artifact_id"),
                                    "physical_artifact_id": physical.input_item.get("artifact_id"),
                                    "workflow_context_resolution_status": context_status,
                                    "script_reference_id": str(ref_ids[-1]),
                                    "script_reference_resolution_basis": final_ref.get("resolution_basis"),
                                    "projection_resolution_status": projection_status,
                                }),
                            ],
                        )


        # Structured script calls are syntax evidence only.  Here they become
        # materialization knowledge only when the call exposes both an observed
        # SQL-path argument and an observed output-table argument and both can be
        # resolved from file-local + workflow-context bindings without similarity matching.
        sql_table_names = {str(row[0]) for row in sc.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='main'").fetchall()}
        file_rows = list(sc.execute("SELECT DISTINCT file FROM sql_statement WHERE file IS NOT NULL").fetchall())
        if "sql_script_statement" in sql_table_names:
            file_rows.extend(sc.execute("SELECT DISTINCT file FROM sql_script_statement WHERE file IS NOT NULL").fetchall())
        known_sql_files = sorted({str(row[0]) for row in file_rows if row[0]})
        local_bindings: dict[tuple[str, str], list[tuple[int, str]]] = defaultdict(list)
        if "sql_script_binding" in sql_table_names:
            for row in sc.execute(
                "SELECT file, line_start, binding_name, value_expression, scalar_value FROM sql_script_binding ORDER BY file, line_start"
            ).fetchall():
                file, line_start, name, value_expression, scalar_value = row
                value = str(scalar_value if scalar_value is not None else value_expression or "")
                local_bindings[(str(file), str(name or "").strip().lower())].append((int(line_start or 0), value))

        workflow_values: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
        for row in sc.execute(
            "SELECT file, binding_name, scalar_value, value_expression FROM sql_workflow_binding ORDER BY file, binding_name"
        ).fetchall():
            file, name, scalar_value, value_expression = row
            value = str(scalar_value if scalar_value is not None else value_expression or "").strip()
            if name and value:
                workflow_values[str(file)][str(name).strip().lstrip("$")].append(value)
        for file, values in workflow_values.items():
            for name in list(values):
                values[name] = sorted(dict.fromkeys(values[name]))

        # Explicit workflow-to-workflow dependency: a producer publishes an entity
        # identity through `entities`, while a consumer trigger waits for the same
        # identity (optionally with a stage/version suffix such as `.2`).  Both are
        # observed workflow bindings; no file-name similarity is involved.
        producer_entity_values: dict[str, list[str]] = defaultdict(list)
        consumer_trigger_values: dict[str, list[str]] = defaultdict(list)
        for row in sc.execute(
            "SELECT file, binding_name, scalar_value, value_expression, resolution_status "
            "FROM sql_workflow_binding WHERE lower(binding_name) IN ('entities','trigger') ORDER BY file, binding_name"
        ).fetchall():
            workflow_file, binding_name, scalar_value, value_expression, resolution_status = row
            value = str(scalar_value if scalar_value is not None else value_expression or "").strip()
            if not value:
                continue
            if str(binding_name or "").strip().lower() == "entities":
                producer_entity_values[str(workflow_file)].append(value)
            else:
                consumer_trigger_values[str(workflow_file)].append(value)

        producers_by_entity: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for producer_workflow, expressions in producer_entity_values.items():
            for expression in expressions:
                for identity in _workflow_identity_tokens(expression):
                    producers_by_entity[identity].append((producer_workflow, expression))

        for consumer_workflow, trigger_expressions in consumer_trigger_values.items():
            for trigger_expression in trigger_expressions:
                for identity in _workflow_identity_tokens(trigger_expression):
                    producers = sorted(dict.fromkeys(producers_by_entity.get(identity, ())))
                    resolution_status = "matched" if len(producers) == 1 else "ambiguous"
                    knowledge_class = "derived" if len(producers) == 1 else "candidate"
                    mapping_basis = (
                        "producer_entities_exact_consumer_trigger_identity"
                        if len(producers) == 1
                        else "nonunique_producer_entities_for_consumer_trigger_identity"
                    )
                    for producer_workflow, producer_expression in producers:
                        if producer_workflow == consumer_workflow:
                            continue
                        c.execute(
                            "INSERT OR IGNORE INTO cross_artifact_workflow_dependency VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                            [
                                stable_id("cross_artifact_workflow_dependency", producer_workflow, consumer_workflow, identity),
                                producer_workflow, consumer_workflow, identity, producer_expression, trigger_expression,
                                resolution_status, knowledge_class, mapping_basis,
                                canonical_json({
                                    "sql_artifact_id": sql.input_item.get("artifact_id"),
                                    "producer_binding": "entities",
                                    "consumer_binding": "trigger",
                                    "identity_normalization": "strip_numeric_trigger_stage_suffix_only",
                                    "producer_candidates": [item[0] for item in producers],
                                }),
                            ],
                        )

        workflow_roots_by_file: dict[str, set[str]] = defaultdict(set)
        for row in sc.execute(
            "SELECT workflow_context_file, reachable_file FROM sql_workflow_context_file WHERE resolution_status IN ('resolved','probable')"
        ).fetchall():
            workflow_roots_by_file[str(row[1])].add(str(row[0]))

        query_ids_by_file: dict[str, list[str]] = defaultdict(list)
        for row in sc.execute(
            "SELECT DISTINCT s.query_id, s.file FROM sql_statement s "
            "JOIN sql_select_scope scp ON scp.query_id=s.query_id "
            "WHERE s.file IS NOT NULL AND scp.parent_scope_id IS NULL ORDER BY s.file, s.query_id"
        ).fetchall():
            query_ids_by_file[str(row[1])].append(str(row[0]))

        def argument_key(value: str) -> str:
            return "".join(ch for ch in str(value or "").lower() if ch.isalnum())

        query_argument_keys = {"querypath", "sqlpath", "queryfile", "sqlfile", "sourcequerypath"}
        table_argument_keys = {"tablename", "targettable", "outputtable", "destinationtable"}

        script_call_rows = []
        if "sql_script_call" in sql_table_names:
            script_call_rows = sc.execute(
                "SELECT sql_script_call_id, file, line_start, call_symbol, named_arguments_json, evidence_json "
                "FROM sql_script_call ORDER BY file, line_start, sql_script_call_id"
            ).fetchall()
        for row in script_call_rows:
            call_id, script_file, line_start, call_symbol, named_json, call_evidence_json = row
            named = _json_value(named_json, {})
            if not isinstance(named, dict):
                continue
            query_args = [str(v) for k, v in named.items() if argument_key(k) in query_argument_keys]
            table_args = [str(v) for k, v in named.items() if argument_key(k) in table_argument_keys]
            if len(query_args) != 1 or len(table_args) != 1:
                continue
            roots = sorted(workflow_roots_by_file.get(str(script_file), ()))
            if not roots:
                continue
            for workflow_root in roots:
                context = workflow_values.get(workflow_root, {})
                query_variants, query_unresolved = _resolve_script_expression(
                    query_args[0], script_file=str(script_file), before_line=int(line_start or 0),
                    local_bindings=local_bindings, context_values=context,
                )
                table_variants, table_unresolved = _resolve_script_expression(
                    table_args[0], script_file=str(script_file), before_line=int(line_start or 0),
                    local_bindings=local_bindings, context_values=context,
                )
                query_files: set[str] = set()
                for variant in query_variants:
                    query_files.update(_match_sql_file_template(variant, known_sql_files, str(script_file)))
                output_tables = sorted({
                    _strip_script_literal(item).strip().split(".")[-1]
                    for item in table_variants
                    if item and not _placeholder_tokens(item)
                })
                if len(query_files) != 1 or len(output_tables) != 1:
                    continue
                query_file = next(iter(query_files))
                query_ids = query_ids_by_file.get(query_file, ())
                if len(query_ids) != 1:
                    continue
                query_id = query_ids[0]
                output_table = output_tables[0]
                c.execute(
                    "INSERT OR IGNORE INTO cross_artifact_relation_materialization VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [
                        stable_id("cross_artifact_relation_materialization", workflow_root, "script_call", call_id, query_id, output_table),
                        workflow_root, "script_call", str(script_file), str(call_id), str(call_symbol), query_file, query_id, None, output_table,
                        "matched", "derived",
                        "structured_script_call_plus_local_and_workflow_binding_resolution",
                        canonical_json({
                            "sql_artifact_id": sql.input_item.get("artifact_id"),
                            "query_argument": query_args[0], "output_table_argument": table_args[0],
                            "query_unresolved_placeholders": query_unresolved,
                            "output_unresolved_placeholders": table_unresolved,
                            "call_evidence": _json_value(call_evidence_json, []),
                            "semantic_rule": "one_query_path_argument_plus_one_output_table_argument",
                        }),
                    ],
                )

        # SQL write targets with an observed SELECT source are relation materializations too.
        # Use only Core-resolved target identities and explicit source scopes.
        if "sql_write_target" in sql_table_names:
            write_rows = sc.execute(
                "SELECT sql_write_target_id, file, query_id, operation_kind, target_relation_name, source_scope_ids_json, payload_json, evidence_json "
                "FROM sql_write_target WHERE source_scope_ids_json IS NOT NULL ORDER BY file, line_start, sql_write_target_id"
            ).fetchall()
            for write_id, write_file, query_id, operation_kind, target_name, source_scopes_json, write_payload_json, write_evidence_json in write_rows:
                source_scopes = [str(x) for x in _json_value(source_scopes_json, []) if x]
                if not source_scopes:
                    continue
                payload = _json_value(write_payload_json, {})
                resolved_target = str((payload if isinstance(payload, dict) else {}).get("resolved_target_relation_name") or target_name or "").strip()
                if not resolved_target or _placeholder_tokens(resolved_target):
                    continue
                output_table = resolved_target.split(".")[-1]
                roots = sorted(workflow_roots_by_file.get(str(write_file), ()))
                if not roots:
                    continue
                for workflow_root in roots:
                    c.execute(
                        "INSERT OR IGNORE INTO cross_artifact_relation_materialization VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        [
                            stable_id("cross_artifact_relation_materialization", workflow_root, "sql_write", write_id, query_id, output_table),
                            workflow_root, "sql_write", str(write_file), str(write_id), str(operation_kind or "sql_write"),
                            str(write_file), str(query_id or ""), None, output_table, "matched", "derived",
                            "observed_sql_write_target_with_resolved_target_and_source_scope",
                            canonical_json({
                                "sql_artifact_id": sql.input_item.get("artifact_id"),
                                "source_scope_ids": source_scopes,
                                "resolved_target_relation_name": resolved_target,
                                "write_evidence": _json_value(write_evidence_json, []),
                            }),
                        ],
                    )

        # Workflow configs may publish explicit source-to-target table movement
        # independently of a SQL query (for example a staging table copied into
        # a persistent auxiliary table).  Compose only the observed s2tTableList
        # contract; do not infer movement from naming conventions.
        if "sql_workflow_binding" in sql_table_names:
            movement_rows = sc.execute(
                "SELECT sql_workflow_binding_id, file, line_start, binding_name, scalar_value, evidence_json "
                "FROM sql_workflow_binding "
                "WHERE lower(binding_name)='s2ttablelist' AND scalar_value IS NOT NULL "
                "ORDER BY file, line_start, sql_workflow_binding_id"
            ).fetchall()
            for binding_id, binding_file, binding_line, binding_name, scalar_value, binding_evidence_json in movement_rows:
                roots = sorted(workflow_roots_by_file.get(str(binding_file), ()))
                if str(binding_file) in workflow_values and str(binding_file) not in roots:
                    roots.append(str(binding_file))
                for workflow_root in roots:
                    context = workflow_values.get(workflow_root, {})
                    variants, unresolved = _resolve_script_expression(
                        str(scalar_value), script_file=str(binding_file), before_line=int(binding_line or 0),
                        local_bindings=local_bindings, context_values=context,
                    )
                    resolved_pairs: set[tuple[str, str]] = set()
                    for variant in variants:
                        if _placeholder_tokens(variant):
                            continue
                        for pair_text in str(variant).split(";"):
                            if pair_text.count("->") != 1:
                                continue
                            source_table, output_table = [part.strip().split(".")[-1] for part in pair_text.split("->", 1)]
                            if not source_table or not output_table or source_table.lower() == output_table.lower():
                                continue
                            resolved_pairs.add((source_table, output_table))
                    for source_table, output_table in sorted(resolved_pairs):
                        c.execute(
                            "INSERT OR IGNORE INTO cross_artifact_relation_materialization VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                            [
                                stable_id("cross_artifact_relation_materialization", workflow_root, "workflow_copy", binding_id, source_table, output_table),
                                workflow_root, "workflow_copy", str(binding_file), str(binding_id), str(binding_name),
                                None, None, source_table, output_table, "matched", "derived",
                                "observed_workflow_s2t_table_list",
                                canonical_json({
                                    "sql_artifact_id": sql.input_item.get("artifact_id"),
                                    "source_expression": str(scalar_value),
                                    "unresolved_placeholders": unresolved,
                                    "binding_evidence": _json_value(binding_evidence_json, []),
                                    "semantic_rule": "observed_s2t_table_list_source_to_target_pair",
                                }),
                            ],
                        )

        if int(c.execute("SELECT count(*) FROM cross_artifact_relation_materialization").fetchone()[0]) > 0:
            # Build a strict projection dependency traversal.  Explicit output names are
            # preferred. Wildcard pass-through is allowed only when its source relation
            # is observed uniquely; this preserves SQL semantics without name guessing.
            usage_by_id: dict[str, dict[str, Any]] = {}
            relation_column_roles: dict[tuple[str, str], set[str]] = defaultdict(set)
            for row in sc.execute(
                "SELECT sql_column_usage_id, query_id, scope_id, file, column_name, table_or_alias, relation_id, relation_kind, relation_name, resolution_status, resolution_basis, usage_role "
                "FROM sql_column_usage ORDER BY sql_column_usage_id"
            ).fetchall():
                usage_by_id[str(row[0])] = {
                    "id": str(row[0]), "query_id": str(row[1]), "scope_id": str(row[2]), "file": str(row[3]),
                    "column": str(row[4] or ""), "table_or_alias": row[5], "relation_id": str(row[6]) if row[6] else None,
                    "relation_kind": row[7], "relation_name": row[8], "resolution_status": row[9], "resolution_basis": row[10],
                    "usage_role": str(row[11] or ""),
                }
                if row[6] and row[4] and row[11]:
                    relation_column_roles[(str(row[6]), str(row[4]).strip().lower())].add(str(row[11]))

            relation_by_id: dict[str, dict[str, Any]] = {}
            relations_by_scope: dict[str, list[str]] = defaultdict(list)
            for row in sc.execute(
                "SELECT sql_relation_id, query_id, scope_id, relation_kind, relation_name, logical_name, alias, source_scope_ids_json, file, payload_json "
                "FROM sql_relation ORDER BY sql_relation_id"
            ).fetchall():
                relation_payload = _json_value(row[9], {})
                relation = {
                    "id": str(row[0]), "query_id": str(row[1]), "scope_id": str(row[2]), "kind": str(row[3] or ""),
                    "name": str(row[4] or ""), "logical": str(row[5] or ""), "alias": row[6],
                    "source_scopes": [str(x) for x in _json_value(row[7], [])], "file": str(row[8] or ""),
                    "output_columns": [str(x) for x in relation_payload.get("output_columns") or []],
                    "output_contract_status": str(relation_payload.get("output_contract_status") or ""),
                    "output_contract_basis": str(relation_payload.get("output_contract_basis") or ""),
                }
                relation_by_id[relation["id"]] = relation
                relations_by_scope[relation["scope_id"]].append(relation["id"])

            projection_by_id: dict[str, dict[str, Any]] = {}
            projections_by_scope: dict[str, list[str]] = defaultdict(list)
            for row in sc.execute(
                "SELECT sql_projection_id, query_id, scope_id, file, output_name, expression, is_wildcard, source_column_usage_ids_json, resolution_status "
                "FROM sql_projection ORDER BY query_id, scope_id, projection_ordinal"
            ).fetchall():
                projection = {
                    "id": str(row[0]), "query_id": str(row[1]), "scope_id": str(row[2]), "file": str(row[3]),
                    "output": str(row[4] or ""), "expression": row[5], "wildcard": bool(row[6]),
                    "source_usages": [str(x) for x in _json_value(row[7], [])], "resolution_status": row[8],
                }
                projection_by_id[projection["id"]] = projection
                projections_by_scope[projection["scope_id"]].append(projection["id"])

            scope_output_contracts: dict[str, dict[str, Any]] = {}
            root_scopes_by_query: dict[str, list[str]] = defaultdict(list)
            for row in sc.execute(
                "SELECT sql_select_scope_id, query_id, parent_scope_id, payload_json FROM sql_select_scope ORDER BY query_id, scope_ordinal"
            ).fetchall():
                scope_id = str(row[0])
                scope_payload = _json_value(row[3], {})
                scope_output_contracts[scope_id] = {
                    "output_columns": [str(x) for x in scope_payload.get("output_columns") or []],
                    "output_contract_status": str(scope_payload.get("output_contract_status") or ""),
                    "output_contract_basis": str(scope_payload.get("output_contract_basis") or ""),
                }
                if row[2] is None:
                    root_scopes_by_query[str(row[1])].append(scope_id)

            materializations_by_context_table: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
            for row in c.execute(
                "SELECT materialization_id, workflow_context_file, materialization_kind, source_file, source_fact_id, source_symbol, "
                "query_file, query_id, source_table_name, output_table_name, provenance_json "
                "FROM cross_artifact_relation_materialization ORDER BY materialization_id"
            ).fetchall():
                provenance = _json_value(row[10], {})
                materializations_by_context_table[(str(row[1]), str(row[9]).strip().lower())].append({
                    "id": str(row[0]), "workflow": str(row[1]), "kind": str(row[2]), "source_file": str(row[3]),
                    "source_fact_id": str(row[4]), "source_symbol": str(row[5] or ""),
                    "query_file": str(row[6] or ""), "query_id": str(row[7] or ""),
                    "source_table": str(row[8] or ""), "table": str(row[9]),
                    "source_scopes": [str(x) for x in (provenance.get("source_scope_ids") or [])] if isinstance(provenance, dict) else [],
                })

            workflow_dependencies = [
                (str(row[1]), str(row[2]), str(row[0]))
                for row in c.execute(
                    "SELECT dependency_id, producer_workflow_context_file, consumer_workflow_context_file "
                    "FROM cross_artifact_workflow_dependency WHERE resolution_status='matched' "
                    "ORDER BY consumer_workflow_context_file, producer_workflow_context_file"
                ).fetchall()
            ]
            materialization_index = ObservedMaterializationIndex(
                materializations=[item for values in materializations_by_context_table.values() for item in values],
                workflow_dependencies=workflow_dependencies,
                root_scopes_by_query=root_scopes_by_query,
                scope_output_contracts=scope_output_contracts,
            )

            def materialization_producers(workflow_context: str, logical_name: str) -> list[tuple[dict[str, Any], tuple[str, ...]]]:
                return materialization_index.producers(workflow_context, logical_name)

            def materialization_output_contract(
                producer: Mapping[str, Any], seen: tuple[str, ...] = ()
            ) -> tuple[set[str] | None, str]:
                return materialization_index.output_contract(producer, seen)

            known_relation_output_contract_cache: dict[tuple[str, str], tuple[set[str] | None, str]] = {}
            def known_relation_output_contract(
                workflow_context: str, relation_id: str
            ) -> tuple[set[str] | None, str]:
                cache_key = (workflow_context, relation_id)
                if cache_key in known_relation_output_contract_cache:
                    return known_relation_output_contract_cache[cache_key]
                """Return a complete observed cross-artifact output contract when available.

                This deliberately composes existing evidence instead of asking the SQL parser
                to guess schemas for joined relations.  Contracts may come from a complete
                CTE/derived output, an exact logical-storage type, or an observed local script
                materialization whose root SELECT has a complete output contract.
                """
                relation = relation_by_id.get(relation_id)
                if relation is None:
                    result = (None, "relation_missing"); known_relation_output_contract_cache[cache_key] = result; return result
                if relation.get("output_contract_status") == "complete":
                    result = ({str(x).strip().lower() for x in relation.get("output_columns") or ()}, "relation_output_contract"); known_relation_output_contract_cache[cache_key] = result; return result

                owners = mapped_relations.get(relation_id, ())
                if len(owners) == 1:
                    owner = owners[0]
                    type_id = str(owner.get("type_id") or "")
                    field_names = set(fields_by_type.get(type_id, {}).keys())
                    # `key` is an observed storage identity even when it is not a Java field.
                    field_names.add("key")
                    result = (field_names, "logical_storage_effective_field_contract"); known_relation_output_contract_cache[cache_key] = result; return result

                if relation.get("kind") in {"physical", "physical_template"}:
                    logical_name = (str(relation.get("logical") or "") or str(relation.get("name") or "").split(".")[-1]).strip().lower()
                    producers = materialization_producers(workflow_context, logical_name)
                    if producers:
                        contracts: list[set[str]] = []
                        bases: list[str] = []
                        for producer, _dependency_path in producers:
                            contract, basis = materialization_output_contract(producer)
                            if contract is None:
                                result = (None, basis); known_relation_output_contract_cache[cache_key] = result; return result
                            contracts.append(contract)
                            bases.append(basis)
                        if contracts:
                            result = (set().union(*contracts), "+".join(sorted(set(bases)))); known_relation_output_contract_cache[cache_key] = result; return result
                result = (None, "output_contract_unavailable"); known_relation_output_contract_cache[cache_key] = result; return result

            inferred_unqualified_relation_cache: dict[tuple[str, str], tuple[dict[str, Any] | None, dict[str, Any] | None]] = {}
            def infer_unqualified_relation(
                workflow_context: str, usage: Mapping[str, Any]
            ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
                cache_key = (workflow_context, str(usage.get("id") or ""))
                if cache_key in inferred_unqualified_relation_cache:
                    return inferred_unqualified_relation_cache[cache_key]
                if usage.get("relation_id") or usage.get("table_or_alias"):
                    return None, None
                if str(usage.get("resolution_status") or "") not in {"ambiguous", "unresolved"}:
                    return None, None
                column_name = str(usage.get("column") or "").strip().lower()
                if not column_name:
                    return None, None

                positive: list[tuple[dict[str, Any], str]] = []
                unknown: list[dict[str, Any]] = []
                negative_count = 0
                for relation_id in relations_by_scope.get(str(usage.get("scope_id") or ""), ()):
                    relation = relation_by_id.get(relation_id)
                    if relation is None or relation.get("kind") == "generated":
                        continue
                    contract, basis = known_relation_output_contract(workflow_context, relation_id)
                    if contract is None:
                        unknown.append(relation)
                    elif column_name in contract:
                        positive.append((relation, basis))
                    else:
                        negative_count += 1
                if len(positive) != 1:
                    result = (None, None)
                    inferred_unqualified_relation_cache[cache_key] = result
                    return result

                relation, contract_basis = positive[0]
                if not unknown:
                    knowledge_class = "derived"
                    basis = "unique_complete_cross_artifact_relation_output_contract"
                elif relation.get("kind") in {"cte", "derived"}:
                    # An opaque joined relation may still expose the same unqualified column.
                    # Preserve that uncertainty as a candidate diagnostic, but never traverse it.
                    candidate = {
                        "usage_id": str(usage.get("id") or ""),
                        "column_name": str(usage.get("column") or ""),
                        "scope_id": str(usage.get("scope_id") or ""),
                        "relation_id": str(relation.get("id") or ""),
                        "relation_name": str(relation.get("name") or ""),
                        "knowledge_class": "candidate",
                        "resolution_basis": "unique_known_intermediate_output_contract_with_opaque_join_relations",
                        "contract_basis": contract_basis,
                        "negative_relation_count": negative_count,
                        "opaque_relation_ids": [str(item.get("id") or "") for item in unknown],
                    }
                    result = (None, candidate)
                    inferred_unqualified_relation_cache[cache_key] = result
                    return result
                else:
                    result = (None, None)
                    inferred_unqualified_relation_cache[cache_key] = result
                    return result
                result = (relation, {
                    "usage_id": str(usage.get("id") or ""),
                    "column_name": str(usage.get("column") or ""),
                    "scope_id": str(usage.get("scope_id") or ""),
                    "relation_id": str(relation.get("id") or ""),
                    "relation_name": str(relation.get("name") or ""),
                    "knowledge_class": knowledge_class,
                    "resolution_basis": basis,
                    "contract_basis": contract_basis,
                    "negative_relation_count": negative_count,
                    "opaque_relation_ids": [str(item.get("id") or "") for item in unknown],
                })
                inferred_unqualified_relation_cache[cache_key] = result
                return result

            logical_by_usage: dict[str, list[dict[str, str]]] = defaultdict(list)
            for row in c.execute(
                "SELECT sql_column_usage_id, logical_type_occurrence_id, logical_fully_qualified_name, effective_field_occurrence_id, logical_field_name, sql_file, sql_column_name "
                "FROM cross_artifact_logical_field_sql_usage ORDER BY sql_column_usage_id"
            ).fetchall():
                logical_by_usage[str(row[0])].append({
                    "type_id": str(row[1]), "fqcn": str(row[2] or ""), "field_id": str(row[3]), "field": str(row[4]),
                    "sql_file": str(row[5]), "sql_column": str(row[6]),
                })

            producer_traversal = SqlProducerColumnTraversal(
                usages=usage_by_id,
                relations=relation_by_id,
                relations_by_scope=relations_by_scope,
                projections=projection_by_id,
                projections_by_scope=projections_by_scope,
                root_scopes_by_query=root_scopes_by_query,
                materializations=materialization_index,
            )

            for target in c.execute(
                "SELECT workflow_context_file, target_table_code, physical_model_table_id, physical_model_column_id, physical_column_code, "
                "transform_sql_file, transform_query_id, projection_id, projection_expression "
                "FROM cross_artifact_workflow_projection_physical_mapping ORDER BY target_table_code, physical_column_code"
            ).fetchall():
                workflow_file, target_table, pdm_table_id, pdm_column_id, pdm_column, transform_file, transform_query, target_projection_id, target_expression = target
                projection = projection_by_id.get(str(target_projection_id))
                if not projection:
                    continue
                raw_origins = producer_traversal.projection_origins(str(workflow_file), projection)
                origins = [item for item in raw_origins if not item.get("frontier_usage_id")]
                frontiers = [item for item in raw_origins if item.get("frontier_usage_id")]
                if not origins and frontiers:
                    queue = list(frontiers)
                    seen_frontiers: set[tuple[str, str]] = set()
                    while queue and len(seen_frontiers) < 64:
                        frontier = queue.pop(0)
                        frontier_usage_id = str(frontier.get("frontier_usage_id") or "")
                        frontier_workflow = str(frontier.get("frontier_workflow_context") or workflow_file)
                        frontier_key = (frontier_workflow, frontier_usage_id)
                        if not frontier_usage_id or frontier_key in seen_frontiers:
                            continue
                        seen_frontiers.add(frontier_key)
                        frontier_usage = usage_by_id.get(frontier_usage_id)
                        if not frontier_usage:
                            continue
                        inferred_relation, derived_resolution = infer_unqualified_relation(frontier_workflow, frontier_usage)
                        if inferred_relation is None:
                            if derived_resolution and derived_resolution.get("knowledge_class") == "candidate":
                                c.execute(
                                    "INSERT OR IGNORE INTO cross_artifact_mapping_gap VALUES (?, ?, ?, ?, ?, ?, ?)",
                                    [
                                        stable_id("cross_artifact_mapping_gap", "unqualified_column_owner_candidate", str(target_projection_id), frontier_usage_id),
                                        "unqualified_column_owner_candidate", "warning", "target_projection", str(target_projection_id),
                                        "One observed intermediate relation can supply the unqualified column, but opaque joined relations prevent a unique proof.",
                                        canonical_json({
                                            "target_table_code": str(target_table),
                                            "physical_column_code": str(pdm_column),
                                            "workflow_context_file": str(workflow_file),
                                            "transform_sql_file": str(transform_file),
                                            "frontier": derived_resolution,
                                        }),
                                    ],
                                )
                            continue
                        if derived_resolution is None:
                            continue
                        continued = producer_traversal.relation_column_origins(
                            frontier_workflow, str(inferred_relation["id"]), str(frontier_usage.get("column") or ""),
                            tuple(frontier.get("frontier_trail") or ()),
                            tuple(frontier.get("materialization_path") or ()),
                            tuple(frontier.get("workflow_dependency_path") or ()),
                        )
                        for item in continued:
                            if item.get("frontier_usage_id"):
                                queue.append(item)
                                continue
                            item.setdefault("column_resolution_path", []).append(derived_resolution)
                            origins.append(item)
                for origin in origins:
                    usage_id = origin.get("usage_id")
                    relation_id = str(origin.get("relation_id") or "")
                    column_name = str(origin.get("column") or "")
                    source_relation = relation_by_id.get(relation_id) or {}
                    source_file = str(origin.get("source_file") or source_relation.get("file") or "")
                    source_relation_name = str(source_relation.get("name") or "")
                    source_relation_kind = str(source_relation.get("kind") or "")
                    source_usage = usage_by_id.get(str(usage_id)) if usage_id else None
                    projection_ids = [
                        str(marker).split("projection:", 1)[1]
                        for marker in origin.get("projection_path") or ()
                        if str(marker).startswith("projection:")
                    ]
                    transformation_path = [
                        {
                            "projection_id": projection_id,
                            "output_name": projection_by_id.get(projection_id, {}).get("output") or None,
                            "expression": projection_by_id.get(projection_id, {}).get("expression"),
                            "resolution_status": projection_by_id.get(projection_id, {}).get("resolution_status"),
                        }
                        for projection_id in projection_ids
                    ]
                    if relation_id and source_relation_name and column_name:
                        target_source_values = [
                            stable_id(
                                "cross_artifact_target_source_mapping", str(workflow_file), str(pdm_column_id),
                                str(target_projection_id), relation_id, column_name,
                                canonical_json(origin.get("materialization_path") or []),
                            ),
                            str(workflow_file), str(target_table), str(pdm_table_id), str(pdm_column_id), str(pdm_column),
                            str(transform_file), str(transform_query), str(target_projection_id), target_expression,
                            str(usage_id) if usage_id else None, relation_id, source_relation_name, source_relation_kind, column_name, source_file,
                            str((source_usage or {}).get("usage_role") or "") or None,
                            "matched", str(origin.get("knowledge_class") or "derived"),
                            "observed_target_projection_plus_recursive_observed_relation_producer_lineage",
                            canonical_json(origin.get("projection_path") or []),
                            canonical_json(transformation_path),
                            canonical_json(origin.get("materialization_path") or []),
                            canonical_json(origin.get("workflow_dependency_path") or []),
                            canonical_json({
                                "sql_artifact_id": sql.input_item.get("artifact_id"),
                                "physical_artifact_id": physical.input_item.get("artifact_id"),
                                "terminal_relation_has_observed_local_producer": False,
                                "column_resolution_path": origin.get("column_resolution_path") or [],
                            }),
                        ]
                        c.execute(
                            "INSERT OR IGNORE INTO cross_artifact_target_source_mapping VALUES ("
                            + ",".join("?" for _ in target_source_values) + ")",
                            target_source_values,
                        )
                    logical_candidates = list(logical_by_usage.get(str(usage_id), ())) if usage_id else []
                    if not logical_candidates:
                        for owner in mapped_relations.get(relation_id, ()):
                            field_candidates = fields_by_type.get(owner["type_id"], {}).get(column_name.strip().lower(), ())
                            if len(field_candidates) != 1:
                                continue
                            field = field_candidates[0]
                            logical_candidates.append({
                                "type_id": owner["type_id"], "fqcn": owner.get("logical_fqcn") or "",
                                "field_id": field["effective_field_occurrence_id"], "field": field["field_name"],
                                "sql_file": source_file,
                                "sql_column": column_name,
                            })

                    # Canonical value-origin lineage contains ordinary logical fields as
                    # one origin kind. Storage identities are separate facts rather than
                    # synthetic Java fields.
                    for logical in logical_candidates:
                        origin_identity = (str(logical.get("fqcn") or logical["type_id"]) + "." + str(logical["field"]))
                        lineage_values = [
                            stable_id("cross_artifact_value_origin_physical_lineage", "logical_field", logical["field_id"], target_projection_id, pdm_column_id, usage_id or (relation_id + ":" + column_name)),
                            "logical_field", origin_identity,
                            logical["type_id"], logical["fqcn"] or None, logical["field_id"], logical["field"],
                            None, None, None,
                            str(usage_id) if usage_id else None, relation_id or None, logical["sql_file"], logical["sql_column"],
                            str(workflow_file), str(target_table), str(pdm_table_id), str(pdm_column_id), str(pdm_column),
                            str(transform_file), str(transform_query), str(target_projection_id), target_expression,
                            str(origin.get("knowledge_class") or "derived"),
                            (
                                "observed_logical_source_usage_plus_exact_sql_projection_and_materialization_path_plus_exact_pdm_target"
                                + ("_plus_schema_aware_unqualified_column_resolution" if origin.get("column_resolution_path") else "")
                            ),
                            canonical_json({"origin_kind": "logical_field"}),
                            canonical_json(origin.get("projection_path") or []), canonical_json(origin.get("materialization_path") or []),
                            canonical_json(origin.get("workflow_dependency_path") or []),
                            canonical_json({
                                "code_artifact_id": code.input_item.get("artifact_id"),
                                "logical_storage_artifact_id": logical_storage.input_item.get("artifact_id"),
                                "sql_artifact_id": sql.input_item.get("artifact_id"),
                                "physical_artifact_id": physical.input_item.get("artifact_id"),
                                "column_resolution_path": origin.get("column_resolution_path") or [],
                            }),
                        ]
                        c.execute(
                            "INSERT OR IGNORE INTO cross_artifact_value_origin_physical_lineage VALUES (" + ",".join("?" for _ in lineage_values) + ")",
                            lineage_values,
                        )

                    if logical_candidates:
                        continue

                    # If the terminal SQL column is the exact observed storage-key field,
                    # preserve that value origin even though no logical Java field exists.
                    # The semantic subtype is derived only from observed SQL use along the
                    # same proof path: JOIN -> reference key, existence CASE -> presence.
                    for owner in mapped_relations.get(relation_id, ()):
                        matching_variants = [
                            item for item in owner.get("storage_key_variants") or ()
                            if str(item.get("storage_key_field") or "").strip().lower() == column_name.strip().lower()
                        ]
                        if not matching_variants:
                            continue
                        expressions = sorted({str(item.get("storage_key_expression") or "") for item in matching_variants if item.get("storage_key_expression")})
                        projection_expressions: list[str] = []
                        for marker in origin.get("projection_path") or ():
                            marker_text = str(marker)
                            projection_id = marker_text.split("projection:", 1)[1] if marker_text.startswith("projection:") else marker_text
                            item = projection_by_id.get(projection_id)
                            if item and item.get("expression"):
                                projection_expressions.append(str(item["expression"]))
                        if target_expression:
                            projection_expressions.append(str(target_expression))
                        expression_text = "\n".join(projection_expressions).lower()
                        observed_roles = sorted(relation_column_roles.get((relation_id, column_name.strip().lower()), set()))
                        existence_semantics = (
                            "case" in expression_text
                            and (" is null" in expression_text or " is not null" in expression_text or "not " in expression_text and " is null" in expression_text)
                        )
                        if existence_semantics:
                            origin_kind = "object_presence"
                            semantic_basis = "observed_storage_identity_used_by_existence_projection"
                        elif "join" in observed_roles:
                            origin_kind = "reference_key"
                            semantic_basis = "observed_storage_identity_used_as_sql_join_key"
                        else:
                            origin_kind = "storage_identity"
                            semantic_basis = "observed_storage_identity"
                        storage_alias = str(owner.get("storage_alias") or owner.get("logical_fqcn") or "")
                        key_field = str(matching_variants[0].get("storage_key_field") or column_name)
                        key_expression = expressions[0] if len(expressions) == 1 else (canonical_json(expressions) if expressions else None)
                        origin_identity = storage_alias + "." + key_field
                        knowledge_class = str(owner.get("knowledge_class") or origin.get("knowledge_class") or "derived")
                        lineage_values = [
                            stable_id("cross_artifact_value_origin_physical_lineage", origin_kind, origin_identity, target_projection_id, pdm_column_id, usage_id or (relation_id + ":" + column_name)),
                            origin_kind, origin_identity,
                            owner.get("type_id") or None, owner.get("logical_fqcn") or None, None, None,
                            storage_alias, key_field, key_expression,
                            str(usage_id) if usage_id else None, relation_id or None, source_file, column_name,
                            str(workflow_file), str(target_table), str(pdm_table_id), str(pdm_column_id), str(pdm_column),
                            str(transform_file), str(transform_query), str(target_projection_id), target_expression,
                            knowledge_class,
                            "observed_storage_key_field_plus_exact_storage_sql_mapping_plus_observed_sql_projection_path_plus_exact_pdm_target_plus_" + semantic_basis,
                            canonical_json({
                                "origin_kind": origin_kind,
                                "semantic_basis": semantic_basis,
                                "observed_sql_usage_roles": observed_roles,
                                "storage_key_expression_variants": expressions,
                                "projection_expressions": projection_expressions,
                            }),
                            canonical_json(origin.get("projection_path") or []), canonical_json(origin.get("materialization_path") or []),
                            canonical_json(origin.get("workflow_dependency_path") or []),
                            canonical_json({
                                "logical_storage_artifact_id": logical_storage.input_item.get("artifact_id"),
                                "sql_artifact_id": sql.input_item.get("artifact_id"),
                                "physical_artifact_id": physical.input_item.get("artifact_id"),
                                "storage_sql_mapping_basis": owner.get("mapping_basis") or "",
                                "column_resolution_path": origin.get("column_resolution_path") or [],
                            }),
                        ]
                        c.execute(
                            "INSERT OR IGNORE INTO cross_artifact_value_origin_physical_lineage VALUES (" + ",".join("?" for _ in lineage_values) + ")",
                            lineage_values,
                        )

        counts = _counts(c)
        checks = {
            "storage_sql_fuzzy_matching_used": False,
            "storage_sql_normalization_is_explicit": True,
            "sql_physical_requires_unique_exact_table_code": True,
            "logical_field_sql_usage_requires_exact_casefolded_field_name": True,
            "workflow_projection_mapping_requires_context_resolved_dynamic_invocation": True,
            "workflow_projection_mapping_requires_exact_pdm_column_code": True,
            "select_cte_recursive_field_propagation_invented": False,
            "select_cte_recursive_field_propagation_materialized_from_observed_graph": True,
            "relation_materialization_supports_structured_script_calls_and_workflow_copy": True,
            "unqualified_column_resolution_uses_cross_artifact_output_contracts": True,
            "unqualified_column_resolution_continues_only_from_observed_unresolved_frontiers": True,
            "unqualified_column_resolution_does_not_traverse_opaque_join_candidates": True,
            "cross_workflow_lineage_requires_exact_entities_to_trigger_dependency": True,
            "cross_workflow_materialization_prefers_same_context_then_nearest_upstream": True,
            "target_source_mapping_uses_recursive_observed_relation_producers": True,
            "target_source_mapping_does_not_require_logical_model_source_binding": True,
            "value_origin_storage_identity_requires_observed_storage_key_field": True,
            "value_origin_reference_key_requires_observed_join_role": True,
            "value_origin_object_presence_requires_observed_existence_projection": True,
            "logical_field_is_one_value_origin_kind_not_a_parallel_lineage_model": True,
            "ucp_or_datamart_specific_names_hardcoded": False,
        }
        completed = utc_now()
        c.execute(
            "UPDATE cross_artifact_mapping_build SET completed_at=?,build_status='complete',counts_json=?,checks_json=? WHERE build_id=?",
            [completed, canonical_json(counts), canonical_json(checks), build_id],
        )
        c.execute("COMMIT")
        transaction_started = False
        c.execute("CHECKPOINT")
        c.close(); c = None
        ls.close(); ls = None
        cc.close(); cc = None
        sc.close(); sc = None
        pc.close(); pc = None
        repos = tuple(sorted(set(sql.manifest.get("repository_ids") or ()) | set(logical_storage.manifest.get("repository_ids") or ())))
        manifest = KnowledgeLayerManifest(
            scope_id=scope_id,
            repository_ids=repos,
            modes=("data-model",),
            producer_version=__version__,
            build_id=build_id,
            build_status="complete",
            counts=counts,
            materialized_marts=("cross-artifact-storage-sql-mapping", "cross-artifact-logical-field-sql-usage", "cross-artifact-workflow-dependency", "cross-artifact-relation-materialization", "cross-artifact-value-origin-physical-lineage", "cross-artifact-target-source-mapping", "cross-artifact-workflow-projection-physical-mapping", "cross-artifact-sql-physical-mapping"),
            capabilities=("common.cross-artifact-data-model-mapping", "common.storage-sql-correspondence", "common.logical-field-sql-usage", "common.workflow-dependency", "common.relation-materialization", "common.value-origin-physical-lineage", "common.sql-target-source-mapping", "common.workflow-projection-physical-correspondence", "common.sql-physical-correspondence"),
            artifacts={"database": CROSS_ARTIFACT_DATABASE, "manifest": "knowledge-layer-manifest.json"},
            source_evidence=(),
            validation_status="complete",
            validation=checks,
            metadata={
                "cross_artifact_schema_version": CROSS_ARTIFACT_SCHEMA_VERSION,
                "started_at": started,
                "completed_at": completed,
                "logical_storage_input_artifact_id": logical_storage.input_item.get("artifact_id"),
                "code_declared_input_artifact_id": code.input_item.get("artifact_id"),
                "sql_input_artifact_id": sql.input_item.get("artifact_id"),
                "physical_input_artifact_id": physical.input_item.get("artifact_id"),
            },
        )
        write_manifest(staging / "knowledge-layer-manifest.json", manifest)
        publish_directory_atomic(staging, output_path, replace=replace, existing_label="knowledge-layer output")
        return manifest.to_dict()
    except Exception:
        if c is not None and transaction_started:
            with suppress(Exception):
                c.execute("ROLLBACK")
        for conn in (ls, cc, sc, pc, c):
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass
        remove_path(staging)
        raise
