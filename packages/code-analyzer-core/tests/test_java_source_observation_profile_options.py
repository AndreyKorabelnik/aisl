import json
from pathlib import Path

import yaml

from code_analyzer_core.java_analysis import run_java_analysis


def _profile(tmp_path: Path, framework_interpreters: list[str] | None) -> Path:
    path = tmp_path / "profile.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "profile_id": "source-observation-option-test",
                "profile_version": 1,
                "pipeline": {
                    "stages": [
                        {"id": "scan_files"},
                        {"id": "config_scan"},
                        {"id": "java_structural_scan"},
                        (
                            {
                                "id": "java_source_observation_build",
                                "options": {"framework_interpreters": framework_interpreters},
                            }
                            if framework_interpreters is not None
                            else {"id": "java_source_observation_build"}
                        ),
                        {"id": "core_output"},
                        {"id": "normalize_facts"},
                        {"id": "compact_package"},
                    ]
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return path


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    source = repo / "src/main/java/example/Sample.java"
    source.parent.mkdir(parents=True)
    source.write_text(
        '''package example;
        class Sample {
          String buildKey(Customer customer) {
            String key = "Customer_" + customer.getId();
            return key;
          }
        }
        class Customer { String getId() { return "1"; } }
        ''',
        encoding="utf-8",
    )
    return repo


def test_generic_source_observation_profile_does_not_run_tsa_interpreter(tmp_path):
    out = tmp_path / "analysis"
    run_java_analysis(
        _repo(tmp_path),
        out,
        repo_id="sample",
        analysis_profile=_profile(tmp_path, []),
    )

    source_status = json.loads(
        (out / "diagnostics/java_source_observation_status.json").read_text()
    )
    tsa_status = json.loads(
        (out / "diagnostics/tsa_interpreter_status.json").read_text()
    )
    manifest = json.loads((out / "facts/full_fact_manifest.json").read_text())

    assert source_status["framework_interpreters"] == []
    assert source_status["tsa_observations_emitted"] == 0
    assert tsa_status["requested"] is False
    assert not any(name.startswith("tsa_") for name in manifest["fact_types"])
    assert manifest["fact_types"]["constructed_value_observation"] >= 1


def test_repository_source_observation_profile_can_enable_tsa_interpreter(tmp_path):
    out = tmp_path / "analysis"
    run_java_analysis(
        _repo(tmp_path),
        out,
        repo_id="sample",
        analysis_profile=_profile(tmp_path, ["tsa"]),
    )

    source_status = json.loads(
        (out / "diagnostics/java_source_observation_status.json").read_text()
    )
    tsa_status = json.loads(
        (out / "diagnostics/tsa_interpreter_status.json").read_text()
    )

    assert source_status["framework_interpreters"] == ["tsa"]
    assert tsa_status["requested"] is True


def test_source_observation_stage_is_framework_neutral_by_default(tmp_path):
    out = tmp_path / "analysis"
    run_java_analysis(
        _repo(tmp_path),
        out,
        repo_id="sample",
        analysis_profile=_profile(tmp_path, None),
    )

    source_status = json.loads(
        (out / "diagnostics/java_source_observation_status.json").read_text()
    )
    tsa_status = json.loads(
        (out / "diagnostics/tsa_interpreter_status.json").read_text()
    )

    assert source_status["framework_interpreters"] == []
    assert tsa_status["requested"] is False
