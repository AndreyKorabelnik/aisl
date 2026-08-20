from knowledge_layer_core.cross_artifact_data_model_builder import _workflow_identity_tokens


def test_workflow_identity_tokens_normalize_only_stage_suffix() -> None:
    assert _workflow_identity_tokens("935120654.2 and 935120655.2") == ["935120654", "935120655"]
    assert _workflow_identity_tokens("customer-load and upstream.task") == ["customer-load", "upstream.task"]


def test_workflow_identity_tokens_keep_concrete_identity_next_to_placeholder() -> None:
    assert _workflow_identity_tokens("${inventory.__EPK_RB_TRIGGER__} and 935120697.2") == ["935120697"]
