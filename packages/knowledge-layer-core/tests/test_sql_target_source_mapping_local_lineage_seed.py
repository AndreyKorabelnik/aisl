from types import SimpleNamespace

from knowledge_layer_core.sql_target_source_mapping_builder import _local_lineage_origins


class Traversal:
    def __init__(self):
        self.calls = []

    def usage_origins(self, workflow, usage_id):
        self.calls.append(("usage", workflow, usage_id))
        return [{"kind": "usage"}]

    def relation_column_origins(self, workflow, relation_id, column):
        self.calls.append(("relation", workflow, relation_id, column))
        return [{"kind": "relation"}]


def test_usage_terminal_remains_primary_seed():
    t = Traversal()
    assert _local_lineage_origins(t, workflow="wf", usage_id="u1", relation_id="r1", column="c1") == [{"kind": "usage"}]
    assert t.calls == [("usage", "wf", "u1")]


def test_observed_relation_column_seeds_synthetic_final_materialization_row():
    t = Traversal()
    assert _local_lineage_origins(t, workflow="wf", usage_id=None, relation_id="r1", column="c1") == [{"kind": "relation"}]
    assert t.calls == [("relation", "wf", "r1", "c1")]


def test_missing_terminal_evidence_remains_unresolved():
    t = Traversal()
    assert _local_lineage_origins(t, workflow="wf", usage_id=None, relation_id=None, column="c1") == []
    assert t.calls == []
