from pathlib import Path

from code_analyzer_core.models import Fact
import code_analyzer_core.scanners.java_trace_builder as trace_builder


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_data_model_lineage_reuses_prebuilt_persistence_facts_without_rebuilding(tmp_path: Path, monkeypatch):
    src = _write(tmp_path / "src" / "main" / "java" / "Profile.java", """
        class ProfileDto { private String stateCode; }
        class ProfileEntity { private String stateCode; }
        class ProfileService {
          ProfileEntity map(ProfileDto dto) {
            ProfileEntity e = new ProfileEntity();
            e.setStateCode(dto.getStateCode());
            return e;
          }
        }
    """)
    persistence_fact = Fact(
        fact_type="persistent_write",
        name="repository.save",
        properties={
            "persistent_write_id": "persistent_write_000001",
            "operation": "ProfileService.save",
            "saved_object": "ProfileEntity",
            "storage_target": "profile",
            "storage_kind": "database",
        },
        evidence=[],
    )

    def fail_rebuild(*args, **kwargs):  # pragma: no cover - only reached on regression
        raise AssertionError("persistence lineage should be reused, not rebuilt")

    monkeypatch.setattr(trace_builder, "build_java_persistence_lineage_facts", fail_rebuild)
    facts, status = trace_builder.build_java_data_model_lineage_facts(
        [src],
        project_code="AS001",
        system_name="as",
        repo_id="repo-a",
        repo_path=str(tmp_path),
        persistence_facts=[persistence_fact],
        persistence_status={"requested": True, "persistent_writes_extracted": 1},
    )

    assert status["reused_persistence_lineage"] is True
    assert any(f.fact_type == "persistent_write" for f in facts)
    assert status["persistence_lineage_status"]["persistent_writes_extracted"] == 1


def test_data_model_lineage_can_reuse_persistence_without_republishing_facts(tmp_path: Path, monkeypatch):
    src = _write(tmp_path / "src" / "main" / "java" / "Profile.java", """
        class ProfileEntity { private String stateCode; }
    """)
    persistence_fact = Fact(
        fact_type="storage_lineage_gap",
        name="field gap",
        properties={
            "storage_lineage_gap_id": "storage_lineage_gap_000001",
            "gap_kind": "field_mapping_not_resolved",
        },
        evidence=[],
    )

    def fail_rebuild(*args, **kwargs):  # pragma: no cover
        raise AssertionError("persistence lineage should be reused, not rebuilt")

    monkeypatch.setattr(trace_builder, "build_java_persistence_lineage_facts", fail_rebuild)
    facts, status = trace_builder.build_java_data_model_lineage_facts(
        [src],
        repo_id="repo-a",
        repo_path=str(tmp_path),
        persistence_facts=[persistence_fact],
        persistence_status={"requested": True},
        include_persistence_facts=False,
    )

    assert status["reused_persistence_lineage"] is True
    assert status["persistence_facts_included"] is False
    assert not any(f.fact_type == "storage_lineage_gap" for f in facts)
