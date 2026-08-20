from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Iterable, Mapping

import duckdb


_IDENTIFIER = re.compile(r"^[A-Za-z_$][A-Za-z0-9_$]*$")
_ENCODING_FACT_TYPES = (
    "storage_reference_encoding_observation",
    "reference_encoding_semantics_observation",
    "builder_api_semantic_observation",
)
_STORAGE_KEY_TABLE_CANDIDATES = (
    "model_storage_record_key_observation",
    "model_relationship_storage_target_key",
)


def _json_value(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, (dict, list, tuple, bool, int, float)):
        return value
    try:
        return json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _rows(con: duckdb.DuckDBPyConnection, sql: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
    cursor = con.execute(sql, list(params))
    columns = [item[0] for item in cursor.description]
    return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


def _java_string_literal(value: Any) -> str | None:
    text = str(value or "").strip()
    if len(text) < 2 or text[0] != '"' or text[-1] != '"':
        return None
    try:
        decoded = json.loads(text)
    except json.JSONDecodeError:
        return None
    return decoded if isinstance(decoded, str) else None


def _table_names(con: duckdb.DuckDBPyConnection) -> set[str]:
    return {
        str(row[0])
        for row in con.execute("SELECT table_name FROM duckdb_tables() WHERE internal = false").fetchall()
    }


def _source_observations_by_id(
    con: duckdb.DuckDBPyConnection,
    occurrence_ids: Iterable[str],
) -> list[dict[str, Any]]:
    ids = sorted({str(item) for item in occurrence_ids if str(item).strip()})
    if not ids:
        return []
    placeholders = ",".join("?" for _ in ids)
    return _rows(
        con,
        f"""SELECT source_observation_occurrence_id, repo_id, fact_type, name,
                    owner_fqcn, owner_operation, target_method, argument_index,
                    source_expression, target_variable, expression_text,
                    source_path, line_start, line_end, payload_json
             FROM source_observation
             WHERE source_observation_occurrence_id IN ({placeholders})
             ORDER BY repo_id, source_path, line_start, source_observation_occurrence_id""",
        ids,
    )


def _reference_operations(
    con: duckdb.DuckDBPyConnection,
    relationship: Mapping[str, Any],
) -> list[dict[str, Any]]:
    ids = _json_value(relationship.get("converter_operation_observation_ids_json"), [])
    result: list[dict[str, Any]] = []
    for row in _source_observations_by_id(con, ids):
        if row.get("fact_type") != "tsa_reference_operation_observation":
            continue
        payload = _json_value(row.get("payload_json"), {})
        properties = payload.get("properties") if isinstance(payload, dict) else {}
        properties = properties if isinstance(properties, dict) else {}
        arguments = list(properties.get("argument_expressions") or [])
        value_expression = str(arguments[1] or "").strip() if len(arguments) > 1 else ""
        result.append(
            {
                "observation_id": row.get("source_observation_occurrence_id"),
                "repo_id": row.get("repo_id"),
                "owner_operation": properties.get("owner_operation") or row.get("owner_operation"),
                "reference_operation": properties.get("method") or row.get("target_method"),
                "relationship_field": (
                    _java_string_literal(arguments[0]) if arguments else None
                ),
                "value_expression": value_expression,
                "value_identifier": value_expression if _IDENTIFIER.fullmatch(value_expression) else None,
                "source_path": row.get("source_path"),
                "line_start": row.get("line_start"),
                "line_end": row.get("line_end"),
            }
        )
    return result


def _local_result_binding_diagnostics(
    con: duckdb.DuckDBPyConnection,
    references: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for reference in references:
        owner_operation = str(reference.get("owner_operation") or "")
        identifier = str(reference.get("value_identifier") or "")
        if not owner_operation or not identifier:
            output.append(
                {
                    "reference_observation_id": reference.get("observation_id"),
                    "status": "not_applicable_or_inline",
                    "owner_operation": owner_operation or None,
                    "value_expression": reference.get("value_expression"),
                    "candidate_count": 0,
                    "candidates": [],
                }
            )
            continue
        candidates = _rows(
            con,
            """SELECT source_observation_occurrence_id, repo_id, name, owner_operation,
                      target_variable, source_path, line_start, line_end, payload_json
               FROM source_observation
               WHERE fact_type='java_call_result_binding_observation'
                 AND owner_operation=? AND target_variable=?
               ORDER BY source_path, line_start, source_observation_occurrence_id""",
            [owner_operation, identifier],
        )
        simplified: list[dict[str, Any]] = []
        for candidate in candidates:
            payload = _json_value(candidate.get("payload_json"), {})
            properties = payload.get("properties") if isinstance(payload, dict) else {}
            properties = properties if isinstance(properties, dict) else {}
            simplified.append(
                {
                    "observation_id": candidate.get("source_observation_occurrence_id"),
                    "callee_operation": properties.get("callee_operation"),
                    "resolution": properties.get("resolution"),
                    "source_path": candidate.get("source_path"),
                    "line_start": candidate.get("line_start"),
                    "line_end": candidate.get("line_end"),
                }
            )
        if len(simplified) == 1:
            status = "resolved_unique"
        elif len(simplified) > 1:
            status = "ambiguous_reused_local_name"
        else:
            status = "unresolved_no_result_binding"
        reference_line = int(reference.get("line_start") or 0)
        preceding = [
            row for row in simplified
            if row.get("line_start") is not None and int(row["line_start"]) <= reference_line
        ]
        nearest_preceding = max(preceding, key=lambda row: int(row.get("line_start") or 0), default=None)
        output.append(
            {
                "reference_observation_id": reference.get("observation_id"),
                "status": status,
                "owner_operation": owner_operation,
                "value_expression": reference.get("value_expression"),
                "value_identifier": identifier,
                "candidate_count": len(simplified),
                "nearest_preceding_candidate": nearest_preceding,
                "candidates": simplified,
                "current_core_matching_key": [owner_operation, identifier],
                "diagnostic_note": (
                    "The current interpreter groups result bindings by owner operation and local variable name; "
                    "it does not use lexical scope or source position to select a dominating assignment."
                    if len(simplified) > 1
                    else None
                ),
            }
        )
    return output


def diagnose_relationship_storage_evidence(
    con: duckdb.DuckDBPyConnection,
    relationship_id: str,
) -> dict[str, Any]:
    """Explain whether a relationship has enough evidence for a physical join.

    The function is diagnostic only. It reports observations and missing evidence;
    it never infers an encoding, normalizes an alias, or confirms a SQL predicate.
    """
    relationships = _rows(
        con,
        "SELECT * FROM model_relationship_observation WHERE relationship_id=?",
        [relationship_id],
    )
    if not relationships:
        raise ValueError(f"relationship not found: {relationship_id}")
    relationship = relationships[0]

    target_key_ids = [
        str(item)
        for item in _json_value(relationship.get("target_key_observation_ids_json"), [])
        if str(item).strip()
    ]
    logical_key_observations = _rows(
        con,
        """SELECT key_observation_id, repo_id, object_fqcn, annotation_name,
                  annotation_fqcn, observation_basis, source_path, line_start, line_end
           FROM model_object_key_observation
           WHERE key_observation_id IN (SELECT unnest(?::VARCHAR[]))
           ORDER BY key_observation_id""",
        [target_key_ids],
    ) if target_key_ids else []
    logical_key_members = _rows(
        con,
        """SELECT key_observation_id, position, role_name, field_name,
                  field_owner_fqcn, field_resolution_kind
           FROM model_object_key_member
           WHERE key_observation_id IN (SELECT unnest(?::VARCHAR[]))
           ORDER BY key_observation_id, position, field_name""",
        [target_key_ids],
    ) if target_key_ids else []

    key_expressions = _rows(
        con,
        """SELECT key_expression_id, endpoint_role, expression_text,
                  source_repo_ids_json, converter_owner_fqcns_json,
                  owner_methods_json, source_observation_occurrence_ids_json
           FROM model_relationship_key_expression
           WHERE relationship_id=?
           ORDER BY endpoint_role, expression_text, key_expression_id""",
        [relationship_id],
    )
    storage_lineages = _rows(
        con,
        """SELECT key_lineage_id, lineage_repo_id, source_observation_occurrence_id,
                  source_alias, relationship_field, target_alias, target_storage_key_field, reference_operation,
                  source_operation, collection_helper_operation, target_key_operation,
                  source_key_expression, target_key_expression_template,
                  composed_target_key_expression, source_key_passed_into_target_key,
                  binding_path_json, observation_basis
           FROM model_relationship_storage_key_derivation
           WHERE relationship_id=?
           ORDER BY key_lineage_id""",
        [relationship_id],
    )
    correspondences = _rows(
        con,
        """SELECT correspondence_id, reference_value_observation_occurrence_id,
                  target_key_observation_occurrence_id, source_alias,
                  relationship_field, target_alias, reference_operation,
                  source_operation, value_converter_operation,
                  composed_reference_value_expression, target_key_expression,
                  target_key_fields_json, match_basis, observation_basis
           FROM model_relationship_reference_value_key_correspondence
           WHERE relationship_id=?
           ORDER BY correspondence_id""",
        [relationship_id],
    )

    first_class_storage_references = _rows(
        con,
        """SELECT storage_reference_id, source_repo_id,
                  source_observation_occurrence_id, source_alias, relationship_field,
                  reference_operation, source_operation, reference_value_expression,
                  reference_value_binding_resolution, target_converter_operation,
                  target_storage_record_observation_local_id,
                  target_storage_record_observation_occurrence_id, target_alias,
                  target_storage_key_field, target_storage_key_expression,
                  target_storage_key_local_variable,
                  target_storage_key_input_symbols_json, value_origin, type_source,
                  key_source, physical_encoding, binding_path_json, observation_basis
           FROM model_relationship_storage_reference
           WHERE relationship_id=?
           ORDER BY source_repo_id, source_observation_occurrence_id, storage_reference_id""",
        [relationship_id],
    )

    polymorphic_targets = _rows(
        con,
        """SELECT polymorphic_target_id, target_type_fqcn, target_java_type_occurrence_id,
                  source_repo_ids_json, source_observation_occurrence_ids_json
           FROM model_relationship_polymorphic_target
           WHERE relationship_id=?
           ORDER BY target_type_fqcn, polymorphic_target_id""",
        [relationship_id],
    )
    target_alias = str(relationship.get("target_type_fqcn") or "")
    accepted_target_aliases = {target_alias} if target_alias else set()
    accepted_target_aliases.update(
        str(row.get("target_type_fqcn") or "")
        for row in polymorphic_targets
        if str(row.get("target_type_fqcn") or "").strip()
    )
    alias_rows = _rows(
        con,
        """SELECT source_observation_occurrence_id, repo_id, owner_fqcn,
                  owner_operation, source_expression, source_path, line_start, line_end
           FROM source_observation
           WHERE fact_type='call_argument_flow_observation'
             AND target_method='alias' AND argument_index=0
           ORDER BY repo_id, owner_operation, line_start, source_observation_occurrence_id""",
    )
    matching_alias_rows: list[dict[str, Any]] = []
    for row in alias_rows:
        observed_alias = _java_string_literal(row.get("source_expression"))
        if observed_alias not in accepted_target_aliases:
            continue
        matching_alias_rows.append({**row, "observed_alias": observed_alias})
    target_operations = sorted({
        (str(row.get("repo_id") or ""), str(row.get("owner_operation") or ""))
        for row in matching_alias_rows
        if row.get("repo_id") and row.get("owner_operation")
    })

    target_key_assignments: list[dict[str, Any]] = []
    for repo_id, operation in target_operations:
        target_key_assignments.extend(
            _rows(
                con,
                """SELECT source_observation_occurrence_id, repo_id, owner_fqcn,
                          owner_operation, key_expression, key_expression_tree_json,
                          source_path, line_start, line_end
                   FROM v_tsa_key_expressions
                   WHERE repo_id=? AND owner_operation=?
                   ORDER BY line_start, source_observation_occurrence_id""",
                [repo_id, operation],
            )
        )

    references = _reference_operations(con, relationship)
    local_binding_diagnostics = _local_result_binding_diagnostics(con, references)
    reference_derivations = _rows(
        con,
        """SELECT source_observation_occurrence_id, repo_id, source_alias,
                  relationship_field, reference_operation, source_operation,
                  value_converter_operation, reference_value_expression,
                  return_expression_template, composed_reference_value_expression,
                  value_converter_parameter_bindings_json, binding_path_json,
                  observation_policy
           FROM v_tsa_reference_value_derivations
           WHERE source_alias=? AND relationship_field=?
           ORDER BY repo_id, source_operation, source_observation_occurrence_id""",
        [relationship.get("source_object_fqcn"), relationship.get("source_field_name")],
    )

    encoding_semantics = _rows(
        con,
        """SELECT source_observation_occurrence_id, repo_id, fact_type, name,
                  owner_fqcn, owner_operation, source_path, line_start, line_end,
                  payload_json
           FROM source_observation
           WHERE fact_type IN (?,?,?)
           ORDER BY repo_id, source_path, line_start, source_observation_occurrence_id""",
        list(_ENCODING_FACT_TYPES),
    )

    tables = _table_names(con)
    first_class_storage_tables = (
        ["model_relationship_storage_reference"]
        if first_class_storage_references and "model_relationship_storage_reference" in tables
        else []
    )
    logical_fields = [str(row.get("field_name") or "") for row in logical_key_members]
    target_expression_texts = [
        str(row.get("expression_text") or "")
        for row in key_expressions
        if row.get("endpoint_role") == "target"
    ]

    root_causes: list[dict[str, Any]] = []
    ambiguous = [row for row in local_binding_diagnostics if row.get("status") == "ambiguous_reused_local_name"]
    if ambiguous:
        root_causes.append(
            {
                "code": "scope_insensitive_local_result_binding",
                "layer": "code-analyzer-core",
                "evidence": [row.get("reference_observation_id") for row in ambiguous],
                "effect": "return-to-referenceField derivation is not emitted when a local name is reused",
            }
        )
    if target_key_assignments and not first_class_storage_tables:
        root_causes.append(
            {
                "code": "storage_record_key_not_first_class",
                "layer": "knowledge-layer-core schema/materialization",
                "evidence": [row.get("source_observation_occurrence_id") for row in target_key_assignments],
                "effect": "observed builder key assignments remain expressions and cannot become a canonical physical target field",
            }
        )
    if target_key_assignments and logical_fields and not correspondences and not first_class_storage_references:
        root_causes.append(
            {
                "code": "logical_identity_is_only_correspondence_domain",
                "layer": "knowledge-layer-core correspondence",
                "evidence": target_key_ids,
                "effect": "reference/value matching is canonicalized only against model_object_key_member fields",
            }
        )
    if not encoding_semantics:
        root_causes.append(
            {
                "code": "reference_encoding_semantics_not_observed",
                "layer": "evidence contract",
                "evidence": [],
                "effect": "alias and key calls do not by themselves prove an encoded source value or alias normalization rule",
            }
        )

    return {
        "diagnostic_schema": "relationship_storage_evidence_diagnostic/v2",
        "relationship": {
            "relationship_id": relationship_id,
            "source_repo_id": relationship.get("source_repo_id"),
            "source_object_fqcn": relationship.get("source_object_fqcn"),
            "source_field_name": relationship.get("source_field_name"),
            "target_repo_id": relationship.get("target_repo_id"),
            "target_type_fqcn": relationship.get("target_type_fqcn"),
            "relation_kind": relationship.get("relation_kind"),
            "cardinality": relationship.get("cardinality"),
        },
        "logical_identity": {
            "status": "observed" if logical_key_members else "not_observed",
            "key_observations": logical_key_observations,
            "members": logical_key_members,
            "field_names": logical_fields,
        },
        "storage_key_evidence": {
            "status": (
                "observed_first_class"
                if first_class_storage_references
                else "observed_not_first_class"
                if target_key_assignments
                else "not_observed"
            ),
            "accepted_target_aliases": sorted(accepted_target_aliases),
            "polymorphic_targets": polymorphic_targets,
            "target_alias_assignments": matching_alias_rows,
            "target_key_assignments": target_key_assignments,
            "relationship_target_expressions": target_expression_texts,
            "storage_lineages": storage_lineages,
            "first_class_storage_tables": first_class_storage_tables,
            "first_class_storage_references": first_class_storage_references,
        },
        "reference_value_flow": {
            "status": (
                "observed"
                if reference_derivations or first_class_storage_references
                else "ambiguous"
                if ambiguous
                else "not_observed"
            ),
            "reference_operations": references,
            "local_result_binding_diagnostics": local_binding_diagnostics,
            "reference_value_derivations": reference_derivations,
        },
        "logical_key_correspondence": {
            "status": "observed" if correspondences else "not_observed",
            "correspondences": correspondences,
            "canonicalization_fields": logical_fields,
        },
        "reference_encoding": {
            "status": (
                "observed"
                if encoding_semantics
                else "downstream_interpretation_required"
                if first_class_storage_references
                else "unresolved"
            ),
            "semantic_observations": encoding_semantics,
            "storage_reference_encodings": sorted({
                str(row.get("physical_encoding") or "")
                for row in first_class_storage_references
                if str(row.get("physical_encoding") or "").strip()
            }),
            "diagnostic_note": (
                "Target alias, physical storage-key field/expression and value origin are first-class; final physical formatting remains downstream."
                if first_class_storage_references and not encoding_semantics
                else "No physical encoding or alias normalization is inferred from separate alias(...) and key(...) calls."
                if not encoding_semantics
                else None
            ),
        },
        "physical_join": {
            "status": "unresolved",
            "confirmed": False,
            "reason": (
                "First-class target alias and storage-key evidence are available, but final physical encoding is delegated downstream."
                if first_class_storage_references
                else "A physical join requires a first-class storage key, resolved reference value flow, and observed encoding semantics."
            ),
        },
        "root_causes": root_causes,
        "safety": {
            "domain_specific_rules_used": False,
            "alias_normalization_inferred": False,
            "physical_join_inferred": False,
        },
    }


def diagnose_relationship_storage_evidence_path(
    database_path: str | Path,
    relationship_id: str,
) -> dict[str, Any]:
    path = Path(database_path)
    con = duckdb.connect(str(path), read_only=True)
    try:
        return diagnose_relationship_storage_evidence(con, relationship_id)
    finally:
        con.close()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Explain observed and missing storage-key evidence for one model relationship."
    )
    parser.add_argument("--database", required=True, help="Path to knowledge-layer.duckdb")
    parser.add_argument("--relationship-id", required=True)
    parser.add_argument("--output", help="Write JSON to this file instead of stdout")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    result = diagnose_relationship_storage_evidence_path(args.database, args.relationship_id)
    content = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(content, encoding="utf-8")
    else:
        print(content, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
