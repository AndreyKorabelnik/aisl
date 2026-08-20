from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "knowledge_api"


def test_knowledge_api_does_not_query_klc_marts_directly() -> None:
    text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(PACKAGE.rglob("*.py"))
        if "contract_v1/store.py" not in path.as_posix()
    )
    forbidden = (
        "import duckdb",
        "duckdb.connect",
        "FROM effective_data_model_",
        "FROM cross_artifact_",
        "FROM observed_storage_",
        "information_schema.tables",
    )
    for token in forbidden:
        assert token not in text, token


def test_publication_registry_sql_is_not_mistaken_for_klc_read_semantics() -> None:
    store = (PACKAGE / "contract_v1" / "store.py").read_text(encoding="utf-8")
    assert "revisions" in store
    assert "systems" in store
    assert "effective_data_model_entity" not in store
    assert "cross_artifact_mapping_build" not in store
