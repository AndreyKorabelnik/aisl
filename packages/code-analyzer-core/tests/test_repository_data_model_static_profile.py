from pathlib import Path

import pytest

from code_analyzer_core.analysis_profiles import load_analysis_profile, profile_stage_ids
from code_analyzer_core.scanners.java_persistence_lineage import _extract_java_attribute_containers
from code_analyzer_core.scanners.java_syntax import tree_sitter_available


def test_repository_data_model_static_profile_is_generic_and_bounded():
    path = Path(__file__).parents[1] / "analysis-profiles" / "repository-data-model-static.yaml"
    text = path.read_text(encoding="utf-8")
    profile = load_analysis_profile(path)
    assert profile["profile_id"] == "repository-data-model-static"
    assert "ucp" not in text.lower()
    stages = profile_stage_ids(profile)
    assert stages == [
        "scan_files", "config_scan", "maven_dependency_scan", "gradle_dependency_scan", "java_structural_scan",
        "java_source_observation_build", "sql_scan", "db_schema_scan",
        "java_persistence_lineage_build", "java_data_model_lineage_build",
        "java_table_observation_build", "core_output", "normalize_facts", "compact_package",
    ]
    source_stage = next(
        item for item in profile["pipeline"]["stages"]
        if isinstance(item, dict) and item.get("id") == "java_source_observation_build"
    )
    assert source_stage["options"]["framework_interpreters"] == ["tsa"]
    forbidden = {"java_field_flow_build", "java_traceability_build", "declared_value_scan"}
    assert forbidden.isdisjoint(stages)


def _require_tree_sitter():
    ok, detail = tree_sitter_available()
    if not ok:
        pytest.skip(detail)


def test_model_annotation_contracts_are_extensible_without_project_switch(tmp_path):
    _require_tree_sitter()
    src = tmp_path / "src/main/java/example/model/Customer.java"
    src.parent.mkdir(parents=True)
    src.write_text(
        "package example.model; @BusinessObject public class Customer { private String id; }",
        encoding="utf-8",
    )
    containers = _extract_java_attribute_containers(
        [src], model_annotation_contracts={"BusinessObject": "meta_entity"}
    )
    customer = next(item for item in containers if item["container_name"] == "Customer")
    assert customer["container_kind"] == "meta_entity"
    assert customer["model_annotation"] == "BusinessObject"


def test_project_annotation_has_no_default_semantics(tmp_path):
    _require_tree_sitter()
    src = tmp_path / "src/main/java/example/model/Customer.java"
    src.parent.mkdir(parents=True)
    src.write_text(
        "package example.model; @MetaEntity public class Customer { private String id; }",
        encoding="utf-8",
    )
    containers = _extract_java_attribute_containers([src])
    customer = next(item for item in containers if item["container_name"] == "Customer")
    assert customer["container_kind"] == "java_class"
    assert customer["model_annotation"] is None
