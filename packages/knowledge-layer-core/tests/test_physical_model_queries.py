from __future__ import annotations

import json
from pathlib import Path

import duckdb

from prepared_knowledge_runtime import KnowledgeLayerQuery
from knowledge_layer_core.physical_model_schema import PHYSICAL_MODEL_DDL


def _artifact(tmp_path: Path) -> Path:
    root = tmp_path / "physical-model-klc"
    root.mkdir()
    db = root / "knowledge-layer.duckdb"
    con = duckdb.connect(str(db))
    try:
        con.execute(PHYSICAL_MODEL_DDL)
        con.execute(
            "INSERT INTO physical_model_source VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                "pdm", "/tmp/manifest.json", "physical-model/v1", "fingerprint", "0.43.7",
                "model.pdm", "sha", "model-object", "Model", "MODEL", "16.6", "Hive",
                "partial", 1, json.dumps({"owner": "test"}), json.dumps({"schema_version": "physical-model/v1"}),
            ],
        )
        tables = [
            (
                "table-client", "pdm", "o1", "uuid-1", "Model", "MODEL",
                json.dumps(["Business"]), json.dumps(["BUSINESS"]), "Клиент", "t_client",
                "Business.t_client", None, "Client table", None, None, None, 2, 1,
                "model.pdm", json.dumps({"file": "model.pdm", "pdm_object_id": "o1"}), json.dumps({}),
            ),
            (
                "table-country", "pdm", "o2", "uuid-2", "Model", "MODEL",
                json.dumps(["Dictionary"]), json.dumps(["DICTIONARY"]), "Страна", "t_country",
                "Dictionary.t_country", None, None, None, None, None, 2, 1,
                "model.pdm", json.dumps({"file": "model.pdm", "pdm_object_id": "o2"}), json.dumps({}),
            ),
        ]
        con.executemany("INSERT INTO physical_model_table VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", tables)
        columns = [
            ("column-client-id", "table-client", "pdm", "c1", "cu1", 1, "Идентификатор", "client_id", "bigint", None, None, True, None, None, None, "model.pdm", json.dumps({"pdm_object_id": "c1"}), json.dumps({})),
            ("column-client-country", "table-client", "pdm", "c2", "cu2", 2, "Код страны", "country_code", "string", 3, None, False, None, None, None, "model.pdm", json.dumps({"pdm_object_id": "c2"}), json.dumps({})),
            ("column-country-code", "table-country", "pdm", "c3", "cu3", 1, "Код", "code", "string", 3, None, True, None, None, None, "model.pdm", json.dumps({"pdm_object_id": "c3"}), json.dumps({})),
            ("column-country-name", "table-country", "pdm", "c4", "cu4", 2, "Название", "name", "string", 200, None, False, None, None, None, "model.pdm", json.dumps({"pdm_object_id": "c4"}), json.dumps({})),
        ]
        con.executemany("INSERT INTO physical_model_column VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", columns)
        keys = [
            ("key-client", "table-client", "pdm", "k1", "ku1", "PK client", "pk_client", "primary", json.dumps(["c1"]), json.dumps(["client_id"]), json.dumps([]), "model.pdm", json.dumps({}), json.dumps({})),
            ("key-country", "table-country", "pdm", "k2", "ku2", "PK country", "pk_country", "primary", json.dumps(["c3"]), json.dumps(["code"]), json.dumps([]), "model.pdm", json.dumps({}), json.dumps({})),
        ]
        con.executemany("INSERT INTO physical_model_key VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", keys)
        con.execute(
            "INSERT INTO physical_model_relationship VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                "rel-country", "pdm", "r1", "ru1", "Клиент — страна", "client_country", "0..1",
                "o2", "table-country", "t_country", "o1", "table-client", "t_client",
                "k2", "key-country",
                json.dumps([{"parent_column_code": "code", "child_column_code": "country_code"}]),
                "resolved", "model.pdm", json.dumps({"pdm_object_id": "r1"}), json.dumps({}),
            ],
        )
        con.execute(
            "INSERT INTO physical_model_gap VALUES (?, ?, ?, ?, ?, ?, ?)",
            ["gap-1", "pdm", "unresolved_domain", "c2", "domain-x", "Domain is unresolved", json.dumps({})],
        )
    finally:
        con.close()
    return root


def test_summary_and_capabilities(tmp_path: Path) -> None:
    query = KnowledgeLayerQuery(_artifact(tmp_path))
    assert "common.physical-model.query" in query.capabilities()
    summary = query.physical_model_summary()
    assert summary["counts"] == {"tables": 2, "columns": 4, "keys": 2, "relationships": 1, "gaps": 1}
    assert summary["relationship_resolution"] == {"resolved": 1}
    assert summary["gap_kinds"] == {"unresolved_domain": 1}


def test_table_search_by_table_or_column_and_detail(tmp_path: Path) -> None:
    query = KnowledgeLayerQuery(_artifact(tmp_path))
    by_table = query.list_physical_model_tables(search="t_country", include_columns=True, max_results=10)
    assert by_table["total_count"] == 1
    assert by_table["items"][0]["table_name"] == "Страна"
    assert [column["column_code"] for column in by_table["items"][0]["columns"]] == ["code", "name"]

    by_column = query.list_physical_model_tables(search="country_code", max_results=10)
    assert [item["table_code"] for item in by_column["items"]] == ["t_client"]

    detail = query.get_physical_model_table("table-client")
    assert detail["not_found"] is False
    assert [column["column_code"] for column in detail["columns"]] == ["client_id", "country_code"]
    assert detail["keys"][0]["column_codes"] == ["client_id"]
    assert detail["relationships"][0]["parent_table_name"] == "Страна"
    assert detail["relationships"][0]["joins"] == [
        {"parent_column_code": "code", "child_column_code": "country_code"}
    ]
    assert query.get_physical_model_table("missing")["not_found"] is True


def test_columns_keys_relationships_and_gaps_are_filterable(tmp_path: Path) -> None:
    query = KnowledgeLayerQuery(_artifact(tmp_path))
    columns = query.list_physical_model_columns(table_id="table-client", search="country", max_results=10)
    assert columns["total_count"] == 1
    assert columns["items"][0]["column_code"] == "country_code"

    keys = query.list_physical_model_keys(table_id="table-country", key_kind="primary", max_results=10)
    assert keys["items"][0]["column_codes"] == ["code"]

    parent = query.list_physical_model_relationships(table_id="table-country", direction="parent", max_results=10)
    child = query.list_physical_model_relationships(table_id="table-client", direction="child", max_results=10)
    assert parent["total_count"] == child["total_count"] == 1
    assert parent["items"][0]["resolution_status"] == "resolved"

    gaps = query.list_physical_model_gaps(gap_kind="unresolved_domain", search="domain-x", max_results=10)
    assert gaps["total_count"] == 1
    assert gaps["items"][0]["message"] == "Domain is unresolved"


def test_page_tokens_are_bound_to_filters(tmp_path: Path) -> None:
    query = KnowledgeLayerQuery(_artifact(tmp_path))
    first = query.list_physical_model_tables(max_results=1)
    assert first["truncated"] is True
    second = query.list_physical_model_tables(max_results=1, page_token=first["next_token"])
    assert second["page_offset"] == 1
    assert second["items"][0]["table_code"] != first["items"][0]["table_code"]
