from __future__ import annotations

from prepared_knowledge_runtime import KnowledgeLayerQuery
from prepared_knowledge_runtime.workspace_query import WorkspaceKnowledgeQuery


def test_workspace_query_is_an_extension_of_scope_neutral_query() -> None:
    assert issubclass(WorkspaceKnowledgeQuery, KnowledgeLayerQuery)
    assert WorkspaceKnowledgeQuery.entities is KnowledgeLayerQuery.entities
    assert WorkspaceKnowledgeQuery.db_schema_tables is KnowledgeLayerQuery.db_schema_tables
    assert WorkspaceKnowledgeQuery.table_key_observations is KnowledgeLayerQuery.table_key_observations
    assert WorkspaceKnowledgeQuery.observed_table_relationships is KnowledgeLayerQuery.observed_table_relationships
    assert WorkspaceKnowledgeQuery.source_observations is KnowledgeLayerQuery.source_observations


def test_workspace_specific_queries_are_owned_by_prepared_knowledge_runtime() -> None:
    assert WorkspaceKnowledgeQuery.tsa_observations.__module__ == "prepared_knowledge_runtime.workspace_query"
    assert WorkspaceKnowledgeQuery.type_reference_resolutions.__module__ == "prepared_knowledge_runtime.workspace_query"
    assert WorkspaceKnowledgeQuery.correspondence_observations.__module__ == "prepared_knowledge_runtime.workspace_query"
    assert WorkspaceKnowledgeQuery.model_relationships.__module__ == "prepared_knowledge_runtime.workspace_query"


def test_read_runtime_modules_are_not_duplicated_in_klc() -> None:
    from pathlib import Path
    import knowledge_layer_core

    root = Path(knowledge_layer_core.__file__).resolve().parent
    for name in (
        "query.py", "workspace_query.py", "reporting_queries.py", "data_model_queries.py",
        "reference_data_queries.py", "foreign_data_queries.py", "consumer_contracts.py",
        "database.py", "contracts.py", "normalization.py", "io.py",
    ):
        assert not (root / name).exists(), name
