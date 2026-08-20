from pathlib import Path

from code_analyzer_core.java_analysis import run_java_analysis
from code_evidence.commands import stored_data_access, read_from_storage, access_boundary, storage_to_access_lineage
from evidence_access_test_utils import assert_evidence_tool_registered


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _profile(path: Path) -> Path:
    p = path / "persistence-no-spoon.yaml"
    p.write_text(
        """
profile_id: persistence-no-spoon
profile_version: 1
pipeline:
  stages:
    - id: scan_files
    - id: config_scan
    - id: java_structural_scan
    - id: sql_scan
    - id: java_persistence_lineage_build
      options:
        max_depth: 4
    - id: core_output
    - id: normalize_facts
    - id: compact_package
""".strip(),
        encoding="utf-8",
    )
    return p


def test_stored_data_access_exposes_read_response_and_save_only(tmp_path: Path):
    repo = tmp_path / "repo"
    _write(repo / "src" / "main" / "java" / "DemoController.java", """
        package demo;
        import org.springframework.web.bind.annotation.*;
        @RestController
        class DemoController {
          private final DemoDao demoDao = null;
          @GetMapping("/objects/{id}")
          public DemoDto getObject(@PathVariable String id) {
            DemoDto dto = demoDao.findById(id);
            return dto;
          }
          @PostMapping("/objects")
          public void save(@RequestBody DemoDto dto) {
            demoDao.save(dto);
          }
        }
        class DemoDto { String objectId; String attributeA; }
        interface DemoDao { DemoDto findById(String id); void save(DemoDto dto); }
    """)
    analysis_out = tmp_path / "analysis-out"
    result = run_java_analysis(repo, analysis_out, repo_id="demo", analysis_profile=_profile(tmp_path))
    out = Path(result["analysis_out"])

    reads = read_from_storage(out, max_results=20)
    assert reads["hit_count"] >= 1

    boundaries = access_boundary(out, max_results=20)
    assert boundaries["hit_count"] >= 1

    links = storage_to_access_lineage(out, max_results=20)
    assert links["hit_count"] >= 1

    view = stored_data_access(out, max_results=20)
    assert view["counts"]["persistent_writes"] >= 1
    assert view["counts"]["read_from_storage"] >= 1
    assert view["counts"]["access_boundaries"] >= 1
    assert view["counts"]["storage_to_access_lineages"] >= 1
    scenario = view["stored_data_access"][0]
    assert scenario["access_side"]["read_evidence_ref"].startswith("read_from_storage_")
    assert scenario["access_side"]["access_evidence_ref"].startswith("access_boundary_")
    assert scenario["same_data_status"] in {"confirmed_same_data", "unresolved"}
    assert scenario["field_overlap"]


def test_stored_data_access_save_only_is_not_access_risk(tmp_path: Path):
    repo = tmp_path / "repo"
    _write(repo / "src" / "main" / "java" / "SaveService.java", """
        package demo;
        class SaveService {
          private final DemoDao demoDao = null;
          public void save(DemoDto dto) { demoDao.save(dto); }
        }
        class DemoDto { String objectId; String attributeA; }
        interface DemoDao { void save(DemoDto dto); }
    """)
    analysis_out = tmp_path / "analysis-out"
    result = run_java_analysis(repo, analysis_out, repo_id="demo", analysis_profile=_profile(tmp_path))
    out = Path(result["analysis_out"])

    view = stored_data_access(out, max_results=20)
    assert view["counts"]["persistent_writes"] >= 1
    assert view["counts"]["access_boundaries"] == 0
    assert view["stored_data_access"]
    assert view["stored_data_access"][0]["access_status"] == "no_access_found"

    for command_id in [
        "read_from_storage",
        "access_boundary",
        "storage_to_access_lineage",
        "stored_field_to_response_field_mapping",
        "stored_data_access",
    ]:
        assert_evidence_tool_registered(command_id)
