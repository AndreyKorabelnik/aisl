from pathlib import Path

from code_analyzer_core.scanners.gradle_scanner import scan_gradle_dependencies
from code_analyzer_core.scanners.java_module_resolution import build_java_module_resolution_facts


def test_gradle_aware_cross_module_type_and_call_resolution(tmp_path: Path):
    (tmp_path / 'settings.gradle').write_text("rootProject.name='demo'\ninclude ':app', ':api'\n")
    (tmp_path / 'build.gradle').write_text('')
    app = tmp_path / 'app'
    api = tmp_path / 'api'
    app.mkdir(); api.mkdir()
    (app / 'build.gradle').write_text("dependencies { implementation project(':api') }\n")
    (api / 'build.gradle').write_text('')
    app_java = app / 'src/main/java/demo/app/Controller.java'
    api_java = api / 'src/main/java/demo/api/ClientApi.java'
    app_java.parent.mkdir(parents=True); api_java.parent.mkdir(parents=True)
    api_java.write_text('package demo.api; public class ClientApi { public String load(String id) { return id; } }')
    app_java.write_text('package demo.app; import demo.api.ClientApi; public class Controller { private ClientApi api; public String get(String id) { return api.load(id); } }')
    files = [p for p in tmp_path.rglob('*') if p.is_file()]
    gradle, _ = scan_gradle_dependencies(files)
    facts, status = build_java_module_resolution_facts(files, gradle)
    assert status['status'] == 'success'
    type_facts = [f for f in facts if f.fact_type == 'cross_module_type_resolution_observation']
    call_facts = [f for f in facts if f.fact_type == 'cross_module_call_resolution_observation']
    boundaries = [f for f in facts if f.fact_type == 'module_boundary_interaction_observation']
    assert any(f.properties['target_fqcn'] == 'demo.api.ClientApi' for f in type_facts)
    assert any(f.properties['callee_operation'] == 'ClientApi.load' for f in call_facts)
    assert any(f.properties['internal_external_classification'] == 'internal_project_module' for f in boundaries)
