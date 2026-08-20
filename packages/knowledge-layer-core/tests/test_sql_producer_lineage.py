from __future__ import annotations

from knowledge_layer_core.sql_producer_lineage import ObservedMaterializationIndex, SqlProducerColumnTraversal


def _index(*, materializations, dependencies=()):
    return ObservedMaterializationIndex(
        materializations=materializations,
        workflow_dependencies=dependencies,
        root_scopes_by_query={"q-stage": ["scope-stage"]},
        scope_output_contracts={"scope-stage": {"output_contract_status": "complete", "output_columns": ["name"]}},
    )


def test_materialization_index_prefers_same_workflow_then_nearest_upstream() -> None:
    materials = [
        {"id": "m-local", "workflow": "consumer", "kind": "script_call", "query_id": "q-stage", "table": "stage"},
        {"id": "m-near", "workflow": "producer-near", "kind": "script_call", "query_id": "q-stage", "table": "other"},
        {"id": "m-far", "workflow": "producer-far", "kind": "script_call", "query_id": "q-stage", "table": "other"},
    ]
    index = _index(
        materializations=materials,
        dependencies=(
            ("producer-near", "consumer", "dep-near"),
            ("producer-far", "producer-near", "dep-far"),
        ),
    )
    assert [(item[0]["id"], item[1]) for item in index.producers("consumer", "stage")] == [("m-local", ())]
    assert [(item[0]["id"], item[1]) for item in index.producers("consumer", "other")] == [("m-near", ("dep-near",))]


def test_column_traversal_continues_through_observed_physical_producer() -> None:
    usages = {
        "u-final": {"id": "u-final", "relation_id": "r-stage", "column": "name", "file": "final.sql", "usage_role": "projection"},
        "u-source": {"id": "u-source", "relation_id": "r-source", "column": "surname", "file": "stage.sql", "usage_role": "projection"},
    }
    relations = {
        "r-stage": {"id": "r-stage", "kind": "physical", "logical": "stage", "name": "dm.stage", "source_scopes": [], "file": "final.sql"},
        "r-source": {"id": "r-source", "kind": "physical", "logical": "individual_name", "name": "src.individual_name", "source_scopes": [], "file": "stage.sql"},
    }
    projections = {
        "p-stage": {"id": "p-stage", "scope_id": "scope-stage", "output": "name", "wildcard": False, "source_usages": ["u-source"], "expression": "surname as name"},
    }
    index = _index(materializations=[
        {"id": "m-stage", "workflow": "wf", "kind": "script_call", "query_id": "q-stage", "table": "stage"},
    ])
    traversal = SqlProducerColumnTraversal(
        usages=usages,
        relations=relations,
        relations_by_scope={},
        projections=projections,
        projections_by_scope={"scope-stage": ["p-stage"]},
        root_scopes_by_query={"q-stage": ["scope-stage"]},
        materializations=index,
    )

    origins = traversal.usage_origins("wf", "u-final")
    assert len(origins) == 1
    assert origins[0]["usage_id"] == "u-source"
    assert origins[0]["relation_id"] == "r-source"
    assert origins[0]["column"] == "surname"
    assert origins[0]["materialization_path"] == ["m-stage"]
    assert origins[0]["projection_path"] == ["projection:p-stage"]


def test_column_traversal_stops_at_physical_relation_without_observed_producer() -> None:
    usages = {"u": {"id": "u", "relation_id": "r", "column": "id", "file": "read.sql", "usage_role": "projection"}}
    relations = {"r": {"id": "r", "kind": "physical", "logical": "external", "name": "src.external", "source_scopes": [], "file": "read.sql"}}
    traversal = SqlProducerColumnTraversal(
        usages=usages,
        relations=relations,
        relations_by_scope={},
        projections={},
        projections_by_scope={},
        root_scopes_by_query={},
        materializations=_index(materializations=[]),
    )
    origins = traversal.usage_origins("wf", "u")
    assert origins == [{
        "usage_id": "u",
        "relation_id": "r",
        "column": "id",
        "source_file": "read.sql",
        "projection_path": [],
        "materialization_path": [],
        "workflow_dependency_path": [],
        "terminal_workflow_context": "wf",
        "terminal_semantic_role": None,
        "terminal_classification_status": None,
        "terminal_classification_basis": None,
        "relation_path": [{
            "relation_id": "r",
            "relation_name": "src.external",
            "relation_kind": "physical",
            "usage_role": "",
            "query_id": "",
            "scope_id": "",
            "scope_ordinal": 0,
            "file": "read.sql",
        }],
    }]


def test_column_traversal_excludes_control_usages_from_producer_projection() -> None:
    usages = {
        "u-final": {"id": "u-final", "relation_id": "r-stage", "column": "valid_to", "file": "final.sql", "usage_role": "projection"},
        "u-value": {"id": "u-value", "relation_id": "r-source", "column": "version_date", "file": "stage.sql", "usage_role": "projection"},
        "u-partition": {"id": "u-partition", "relation_id": "r-source", "column": "entity_id", "file": "stage.sql", "usage_role": "window_partition"},
        "u-order": {"id": "u-order", "relation_id": "r-source", "column": "version_date", "file": "stage.sql", "usage_role": "window_order"},
    }
    relations = {
        "r-stage": {"id": "r-stage", "kind": "physical", "logical": "stage", "name": "dm.stage", "source_scopes": [], "file": "final.sql"},
        "r-source": {"id": "r-source", "kind": "physical", "logical": "source", "name": "src.source", "source_scopes": [], "file": "stage.sql"},
    }
    projections = {
        "p-stage": {
            "id": "p-stage", "scope_id": "scope-stage", "output": "valid_to", "wildcard": False,
            "source_usages": ["u-value", "u-partition", "u-order"],
            "expression": "lead(version_date) over (partition by entity_id order by version_date)",
        },
    }
    traversal = SqlProducerColumnTraversal(
        usages=usages, relations=relations, relations_by_scope={}, projections=projections,
        projections_by_scope={"scope-stage": ["p-stage"]}, root_scopes_by_query={"q-stage": ["scope-stage"]},
        materializations=_index(materializations=[
            {"id": "m-stage", "workflow": "wf", "kind": "script_call", "query_id": "q-stage", "table": "stage"},
        ]),
    )
    origins = traversal.usage_origins("wf", "u-final")
    assert [(origin["usage_id"], origin["column"]) for origin in origins] == [("u-value", "version_date")]


def test_script_materialization_traverses_compatible_union_root_branches() -> None:
    usages = {
        "u-final": {"id": "u-final", "relation_id": "r-stage", "column": "epk_id", "file": "final.sql", "usage_role": "projection"},
        "u-a": {"id": "u-a", "relation_id": "r-a", "column": "key", "file": "stage.sql", "usage_role": "projection"},
        "u-b": {"id": "u-b", "relation_id": "r-b", "column": "key", "file": "stage.sql", "usage_role": "projection"},
    }
    relations = {
        "r-stage": {"id": "r-stage", "kind": "physical", "logical": "stage", "name": "dm.stage", "source_scopes": [], "file": "final.sql"},
        "r-a": {"id": "r-a", "kind": "physical", "logical": "source_a", "name": "src.source_a", "source_scopes": [], "file": "stage.sql"},
        "r-b": {"id": "r-b", "kind": "physical", "logical": "source_b", "name": "src.source_b", "source_scopes": [], "file": "stage.sql"},
    }
    projections = {
        "p-a": {"id": "p-a", "scope_id": "scope-a", "output": "epk_id", "wildcard": False, "source_usages": ["u-a"], "expression": "key as epk_id"},
        "p-b": {"id": "p-b", "scope_id": "scope-b", "output": "epk_id", "wildcard": False, "source_usages": ["u-b"], "expression": "key as epk_id"},
    }
    index = ObservedMaterializationIndex(
        materializations=[{"id": "m-stage", "workflow": "wf", "kind": "script_call", "query_id": "q-union", "table": "stage"}],
        workflow_dependencies=(),
        root_scopes_by_query={"q-union": ["scope-a", "scope-b"]},
        scope_output_contracts={
            "scope-a": {"output_contract_status": "complete", "output_columns": ["epk_id"]},
            "scope-b": {"output_contract_status": "complete", "output_columns": ["epk_id"]},
        },
    )
    assert index.output_contract({"id": "m-stage", "workflow": "wf", "kind": "script_call", "query_id": "q-union", "table": "stage"}) == (
        {"epk_id"}, "script_materialization_set_branch_output_contract"
    )
    traversal = SqlProducerColumnTraversal(
        usages=usages,
        relations=relations,
        relations_by_scope={},
        projections=projections,
        projections_by_scope={"scope-a": ["p-a"], "scope-b": ["p-b"]},
        root_scopes_by_query={"q-union": ["scope-a", "scope-b"]},
        materializations=index,
    )
    origins = traversal.usage_origins("wf", "u-final")
    assert {(origin["relation_id"], origin["column"]) for origin in origins} == {("r-a", "key"), ("r-b", "key")}


def test_script_materialization_rejects_mismatched_union_root_contracts() -> None:
    index = ObservedMaterializationIndex(
        materializations=[], workflow_dependencies=(),
        root_scopes_by_query={"q-union": ["scope-a", "scope-b"]},
        scope_output_contracts={
            "scope-a": {"output_contract_status": "complete", "output_columns": ["epk_id"]},
            "scope-b": {"output_contract_status": "complete", "output_columns": ["other_id"]},
        },
    )
    contract, basis = index.output_contract({"id": "m", "kind": "script_call", "query_id": "q-union"})
    assert contract is None
    assert basis == "materialization_root_scope_output_contract_mismatch"


def test_config_transform_preserves_identity_and_applies_explicit_column_mapping() -> None:
    usages = {
        "u-name": {"id": "u-name", "relation_id": "r-output", "column": "name", "file": "final.sql", "usage_role": "projection"},
        "u-part": {"id": "u-part", "relation_id": "r-output", "column": "part_day", "file": "final.sql", "usage_role": "projection"},
        "u-src-name": {"id": "u-src-name", "relation_id": "r-source", "column": "name", "file": "stage.sql", "usage_role": "projection"},
        "u-src-end": {"id": "u-src-end", "relation_id": "r-source", "column": "end_dt", "file": "stage.sql", "usage_role": "projection"},
    }
    relations = {
        "r-output": {"id": "r-output", "kind": "physical", "logical": "target_stg", "name": "dm.target_stg", "source_scopes": [], "file": "final.sql"},
        "r-pre": {"id": "r-pre", "kind": "physical", "logical": "target_prestg", "name": "dm.target_prestg", "source_scopes": [], "file": "hist.sql"},
        "r-source": {"id": "r-source", "kind": "physical", "logical": "source", "name": "src.source", "source_scopes": [], "file": "stage.sql"},
    }
    projections = {
        "p-name": {"id": "p-name", "scope_id": "scope-pre", "output": "name", "wildcard": False, "source_usages": ["u-src-name"], "expression": "name"},
        "p-end": {"id": "p-end", "scope_id": "scope-pre", "output": "end_dt", "wildcard": False, "source_usages": ["u-src-end"], "expression": "end_dt"},
    }
    index = ObservedMaterializationIndex(
        materializations=[
            {"id": "m-pre", "workflow": "wf", "kind": "sql_write", "source_scopes": ["scope-pre"], "table": "target_prestg"},
            {"id": "m-hist", "workflow": "wf", "kind": "config_transform", "source_table": "target_prestg", "table": "target_stg", "provenance": {"identity_passthrough": True, "column_mappings": {"part_day": "end_dt"}}},
        ],
        workflow_dependencies=(),
        root_scopes_by_query={},
        scope_output_contracts={"scope-pre": {"output_contract_status": "complete", "output_columns": ["name", "end_dt"]}},
    )
    traversal = SqlProducerColumnTraversal(
        usages=usages,
        relations=relations,
        relations_by_scope={},
        projections=projections,
        projections_by_scope={"scope-pre": ["p-name", "p-end"]},
        root_scopes_by_query={},
        materializations=index,
    )
    name_origins = traversal.usage_origins("wf", "u-name")
    assert [(item["relation_id"], item["column"]) for item in name_origins] == [("r-source", "name")]
    part_origins = traversal.usage_origins("wf", "u-part")
    assert [(item["relation_id"], item["column"]) for item in part_origins] == [("r-source", "end_dt")]


def test_producer_observations_compose_structured_name_prior_value_workflow_parameter() -> None:
    import duckdb
    from knowledge_layer_core.sql_analysis_schema import SQL_ANALYSIS_DDL
    from knowledge_layer_core.sql_producer_observations import derive_sql_producer_observations

    con = duckdb.connect(":memory:")
    con.execute(SQL_ANALYSIS_DDL)
    columns = (
        "sql_workflow_binding_id,repo_id,file,line_start,line_end,config_format,binding_path,parent_path,"
        "binding_name,value_type,scalar_value,value_expression,referenced_placeholders_json,resolution_status,"
        "evidence_maturity_level,evidence_json,payload_json"
    )
    con.execute(
        f"INSERT INTO sql_workflow_binding ({columns}) VALUES "
        "('n','repo','workflow.yml',1,1,'yaml','x.name','x','name','string',"
        "'s2t.source.table.name','s2t.source.table.name','[]','literal','observed','[]','{}')"
    )
    con.execute(
        f"INSERT INTO sql_workflow_binding ({columns}) VALUES "
        "('v','repo','workflow.yml',2,2,'yaml','x.prior_value','x','prior_value','string',"
        "'stage_a','stage_a','[]','literal','observed','[]','{}')"
    )
    con.execute(
        f"INSERT INTO sql_workflow_binding ({columns}) VALUES "
        "('s','repo','workflow.yml',3,3,'json','s2tTableList',NULL,'s2tTableList','string',"
        "'${s2t.source.table.name}->final_a','${s2t.source.table.name}->final_a',"
        "'[\"s2t.source.table.name\"]','template','observed','[]','{}')"
    )
    observations = derive_sql_producer_observations(con, repo_id='repo')
    con.close()
    rows = [m for m in observations.materializations if m.get('kind') == 'workflow_copy']
    assert [(m.get('source_table'), m.get('table')) for m in rows] == [('stage_a', 'final_a')]



def test_materialization_index_uses_repository_unique_exact_producer_as_derived_fallback() -> None:
    index = _index(materializations=[
        {"id": "m-stage", "workflow": "producer-workflow", "kind": "script_call", "query_id": "q-stage", "table": "stage"},
    ])
    rows = index.producers("consumer-workflow", "stage")
    assert len(rows) == 1
    producer, dependency_path = rows[0]
    assert producer["id"] == "m-stage"
    assert dependency_path == ()
    assert producer["_producer_resolution_status"] == "strongly_supported"
    assert producer["_producer_resolution_basis"] == "repository_unique_exact_table_producer"
    assert producer["_producer_resolution_consumer_workflow"] == "consumer-workflow"
    assert producer["_producer_resolution_producer_workflow"] == "producer-workflow"


def test_materialization_index_does_not_select_ambiguous_repository_exact_producer() -> None:
    index = _index(materializations=[
        {"id": "m-a", "workflow": "wf-a", "kind": "script_call", "query_id": "q-stage", "table": "stage"},
        {"id": "m-b", "workflow": "wf-b", "kind": "script_call", "query_id": "q-stage", "table": "stage"},
    ])
    assert index.producers("consumer-workflow", "stage") == []
    assert {item["id"] for item in index.exact_table_candidates("stage")} == {"m-a", "m-b"}


def test_column_traversal_continues_via_repository_unique_exact_producer_and_keeps_basis() -> None:
    usages = {
        "u-final": {"id": "u-final", "relation_id": "r-stage", "column": "name", "file": "final.sql", "usage_role": "projection"},
        "u-source": {"id": "u-source", "relation_id": "r-source", "column": "surname", "file": "stage.sql", "usage_role": "projection"},
    }
    relations = {
        "r-stage": {"id": "r-stage", "kind": "physical", "logical": "stage", "name": "dm.stage", "source_scopes": [], "file": "final.sql"},
        "r-source": {"id": "r-source", "kind": "physical", "logical": "individual_name", "name": "src.individual_name", "source_scopes": [], "file": "stage.sql"},
    }
    projections = {
        "p-stage": {"id": "p-stage", "scope_id": "scope-stage", "output": "name", "wildcard": False, "source_usages": ["u-source"], "expression": "surname as name"},
    }
    traversal = SqlProducerColumnTraversal(
        usages=usages,
        relations=relations,
        relations_by_scope={},
        projections=projections,
        projections_by_scope={"scope-stage": ["p-stage"]},
        root_scopes_by_query={"q-stage": ["scope-stage"]},
        materializations=_index(materializations=[
            {"id": "m-stage", "workflow": "producer-workflow", "kind": "script_call", "query_id": "q-stage", "table": "stage"},
        ]),
    )
    origins = traversal.usage_origins("consumer-workflow", "u-final")
    assert len(origins) == 1
    assert origins[0]["relation_id"] == "r-source"
    assert origins[0]["column"] == "surname"
    assert origins[0]["materialization_path"] == ["m-stage"]
    assert origins[0]["producer_resolution_path"] == [{
        "status": "strongly_supported",
        "basis": "repository_unique_exact_table_producer",
        "logical_table": "stage",
        "consumer_workflow": "consumer-workflow",
        "producer_workflow": "producer-workflow",
        "producer_id": "m-stage",
    }]


def test_column_traversal_preserves_ambiguous_exact_producer_frontier() -> None:
    usages = {"u": {"id": "u", "relation_id": "r", "column": "id", "file": "read.sql", "usage_role": "projection"}}
    relations = {"r": {"id": "r", "kind": "physical", "logical": "stage", "name": "dm.stage", "source_scopes": [], "file": "read.sql"}}
    traversal = SqlProducerColumnTraversal(
        usages=usages,
        relations=relations,
        relations_by_scope={},
        projections={},
        projections_by_scope={},
        root_scopes_by_query={},
        materializations=_index(materializations=[
            {"id": "m-a", "workflow": "wf-a", "kind": "script_call", "query_id": "q-stage", "table": "stage"},
            {"id": "m-b", "workflow": "wf-b", "kind": "script_call", "query_id": "q-stage", "table": "stage"},
        ]),
    )
    origins = traversal.usage_origins("consumer", "u")
    assert len(origins) == 1
    assert origins[0]["usage_id"] == "u"
    assert origins[0]["producer_resolution_status"] == "ambiguous"
    assert origins[0]["producer_resolution_basis"] == "multiple_repository_exact_table_producers_without_observed_workflow_path"
    assert {item["producer_id"] for item in origins[0]["producer_resolution_candidates"]} == {"m-a", "m-b"}


def test_workflow_copy_uses_consistent_complete_branch_and_keeps_incomplete_diagnostic() -> None:
    complete = {
        "id": "write-complete",
        "kind": "sql_write",
        "workflow": "wf",
        "table": "target_diff",
        "source_scopes": ["scope-complete"],
        "provenance": {
            "materialized_output_contract_status": "complete",
            "materialized_output_contract_basis": "repository_materialized_relation_contract",
            "materialized_output_columns": ["ID", "Value"],
        },
    }
    incomplete = {
        "id": "write-incomplete",
        "kind": "sql_write",
        "workflow": "wf",
        "table": "target_diff",
        "source_scopes": ["scope-incomplete"],
        "provenance": {},
    }
    copy = {
        "id": "copy",
        "kind": "workflow_copy",
        "workflow": "wf",
        "source_table": "target_diff",
        "table": "target",
        "provenance": {},
    }
    index = ObservedMaterializationIndex(
        materializations=[complete, incomplete, copy],
        workflow_dependencies=[],
        root_scopes_by_query={},
        scope_output_contracts={
            "scope-incomplete": {
                "output_contract_status": "partial",
                "output_columns": ["id"],
            }
        },
    )

    contract, basis = index.output_contract(copy)

    assert contract == {"id", "value"}
    assert basis == "workflow_copy_partial_consistent_source_materialization_contract"
    diagnostics = index.output_contract_diagnostics(copy)
    assert len(diagnostics) == 1
    assert diagnostics[0]["gap_kind"] == "workflow_copy_source_branch_incomplete"
    assert diagnostics[0]["source_producer_id"] == "write-incomplete"
    assert diagnostics[0]["resolution_basis"] == "sql_write_source_contract_incomplete"


def test_workflow_copy_does_not_choose_between_conflicting_complete_branches() -> None:
    def producer(pid: str, columns: list[str]) -> dict:
        return {
            "id": pid,
            "kind": "sql_write",
            "workflow": "wf",
            "table": "target_diff",
            "source_scopes": [],
            "provenance": {
                "materialized_output_contract_status": "complete",
                "materialized_output_contract_basis": "repository_materialized_relation_contract",
                "materialized_output_columns": columns,
            },
        }

    copy = {
        "id": "copy-conflict",
        "kind": "workflow_copy",
        "workflow": "wf",
        "source_table": "target_diff",
        "table": "target",
        "provenance": {},
    }
    index = ObservedMaterializationIndex(
        materializations=[producer("a", ["id", "value"]), producer("b", ["id", "other"]), copy],
        workflow_dependencies=[],
        root_scopes_by_query={},
        scope_output_contracts={},
    )

    contract, basis = index.output_contract(copy)

    assert contract is None
    assert basis == "workflow_copy_source_contract_ambiguous"


def test_direct_s2t_template_does_not_cross_product_multi_scope_workflow_values() -> None:
    import duckdb
    from knowledge_layer_core.sql_analysis_schema import SQL_ANALYSIS_DDL
    from knowledge_layer_core.sql_producer_observations import derive_sql_producer_observations

    con = duckdb.connect(":memory:")
    con.execute(SQL_ANALYSIS_DDL)
    columns = (
        "sql_workflow_binding_id,repo_id,file,line_start,line_end,config_format,binding_path,parent_path,"
        "binding_name,value_type,scalar_value,value_expression,referenced_placeholders_json,resolution_status,"
        "evidence_maturity_level,evidence_json,payload_json"
    )
    rows = [
        ("n1", "repo", "ctl.yml", 1, 1, "yaml", "workflows[1].a.params[1].param.name", "workflows[1].a.params[1].param", "name", "string", "s2t.source.table.name", "s2t.source.table.name", "[]", "literal", "observed", "[]", "{}"),
        ("v1", "repo", "ctl.yml", 1, 1, "yaml", "workflows[1].a.params[1].param.prior_value", "workflows[1].a.params[1].param", "prior_value", "string", "stage_a", "stage_a", "[]", "literal", "observed", "[]", "{}"),
        ("n2", "repo", "ctl.yml", 2, 2, "yaml", "workflows[1].a.params[2].param.name", "workflows[1].a.params[2].param", "name", "string", "s2t.target.table.name", "s2t.target.table.name", "[]", "literal", "observed", "[]", "{}"),
        ("v2", "repo", "ctl.yml", 2, 2, "yaml", "workflows[1].a.params[2].param.prior_value", "workflows[1].a.params[2].param", "prior_value", "string", "final_a", "final_a", "[]", "literal", "observed", "[]", "{}"),
        ("c1", "repo", "ctl.yml", 3, 3, "yaml", "workflows[1].a.params[3].param.name", "workflows[1].a.params[3].param", "name", "string", "b2c.sql.pipelines.config.path", "b2c.sql.pipelines.config.path", "[]", "literal", "observed", "[]", "{}"),
        ("c2", "repo", "ctl.yml", 3, 3, "yaml", "workflows[1].a.params[3].param.prior_value", "workflows[1].a.params[3].param", "prior_value", "string", "cfg.json", "cfg.json", "[]", "literal", "observed", "[]", "{}"),
        ("n3", "repo", "ctl.yml", 10, 10, "yaml", "workflows[2].b.params[1].param.name", "workflows[2].b.params[1].param", "name", "string", "s2t.source.table.name", "s2t.source.table.name", "[]", "literal", "observed", "[]", "{}"),
        ("v3", "repo", "ctl.yml", 10, 10, "yaml", "workflows[2].b.params[1].param.prior_value", "workflows[2].b.params[1].param", "prior_value", "string", "stage_b", "stage_b", "[]", "literal", "observed", "[]", "{}"),
        ("n4", "repo", "ctl.yml", 11, 11, "yaml", "workflows[2].b.params[2].param.name", "workflows[2].b.params[2].param", "name", "string", "s2t.target.table.name", "s2t.target.table.name", "[]", "literal", "observed", "[]", "{}"),
        ("v4", "repo", "ctl.yml", 11, 11, "yaml", "workflows[2].b.params[2].param.prior_value", "workflows[2].b.params[2].param", "prior_value", "string", "final_b", "final_b", "[]", "literal", "observed", "[]", "{}"),
        ("c3", "repo", "ctl.yml", 12, 12, "yaml", "workflows[2].b.params[3].param.name", "workflows[2].b.params[3].param", "name", "string", "b2c.sql.pipelines.config.path", "b2c.sql.pipelines.config.path", "[]", "literal", "observed", "[]", "{}"),
        ("c4", "repo", "ctl.yml", 12, 12, "yaml", "workflows[2].b.params[3].param.prior_value", "workflows[2].b.params[3].param", "prior_value", "string", "cfg.json", "cfg.json", "[]", "literal", "observed", "[]", "{}"),
        ("s", "repo", "cfg.json", 20, 20, "json", "s2tTableList", None, "s2tTableList", "string", "${s2t.source.table.name}->${s2t.target.table.name}", "${s2t.source.table.name}->${s2t.target.table.name}", "[]", "template", "observed", "[]", "{}"),
    ]
    con.executemany(
        f"INSERT INTO sql_workflow_binding ({columns}) VALUES ({','.join('?' for _ in range(17))})",
        rows,
    )
    con.execute(
        "INSERT INTO sql_workflow_context_file "
        "(sql_workflow_context_file_id,repo_id,workflow_context_file,reachable_file,reachable_file_kind,context_hop_count,context_files_json,context_reference_ids_json,resolution_status,resolution_reasons_json) "
        "VALUES ('ctx','repo','ctl.yml','cfg.json','config',1,'[\"ctl.yml\",\"cfg.json\"]','[]','resolved','[]')"
    )

    observations = derive_sql_producer_observations(con, repo_id="repo")
    copies = [m for m in observations.materializations if m.get("kind") == "workflow_copy"]
    pairs = {(m.get("source_table"), m.get("table"), m.get("mapping_basis")) for m in copies}
    assert pairs == {
        ("stage_a", "final_a", "observed_scoped_parameter_environment_plus_referenced_s2t_table_list"),
        ("stage_b", "final_b", "observed_scoped_parameter_environment_plus_referenced_s2t_table_list"),
    }
    con.close()
