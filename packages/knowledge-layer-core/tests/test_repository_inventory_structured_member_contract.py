from knowledge_layer_core.materialization_contracts import CURRENT_MATERIALIZATIONS


def test_repository_inventory_structured_shape_enrichment_is_bounded_preflight() -> None:
    definition = next(item for item in CURRENT_MATERIALIZATIONS if item.materialization_id == "repository-inventory")
    requirement = next(
        item for item in definition.optional_evidence
        if item.artifact_kind == "structured-file-shape-evidence"
    )
    assert requirement.schema_versions == ("structured-file-shape-evidence/v1",)
    assert requirement.production_policy == "produce_if_missing"
    assert "common.repository-structural-members" not in definition.capabilities
    assert definition.conditional_capabilities == ("common.repository-structural-members",)
