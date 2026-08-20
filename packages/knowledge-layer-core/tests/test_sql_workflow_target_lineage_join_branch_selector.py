from types import SimpleNamespace

from knowledge_layer_core.sql_workflow_target_lineage import _filter_terminals_by_join_branch_selector


def test_join_key_filters_incompatible_inner_set_branch() -> None:
    traversal = SimpleNamespace(
        projections={
            'p-sbs': {'output': 'sbs_counterparty_sid', 'expression': 's.counterparty_sid AS sbs_counterparty_sid', 'wildcard': False},
            'p-asbs': {'output': 'sbs_counterparty_sid', 'expression': 'CAST(NULL AS STRING) AS sbs_counterparty_sid', 'wildcard': False},
        },
        projections_by_scope={'scope-sbs': ['p-sbs'], 'scope-asbs': ['p-asbs']},
        relations={
            'set-rel': {'source_scopes': ['scope-sbs', 'scope-asbs']},
        },
    )
    selector_index = {
        ('outer-scope', 'joined-rel'): [
            {'join_edge_id': 'j1', 'column': 'sbs_counterparty_sid', 'predicate': 's.sid = c.sbs_counterparty_sid'}
        ]
    }

    def terminal(branch_scope: str) -> dict:
        return {
            'relation_path': [
                {'relation_id': 'joined-rel', 'scope_id': 'outer-scope', 'usage_role': 'join', 'relation_kind': 'physical'},
                {'relation_id': 'set-rel', 'scope_id': 'set-container', 'usage_role': 'from', 'relation_kind': 'cte'},
                {'relation_id': f'branch-{branch_scope}', 'scope_id': branch_scope, 'usage_role': 'from', 'relation_kind': 'cte'},
            ]
        }

    filtered = _filter_terminals_by_join_branch_selector(
        [terminal('scope-sbs'), terminal('scope-asbs')],
        traversal=traversal,
        selector_index=selector_index,
    )

    assert len(filtered) == 1
    assert filtered[0]['join_branch_selector']['selector_column'] == 'sbs_counterparty_sid'
    assert filtered[0]['join_branch_selector']['selected_branch_scope_id'] == 'scope-sbs'
    assert filtered[0]['join_branch_selector']['branch_projection_state'] == 'populated'
