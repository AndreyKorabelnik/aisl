from __future__ import annotations

import json
from pathlib import Path

from code_analyzer_core.pipeline import run_analysis
from code_evidence.commands import db_table_detail


def _make_profile(tmp_path: Path) -> Path:
    p = tmp_path / "profile.yaml"
    p.write_text(
        "\n".join([
            "profile_id: java-db-schema-test",
            "pipeline:",
            "  stages:",
            "    - id: scan_files",
            "    - id: java_structural_scan",
            "    - id: sql_scan",
            "    - id: db_schema_scan",
            "    - id: core_output",
            "    - id: normalize_facts",
            "    - id: compact_package",
            "",
        ]),
        encoding="utf-8",
    )
    return p


def _make_jooq_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    table_dir = repo / "src/main/java/com/acme/db/generated/tables"
    table_dir.mkdir(parents=True)
    (table_dir / "SampleObject.java").write_text(
        '''
package com.acme.db.generated.tables;
import org.jooq.*;
import org.jooq.impl.*;
import com.acme.db.generated.Keys;
import com.acme.db.generated.Indexes;
import com.acme.db.generated.tables.records.SampleObjectRecord;
public class SampleObject extends TableImpl<SampleObjectRecord> {
  public static final SampleObject SAMPLE_OBJECT = new SampleObject();
  public final TableField<SampleObjectRecord, Long> ID = createField(DSL.name("id"), SQLDataType.BIGINT.nullable(false), this, "Primary id");
  public final TableField<SampleObjectRecord, String> NAME = createField(DSL.name("name"), SQLDataType.VARCHAR(100), this, "Object name");
  public SampleObject() { this(DSL.name("sample_object"), null); }
  private SampleObject(Name alias, Table<SampleObjectRecord> aliased) { super(alias, null, aliased, null, DSL.comment("Sample object table"), TableOptions.table()); }
  public Schema getSchema() { return Public.PUBLIC; }
  public UniqueKey<SampleObjectRecord> getPrimaryKey() { return Keys.PK_SAMPLE_OBJECT; }
  public java.util.List<Index> getIndexes() { return java.util.Arrays.<Index>asList(Indexes.SAMPLE_OBJECT_NAME_IDX); }
}
''',
        encoding="utf-8",
    )
    gen = repo / "src/main/java/com/acme/db/generated"
    (gen / "Keys.java").write_text(
        '''
package com.acme.db.generated;
import org.jooq.*; import org.jooq.impl.*;
import com.acme.db.generated.tables.SampleObject;
class SampleObjectRecord {}
public class Keys {
  public static final UniqueKey<SampleObjectRecord> PK_SAMPLE_OBJECT = UniqueKeys0.PK_SAMPLE_OBJECT;
  private static class UniqueKeys0 {
    public static final UniqueKey<SampleObjectRecord> PK_SAMPLE_OBJECT = Internal.createUniqueKey(SampleObject.SAMPLE_OBJECT, "pk_sample_object", new TableField[] { SampleObject.SAMPLE_OBJECT.ID }, true);
  }
}
''',
        encoding="utf-8",
    )
    (gen / "Indexes.java").write_text(
        '''
package com.acme.db.generated;
import org.jooq.*; import org.jooq.impl.*;
import com.acme.db.generated.tables.SampleObject;
public class Indexes {
  public static final Index SAMPLE_OBJECT_NAME_IDX = Indexes0.SAMPLE_OBJECT_NAME_IDX;
  private static class Indexes0 {
    public static Index SAMPLE_OBJECT_NAME_IDX = Internal.createIndex("sample_object_name_idx", SampleObject.SAMPLE_OBJECT, new OrderField[] { SampleObject.SAMPLE_OBJECT.NAME }, false);
  }
}
''',
        encoding="utf-8",
    )
    return repo


def test_java_pipeline_db_schema_scan_writes_artifacts_facts_and_cli_views(tmp_path: Path) -> None:
    repo = _make_jooq_repo(tmp_path)
    profile = _make_profile(tmp_path)
    out = tmp_path / "analysis-output"

    run_analysis(
        repo,
        out,
        project_code="PRJ",
        system_name="sample-system",
        analysis_profile=profile,
        repo_id="repo_a",
    )

    tables = json.loads((out / "sql" / "db_schema_tables.json").read_text(encoding="utf-8"))
    columns = json.loads((out / "sql" / "db_schema_columns.json").read_text(encoding="utf-8"))
    status = json.loads((out / "diagnostics" / "db_schema_status.json").read_text(encoding="utf-8"))
    coverage = json.loads((out / "evidence_coverage.json").read_text(encoding="utf-8"))
    fact_summary = json.loads((out / "facts" / "fact_summary.json").read_text(encoding="utf-8"))

    assert coverage["stages"]["java_structural_scan"]["syntax_provider"] == "tree_sitter"
    assert coverage["stages"]["java_structural_scan"]["syntax_cache"]["cache_misses"] >= 1
    assert "cache_entries" in coverage["stages"]["java_structural_scan"]["syntax_cache"]
    assert tables[0]["table_name"] == "sample_object"
    assert {c["column_name"] for c in columns} == {"id", "name"}
    assert status["tables_extracted"] == 1
    assert fact_summary["facts_by_type"]["db_schema_table"] == 1
    assert fact_summary["facts_by_type"]["db_schema_column"] == 2

    payload = db_table_detail(out, "sample_object")
    assert payload["kind"] == "db-table-detail"
    assert payload["columns"]
