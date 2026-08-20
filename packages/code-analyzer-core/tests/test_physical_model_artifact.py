from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from code_analyzer_core.cli import app
from code_analyzer_core.physical_model import build_physical_model_artifact


PDM = '''<?xml version="1.0" encoding="UTF-8"?>
<?PowerDesigner Name="Fixture" Target="Hadoop Hive 1.0" signature="PDM_DATA_MODEL_XML" version="16.6"?>
<Model xmlns:a="attribute" xmlns:c="collection" xmlns:o="object">
<o:RootObject Id="o1"><c:Children><o:Model Id="o2">
<a:ObjectID>model-uuid</a:ObjectID><a:Name>Fixture model</a:Name><a:Code>fixture_model</a:Code>
<c:Packages><o:Package Id="p1"><a:Name>Business</a:Name><a:Code>business</a:Code>
<c:Tables>
<o:Table Id="t1"><a:ObjectID>t1-uuid</a:ObjectID><a:Name>Customer</a:Name><a:Code>customer</a:Code>
<c:Columns>
<o:Column Id="c1"><a:Name>Id</a:Name><a:Code>id</a:Code><a:DataType>string</a:DataType><a:Column.Mandatory>1</a:Column.Mandatory></o:Column>
<o:Column Id="c2"><a:Name>Status</a:Name><a:Code>status</a:Code><a:DataType>string</a:DataType></o:Column>
</c:Columns>
<c:Keys><o:Key Id="k1"><a:Name>PK Customer</a:Name><a:Code>pk_customer</a:Code><c:Key.Columns><o:Column Ref="c1"/></c:Key.Columns></o:Key></c:Keys>
<c:PrimaryKey><o:Key Ref="k1"/></c:PrimaryKey>
</o:Table>
<o:Table Id="t2"><a:ObjectID>t2-uuid</a:ObjectID><a:Name>Order</a:Name><a:Code>orders</a:Code>
<c:Columns><o:Column Id="c3"><a:Name>Customer Id</a:Name><a:Code>customer_id</a:Code><a:DataType>string</a:DataType></o:Column></c:Columns>
</o:Table>
</c:Tables>
<c:References><o:Reference Id="r1"><a:Name>Order customer</a:Name><a:Code>fk_order_customer</a:Code><a:Cardinality>0..*</a:Cardinality>
<c:ParentTable><o:Table Ref="t1"/></c:ParentTable><c:ChildTable><o:Table Ref="t2"/></c:ChildTable><c:ParentKey><o:Key Ref="k1"/></c:ParentKey>
<c:Joins><o:ReferenceJoin Id="j1"><c:Object1><o:Column Ref="c1"/></c:Object1><c:Object2><o:Column Ref="c3"/></c:Object2></o:ReferenceJoin></c:Joins>
</o:Reference></c:References>
</o:Package></c:Packages>
</o:Model></c:Children></o:RootObject>
</Model>
'''


def _write_fixture(path: Path) -> None:
    path.write_text(PDM, encoding="utf-8")


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def test_build_physical_model_artifact_extracts_typed_facts(tmp_path: Path) -> None:
    model = tmp_path / "fixture.pdm"
    output = tmp_path / "artifact"
    _write_fixture(model)

    result = build_physical_model_artifact(model_path=model, output_dir=output, source_id="fixture")

    assert result.counts == {
        "physical_model_table": 2,
        "physical_model_column": 3,
        "physical_model_key": 1,
        "physical_model_relationship": 1,
        "physical_model_gap": 0,
    }
    tables = _read_jsonl(output / "facts/physical_model_table.jsonl")
    assert tables[0]["package_code_path"] == ["business"]
    assert tables[0]["logical_identity"] == "business.customer"
    columns = _read_jsonl(output / "facts/physical_model_column.jsonl")
    assert columns[0]["column_code"] == "id"
    assert columns[0]["mandatory"] is True
    keys = _read_jsonl(output / "facts/physical_model_key.jsonl")
    assert keys[0]["key_kind"] == "primary"
    assert keys[0]["column_codes"] == ["id"]
    relationships = _read_jsonl(output / "facts/physical_model_relationship.jsonl")
    assert relationships[0]["resolution_status"] == "resolved"
    assert relationships[0]["parent_table_code"] == "customer"
    assert relationships[0]["child_table_code"] == "orders"
    assert relationships[0]["joins"][0]["parent_column_code"] == "id"
    assert relationships[0]["joins"][0]["child_column_code"] == "customer_id"


def test_physical_model_artifact_is_deterministic_except_created_at(tmp_path: Path) -> None:
    model = tmp_path / "fixture.pdm"
    _write_fixture(model)
    first = build_physical_model_artifact(model_path=model, output_dir=tmp_path / "one", source_id="fixture")
    second = build_physical_model_artifact(model_path=model, output_dir=tmp_path / "two", source_id="fixture")

    assert first.content_fingerprint == second.content_fingerprint
    for name in [
        "physical_model_table",
        "physical_model_column",
        "physical_model_key",
        "physical_model_relationship",
        "physical_model_gap",
    ]:
        assert (tmp_path / "one/facts" / f"{name}.jsonl").read_bytes() == (tmp_path / "two/facts" / f"{name}.jsonl").read_bytes()


def test_unresolved_relationship_reference_is_a_gap_not_a_failure(tmp_path: Path) -> None:
    model = tmp_path / "fixture.pdm"
    _write_fixture(model)
    model.write_text(PDM.replace('Ref="t2"', 'Ref="missing-table"', 1), encoding="utf-8")

    result = build_physical_model_artifact(model_path=model, output_dir=tmp_path / "artifact", source_id="fixture")

    assert result.counts["physical_model_gap"] == 1
    manifest = json.loads((tmp_path / "artifact/manifest.json").read_text(encoding="utf-8"))
    assert manifest["coverage"]["status"] == "partial"
    relationship = _read_jsonl(tmp_path / "artifact/facts/physical_model_relationship.jsonl")[0]
    assert relationship["resolution_status"] == "partial"


def test_cli_analyze_physical_model(tmp_path: Path) -> None:
    model = tmp_path / "fixture.pdm"
    _write_fixture(model)
    output = tmp_path / "artifact"

    result = CliRunner().invoke(app, [
        "analyze-physical-model",
        str(model),
        "--artifact-output",
        str(output),
        "--source-id",
        "fixture",
    ])

    assert result.exit_code == 0, result.output
    assert "tables=2" in result.output
    assert (output / "manifest.json").is_file()


def test_duplicate_column_codes_keep_distinct_pdm_fact_ids(tmp_path: Path) -> None:
    model = tmp_path / "fixture.pdm"
    _write_fixture(model)
    model.write_text(PDM.replace('<a:Code>status</a:Code>', '<a:Code>id</a:Code>'), encoding="utf-8")
    output = tmp_path / "artifact"

    build_physical_model_artifact(model_path=model, output_dir=output, source_id="fixture")

    columns = _read_jsonl(output / "facts/physical_model_column.jsonl")
    assert len(columns) == 3
    assert len({item["physical_model_column_id"] for item in columns}) == 3
