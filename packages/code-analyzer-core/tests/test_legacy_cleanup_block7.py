from __future__ import annotations

from pathlib import Path

from code_analyzer_core.analysis_profiles import load_analysis_profile, profile_stage_ids


ROOT = Path(__file__).resolve().parents[1]


def test_code_conceptual_model_producer_is_physically_removed() -> None:
    assert not (ROOT / "code_analyzer_core/prepared_artifacts/code_conceptual_model.py").exists()
    active = [ROOT / "code_analyzer_core", ROOT / "analysis-profiles"]
    for root in active:
        for path in root.rglob("*"):
            if path.is_file() and path.suffix in {".py", ".yaml", ".json"}:
                text = path.read_text(encoding="utf-8")
                assert "code_conceptual_model_build" not in text, path
                assert "code_conceptual_model_v2" not in text, path
                assert "code_conceptual_model/v2" not in text, path


def test_data_model_profiles_publish_evidence_not_umbrella() -> None:
    for name in ("repository-system-data-model.yaml", "repository-data-model-static.yaml"):
        profile = load_analysis_profile(ROOT / "analysis-profiles" / name)
        assert "code_conceptual_model_build" not in profile_stage_ids(profile)
        assert profile["output_contract"]["primary_interface"] == "evidence_access_api"
