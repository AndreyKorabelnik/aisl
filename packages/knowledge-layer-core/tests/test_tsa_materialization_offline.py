from prepared_knowledge_runtime.workspace_query import TSA_FACT_TYPES
from knowledge_layer_core.workspace_schema import DDL
from prepared_knowledge_runtime.evidence_layout import SOURCE_OBSERVATION_FILES


def test_schema_materializes_all_tsa_fact_types_as_views():
    expected_views = {
        "v_tsa_annotations": "tsa_annotation_observation",
        "v_tsa_converter_configurations": "tsa_converter_configuration_observation",
        "v_tsa_configuration_directives": "tsa_configuration_directive_observation",
        "v_tsa_reference_operations": "tsa_reference_operation_observation",
        "v_tsa_key_expressions": "tsa_key_expression_observation",
        "v_tsa_storage_key_derivations": "tsa_storage_key_lineage_observation",
        "v_tsa_reference_value_derivations": "tsa_reference_value_derivation_observation",
    }
    for view, fact_type in expected_views.items():
        assert f"CREATE VIEW {view}" in DDL
        assert fact_type in DDL
    assert set(expected_views.values()) == set(TSA_FACT_TYPES)
    assert "tsa_observation_count" in DDL


def test_tsa_views_keep_semantics_as_observed_payload_fields():
    assert "key_expression" in DDL
    assert "argument_expressions_json" in DDL
    assert "tsa_observation_kind" in DDL
    assert "confidence" not in " ".join(line for line in DDL.splitlines() if "v_tsa_" in line)


def test_tsa_query_validates_fact_type_and_builds_bounded_query():
    from prepared_knowledge_runtime.workspace_query import WorkspaceKnowledgeQuery

    captured = {}
    query = object.__new__(WorkspaceKnowledgeQuery)
    query._paged_select = lambda **kwargs: captured.update(kwargs) or kwargs

    result = query.tsa_observations(
        token="reference",
        repo_id="repo-a",
        fact_type="tsa_reference_operation_observation",
        owner_fqcn="a.Converter",
        max_results=25,
    )
    assert result["query_id"] == "tsa_observations"
    assert result["max_results"] == 25
    assert "fact_type IN (?)" in result["select_sql"]
    assert result["args"][-2:] == ["repo-a", "a.Converter"]

    try:
        query.tsa_observations(fact_type="table_verdict")
    except ValueError as exc:
        assert "unsupported TSA fact_type" in str(exc)
    else:
        raise AssertionError("unsupported TSA fact type must be rejected")


def test_source_observation_import_includes_tsa_and_method_reference_fact_stores() -> None:
    expected = {
        "java_method_reference_observation.jsonl",
        "java_call_parameter_binding_observation.jsonl",
        "java_call_result_binding_observation.jsonl",
        "tsa_annotation_observation.jsonl",
        "tsa_converter_configuration_observation.jsonl",
        "tsa_configuration_directive_observation.jsonl",
        "tsa_reference_operation_observation.jsonl",
        "tsa_key_expression_observation.jsonl",
        "tsa_storage_key_lineage_observation.jsonl",
        "tsa_reference_value_derivation_observation.jsonl",
        "storage_alias_assignment_observation.jsonl",
        "storage_record_observation.jsonl",
        "storage_reference_observation.jsonl",
    }
    assert expected.issubset(set(SOURCE_OBSERVATION_FILES))
