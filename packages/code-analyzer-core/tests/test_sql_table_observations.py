from __future__ import annotations

from pathlib import Path

from code_analyzer_core.scanners.sql_table_observations import scan_sql_table_observations


def _db_schema() -> dict:
    return {
        "keys": [
            {
                "db_schema_key_id": "pk_customers",
                "constraint_kind": "primary_key",
                "constraint_name": "pk_customers",
                "table_name": "customers",
                "columns": ["id", "namespace"],
                "file": "db/V1.sql",
                "line_start": 2,
                "source_type": "liquibase_sql_ddl",
            },
            {
                "db_schema_key_id": "pk_orders",
                "constraint_kind": "primary_key",
                "constraint_name": "pk_orders",
                "table_name": "orders",
                "columns": ["order_id"],
                "file": "db/V1.sql",
                "line_start": 8,
                "source_type": "liquibase_sql_ddl",
            },
        ],
        "indexes": [
            {
                "db_schema_index_id": "ux_orders_external",
                "index_name": "ux_orders_external",
                "table_name": "orders",
                "columns": ["external_id"],
                "unique": True,
                "file": "db/V1.sql",
                "line_start": 12,
                "source_type": "liquibase_sql_ddl",
            }
        ],
    }


def _scan(tmp_path: Path, sql: str) -> dict:
    path = tmp_path / "src/main/resources/db/query.sql"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(sql, encoding="utf-8")
    return scan_sql_table_observations(tmp_path, [path], repo_id="repo", db_schema=_db_schema())


def test_composite_join_pairs_are_extracted_and_match_declared_key(tmp_path):
    result = _scan(
        tmp_path,
        """
        SELECT o.order_id
        FROM orders o
        JOIN customers c
          ON o.customer_id = c.id
         AND o.namespace = c.namespace;
        """,
    )
    joins = [x for x in result["relationships"] if x["relation_kind"] == "sql_join_predicate"]
    assert len(joins) == 1
    assert [(p["left"]["column_name"], p["right"]["column_name"]) for p in joins[0]["column_pairs"]] == [
        ("customer_id", "id"),
        ("namespace", "namespace"),
    ]
    assert joins[0]["matched_declared_keys"] == [
        {
            "side": "right",
            "key_id": "pk_customers",
            "key_kind": "declared_primary_key",
            "matched_columns": ["id", "namespace"],
        }
    ]


def test_correlated_subquery_predicate_is_separate_from_join(tmp_path):
    result = _scan(
        tmp_path,
        """
        SELECT o.order_id
        FROM orders o
        WHERE EXISTS (
          SELECT 1 FROM customers c
          WHERE c.id = o.customer_id
            AND c.namespace = o.namespace
        );
        """,
    )
    items = [x for x in result["relationships"] if x["relation_kind"] == "correlated_subquery_predicate"]
    assert len(items) == 1
    assert len(items[0]["column_pairs"]) == 2


def test_insert_select_and_create_view_publish_directional_dependencies(tmp_path):
    result = _scan(
        tmp_path,
        """
        INSERT INTO order_archive(order_id, external_id)
        SELECT o.order_id, o.external_id FROM orders o;
        CREATE VIEW active_orders AS SELECT * FROM orders WHERE status = 'ACTIVE';
        """,
    )
    movement = [x for x in result["relationships"] if x["relation_kind"] == "data_movement"]
    view = [x for x in result["relationships"] if x["relation_kind"] == "view_dependency"]
    assert len(movement) == 1
    assert movement[0]["left_table"]["table_name"] == "orders"
    assert movement[0]["right_table"]["table_name"] == "order_archive"
    assert [(p["left"]["column_name"], p["right"]["column_name"]) for p in movement[0]["column_pairs"]] == [
        ("order_id", "order_id"),
        ("external_id", "external_id"),
    ]
    assert len(view) == 1
    assert view[0]["left_table"]["table_name"] == "orders"
    assert view[0]["right_table"]["table_name"] == "active_orders"


def test_merge_and_on_conflict_publish_key_usage_without_primary_key_verdict(tmp_path):
    result = _scan(
        tmp_path,
        """
        MERGE INTO orders o
        USING incoming_orders s
        ON o.external_id = s.external_id
        WHEN MATCHED THEN UPDATE SET status = s.status;
        INSERT INTO orders(order_id, external_id)
        VALUES (1, 'A')
        ON CONFLICT (external_id) DO UPDATE SET order_id = excluded.order_id;
        """,
    )
    kinds = [x["key_kind"] for x in result["keys"]]
    assert kinds.count("merge_match_key") == 2
    assert kinds.count("upsert_conflict_key") == 1
    assert "declared_primary_key" in kinds
    assert "declared_unique_index" in kinds
    assert all("confidence" not in x and "verdict" not in x for x in result["keys"])


def test_row_number_partition_is_observation_not_declared_key(tmp_path):
    result = _scan(
        tmp_path,
        """
        SELECT order_id,
               ROW_NUMBER() OVER (PARTITION BY customer_id, namespace ORDER BY created_at DESC) AS rn
        FROM orders;
        """,
    )
    candidates = [x for x in result["keys"] if x["key_kind"] == "deduplication_partition_key"]
    assert len(candidates) == 1
    assert [x["column_name"] for x in candidates[0]["columns"]] == ["customer_id", "namespace"]
    assert candidates[0]["observation_basis"] == ["row_number_partition_by"]


def test_overview_counts_and_fact_projection_are_consistent(tmp_path):
    result = _scan(tmp_path, "SELECT * FROM orders o JOIN customers c ON o.customer_id = c.id;")
    assert result["overview"]["relationship_observations"] == len(result["relationships"])
    assert result["overview"]["key_observations"] == len(result["keys"])
    assert len(result["facts"]) == len(result["relationships"]) + len(result["keys"])

