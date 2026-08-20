from __future__ import annotations

import json

import duckdb

from knowledge_layer_core.sql_value_source_semantics import (
    StorageKeySemanticIndex,
    is_parent_key_identity_extraction,
)
from knowledge_layer_core.sql_target_source_mapping_builder import _PlaceholderResolutionIndex, _build_diagnostics, _classify_terminal_source_identity, _has_terminal_field_identity


def _payload(tree: dict) -> str:
    return json.dumps({"properties": {"storage_key_expression_tree": tree}}, sort_keys=True)


def test_parent_key_semantics_require_structured_sql_and_observed_storage_evidence() -> None:
    c = duckdb.connect(":memory:")
    c.execute("CREATE TABLE model_storage_record(observation_id VARCHAR, storage_alias VARCHAR, storage_key_field VARCHAR, payload_json JSON)")
    c.execute("CREATE TABLE model_storage_key_lineage(observation_id VARCHAR, source_alias VARCHAR, target_alias VARCHAR, source_key_passed_into_target_key BOOLEAN, payload_json JSON)")
    c.execute("CREATE TABLE model_storage_reference(observation_id VARCHAR, source_alias VARCHAR, target_alias VARCHAR, target_storage_key_field VARCHAR, payload_json JSON)")

    parent = "com.example.Parent"
    child = "com.example.Child"
    parent_tree = {
        "node_type": "binary_expression",
        "operator": "+",
        "children": [
            {"node_type": "string_literal", "children": [{"node_type": "string_fragment", "value": "Parent_"}]},
            {"node_type": "method_invocation", "children": [{"node_type": "identifier", "value": "getId"}]},
        ],
    }
    child_tree = {
        "node_type": "binary_expression",
        "operator": "+",
        "children": [
            {"node_type": "identifier", "value": "parentKey"},
            {"node_type": "character_literal", "value": "'.'"},
            {"node_type": "identifier", "value": "fieldName"},
        ],
    }
    c.execute("INSERT INTO model_storage_record VALUES (?,?,?,?)", ["p", parent, "key", _payload(parent_tree)])
    c.execute("INSERT INTO model_storage_record VALUES (?,?,?,?)", ["c", child, "key", _payload(child_tree)])
    reference_payload = json.dumps({"properties": {"binding_path": [{
        "callee_parameter": "parentKey",
        "resolution": "exact_same_class_name_and_arity",
        "resolved_expression": '"Parent_" + parent.getId()',
    }]}})
    c.execute("INSERT INTO model_storage_reference VALUES (?,?,?,?,?)", ["r1", parent, child, "key", reference_payload])

    index = StorageKeySemanticIndex(c)
    alias, representation, basis = index.resolve_relation_alias("${schema}.com_example_child_hist")
    assert (alias, representation, basis) == (child, "history", "unique_exact_flattened_storage_alias")
    paths = index.ancestor_paths(child, "key")
    assert [item["ancestor_alias"] for item in paths] == [parent]
    assert paths[0]["evidence_ids"] == ("r1",)

    structured_path = [
        {"operation": "regexpsplit", "secondary_expression": "'\\\\.'"},
        {"operation": "bracket", "index_expressions": ["0"]},
        {"operation": "regexpsplit", "secondary_expression": "'_'"},
        {"operation": "bracket", "index_expressions": ["1"]},
        {"operation": "trycast", "target_type": "BIGINT"},
        {"operation": "alias", "output_name": "id"},
    ]
    assert is_parent_key_identity_extraction(structured_path)
    assert not is_parent_key_identity_extraction(structured_path[:3])
    wrong = [dict(x) for x in structured_path]
    wrong[3] = {"operation": "bracket", "index_expressions": ["2"]}
    assert not is_parent_key_identity_extraction(wrong)


def test_placeholder_resolution_never_guesses_through_partial_binding() -> None:
    c=duckdb.connect(":memory:")
    c.execute("""CREATE TABLE sql_placeholder_binding_resolution(
      sql_placeholder_binding_resolution_id VARCHAR, repo_id VARCHAR, workflow_context_file VARCHAR, sql_file VARCHAR,
      placeholder VARCHAR, resolved_value VARCHAR, resolution_status VARCHAR, resolution_reasons_json JSON,
      sql_workflow_binding_id VARCHAR, evidence_json JSON
    )""")
    c.execute("INSERT INTO sql_placeholder_binding_resolution VALUES (?,?,?,?,?,?,?,?,?,?)",[
        'p1','repo','wf.yaml','read.sql','snp_src_schema_name','${inventory.cod_src_schema}','partial',
        json.dumps(['binding_template_has_unresolved_placeholders']),'b1',json.dumps([{'file':'wf.yaml'}]),
    ])
    index=_PlaceholderResolutionIndex(c,'repo')
    relation,status,evidence=index.resolve_relation('${snp_src_schema_name}.individual',workflow_context='wf.yaml',sql_file='read.sql')
    assert relation=='${snp_src_schema_name}.individual'
    assert status=='partial'
    assert evidence[0]['status']=='partial'


def test_placeholder_resolution_uses_only_exact_observed_complete_binding() -> None:
    c=duckdb.connect(":memory:")
    c.execute("""CREATE TABLE sql_placeholder_binding_resolution(
      sql_placeholder_binding_resolution_id VARCHAR, repo_id VARCHAR, workflow_context_file VARCHAR, sql_file VARCHAR,
      placeholder VARCHAR, resolved_value VARCHAR, resolution_status VARCHAR, resolution_reasons_json JSON,
      sql_workflow_binding_id VARCHAR, evidence_json JSON
    )""")
    c.execute("INSERT INTO sql_placeholder_binding_resolution VALUES (?,?,?,?,?,?,?,?,?,?)",[
        'p1','repo','wf.yaml','read.sql','schema_name','platform_src','resolved',json.dumps([]),'b1',json.dumps([]),
    ])
    index=_PlaceholderResolutionIndex(c,'repo')
    relation,status,evidence=index.resolve_relation('${schema_name}.individual',workflow_context='wf.yaml',sql_file='read.sql')
    assert relation=='platform_src.individual'
    assert status=='resolved'
    assert evidence[0]['status']=='resolved'
    # Same placeholder name in another SQL file is not reused as a fallback.
    other,status_other,_=index.resolve_relation('${schema_name}.individual',workflow_context='wf.yaml',sql_file='other.sql')
    assert other=='${schema_name}.individual'
    assert status_other=='partial'


def test_product_field_origin_requires_relation_and_column_identity() -> None:
    assert _has_terminal_field_identity('schema.table', 'field')
    assert not _has_terminal_field_identity(None, 'field')
    assert not _has_terminal_field_identity('schema.table', None)
    assert not _has_terminal_field_identity('', '${expression}')


def test_terminal_source_placeholder_is_useful_but_not_resolved_identity() -> None:
    assert _classify_terminal_source_identity(
        "schema.${table_name}", "client_id", placeholder_status="partial"
    ) == ("partial", "candidate", "source_relation_placeholder_unresolved")
    assert _classify_terminal_source_identity(
        "schema.client", "client_id", placeholder_status="resolved"
    ) == ("resolved", "derived", "terminal_physical_relation_without_observed_local_producer")


def test_empty_mapping_with_observed_materializations_is_visible_diagnostic() -> None:
    diagnostics = _build_diagnostics({
        "sql_observed_relation_materialization": 635,
        "sql_target_source_mapping": 0,
        "sql_target_source_mapping_gap": 0,
    })
    assert diagnostics == [{
        "code": "sql_target_source_mapping_empty_with_observed_materializations",
        "severity": "warning",
        "message": "Observed SQL relation materializations exist, but no target-to-source column mappings were produced.",
        "basis": "observed_relation_materializations_without_target_column_mapping_seed",
        "counts": {
            "sql_observed_relation_materialization": 635,
            "sql_target_source_mapping": 0,
            "sql_target_source_mapping_gap": 0,
        },
    }]
    assert _build_diagnostics({
        "sql_observed_relation_materialization": 6,
        "sql_target_source_mapping": 878,
        "sql_target_source_mapping_gap": 42,
    }) == []
