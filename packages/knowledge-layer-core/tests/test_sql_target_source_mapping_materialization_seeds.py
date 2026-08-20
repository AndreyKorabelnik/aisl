from types import SimpleNamespace

from knowledge_layer_core.sql_target_source_mapping_builder import _observed_materialization_projection_seeds


def _traversal():
    return SimpleNamespace(
        root_scopes_by_query={"q1": ("s1",)},
        projections_by_scope={"s1": ("p1", "p2", "pw")},
        projections={
            "p1": {"id": "p1", "output": "code", "expression": "cast(code as bigint)", "wildcard": False},
            "p2": {"id": "p2", "output": "name", "expression": "cast(name as string)", "wildcard": False},
            "pw": {"id": "pw", "output": "*", "expression": "*", "wildcard": True},
        },
    )


def test_exact_observed_query_materialization_seeds_explicit_root_projections() -> None:
    observations = SimpleNamespace(materializations=(
        {
            "id": "m1", "workflow": "wf.yaml", "kind": "script_call", "query_id": "q1",
            "table": "dictionary_contactstatus", "resolution_status": "matched",
            "mapping_basis": "structured_script_call_plus_observed_literal_loop_candidate_correlation",
        },
    ))
    seeds = _observed_materialization_projection_seeds(observations, _traversal())
    assert [(row["target"], row["target_col"], row["root_projection_id"]) for row in seeds] == [
        ("dictionary_contactstatus", "code", "p1"),
        ("dictionary_contactstatus", "name", "p2"),
    ]


def test_unresolved_or_non_query_materialization_is_not_a_target_seed() -> None:
    observations = SimpleNamespace(materializations=(
        {"id": "m1", "workflow": "wf.yaml", "kind": "script_call", "query_id": "q1", "table": "t1", "resolution_status": "ambiguous"},
        {"id": "m2", "workflow": "wf.yaml", "kind": "workflow_copy", "query_id": "q1", "table": "t2", "resolution_status": "matched"},
        {"id": "m3", "workflow": "wf.yaml", "kind": "script_call", "query_id": "", "table": "t3", "resolution_status": "matched"},
    ))
    assert _observed_materialization_projection_seeds(observations, _traversal()) == []


def test_existing_workflow_target_projection_seed_is_not_duplicated() -> None:
    observations = SimpleNamespace(materializations=(
        {"id": "m1", "workflow": "wf.yaml", "kind": "script_call", "query_id": "q1", "table": "dictionary_contactstatus", "resolution_status": "matched", "mapping_basis": "structured_script_call_plus_observed_literal_loop_candidate_correlation"},
    ))
    seeds = _observed_materialization_projection_seeds(
        observations,
        _traversal(),
        {("wf.yaml", "dictionary_contactstatus", "code", "p1")},
    )
    assert [(row["target_col"], row["root_projection_id"]) for row in seeds] == [("name", "p2")]


def test_ordinary_script_or_sql_write_output_remains_producer_edge_not_target_seed() -> None:
    observations = SimpleNamespace(materializations=(
        {"id": "m1", "workflow": "wf.yaml", "kind": "script_call", "query_id": "q1", "table": "stg_x", "resolution_status": "matched", "mapping_basis": "structured_script_call_plus_local_and_workflow_binding_resolution"},
        {"id": "m2", "workflow": "wf.yaml", "kind": "sql_write", "query_id": "q1", "table": "pre_x", "resolution_status": "matched", "mapping_basis": "observed_sql_write_target_with_resolved_target_and_source_scope"},
    ))
    assert _observed_materialization_projection_seeds(observations, _traversal()) == []
