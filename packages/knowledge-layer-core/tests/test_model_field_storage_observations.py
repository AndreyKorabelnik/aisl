from pathlib import Path

import duckdb

from prepared_knowledge_runtime.workspace_query import WorkspaceKnowledgeQuery


def _database(path: Path) -> None:
    con = duckdb.connect(str(path))
    try:
        con.execute(
            """
            CREATE TABLE v_model_object_fields(
                repo_id VARCHAR,
                object_fqcn VARCHAR,
                field_name VARCHAR,
                inherited BOOLEAN,
                key_position INTEGER,
                effective_field_occurrence_id VARCHAR,
                declaration_owner_fqcn VARCHAR,
                declared_type VARCHAR,
                effective_type VARCHAR,
                java_type_occurrence_id VARCHAR,
                key_observation_id VARCHAR,
                container_kind VARCHAR,
                element_type VARCHAR,
                display_name VARCHAR,
                description VARCHAR,
                inheritance_depth INTEGER,
                key_member_id VARCHAR,
                key_role_name VARCHAR,
                model_exclusion_observed BOOLEAN
            );
            INSERT INTO v_model_object_fields VALUES
              ('model', 'example.Country', 'nameInEnglish', false, NULL, 'field-1',
               'example.Country', 'String', 'String', 'type-1', 'key-1', NULL, NULL,
               NULL, NULL, 0, NULL, NULL, false),
              ('model', 'example.Country', 'notPersisted', false, NULL, 'field-2',
               'example.Country', 'String', 'String', 'type-1', 'key-1', NULL, NULL,
               NULL, NULL, 0, NULL, NULL, false);

            CREATE TABLE source_observation(
                repo_id VARCHAR,
                fact_type VARCHAR,
                target_method VARCHAR,
                argument_index INTEGER,
                source_expression VARCHAR,
                owner_fqcn VARCHAR,
                owner_method VARCHAR,
                call_observation_local_id VARCHAR,
                source_observation_occurrence_id VARCHAR,
                source_path VARCHAR,
                line_start INTEGER,
                line_end INTEGER,
                extractor VARCHAR
            );
            """
        )
        con.executemany(
            "INSERT INTO source_observation VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    "converter", "call_argument_flow_observation", "alias", 0,
                    '"example.Country"', "example.CountryConverter", "convert", "alias-call",
                    "alias-observation", "src/CountryConverter.java", 10, 10, "java_tree_sitter",
                ),
                (
                    "converter", "call_argument_flow_observation", "primitiveField", 0,
                    '"nameInEnglish"', "example.CountryConverter", "convert", "primitive-call",
                    "field-name-observation", "src/CountryConverter.java", 12, 12, "java_tree_sitter",
                ),
                (
                    "converter", "call_argument_flow_observation", "primitiveField", 1,
                    "country.getNameInEnglish()", "example.CountryConverter", "convert", "primitive-call",
                    "value-observation", "src/CountryConverter.java", 12, 12, "java_tree_sitter",
                ),
                # Same physical field name but a different exact alias must not attach.
                (
                    "converter", "call_argument_flow_observation", "alias", 0,
                    '"example.Other"', "example.OtherConverter", "convert", "other-alias-call",
                    "other-alias", "src/OtherConverter.java", 20, 20, "java_tree_sitter",
                ),
                (
                    "converter", "call_argument_flow_observation", "primitiveField", 0,
                    '"nameInEnglish"', "example.OtherConverter", "convert", "other-primitive-call",
                    "other-field", "src/OtherConverter.java", 22, 22, "java_tree_sitter",
                ),
            ],
        )
        con.execute("CHECKPOINT")
    finally:
        con.close()


def test_model_object_fields_attach_exact_alias_and_primitive_field_evidence(tmp_path: Path) -> None:
    database = tmp_path / "field-storage.duckdb"
    _database(database)

    result = WorkspaceKnowledgeQuery(database).model_object_fields(object_id="example.Country")
    fields = {item["field_name"]: item for item in result["items"]}

    observed = fields["nameInEnglish"]
    assert observed["storage_observation_count"] == 1
    assert observed["storage_observations_truncated"] is False
    storage = observed["storage_observations"][0]
    assert storage["physical_field_name"] == "nameInEnglish"
    assert storage["object_alias"] == "example.Country"
    assert storage["value_expression"] == "country.getNameInEnglish()"
    assert storage["match_basis"] == "exact_converter_alias_and_exact_model_field_name"
    assert storage["value_mapping_status"] == "observed_expression_not_semantically_interpreted"
    assert [item["role"] for item in storage["evidence"]] == [
        "object_alias", "physical_field_name", "value_expression"
    ]
    assert {item["repo_id"] for item in storage["evidence"]} == {"converter"}

    assert fields["notPersisted"]["storage_observation_count"] == 0
    assert fields["notPersisted"]["storage_observations"] == []
