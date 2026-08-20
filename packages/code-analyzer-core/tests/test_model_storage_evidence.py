from pathlib import Path

from code_analyzer_core.prepared_artifacts.model_storage_evidence import build_model_storage_evidence


def test_model_storage_evidence_publishes_record_reference_and_key_lineage(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = repo / "src/main/java/example/Converter.java"
    source.parent.mkdir(parents=True)
    source.write_text('''package example;
class Converter {
  String convert(Parent parent, Writer parentWriter) {
    String parentKey = "Parent_" + parent.id();
    parentWriter.alias("example.Parent");
    parentWriter.key(parentKey);
    String ref = makeChild(parent.child(), "child", parentKey);
    parentWriter.referenceField("child", ref);
    parentWriter.replaceReferenceCollection("children", convertChildren(parent.children(), parentKey));
    return parentKey;
  }
  String makeChild(Child child, String fieldName, String parentKey) {
    String key = parentKey + "." + fieldName;
    Writer writer = createWriter();
    writer.alias("example.Child");
    writer.key(key);
    return key;
  }
  java.util.List<String> convertChildren(java.util.List<Child> children, String parentKey) {
    return java.util.List.of(makeCollectionChild(children.get(0), parentKey));
  }
  String makeCollectionChild(Child child, String parentKey) {
    String key = parentKey + ".children_" + child.id();
    Writer writer = createWriter();
    writer.alias("example.Child");
    writer.key(key);
    return key;
  }
  Writer createWriter() { return null; }
}
''', encoding="utf-8")
    artifact = build_model_storage_evidence(repository=repo, files=[source], repo_id="demo")
    assert artifact["artifact_kind"] == "model-storage-evidence"
    assert artifact["coverage"]["coverage_status"] == "complete"
    assert artifact["payload"]["storage_records"]
    assert artifact["payload"]["storage_references"]
    assert artifact["payload"]["storage_key_lineage"]
    assert all(
        not Path(ref["repository_relative_path"]).is_absolute()
        for section in artifact["payload"].values()
        for row in section
        for ref in row["source_refs"]
    )


def test_model_storage_evidence_is_not_applicable_without_framework_signature(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = repo / "src/main/java/example/Plain.java"
    source.parent.mkdir(parents=True)
    source.write_text('''package example; class Plain { void x(Writer w) { w.key("x"); } }''', encoding="utf-8")
    artifact = build_model_storage_evidence(repository=repo, files=[source], repo_id="plain")
    assert artifact["coverage"]["coverage_status"] == "not_applicable"
    assert all(not rows for rows in artifact["payload"].values())
