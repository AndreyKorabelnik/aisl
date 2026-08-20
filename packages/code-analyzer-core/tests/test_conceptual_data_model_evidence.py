from pathlib import Path

from code_analyzer_core.scanners.db_schema_scanner import scan_database_schema
from code_analyzer_core.scanners.java_scanner import scan_java_files
from code_analyzer_core.scanners.repo_scanner import scan_files
from code_analyzer_core.scanners.sql_scanner import scan_sql_files


def test_liquibase_yaml_schema_preserves_qualified_tables_and_reference_data(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    changelog = repo / "workplaces-db-migrations/src/main/resources/db/workplaces/workplaces.changelog-12.0.yaml"
    changelog.parent.mkdir(parents=True)
    changelog.write_text(
        """
databaseChangeLog:
  - changeSet:
      id: 12-1
      author: tester
      changes:
        - createTable:
            schemaName: workplaces
            tableName: petition_status
            remarks: Статусы заявок
            columns:
              - column:
                  name: id
                  type: varchar(32)
                  remarks: Код статуса
                  constraints:
                    primaryKey: true
                    primaryKeyName: petition_status_pkey
              - column:
                  name: name
                  type: varchar(255)
                  remarks: Наименование
        - insert:
            schemaName: workplaces
            tableName: petition_status
            columns:
              - column:
                  name: id
                  value: NEW
              - column:
                  name: name
                  value: Новая
""",
        encoding="utf-8",
    )

    db_schema = scan_database_schema(repo, scan_files(repo), repo_id="r", project_code="P", system_name="S")
    tables = db_schema["tables"]
    assert any(t["qualified_table_name"] == "workplaces.petition_status" for t in tables)
    cols = [c for c in db_schema["columns"] if c.get("qualified_table_name") == "workplaces.petition_status"]
    assert {c["column_name"] for c in cols} == {"id", "name"}
    assert db_schema["keys"][0]["qualified_table_name"] == "workplaces.petition_status"
    assert db_schema["literal_data_writes"][0]["qualified_table_name"] == "workplaces.petition_status"
    assert db_schema["literal_data_writes"][0]["operation"] == "insert"
    assert "reference_data" not in db_schema
    assert db_schema["literal_data_writes"][0]["values"]["id"]["value"] == "NEW"


def test_jpa_relationship_and_inheritance_facts(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    src = repo / "src/main/java/com/acme"
    src.mkdir(parents=True)
    (src / "Booking.java").write_text(
        """
package com.acme;
import jakarta.persistence.*;
@Entity
@Table(schema = "reservation", name = "booking")
@Inheritance(strategy = InheritanceType.SINGLE_TABLE)
@DiscriminatorColumn(name = "booking_type")
public class Booking {
  @ManyToOne(fetch = FetchType.LAZY, optional = false)
  @JoinColumn(name = "zone_id", referencedColumnName = "id", nullable = false)
  private Zone zone;
}
""",
        encoding="utf-8",
    )
    (src / "BookingSingle.java").write_text(
        """
package com.acme;
import jakarta.persistence.*;
@Entity
@DiscriminatorValue("SINGLE")
public class BookingSingle extends Booking {}
""",
        encoding="utf-8",
    )
    (src / "Zone.java").write_text("package com.acme; import jakarta.persistence.*; @Entity @Table(schema=\"reservation\", name=\"zone\") public class Zone { @Id Long id; }", encoding="utf-8")

    facts, schemas, interfaces, relations, mapper_facts, warnings = scan_java_files(scan_files(repo))
    by_type = {}
    for fact in facts:
        by_type.setdefault(fact.fact_type, []).append(fact)
    rel = by_type["jpa_relationship"][0]
    assert rel.properties["source_entity"] == "Booking"
    assert rel.properties["target_entity"] == "Zone"
    assert rel.properties["source_table_identity"]["qualified_table_name"] == "reservation.booking"
    assert rel.properties["join_columns"][0]["join_column"] == "zone_id"
    assert rel.properties["join_columns"][0]["nullable"] is False
    inheritance = [f for f in by_type["jpa_inheritance"] if f.name == "Booking"]
    assert inheritance[0].properties["discriminator_column"] == "booking_type"
    subtype = [f for f in by_type["jpa_inheritance"] if f.name == "BookingSingle"]
    assert subtype[0].properties["parent_class"] == "Booking"
    assert subtype[0].properties["discriminator_value"] == "SINGLE"


def test_rest_controller_implementation_uses_mapping_declared_on_interface(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    src = repo / "src/main/java/com/acme"
    src.mkdir(parents=True)
    (src / "BookingController.java").write_text(
        """
package com.acme;
import org.springframework.web.bind.annotation.*;
@RequestMapping("/v1/booking")
public interface BookingController {
  @PostMapping("/conferenceRoomBooking")
  BookingResponse create(@RequestBody BookingRequest request);
}
class BookingRequest { String zoneId; }
class BookingResponse { String id; }
""",
        encoding="utf-8",
    )
    (src / "BookingControllerImpl.java").write_text(
        """
package com.acme;
import org.springframework.web.bind.annotation.*;
@RestController
public class BookingControllerImpl implements BookingController {
  public BookingResponse create(BookingRequest request) { return new BookingResponse(); }
}
""",
        encoding="utf-8",
    )
    facts, schemas, interfaces, relations, mapper_facts, warnings = scan_java_files(scan_files(repo))
    inbound = [i for i in interfaces if i.path == "/v1/booking/conferenceRoomBooking" and i.properties.get("boundary_role") == "rest_request"]
    assert inbound
    assert inbound[0].schema_ref == "BookingRequest"
    assert inbound[0].properties["declared_on_interface"] == "BookingController"


def test_sql_join_is_observed_without_reference_data_classification(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    sql = repo / "src/main/resources/query.sql"
    sql.parent.mkdir(parents=True)
    sql.write_text(
        """
select b.id, z.id
from reservation.booking b
join reservation.zone z on z.id = b.zone_id;
""",
        encoding="utf-8",
    )
    facts, summary, warnings = scan_sql_files(scan_files(repo))
    joins = [f for f in facts if f.fact_type == "sql_join_observation"]
    assert joins
    assert joins[0].properties["observation_kind"] == "native_sql_join_usage"
    assert joins[0].properties["observation_status"] == "extracted"
    assert "relationship_confidence" not in joins[0].properties


def test_sql_literal_insert_and_update_are_observed_facts(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    sql = repo / "src/main/resources/db/migration/V1__values.sql"
    sql.parent.mkdir(parents=True)
    sql.write_text(
        "insert into public.state_values(code, label) values ('A', 'Active'), ('B', 'Blocked');\n"
        "update public.state_values set label = 'Enabled' where code = 'A';\n",
        encoding="utf-8",
    )
    facts, summary, warnings = scan_sql_files(scan_files(repo))
    writes = [f for f in facts if f.fact_type == "literal_data_write"]
    assert len(writes) == 2
    insert = next(f for f in writes if f.properties["operation"] == "insert")
    update = next(f for f in writes if f.properties["operation"] == "update")
    assert insert.properties["qualified_table_name"] == "public.state_values"
    assert insert.properties["rows_count"] == 2
    assert insert.properties["rows"][0]["by_column"]["code"]["value"] == "A"
    assert insert.properties["source_set"] == "migration"
    assert update.properties["assignments"][0]["column"] == "label"
    assert update.properties["assignments"][0]["value"]["value"] == "Enabled"
    assert update.properties["where_expression"] == "code = 'A'"
    assert summary["literal_data_writes"] == 2


def test_check_constraint_preserves_literal_values(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    ddl = repo / "src/main/resources/schema.sql"
    ddl.parent.mkdir(parents=True)
    ddl.write_text(
        "create table public.object_state (id bigint primary key, status varchar(20) check (status in ('ACTIVE', 'BLOCKED')));",
        encoding="utf-8",
    )
    schema = scan_database_schema(repo, scan_files(repo), repo_id="r", project_code="P", system_name="S")
    checks = [x for x in schema["constraints"] if x.get("constraint_kind") == "check"]
    assert checks
    assert [x["value"] for x in checks[0]["literal_values"]] == ["ACTIVE", "BLOCKED"]
