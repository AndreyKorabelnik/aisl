from pathlib import Path
from code_analyzer_core.scanners.java_syntax import parse_java_text, java_type_shape
from code_analyzer_core.scanners.java_trace_builder import build_java_data_model_lineage_facts


META_CONTRACTS = {
    "MetaRootEntity": "meta_entity",
    "MetaVersionedEntity": "meta_entity",
    "MetaEntity": "meta_entity",
    "MetaDictionary": "meta_dictionary",
    "MetaVersionedDictionary": "meta_dictionary",
}

def _write(root: Path, rel: str, text: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path



def test_tree_sitter_separates_superclass_interfaces_and_type_parameters():
    parsed = parse_java_text(
        "package d; public abstract class Child<T extends BaseValue> extends Parent<T> implements A<String>, x.B<Integer> {}"
    )
    cls = parsed.classes[0]
    assert cls.type_parameters == ("T",)
    assert cls.modifier_tokens == ("public", "abstract")
    assert cls.extends == "Parent<T>"
    assert cls.extends_base == "Parent"
    assert cls.extends_type_arguments == ("T",)
    assert cls.implements == ("A<String>", "x.B<Integer>")
    assert cls.implements_bases == ("A", "x.B")
    assert cls.implements_type_arguments == (("String",), ("Integer",))


def test_class_with_only_implements_has_no_false_superclass():
    parsed = parse_java_text("package d; public class Worker implements Runnable, AutoCloseable {}")
    cls = parsed.classes[0]
    assert cls.extends is None
    assert cls.extends_base is None
    assert cls.implements == ("Runnable", "AutoCloseable")


def test_effective_model_java_structure_has_no_regex_parser_fallback():
    from code_analyzer_core.scanners import java_persistence_lineage as lineage

    assert not hasattr(lineage, "_java_declared_type_parameters")
    assert not hasattr(lineage, "_java_supertype_arguments")
    assert not hasattr(lineage, "_java_type_reference_base")


def test_tree_sitter_type_shape_handles_nested_generics_and_arrays():
    shape = java_type_shape("java.util.Map<String, java.util.List<Phone[]>>")
    assert shape["base_type"] == "java.util.Map"
    assert shape["container_kind"] == "map"
    assert shape["type_references"] == ["java.util.Map", "String", "java.util.List", "Phone"]
    assert shape["map_value_type"] == "java.util.List<Phone[]>"
