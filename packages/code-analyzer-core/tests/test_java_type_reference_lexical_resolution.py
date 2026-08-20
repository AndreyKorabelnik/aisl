from pathlib import Path

from code_analyzer_core.scanners.java_source_observations import build_java_source_observation_facts


def _write(root: Path, rel: str, text: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _field_reference(facts, owner: str, field: str):
    return next(
        fact.properties
        for fact in facts
        if fact.fact_type == "type_reference_observation"
        and fact.properties.get("owner_fqcn") == owner
        and fact.properties.get("reference_role") == "field_type"
        and fact.properties.get("member_name") == field
    )


def test_explicit_import_precedes_unrelated_workspace_simple_name_candidates(tmp_path: Path) -> None:
    files = [
        _write(tmp_path, "src/a/UserInfo.java", "package a; public class UserInfo {}"),
        _write(tmp_path, "src/b/UserInfo.java", "package b; public class UserInfo {}"),
        _write(tmp_path, "src/c/Owner.java", "package c; import a.UserInfo; public class Owner { UserInfo userInfo; }"),
    ]
    facts, _ = build_java_source_observation_facts(files)
    ref = _field_reference(facts, "c.Owner", "userInfo")
    assert ref["resolution"] == "explicit_import"
    assert ref["resolved_fqcn"] == "a.UserInfo"
    assert ref["candidate_fqcns"] == ["a.UserInfo"]


def test_same_package_precedes_unrelated_workspace_simple_name_candidates(tmp_path: Path) -> None:
    files = [
        _write(tmp_path, "src/a/UserInfo.java", "package a; public class UserInfo {}"),
        _write(tmp_path, "src/b/UserInfo.java", "package b; public class UserInfo {}"),
        _write(tmp_path, "src/b/Owner.java", "package b; public class Owner { UserInfo userInfo; }"),
    ]
    facts, _ = build_java_source_observation_facts(files)
    ref = _field_reference(facts, "b.Owner", "userInfo")
    assert ref["resolution"] == "same_package"
    assert ref["resolved_fqcn"] == "b.UserInfo"
    assert ref["candidate_fqcns"] == ["b.UserInfo"]
