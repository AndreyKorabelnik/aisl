from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import ast
import json
import re
from typing import Any, Mapping, Sequence

from prepared_knowledge_runtime.normalization import stable_id
from .sql_producer_lineage import ObservedMaterializationIndex, SqlProducerColumnTraversal


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
    pattern = re.compile(r"\$\{\s*\$?(?P<braced>[^{}]+?)\s*\}|(?<![A-Za-z0-9$])\$(?P<bare>[A-Za-z_][A-Za-z0-9_.]*)")
    return [str(m.group("braced") or m.group("bare") or "").strip().lstrip("$") for m in pattern.finditer(str(text or ""))]


def _replace_placeholder(text: str, name: str, value: str) -> str:
    escaped = re.escape(name)
    return re.sub(r"\$\{\s*\$?" + escaped + r"\s*\}|(?<![A-Za-z0-9$])\$" + escaped + r"\b", lambda _m: value, text)


def _strip_script_literal(value: str) -> str:
    text = str(value or "").strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        return text[1:-1]
    return text


def _literal_string_list(value: str) -> list[str]:
    """Return only an exactly observed literal list of scalar strings.

    This is deliberately not a DSL evaluator.  ``ast.literal_eval`` is used only
    for Python-compatible literal syntax and the result is accepted only when it
    is a non-empty list/tuple consisting entirely of strings.  Any expression,
    placeholder or computed item stays unresolved.
    """
    text = str(value or "").strip()
    if not (text.startswith("[") and text.endswith("]")):
        return []
    try:
        parsed = ast.literal_eval(text)
    except (SyntaxError, ValueError):
        return []
    if not isinstance(parsed, (list, tuple)) or not parsed or not all(isinstance(item, str) for item in parsed):
        return []
    return list(dict.fromkeys(str(item) for item in parsed))


def _observed_indexed_list_candidates(
    connection: Any, *, repo_id: str, literal_lists: Mapping[tuple[str, str], list[str]]
) -> list[tuple[str, int, str, str, str]]:
    """Derive candidate scalar bindings from an observed literal-list index assignment.

    Example observed statement::

        for i in ... loop let table_name = '${$dict_table_names[$i]}'

    When ``dict_table_names`` is independently observed as a literal string list,
    every list item is a grounded candidate for ``table_name``.  Correlation with
    a later query/output pair is preserved downstream; no loop execution or value
    guessing is performed here.
    """
    if not _has_table(connection, 'sql_script_statement'):
        return []
    pattern = re.compile(
        r"\blet\s+\$?(?P<target>[A-Za-z_][A-Za-z0-9_.]*)\s*=\s*"
        r"(?P<quote>['\"])\s*\$\{\s*\$?(?P<source>[A-Za-z_][A-Za-z0-9_.]*)"
        r"\s*\[\s*\$?[A-Za-z_][A-Za-z0-9_.]*\s*\]\s*\}\s*(?P=quote)",
        re.IGNORECASE,
    )
    rows = connection.execute(
        "SELECT file,line_start,statement_preview FROM sql_script_statement WHERE repo_id=? ORDER BY file,line_start,sql_script_statement_id",
        [repo_id],
    ).fetchall()
    derived: list[tuple[str, int, str, str, str]] = []
    for file, line_start, preview in rows:
        for match in pattern.finditer(str(preview or '')):
            source = str(match.group('source')).lower()
            target = str(match.group('target')).lower()
            values = literal_lists.get((str(file), source)) or []
            for value in values:
                derived.append((str(file), int(line_start or 0), target, value, source))
    return derived


def _resolve_script_expression(
    expression: str, *, script_file: str, before_line: int,
    local_bindings: Mapping[tuple[str, str], list[tuple[int, str]]],
    context_values: Mapping[str, list[str]], max_depth: int = 12,
) -> tuple[list[str], list[str]]:
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
                    latest_line = max(item[0] for item in local)
                    candidates = sorted(dict.fromkeys(item[1] for item in local if item[0] == latest_line))
                elif context_values.get(name):
                    candidates = list(context_values[name])
                if not candidates:
                    continue
                for candidate in candidates:
                    next_variants.append(_replace_placeholder(variant, name, _strip_script_literal(candidate)))
                changed = replaced = True
                break
            if not replaced:
                next_variants.append(variant)
        variants = sorted(dict.fromkeys(next_variants))[:100]
        if not changed:
            break
    for variant in variants:
        unresolved.update(_placeholder_tokens(variant))
    return variants, sorted(unresolved)


def _resolve_observed_output_table(
    expression: str, *, script_file: str, before_line: int,
    local_bindings: Mapping[tuple[str, str], list[tuple[int, str]]],
    context_values: Mapping[str, list[str]],
) -> tuple[str | None, list[str], list[str]]:
    """Resolve only the terminal table component of an observed relation template.

    Schema/catalog placeholders may remain unresolved.  A table is accepted only
    when every grounded variant exposes the same concrete final path component.
    Ambiguous or still-placeholder-bearing table components remain unresolved.
    """
    variants, unresolved = _resolve_script_expression(
        expression, script_file=script_file, before_line=before_line,
        local_bindings=local_bindings, context_values=context_values,
    )
    tables: set[str] = set()
    for variant in variants:
        tail = str(variant or "").strip().strip(" \t\r\n\"'`()[]{};,. ").replace("\\", "/").rsplit("/", 1)[-1].split(".")[-1]
        if not tail or _placeholder_tokens(tail):
            continue
        tables.add(tail)
    return (next(iter(tables)) if len(tables) == 1 else None), variants, unresolved


def _match_sql_file_template(template: str, known_files: Sequence[str], source_file: str) -> list[str]:
    # Preserve template delimiters while normalizing path punctuation.  Both
    # ${...}/$name and {{...}} are observed deployment-template syntaxes; for
    # path matching only, their lexical spans act as unknown prefixes.
    normalized = str(template or "").strip().replace("\\", "/").strip(" \t\r\n\"'`()[];,. ").lstrip("/")
    known = sorted(dict.fromkeys(str(item).replace("\\", "/").lstrip("/") for item in known_files if item))
    if normalized in known:
        return [normalized]
    matches = list(re.finditer(r"\{\{[^{}]+\}\}|\$\{[^{}]+\}|(?<![A-Za-z0-9$])\$[A-Za-z_][A-Za-z0-9_.]*", normalized))
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
        parts = item.split("/")[:-1]; n = 0
        for a, b in zip(source_parts, parts):
            if a != b: break
            n += 1
        return n
    scores = {item: prefix_len(item) for item in candidates}; best = max(scores.values(), default=0)
    return [item for item in candidates if scores[item] == best]



def _template_matches_concrete_relation(template: str, concrete: str) -> bool:
    """Match one observed relation template to one exact configured relation.

    Placeholders are wildcards only inside their own lexical span; all other
    characters remain exact.  This is structural matching, not name similarity.
    """
    raw = str(template or "").strip().lower()
    target = str(concrete or "").strip().lower()
    if not raw or not target:
        return False
    parts: list[str] = []
    pos = 0
    pattern = re.compile(r"\$\{[^{}]+\}|(?<![A-Za-z0-9$])\$[A-Za-z_][A-Za-z0-9_.]*")
    for match in pattern.finditer(raw):
        parts.append(re.escape(raw[pos:match.start()]))
        parts.append(r"[^./]*")
        pos = match.end()
    parts.append(re.escape(raw[pos:]))
    return re.fullmatch("".join(parts), target, re.IGNORECASE) is not None


def _config_scalar_index(connection: Any, *, repo_id: str) -> dict[str, dict[str, str]]:
    values: dict[str, dict[str, str]] = defaultdict(dict)
    if not _has_table(connection, 'sql_workflow_binding'):
        return values
    for row in connection.execute(
        "SELECT file,binding_path,scalar_value,value_expression FROM sql_workflow_binding "
        "WHERE repo_id=? ORDER BY file,binding_path", [repo_id]
    ).fetchall():
        file, path, scalar, expression = row
        value = str(scalar if scalar is not None else expression or "").strip()
        if file and path and value:
            values[str(file)][str(path).strip().lower()] = value
    return values


def _config_relation(config: Mapping[str, str], schema_path: str, table_path: str) -> tuple[str, str] | None:
    table = str(config.get(table_path.lower()) or "").strip()
    if not table or _placeholder_tokens(table):
        return None
    schema = str(config.get(schema_path.lower()) or "").strip()
    full = f"{schema}.{table}" if schema and not _placeholder_tokens(schema) else table
    return full, table.split('.')[-1]


def _config_partition_column_mappings(config: Mapping[str, str]) -> dict[str, str]:
    mappings: dict[str, str] = {}
    # JSON/YAML flattening publishes list elements as [...].  Pair only fields
    # with the same observed list index; no column-name similarity is used.
    pattern = re.compile(r"^params\.target\.partitioning\.snp\[(?P<idx>\d+)\]\.partitioningcolumn$")
    for path, output in config.items():
        match = pattern.match(path)
        if not match:
            continue
        source = config.get(f"params.target.partitioning.snp[{match.group('idx')}].initialcolumn")
        if source and output:
            mappings[str(output).strip().lower()] = str(source).strip()
    return mappings


def _parameter_scope_path(parent_path: str) -> str:
    """Return the enclosing observed parameter-record scope without guessing semantics."""
    text = str(parent_path or "").strip()
    match = re.match(r"^(?P<scope>.+?)\.params\[\d+\]\.param$", text)
    if match:
        return str(match.group("scope"))
    return text.rsplit(".", 1)[0] if "." in text else text


def _scoped_parameter_environments(connection: Any, *, repo_id: str) -> list[dict[str, Any]]:
    """Compose observed ``name``/``prior_value`` records inside one config scope.

    This is structural composition over already extracted config scalars.  It does
    not evaluate deployment precedence or merge values across sibling workflow
    blocks in the same file.
    """
    if not _has_table(connection, 'sql_workflow_binding'):
        return []
    rows = connection.execute(
        "SELECT sql_workflow_binding_id,file,binding_path,parent_path,binding_name,scalar_value,value_expression,line_start,evidence_json "
        "FROM sql_workflow_binding WHERE repo_id=? ORDER BY file,parent_path,binding_path,sql_workflow_binding_id",
        [repo_id],
    ).fetchall()
    records: dict[tuple[str, str], dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for bid, file, path, parent, name, scalar, expression, line_start, evidence_json in rows:
        parent_text = str(parent or "").strip()
        name_text = str(name or "").strip().lower()
        if not file or not parent_text or name_text not in {"name", "prior_value"}:
            continue
        value = str(scalar if scalar is not None else expression or "").strip()
        if not value:
            continue
        records[(str(file), parent_text)][name_text].append({
            'binding_id': str(bid), 'binding_path': str(path or ''), 'value': value,
            'line_start': int(line_start or 0), 'evidence': _json_value(evidence_json, []),
        })

    scoped: dict[tuple[str, str], dict[str, Any]] = {}
    for (file, parent), fields in records.items():
        names = fields.get('name') or []
        values = fields.get('prior_value') or []
        if len(names) != 1 or len(values) != 1:
            continue
        parameter_name = str(names[0]['value']).strip().lstrip('$')
        parameter_value = str(values[0]['value']).strip()
        if not parameter_name or not parameter_value:
            continue
        scope_path = _parameter_scope_path(parent)
        slot = scoped.setdefault((file, scope_path), {
            'file': file, 'scope_path': scope_path, 'values': defaultdict(list), 'records': [],
        })
        slot['values'][parameter_name].append(parameter_value)
        slot['records'].append({
            'name': parameter_name, 'value': parameter_value, 'parent_path': parent,
            'name_binding_id': names[0]['binding_id'], 'value_binding_id': values[0]['binding_id'],
            'evidence': [*names[0]['evidence'], *values[0]['evidence']],
        })
    out: list[dict[str, Any]] = []
    for key in sorted(scoped):
        slot = scoped[key]
        values = {name: sorted(dict.fromkeys(items)) for name, items in slot['values'].items()}
        out.append({**slot, 'values': values})
    return out


def _observed_scoped_s2t_copies(connection: Any, *, repo_id: str) -> list[dict[str, Any]]:
    """Resolve exact scoped parameter values into an observed ``s2tTableList`` template."""
    if not _has_table(connection, 'sql_workflow_binding'):
        return []
    template_rows = connection.execute(
        "SELECT sql_workflow_binding_id,file,line_start,scalar_value,value_expression,evidence_json "
        "FROM sql_workflow_binding WHERE repo_id=? AND lower(binding_name)='s2ttablelist' ORDER BY file,line_start,sql_workflow_binding_id",
        [repo_id],
    ).fetchall()
    templates_by_file: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for bid, file, line_start, scalar, expression, evidence_json in template_rows:
        value = str(scalar if scalar is not None else expression or "").strip()
        if file and value:
            templates_by_file[str(file)].append({
                'binding_id': str(bid), 'line_start': int(line_start or 0), 'value': value,
                'evidence': _json_value(evidence_json, []),
            })
    if not templates_by_file:
        return []
    template_files = sorted(templates_by_file)
    copies: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for env in _scoped_parameter_environments(connection, repo_id=repo_id):
        candidate_configs: set[str] = set()
        for values in env['values'].values():
            for value in values:
                if not any(suffix in str(value).lower() for suffix in ('.json', '.yaml', '.yml', '.conf', '.properties')):
                    continue
                candidate_configs.update(_match_sql_file_template(str(value), template_files, str(env['file'])))
        for config_file in sorted(candidate_configs):
            for template in templates_by_file.get(config_file, ()):
                variants, unresolved = _resolve_script_expression(
                    str(template['value']), script_file=config_file, before_line=int(template['line_start'] or 0),
                    local_bindings={}, context_values=env['values'],
                )
                for variant in variants:
                    if _placeholder_tokens(variant):
                        continue
                    for raw_pair in str(variant).split(';'):
                        if raw_pair.count('->') != 1:
                            continue
                        source_raw, target_raw = [part.strip() for part in raw_pair.split('->', 1)]
                        source = source_raw.split('.')[-1].strip()
                        target = target_raw.split('.')[-1].strip()
                        if not source or not target or source.lower() == target.lower():
                            continue
                        dedupe = (str(env['file']), str(env['scope_path']), source.lower(), target.lower())
                        if dedupe in seen:
                            continue
                        seen.add(dedupe)
                        required_parameter_names = set(_placeholder_tokens(str(template['value'])))
                        supporting_parameter_records: list[dict[str, Any]] = []
                        seen_parameter_records: set[tuple[str, str]] = set()
                        for record in env['records']:
                            if not isinstance(record, dict):
                                continue
                            include = str(record.get('name') or '') in required_parameter_names
                            record_value = str(record.get('value') or '')
                            if not include and any(
                                suffix in record_value.lower()
                                for suffix in ('.json', '.yaml', '.yml', '.conf', '.properties')
                            ):
                                include = config_file in _match_sql_file_template(
                                    record_value, template_files, str(env['file'])
                                )
                            if not include:
                                continue
                            record_key = (
                                str(record.get('name_binding_id') or ''),
                                str(record.get('value_binding_id') or ''),
                            )
                            if record_key in seen_parameter_records:
                                continue
                            seen_parameter_records.add(record_key)
                            supporting_parameter_records.append(dict(record))
                        copies.append({
                            'workflow': str(env['file']), 'scope_path': str(env['scope_path']),
                            'source': source, 'target': target, 'config_file': config_file,
                            'template_binding_id': str(template['binding_id']),
                            'template': str(template['value']), 'unresolved_placeholders': unresolved,
                            # Keep only observed parameters that establish this exact
                            # copy contract: placeholders used by s2tTableList plus
                            # the observed parameter that resolves its referenced
                            # config file.  Other workflow parameters remain in the
                            # generic binding knowledge and are not duplicated into
                            # every downstream lineage row.
                            'parameter_records': supporting_parameter_records,
                            'template_evidence': list(template['evidence']),
                        })
    return copies


def _unambiguous_template_context(
    expression: str, context_values: Mapping[str, Sequence[str]]
) -> dict[str, list[str]] | None:
    """Return only a context that cannot create cross-scope placeholder products.

    A workflow file may contain many independently scoped parameter records. The
    coarse ``workflow_values[file]`` index intentionally preserves all observed
    values, but it does not preserve which sibling scope they came from. It is
    therefore safe for direct template substitution only when every placeholder
    used by the expression has exactly one observed value in that file-level
    context. Multi-valued placeholders must be resolved by a scope-preserving
    mechanism such as ``_observed_scoped_s2t_copies`` instead of a Cartesian
    product across unrelated workflow definitions.
    """
    resolved: dict[str, list[str]] = {}
    for name in _placeholder_tokens(expression):
        values = sorted(dict.fromkeys(str(item) for item in context_values.get(name, ()) if str(item)))
        if len(values) != 1:
            return None
        resolved[name] = values
    return resolved


def _workflow_identity_tokens(value: str) -> list[str]:
    tokens: list[str] = []
    cleaned = re.sub(r"\$\{[^}]+\}", " ", str(value or ""))
    for match in re.finditer(r"[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*", cleaned):
        token = match.group(0).strip()
        if token.lower() in {"and", "or", "not", "true", "false"}: continue
        parts = token.split(".")
        if len(parts) > 1 and parts[-1].isdigit(): token = ".".join(parts[:-1])
        if token: tokens.append(token)
    return sorted(dict.fromkeys(tokens))


def _has_table(connection: Any, table: str) -> bool:
    return bool(connection.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema='main' AND table_name=?", [table]).fetchone()[0])


def _has_column(connection: Any, table: str, column: str) -> bool:
    if not _has_table(connection, table):
        return False
    return any(str(row[1]) == column for row in connection.execute(f"PRAGMA table_info('{table}')").fetchall())


@dataclass(frozen=True)
class SqlProducerObservations:
    dependencies: tuple[dict[str, Any], ...]
    materializations: tuple[dict[str, Any], ...]


def derive_sql_producer_observations(connection: Any, *, repo_id: str, sql_artifact_id: str | None = None) -> SqlProducerObservations:
    # Workflow values and dependency edges.
    workflow_values: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for row in connection.execute(
        "SELECT file,binding_name,scalar_value,value_expression FROM sql_workflow_binding WHERE repo_id=? ORDER BY file,binding_name", [repo_id]
    ).fetchall():
        value = str(row[2] if row[2] is not None else row[3] or "").strip()
        if row[1] and value: workflow_values[str(row[0])][str(row[1]).strip().lstrip("$")].append(value)

    # Some workflow formats represent parameters structurally as sibling scalars
    # (name + prior_value/value) instead of as a direct mapping key. Compose only
    # siblings observed under the exact same parent_path. This is identity-preserving
    # configuration evidence, not a naming heuristic or runtime substitution.
    if _has_column(connection, 'sql_workflow_binding', 'parent_path'):
        grouped: dict[tuple[str, str], dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
        for file, parent_path, binding_name, scalar_value, value_expression in connection.execute(
            "SELECT file,parent_path,binding_name,scalar_value,value_expression FROM sql_workflow_binding "
            "WHERE repo_id=? AND parent_path IS NOT NULL AND lower(binding_name) IN ('name','prior_value','value') "
            "ORDER BY file,parent_path,binding_name", [repo_id]
        ).fetchall():
            value = str(scalar_value if scalar_value is not None else value_expression or '').strip()
            if file and parent_path and binding_name and value:
                grouped[(str(file), str(parent_path))][str(binding_name).strip().lower()].append(value)
        for (file, _parent_path), siblings in grouped.items():
            names = sorted(dict.fromkeys(siblings.get('name') or ()))
            values = sorted(dict.fromkeys([*(siblings.get('prior_value') or ()), *(siblings.get('value') or ())]))
            if len(names) != 1 or len(values) != 1:
                continue
            workflow_values[file][names[0].lstrip('$')].append(values[0])

    for values in workflow_values.values():
        for name in list(values): values[name] = sorted(dict.fromkeys(values[name]))
    config_scalars = _config_scalar_index(connection, repo_id=repo_id)

    producer_entities: dict[str, list[str]] = defaultdict(list); consumer_triggers: dict[str, list[str]] = defaultdict(list)
    for row in connection.execute(
        "SELECT file,binding_name,scalar_value,value_expression FROM sql_workflow_binding WHERE repo_id=? AND lower(binding_name) IN ('entities','trigger') ORDER BY file,binding_name", [repo_id]
    ).fetchall():
        value = str(row[2] if row[2] is not None else row[3] or "").strip()
        if not value: continue
        (producer_entities if str(row[1]).lower() == 'entities' else consumer_triggers)[str(row[0])].append(value)
    producers_by_entity: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for wf, expressions in producer_entities.items():
        for expr in expressions:
            for identity in _workflow_identity_tokens(expr): producers_by_entity[identity].append((wf, expr))
    dependencies: list[dict[str, Any]] = []
    for consumer, expressions in consumer_triggers.items():
        for trigger_expr in expressions:
            for identity in _workflow_identity_tokens(trigger_expr):
                producers = sorted(dict.fromkeys(producers_by_entity.get(identity, ())))
                status = 'matched' if len(producers) == 1 else 'ambiguous'
                for producer, producer_expr in producers:
                    if producer == consumer: continue
                    dependencies.append({
                        'id': stable_id('sql_workflow_dependency', repo_id, producer, consumer, identity),
                        'producer_workflow': producer, 'consumer_workflow': consumer, 'entity_identity': identity,
                        'producer_expression': producer_expr, 'consumer_expression': trigger_expr,
                        'resolution_status': status, 'knowledge_class': 'derived' if status == 'matched' else 'candidate',
                        'mapping_basis': 'producer_entities_exact_consumer_trigger_identity' if status == 'matched' else 'nonunique_producer_entities_for_consumer_trigger_identity',
                        'provenance': {'sql_artifact_id': sql_artifact_id, 'producer_binding':'entities','consumer_binding':'trigger','identity_normalization':'strip_numeric_trigger_stage_suffix_only','producer_candidates':[x[0] for x in producers]},
                    })

    workflow_roots_by_file: dict[str, set[str]] = defaultdict(set)
    for row in connection.execute(
        "SELECT workflow_context_file,reachable_file FROM sql_workflow_context_file WHERE repo_id=? AND resolution_status IN ('resolved','probable')", [repo_id]
    ).fetchall(): workflow_roots_by_file[str(row[1])].add(str(row[0]))

    known_sql_files = {str(row[0]) for row in connection.execute("SELECT DISTINCT file FROM sql_statement WHERE repo_id=? AND file IS NOT NULL", [repo_id]).fetchall() if row[0]}
    if _has_table(connection, 'sql_script_statement'):
        known_sql_files.update(str(row[0]) for row in connection.execute("SELECT DISTINCT file FROM sql_script_statement WHERE repo_id=? AND file IS NOT NULL", [repo_id]).fetchall() if row[0])
    known_sql_files = sorted(known_sql_files)
    local_bindings: dict[tuple[str, str], list[tuple[int, str]]] = defaultdict(list)
    literal_lists: dict[tuple[str, str], list[str]] = {}
    if _has_table(connection, 'sql_script_binding'):
        for row in connection.execute("SELECT file,line_start,binding_name,value_expression,scalar_value FROM sql_script_binding WHERE repo_id=? ORDER BY file,line_start", [repo_id]).fetchall():
            file = str(row[0]); name = str(row[2] or '').strip().lower()
            value_expression = str(row[3] or "")
            value = str(row[4] if row[4] is not None else value_expression)
            local_bindings[(file, name)].append((int(row[1] or 0), value))
            observed_list = _literal_string_list(value_expression)
            if observed_list:
                literal_lists[(file, name)] = observed_list
        for file, line_start, target, value, _source in _observed_indexed_list_candidates(
            connection, repo_id=repo_id, literal_lists=literal_lists
        ):
            local_bindings[(file, target)].append((line_start, value))
        for key in list(local_bindings):
            local_bindings[key].sort(key=lambda item: (item[0], item[1]))
    query_ids_by_file: dict[str, list[str]] = defaultdict(list)
    for row in connection.execute(
        "SELECT DISTINCT s.query_id,s.file FROM sql_statement s JOIN sql_select_scope scp ON scp.repo_id=s.repo_id AND scp.query_id=s.query_id WHERE s.repo_id=? AND s.file IS NOT NULL AND scp.parent_scope_id IS NULL ORDER BY s.file,s.query_id", [repo_id]
    ).fetchall(): query_ids_by_file[str(row[1])].append(str(row[0]))

    materializations: list[dict[str, Any]] = []
    def add(kind: str, workflow: str, source_file: str, source_fact_id: str, source_symbol: str | None, query_file: str | None, query_id: str | None, source_table: str | None, output_table: str, basis: str, provenance: Mapping[str, Any], source_scopes: Sequence[str]=()) -> None:
        materializations.append({
            'id': stable_id('sql_relation_materialization', repo_id, workflow, kind, source_fact_id, query_id, source_table, output_table),
            'workflow': workflow, 'kind': kind, 'source_file': source_file, 'source_fact_id': source_fact_id, 'source_symbol': source_symbol,
            'query_file': query_file or '', 'query_id': query_id or '', 'source_table': source_table or '', 'table': output_table,
            'source_scopes': list(source_scopes), 'resolution_status':'matched','knowledge_class':'derived','mapping_basis':basis,'provenance':dict(provenance),
        })

    def arg_key(value: str) -> str: return ''.join(ch for ch in str(value or '').lower() if ch.isalnum())
    qkeys={'querypath','sqlpath','queryfile','sqlfile','sourcequerypath'}; tkeys={'tablename','targettable','outputtable','destinationtable'}
    if _has_table(connection, 'sql_script_call'):
        for row in connection.execute("SELECT sql_script_call_id,file,line_start,call_symbol,named_arguments_json,evidence_json FROM sql_script_call WHERE repo_id=? ORDER BY file,line_start,sql_script_call_id", [repo_id]).fetchall():
            call_id, script_file, line_start, symbol, named_json, evidence_json = row; named=_json_value(named_json,{})
            if not isinstance(named,dict): continue
            qargs=[str(v) for k,v in named.items() if arg_key(k) in qkeys]; targs=[str(v) for k,v in named.items() if arg_key(k) in tkeys]
            if len(qargs)!=1 or len(targs)!=1: continue
            roots=sorted(workflow_roots_by_file.get(str(script_file),()))
            for wf in roots:
                qvars,qun=_resolve_script_expression(qargs[0],script_file=str(script_file),before_line=int(line_start or 0),local_bindings=local_bindings,context_values=workflow_values.get(wf,{}))
                tvars,tun=_resolve_script_expression(targs[0],script_file=str(script_file),before_line=int(line_start or 0),local_bindings=local_bindings,context_values=workflow_values.get(wf,{}))
                qfiles=set(); [qfiles.update(_match_sql_file_template(v,known_sql_files,str(script_file))) for v in qvars]
                tables=sorted({_strip_script_literal(v).strip().split('.')[-1] for v in tvars if v and not _placeholder_tokens(v)})
                pairs: list[tuple[str, str, str]] = []
                if len(qfiles)==1 and len(tables)==1:
                    pairs=[(next(iter(qfiles)),tables[0],'structured_script_call_plus_local_and_workflow_binding_resolution')]
                elif qfiles and tables:
                    # Multiple grounded loop candidates are correlated only by the
                    # exact observed query-file basename and output table value.
                    # This avoids a Cartesian product and does not use fuzzy/name
                    # similarity: ``.../<value>.sql`` must equal ``tableName=<value>``.
                    for table in tables:
                        matches=[qfile for qfile in sorted(qfiles) if qfile.rsplit('/',1)[-1].rsplit('.',1)[0].casefold()==table.casefold()]
                        if len(matches)==1:
                            pairs.append((matches[0],table,'structured_script_call_plus_observed_literal_loop_candidate_correlation'))
                for qfile, table, basis in pairs:
                    qids=query_ids_by_file.get(qfile,())
                    if len(qids)!=1: continue
                    add('script_call',wf,str(script_file),str(call_id),str(symbol or ''),qfile,qids[0],None,table,basis,{'sql_artifact_id':sql_artifact_id,'query_argument':qargs[0],'output_table_argument':targs[0],'query_unresolved_placeholders':qun,'output_unresolved_placeholders':tun,'query_candidate_count':len(qfiles),'output_candidate_count':len(tables),'call_evidence':_json_value(evidence_json,[]),'semantic_rule':'one_query_path_argument_plus_one_output_table_argument_or_exact_literal_loop_candidate_correlation'})

    # Config-driven relation transforms are materialized only when both the
    # structured call and its referenced repository config are observed.  The
    # historicity symbol is a platform-level transform contract: increment rows
    # flow to the configured snapshot output, while explicit partition mappings
    # override identity passthrough for the mapped output columns.
    if _has_table(connection, 'sql_script_call') and config_scalars:
        known_config_files = sorted(config_scalars)
        write_rows_by_file: dict[str, list[tuple[Any, ...]]] = defaultdict(list)
        if _has_table(connection, 'sql_write_target'):
            for write_row in connection.execute(
                "SELECT sql_write_target_id,file,query_id,operation_kind,target_relation_name,source_scope_ids_json,payload_json,evidence_json "
                "FROM sql_write_target WHERE repo_id=? AND source_scope_ids_json IS NOT NULL ORDER BY file,line_start,sql_write_target_id",
                [repo_id],
            ).fetchall():
                write_rows_by_file[str(write_row[1])].append(write_row)
        for row in connection.execute(
            "SELECT sql_script_call_id,file,line_start,call_symbol,named_arguments_json,positional_arguments_json,evidence_json "
            "FROM sql_script_call WHERE repo_id=? ORDER BY file,line_start,sql_script_call_id", [repo_id]
        ).fetchall():
            call_id, script_file, line_start, symbol, named_json, positional_json, evidence_json = row
            if str(symbol or '').strip().lower() != 'historicity':
                continue
            named = _json_value(named_json, {})
            positional = _json_value(positional_json, [])
            config_args: list[str] = []
            if isinstance(positional, list):
                config_args.extend(str(item) for item in positional if item)
            if isinstance(named, dict):
                for key, value in named.items():
                    if arg_key(str(key)) in {'config','configpath','path','filepath'} and value:
                        config_args.append(str(value))
            config_candidates: set[str] = set()
            for argument in config_args:
                variants, _unresolved = _resolve_script_expression(
                    argument,
                    script_file=str(script_file),
                    before_line=int(line_start or 0),
                    local_bindings=local_bindings,
                    context_values={},
                )
                for variant in variants:
                    config_candidates.update(_match_sql_file_template(variant, known_config_files, str(script_file)))
            if len(config_candidates) != 1:
                continue
            config_file = next(iter(config_candidates))
            config = config_scalars.get(config_file) or {}
            increment = _config_relation(config, 'params.increment.schemaName', 'params.increment.tableName')
            output = _config_relation(config, 'params.output.schemaName', 'params.output.tableNameSnp')
            if not increment or not output:
                continue
            increment_full, increment_table = increment
            output_full, output_table = output
            roots = sorted(workflow_roots_by_file.get(str(script_file), ()))
            if not roots:
                continue
            explicit_column_mappings = _config_partition_column_mappings(config)
            for wf in roots:
                # If the SQL statement feeding historicity writes a template that
                # structurally matches a configured relation, the config provides
                # an exact value for that otherwise unresolved placeholder.
                for write_row in write_rows_by_file.get(str(script_file), ()):
                    write_id, wfile, qid, op, target, scopes_json, payload_json, write_evidence_json = write_row
                    scopes = [str(x) for x in _json_value(scopes_json, []) if x]
                    if not scopes:
                        continue
                    payload = _json_value(payload_json, {})
                    observed_template = str((payload if isinstance(payload, dict) else {}).get('resolved_target_relation_name') or target or '').strip()
                    for configured_full, configured_table in ((increment_full, increment_table), (output_full, output_table)):
                        if not _template_matches_concrete_relation(observed_template, configured_full):
                            continue
                        add(
                            'sql_write', wf, str(wfile), str(write_id), str(op or 'sql_write'), str(wfile), str(qid or ''),
                            None, configured_table,
                            'observed_sql_write_template_resolved_by_referenced_transform_config',
                            {
                                'sql_artifact_id': sql_artifact_id,
                                'source_scope_ids': scopes,
                                'observed_target_relation_template': observed_template,
                                'configured_relation_name': configured_full,
                                'config_file': config_file,
                                'config_call_id': str(call_id),
                                'write_evidence': _json_value(write_evidence_json, []),
                                'semantic_rule': 'exact_relation_template_match_to_referenced_config_relation',
                            }, scopes,
                        )
                add(
                    'config_transform', wf, str(script_file), str(call_id), str(symbol or ''), None, None,
                    increment_table, output_table,
                    'observed_historicity_call_plus_referenced_config_increment_to_output',
                    {
                        'sql_artifact_id': sql_artifact_id,
                        'config_file': config_file,
                        'configured_increment_relation': increment_full,
                        'configured_output_relation': output_full,
                        'identity_passthrough': True,
                        'column_mappings': explicit_column_mappings,
                        'call_evidence': _json_value(evidence_json, []),
                        'semantic_rule': 'historicity_increment_to_snapshot_output_with_explicit_config_column_mappings',
                    },
                )

    if _has_table(connection, 'sql_write_target'):
        for row in connection.execute("SELECT sql_write_target_id,file,line_start,query_id,operation_kind,target_relation_name,source_scope_ids_json,payload_json,evidence_json FROM sql_write_target WHERE repo_id=? AND source_scope_ids_json IS NOT NULL ORDER BY file,line_start,sql_write_target_id", [repo_id]).fetchall():
            write_id,wfile,line_start,qid,op,target,scopes_json,payload_json,evidence_json=row; scopes=[str(x) for x in _json_value(scopes_json,[]) if x]
            if not scopes: continue
            payload=_json_value(payload_json,{})
            observed_target=str((payload if isinstance(payload,dict) else {}).get('resolved_target_relation_name') or target or '').strip()
            if not observed_target: continue
            for wf in sorted(workflow_roots_by_file.get(str(wfile),())):
                output, variants, unresolved = _resolve_observed_output_table(
                    observed_target, script_file=str(wfile), before_line=int(line_start or 0),
                    local_bindings=local_bindings, context_values=workflow_values.get(wf,{}),
                )
                if not output: continue
                fully_resolved=[variant for variant in variants if not _placeholder_tokens(variant)]
                basis=(
                    'observed_sql_write_target_with_resolved_target_and_source_scope'
                    if fully_resolved
                    else 'observed_sql_write_target_plus_workflow_binding_exact_output_table'
                )
                add('sql_write',wf,str(wfile),str(write_id),str(op or 'sql_write'),str(wfile),str(qid or ''),None,output,basis,{
                    'sql_artifact_id':sql_artifact_id,'source_scope_ids':scopes,
                    'observed_target_relation_template':observed_target,
                    'resolved_target_relation_candidates':fully_resolved,
                    'partially_resolved_target_relation_candidates':variants,
                    'unresolved_placeholders':unresolved,
                    'write_evidence':_json_value(evidence_json,[]),
                    # Preserve an observed materialized relation contract when Core/SQL
                    # already published it.  This is evidence, not an inferred schema,
                    # and lets downstream producer traversal use a useful contract even
                    # when one of the statement source scopes is locally incomplete.
                    'materialized_output_columns': list((payload if isinstance(payload,dict) else {}).get('materialized_output_columns') or []),
                    'materialized_output_contract_status': str((payload if isinstance(payload,dict) else {}).get('materialized_output_contract_status') or ''),
                    'materialized_output_contract_basis': str((payload if isinstance(payload,dict) else {}).get('materialized_output_contract_basis') or ''),
                    'semantic_rule':'workflow_and_file_local_bindings_may_resolve_exact_output_table_component_without_guessing_unresolved_schema',
                },scopes)

    if _has_table(connection, 'sql_workflow_binding'):
        for row in connection.execute("SELECT sql_workflow_binding_id,file,line_start,binding_name,scalar_value,evidence_json FROM sql_workflow_binding WHERE repo_id=? AND lower(binding_name)='s2ttablelist' AND scalar_value IS NOT NULL ORDER BY file,line_start,sql_workflow_binding_id", [repo_id]).fetchall():
            bid,bfile,bline,bname,value,evidence_json=row; roots=sorted(workflow_roots_by_file.get(str(bfile),()))
            if str(bfile) in workflow_values and str(bfile) not in roots: roots.append(str(bfile))
            for wf in roots:
                context_values = _unambiguous_template_context(
                    str(value), workflow_values.get(wf, {})
                )
                if context_values is None:
                    # A file-level workflow context with more than one value for a
                    # template placeholder has lost sibling-scope correlation. Do
                    # not manufacture source/target combinations here; the scoped
                    # parameter/config composition below owns that evidence.
                    continue
                variants,un=_resolve_script_expression(
                    str(value), script_file=str(bfile), before_line=int(bline or 0),
                    local_bindings=local_bindings, context_values=context_values
                )
                pairs=set()
                for variant in variants:
                    if _placeholder_tokens(variant): continue
                    for pair in str(variant).split(';'):
                        if pair.count('->')!=1: continue
                        source,output=[part.strip().split('.')[-1] for part in pair.split('->',1)]
                        if source and output and source.lower()!=output.lower(): pairs.add((source,output))
                for source,output in sorted(pairs):
                    add('workflow_copy',wf,str(bfile),str(bid),str(bname),None,None,source,output,'observed_workflow_s2t_table_list',{'sql_artifact_id':sql_artifact_id,'source_expression':str(value),'unresolved_placeholders':un,'binding_evidence':_json_value(evidence_json,[]),'semantic_rule':'observed_s2t_table_list_source_to_target_pair'})

    # Monolithic scheduler YAML may carry many workflow parameter records in one
    # file.  Resolve only an exact name/prior_value environment inside each
    # observed workflow scope and only when that scope references a config that
    # itself declares s2tTableList.  This avoids global same-name substitution.
    for copy in _observed_scoped_s2t_copies(connection, repo_id=repo_id):
        add(
            'workflow_copy', copy['workflow'], copy['config_file'],
            stable_id('observed_scoped_s2t_copy', repo_id, copy['workflow'], copy['scope_path'], copy['source'], copy['target']),
            's2tTableList', None, None, copy['source'], copy['target'],
            'observed_scoped_parameter_environment_plus_referenced_s2t_table_list',
            {
                'sql_artifact_id': sql_artifact_id,
                'workflow_scope_path': copy['scope_path'],
                'config_file': copy['config_file'],
                'template_binding_id': copy['template_binding_id'],
                'source_expression': copy['template'],
                'unresolved_placeholders': copy['unresolved_placeholders'],
                'parameter_records': copy['parameter_records'],
                'template_evidence': copy['template_evidence'],
                'semantic_rule': 'exact_sibling_name_prior_value_bindings_resolve_referenced_s2t_table_list_within_one_observed_scope',
            },
        )

    # deterministic de-duplication
    deps={d['id']:d for d in dependencies}; mats={m['id']:m for m in materializations}
    return SqlProducerObservations(tuple(deps[k] for k in sorted(deps)), tuple(mats[k] for k in sorted(mats)))


def build_sql_producer_traversal(connection: Any, *, repo_id: str, observations: SqlProducerObservations) -> tuple[SqlProducerColumnTraversal, dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    usages: dict[str, dict[str, Any]]={}; relations: dict[str, dict[str, Any]]={}; relations_by_scope: dict[str,list[str]]=defaultdict(list); projections: dict[str,dict[str,Any]]={}; projections_by_scope: dict[str,list[str]]=defaultdict(list); roots: dict[str,list[str]]=defaultdict(list); scope_contracts: dict[str,dict[str,Any]]={}; scope_ordinals: dict[str,int]={}
    for row in connection.execute("SELECT sql_column_usage_id,query_id,scope_id,file,column_name,table_or_alias,relation_id,relation_kind,relation_name,resolution_status,resolution_basis,usage_role FROM sql_column_usage WHERE repo_id=? ORDER BY sql_column_usage_id",[repo_id]).fetchall():
        usages[str(row[0])]={'id':str(row[0]),'query_id':str(row[1]),'scope_id':str(row[2]),'file':str(row[3]),'column':str(row[4] or ''),'table_or_alias':row[5],'relation_id':str(row[6]) if row[6] else None,'relation_kind':row[7],'relation_name':row[8],'resolution_status':row[9],'resolution_basis':row[10],'usage_role':str(row[11] or '')}
    for row in connection.execute("SELECT sql_relation_id,query_id,scope_id,relation_kind,relation_name,logical_name,alias,source_scope_ids_json,file,payload_json,usage_role FROM sql_relation WHERE repo_id=? ORDER BY sql_relation_id",[repo_id]).fetchall():
        payload=_json_value(row[9],{}); rel={'id':str(row[0]),'query_id':str(row[1]),'scope_id':str(row[2]),'kind':str(row[3] or ''),'name':str(row[4] or ''),'logical':str(row[5] or ''),'alias':row[6],'source_scopes':[str(x) for x in _json_value(row[7],[])],'file':str(row[8] or ''),'output_columns':[str(x) for x in (payload.get('output_columns') or [])] if isinstance(payload,dict) else [],'usage_role':str(row[10] or '')}; relations[rel['id']]=rel; relations_by_scope[rel['scope_id']].append(rel['id'])
    # Semantic role never selects a producer.  It is carried only to classify a
    # physical frontier when no observed producer exists, so an intermediate
    # relation is not silently promoted to an ultimate source.
    if _has_table(connection, 'sql_relation_semantic_role'):
        role_by_identity={}
        for identity,role,status,reasons in connection.execute(
            "SELECT relation_identity,semantic_role,classification_status,classification_reasons_json "
            "FROM sql_relation_semantic_role WHERE repo_id=? ORDER BY relation_identity",[repo_id]
        ).fetchall():
            role_by_identity[str(identity or '').strip().lower()]={
                'semantic_role':str(role or ''),
                'semantic_classification_status':str(status or ''),
                'semantic_classification_basis':_json_value(reasons,[]),
            }
        for rel in relations.values():
            meta=role_by_identity.get(str(rel.get('name') or '').strip().lower())
            if meta: rel.update(meta)
    for row in connection.execute("SELECT sql_projection_id,query_id,scope_id,file,output_name,expression,is_wildcard,source_column_usage_ids_json,resolution_status,expression_kind FROM sql_projection WHERE repo_id=? ORDER BY query_id,scope_id,projection_ordinal",[repo_id]).fetchall():
        p={'id':str(row[0]),'query_id':str(row[1]),'scope_id':str(row[2]),'file':str(row[3]),'output':str(row[4] or ''),'expression':row[5],'wildcard':bool(row[6]),'source_usages':[str(x) for x in _json_value(row[7],[])],'resolution_status':row[8],'expression_kind':row[9]}; projections[p['id']]=p; projections_by_scope[p['scope_id']].append(p['id'])
    for row in connection.execute("SELECT sql_select_scope_id,query_id,parent_scope_id,payload_json,scope_ordinal FROM sql_select_scope WHERE repo_id=? ORDER BY query_id,scope_ordinal",[repo_id]).fetchall():
        payload=_json_value(row[3],{}); sid=str(row[0]); scope_contracts[sid]={'output_columns':[str(x) for x in (payload.get('output_columns') or [])] if isinstance(payload,dict) else [],'output_contract_status':str(payload.get('output_contract_status') or '') if isinstance(payload,dict) else '','output_contract_basis':str(payload.get('output_contract_basis') or '') if isinstance(payload,dict) else ''}; scope_ordinals[sid]=int(row[4] or 0)
        if row[2] is None: roots[str(row[1])].append(sid)
    for rel in relations.values():
        rel['scope_ordinal']=scope_ordinals.get(str(rel.get('scope_id') or ''),0)
    index=ObservedMaterializationIndex(materializations=observations.materializations,workflow_dependencies=[(d['producer_workflow'],d['consumer_workflow'],d['id']) for d in observations.dependencies if d['resolution_status']=='matched'],root_scopes_by_query=roots,scope_output_contracts=scope_contracts)
    return SqlProducerColumnTraversal(usages=usages,relations=relations,relations_by_scope=relations_by_scope,projections=projections,projections_by_scope=projections_by_scope,root_scopes_by_query=roots,materializations=index), usages, relations
