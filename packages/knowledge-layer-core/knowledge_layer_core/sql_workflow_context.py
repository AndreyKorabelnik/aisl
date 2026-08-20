from __future__ import annotations

import json
import re
from collections import defaultdict, deque
from pathlib import PurePosixPath
from typing import Any, Iterable

from prepared_knowledge_runtime.normalization import stable_id

from .progress import emit_progress, timed_phase

_FILE_REF_RE = re.compile(
    r"(?P<path>(?:[A-Za-z][A-Za-z0-9+.-]*://)?[^;\n\r\t\"']+?\.(?:sql|hql|q|json|ya?ml|properties|conf|sh))",
    re.IGNORECASE,
)
_PLACEHOLDER_RE = re.compile(
    r"\$\{\s*\$?(?P<braced>[^{}]+?)\s*\}|"
    r"\{\{\s*(?P<jinja>[^{}]+?)\s*\}\}|"
    r"%\((?P<py>[^)]+)\)s|"
    r"(?<![A-Za-z0-9$])\$(?P<bare>[A-Za-z_][A-Za-z0-9_.]*)"
)
_SUPPORTED_FILE_SUFFIXES = (".sql", ".hql", ".q", ".json", ".yaml", ".yml", ".properties", ".conf", ".sh")


def _load_json(value: Any, default: Any) -> Any:
    if value in (None, ""):
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _normalize_file(value: Any) -> str:
    text = str(value or "").strip().replace("\\", "/")
    text = text.strip(" \t\r\n\"'`()[];,.")
    text = re.sub(r"^[A-Za-z][A-Za-z0-9+.-]*://+", "", text)
    text = re.sub(r"/+", "/", text)
    return text.lstrip("/")


def _placeholder_name(match: re.Match[str]) -> str:
    value = match.group("braced") or match.group("jinja") or match.group("py") or match.group("bare") or ""
    return str(value).strip().lstrip("$").strip()


def _literal_suffix(template: str) -> str:
    normalized = _normalize_file(template)
    matches = list(_PLACEHOLDER_RE.finditer(normalized))
    suffix = normalized[matches[-1].end():] if matches else normalized
    suffix = suffix.lstrip("/")
    return suffix


def _extract_file_templates(value: Any) -> list[str]:
    text = str(value or "")
    results: list[str] = []
    for part in re.split(r"[;\n\r]+", text):
        fragment = part.strip()
        if not fragment:
            continue
        for match in _FILE_REF_RE.finditer(fragment):
            candidate = match.group("path").strip()
            if candidate:
                results.append(candidate)
    return sorted(dict.fromkeys(results))


def _narrow_candidates_by_source_directory(
    source_file: str, candidates: Iterable[str]
) -> tuple[list[str], bool]:
    """Keep candidates with the strongest exact directory context of the source file.

    This does not infer missing configuration values. It only prevents a reference
    observed in one concrete repository directory (for example ``dml_inc``) from
    jumping to an otherwise identical file in a sibling directory (``dml_arc``).
    When the source file has no stronger directory context, every candidate is kept.
    """
    normalized_source = _normalize_file(source_file)
    normalized_candidates = sorted(
        dict.fromkeys(_normalize_file(item) for item in candidates if item)
    )
    if len(normalized_candidates) < 2 or not normalized_source:
        return normalized_candidates, False

    source_parts = PurePosixPath(normalized_source).parent.parts

    def common_prefix_length(candidate: str) -> int:
        candidate_parts = PurePosixPath(candidate).parent.parts
        length = 0
        for left, right in zip(source_parts, candidate_parts):
            if left != right:
                break
            length += 1
        return length

    scores = {candidate: common_prefix_length(candidate) for candidate in normalized_candidates}
    maximum = max(scores.values(), default=0)
    minimum = min(scores.values(), default=0)
    if maximum <= 0 or maximum == minimum:
        return normalized_candidates, False
    narrowed = [candidate for candidate in normalized_candidates if scores[candidate] == maximum]
    return narrowed, len(narrowed) < len(normalized_candidates)


def _match_known_files(template: str, known_files: Iterable[str]) -> tuple[list[str], str]:
    normalized_template = _normalize_file(template)
    known = sorted(dict.fromkeys(_normalize_file(item) for item in known_files if item))
    if normalized_template in known:
        return [normalized_template], "exact_repository_relative_path"

    suffix = _literal_suffix(template)
    if suffix:
        suffix_matches = [item for item in known if item == suffix or item.endswith("/" + suffix)]
        if suffix_matches:
            return suffix_matches, "exact_literal_suffix_after_placeholder"

    # A path can contain an unresolved placeholder inside an otherwise exact
    # repository-local template (for example ``pipeline_${load_type}.json``).
    # Treat only placeholder spans as wildcards; every literal character remains
    # exact.  This preserves ambiguity instead of guessing a runtime value.
    for anchor in ("wf/", "workflow/", "sql/", "dml/", "config/"):
        index = normalized_template.find(anchor)
        if index < 0:
            continue
        tail = normalized_template[index:]
        # Structural matching is safe only when every unresolved placeholder is
        # embedded in a segment that also carries a stable literal identity.
        # A whole dynamic directory such as ``${main_table}/...`` would otherwise
        # turn one unknown binding into a repository-wide wildcard.
        structural_safe = True
        for segment in tail.split("/"):
            matches = list(_PLACEHOLDER_RE.finditer(segment))
            if not matches:
                continue
            literal = segment
            for match in reversed(matches):
                literal = literal[:match.start()] + literal[match.end():]
            if not re.search(r"[A-Za-z0-9_]", literal):
                structural_safe = False
                break
        if structural_safe:
            pieces: list[str] = []
            pos = 0
            for match in _PLACEHOLDER_RE.finditer(tail):
                pieces.append(re.escape(tail[pos:match.start()]))
                pieces.append(r"[^/]+")
                pos = match.end()
            pieces.append(re.escape(tail[pos:]))
            pattern = re.compile(r"(?:^|.*/)" + "".join(pieces) + r"$")
            structural = [item for item in known if pattern.search(item)]
            if structural:
                return structural, f"exact_template_structure:{anchor.rstrip('/')}"
        anchored = [item for item in known if item == tail or item.endswith("/" + tail)]
        if anchored:
            return anchored, f"exact_anchored_suffix:{anchor.rstrip('/')}"
    return [], "no_repository_local_exact_suffix"


def _resolve_template_value(value: str, values_by_name: dict[str, list[str]], *, max_depth: int = 8) -> tuple[list[str], list[str]]:
    variants = [str(value)]
    unresolved: set[str] = set()
    for _ in range(max_depth):
        changed = False
        next_variants: list[str] = []
        for variant in variants:
            matches = list(_PLACEHOLDER_RE.finditer(variant))
            replacement = next((
                (match, values_by_name.get(_placeholder_name(match)) or [])
                for match in matches
                if values_by_name.get(_placeholder_name(match))
            ), None)
            if replacement is None:
                unresolved.update(_placeholder_name(match) for match in matches)
                next_variants.append(variant)
                continue
            match, candidates = replacement
            changed = True
            for candidate in candidates:
                next_variants.append(variant[: match.start()] + candidate + variant[match.end():])
        variants = sorted(dict.fromkeys(next_variants))[:100]
        if not changed:
            break
    unresolved.clear()
    for variant in variants:
        unresolved.update(_placeholder_name(match) for match in _PLACEHOLDER_RE.finditer(variant))
    return variants, sorted(item for item in unresolved if item)

def _contextual_edge_targets(
    template: str,
    candidates: Iterable[str],
    values_by_name: dict[str, list[str]],
    *,
    known_files: Iterable[str] = (),
    source_file: str = "",
) -> tuple[list[str], str]:
    """Resolve or narrow a file reference using bindings on the current workflow path.

    Static resolution can legitimately return no candidate when an unknown root
    placeholder precedes a known workflow placeholder.  In that case, substitute
    only the bindings actually present on the current path and retry exact
    repository-local matching.  This never performs global same-name matching.
    """
    normalized_candidates = sorted(
        dict.fromkeys(_normalize_file(item) for item in candidates if item)
    )
    if not values_by_name:
        status = "resolved" if len(normalized_candidates) == 1 else "ambiguous" if normalized_candidates else "unresolved"
        return normalized_candidates, status

    raw_template = str(template or "")
    available_names = {
        _placeholder_name(match)
        for match in _PLACEHOLDER_RE.finditer(raw_template)
        if values_by_name.get(_placeholder_name(match))
    }
    if not available_names:
        status = "resolved" if len(normalized_candidates) == 1 else "ambiguous" if normalized_candidates else "unresolved"
        return normalized_candidates, status

    variants, _unresolved = _resolve_template_value(raw_template, values_by_name)
    search_space = normalized_candidates or sorted(
        dict.fromkeys(_normalize_file(item) for item in known_files if item)
    )
    contextual: set[str] = set()
    for variant in variants:
        matches, _basis = _match_known_files(variant, search_space)
        contextual.update(matches)

    selected = sorted(contextual) if contextual else normalized_candidates
    selected, _narrowed = _narrow_candidates_by_source_directory(source_file, selected)
    status = "resolved" if len(selected) == 1 else "ambiguous" if selected else "unresolved"
    return selected, status


def _known_files(connection: Any, repo_id: str) -> tuple[dict[str, str], set[str]]:
    kinds: dict[str, str] = {}
    config_rows = connection.execute(
        "SELECT DISTINCT file FROM sql_workflow_binding WHERE repo_id=? AND file IS NOT NULL",
        [repo_id],
    ).fetchall()
    for (file,) in config_rows:
        kinds[_normalize_file(file)] = "config"
    for table in ("sql_statement", "sql_script_statement", "sql_semantic_placeholder"):
        rows = connection.execute(
            f"SELECT DISTINCT file FROM {table} WHERE repo_id=? AND file IS NOT NULL",
            [repo_id],
        ).fetchall()
        for (file,) in rows:
            normalized = _normalize_file(file)
            if normalized:
                kinds[normalized] = "sql"
    return kinds, set(kinds)


def _binding_rows(connection: Any, repo_id: str) -> list[dict[str, Any]]:
    cursor = connection.execute(
        """SELECT sql_workflow_binding_id, file, line_start, binding_path, binding_name,
                  scalar_value, value_expression, referenced_placeholders_json,
                  resolution_status, evidence_json
           FROM sql_workflow_binding
           WHERE repo_id=?
           ORDER BY file, line_start, binding_path, sql_workflow_binding_id""",
        [repo_id],
    )
    columns = [item[0] for item in cursor.description]
    rows: list[dict[str, Any]] = []
    for raw in cursor.fetchall():
        row = dict(zip(columns, raw))
        row["file"] = _normalize_file(row.get("file"))
        row["referenced_placeholders"] = _load_json(row.pop("referenced_placeholders_json"), [])
        row["evidence"] = _load_json(row.pop("evidence_json"), [])
        rows.append(row)
    return rows


def _script_invocation_rows(connection: Any, repo_id: str) -> list[dict[str, Any]]:
    cursor = connection.execute(
        """SELECT sql_script_invocation_id, file, line_start, target_path_template,
                  resolved_file, resolution_status, resolution_basis,
                  resolution_candidates_json, evidence_json
           FROM sql_script_invocation
           WHERE repo_id=? AND target_path_template IS NOT NULL
           ORDER BY file, line_start, sql_script_invocation_id""",
        [repo_id],
    )
    columns = [item[0] for item in cursor.description]
    rows: list[dict[str, Any]] = []
    for raw in cursor.fetchall():
        row = dict(zip(columns, raw))
        row["file"] = _normalize_file(row.get("file"))
        row["resolved_file"] = _normalize_file(row.get("resolved_file")) if row.get("resolved_file") else None
        row["resolution_candidates"] = _load_json(row.pop("resolution_candidates_json"), [])
        row["evidence"] = _load_json(row.pop("evidence_json"), [])
        rows.append(row)
    return rows


def _placeholder_rows(connection: Any, repo_id: str) -> dict[str, list[dict[str, Any]]]:
    cursor = connection.execute(
        """SELECT sql_semantic_placeholder_id, query_id, file, line_start, placeholder,
                  template, usage_roles_json, resolution_status, evidence_json
           FROM sql_semantic_placeholder
           WHERE repo_id=?
           ORDER BY file, query_id, placeholder, sql_semantic_placeholder_id""",
        [repo_id],
    )
    columns = [item[0] for item in cursor.description]
    by_file: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for raw in cursor.fetchall():
        row = dict(zip(columns, raw))
        row["file"] = _normalize_file(row.get("file"))
        row["usage_roles"] = _load_json(row.pop("usage_roles_json"), [])
        row["evidence"] = _load_json(row.pop("evidence_json"), [])
        by_file[row["file"]].append(row)
    return by_file


def _insert_rows_batched(
    connection: Any, table: str, rows: list[list[Any]], *, column_count: int, batch_size: int = 250
) -> None:
    """Publish bounded multi-row VALUES without changing row semantics."""
    placeholders = "(" + ",".join("?" for _ in range(column_count)) + ")"
    for offset in range(0, len(rows), batch_size):
        batch = rows[offset : offset + batch_size]
        connection.execute(
            f"INSERT INTO {table} VALUES " + ",".join(placeholders for _ in batch),
            [value for row in batch for value in row],
        )


def materialize_sql_workflow_context(connection: Any, *, repo_id: str, max_hops: int = 12) -> dict[str, Any]:
    """Materialize exact repository-local config/file references and placeholder candidates.

    No global same-name substitution is performed. A binding reaches a SQL placeholder
    only through an observed configuration or script invocation path.
    """
    with timed_phase("workflow-context reset derived tables"):
        connection.execute("DELETE FROM sql_placeholder_binding_resolution WHERE repo_id=?", [repo_id])
        connection.execute("DELETE FROM sql_workflow_context_file WHERE repo_id=?", [repo_id])
        connection.execute("DELETE FROM sql_workflow_file_reference WHERE repo_id=?", [repo_id])

    with timed_phase("workflow-context load known files and bindings"):
        file_kinds, known_files = _known_files(connection, repo_id)
        bindings = _binding_rows(connection, repo_id)
    emit_progress(f"workflow-context inventory known_files={len(known_files)} bindings={len(bindings)}")
    normalized_known_files = tuple(sorted(known_files))
    known_match_cache: dict[str, tuple[tuple[str, ...], str]] = {}

    def match_known_files_cached(template: str) -> tuple[list[str], str]:
        cache_key = str(template or "")
        cached = known_match_cache.get(cache_key)
        if cached is None:
            candidates, basis = _match_known_files(cache_key, normalized_known_files)
            cached = (tuple(candidates), basis)
            known_match_cache[cache_key] = cached
        return list(cached[0]), cached[1]

    bindings_by_file: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in bindings:
        bindings_by_file[row["file"]].append(row)

    references: list[dict[str, Any]] = []
    reference_discovery_started = __import__("time").monotonic()
    for row in bindings:
        templates = _extract_file_templates(row.get("value_expression"))
        for ordinal, template in enumerate(templates, 1):
            candidates, basis = match_known_files_cached(template)
            candidates, narrowed = _narrow_candidates_by_source_directory(row["file"], candidates)
            if narrowed:
                basis = f"{basis}+exact_source_directory_context"
            status = "resolved" if len(candidates) == 1 else "ambiguous" if candidates else "unresolved"
            references.append({
                "source_file": row["file"],
                "source_kind": "workflow_binding",
                "source_fact_id": row["sql_workflow_binding_id"],
                "line_start": row.get("line_start"),
                "reference_ordinal": ordinal,
                "target_path_template": template,
                "candidates": candidates,
                "resolution_status": status,
                "resolution_basis": basis,
                "evidence": row.get("evidence") or [],
            })

    emit_progress(
        f"workflow-context binding references discovered={len(references)}; "
        f"duration={__import__('time').monotonic() - reference_discovery_started:.1f}s"
    )
    invocation_reference_started = __import__("time").monotonic()
    for row in _script_invocation_rows(connection, repo_id):
        template = str(row.get("target_path_template") or "")
        candidates: list[str]
        basis: str
        resolved_file = row.get("resolved_file")
        if resolved_file and resolved_file in known_files:
            candidates, basis = [resolved_file], "core_resolved_repository_file"
        else:
            candidates, basis = match_known_files_cached(template)
        candidates, narrowed = _narrow_candidates_by_source_directory(row["file"], candidates)
        if narrowed:
            basis = f"{basis}+exact_source_directory_context"
        status = "resolved" if len(candidates) == 1 else "ambiguous" if candidates else "unresolved"
        references.append({
            "source_file": row["file"],
            "source_kind": "script_invocation",
            "source_fact_id": row["sql_script_invocation_id"],
            "line_start": row.get("line_start"),
            "reference_ordinal": 1,
            "target_path_template": template,
            "candidates": candidates,
            "resolution_status": status,
            "resolution_basis": basis,
            "evidence": row.get("evidence") or [],
        })

    emit_progress(
        f"workflow-context script invocation references total={len(references)}; "
        f"unique_templates={len(known_match_cache)}; "
        f"duration={__import__('time').monotonic() - invocation_reference_started:.1f}s"
    )
    reference_rows: list[list[Any]] = []
    adjacency: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for ref in references:
        candidates = ref["candidates"]
        reference_id = stable_id(
            "sql_workflow_file_reference",
            repo_id,
            ref["source_kind"],
            ref["source_fact_id"],
            ref["reference_ordinal"],
            ref["target_path_template"],
        )
        reference_rows.append([
            reference_id,
            repo_id,
            ref["source_file"],
            ref["source_kind"],
            ref["source_fact_id"],
            ref.get("line_start"),
            ref["reference_ordinal"],
            ref["target_path_template"],
            candidates[0] if len(candidates) == 1 else None,
            file_kinds.get(candidates[0]) if len(candidates) == 1 else None,
            ref["resolution_status"],
            ref["resolution_basis"],
            len(candidates),
            json.dumps(candidates, ensure_ascii=False, sort_keys=True),
            json.dumps(ref.get("evidence") or [], ensure_ascii=False, sort_keys=True),
        ])
        adjacency[ref["source_file"]].append({
            "reference_id": reference_id,
            "status": ref["resolution_status"],
            "template": ref["target_path_template"],
            "targets": candidates,
        })
    reference_insert_started = __import__("time").monotonic()
    if reference_rows:
        _insert_rows_batched(
            connection, "sql_workflow_file_reference", reference_rows, column_count=15
        )
    emit_progress(
        f"workflow-context file references published={len(reference_rows)}; "
        f"duration={__import__('time').monotonic() - reference_insert_started:.1f}s"
    )

    placeholder_load_started = __import__("time").monotonic()
    placeholders_by_file = _placeholder_rows(connection, repo_id)
    roots = sorted(file for file in bindings_by_file if file_kinds.get(file) == "config")
    emit_progress(
        f"workflow-context placeholders loaded files={len(placeholders_by_file)} roots={len(roots)}; "
        f"duration={__import__('time').monotonic() - placeholder_load_started:.1f}s"
    )
    resolution_rows: dict[str, list[Any]] = {}
    context_file_rows: dict[str, list[Any]] = {}

    traversal_started = __import__("time").monotonic()
    for root_ordinal, root_file in enumerate(roots, start=1):
        root_bindings = bindings_by_file[root_file]
        queue: deque[tuple[str, tuple[str, ...], tuple[str, ...], tuple[str, ...], int]] = deque()
        queue.append((root_file, (root_file,), tuple(), tuple(), 0))
        seen_states: set[tuple[str, tuple[str, ...]]] = set()
        while queue:
            current_file, path_files, path_refs, path_edge_statuses, hop_count = queue.popleft()
            state_key = (current_file, path_files)
            if state_key in seen_states or hop_count > max_hops:
                continue
            seen_states.add(state_key)

            path_reasons: list[str] = []
            if any(status == "ambiguous" for status in path_edge_statuses):
                path_reasons.append("context_path_contains_ambiguous_file_reference")
            context_status = "resolved" if not path_reasons else "probable"
            context_file_id = stable_id(
                "sql_workflow_context_file", repo_id, root_file, current_file, path_refs
            )
            context_file_rows[context_file_id] = [
                context_file_id,
                repo_id,
                root_file,
                current_file,
                file_kinds.get(current_file, "unknown"),
                hop_count,
                json.dumps(list(path_files), ensure_ascii=False),
                json.dumps(list(path_refs), ensure_ascii=False),
                context_status,
                json.dumps(sorted(dict.fromkeys(path_reasons)), ensure_ascii=False),
            ]

            context_bindings: list[dict[str, Any]] = []
            for file in path_files:
                context_bindings.extend(bindings_by_file.get(file) or [])
            values_by_name: dict[str, list[str]] = defaultdict(list)
            binding_rows_by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for binding in context_bindings:
                name = str(binding.get("binding_name") or "").strip()
                if not name:
                    continue
                value = str(binding.get("value_expression") or binding.get("scalar_value") or "")
                values_by_name[name].append(value)
                binding_rows_by_name[name].append(binding)
            for name in list(values_by_name):
                values_by_name[name] = sorted(dict.fromkeys(values_by_name[name]))

            for placeholder in placeholders_by_file.get(current_file) or []:
                name = str(placeholder.get("placeholder") or "").strip().lstrip("$")
                for binding in binding_rows_by_name.get(name) or []:
                    raw_value = str(binding.get("value_expression") or binding.get("scalar_value") or "")
                    variants, unresolved = _resolve_template_value(raw_value, values_by_name)
                    for variant in variants:
                        reasons: list[str] = []
                        if unresolved:
                            reasons.append("binding_template_has_unresolved_placeholders")
                        if path_reasons:
                            reasons.append("context_path_contains_ambiguous_file_reference")
                        status = "resolved" if not reasons else "probable" if reasons == ["context_path_contains_ambiguous_file_reference"] else "partial"
                        resolution_id = stable_id(
                            "sql_placeholder_binding_resolution",
                            repo_id,
                            root_file,
                            current_file,
                            placeholder.get("sql_semantic_placeholder_id"),
                            binding.get("sql_workflow_binding_id"),
                            variant,
                            path_refs,
                        )
                        evidence = []
                        evidence.extend(binding.get("evidence") or [])
                        evidence.extend(placeholder.get("evidence") or [])
                        resolution_rows[resolution_id] = [
                            resolution_id,
                            repo_id,
                            root_file,
                            current_file,
                            placeholder.get("query_id"),
                            placeholder.get("sql_semantic_placeholder_id"),
                            name,
                            json.dumps(placeholder.get("usage_roles") or [], ensure_ascii=False, sort_keys=True),
                            binding.get("sql_workflow_binding_id"),
                            binding.get("file"),
                            binding.get("line_start"),
                            binding.get("binding_path"),
                            binding.get("binding_name"),
                            raw_value,
                            variant,
                            hop_count,
                            json.dumps(list(path_files), ensure_ascii=False),
                            json.dumps(list(path_refs), ensure_ascii=False),
                            status,
                            json.dumps(reasons, ensure_ascii=False, sort_keys=True),
                            json.dumps(evidence, ensure_ascii=False, sort_keys=True),
                        ]

            if hop_count == max_hops:
                continue
            for edge in adjacency.get(current_file) or []:
                targets, contextual_status = _contextual_edge_targets(
                    str(edge.get("template") or ""),
                    edge["targets"],
                    values_by_name,
                    known_files=known_files,
                    source_file=current_file,
                )
                for target in targets:
                    if target in path_files:
                        continue
                    # Preserve one explicit ambiguity as a probable context path,
                    # but do not compound independent unresolved ambiguities.
                    # Chaining ambiguity A through ambiguity B creates a Cartesian
                    # product of candidates without additional evidence and can
                    # falsely mix bindings from unrelated alternatives.
                    if contextual_status == "ambiguous" and "ambiguous" in path_edge_statuses:
                        continue
                    queue.append((
                        target,
                        (*path_files, target),
                        (*path_refs, edge["reference_id"]),
                        (*path_edge_statuses, contextual_status),
                        hop_count + 1,
                    ))
        if root_ordinal % 50 == 0 or root_ordinal == len(roots):
            emit_progress(
                f"workflow-context traversal roots={root_ordinal}/{len(roots)} "
                f"context_files={len(context_file_rows)} resolutions={len(resolution_rows)} "
                f"elapsed={__import__('time').monotonic() - traversal_started:.1f}s"
            )

    emit_progress(
        f"workflow-context traversal completed; context_files={len(context_file_rows)} "
        f"resolutions={len(resolution_rows)}; duration={__import__('time').monotonic() - traversal_started:.1f}s"
    )
    context_insert_started = __import__("time").monotonic()
    if context_file_rows:
        _insert_rows_batched(
            connection, "sql_workflow_context_file", list(context_file_rows.values()), column_count=10
        )

    emit_progress(
        f"workflow-context context rows published={len(context_file_rows)}; "
        f"duration={__import__('time').monotonic() - context_insert_started:.1f}s"
    )
    resolution_insert_started = __import__("time").monotonic()
    if resolution_rows:
        _insert_rows_batched(
            connection, "sql_placeholder_binding_resolution", list(resolution_rows.values()), column_count=21
        )

    emit_progress(
        f"workflow-context placeholder resolutions published={len(resolution_rows)}; "
        f"duration={__import__('time').monotonic() - resolution_insert_started:.1f}s"
    )
    status_counts = dict(connection.execute(
        """SELECT resolution_status, count(*)
           FROM sql_placeholder_binding_resolution WHERE repo_id=?
           GROUP BY resolution_status ORDER BY resolution_status""",
        [repo_id],
    ).fetchall())
    return {
        "known_file_count": len(known_files),
        "workflow_context_count": len(roots),
        "file_reference_count": len(reference_rows),
        "resolved_file_reference_count": sum(1 for item in references if item["resolution_status"] == "resolved"),
        "ambiguous_file_reference_count": sum(1 for item in references if item["resolution_status"] == "ambiguous"),
        "unresolved_file_reference_count": sum(1 for item in references if item["resolution_status"] == "unresolved"),
        "workflow_context_file_count": len(context_file_rows),
        "placeholder_binding_resolution_count": len(resolution_rows),
        "placeholder_binding_by_status": {str(key): int(value) for key, value in status_counts.items()},
    }
