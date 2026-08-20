from __future__ import annotations

import gc
from pathlib import Path

from code_analyzer_core.analysis_profiles import profile_stage_entries
from code_analyzer_core.prepared_artifacts.persistence_lineage_evidence import _profile


ROOT = Path(__file__).resolve().parents[1]


def test_typed_persistence_profile_enables_stage_local_runtime_guard() -> None:
    stage = next(item for item in profile_stage_entries(_profile(max_depth=7, deep=True)) if item.get("id") == "java_persistence_lineage_build")
    assert stage["options"]["deep"] is True
    assert stage["options"]["max_depth"] == 7
    assert stage["options"]["suspend_automatic_gc"] is True
    assert stage["options"]["progress_interval"] == 25

def test_run_analysis_does_not_suspend_gc_for_the_whole_pipeline(monkeypatch) -> None:
    import code_analyzer_core.pipeline as pipeline

    observed: dict[str, bool] = {}
    sentinel = object()

    def fake_impl(**kwargs):
        observed["inside"] = gc.isenabled()
        return sentinel

    monkeypatch.setattr(pipeline, "_run_analysis_impl", fake_impl)
    was_enabled = gc.isenabled()
    if not was_enabled:
        gc.enable()
    try:
        result = pipeline.run_analysis(
            repo_path=".",
            out_dir="./out",
            project_code="P",
            system_name="S",
            analysis_profile=_profile(max_depth=7, deep=True),
        )
        assert result is sentinel
        assert observed["inside"] is True
        assert gc.isenabled() is True
    finally:
        if not was_enabled:
            gc.disable()
