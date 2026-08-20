from __future__ import annotations

from knowledge_layer_core import data_model_materialization as materialization


def test_physical_persistence_and_source_builders_are_owned_by_core() -> None:
    names = (
        "_load_physical_assets",
        "_load_physical_asset_facts",
        "_load_mappings",
        "_load_persistent_structures",
        "_load_db_schema_tables",
        "_load_db_schema_columns",
        "_load_db_schema_keys",
        "_load_db_schema_relationships",
        "_load_db_schema_constraints",
        "_load_db_schema_indexes",
        "_load_db_schema_partitioning",
        "_load_db_schema_sequences",
        "_load_db_schema_triggers",
        "_load_table_relationship_observations",
        "_load_table_key_observations",
        "_load_source_observations",
        "_build_effective_entity_fields_from_code",
        "_build_configuration_type_correspondences",
    )
    assert all(getattr(materialization, name).__module__ == materialization.__name__ for name in names)
