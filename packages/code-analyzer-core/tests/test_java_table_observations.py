from __future__ import annotations

from pathlib import Path

from code_analyzer_core.scanners.java_scanner import scan_java_files
from code_analyzer_core.scanners.java_table_observations import scan_java_table_observations


def _schema() -> dict:
    return {
        "tables": [
            {"db_schema_table_id": "t_orders", "table_name": "orders", "table_constant": "ORDERS"},
            {"db_schema_table_id": "t_customers", "table_name": "customers", "table_constant": "CUSTOMERS"},
        ],
        "columns": [
            {"table_name": "orders", "table_constant": "ORDERS", "field_constant": "CUSTOMER_ID", "column_name": "customer_id"},
            {"table_name": "orders", "table_constant": "ORDERS", "field_constant": "NAMESPACE", "column_name": "namespace"},
            {"table_name": "orders", "table_constant": "ORDERS", "field_constant": "EXTERNAL_ID", "column_name": "external_id"},
            {"table_name": "customers", "table_constant": "CUSTOMERS", "field_constant": "ID", "column_name": "id"},
            {"table_name": "customers", "table_constant": "CUSTOMERS", "field_constant": "NAMESPACE", "column_name": "namespace"},
        ],
        "keys": [
            {
                "db_schema_key_id": "pk_customers",
                "constraint_kind": "primary_key",
                "table_name": "customers",
                "columns": ["id", "namespace"],
                "file": "V1.sql",
                "line_start": 1,
                "source_type": "liquibase_sql_ddl",
            }
        ],
        "indexes": [],
    }


def _write(repo: Path, rel: str, text: str) -> Path:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_jpa_relationship_and_identity_observations_use_tree_sitter(tmp_path):
    repo = tmp_path / "repo"
    customer_id = _write(repo, "src/main/java/x/CustomerId.java", """
        package x;
        import jakarta.persistence.*;
        @Embeddable
        public class CustomerId {
          @Column(name = "id") Long id;
          @Column(name = "namespace") String namespace;
        }
    """)
    customer = _write(repo, "src/main/java/x/Customer.java", """
        package x;
        import jakarta.persistence.*;
        @Entity @Table(name = "customers")
        public class Customer {
          @EmbeddedId CustomerId id;
        }
    """)
    order = _write(repo, "src/main/java/x/Order.java", """
        package x;
        import jakarta.persistence.*;
        @Entity @Table(name = "orders")
        public class Order {
          @Id @Column(name = "order_id") Long id;
          @ManyToOne
          @JoinColumns({
            @JoinColumn(name = "customer_id", referencedColumnName = "id"),
            @JoinColumn(name = "namespace", referencedColumnName = "namespace")
          })
          Customer customer;
        }
    """)
    files = [customer_id, customer, order]
    facts, *_ = scan_java_files(files)
    result = scan_java_table_observations(repo, files, repo_id="repo", facts=facts, db_schema=_schema())

    orm = [item for item in result["relationships"] if item["relation_kind"] == "orm_mapping"]
    assert len(orm) == 1
    assert orm[0]["left_table"]["table_name"] == "orders"
    assert orm[0]["right_table"]["table_name"] == "customers"
    assert [(pair["left"]["column_name"], pair["right"]["column_name"]) for pair in orm[0]["column_pairs"]] == [
        ("customer_id", "id"),
        ("namespace", "namespace"),
    ]
    assert orm[0]["matched_declared_keys"][0]["key_id"] == "pk_customers"

    identities = [item for item in result["keys"] if item["key_kind"] == "orm_identity"]
    by_entity = {item["entity_name"]: item for item in identities}
    assert [column["column_name"] for column in by_entity["Customer"]["columns"]] == ["id", "namespace"]
    assert [column["column_name"] for column in by_entity["Order"]["columns"]] == ["order_id"]
    assert result["overview"]["syntax_provider"] == "tree_sitter"


def test_unresolved_target_entity_is_retained_instead_of_dropped(tmp_path):
    repo = tmp_path / "repo"
    order = _write(repo, "src/main/java/x/Order.java", """
        package x;
        import jakarta.persistence.*;
        @Entity @Table(name = "orders")
        public class Order {
          @Id Long id;
          @ManyToOne @JoinColumn(name = "customer_id") ExternalCustomer customer;
        }
    """)
    facts, *_ = scan_java_files([order])
    result = scan_java_table_observations(repo, [order], repo_id="repo", facts=facts, db_schema={"keys": [], "indexes": []})
    orm = [item for item in result["relationships"] if item["relation_kind"] == "orm_mapping"]
    assert len(orm) == 1
    assert orm[0]["right_table"]["unresolved_name"] == "ExternalCustomer"
    assert orm[0]["properties"]["referenced_column_unspecified"] is True


def test_id_class_is_mapped_to_entity_columns(tmp_path):
    repo = tmp_path / "repo"
    id_class = _write(repo, "src/main/java/x/OrderId.java", """
        package x;
        public class OrderId { Long tenantId; Long orderId; }
    """)
    entity = _write(repo, "src/main/java/x/Order.java", """
        package x;
        import jakarta.persistence.*;
        @Entity @Table(name = "orders") @IdClass(OrderId.class)
        public class Order {
          @Column(name = "tenant_id") Long tenantId;
          @Column(name = "order_id") Long orderId;
        }
    """)
    facts, *_ = scan_java_files([id_class, entity])
    result = scan_java_table_observations(repo, [id_class, entity], repo_id="repo", facts=facts, db_schema={"keys": [], "indexes": []})
    identity = next(item for item in result["keys"] if item.get("entity_name") == "Order")
    assert identity["key_kind"] == "orm_identity"
    assert [column["column_name"] for column in identity["columns"]] == ["tenant_id", "order_id"]
    assert "jpa_id_class" in identity["observation_basis"]


def test_jooq_join_and_lookup_use_tree_sitter_call_nodes(tmp_path):
    repo = tmp_path / "repo"
    query = _write(repo, "src/main/java/x/Queries.java", """
        package x;
        public class Queries {
          void load(Object externalId) {
            dsl.select().from(ORDERS).join(CUSTOMERS)
              .on(ORDERS.CUSTOMER_ID.eq(CUSTOMERS.ID)
                .and(ORDERS.NAMESPACE.eq(CUSTOMERS.NAMESPACE)))
              .where(ORDERS.EXTERNAL_ID.eq(externalId)).fetch();
          }
        }
    """)
    facts, *_ = scan_java_files([query])
    result = scan_java_table_observations(repo, [query], repo_id="repo", facts=facts, db_schema=_schema())
    joins = [item for item in result["relationships"] if item["source_kind"] == "jooq"]
    assert len(joins) == 1
    assert [(pair["left"]["column_name"], pair["right"]["column_name"]) for pair in joins[0]["column_pairs"]] == [
        ("customer_id", "id"),
        ("namespace", "namespace"),
    ]
    assert joins[0]["matched_declared_keys"][0]["key_id"] == "pk_customers"
    lookups = [item for item in result["keys"] if item["key_kind"] == "lookup_key_usage"]
    assert len(lookups) == 1
    assert [column["column_name"] for column in lookups[0]["columns"]] == ["external_id"]
