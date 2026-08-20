from types import SimpleNamespace

import duckdb

from knowledge_layer_core.sql_producer_observations import _observed_scoped_s2t_copies
from knowledge_layer_core.sql_target_source_mapping_builder import _observed_workflow_copy_target_seeds


def test_scoped_name_prior_value_parameters_resolve_referenced_s2t_table_list() -> None:
    c = duckdb.connect(':memory:')
    c.execute('''
        CREATE TABLE sql_workflow_binding(
            sql_workflow_binding_id VARCHAR,
            repo_id VARCHAR,
            file VARCHAR,
            line_start BIGINT,
            binding_path VARCHAR,
            parent_path VARCHAR,
            binding_name VARCHAR,
            scalar_value VARCHAR,
            value_expression VARCHAR,
            evidence_json JSON
        )
    ''')
    rows = [
        ('b1','r','resources/ctl/ctl.yml',10,'workflows[1].target.params[1].param.name','workflows[1].target.params[1].param','name','b2c.sql.pipelines.config.path','b2c.sql.pipelines.config.path','[]'),
        ('b2','r','resources/ctl/ctl.yml',10,'workflows[1].target.params[1].param.prior_value','workflows[1].target.params[1].param','prior_value','{{datamart_dir}}/etl/workflows/pa/conf/b2c_sql_config.json','{{datamart_dir}}/etl/workflows/pa/conf/b2c_sql_config.json','[]'),
        ('b3','r','resources/ctl/ctl.yml',11,'workflows[1].target.params[2].param.name','workflows[1].target.params[2].param','name','s2t.source.table.name','s2t.source.table.name','[]'),
        ('b4','r','resources/ctl/ctl.yml',11,'workflows[1].target.params[2].param.prior_value','workflows[1].target.params[2].param','prior_value','target_diff','target_diff','[]'),
        ('b5','r','resources/ctl/ctl.yml',12,'workflows[1].target.params[3].param.name','workflows[1].target.params[3].param','name','s2t.target.table.name','s2t.target.table.name','[]'),
        ('b6','r','resources/ctl/ctl.yml',12,'workflows[1].target.params[3].param.prior_value','workflows[1].target.params[3].param','prior_value','target','target','[]'),
        ('b7','r','resources/ctl/ctl.yml',13,'workflows[1].target.params[4].param.name','workflows[1].target.params[4].param','name','description','description','[]'),
        ('b8','r','resources/ctl/ctl.yml',13,'workflows[1].target.params[4].param.prior_value','workflows[1].target.params[4].param','prior_value','unrelated workflow metadata','unrelated workflow metadata','[]'),
        ('cfg','r','etl/workflows/pa/conf/b2c_sql_config.json',42,'stage.config.s2tTableList','stage.config','s2tTableList','${s2t.source.table.name}->${s2t.target.table.name}','${s2t.source.table.name}->${s2t.target.table.name}','[]'),
    ]
    c.executemany('INSERT INTO sql_workflow_binding VALUES (?,?,?,?,?,?,?,?,?,?)', rows)

    copies = _observed_scoped_s2t_copies(c, repo_id='r')
    assert [(item['source'], item['target']) for item in copies] == [('target_diff', 'target')]
    assert copies[0]['workflow'] == 'resources/ctl/ctl.yml'
    assert copies[0]['scope_path'] == 'workflows[1].target'
    assert {item['name'] for item in copies[0]['parameter_records']} == {
        'b2c.sql.pipelines.config.path', 's2t.source.table.name', 's2t.target.table.name'
    }


def test_observed_workflow_copy_is_target_seed_only_with_complete_source_contract() -> None:
    materialization = {
        'id': 'copy1',
        'workflow': 'resources/ctl/ctl.yml',
        'kind': 'workflow_copy',
        'source_table': 'target_diff',
        'table': 'target',
        'resolution_status': 'matched',
        'mapping_basis': 'observed_scoped_parameter_environment_plus_referenced_s2t_table_list',
        'provenance': {},
    }

    class Index:
        def output_contract(self, producer):
            assert producer is materialization
            return {'id', 'name'}, 'workflow_copy_source_materialization_contract'

    class Traversal:
        materializations = Index()

        def materialized_table_column_origins(self, workflow, target, column):
            return [{'relation_id': 'src', 'column': column, 'materialization_path': ['copy1']}]

    seeds, gaps = _observed_workflow_copy_target_seeds(
        SimpleNamespace(materializations=(materialization,)), Traversal()
    )
    assert gaps == []
    assert [(item['target'], item['target_col']) for item in seeds] == [('target', 'id'), ('target', 'name')]
    assert all('origins' not in item for item in seeds)  # origins are streamed per seed during publication


def test_observed_workflow_copy_keeps_explicit_gap_when_source_contract_is_incomplete() -> None:
    materialization = {
        'id': 'copy1', 'workflow': 'wf', 'kind': 'workflow_copy', 'source_table': 'x_diff', 'table': 'x',
        'resolution_status': 'matched', 'mapping_basis': 'observed_workflow_s2t_table_list', 'provenance': {},
    }

    class Index:
        def output_contract(self, _producer):
            return None, 'workflow_copy_source_contract_incomplete'

    traversal = SimpleNamespace(materializations=Index())
    seeds, gaps = _observed_workflow_copy_target_seeds(SimpleNamespace(materializations=(materialization,)), traversal)
    assert seeds == []
    assert gaps[0]['target'] == 'x'
    assert gaps[0]['gap_kind'] == 'workflow_copy_output_contract_unresolved'


def test_workflow_copy_partial_contract_publishes_branch_gap_and_target_seeds() -> None:
    materialization = {
        'id': 'copy-partial',
        'workflow': 'wf',
        'kind': 'workflow_copy',
        'source_table': 'x_diff',
        'table': 'x',
        'resolution_status': 'matched',
        'mapping_basis': 'observed_workflow_s2t_table_list',
        'provenance': {},
    }

    class Index:
        def output_contract(self, _producer):
            return {'id', 'name'}, 'workflow_copy_partial_consistent_source_materialization_contract'

        def output_contract_diagnostics(self, _producer):
            return ({
                'gap_kind': 'workflow_copy_source_branch_incomplete',
                'source_producer_id': 'branch-2',
                'resolution_basis': 'sql_write_source_contract_incomplete',
            },)

    traversal = SimpleNamespace(materializations=Index())
    seeds, gaps = _observed_workflow_copy_target_seeds(
        SimpleNamespace(materializations=(materialization,)), traversal
    )

    assert [(item['target'], item['target_col']) for item in seeds] == [('x', 'id'), ('x', 'name')]
    assert len(gaps) == 1
    assert gaps[0]['gap_kind'] == 'workflow_copy_source_branch_incomplete'
    assert gaps[0]['source_branch']['source_producer_id'] == 'branch-2'
