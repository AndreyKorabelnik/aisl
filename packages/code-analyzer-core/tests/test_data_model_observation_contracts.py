from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from code_analyzer_core.data_model_observations import (
    TABLE_KEY_OBSERVATION_SCHEMA_VERSION,
    TABLE_RELATIONSHIP_OBSERVATION_SCHEMA_VERSION,
    TableKeyObservation,
    TableRelationshipObservation,
    key_observation_json_schema,
    relationship_observation_json_schema,
)


def _evidence() -> list[dict[str, object]]:
    return [{"file": "src/main/resources/db/query.sql", "line_start": 4, "line_end": 6, "kind": "sql_join_predicate"}]


def test_sql_join_relationship_contract_preserves_observed_column_pairs():
    item = TableRelationshipObservation.model_validate({
        "schema_version": TABLE_RELATIONSHIP_OBSERVATION_SCHEMA_VERSION,
        "observation_id": "rel_repo_001",
        "repo_id": "repo",
        "relation_kind": "sql_join_predicate",
        "left_table": {"schema_name": "public", "table_name": "orders"},
        "right_table": {"schema_name": "public", "table_name": "customers"},
        "column_pairs": [{
            "left": {"column_name": "customer_id"},
            "operator": "=",
            "right": {"column_name": "id"},
            "predicate_ordinal": 0,
        }],
        "source_kind": "sql",
        "statement_id": "sql_001",
        "join_type": "left",
        "evidence_refs": _evidence(),
    })
    assert item.relation_kind.value == "sql_join_predicate"
    assert item.column_pairs[0].left.column_name == "customer_id"
    assert item.column_pairs[0].right.column_name == "id"


def test_join_contract_requires_column_pair_and_rejects_analytical_verdicts():
    with pytest.raises(ValidationError):
        TableRelationshipObservation.model_validate({
            "observation_id": "rel_repo_002",
            "repo_id": "repo",
            "relation_kind": "sql_join_predicate",
            "left_table": {"table_name": "a"},
            "right_table": {"table_name": "b"},
            "source_kind": "sql",
            "properties": {"confidence": 0.95},
            "evidence_refs": _evidence(),
        })


def test_declared_primary_key_and_candidate_key_are_distinct_contract_kinds():
    declared = TableKeyObservation.model_validate({
        "schema_version": TABLE_KEY_OBSERVATION_SCHEMA_VERSION,
        "observation_id": "key_repo_pk_orders",
        "repo_id": "repo",
        "key_kind": "declared_primary_key",
        "table": {"table_name": "orders"},
        "columns": [{"column_name": "order_id"}],
        "constraint_name": "pk_orders",
        "source_kind": "ddl",
        "evidence_refs": _evidence(),
    })
    candidate = TableKeyObservation.model_validate({
        "observation_id": "key_repo_merge_orders",
        "repo_id": "repo",
        "key_kind": "merge_match_key",
        "table": {"table_name": "orders"},
        "columns": [{"column_name": "external_id"}],
        "source_kind": "sql",
        "observation_basis": ["merge_match_predicate"],
        "evidence_refs": _evidence(),
    })
    assert declared.key_kind.value == "declared_primary_key"
    assert candidate.key_kind.value == "merge_match_key"


def test_candidate_key_requires_observation_basis_and_rejects_primary_key_verdict():
    with pytest.raises(ValidationError):
        TableKeyObservation.model_validate({
            "observation_id": "key_repo_candidate",
            "repo_id": "repo",
            "key_kind": "key_candidate_observation",
            "table": {"table_name": "orders"},
            "columns": [{"column_name": "id"}],
            "source_kind": "sql",
            "properties": {"is_primary_key": True},
            "evidence_refs": _evidence(),
        })


def test_published_json_schemas_match_runtime_models():
    base = Path(__file__).resolve().parents[1] / "code_analyzer_core" / "resources"
    relationship_schema = json.loads((base / "table_relationship_observation_v1.schema.json").read_text(encoding="utf-8"))
    key_schema = json.loads((base / "table_key_observation_v1.schema.json").read_text(encoding="utf-8"))
    assert relationship_schema == relationship_observation_json_schema()
    assert key_schema == key_observation_json_schema()
