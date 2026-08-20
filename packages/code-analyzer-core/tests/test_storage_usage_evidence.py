from pathlib import Path

from code_analyzer_core.prepared_artifacts.storage_usage_evidence import build_storage_usage_evidence


def test_storage_usage_evidence_observes_reads_writes_and_gaps(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = repo / "src/main/java/demo/Service.java"
    source.parent.mkdir(parents=True)
    source.write_text("""
package demo;
class Service {
  CustomerRepository repository;
  void work(Customer customer) {
    repository.save(customer);
    repository.findById(customer.getId());
    repository.deleteById(customer.getId());
  }
}
""", encoding="utf-8")
    artifact = build_storage_usage_evidence(repository=repo, files=[source], repo_id="demo")
    assert artifact["artifact_kind"] == "storage-usage-evidence"
    payload = artifact["payload"]
    assert {item["access_kind"] for item in payload["storage_accesses"]} == {"read", "write", "mutation"}
    assert len(payload["storage_reads"]) == 1
    assert len(payload["storage_writes"]) == 2
    assert all(not Path(item["source_ref"]["repository_relative_path"]).is_absolute() for item in payload["storage_accesses"])
    assert payload["storage_usage_gaps"] == []
    assert artifact["coverage"]["coverage_status"] == "complete"
