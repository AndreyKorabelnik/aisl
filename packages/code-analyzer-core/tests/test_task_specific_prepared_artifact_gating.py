from pathlib import Path

from code_analyzer_core.pipeline import run_analysis


ROOT = Path(__file__).resolve().parents[1]


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    source = repo / "src/main/java/example/Customer.java"
    source.parent.mkdir(parents=True)
    source.write_text(
        "package example; public class Customer { private String id; public String getId(){ return id; } }",
        encoding="utf-8",
    )
    return repo


def test_data_model_profile_does_not_build_unrequested_task_artifacts(tmp_path: Path):
    out = tmp_path / "out"
    run_analysis(
        repo_path=_repo(tmp_path),
        out_dir=out,
        project_code="TEST",
        system_name="test",
        analysis_profile=ROOT / "analysis-profiles/repository-system-data-model.yaml",
        repo_id="test",
    )
    assert not (out / "diagnostics/system_description_enrichment_status.json").exists()
    assert not (out / "diagnostics/reference_data_fact_base_status.json").exists()
    assert not (out / "compact/reference_data_fact_base.json").exists()
    assert not (out / "compact/code_conceptual_model.json").exists()
    assert not (out / "diagnostics/code_conceptual_model_status.json").exists()

