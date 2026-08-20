from prepared_knowledge_runtime.sql_target_resolution import _recommended_target_relation


def test_recommended_target_relation_prefers_observed_write() -> None:
    relation, status, reasons = _recommended_target_relation(
        logical_target_name="client",
        relation_candidates=["schema_b.client", "schema_a.client"],
        write_observations=[{"target_relation_name": "schema_b.client"}],
        read_observations=[{"relation_name": "schema_a.client"}],
    )
    assert relation == "schema_b.client"
    assert status == "probable_ranked"
    assert "most_observed_write_target" in reasons


def test_recommended_target_relation_keeps_deterministic_tie_break_visible() -> None:
    relation, status, reasons = _recommended_target_relation(
        logical_target_name="client",
        relation_candidates=["schema_b.client", "schema_a.client"],
        write_observations=[],
        read_observations=[],
    )
    assert relation == "schema_a.client"
    assert status == "probable_tie_break"
    assert "deterministic_lexical_tie_break" in reasons
