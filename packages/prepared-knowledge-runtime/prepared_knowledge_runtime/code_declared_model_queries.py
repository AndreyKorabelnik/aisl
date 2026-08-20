from __future__ import annotations

import json
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .query import KnowledgeLayerQuery

CODE_DECLARED_MODEL_SCHEMA_VERSION = "code-declared-data-model/v1"
CODE_DECLARED_MODEL_QUERY_SCHEMA_VERSION = "code-declared-data-model-query/v2"

_REQUIRED = {
    "code_declared_model_build",
    "code_declared_type",
    "code_declared_field",
    "code_declared_effective_field",
    "code_declared_relationship",
}


def _json(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _doc(value: Any) -> dict[str, Any]:
    parsed = _json(value, {})
    return dict(parsed) if isinstance(parsed, dict) else {}


def _source_ref(value: Any) -> dict[str, Any]:
    parsed = _json(value, {})
    return dict(parsed) if isinstance(parsed, dict) else {}


def _provenance(value: Any) -> dict[str, Any]:
    parsed = _json(value, {})
    return dict(parsed) if isinstance(parsed, dict) else {}


def _names(values: Any) -> list[str]:
    if values is None:
        return []
    if isinstance(values, str):
        raw = values.split(",")
    else:
        raw = list(values)
    result: list[str] = []
    seen: set[str] = set()
    for value in raw:
        name = str(value or "").strip()
        if name and name not in seen:
            seen.add(name)
            result.append(name)
    return result


def _annotation_map(con: Any, query: "KnowledgeLayerQuery", target_kind: str, target_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
    if not target_ids or not query._has_relation("code_declared_annotation"):
        return {target_id: [] for target_id in target_ids}
    placeholders = ",".join("?" for _ in target_ids)
    rows = query._rows(
        con.execute(
            f"""
            SELECT target_occurrence_id,annotation_occurrence_id,annotation_name,arguments_raw,
                   resolution_status,resolved_annotation_type,candidate_annotation_types_json,
                   structured_arguments_json,source_ref_json
            FROM code_declared_annotation
            WHERE target_kind=? AND target_occurrence_id IN ({placeholders})
            ORDER BY target_occurrence_id,lower(annotation_name),annotation_occurrence_id
            """,
            [target_kind, *target_ids],
        )
    )
    result: dict[str, list[dict[str, Any]]] = {target_id: [] for target_id in target_ids}
    for row in rows:
        target_id = str(row.pop("target_occurrence_id"))
        row["candidate_annotation_types"] = _json(row.pop("candidate_annotation_types_json", None), [])
        row["structured_arguments"] = _json(row.pop("structured_arguments_json", None), [])
        row["source_ref"] = _source_ref(row.pop("source_ref_json", None))
        result.setdefault(target_id, []).append(row)
    return result


def _cardinality_hint(declared_type_expression: Any) -> tuple[str, str]:
    value = str(declared_type_expression or "").strip()
    compact = "".join(value.split())
    raw = compact.rsplit(".", 1)[-1] if "<" not in compact else compact
    outer = raw.split("<", 1)[0].rsplit(".", 1)[-1]
    if compact.endswith("[]") or outer in {"List", "Set", "Collection", "Iterable"}:
        return "many", "declared_java_container_type"
    return "one", "declared_non_collection_type"


def _check_available(query: "KnowledgeLayerQuery") -> dict[str, Any] | None:
    missing = sorted(name for name in _REQUIRED if not query._has_relation(name))
    if missing:
        return {
            "schema_version": CODE_DECLARED_MODEL_QUERY_SCHEMA_VERSION,
            "model_schema_version": CODE_DECLARED_MODEL_SCHEMA_VERSION,
            "not_available": True,
            "missing_relations": missing,
        }
    with query._connect() as con:
        rows = query._rows(
            con.execute(
                "SELECT schema_version,build_status,scope_id,builder_version "
                "FROM code_declared_model_build ORDER BY completed_at DESC LIMIT 1"
            )
        )
    build = rows[0] if rows else {}
    if str(build.get("schema_version") or "") != CODE_DECLARED_MODEL_SCHEMA_VERSION:
        raise ValueError(
            f"code-declared artifact schema mismatch: expected {CODE_DECLARED_MODEL_SCHEMA_VERSION!r}"
        )
    if str(build.get("build_status") or "") != "complete":
        raise ValueError("code-declared data model build is incomplete")
    return None


def _field_rows(con: Any, query: "KnowledgeLayerQuery", owner_ids: list[str]) -> dict[str, list[dict[str, Any]]] :
    if not owner_ids:
        return {}
    placeholders = ",".join("?" for _ in owner_ids)
    rows = query._rows(
        con.execute(
            f"""
            SELECT e.effective_owner_type_occurrence_id AS object_id,
                   e.effective_field_occurrence_id,
                   e.field_occurrence_id,
                   e.declaring_type_occurrence_id,
                   e.field_name AS name,
                   e.inherited_depth,
                   e.is_inherited,
                   e.derivation_kind,
                   e.provenance_json,
                   f.declared_type_expression,
                   f.normalized_type_expression,
                   f.documentation_json,
                   f.source_ref_json,
                   f.is_static,
                   f.is_final
            FROM code_declared_effective_field e
            JOIN code_declared_field f ON f.field_occurrence_id=e.field_occurrence_id
            WHERE e.effective_owner_type_occurrence_id IN ({placeholders})
            ORDER BY e.effective_owner_type_occurrence_id, lower(e.field_name), e.inherited_depth,
                     e.effective_field_occurrence_id
            """,
            owner_ids,
        )
    )
    field_ids = sorted({str(row.get("field_occurrence_id")) for row in rows if row.get("field_occurrence_id")})
    annotations = _annotation_map(con, query, "field", field_ids)
    result: dict[str, list[dict[str, Any]]] = {owner_id: [] for owner_id in owner_ids}
    for row in rows:
        owner = str(row.pop("object_id"))
        field_id = str(row.get("field_occurrence_id") or "")
        row["documentation"] = _doc(row.pop("documentation_json", None))
        row["source_ref"] = _source_ref(row.pop("source_ref_json", None))
        row["provenance"] = _provenance(row.pop("provenance_json", None))
        row["annotations"] = annotations.get(field_id, [])
        result.setdefault(owner, []).append(row)
    return result


def _relationship_rows(
    con: Any,
    query: "KnowledgeLayerQuery",
    owner_ids: list[str],
) -> dict[str, list[dict[str, Any]]]:
    if not owner_ids:
        return {}
    placeholders = ",".join("?" for _ in owner_ids)
    rows = query._rows(
        con.execute(
            f"""
            SELECT r.source_type_occurrence_id AS object_id,
                   r.relationship_occurrence_id AS relationship_id,
                   r.field_occurrence_id,
                   f.name AS source_field,
                   f.declared_type_expression,
                   r.target_type_occurrence_id,
                   tt.fully_qualified_name AS target_fqcn,
                   tt.simple_name AS target_name,
                   r.relationship_kind,
                   r.resolution_status,
                   r.provenance_json,
                   f.source_ref_json
            FROM code_declared_relationship r
            JOIN code_declared_field f ON f.field_occurrence_id=r.field_occurrence_id
            JOIN code_declared_type tt ON tt.type_occurrence_id=r.target_type_occurrence_id
            WHERE r.source_type_occurrence_id IN ({placeholders})
            ORDER BY r.source_type_occurrence_id, lower(f.name), lower(tt.fully_qualified_name),
                     r.relationship_occurrence_id
            """,
            owner_ids,
        )
    )
    field_ids = sorted({str(row.get("field_occurrence_id")) for row in rows if row.get("field_occurrence_id")})
    annotations = _annotation_map(con, query, "field", field_ids)
    result: dict[str, list[dict[str, Any]]] = {owner_id: [] for owner_id in owner_ids}
    for row in rows:
        owner = str(row.pop("object_id"))
        field_id = str(row.get("field_occurrence_id") or "")
        row["provenance"] = _provenance(row.pop("provenance_json", None))
        row["source_ref"] = _source_ref(row.pop("source_ref_json", None))
        row["source_field_annotations"] = annotations.get(field_id, [])
        row["is_inherited"] = bool(row["provenance"].get("is_inherited"))
        row["inherited_depth"] = int(row["provenance"].get("inherited_depth") or 0)
        cardinality, basis = _cardinality_hint(row.get("declared_type_expression"))
        row["cardinality_hint"] = cardinality
        row["cardinality_basis"] = basis
        result.setdefault(owner, []).append(row)
    return result



def _search_text_score(value: Any, token: str, *, exact: int, prefix: int, contains: int) -> tuple[int, str | None]:
    raw = str(value or "").strip().lower()
    needle = token.strip().lower()
    if not raw or not needle:
        return 0, None
    if raw == needle:
        return exact, "exact"
    if raw.startswith(needle):
        return prefix, "prefix"
    if needle in raw:
        return contains, "substring"
    return 0, None


def _documentation_matches(documentation: dict[str, Any], token: str, *, exact: int, prefix: int, contains: int) -> tuple[int, str | None, str | None]:
    best = (0, None, None)
    for key in ("display_name", "summary", "description"):
        score, mode = _search_text_score(documentation.get(key), token, exact=exact, prefix=prefix, contains=contains)
        if score > best[0]:
            best = (score, mode, key)
    return best


def _lightweight_field_match_rows(con: Any, query: "KnowledgeLayerQuery", owner_ids: list[str], token: str) -> dict[str, list[dict[str, Any]]]:
    if not owner_ids or not token:
        return {owner_id: [] for owner_id in owner_ids}
    placeholders = ",".join("?" for _ in owner_ids)
    pattern = f"%{token}%"
    rows = query._rows(con.execute(
        f"""
        SELECT e.effective_owner_type_occurrence_id AS object_id,
               e.effective_field_occurrence_id,
               e.field_occurrence_id,
               e.field_name AS name,
               e.inherited_depth,
               e.is_inherited,
               f.declared_type_expression,
               f.documentation_json,
               f.source_ref_json
        FROM code_declared_effective_field e
        JOIN code_declared_field f ON f.field_occurrence_id=e.field_occurrence_id
        WHERE e.effective_owner_type_occurrence_id IN ({placeholders})
          AND (f.name ILIKE ? OR f.declared_type_expression ILIKE ?
               OR coalesce(json_extract_string(f.documentation_json,'$.display_name'),'') ILIKE ?
               OR coalesce(json_extract_string(f.documentation_json,'$.description'),'') ILIKE ?
               OR coalesce(json_extract_string(f.documentation_json,'$.summary'),'') ILIKE ?)
        ORDER BY e.effective_owner_type_occurrence_id, e.inherited_depth, lower(e.field_name), e.effective_field_occurrence_id
        """,
        [*owner_ids, pattern, pattern, pattern, pattern, pattern],
    ))
    result = {owner_id: [] for owner_id in owner_ids}
    for row in rows:
        owner = str(row.pop("object_id"))
        row["documentation"] = _doc(row.pop("documentation_json", None))
        row["source_ref"] = _source_ref(row.pop("source_ref_json", None))
        result.setdefault(owner, []).append(row)
    return result


def _field_match_evidence(row: dict[str, Any], token: str) -> dict[str, Any] | None:
    candidates: list[tuple[int, str]] = []
    score, mode = _search_text_score(row.get("name"), token, exact=990, prefix=940, contains=880)
    if score:
        candidates.append((score, f"field_name_{mode}"))
    score, mode = _search_text_score(row.get("declared_type_expression"), token, exact=860, prefix=810, contains=740)
    if score:
        candidates.append((score, f"field_type_{mode}"))
    score, mode, key = _documentation_matches(dict(row.get("documentation") or {}), token, exact=970, prefix=910, contains=830)
    if score:
        candidates.append((score, f"field_documentation_{key}_{mode}"))
    if not candidates:
        return None
    score, kind = max(candidates, key=lambda x: (x[0], x[1]))
    return {
        "target_kind": "field",
        "match_kind": kind,
        "score": score,
        "field_occurrence_id": row.get("field_occurrence_id"),
        "effective_field_occurrence_id": row.get("effective_field_occurrence_id"),
        "field_name": row.get("name"),
        "declared_type_expression": row.get("declared_type_expression"),
        "documentation": dict(row.get("documentation") or {}),
        "source_ref": dict(row.get("source_ref") or {}),
        "is_inherited": bool(row.get("is_inherited")),
        "inherited_depth": int(row.get("inherited_depth") or 0),
        "evidence_role": "direct_observed_field_match",
    }


def _type_match_evidence(row: dict[str, Any], token: str) -> dict[str, Any] | None:
    candidates: list[tuple[int, str]] = []
    score, mode = _search_text_score(row.get("name"), token, exact=1000, prefix=930, contains=800)
    if score:
        candidates.append((score, f"type_name_{mode}"))
    score, mode = _search_text_score(row.get("fqcn"), token, exact=995, prefix=900, contains=700)
    if score:
        candidates.append((score, f"type_fqcn_{mode}"))
    score, mode, key = _documentation_matches(dict(row.get("documentation") or {}), token, exact=960, prefix=890, contains=780)
    if score:
        candidates.append((score, f"type_documentation_{key}_{mode}"))
    if not candidates:
        return None
    score, kind = max(candidates, key=lambda x: (x[0], x[1]))
    return {
        "target_kind": "type",
        "match_kind": kind,
        "score": score,
        "documentation": dict(row.get("documentation") or {}),
        "source_ref": dict(row.get("source_ref") or {}),
        "evidence_role": "observed_type_match",
    }


def _binding_summary_map(con: Any, query: "KnowledgeLayerQuery", owner_ids: list[str], outgoing_counts: dict[str, int]) -> dict[str, dict[str, Any]]:
    if not owner_ids:
        return {}
    placeholders = ",".join("?" for _ in owner_ids)
    rows = query._rows(con.execute(
        f"""
        SELECT r.target_type_occurrence_id AS object_id,
               r.relationship_occurrence_id AS relationship_id,
               r.source_type_occurrence_id AS source_object_id,
               st.fully_qualified_name AS source_fqcn,
               st.simple_name AS source_name,
               f.field_occurrence_id,
               f.name AS source_field,
               f.declared_type_expression,
               r.relationship_kind,
               r.resolution_status,
               r.provenance_json,
               f.source_ref_json
        FROM code_declared_relationship r
        JOIN code_declared_type st ON st.type_occurrence_id=r.source_type_occurrence_id
        JOIN code_declared_field f ON f.field_occurrence_id=r.field_occurrence_id
        WHERE r.target_type_occurrence_id IN ({placeholders})
        ORDER BY r.target_type_occurrence_id, lower(st.fully_qualified_name), lower(f.name), r.relationship_occurrence_id
        """,
        owner_ids,
    ))
    grouped: dict[str, list[dict[str, Any]]] = {owner_id: [] for owner_id in owner_ids}
    for row in rows:
        owner = str(row.pop("object_id"))
        row["provenance"] = _provenance(row.pop("provenance_json", None))
        row["source_ref"] = _source_ref(row.pop("source_ref_json", None))
        grouped.setdefault(owner, []).append(row)
    result: dict[str, dict[str, Any]] = {}
    for owner_id in owner_ids:
        incoming = grouped.get(owner_id, [])
        result[owner_id] = {
            "incoming_relationship_count": len(incoming),
            "outgoing_relationship_count": int(outgoing_counts.get(owner_id, 0)),
            "has_observed_incoming_binding": bool(incoming),
            "incoming_examples": incoming[:3],
            "incoming_examples_truncated": len(incoming) > 3,
        }
    return result

def list_code_declared_objects(
    query: "KnowledgeLayerQuery",
    *,
    repo_id: str | None = None,
    search: str | None = None,
    type_annotations: Any = None,
    include_fields: bool = False,
    offset: int = 0,
    limit: int = 50,
) -> dict[str, Any]:
    """Ranked lexical search over prepared declared-model facts.

    Search remains deterministic lexical retrieval. Ranking is retrieval metadata only and
    MUST NOT be interpreted as semantic confidence. Match evidence exposes only the bounded
    observed type/field facts that caused a hit; full field/relationship detail remains owned
    by ``get_code_declared_object``.
    """
    if offset < 0:
        raise ValueError("offset must be >= 0")
    if limit < 1 or limit > 500:
        raise ValueError("limit must be between 1 and 500")
    requested_annotations = _names(type_annotations)
    search_scope = "type_annotation_projection" if requested_annotations else "all_declared_types"
    unavailable = _check_available(query)
    if unavailable:
        return {
            **unavailable,
            "filters": {"repo_id": repo_id, "search": search, "type_annotations": requested_annotations, "search_scope": search_scope},
            "items": [],
            "total_count": 0,
        }

    clauses: list[str] = []
    params: list[Any] = []
    if repo_id:
        clauses.append("t.repo_id=?")
        params.append(repo_id)
    if requested_annotations:
        placeholders = ",".join("?" for _ in requested_annotations)
        clauses.append(
            f"EXISTS (SELECT 1 FROM code_declared_annotation a WHERE a.target_kind='type' "
            f"AND a.target_occurrence_id=t.type_occurrence_id AND a.annotation_name IN ({placeholders}))"
        )
        params.extend(requested_annotations)
    token = (search or "").strip()
    if token:
        pattern = f"%{token}%"
        clauses.append(
            "("
            "t.fully_qualified_name ILIKE ? OR t.simple_name ILIKE ? "
            "OR coalesce(json_extract_string(t.documentation_json,'$.display_name'),'') ILIKE ? "
            "OR coalesce(json_extract_string(t.documentation_json,'$.description'),'') ILIKE ? "
            "OR coalesce(json_extract_string(t.documentation_json,'$.summary'),'') ILIKE ? "
            "OR EXISTS ("
            " SELECT 1 FROM code_declared_effective_field ef "
            " JOIN code_declared_field f ON f.field_occurrence_id=ef.field_occurrence_id "
            " WHERE ef.effective_owner_type_occurrence_id=t.type_occurrence_id "
            " AND (f.name ILIKE ? OR f.declared_type_expression ILIKE ? "
            "      OR coalesce(json_extract_string(f.documentation_json,'$.display_name'),'') ILIKE ? "
            "      OR coalesce(json_extract_string(f.documentation_json,'$.description'),'') ILIKE ? "
            "      OR coalesce(json_extract_string(f.documentation_json,'$.summary'),'') ILIKE ?)"
            ")"
            ")"
        )
        params.extend([pattern] * 10)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""

    with query._connect() as con:
        candidate_rows = query._rows(con.execute(
            """
            SELECT t.type_occurrence_id AS object_id,t.repo_id,t.fully_qualified_name AS fqcn,
                   t.simple_name AS name,t.package_name,t.type_kind,t.source_set,
                   t.documentation_json,t.source_ref_json,
                   (SELECT count(*) FROM code_declared_effective_field ef
                    WHERE ef.effective_owner_type_occurrence_id=t.type_occurrence_id) AS field_count,
                   (SELECT count(*) FROM code_declared_relationship r
                    WHERE r.source_type_occurrence_id=t.type_occurrence_id) AS relationship_count
            FROM code_declared_type t
            """ + where,
            params,
        ))
        for row in candidate_rows:
            row["documentation"] = _doc(row.pop("documentation_json", None))
            row["source_ref"] = _source_ref(row.pop("source_ref_json", None))

        candidate_ids = [str(row["object_id"]) for row in candidate_rows]
        field_matches = _lightweight_field_match_rows(con, query, candidate_ids, token) if token else {oid: [] for oid in candidate_ids}
        for row in candidate_rows:
            evidences: list[dict[str, Any]] = []
            if token:
                type_ev = _type_match_evidence(row, token)
                if type_ev:
                    evidences.append(type_ev)
                for field_row in field_matches.get(str(row["object_id"]), []):
                    field_ev = _field_match_evidence(field_row, token)
                    if field_ev:
                        evidences.append(field_ev)
                evidences.sort(key=lambda ev: (-int(ev.get("score") or 0), str(ev.get("match_kind") or ""), str(ev.get("field_name") or "")))
            row["retrieval_score"] = int(evidences[0]["score"]) if evidences else 0
            row["score_basis"] = str(evidences[0]["match_kind"]) if evidences else ("unfiltered_listing" if not token else "lexical_match")
            row["match_evidence"] = evidences[:5]
            row["match_evidence_truncated"] = len(evidences) > 5

        candidate_rows.sort(key=lambda row: (-int(row.get("retrieval_score") or 0), str(row.get("fqcn") or "").lower(), str(row.get("repo_id") or ""), str(row.get("object_id") or "")))
        total = len(candidate_rows)
        rows = candidate_rows[offset: offset + limit]
        owner_ids = [str(row["object_id"]) for row in rows]
        annotations = _annotation_map(con, query, "type", owner_ids)
        fields = _field_rows(con, query, owner_ids) if include_fields else {}
        outgoing_counts = {str(row["object_id"]): int(row.get("relationship_count") or 0) for row in rows}
        bindings = _binding_summary_map(con, query, owner_ids, outgoing_counts)

    items: list[dict[str, Any]] = []
    for row in rows:
        object_id = str(row["object_id"])
        row["annotations"] = annotations.get(object_id, [])
        row["binding_summary"] = bindings.get(object_id, {})
        if include_fields:
            row["fields"] = fields.get(object_id, [])
        items.append(row)
    return {
        "schema_version": CODE_DECLARED_MODEL_QUERY_SCHEMA_VERSION,
        "model_schema_version": CODE_DECLARED_MODEL_SCHEMA_VERSION,
        "not_available": False,
        "filters": {"repo_id": repo_id, "search": search, "type_annotations": requested_annotations, "search_scope": search_scope},
        "items": items,
        "total_count": total,
    }

def get_code_declared_object(
    query: "KnowledgeLayerQuery",
    object_id: str,
) -> dict[str, Any]:
    if not str(object_id or "").strip():
        raise ValueError("object_id must not be empty")
    unavailable = _check_available(query)
    if unavailable:
        return {**unavailable, "object": None}
    with query._connect() as con:
        rows = query._rows(
            con.execute(
                """
                SELECT t.type_occurrence_id AS object_id,t.repo_id,t.fully_qualified_name AS fqcn,
                       t.simple_name AS name,t.package_name,t.type_kind,t.source_set,
                       t.documentation_json,t.source_ref_json,t.modifier_tokens_json,t.type_parameters_json
                FROM code_declared_type t WHERE t.type_occurrence_id=?
                """,
                [object_id],
            )
        )
        if not rows:
            return {
                "schema_version": CODE_DECLARED_MODEL_QUERY_SCHEMA_VERSION,
                "model_schema_version": CODE_DECLARED_MODEL_SCHEMA_VERSION,
                "not_available": False,
                "object": None,
            }
        fields = _field_rows(con, query, [object_id]).get(object_id, [])
        relationships = _relationship_rows(con, query, [object_id]).get(object_id, [])
        binding_summary = _binding_summary_map(con, query, [object_id], {object_id: len(relationships)}).get(object_id, {})
        inheritance = query._rows(
            con.execute(
                """
                SELECT inheritance_occurrence_id,relation_kind,declared_supertype_expression,
                       resolution_status,resolved_supertype_occurrence_id,resolved_fqcn,
                       candidate_fqcns_json,source_ref_json
                FROM code_declared_inheritance WHERE subtype_occurrence_id=?
                ORDER BY relation_kind,declared_supertype_expression,inheritance_occurrence_id
                """,
                [object_id],
            )
        ) if query._has_relation("code_declared_inheritance") else []
    with query._connect() as con:
        type_annotations = _annotation_map(con, query, "type", [object_id]).get(object_id, [])
    row = rows[0]
    row["documentation"] = _doc(row.pop("documentation_json", None))
    row["annotations"] = type_annotations
    row["source_ref"] = _source_ref(row.pop("source_ref_json", None))
    row["modifier_tokens"] = _json(row.pop("modifier_tokens_json", None), [])
    row["type_parameters"] = _json(row.pop("type_parameters_json", None), [])
    for item in inheritance:
        item["candidate_fqcns"] = _json(item.pop("candidate_fqcns_json", None), [])
        item["source_ref"] = _source_ref(item.pop("source_ref_json", None))
    row["fields"] = fields
    row["relationships"] = relationships
    row["binding_summary"] = binding_summary
    row["inheritance"] = inheritance
    return {
        "schema_version": CODE_DECLARED_MODEL_QUERY_SCHEMA_VERSION,
        "model_schema_version": CODE_DECLARED_MODEL_SCHEMA_VERSION,
        "not_available": False,
        "object": row,
    }

def summarize_code_declared_model(
    query: "KnowledgeLayerQuery",
    *,
    repo_id: str | None = None,
    type_annotations: Any = None,
    exclude_field_annotations: Any = None,
) -> dict[str, Any]:
    """Return a deterministic observed summary with caller-selected annotation filters.

    Annotation names are exact observed code facts. KLC does not assign business meaning to
    them; callers may select a subset after inspecting annotation frequencies. Excluded field
    annotations affect effective-field and relationship counts only and remain visible in
    object detail.
    """
    unavailable = _check_available(query)
    selected_annotations = _names(type_annotations)
    excluded_annotations = _names(exclude_field_annotations)
    filters = {
        "repo_id": repo_id,
        "type_annotations": selected_annotations,
        "exclude_field_annotations": excluded_annotations,
    }
    if unavailable:
        return {**unavailable, "filters": filters, "counts": {}, "type_annotation_counts": [], "field_annotation_counts": [], "gap_counts": []}

    type_clauses: list[str] = []
    type_params: list[Any] = []
    if repo_id:
        type_clauses.append("t.repo_id=?")
        type_params.append(repo_id)
    if selected_annotations:
        placeholders = ",".join("?" for _ in selected_annotations)
        type_clauses.append(
            f"EXISTS (SELECT 1 FROM code_declared_annotation ta WHERE ta.target_kind='type' "
            f"AND ta.target_occurrence_id=t.type_occurrence_id AND ta.annotation_name IN ({placeholders}))"
        )
        type_params.extend(selected_annotations)
    type_where = " WHERE " + " AND ".join(type_clauses) if type_clauses else ""

    excluded_sql = ""
    excluded_params: list[Any] = []
    if excluded_annotations:
        placeholders = ",".join("?" for _ in excluded_annotations)
        excluded_sql = (
            f" AND NOT EXISTS (SELECT 1 FROM code_declared_annotation fa WHERE fa.target_kind='field' "
            f"AND fa.target_occurrence_id={{field_expr}} AND fa.annotation_name IN ({placeholders}))"
        )
        excluded_params.extend(excluded_annotations)

    with query._connect() as con:
        type_count = int(con.execute("SELECT count(*) FROM code_declared_type t" + type_where, type_params).fetchone()[0])
        type_ids_sql = "SELECT t.type_occurrence_id FROM code_declared_type t" + type_where
        ef_extra = excluded_sql.format(field_expr="ef.field_occurrence_id") if excluded_sql else ""
        rel_extra = excluded_sql.format(field_expr="r.field_occurrence_id") if excluded_sql else ""
        effective_field_count = int(con.execute(
            f"SELECT count(*) FROM code_declared_effective_field ef WHERE ef.effective_owner_type_occurrence_id IN ({type_ids_sql}){ef_extra}",
            [*type_params, *excluded_params],
        ).fetchone()[0])
        relationship_count = int(con.execute(
            f"SELECT count(*) FROM code_declared_relationship r WHERE r.source_type_occurrence_id IN ({type_ids_sql}){rel_extra}",
            [*type_params, *excluded_params],
        ).fetchone()[0])
        inherited_relationship_count = int(con.execute(
            f"SELECT count(*) FROM code_declared_relationship r WHERE r.source_type_occurrence_id IN ({type_ids_sql}) "
            f"AND coalesce(cast(json_extract(r.provenance_json,'$.is_inherited') as boolean),false){rel_extra}",
            [*type_params, *excluded_params],
        ).fetchone()[0])
        relationship_rows = query._rows(con.execute(
            f"SELECT f.declared_type_expression FROM code_declared_relationship r "
            f"JOIN code_declared_field f ON f.field_occurrence_id=r.field_occurrence_id "
            f"WHERE r.source_type_occurrence_id IN ({type_ids_sql}){rel_extra}",
            [*type_params, *excluded_params],
        ))
        collection_relationship_count = sum(1 for row in relationship_rows if _cardinality_hint(row.get("declared_type_expression"))[0] == "many")
        inheritance_count = int(con.execute(
            f"SELECT count(*) FROM code_declared_inheritance i WHERE i.subtype_occurrence_id IN ({type_ids_sql})",
            type_params,
        ).fetchone()[0]) if query._has_relation("code_declared_inheritance") else 0
        gap_clauses = ["1=1"]
        gap_params: list[Any] = []
        if repo_id:
            gap_clauses.append("repo_id=?")
            gap_params.append(repo_id)
        gap_count = int(con.execute("SELECT count(*) FROM code_declared_model_gap WHERE " + " AND ".join(gap_clauses), gap_params).fetchone()[0]) if query._has_relation("code_declared_model_gap") else 0
        type_ann = query._rows(con.execute(
            "SELECT annotation_name,count(*) AS count FROM code_declared_annotation "
            "WHERE target_kind='type'" + (" AND repo_id=?" if repo_id else "") +
            " GROUP BY annotation_name ORDER BY count DESC,lower(annotation_name)",
            [repo_id] if repo_id else [],
        )) if query._has_relation("code_declared_annotation") else []
        field_ann = query._rows(con.execute(
            "SELECT annotation_name,count(*) AS count FROM code_declared_annotation "
            "WHERE target_kind='field'" + (" AND repo_id=?" if repo_id else "") +
            " GROUP BY annotation_name ORDER BY count DESC,lower(annotation_name)",
            [repo_id] if repo_id else [],
        )) if query._has_relation("code_declared_annotation") else []
        gaps = query._rows(con.execute(
            "SELECT gap_code,severity,count(*) AS count FROM code_declared_model_gap " +
            (("WHERE repo_id=? ") if repo_id else "") +
            "GROUP BY gap_code,severity ORDER BY count DESC,gap_code,severity",
            [repo_id] if repo_id else [],
        )) if query._has_relation("code_declared_model_gap") else []
        build_rows = query._rows(con.execute(
            "SELECT scope_id,builder_version,build_status,completed_at FROM code_declared_model_build ORDER BY completed_at DESC LIMIT 1"
        ))
    return {
        "schema_version": CODE_DECLARED_MODEL_QUERY_SCHEMA_VERSION,
        "model_schema_version": CODE_DECLARED_MODEL_SCHEMA_VERSION,
        "not_available": False,
        "filters": filters,
        "build": build_rows[0] if build_rows else {},
        "counts": {
            "type_count": type_count,
            "effective_field_count": effective_field_count,
            "relationship_count": relationship_count,
            "collection_relationship_count": collection_relationship_count,
            "inherited_relationship_count": inherited_relationship_count,
            "inheritance_declaration_count": inheritance_count,
            "gap_count": gap_count,
        },
        "type_annotation_counts": type_ann,
        "field_annotation_counts": field_ann,
        "gap_counts": gaps,
    }

