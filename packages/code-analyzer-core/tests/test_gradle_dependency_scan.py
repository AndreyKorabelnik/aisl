from __future__ import annotations

from pathlib import Path

from code_analyzer_core.scanners.gradle_scanner import scan_gradle_dependencies
from code_analyzer_core.scanners.repo_scanner import scan_files


def test_gradle_scanner_extracts_modules_project_edges_aliases_and_plugins(tmp_path: Path) -> None:
    (tmp_path / "settings.gradle").write_text(
        """include 'api',
        'app'
rootProject.name = 'sample'
""",
        encoding="utf-8",
    )
    (tmp_path / "build.gradle").write_text(
        """def springVer = "6.2.1"
ext {
  libs = [
    springWeb: "org.springframework:spring-web:${springVer}"
  ]
}
plugins { id "org.sonarqube" version "6.1.0" }
""",
        encoding="utf-8",
    )
    (tmp_path / "api").mkdir()
    (tmp_path / "api" / "build.gradle").write_text(
        """plugins { id 'java' }
dependencies { implementation libs.springWeb }
""",
        encoding="utf-8",
    )
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "build.gradle").write_text(
        """plugins { id 'org.springframework.boot' version '3.5.14' }
dependencies {
  implementation project(":api")
  testImplementation "org.junit.jupiter:junit-jupiter:5.11.0"
}
""",
        encoding="utf-8",
    )

    facts, status = scan_gradle_dependencies(scan_files(tmp_path))

    modules = {fact.properties["module_path"] for fact in facts if fact.fact_type == "gradle_module_observation"}
    assert modules == {":", ":api", ":app"}
    module_edges = [fact for fact in facts if fact.fact_type == "module_dependency_observation"]
    assert len(module_edges) == 1
    assert module_edges[0].properties["source_module_path"] == ":app"
    assert module_edges[0].properties["target_module_path"] == ":api"
    assert module_edges[0].properties["expression"] == 'project(":api")'
    external = [fact for fact in facts if fact.fact_type == "external_dependency"]
    assert {fact.properties["coordinate"] for fact in external} == {
        "org.springframework:spring-web:6.2.1",
        "org.junit.jupiter:junit-jupiter:5.11.0",
    }
    assert next(f for f in external if f.properties["artifact_id"] == "junit-jupiter").properties["is_test_source"] is True
    plugins = {(fact.name, fact.properties.get("version")) for fact in facts if fact.fact_type == "gradle_plugin_observation"}
    assert ("org.sonarqube", "6.1.0") in plugins
    assert ("org.springframework.boot", "3.5.14") in plugins
    assert status["modules_observed"] == 3
    assert status["module_dependencies_extracted"] == 1
    assert status["external_dependencies_extracted"] == 2


def test_gradle_scanner_keeps_dynamic_dependency_as_unresolved_observation(tmp_path: Path) -> None:
    (tmp_path / "settings.gradle.kts").write_text('rootProject.name = "sample"\n', encoding="utf-8")
    (tmp_path / "build.gradle.kts").write_text(
        """dependencies {
  implementation(providerFactory())
}
""",
        encoding="utf-8",
    )
    facts, status = scan_gradle_dependencies(scan_files(tmp_path))
    unresolved = [fact for fact in facts if fact.fact_type == "gradle_unresolved_dependency_observation"]
    assert len(unresolved) == 1
    assert unresolved[0].properties["evidence_maturity_level"] == "unresolved"
    assert status["unresolved_dependency_expressions"] == 1


def test_gradle_scanner_resolves_alias_with_inline_dependency_closure(tmp_path: Path) -> None:
    (tmp_path / "settings.gradle").write_text("rootProject.name = 'sample'\n", encoding="utf-8")
    (tmp_path / "dependencies.gradle").write_text(
        "ext.core = [\n  monitoringClient: 'com.example:monitoring-client:1.2.3'\n]\n",
        encoding="utf-8",
    )
    (tmp_path / "build.gradle").write_text(
        "apply from: 'dependencies.gradle'\ndependencies {\n  implementation(core.monitoringClient) {\n    exclude group: 'x'\n  }\n}\n",
        encoding="utf-8",
    )
    facts, status = scan_gradle_dependencies(scan_files(tmp_path))
    external = [fact for fact in facts if fact.fact_type == "external_dependency"]
    assert [fact.properties["coordinate"] for fact in external] == ["com.example:monitoring-client:1.2.3"]
    assert status["unresolved_dependency_expressions"] == 0
