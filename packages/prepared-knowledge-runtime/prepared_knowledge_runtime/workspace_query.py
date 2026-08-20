from __future__ import annotations

import base64
import hashlib
import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

try:
    import duckdb
except ModuleNotFoundError:  # runtime dependency; catalog and preflight remain available
    duckdb = None  # type: ignore[assignment]

from .database import connect_database
from .query import KnowledgeLayerQuery

from .normalization import normalize_db_identifier
from .evidence_layout import CONFIGURATION_FACT_TYPES

TSA_FACT_TYPES = (
    "tsa_annotation_observation",
    "tsa_converter_configuration_observation",
    "tsa_configuration_directive_observation",
    "tsa_reference_operation_observation",
    "tsa_key_expression_observation",
    "tsa_storage_key_lineage_observation",
    "tsa_reference_value_derivation_observation",
)


def _exact_string_literal(expression: Any) -> str | None:
    """Return a literal string only; never evaluate or normalize an expression."""
    text = str(expression or "").strip()
    if len(text) < 2 or text[0] != text[-1] or text[0] not in {"'", '"'}:
        return None
    if text[0] == '"':
        try:
            value = json.loads(text)
        except (TypeError, ValueError, json.JSONDecodeError):
            return None
        return value if isinstance(value, str) else None
    # Java/YAML-style single-quoted literal. Only quote unescaping is applied.
    return text[1:-1].replace("''", "'").replace("\\'", "'")


class WorkspaceKnowledgeQuery(KnowledgeLayerQuery):



























    def tsa_observations(
        self,
        token: str = "",
        repo_id: str | None = None,
        fact_type: str | None = None,
        owner_fqcn: str | None = None,
        max_results: int = 100,
        page_token: str = "",
    ) -> dict[str, Any]:
        if fact_type is not None and fact_type not in TSA_FACT_TYPES:
            allowed = ", ".join(TSA_FACT_TYPES)
            raise ValueError(f"unsupported TSA fact_type: {fact_type!r}; expected one of: {allowed}")
        selected = (fact_type,) if fact_type else TSA_FACT_TYPES
        placeholders = ",".join("?" for _ in selected)
        clauses = [f"fact_type IN ({placeholders})"]
        args: list[Any] = list(selected)
        if token:
            clauses.append("lower(coalesce(name,'') || ' ' || coalesce(owner_fqcn,'') || ' ' || coalesce(configuration_path,'') || ' ' || coalesce(payload_json::VARCHAR,'')) LIKE ?")
            args.append(f"%{token.lower()}%")
        if repo_id:
            clauses.append("repo_id=?")
            args.append(repo_id)
        if owner_fqcn:
            clauses.append("owner_fqcn=?")
            args.append(owner_fqcn)
        where = " AND ".join(clauses)
        return self._paged_select(
            kind="workspace-data-model-tsa-observations",
            query_id="tsa_observations",
            select_sql=f"SELECT * FROM source_observation WHERE {where} ORDER BY repo_id, fact_type, source_path, line_start, occurrence_ordinal",
            count_sql=f"SELECT count(*) FROM source_observation WHERE {where}",
            args=args,
            filters={"token": token, "repo_id": repo_id, "fact_type": fact_type, "owner_fqcn": owner_fqcn},
            max_results=max_results,
            page_token=page_token,
        )

    def model_configuration_directives(
        self,
        token: str = "",
        directive_kind: str | None = None,
        object_id: str = "",
        field_name: str = "",
        repo_id: str | None = None,
        max_results: int = 100,
        page_token: str = "",
    ) -> dict[str, Any]:
        """Return normalized configuration directives and mechanically paired sibling values."""
        clauses = ["1=1"]
        args: list[Any] = []
        if token:
            clauses.append(
                "lower(coalesce(d.directive_value,'') || ' ' || coalesce(d.configuration_path,'') || ' ' "
                "|| coalesce(d.configured_target_type,'') || ' ' || coalesce(d.converter_instantiator,'')) LIKE ?"
            )
            args.append(f"%{token.lower()}%")
        if directive_kind:
            clauses.append("d.directive_kind=?")
            args.append(directive_kind)
        if object_id:
            clauses.append("d.object_fqcn=?")
            args.append(object_id)
        if field_name:
            clauses.append("d.field_name=?")
            args.append(field_name)
        if repo_id:
            clauses.append("d.directive_repo_id=?")
            args.append(repo_id)
        where = " AND ".join(clauses)
        filters = {
            "token": token,
            "directive_kind": directive_kind,
            "object_id": object_id,
            "field_name": field_name,
            "repo_id": repo_id,
        }
        return self._paged_select(
            kind="workspace-data-model-configuration-directives",
            query_id="model_configuration_directives",
            select_sql=f"""SELECT d.* FROM v_model_configuration_directives d
                           WHERE {where}
                           ORDER BY d.directive_kind, d.directive_value, d.configuration_path, d.directive_observation_id""",
            count_sql=f"SELECT count(*) FROM v_model_configuration_directives d WHERE {where}",
            args=args,
            filters=filters,
            max_results=max_results,
            page_token=page_token,
        )

    def model_configuration_directive_matches(
        self,
        directive_kind: str | None = None,
        object_id: str = "",
        field_name: str = "",
        match_kind: str | None = None,
        max_results: int = 100,
        page_token: str = "",
    ) -> dict[str, Any]:
        """Return exact directive-to-object/field correspondences without applying an exclusion or publication verdict."""
        clauses = ["1=1"]
        args: list[Any] = []
        if directive_kind:
            clauses.append("m.directive_kind=?")
            args.append(directive_kind)
        if object_id:
            clauses.append("m.matched_object_fqcn=?")
            args.append(object_id)
        if field_name:
            clauses.append("m.matched_field_name=?")
            args.append(field_name)
        if match_kind:
            clauses.append("m.match_kind=?")
            args.append(match_kind)
        where = " AND ".join(clauses)
        filters = {
            "directive_kind": directive_kind,
            "object_id": object_id,
            "field_name": field_name,
            "match_kind": match_kind,
        }
        return self._paged_select(
            kind="workspace-data-model-configuration-directive-matches",
            query_id="model_configuration_directive_matches",
            select_sql=f"""SELECT m.* FROM v_model_configuration_directive_matches m
                           WHERE {where}
                           ORDER BY m.directive_kind, m.matched_repo_id, m.matched_object_fqcn,
                                    m.matched_field_name, m.directive_observation_id""",
            count_sql=f"SELECT count(*) FROM v_model_configuration_directive_matches m WHERE {where}",
            args=args,
            filters=filters,
            max_results=max_results,
            page_token=page_token,
        )

    def model_object_configuration(
        self,
        object_id: str = "",
        repo_id: str | None = None,
        excluded_only: bool = False,
    ) -> dict[str, Any]:
        """Return object key observations with exact configured type-exclusion evidence."""
        clauses = ["1=1"]
        args: list[Any] = []
        if object_id:
            clauses.append("(object_fqcn=? OR java_type_occurrence_id=? OR key_observation_id=?)")
            args.extend([object_id, object_id, object_id])
        if repo_id:
            clauses.append("repo_id=?")
            args.append(repo_id)
        if excluded_only:
            clauses.append("configuration_type_exclusion_observed")
        where = " AND ".join(clauses)
        with self._connect() as con:
            rows = self._rows(con.execute(
                f"""SELECT * FROM v_model_object_configuration_observations
                    WHERE {where}
                    ORDER BY repo_id, object_fqcn, key_observation_id""",
                args,
            ))
        return {
            "kind": "workspace-data-model-object-configuration",
            "filters": {"object_id": object_id, "repo_id": repo_id, "excluded_only": excluded_only},
            "total_count": len(rows),
            "items": rows,
        }


    def type_reference_resolutions(self, token: str = "", source_repo_id: str | None = None, target_repo_id: str | None = None, match_scope: str | None = None, max_results: int = 100, page_token: str = "") -> dict[str, Any]:
        clauses = ["1=1"]
        args: list[Any] = []
        if token:
            clauses.append("lower(coalesce(owner_fqcn,'') || ' ' || coalesce(referenced_type,'') || ' ' || candidate_fqcn) LIKE ?")
            args.append(f"%{token.lower()}%")
        if source_repo_id:
            clauses.append("source_repo_id=?")
            args.append(source_repo_id)
        if target_repo_id:
            clauses.append("target_repo_id=?")
            args.append(target_repo_id)
        if match_scope:
            clauses.append("match_scope=?")
            args.append(match_scope)
        where = " AND ".join(clauses)
        filters = {"token": token, "source_repo_id": source_repo_id, "target_repo_id": target_repo_id, "match_scope": match_scope}
        return self._paged_select(
            kind="workspace-data-model-type-reference-resolutions",
            query_id="type_reference_resolutions",
            select_sql=f"SELECT * FROM type_reference_resolution_candidate WHERE {where} ORDER BY source_repo_id, owner_fqcn, candidate_fqcn, target_repo_id, target_java_type_occurrence_id",
            count_sql=f"SELECT count(*) FROM type_reference_resolution_candidate WHERE {where}",
            args=args,
            filters=filters,
            max_results=max_results,
            page_token=page_token,
        )





    def model_object_fields(
        self,
        object_id: str = "",
        repo_id: str | None = None,
        inherited: bool | None = None,
        key_only: bool = False,
    ) -> dict[str, Any]:
        """Return effective direct/inherited fields for configured model objects with observed key-role membership."""
        clauses = ["1=1"]
        args: list[Any] = []
        if object_id:
            clauses.append("(object_fqcn=? OR java_type_occurrence_id=? OR key_observation_id=?)")
            args.extend([object_id, object_id, object_id])
        if repo_id:
            clauses.append("repo_id=?")
            args.append(repo_id)
        if inherited is not None:
            clauses.append("inherited=?")
            args.append(bool(inherited))
        if key_only:
            clauses.append("key_member_id IS NOT NULL")
        where = " AND ".join(clauses)
        with self._connect() as con:
            rows = self._rows(con.execute(
                f"""SELECT * FROM v_model_object_fields WHERE {where}
                    ORDER BY repo_id, object_fqcn, inherited, field_name, key_position, effective_field_occurrence_id""",
                args,
            ))
            storage_by_field = self._model_field_storage_observations(con, rows)
        for row in rows:
            key = (str(row.get("object_fqcn") or ""), str(row.get("field_name") or ""))
            observations = storage_by_field.get(key, ())
            row["storage_observation_count"] = len(observations)
            row["storage_observations"] = list(observations[:20])
            row["storage_observations_truncated"] = len(observations) > 20
        return {
            "kind": "workspace-data-model-object-fields",
            "filters": {"object_id": object_id, "repo_id": repo_id, "inherited": inherited, "key_only": key_only},
            "total_count": len(rows),
            "items": rows,
        }

    def _model_field_storage_observations(
        self,
        con: Any,
        field_rows: list[dict[str, Any]],
    ) -> dict[tuple[str, str], tuple[dict[str, Any], ...]]:
        """Project exact converter alias + primitive-field calls onto model fields.

        This is an observation projection, not a semantic value-mapping verdict. An
        item is attached only when both the converter alias and the primitive field
        name are exact string literals and the latter exactly equals a model field.
        """
        requested = {
            (str(row.get("object_fqcn") or ""), str(row.get("field_name") or ""))
            for row in field_rows
            if row.get("object_fqcn") and row.get("field_name")
        }
        if not requested or not self._has_relation("source_observation"):
            return {}
        cursor = con.execute(
            """
            WITH aliases AS (
                SELECT repo_id, owner_fqcn, owner_method, source_expression AS alias_expression,
                       source_observation_occurrence_id AS alias_observation_id,
                       source_path AS alias_source_path, line_start AS alias_line_start,
                       line_end AS alias_line_end, extractor AS alias_extractor
                FROM source_observation
                WHERE fact_type='call_argument_flow_observation'
                  AND target_method='alias' AND argument_index=0
            ), primitive_names AS (
                SELECT repo_id, owner_fqcn, owner_method, call_observation_local_id,
                       source_expression AS physical_field_expression,
                       source_observation_occurrence_id AS field_name_observation_id,
                       source_path, line_start, line_end, extractor
                FROM source_observation
                WHERE fact_type='call_argument_flow_observation'
                  AND target_method='primitiveField' AND argument_index=0
                  AND call_observation_local_id IS NOT NULL
            ), primitive_values AS (
                SELECT repo_id, owner_fqcn, owner_method, call_observation_local_id,
                       source_expression AS value_expression,
                       source_observation_occurrence_id AS value_observation_id,
                       source_path AS value_source_path, line_start AS value_line_start,
                       line_end AS value_line_end, extractor AS value_extractor
                FROM source_observation
                WHERE fact_type='call_argument_flow_observation'
                  AND target_method='primitiveField' AND argument_index=1
                  AND call_observation_local_id IS NOT NULL
            )
            SELECT a.repo_id, a.owner_fqcn, a.owner_method, a.alias_expression,
                   a.alias_observation_id, a.alias_source_path, a.alias_line_start,
                   a.alias_line_end, a.alias_extractor,
                   n.call_observation_local_id, n.physical_field_expression,
                   n.field_name_observation_id, n.source_path, n.line_start, n.line_end, n.extractor,
                   v.value_expression, v.value_observation_id, v.value_source_path,
                   v.value_line_start, v.value_line_end, v.value_extractor
            FROM aliases a
            JOIN primitive_names n
              ON n.repo_id=a.repo_id
             AND n.owner_fqcn IS NOT DISTINCT FROM a.owner_fqcn
             AND n.owner_method IS NOT DISTINCT FROM a.owner_method
            LEFT JOIN primitive_values v
              ON v.repo_id=n.repo_id
             AND v.owner_fqcn IS NOT DISTINCT FROM n.owner_fqcn
             AND v.owner_method IS NOT DISTINCT FROM n.owner_method
             AND v.call_observation_local_id=n.call_observation_local_id
            ORDER BY a.repo_id, a.owner_fqcn, a.owner_method, n.source_path, n.line_start,
                     n.call_observation_local_id, a.alias_observation_id
            """
        )
        raw_rows = self._rows(cursor)
        grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
        seen: set[tuple[str, str, str, str]] = set()
        for item in raw_rows:
            object_alias = _exact_string_literal(item.get("alias_expression"))
            physical_field = _exact_string_literal(item.get("physical_field_expression"))
            key = (object_alias or "", physical_field or "")
            if key not in requested:
                continue
            dedup = (
                key[0], key[1], str(item.get("field_name_observation_id") or ""),
                str(item.get("alias_observation_id") or ""),
            )
            if dedup in seen:
                continue
            seen.add(dedup)
            evidence = [
                {
                    "observation_id": item.get("alias_observation_id"),
                    "repo_id": item.get("repo_id"),
                    "role": "object_alias",
                    "file": item.get("alias_source_path"),
                    "line_start": item.get("alias_line_start"),
                    "line_end": item.get("alias_line_end"),
                    "extractor": item.get("alias_extractor"),
                },
                {
                    "observation_id": item.get("field_name_observation_id"),
                    "repo_id": item.get("repo_id"),
                    "role": "physical_field_name",
                    "file": item.get("source_path"),
                    "line_start": item.get("line_start"),
                    "line_end": item.get("line_end"),
                    "extractor": item.get("extractor"),
                },
            ]
            if item.get("value_observation_id"):
                evidence.append({
                    "observation_id": item.get("value_observation_id"),
                    "repo_id": item.get("repo_id"),
                    "role": "value_expression",
                    "file": item.get("value_source_path"),
                    "line_start": item.get("value_line_start"),
                    "line_end": item.get("value_line_end"),
                    "extractor": item.get("value_extractor"),
                })
            grouped.setdefault(key, []).append({
                "physical_field_name": physical_field,
                "operation": "primitiveField",
                "object_alias": object_alias,
                "value_expression": item.get("value_expression"),
                "converter_owner_fqcn": item.get("owner_fqcn"),
                "converter_method": item.get("owner_method"),
                "call_observation_id": item.get("call_observation_local_id"),
                "match_basis": "exact_converter_alias_and_exact_model_field_name",
                "value_mapping_status": "observed_expression_not_semantically_interpreted",
                "evidence": evidence,
            })
        return {
            key: tuple(sorted(values, key=lambda value: (
                str(value.get("converter_owner_fqcn") or ""),
                str(value.get("converter_method") or ""),
                str(value.get("call_observation_id") or ""),
            )))
            for key, values in grouped.items()
        }


    def model_relationship_join_evidence(
        self,
        relationship_id: str = "",
        source_object_id: str = "",
        target_object_id: str = "",
    ) -> dict[str, Any]:
        """Return observed key/reference components for relationships without assigning joinability or a verdict."""
        clauses = ["1=1"]
        args: list[Any] = []
        if relationship_id:
            clauses.append("relationship_id=?")
            args.append(relationship_id)
        if source_object_id:
            clauses.append("(source_object_fqcn=? OR source_java_type_occurrence_id=?)")
            args.extend([source_object_id, source_object_id])
        if target_object_id:
            clauses.append("(target_type_fqcn=? OR target_java_type_occurrence_id=?)")
            args.extend([target_object_id, target_object_id])
        where = " AND ".join(clauses)
        with self._connect() as con:
            rows = self._rows(con.execute(
                f"""SELECT * FROM v_model_relationship_join_evidence WHERE {where}
                    ORDER BY source_repo_id, source_object_fqcn, source_field_name, target_type_fqcn, relationship_id""",
                args,
            ))
        return {
            "kind": "workspace-data-model-relationship-join-evidence",
            "filters": {
                "relationship_id": relationship_id,
                "source_object_id": source_object_id,
                "target_object_id": target_object_id,
            },
            "total_count": len(rows),
            "items": rows,
        }


    def model_relationship_key_expression_bindings(
        self,
        relationship_id: str = "",
        endpoint_role: str | None = None,
        reference_operation_observation_id: str = "",
    ) -> dict[str, Any]:
        """Return expression-to-reference-operation bindings as observed facts, without a JOIN verdict."""
        clauses = ["1=1"]
        args: list[Any] = []
        if relationship_id:
            clauses.append("relationship_id=?")
            args.append(relationship_id)
        if endpoint_role:
            clauses.append("endpoint_role=?")
            args.append(endpoint_role)
        if reference_operation_observation_id:
            clauses.append("reference_operation_observation_id=?")
            args.append(reference_operation_observation_id)
        where = " AND ".join(clauses)
        with self._connect() as con:
            rows = self._rows(con.execute(
                f"""SELECT * FROM v_model_relationship_key_expression_bindings WHERE {where}
                    ORDER BY relationship_id, endpoint_role, expression_text,
                             reference_operation_observation_id, key_expression_id""",
                args,
            ))
        return {
            "kind": "workspace-data-model-relationship-key-expression-bindings",
            "filters": {
                "relationship_id": relationship_id,
                "endpoint_role": endpoint_role,
                "reference_operation_observation_id": reference_operation_observation_id,
            },
            "total_count": len(rows),
            "items": rows,
        }


    def model_relationship_storage_key_derivation(
        self,
        relationship_id: str = "",
        source_object_id: str = "",
        target_object_id: str = "",
    ) -> dict[str, Any]:
        """Return exact TSA storage-key lineage observations attached by FQCN/field equality."""
        clauses = ["1=1"]
        args: list[Any] = []
        if relationship_id:
            clauses.append("relationship_id=?")
            args.append(relationship_id)
        if source_object_id:
            clauses.append("source_alias=?")
            args.append(source_object_id)
        if target_object_id:
            clauses.append("target_alias=?")
            args.append(target_object_id)
        where = " AND ".join(clauses)
        with self._connect() as con:
            rows = self._rows(con.execute(
                f"""SELECT * FROM v_model_relationship_storage_key_derivation WHERE {where}
                    ORDER BY relationship_id, lineage_repo_id, source_observation_occurrence_id, key_lineage_id""",
                args,
            ))
        return {
            "kind": "workspace-data-model-relationship-key-lineage",
            "filters": {
                "relationship_id": relationship_id,
                "source_object_id": source_object_id,
                "target_object_id": target_object_id,
            },
            "total_count": len(rows),
            "items": rows,
        }


    def model_relationship_storage_references(
        self,
        relationship_id: str = "",
        source_object_id: str = "",
        target_object_id: str = "",
        source_field: str = "",
    ) -> dict[str, Any]:
        """Return first-class physical storage-key references attached by exact evidence."""
        clauses = ["1=1"]
        args: list[Any] = []
        if relationship_id:
            clauses.append("relationship_id=?")
            args.append(relationship_id)
        if source_object_id:
            clauses.append("source_alias=?")
            args.append(source_object_id)
        if target_object_id:
            clauses.append("target_alias=?")
            args.append(target_object_id)
        if source_field:
            clauses.append("relationship_field=?")
            args.append(source_field)
        where = " AND ".join(clauses)
        with self._connect() as con:
            rows = self._rows(con.execute(
                f"""SELECT * FROM v_model_relationship_storage_references WHERE {where}
                    ORDER BY relationship_id, source_repo_id,
                             source_observation_occurrence_id, storage_reference_id""",
                args,
            ))
        return {
            "kind": "workspace-data-model-relationship-storage-references",
            "filters": {
                "relationship_id": relationship_id,
                "source_object_id": source_object_id,
                "target_object_id": target_object_id,
                "source_field": source_field,
            },
            "total_count": len(rows),
            "items": rows,
        }

    def model_relationship_logical_identity_members(
        self,
        relationship_id: str = "",
    ) -> dict[str, Any]:
        """Return logical identity/version roles separately from storage-record keys."""
        clauses = ["1=1"]
        args: list[Any] = []
        if relationship_id:
            clauses.append("relationship_id=?")
            args.append(relationship_id)
        where = " AND ".join(clauses)
        with self._connect() as con:
            rows = self._rows(con.execute(
                f"""SELECT * FROM v_model_relationship_logical_identity_members WHERE {where}
                    ORDER BY relationship_id, position, key_member_id""",
                args,
            ))
        return {
            "kind": "workspace-data-model-relationship-logical-identity-members",
            "filters": {"relationship_id": relationship_id},
            "total_count": len(rows),
            "items": rows,
        }


    def model_relationships(self, source_object_id: str = "", target_object_id: str = "", relation_kind: str | None = None) -> dict[str, Any]:
        clauses = ["1=1"]
        args: list[Any] = []
        if source_object_id:
            clauses.append("(source_object_fqcn=? OR source_java_type_occurrence_id=?)")
            args.extend([source_object_id, source_object_id])
        if target_object_id:
            clauses.append("(target_type_fqcn=? OR target_java_type_occurrence_id=?)")
            args.extend([target_object_id, target_object_id])
        if relation_kind:
            clauses.append("relation_kind=?")
            args.append(relation_kind)
        where = " AND ".join(clauses)
        with self._connect() as con:
            relationships = self._rows(con.execute(
                f"SELECT * FROM v_model_relationships WHERE {where} ORDER BY source_object_fqcn, source_field_name, relation_kind, target_type_fqcn, relationship_id",
                args,
            ))
            ids = [str(row["relationship_id"]) for row in relationships]
            expressions: list[dict[str, Any]] = []
            polymorphic: list[dict[str, Any]] = []
            key_lineages: list[dict[str, Any]] = []
            reference_value_key_correspondences: list[dict[str, Any]] = []
            storage_references: list[dict[str, Any]] = []
            logical_identity_members: list[dict[str, Any]] = []
            if ids:
                placeholders = ",".join("?" for _ in ids)
                expressions = self._rows(con.execute(
                    f"SELECT * FROM model_relationship_key_expression WHERE relationship_id IN ({placeholders}) ORDER BY relationship_id, endpoint_role, expression_text, key_expression_id",
                    ids,
                ))
                polymorphic = self._rows(con.execute(
                    f"SELECT * FROM model_relationship_polymorphic_target WHERE relationship_id IN ({placeholders}) ORDER BY relationship_id, target_type_fqcn, polymorphic_target_id",
                    ids,
                ))
                key_lineages = self._rows(con.execute(
                    f"SELECT * FROM v_model_relationship_storage_key_derivation WHERE relationship_id IN ({placeholders}) ORDER BY relationship_id, lineage_repo_id, source_observation_occurrence_id, key_lineage_id",
                    ids,
                ))
                reference_value_key_correspondences = self._rows(con.execute(
                    f"SELECT * FROM v_model_relationship_reference_value_key_correspondence WHERE relationship_id IN ({placeholders}) ORDER BY relationship_id, source_repo_id, reference_value_observation_occurrence_id, target_key_observation_occurrence_id, correspondence_id",
                    ids,
                ))
                storage_references = self._rows(con.execute(
                    f"SELECT * FROM v_model_relationship_storage_references WHERE relationship_id IN ({placeholders}) ORDER BY relationship_id, source_repo_id, source_observation_occurrence_id, storage_reference_id",
                    ids,
                ))
                logical_identity_members = self._rows(con.execute(
                    f"SELECT * FROM v_model_relationship_logical_identity_members WHERE relationship_id IN ({placeholders}) ORDER BY relationship_id, position, key_member_id",
                    ids,
                ))
        expressions_by_id: dict[str, list[dict[str, Any]]] = {}
        for row in expressions:
            expressions_by_id.setdefault(str(row["relationship_id"]), []).append(row)
        polymorphic_by_id: dict[str, list[dict[str, Any]]] = {}
        for row in polymorphic:
            polymorphic_by_id.setdefault(str(row["relationship_id"]), []).append(row)
        key_lineages_by_id: dict[str, list[dict[str, Any]]] = {}
        for row in key_lineages:
            key_lineages_by_id.setdefault(str(row["relationship_id"]), []).append(row)
        reference_value_key_correspondences_by_id: dict[str, list[dict[str, Any]]] = {}
        for row in reference_value_key_correspondences:
            reference_value_key_correspondences_by_id.setdefault(str(row["relationship_id"]), []).append(row)
        storage_references_by_id: dict[str, list[dict[str, Any]]] = {}
        for row in storage_references:
            storage_references_by_id.setdefault(str(row["relationship_id"]), []).append(row)
        logical_identity_members_by_id: dict[str, list[dict[str, Any]]] = {}
        for row in logical_identity_members:
            logical_identity_members_by_id.setdefault(str(row["relationship_id"]), []).append(row)
        for row in relationships:
            rid = str(row["relationship_id"])
            members = logical_identity_members_by_id.get(rid, [])
            identity_fields = [str(item.get("field_name") or "") for item in members if item.get("logical_member_kind") == "identity"]
            version_fields = [str(item.get("field_name") or "") for item in members if item.get("logical_member_kind") == "version"]
            collocation_fields = [str(item.get("field_name") or "") for item in members if item.get("logical_member_kind") == "collocation"]
            row["key_expressions"] = expressions_by_id.get(rid, [])
            row["polymorphic_targets"] = polymorphic_by_id.get(rid, [])
            row["key_lineages"] = key_lineages_by_id.get(rid, [])
            row["reference_value_key_correspondences"] = reference_value_key_correspondences_by_id.get(rid, [])
            row["storage_references"] = storage_references_by_id.get(rid, [])
            row["target_logical_identity"] = {
                "identity_fields": identity_fields,
                "version_fields": version_fields,
                "collocation_fields": collocation_fields,
                "members": members,
                "classification_basis": "observed_key_member_role",
            }
        return {"kind": "workspace-data-model-relationships", "total_count": len(relationships), "items": relationships}


    def model_relationship_candidates(self, source_object_id: str = "", candidate_kind: str | None = None) -> dict[str, Any]:
        clauses = ["1=1"]
        args: list[Any] = []
        if source_object_id:
            clauses.append("source_object_fqcn=?")
            args.append(source_object_id)
        if candidate_kind:
            clauses.append("candidate_kind=?")
            args.append(candidate_kind)
        with self._connect() as con:
            items = self._rows(con.execute(
                f"SELECT * FROM model_relationship_candidate WHERE {' AND '.join(clauses)} ORDER BY source_object_fqcn, source_field_name, candidate_kind, candidate_id",
                args,
            ))
        return {"kind": "workspace-data-model-relationship-candidates", "total_count": len(items), "items": items}

    def artifact_dependency_correspondences(self, token: str = "", repo_id: str | None = None, max_results: int = 100, page_token: str = "") -> dict[str, Any]:
        clauses = ["1=1"]
        args: list[Any] = []
        if token:
            clauses.append("normalized_coordinate LIKE ?")
            args.append(f"%{token.lower()}%")
        if repo_id:
            clauses.append("(left_repo_id=? OR right_repo_id=?)")
            args.extend([repo_id, repo_id])
        where = " AND ".join(clauses)
        filters = {"token": token, "repo_id": repo_id}
        return self._paged_select(
            kind="workspace-data-model-artifact-dependency-correspondences",
            query_id="artifact_dependency_correspondences",
            select_sql=f"SELECT * FROM artifact_dependency_correspondence_observation WHERE {where} ORDER BY normalized_coordinate, left_repo_id, right_repo_id, observation_id",
            count_sql=f"SELECT count(*) FROM artifact_dependency_correspondence_observation WHERE {where}",
            args=args,
            filters=filters,
            max_results=max_results,
            page_token=page_token,
        )

    def type_neighborhood(self, type_id: str, max_results: int = 50) -> dict[str, Any]:
        limit = min(self._normalize_page_size(max_results), 200)
        with self._connect() as con:
            definitions = self._rows(con.execute(
                """SELECT * FROM java_type_declaration
                   WHERE java_type_occurrence_id=? OR fqcn=? OR simple_name=?
                   ORDER BY repo_id, fqcn, occurrence_ordinal""",
                [type_id, type_id, type_id],
            ))
            if not definitions:
                return {"kind": "workspace-data-model-type-neighborhood", "type_id": type_id, "not_found": True}
            fqcns = sorted({str(row["fqcn"]) for row in definitions if row.get("fqcn")})
            definition_repo_ids = sorted({str(row["repo_id"]) for row in definitions})
            placeholders = ",".join("?" for _ in fqcns)

            related_owner_rows = self._rows(con.execute(
                f"""SELECT DISTINCT repo_id, owner_fqcn
                     FROM source_observation
                     WHERE fact_type='type_reference_observation'
                       AND resolved_fqcn IN ({placeholders})
                       AND owner_fqcn IS NOT NULL
                     UNION
                     SELECT DISTINCT c.source_repo_id AS repo_id, c.owner_fqcn
                     FROM type_reference_resolution_candidate c
                     JOIN java_type_declaration t
                       ON t.java_type_occurrence_id=c.target_java_type_occurrence_id
                     WHERE t.fqcn IN ({placeholders}) AND c.owner_fqcn IS NOT NULL
                     ORDER BY repo_id, owner_fqcn""",
                [*fqcns, *fqcns],
            ))
            related_owner_fqcns = sorted({
                str(row["owner_fqcn"]) for row in related_owner_rows if row.get("owner_fqcn")
            })
            repo_ids = sorted({
                *definition_repo_ids,
                *(str(row["repo_id"]) for row in related_owner_rows if row.get("repo_id")),
            })
            repo_placeholders = ",".join("?" for _ in repo_ids)

            def section(select_sql: str, count_sql: str, args: list[Any]) -> dict[str, Any]:
                total = int(con.execute(count_sql, args).fetchone()[0])
                items = self._rows(con.execute(select_sql + " LIMIT ?", [*args, limit]))
                return {"items": items, "total_count": total, "returned_count": len(items), "truncated": len(items) < total}

            code_fields = section(
                f"""WITH RECURSIVE ancestry(root_repo_id, root_fqcn, owner_fqcn, inheritance_depth, inheritance_path) AS (
                        SELECT repo_id, fqcn, fqcn, 0, fqcn
                        FROM java_type_declaration
                        WHERE fqcn IN ({placeholders})
                        UNION ALL
                        SELECT a.root_repo_id, a.root_fqcn, i.resolved_parent_fqcn,
                               a.inheritance_depth + 1,
                               a.inheritance_path || ' -> ' || i.resolved_parent_fqcn
                        FROM ancestry a
                        JOIN java_inheritance_observation i
                          ON i.repo_id=a.root_repo_id AND i.child_fqcn=a.owner_fqcn
                        WHERE i.resolved_parent_fqcn IS NOT NULL
                          AND a.inheritance_depth < 100
                          AND position(i.resolved_parent_fqcn IN a.inheritance_path)=0
                    )
                    SELECT f.*, a.root_fqcn AS effective_owner_fqcn,
                           a.inheritance_depth,
                           a.inheritance_depth > 0 AS inherited,
                           a.inheritance_path
                    FROM ancestry a
                    JOIN v_code_field_observation f
                      ON f.repo_id=a.root_repo_id AND f.owner_fqcn=a.owner_fqcn
                    ORDER BY a.root_fqcn, a.inheritance_depth, f.occurrence_ordinal, f.field_name, f.code_field_occurrence_id""",
                f"""WITH RECURSIVE ancestry(root_repo_id, root_fqcn, owner_fqcn, inheritance_depth, inheritance_path) AS (
                        SELECT repo_id, fqcn, fqcn, 0, fqcn
                        FROM java_type_declaration
                        WHERE fqcn IN ({placeholders})
                        UNION ALL
                        SELECT a.root_repo_id, a.root_fqcn, i.resolved_parent_fqcn,
                               a.inheritance_depth + 1,
                               a.inheritance_path || ' -> ' || i.resolved_parent_fqcn
                        FROM ancestry a
                        JOIN java_inheritance_observation i
                          ON i.repo_id=a.root_repo_id AND i.child_fqcn=a.owner_fqcn
                        WHERE i.resolved_parent_fqcn IS NOT NULL
                          AND a.inheritance_depth < 100
                          AND position(i.resolved_parent_fqcn IN a.inheritance_path)=0
                    )
                    SELECT count(*)
                    FROM ancestry a
                    JOIN code_field_observation f
                      ON f.repo_id=a.root_repo_id AND f.owner_fqcn=a.owner_fqcn""",
                fqcns,
            )
            fields = section(
                f"SELECT * FROM effective_entity_field WHERE effective_owner_fqcn IN ({placeholders}) ORDER BY effective_owner_fqcn, inheritance_depth, field_name, effective_field_occurrence_id",
                f"SELECT count(*) FROM effective_entity_field WHERE effective_owner_fqcn IN ({placeholders})",
                fqcns,
            )
            associations = section(
                f"SELECT * FROM effective_entity_association WHERE effective_owner_fqcn IN ({placeholders}) OR target_observed_fqcn IN ({placeholders}) ORDER BY effective_owner_fqcn, source_field, target_observed_fqcn, effective_association_occurrence_id",
                f"SELECT count(*) FROM effective_entity_association WHERE effective_owner_fqcn IN ({placeholders}) OR target_observed_fqcn IN ({placeholders})",
                [*fqcns, *fqcns],
            )
            inheritance = section(
                f"SELECT * FROM java_inheritance_observation WHERE child_fqcn IN ({placeholders}) OR resolved_parent_fqcn IN ({placeholders}) ORDER BY child_fqcn, relation_kind, declared_parent_reference, inheritance_occurrence_id",
                f"SELECT count(*) FROM java_inheritance_observation WHERE child_fqcn IN ({placeholders}) OR resolved_parent_fqcn IN ({placeholders})",
                [*fqcns, *fqcns],
            )
            source_owner_values = sorted({*fqcns, *related_owner_fqcns})
            source_owner_placeholders = ",".join("?" for _ in source_owner_values)
            source_observation_where = (
                f"owner_fqcn IN ({source_owner_placeholders}) OR resolved_fqcn IN ({placeholders})"
            )
            source_observation_args = [*source_owner_values, *fqcns]
            source_observations = section(
                f"""SELECT * FROM v_source_observation_compact
                     WHERE {source_observation_where}
                     ORDER BY fact_type, repo_id, source_path, line_start, occurrence_ordinal""",
                f"SELECT count(*) FROM v_source_observation_compact WHERE {source_observation_where}",
                source_observation_args,
            )
            source_owner_summary = self._rows(con.execute(
                f"""SELECT repo_id, owner_fqcn, fact_type, count(*) AS observation_count
                     FROM v_source_observation_compact
                     WHERE {source_observation_where} AND owner_fqcn IS NOT NULL
                     GROUP BY repo_id, owner_fqcn, fact_type
                     ORDER BY repo_id, owner_fqcn, fact_type""",
                source_observation_args,
            ))
            per_fact_type_limit = min(limit, 20)
            source_observation_groups: dict[str, dict[str, Any]] = {}
            for fact_type in (
                "code_annotation",
                "configuration_entry",
                "configuration_object_observation",
                "configuration_reference_observation",
                "configuration_comment_observation",
                "external_dependency",
                "java_method_call_observation",
                "call_argument_flow_observation",
                "constructed_value_observation",
                "collection_mutation_observation",
                "type_reference_observation",
            ):
                source_observation_groups[fact_type] = section(
                    f"""SELECT * FROM v_source_observation_compact
                         WHERE ({source_observation_where}) AND fact_type=?
                         ORDER BY repo_id, owner_fqcn, source_path, line_start, occurrence_ordinal""",
                    f"SELECT count(*) FROM v_source_observation_compact WHERE ({source_observation_where}) AND fact_type=?",
                    [*source_observation_args, fact_type],
                )
                group = source_observation_groups[fact_type]
                if group["returned_count"] > per_fact_type_limit:
                    group["items"] = group["items"][:per_fact_type_limit]
                    group["returned_count"] = len(group["items"])
                    group["truncated"] = group["returned_count"] < group["total_count"]
                group["sample_limit"] = per_fact_type_limit
            resolutions = section(
                f"""SELECT c.* FROM type_reference_resolution_candidate c
                     JOIN java_type_declaration t ON t.java_type_occurrence_id=c.target_java_type_occurrence_id
                     WHERE c.owner_fqcn IN ({placeholders}) OR t.fqcn IN ({placeholders})
                     ORDER BY c.source_repo_id, c.owner_fqcn, c.candidate_fqcn, c.target_repo_id""",
                f"""SELECT count(*) FROM type_reference_resolution_candidate c
                     JOIN java_type_declaration t ON t.java_type_occurrence_id=c.target_java_type_occurrence_id
                     WHERE c.owner_fqcn IN ({placeholders}) OR t.fqcn IN ({placeholders})""",
                [*fqcns, *fqcns],
            )
            dependency_rows = section(
                f"SELECT * FROM v_source_observation_compact WHERE fact_type='external_dependency' AND repo_id IN ({repo_placeholders}) ORDER BY repo_id, coordinate, source_observation_occurrence_id",
                f"SELECT count(*) FROM v_source_observation_compact WHERE fact_type='external_dependency' AND repo_id IN ({repo_placeholders})",
                repo_ids,
            )
            configuration_tokens = sorted({fqcn.lower() for fqcn in fqcns if fqcn})
            configuration_text = """lower(
                coalesce(name,'') || ' ' || coalesce(configuration_path,'') || ' ' ||
                coalesce(parent_path,'') || ' ' || coalesce(node_kind,'') || ' ' ||
                coalesce(member_name,'') || ' ' || coalesce(referenced_type,'') || ' ' ||
                coalesce(owner_fqcn,'') || ' ' || coalesce(scalar_value_json::VARCHAR,'') || ' ' ||
                coalesce(source_path,'') || ' ' || coalesce(json_extract(payload_json, '$.properties')::VARCHAR,'')
            )"""
            configuration_predicate = " OR ".join(f"{configuration_text} LIKE ?" for _ in configuration_tokens)
            configuration_type_placeholders = ",".join("?" for _ in CONFIGURATION_FACT_TYPES)
            configuration_args = [*CONFIGURATION_FACT_TYPES, *[f"%{token}%" for token in configuration_tokens]]
            configuration_cte = f"""
                WITH config AS (
                    SELECT * FROM source_observation
                    WHERE fact_type IN ({configuration_type_placeholders})
                ),
                direct AS (
                    SELECT * FROM config WHERE {configuration_predicate}
                ),
                context_paths AS (
                    SELECT DISTINCT repo_id, source_path,
                        CASE
                            WHEN fact_type='configuration_object_observation'
                                THEN configuration_path
                            WHEN fact_type='configuration_reference_observation'
                                THEN coalesce(parent_path, configuration_path)
                            WHEN fact_type='configuration_comment_observation'
                                THEN coalesce(parent_path, configuration_path)
                            ELSE configuration_path
                        END AS context_path
                    FROM direct
                ),
                matched_ids AS (
                    SELECT source_observation_occurrence_id FROM direct
                    UNION
                    SELECT c.source_observation_occurrence_id
                    FROM config c
                    JOIN context_paths p
                      ON c.repo_id=p.repo_id
                     AND coalesce(c.source_path,'')=coalesce(p.source_path,'')
                     AND p.context_path IS NOT NULL
                     AND (
                            c.configuration_path=p.context_path
                         OR c.parent_path=p.context_path
                         OR (
                                c.fact_type='configuration_comment_observation'
                            AND c.parent_path LIKE p.context_path || '.%'
                         )
                     )
                )
            """
            configuration = section(
                configuration_cte + """
                    SELECT c.* FROM config c
                    JOIN matched_ids m USING(source_observation_occurrence_id)
                    ORDER BY c.repo_id, c.fact_type, c.source_path, c.configuration_path,
                             c.line_start, c.occurrence_ordinal
                """,
                configuration_cte + "SELECT count(*) FROM matched_ids",
                configuration_args,
            )
            repo_ids = sorted({
                *repo_ids,
                *(str(row["repo_id"]) for row in configuration["items"] if row.get("repo_id")),
            })
            owner_ids = [row["java_type_occurrence_id"] for row in definitions]
            owner_ids.extend(row["source_observation_occurrence_id"] for row in source_observations["items"])
            for group in source_observation_groups.values():
                owner_ids.extend(row["source_observation_occurrence_id"] for row in group["items"])
            owner_ids.extend(row["source_observation_occurrence_id"] for row in configuration["items"])
            owner_ids = list(dict.fromkeys(owner_ids))
            evidence: list[dict[str, Any]] = []
            if owner_ids:
                evidence_placeholders = ",".join("?" for _ in owner_ids)
                evidence = self._rows(con.execute(
                    f"SELECT * FROM evidence_ref WHERE owner_occurrence_id IN ({evidence_placeholders}) ORDER BY owner_occurrence_id, file_path, line_start LIMIT ?",
                    [*owner_ids, limit],
                ))
        return {
            "kind": "workspace-data-model-type-neighborhood",
            "type_id": type_id,
            "resolved_fqcns": fqcns,
            "repositories": repo_ids,
            "definition_repositories": definition_repo_ids,
            "related_source_owners": related_owner_rows,
            "definitions": definitions,
            "code_fields": code_fields,
            "effective_fields": fields,
            "effective_associations": associations,
            "inheritance": inheritance,
            "source_observations": source_observations,
            "source_observation_groups": source_observation_groups,
            "source_owner_fact_counts": source_owner_summary,
            "type_reference_resolution_candidates": resolutions,
            "repository_artifact_dependencies": dependency_rows,
            "configuration_mentions": configuration,
            "configuration_fact_types": list(CONFIGURATION_FACT_TYPES),
            "evidence": evidence,
            "interpretation_policy": "facts_only_no_replica_object_key_relationship_or_join_classification",
        }


























    def correspondence_observations(self, token: str = "", observation_kind: str | None = None, max_results: int = 100, page_token: str = "") -> dict[str, Any]:
        clauses = ["1=1"]
        args: list[Any] = []
        if token:
            clauses.append("normalized_value LIKE ?")
            args.append(f"%{token.lower()}%")
        if observation_kind:
            clauses.append("observation_kind=?")
            args.append(observation_kind)
        where = " AND ".join(clauses)
        filters = {"token": token, "observation_kind": observation_kind}
        observations_sql = """
            WITH observations AS (
                SELECT observation_id,
                       'cross_repository' AS observation_scope,
                       observation_kind,
                       normalized_value,
                       left_repo_id,
                       NULL::VARCHAR AS left_object_kind,
                       left_occurrence_id,
                       right_repo_id,
                       NULL::VARCHAR AS right_object_kind,
                       right_occurrence_id,
                       basis_json
                FROM data_model_correspondence_observation
                UNION ALL
                SELECT observation_id,
                       'repository_local' AS observation_scope,
                       observation_kind,
                       normalized_value,
                       repo_id AS left_repo_id,
                       left_object_kind,
                       left_occurrence_id,
                       repo_id AS right_repo_id,
                       right_object_kind,
                       right_occurrence_id,
                       basis_json
                FROM data_model_local_correspondence_observation
            )
        """
        return self._paged_select(
            kind="workspace-data-model-correspondence-observations",
            query_id="correspondence_observations",
            select_sql=f"""{observations_sql}
                SELECT * FROM observations
                WHERE {where}
                ORDER BY observation_scope, observation_kind, normalized_value, observation_id
            """,
            count_sql=f"""{observations_sql}
                SELECT count(*) FROM observations WHERE {where}
            """,
            args=args,
            filters=filters,
            max_results=max_results,
            page_token=page_token,
        )



