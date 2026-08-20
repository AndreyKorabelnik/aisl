from pathlib import Path

from code_analyzer_core.scanners.declared_value_scanner import scan_declared_values
from code_analyzer_core.python_analysis import run_python_analysis
from code_evidence import commands
from code_evidence.access import execute_evidence_request


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_declared_value_scan_detects_java_enum_map_yaml_csv_and_sql(tmp_path: Path):
    java = _write(tmp_path / "src" / "main" / "java" / "StateCodes.java", '''
package demo;
public enum StateCodes {
    ACTIVE("A", "Active"),
    BLOCKED("B", "Blocked");
}
class LocalMappings {
    static final java.util.Map<String, String> STATE_LABELS = java.util.Map.of(
        "A", "Active",
        "B", "Blocked"
    );
}
''')
    yaml = _write(tmp_path / "config" / "state-values.yaml", '''
stateValues:
  A: Active
  B: Blocked
''')
    csv = _write(tmp_path / "data" / "state_values.csv", "code,name\nA,Active\nB,Blocked\n")
    sql = _write(tmp_path / "sql" / "state_case.sql", "select case state_code when 'A' then 'Active' when 'B' then 'Blocked' end as state_name from object_table")

    facts, status = scan_declared_values([java, yaml, csv, sql])
    candidates = [f for f in facts if f.fact_type == "declared_value_set"]
    kinds = {f.properties["syntax_kind"] for f in candidates}

    assert status["value_sets_extracted"] >= 3
    assert "yaml_map" in kinds
    assert "csv_table" in kinds
    assert "sql_case_mapping" in kinds
    assert all(f.properties.get("declared_value_set_id", "").startswith("declared_value_set_") for f in candidates)


def test_python_analysis_exports_declared_value_sets_and_evidence_access(tmp_path: Path):
    repo = tmp_path / "repo"
    out = tmp_path / "analysis-output"
    _write(repo / "service.py", '''
STATE_LABELS = {
    "A": "Active",
    "B": "Blocked",
}
ALLOWED_STATES = ["A", "B"]
''')

    run_python_analysis(repo, out, project_code="GEN", system_name="generic-service")

    ref_compact = out / "compact" / "declared_value_sets.json"
    assert ref_compact.exists()
    ref_text = ref_compact.read_text(encoding="utf-8")
    assert "declared_value_set_" in ref_text
    assert "STATE_LABELS" in ref_text

    first_id = next(f.properties["declared_value_set_id"] for f in scan_declared_values([repo / "service.py"])[0] if f.fact_type == "declared_value_set")
    shown = commands.show(out, first_id)
    assert shown["hit_count"] >= 1

    listed = commands.declared_value_set(out, "STATE_LABELS")
    assert listed["hit_count"] >= 1

    via_api = execute_evidence_request(
        {"command_id": "declared_value_set", "arguments": {"token": "STATE_LABELS", "max_results": 5}},
        static_analysis_output=out,
    )
    assert via_api["hit_count"] >= 1
    assert via_api["hits"][0]["source_file"].endswith("declared_value_sets.jsonl")


def test_declared_value_set_ids_are_stable_when_unrelated_file_is_added(tmp_path: Path):
    target = _write(tmp_path / "src" / "main" / "python" / "values.py", 'CODES = {"A": "Alpha", "B": "Beta"}\n')
    facts1, _ = scan_declared_values([target])
    ids1 = {f.properties["name"]: f.properties["declared_value_set_id"] for f in facts1 if f.fact_type == "declared_value_set"}

    unrelated = _write(tmp_path / "src" / "main" / "python" / "aaa.py", 'OTHER = ["X", "Y"]\n')
    facts2, _ = scan_declared_values([unrelated, target])
    ids2 = {f.properties["name"]: f.properties["declared_value_set_id"] for f in facts2 if f.fact_type == "declared_value_set"}

    assert ids1["CODES"] == ids2["CODES"]


def test_sql_join_name_does_not_create_declared_value_set(tmp_path: Path):
    sql = _write(
        tmp_path / "src" / "main" / "resources" / "query.sql",
        "select o.id from object_table o join status_dictionary s on s.id = o.status_id",
    )
    facts, _ = scan_declared_values([sql])
    assert not [f for f in facts if f.fact_type == "declared_value_set"]


def test_source_set_and_truncation_are_observed_metadata(tmp_path: Path):
    test_file = _write(tmp_path / "src" / "test" / "python" / "values.py", 'VALUES = ["A", "B", "C"]\n')
    facts, status = scan_declared_values([test_file])
    value_set = next(f for f in facts if f.fact_type == "declared_value_set")
    assert value_set.properties["source_set"] == "test"
    assert value_set.properties["extraction_truncated"] is False
    assert status["semantic_classification_performed"] is False
