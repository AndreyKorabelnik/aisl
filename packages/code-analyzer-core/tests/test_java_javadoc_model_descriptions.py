from pathlib import Path

from code_analyzer_core.scanners.java_persistence_lineage import (
    _attribute_occurrence_fact,
    _extract_java_attribute_containers,
    _java_type_declaration_and_inheritance_facts,
)
from code_analyzer_core.scanners.java_syntax import parse_java_text


JAVA = '''
package demo.model;

/**
 * People root model.
 * @name Person
 * @description Master person profile
 * @category PD
 */
@MetaRootEntity(id = "id")
public class Person {
    /**
     * @name Person identifier
     * @description Stable identifier
     */
    private String id;

    /** Human-readable name. */
    private String name;
}
'''


def test_tree_sitter_attaches_javadoc_to_class_and_fields() -> None:
    parsed = parse_java_text(JAVA)
    cls = parsed.classes[0]
    assert cls.documentation["display_name"] == "Person"
    assert cls.documentation["description"] == "Master person profile"
    fields = {field.name: field for field in cls.fields}
    assert fields["id"].documentation["display_name"] == "Person identifier"
    assert fields["id"].documentation["description"] == "Stable identifier"
    assert fields["name"].documentation["description"] == "Human-readable name."


def test_model_facts_publish_javadoc_descriptions(tmp_path: Path) -> None:
    source = tmp_path / "Person.java"
    source.write_text(JAVA, encoding="utf-8")
    containers = _extract_java_attribute_containers([source], model_annotation_contracts={"MetaRootEntity": "meta_entity"})
    assert len(containers) == 1
    container = containers[0]
    assert container["display_name"] == "Person"
    assert container["description"] == "Master person profile"
    id_field = next(field for field in container["fields"] if field["name"] == "id")
    fact = _attribute_occurrence_fact("attribute_occurrence_1", ctx={}, container=container, field=id_field)
    assert fact.properties["display_name"] == "Person identifier"
    assert fact.properties["description"] == "Stable identifier"

    declaration_facts, _ = _java_type_declaration_and_inheritance_facts([source], ctx={})
    declaration = next(f for f in declaration_facts if f.fact_type == "java_type_declaration")
    assert declaration.properties["display_name"] == "Person"
    assert declaration.properties["description"] == "Master person profile"
