from pathlib import Path

from code_analyzer_core.prepared_artifacts.persistence_lineage_evidence import (
    build_persistence_lineage_evidence,
)


def test_persistence_lineage_evidence_uses_typed_contract_without_task_semantics(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    source = repo / "src/main/java/demo/Repository.java"
    source.parent.mkdir(parents=True)
    source.write_text(
        """
        package demo;
        class Request { String id; }
        class Entity { String id; }
        class Repository {
          void save(Entity entity) {}
          Entity findById(String id) { return new Entity(); }
        }
        class Service {
          private final Repository repository = new Repository();
          void execute(Request request) {
            Entity entity = new Entity(); entity.id=request.id; repository.save(entity);
          }
          Entity load(String id) { return repository.findById(id); }
        }
        """,
        encoding="utf-8",
    )
    artifact = build_persistence_lineage_evidence(
        repository=repo,
        files=[source],
        repo_id="demo",
        output_root=tmp_path / "out",
        parameters={"persistence_depth": "standard", "max_depth": 4},
    )
    assert artifact["artifact_kind"] == "persistence-lineage-evidence"
    assert artifact["schema_version"] == "persistence-lineage-evidence/v1"
    assert "task_suite_profile_semantics" not in artifact["provenance"]
    assert "legacy_fallback" not in artifact["provenance"]
    assert {item["artifact_name"] for item in artifact["payload"]["artifacts"]} == {
        "source_to_storage_lineage.json",
        "storage_to_access_lineage.json",
        "persistent_writes.json",
        "storage_accesses.json",
        "storage_lineage_gaps.json",
        "stored_field_to_response_field_mappings.json",
    }
