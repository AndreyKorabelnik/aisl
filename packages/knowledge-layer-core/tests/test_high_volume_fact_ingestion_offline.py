from pathlib import Path
import re

from knowledge_layer_core.workspace_schema import DDL


def _table_statement(name: str) -> str:
    match = re.search(rf"CREATE TABLE {re.escape(name)}\s*\(", DDL)
    assert match is not None
    end = DDL.index(";", match.start())
    return DDL[match.start():end + 1]


def test_high_volume_fact_tables_are_append_only_and_validated_separately():
    import knowledge_layer_core.data_model_materialization as materialization_module
    materialization = Path(materialization_module.__file__).read_text()
    evidence = _table_statement("evidence_ref")
    observations = _table_statement("source_observation")
    assert "PRIMARY KEY" not in evidence
    assert "PRIMARY KEY" not in observations
    assert "batch_size: int = 100000" in materialization
