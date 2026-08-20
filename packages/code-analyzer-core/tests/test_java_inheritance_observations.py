from pathlib import Path

from code_analyzer_core.scanners.java_trace_builder import build_java_data_model_lineage_facts


def _write(root: Path, rel: str, text: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _props(facts, kind):
    return [f.properties for f in facts if f.fact_type == kind]


def test_repository_wide_inheritance_graph_resolves_multiple_lexical_forms(tmp_path: Path):
    files = [
        _write(tmp_path, "src/main/java/a/Base.java", "package a; public abstract class Base<T> { T value; }"),
        _write(tmp_path, "src/main/java/a/Mid.java", "package a; public class Mid extends Base<String> {}"),
        _write(tmp_path, "src/main/java/b/Marker.java", "package b; public interface Marker {}"),
        _write(tmp_path, "src/main/java/c/Child.java", "package c; import a.Mid; import b.*; public class Child extends Mid implements Marker {}"),
    ]
    facts, status = build_java_data_model_lineage_facts(files, repo_id="repo", repo_path=str(tmp_path))
    declarations = _props(facts, "java_type_declaration")
    edges = _props(facts, "java_inheritance_observation")
    assert {x["fqcn"] for x in declarations} == {"a.Base", "a.Mid", "b.Marker", "c.Child"}
    mid = next(x for x in edges if x["child_fqcn"] == "a.Mid")
    assert mid["resolved_parent_fqcn"] == "a.Base"
    assert mid["resolution_kind"] == "same_package"
    child_extends = next(x for x in edges if x["child_fqcn"] == "c.Child" and x["relation_kind"] == "extends")
    assert child_extends["resolved_parent_fqcn"] == "a.Mid"
    assert child_extends["resolution_kind"] == "explicit_import"
    child_impl = next(x for x in edges if x["child_fqcn"] == "c.Child" and x["relation_kind"] == "implements")
    assert child_impl["resolved_parent_fqcn"] == "b.Marker"
    assert child_impl["resolution_kind"] == "wildcard_import"
    assert status["java_type_declarations_extracted"] == 4
    assert status["java_inheritance_observations_extracted"] == 3


def test_ambiguous_and_external_parents_are_retained(tmp_path: Path):
    files = [
        _write(tmp_path, "src/main/java/a/Common.java", "package a; public class Common {}"),
        _write(tmp_path, "src/main/java/b/Common.java", "package b; public class Common {}"),
        _write(tmp_path, "src/main/java/c/Ambiguous.java", "package c; public class Ambiguous extends Common {}"),
        _write(tmp_path, "src/main/java/c/External.java", "package c; public class External extends vendor.ExternalBase {}"),
    ]
    facts, status = build_java_data_model_lineage_facts(files, repo_id="repo", repo_path=str(tmp_path))
    edges = _props(facts, "java_inheritance_observation")
    ambiguous = next(x for x in edges if x["child_fqcn"] == "c.Ambiguous")
    assert ambiguous["resolution_kind"] == "ambiguous"
    assert ambiguous["candidate_parent_fqcns"] == ["a.Common", "b.Common"]
    assert ambiguous["resolved"] is False
    external = next(x for x in edges if x["child_fqcn"] == "c.External")
    assert external["resolution_kind"] == "unresolved"
    assert external["declared_parent_reference"] == "vendor.ExternalBase"
    assert status["java_inheritance_ambiguous"] == 1
    assert status["java_inheritance_unresolved"] == 1


def test_inheritance_cycle_is_observed_without_verdict(tmp_path: Path):
    files = [
        _write(tmp_path, "src/main/java/x/A.java", "package x; public class A extends B {}"),
        _write(tmp_path, "src/main/java/x/B.java", "package x; public class B extends A {}"),
    ]
    facts, status = build_java_data_model_lineage_facts(files, repo_id="repo", repo_path=str(tmp_path))
    edges = _props(facts, "java_inheritance_observation")
    assert all(x["cycle_observed"] is True for x in edges)
    assert status["java_inheritance_cycle_nodes"] == 2
    assert not any("confidence" in x or "verdict" in x for x in edges)


def test_transitive_descendants_are_published_with_paths(tmp_path: Path):
    files = [
        _write(tmp_path, "src/main/java/a/Base.java", "package a; public abstract class Base {}"),
        _write(tmp_path, "src/main/java/a/Mid.java", "package a; public class Mid extends Base {}"),
        _write(tmp_path, "src/main/java/a/Leaf.java", "package a; public class Leaf extends Mid {}"),
    ]
    facts, status = build_java_data_model_lineage_facts(files, repo_id="repo", repo_path=str(tmp_path))
    descendants = _props(facts, "java_type_descendant_observation")
    base_leaf = next(x for x in descendants if x["ancestor_fqcn"] == "a.Base" and x["descendant_fqcn"] == "a.Leaf")
    assert base_leaf["depth"] == 2
    assert base_leaf["direct"] is False
    assert base_leaf["inheritance_path"] == ["a.Base", "a.Mid", "a.Leaf"]
    assert base_leaf["relation_path"] == ["extends", "extends"]
    assert status["java_type_descendant_observations_extracted"] == 3


def test_bounded_entity_paths_record_cycles_and_terminal_stops(tmp_path: Path):
    files = [
        _write(tmp_path, "src/main/java/a/Entity.java", "package a; public @interface Entity {}"),
        _write(tmp_path, "src/main/java/a/A.java", "package a; @Entity public class A { B b; }"),
        _write(tmp_path, "src/main/java/a/B.java", "package a; @Entity public class B { A a; C c; }"),
        _write(tmp_path, "src/main/java/a/C.java", "package a; @Entity public class C { String value; }"),
    ]
    facts, status = build_java_data_model_lineage_facts(files, repo_id="repo", repo_path=str(tmp_path))
    paths = _props(facts, "bounded_entity_type_path_observation")
    cycle = next(x for x in paths if x["root_fqcn"] == "a.A" and x["field_path"] == ["b", "a"])
    terminal = next(x for x in paths if x["root_fqcn"] == "a.A" and x["field_path"] == ["b", "c"])
    assert cycle["stop_reason"] == "cycle"
    assert cycle["traversal_continues"] is False
    assert terminal["stop_reason"] == "no_observed_outgoing_association"
    assert terminal["type_path"] == ["a.A", "a.B", "a.C"]
    assert status["bounded_entity_type_path_observations_extracted"] >= 4
