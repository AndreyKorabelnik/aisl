from __future__ import annotations

import duckdb
import pytest

from knowledge_layer_core.interaction_contracts import materialize_system_interaction_field_contracts
from knowledge_layer_core.interaction_field_contract_knowledge_schema import INTERACTION_FIELD_CONTRACT_DDL
from knowledge_layer_core.interaction_graph import materialize_system_interactions
from knowledge_layer_core.interaction_knowledge_schema import INTERACTION_KNOWLEDGE_DDL
from knowledge_layer_core.value_flow import materialize_repository_value_flow
from knowledge_layer_core.value_flow_knowledge_schema import VALUE_FLOW_KNOWLEDGE_DDL


def _old_generic_analysis_record(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(
        """CREATE TABLE analysis_record (
               record_occurrence_id VARCHAR, repo_id VARCHAR, artifact_name VARCHAR,
               local_record_id VARCHAR, occurrence_ordinal BIGINT, payload_json JSON
           )"""
    )


def test_repository_value_flow_rejects_generic_only_analysis_record() -> None:
    con = duckdb.connect(":memory:")
    con.execute(VALUE_FLOW_KNOWLEDGE_DDL)
    con.execute("DROP TABLE value_flow_evidence_record")
    _old_generic_analysis_record(con)
    with pytest.raises(duckdb.CatalogException, match="value_flow_evidence_record"):
        materialize_repository_value_flow(con, scope_id="scope")


def test_system_interactions_rejects_generic_only_analysis_record() -> None:
    con = duckdb.connect(":memory:")
    con.execute(INTERACTION_KNOWLEDGE_DDL)
    con.execute("DROP TABLE interaction_boundary_evidence_record")
    _old_generic_analysis_record(con)
    with pytest.raises(duckdb.CatalogException, match="interaction_boundary_evidence_record"):
        materialize_system_interactions(con, scope_id="scope")


def test_interaction_field_contracts_reject_generic_only_analysis_record() -> None:
    con = duckdb.connect(":memory:")
    con.execute(INTERACTION_FIELD_CONTRACT_DDL)
    con.execute(INTERACTION_KNOWLEDGE_DDL)
    _old_generic_analysis_record(con)
    with pytest.raises(duckdb.CatalogException, match="value_flow_evidence_record"):
        materialize_system_interaction_field_contracts(con, scope_id="scope")
