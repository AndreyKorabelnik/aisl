from prepared_knowledge_runtime.evidence_layout import SOURCE_OBSERVATION_FILES


def test_source_observation_layout_includes_module_resolution_evidence() -> None:
    required = {
        "cross_module_call_resolution_observation.jsonl",
        "cross_module_type_resolution_observation.jsonl",
        "module_boundary_interaction_observation.jsonl",
        "unresolved_module_reference_observation.jsonl",
        "storage_alias_assignment_observation.jsonl",
        "storage_record_observation.jsonl",
        "storage_reference_observation.jsonl",
    }
    assert required.issubset(set(SOURCE_OBSERVATION_FILES))
