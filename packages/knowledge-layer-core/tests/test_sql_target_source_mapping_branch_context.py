from types import SimpleNamespace

import duckdb

from knowledge_layer_core.sql_target_source_mapping_builder import (
    _PlaceholderResolutionIndex,
    _mapping_branch_metadata,
    _materialize_value_sources,
    _resolve_branch_driver_metadata,
)
from knowledge_layer_core.sql_target_source_mapping_schema import SQL_TARGET_SOURCE_MAPPING_DDL
from knowledge_layer_core.sql_workflow_target_lineage import _aggregate_equivalent_terminals


def test_scoped_recursive_placeholder_resolution_keeps_unselected_environment_partial() -> None:
    c = duckdb.connect(":memory:")
    c.execute("""CREATE TABLE sql_placeholder_binding_resolution(
      sql_placeholder_binding_resolution_id VARCHAR, repo_id VARCHAR, workflow_context_file VARCHAR, sql_file VARCHAR,
      placeholder VARCHAR, resolved_value VARCHAR, resolution_status VARCHAR, resolution_reasons_json JSON,
      sql_workflow_binding_id VARCHAR, evidence_json JSON
    )""")
    c.execute("""CREATE TABLE sql_statement(repo_id VARCHAR, file VARCHAR)""")
    c.execute("""CREATE TABLE sql_workflow_binding(
      sql_workflow_binding_id VARCHAR, repo_id VARCHAR, file VARCHAR, line_start BIGINT,
      binding_path VARCHAR, parent_path VARCHAR, binding_name VARCHAR,
      scalar_value VARCHAR, value_expression VARCHAR, evidence_json JSON
    )""")
    c.execute("INSERT INTO sql_statement VALUES ('r','etl/workflows/src/sbs/dml/policyaccruals.sql')")
    rows = [
        ('n1','r','resources/ctl/ctl.yml',1,'workflows[1].params[1].param.name','workflows[1].params[1].param','name','app.stg.file.path','app.stg.file.path','[]'),
        ('v1','r','resources/ctl/ctl.yml',1,'workflows[1].params[1].param.prior_value','workflows[1].params[1].param','prior_value','{{datamart_dir}}/etl/workflows/src/sbs/dml/policyaccruals.sql','{{datamart_dir}}/etl/workflows/src/sbs/dml/policyaccruals.sql','[]'),
        ('n2','r','resources/ctl/ctl.yml',2,'workflows[1].params[2].param.name','workflows[1].params[2].param','name','app.sbs.schema.name','app.sbs.schema.name','[]'),
        ('v2','r','resources/ctl/ctl.yml',2,'workflows[1].params[2].param.prior_value','workflows[1].params[2].param','prior_value','{{src_sbs_schema_name}}','{{src_sbs_schema_name}}','[]'),
        ('n3','r','resources/ctl/ctl.yml',3,'workflows[1].params[3].param.name','workflows[1].params[3].param','name','app.sbs.table.name','app.sbs.table.name','[]'),
        ('v3','r','resources/ctl/ctl.yml',3,'workflows[1].params[3].param.prior_value','workflows[1].params[3].param','prior_value','policyaccruals','policyaccruals','[]'),
        ('m1','r','resources/mart.yml',10,'vars.src_sbs_schema_name','vars','src_sbs_schema_name','dev_schema','dev_schema','[]'),
        ('m2','r','resources/mart.yml',20,'stands[1].vars.src_sbs_schema_name','stands[1].vars','src_sbs_schema_name','prod_schema','prod_schema','[]'),
    ]
    c.executemany('INSERT INTO sql_workflow_binding VALUES (?,?,?,?,?,?,?,?,?,?)', rows)

    index = _PlaceholderResolutionIndex(c, 'r')
    relation, status, evidence = index.resolve_relation(
        '${$app.sbs.schema.name}.${$app.sbs.table.name}',
        workflow_context='resources/ctl/ctl.yml',
        sql_file='etl/workflows/src/sbs/dml/policyaccruals.sql',
    )
    assert relation == '{{src_sbs_schema_name}}.policyaccruals'
    assert status == 'partial'
    assert any(item['placeholder'] == 'app.sbs.table.name' and item['status'] == 'resolved' for item in evidence)
    nested = [item for item in evidence if item['placeholder'] == 'src_sbs_schema_name']
    assert nested and nested[-1]['status'] == 'ambiguous'
    assert nested[-1]['candidate_values'] == ['dev_schema', 'prod_schema']


def test_branch_metadata_marks_driver_path_and_join_enrichment() -> None:
    relations = {
        'driver': {'id':'driver','scope_id':'s2','name':'aux.target_sbs','usage_role':'from'},
        'lookup': {'id':'lookup','scope_id':'s2','name':'dim_counterparty','usage_role':'join'},
    }
    traversal = SimpleNamespace(relations=relations, relations_by_scope={'s2':['driver','lookup']})
    driver_origin = {'relation_path':[{
        'relation_id':'driver','relation_name':'aux.target_sbs','relation_kind':'physical','usage_role':'from',
        'query_id':'q','scope_id':'s2','scope_ordinal':2,'file':'target.sql',
    }]}
    enrichment_origin = {'relation_path':[{
        'relation_id':'lookup','relation_name':'dim_counterparty','relation_kind':'physical','usage_role':'join',
        'query_id':'q','scope_id':'s2','scope_ordinal':2,'file':'target.sql',
    }]}
    d = _mapping_branch_metadata(driver_origin, traversal)
    e = _mapping_branch_metadata(enrichment_origin, traversal)
    assert d['source_branch'] == 'target_sbs'
    assert d['branch_relation_name'] == 'aux.target_sbs'
    assert d['driver_relation_name'] is None
    assert d['source_relation_role'] == 'driver_path'
    assert e['source_branch'] == 'target_sbs'
    assert e['branch_relation_name'] == 'aux.target_sbs'
    assert e['driver_relation_name'] is None
    assert e['source_relation_role'] == 'enrichment'


def test_terminal_aggregation_preserves_same_source_across_distinct_union_branches() -> None:
    base = {
        'terminal_source_kind':'column_usage','terminal_relation_id':'src','terminal_relation_name':'schema.src',
        'terminal_relation_kind':'physical','terminal_column':'id','transformations':[],
        'recursive_resolution_status':'resolved','physical_origin_status':'resolved','lineage_status':'resolved',
    }
    a = {**base, 'relation_path':[{'relation_kind':'physical','query_id':'q','scope_id':'s2','scope_ordinal':2}]}
    b = {**base, 'relation_path':[{'relation_kind':'physical','query_id':'q','scope_id':'s3','scope_ordinal':3}]}
    result = _aggregate_equivalent_terminals([a,b])
    assert len(result) == 2


def test_target_branch_anchor_survives_nested_producer_and_marks_nested_join_enrichment() -> None:
    relations = {
        'branch_driver': {'id':'branch_driver','scope_id':'branch_sbs','name':'aux.t_dim_accrual_sbs','usage_role':'from'},
        'branch_lookup': {'id':'branch_lookup','scope_id':'branch_sbs','name':'dim_counterparty','usage_role':'join'},
        'nested_driver': {'id':'nested_driver','scope_id':'nested','name':'src.policyaccruals','usage_role':'from'},
        'nested_join': {'id':'nested_join','scope_id':'nested_join_scope','name':'src.policyaccrualdetails','usage_role':'from'},
    }
    traversal = SimpleNamespace(
        relations=relations,
        relations_by_scope={
            'branch_sbs':['branch_driver','branch_lookup'],
            'nested':['nested_driver'],
            'nested_join_scope':['nested_join'],
        },
    )
    driver_origin = {'relation_path':[
        {'relation_id':'target_cte','relation_name':'t_dim_accrual','relation_kind':'cte','usage_role':'from','query_id':'q','scope_id':'root','scope_ordinal':1,'file':'target.sql'},
        {'relation_id':'branch_driver','relation_name':'aux.t_dim_accrual_sbs','relation_kind':'physical','usage_role':'from','query_id':'q','scope_id':'branch_sbs','scope_ordinal':3,'file':'target.sql'},
        {'relation_id':'nested_driver','relation_name':'src.policyaccruals','relation_kind':'physical','usage_role':'from','query_id':'q2','scope_id':'nested','scope_ordinal':1,'file':'source.sql'},
    ]}
    nested_enrichment_origin = {'relation_path':[
        {'relation_id':'target_cte','relation_name':'t_dim_accrual','relation_kind':'cte','usage_role':'from','query_id':'q','scope_id':'root','scope_ordinal':1,'file':'target.sql'},
        {'relation_id':'branch_driver','relation_name':'aux.t_dim_accrual_sbs','relation_kind':'physical','usage_role':'from','query_id':'q','scope_id':'branch_sbs','scope_ordinal':3,'file':'target.sql'},
        {'relation_id':'dedup','relation_name':'dedup','relation_kind':'cte','usage_role':'join','query_id':'q2','scope_id':'nested','scope_ordinal':3,'file':'stage.sql'},
        {'relation_id':'nested_join','relation_name':'src.policyaccrualdetails','relation_kind':'physical','usage_role':'from','query_id':'q3','scope_id':'nested_join_scope','scope_ordinal':1,'file':'details.sql'},
    ]}
    d = _mapping_branch_metadata(driver_origin, traversal, target_logical_name='t_dim_accrual')
    e = _mapping_branch_metadata(nested_enrichment_origin, traversal, target_logical_name='t_dim_accrual')
    assert d['source_branch'] == 't_dim_accrual_sbs'
    assert d['branch_relation_name'] == 'aux.t_dim_accrual_sbs'
    assert d['driver_relation_name'] is None
    assert d['source_relation_role'] == 'driver_path'
    assert e['source_branch'] == 't_dim_accrual_sbs'
    assert e['branch_relation_name'] == 'aux.t_dim_accrual_sbs'
    assert e['driver_relation_name'] is None
    assert e['source_relation_role'] == 'enrichment'
    assert e['source_relation_role_basis'] == 'observed_join_boundary_on_value_path_after_target_branch_anchor'


def test_scoped_placeholder_resolution_follows_exact_resolved_config_to_sql_reference() -> None:
    c = duckdb.connect(":memory:")
    c.execute("""CREATE TABLE sql_placeholder_binding_resolution(
      sql_placeholder_binding_resolution_id VARCHAR, repo_id VARCHAR, workflow_context_file VARCHAR, sql_file VARCHAR,
      placeholder VARCHAR, resolved_value VARCHAR, resolution_status VARCHAR, resolution_reasons_json JSON,
      sql_workflow_binding_id VARCHAR, evidence_json JSON
    )""")
    c.execute("""CREATE TABLE sql_statement(repo_id VARCHAR, file VARCHAR)""")
    c.execute("""CREATE TABLE sql_workflow_binding(
      sql_workflow_binding_id VARCHAR, repo_id VARCHAR, file VARCHAR, line_start BIGINT,
      binding_path VARCHAR, parent_path VARCHAR, binding_name VARCHAR,
      scalar_value VARCHAR, value_expression VARCHAR, evidence_json JSON
    )""")
    c.execute("""CREATE TABLE sql_workflow_file_reference(
      repo_id VARCHAR, source_file VARCHAR, source_fact_id VARCHAR, resolved_target_file VARCHAR,
      resolved_target_kind VARCHAR, resolution_status VARCHAR, evidence_json JSON
    )""")
    sql_file='etl/workflows/src/b2c_credit/dml/loan_agrmnt.sql'
    config_file='resources/b2c_sql_config_loan.json'
    workflow_file='resources/ctl/ctl.yml'
    c.execute("INSERT INTO sql_statement VALUES ('r', ?)", [sql_file])
    rows = [
        ('n1','r',workflow_file,1,'workflows[2].params[1].param.name','workflows[2].params[1].param','name','b2c.sql.pipelines.config.path','b2c.sql.pipelines.config.path','[]'),
        ('v1','r',workflow_file,1,'workflows[2].params[1].param.prior_value','workflows[2].params[1].param','prior_value',config_file,config_file,'[]'),
        ('n2','r',workflow_file,2,'workflows[2].params[2].param.name','workflows[2].params[2].param','name','app.b2c_credit.schema.name','app.b2c_credit.schema.name','[]'),
        ('v2','r',workflow_file,2,'workflows[2].params[2].param.prior_value','workflows[2].params[2].param','prior_value','{{src_b2c_credit_schema_name}}','{{src_b2c_credit_schema_name}}','[]'),
        ('n3','r',workflow_file,3,'workflows[2].params[3].param.name','workflows[2].params[3].param','name','app.b2c_credit.table.name','app.b2c_credit.table.name','[]'),
        ('v3','r',workflow_file,3,'workflows[2].params[3].param.prior_value','workflows[2].params[3].param','prior_value','loan_agrmnt','loan_agrmnt','[]'),
    ]
    c.executemany('INSERT INTO sql_workflow_binding VALUES (?,?,?,?,?,?,?,?,?,?)', rows)
    # Exact observed chain: the CTL value binding resolves to one config; that config resolves to one SQL file.
    c.execute("INSERT INTO sql_workflow_file_reference VALUES ('r',?,?,?,?,?,?)", [workflow_file,'v1',config_file,'workflow_config','resolved','[]'])
    c.execute("INSERT INTO sql_workflow_file_reference VALUES ('r',?,?,?,?,?,?)", [config_file,'cfg-filepath',sql_file,'sql','resolved','[]'])

    index = _PlaceholderResolutionIndex(c, 'r')
    relation, status, evidence = index.resolve_relation(
        '${$app.b2c_credit.schema.name}.${$app.b2c_credit.table.name}',
        workflow_context=workflow_file,
        sql_file=sql_file,
    )
    assert relation == '{{src_b2c_credit_schema_name}}.loan_agrmnt'
    assert status == 'partial'
    table_resolution=[item for item in evidence if item['placeholder']=='app.b2c_credit.table.name']
    assert table_resolution and table_resolution[-1]['status']=='resolved'
    assert table_resolution[-1]['resolution_basis']=='exact_scoped_parameter_environment_via_resolved_config_sql_reference'


def test_value_mapping_preserves_distinct_branch_context_for_same_terminal_source() -> None:
    source = duckdb.connect(":memory:")
    source.execute("CREATE TABLE sql_column_usage(repo_id VARCHAR, sql_column_usage_id VARCHAR, payload_json JSON)")
    source.execute("""CREATE TABLE sql_placeholder_binding_resolution(
      sql_placeholder_binding_resolution_id VARCHAR, repo_id VARCHAR, workflow_context_file VARCHAR, sql_file VARCHAR,
      placeholder VARCHAR, resolved_value VARCHAR, resolution_status VARCHAR, resolution_reasons_json JSON,
      sql_workflow_binding_id VARCHAR, evidence_json JSON)""")
    target = duckdb.connect(":memory:")
    target.execute(SQL_TARGET_SOURCE_MAPPING_DDL)
    index = _PlaceholderResolutionIndex(source, 'r')
    base = {
        'repo_id':'r','workflow':'resources/ctl/ctl.yml','target':'t_dim_accrual','target_col':'accrual_dt',
        'source_usage_id':None,'source_relation_id':'src','source_relation_name':'src.payments','source_column':'payment_dt',
        'source_file':'source.sql','knowledge_class':'derived','producer_projection_ids':[],
        'terminal_workflow_context':'resources/ctl/ctl.yml','source_relation_role':'driver_path',
        'source_relation_role_basis':'unique_observed_from_relation_in_target_branch_scope',
        'branch_relation_name':'aux.branch','driver_relation_name':'src.payments',
        'driver_relation_status':'resolved','driver_relation_basis':'unique_terminal_relation_on_driver_path_within_observed_branch',
        'driver_relation_candidates':['src.payments'],'root_projection_id':'p','local_lineage_id':'l',
    }
    rows=[
        {**base,'mapping_id':'m1','source_branch':'branch_sbs','source_branch_scope_id':'sbs','source_branch_ordinal':1},
        {**base,'mapping_id':'m2','source_branch':'branch_sbszh','source_branch_scope_id':'sbszh','source_branch_ordinal':2},
    ]
    count,gaps,_ = _materialize_value_sources(
        target, sc=source, repo_id='r', raw_records=rows, semantic_index=None,
        model_storage_artifact_id=None, projections={}, placeholder_index=index,
    )
    assert count == 2
    assert gaps == 0
    actual=target.execute(
        "SELECT source_branch,source_branch_scope_id,source_branch_ordinal,branch_relation_name,driver_relation_name,driver_relation_status,source_relation_role "
        "FROM sql_target_value_source_mapping ORDER BY source_branch"
    ).fetchall()
    assert actual == [
        ('branch_sbs','sbs',1,'aux.branch','src.payments','resolved','driver_path'),
        ('branch_sbszh','sbszh',2,'aux.branch','src.payments','resolved','driver_path'),
    ]


def test_branch_driver_is_unique_terminal_driver_or_explicit_ambiguity() -> None:
    base = {
        'repo_id':'r','workflow':'ctl.yml','target':'t_dim_accrual',
        'source_branch_scope_id':'sbs','source_branch_ordinal':3,'source_branch':'t_dim_accrual_sbs',
        'branch_relation_name':'aux.t_dim_accrual_sbs','mapping_status':'partial',
    }
    rows = [
        {**base,'source_relation_role':'driver_path','source_relation_name':'{{src_sbs_schema_name}}.policyaccruals'},
        {**base,'source_relation_role':'enrichment','source_relation_name':'{{src_sbs_schema_name}}.policyaccrualdetails'},
    ]
    result = _resolve_branch_driver_metadata(rows)
    meta = next(iter(result.values()))
    assert meta['driver_relation_name'] == '{{src_sbs_schema_name}}.policyaccruals'
    assert meta['driver_relation_status'] == 'partial'
    assert rows[1]['driver_relation_name'] == '{{src_sbs_schema_name}}.policyaccruals'

    ambiguous = [
        {**base,'source_branch_scope_id':'asbs','source_branch':'t_dim_accrual_asbs','branch_relation_name':'aux.t_dim_accrual_asbs','source_relation_role':'driver_path','source_relation_name':'src.osago','mapping_status':'resolved'},
        {**base,'source_branch_scope_id':'asbs','source_branch':'t_dim_accrual_asbs','branch_relation_name':'aux.t_dim_accrual_asbs','source_relation_role':'driver_path','source_relation_name':'src.vzr','mapping_status':'resolved'},
    ]
    meta2 = next(iter(_resolve_branch_driver_metadata(ambiguous).values()))
    assert meta2['driver_relation_name'] is None
    assert meta2['driver_relation_status'] == 'ambiguous'
    assert meta2['driver_relation_candidates'] == ['src.osago','src.vzr']


def test_branch_anchor_skips_same_named_target_staging_relation_when_real_branch_follows() -> None:
    relations = {
        'stg': {'id':'stg','scope_id':'stg_scope','name':'custom_stg.t_dim_accrual','usage_role':'from'},
        'branch': {'id':'branch','scope_id':'branch_scope','name':'custom_aux.t_dim_accrual_sbs','usage_role':'from'},
    }
    traversal = SimpleNamespace(relations=relations, relations_by_scope={'stg_scope':['stg'],'branch_scope':['branch']})
    origin = {'relation_path':[
        {'relation_id':'target','relation_name':'t_dim_accrual','relation_kind':'cte','usage_role':'from','query_id':'q','scope_id':'root','scope_ordinal':1,'file':'target.sql'},
        {'relation_id':'stg','relation_name':'custom_stg.t_dim_accrual','relation_kind':'physical','usage_role':'from','query_id':'q','scope_id':'stg_scope','scope_ordinal':2,'file':'target.sql'},
        {'relation_id':'branch','relation_name':'custom_aux.t_dim_accrual_sbs','relation_kind':'physical','usage_role':'from','query_id':'q2','scope_id':'branch_scope','scope_ordinal':3,'file':'target.sql'},
    ]}
    meta = _mapping_branch_metadata(origin,traversal,target_logical_name='t_dim_accrual')
    assert meta['source_branch'] == 't_dim_accrual_sbs'
    assert meta['branch_relation_name'] == 'custom_aux.t_dim_accrual_sbs'
