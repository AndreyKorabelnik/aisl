from __future__ import annotations

from pathlib import Path

from knowledge_layer_core import CORE_DDL
from prepared_knowledge_runtime import KnowledgeLayerQuery, connect_database, write_json
from knowledge_layer_core.evidence import execute_evidence_request, load_evidence_tool_catalog
from knowledge_layer_core.data_model_materialization import _build_build_dependency_marts, _load_source_observations


def _fact(fact_type: str, name: str, properties: dict) -> dict:
    return {
        "fact_id": properties.get("observation_id", f"{fact_type}-{name}"),
        "fact_type": fact_type,
        "name": name,
        "properties": properties,
        "evidence": [{"file_path": "build.gradle", "line_start": 1, "extractor": "gradle_source_declaration"}],
    }


def test_build_dependency_marts_and_queries(tmp_path: Path) -> None:
    root = tmp_path / "knowledge"
    root.mkdir()
    database = root / "knowledge-layer.duckdb"
    con = connect_database(database)
    con.execute(CORE_DDL)
    con.execute(
        """INSERT INTO workspace_build VALUES (
        'build-1','scope-1','data-model','','selection','0.10.2',
        'knowledge_layer_data_model_core/v1',current_timestamp,current_timestamp,'complete','{}','{}')"""
    )
    con.execute(
        """INSERT INTO workspace_repository VALUES (
        'repo-1','',NULL,'','fp','System','P','0.36.40','repository-system-data-model.yaml',
        'code_conceptual_model/v2','projection','{}','{}','{}')"""
    )
    rows = {
        "gradle_project_observation": [
            _fact("gradle_project_observation", "sample", {
                "observation_id": "project-1", "root_project_name": "sample", "root_directory": "/repo",
                "module_paths": [":", ":api", ":app"], "build_system": "gradle",
            })
        ],
        "gradle_module_observation": [
            _fact("gradle_module_observation", ":api", {
                "observation_id": "module-api", "module_path": ":api", "module_name": "api",
                "project_directory": "/repo/api", "build_file": "/repo/api/build.gradle",
                "build_system": "gradle", "declared_in_settings": True, "evidence_maturity_level": "confirmed",
            }),
            _fact("gradle_module_observation", ":app", {
                "observation_id": "module-app", "module_path": ":app", "module_name": "app",
                "project_directory": "/repo/app", "build_file": "/repo/app/build.gradle",
                "build_system": "gradle", "declared_in_settings": True, "evidence_maturity_level": "confirmed",
            }),
        ],
        "module_dependency_observation": [
            _fact("module_dependency_observation", ":app->:api", {
                "observation_id": "edge-1", "dependency_kind": "gradle_project",
                "source_module_path": ":app", "target_module_path": ":api",
                "configuration": "implementation", "scope": "implementation", "source_set": "main",
                "evidence_maturity_level": "confirmed",
            })
        ],
        "external_dependency": [
            _fact("external_dependency", "org.springframework:spring-web:6.2.1", {
                "observation_id": "dep-1", "dependency_kind": "gradle_artifact", "build_system": "gradle",
                "source_module_path": ":app", "configuration": "implementation", "scope": "implementation",
                "source_set": "main", "is_test_source": False, "group_id": "org.springframework",
                "artifact_id": "spring-web", "version": "6.2.1", "coordinate": "org.springframework:spring-web:6.2.1",
                "resolution_basis": "alias", "alias": "libs.springWeb", "evidence_maturity_level": "confirmed",
            })
        ],
        "gradle_plugin_observation": [
            _fact("gradle_plugin_observation", "org.springframework.boot", {
                "observation_id": "plugin-1", "module_path": ":app", "plugin_id": "org.springframework.boot",
                "version": "3.5.14", "application_kind": "plugins_block",
            })
        ],
    }
    for fact_type, facts in rows.items():
        _load_source_observations(con, "repo-1", fact_type, facts)
    counts = _build_build_dependency_marts(con)
    assert counts == {"projects": 1, "modules": 2, "dependencies": 2, "plugins": 1, "repositories": 0, "source_sets": 0}
    con.close()
    write_json(root / "knowledge-layer-manifest.json", {
        "schema_version": "knowledge_layer/v1", "scope_id": "scope-1", "scope_type": "repository",
        "repository_count": 1, "repository_ids": ["repo-1"], "database_path": "knowledge-layer.duckdb",
    })

    query = KnowledgeLayerQuery(root)
    assert "common.build-dependencies" in query.capabilities()
    assert query.list_modules()["total_count"] == 2
    edges = query.module_dependencies(source_module_path=":app")
    assert edges["total_count"] == 1
    assert edges["items"][0]["target_module_path"] == ":api"
    external = query.external_dependencies(source_module_path=":app")
    assert external["total_count"] == 1
    assert external["items"][0]["coordinate"] == "org.springframework:spring-web:6.2.1"
    neighborhood = query.module_neighborhood(":app", repo_id="repo-1")
    assert neighborhood["counts"] == {"modules": 1, "dependencies": 2, "plugins": 1}


def test_build_dependency_evidence_tools_are_capability_gated_and_executable(tmp_path: Path) -> None:
    root = tmp_path / "knowledge-tools"
    root.mkdir()
    database = root / "knowledge-layer.duckdb"
    con = connect_database(database)
    con.execute(CORE_DDL)
    con.execute("""INSERT INTO workspace_build VALUES (
        'build-1','scope-1','data-model','','selection','0.10.2',
        'knowledge_layer_data_model_core/v1',current_timestamp,current_timestamp,'complete','{}','{}')""")
    con.execute("""INSERT INTO workspace_repository VALUES (
        'repo-1','',NULL,'','fp','System','P','0.36.40','repository-system-data-model.yaml',
        'code_conceptual_model/v2','projection','{}','{}','{}')""")
    _load_source_observations(con, "repo-1", "gradle_module_observation", [
        _fact("gradle_module_observation", ":app", {
            "observation_id": "module-app", "module_path": ":app", "module_name": "app",
            "project_directory": "/repo/app", "build_file": "/repo/app/build.gradle",
            "build_system": "gradle", "declared_in_settings": True, "evidence_maturity_level": "confirmed",
        })
    ])
    _load_source_observations(con, "repo-1", "gradle_plugin_observation", [
        _fact("gradle_plugin_observation", "org.springframework.boot", {
            "observation_id": "plugin-1", "module_path": ":app", "plugin_id": "org.springframework.boot",
            "version": "3.5.14", "application_kind": "plugins_block",
        })
    ])
    _build_build_dependency_marts(con)
    con.close()
    write_json(root / "knowledge-layer-manifest.json", {
        "schema_version": "knowledge_layer/v1", "scope_id": "scope-1", "scope_type": "repository",
        "repository_count": 1, "repository_ids": ["repo-1"], "database_path": "knowledge-layer.duckdb",
        "capabilities": ["common.build-dependencies"],
    })

    catalog = {item["command_id"]: item for item in load_evidence_tool_catalog()["tools"]}
    assert catalog["knowledge_layer_build_modules"]["required_capabilities"] == ["common.build-dependencies"]
    assert catalog["knowledge_layer_module_neighborhood"]["query_method"] == "module_neighborhood"
    modules = execute_evidence_request(
        {"command_id": "knowledge_layer_build_modules", "arguments": {}},
        knowledge_layer_path=root,
    )
    assert modules["total_count"] == 1
    neighborhood = execute_evidence_request(
        {"command_id": "knowledge_layer_module_neighborhood", "arguments": {"module_path": ":app"}},
        knowledge_layer_path=root,
    )
    assert neighborhood["counts"] == {"modules": 1, "dependencies": 0, "plugins": 1}


def test_empty_build_tables_do_not_advertise_build_dependency_capability(tmp_path: Path) -> None:
    root = tmp_path / "empty-build-knowledge"
    root.mkdir()
    database = root / "knowledge-layer.duckdb"
    con = connect_database(database)
    con.execute(CORE_DDL)
    con.close()
    write_json(root / "knowledge-layer-manifest.json", {
        "schema_version": "knowledge_layer/v1", "scope_id": "scope-empty", "scope_type": "repository",
        "repository_count": 1, "repository_ids": ["repo-1"], "database_path": "knowledge-layer.duckdb",
    })
    assert "common.build-dependencies" not in KnowledgeLayerQuery(root).capabilities()
