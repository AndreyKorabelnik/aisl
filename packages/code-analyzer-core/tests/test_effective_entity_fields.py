from pathlib import Path
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
    path.write_text(text, encoding='utf-8')
    return path


def _effective(facts, owner):
    return [f.properties for f in facts if f.fact_type == 'effective_entity_field' and f.properties.get('effective_owner_fqcn') == owner]


def test_effective_fields_include_multi_level_inheritance_and_field_hiding(tmp_path: Path):
    files = [
        _write(tmp_path, 'src/main/java/m/Base.java', 'package m; public abstract class Base<T> { protected T value; protected String hidden; @jakarta.persistence.Transient String ignored; }'),
        _write(tmp_path, 'src/main/java/m/Mid.java', 'package m; public abstract class Mid<U> extends Base<java.util.List<U>> { protected String middle; }'),
        _write(tmp_path, 'src/main/java/m/Customer.java', 'package m; @MetaEntity public class Customer extends Mid<String> { private Long id; private Integer hidden; }'),
    ]
    facts, status = build_java_data_model_lineage_facts(files, repo_id='r', repo_path=str(tmp_path), model_annotation_contracts=META_CONTRACTS)
    rows = _effective(facts, 'm.Customer')
    by_name = {x['field_name']: x for x in rows}
    assert set(by_name) == {'id', 'hidden', 'middle', 'value', 'ignored'}
    assert by_name['hidden']['declared_in_fqcn'] == 'm.Customer'
    assert by_name['value']['declared_in_fqcn'] == 'm.Base'
    assert by_name['value']['effective_type'].replace(' ', '') == 'java.util.List<String>'
    assert by_name['value']['inheritance_path'] == ['m.Customer', 'm.Mid', 'm.Base']
    assert by_name['value']['inherited'] is True
    assert by_name['ignored']['model_exclusion_observed'] is True
    assert by_name['ignored']['model_exclusion_annotations'] == ['Transient']
    assert status['effective_entity_fields_excluded'] == 0
    assert status['effective_entity_fields_with_model_exclusion_annotation'] == 1


def test_effective_fields_are_projected_for_all_entity_types_not_named_examples(tmp_path: Path):
    files = [
        _write(tmp_path, 'src/main/java/domain/AbstractAsset.java', 'package domain; public abstract class AbstractAsset { protected java.util.Set<Tag> tags; }'),
        _write(tmp_path, 'src/main/java/domain/Tag.java', 'package domain; @MetaDictionary public class Tag { String code; }'),
        _write(tmp_path, 'src/main/java/domain/Product.java', 'package domain; @MetaRootEntity public class Product extends AbstractAsset { String sku; }'),
        _write(tmp_path, 'src/main/java/domain/Contract.java', 'package domain; @MetaVersionedEntity public class Contract extends AbstractAsset { String number; }'),
    ]
    facts, _ = build_java_data_model_lineage_facts(files, repo_id='r', repo_path=str(tmp_path), model_annotation_contracts=META_CONTRACTS)
    product = {x['field_name']: x for x in _effective(facts, 'domain.Product')}
    contract = {x['field_name']: x for x in _effective(facts, 'domain.Contract')}
    assert product['tags']['field_container_kind'] == 'collection'
    assert product['tags']['field_element_type'] == 'Tag'
    assert contract['tags']['declared_in_fqcn'] == 'domain.AbstractAsset'


def test_unresolved_external_parent_keeps_direct_fields_without_invention(tmp_path: Path):
    src = _write(tmp_path, 'src/main/java/d/Entity.java', 'package d; @MetaEntity public class Entity extends vendor.ExternalBase { String own; }')
    facts, status = build_java_data_model_lineage_facts([src], repo_id='r', repo_path=str(tmp_path), model_annotation_contracts=META_CONTRACTS)
    rows = _effective(facts, 'd.Entity')
    assert [x['field_name'] for x in rows] == ['own']
    assert status['effective_entity_field_unresolved_paths'] == 1


def test_static_field_filter_uses_tree_sitter_modifiers(tmp_path: Path):
    src = _write(
        tmp_path,
        'src/main/java/d/Entity.java',
        'package d; @MetaEntity public class Entity { static Related global; Related local; } class Related {}',
    )
    facts, _ = build_java_data_model_lineage_facts([src], repo_id='r', repo_path=str(tmp_path), model_annotation_contracts=META_CONTRACTS)
    rows = _effective(facts, 'd.Entity')
    assert [x['field_name'] for x in rows] == ['local']
    assert rows[0]['syntax_provider'] == 'tree_sitter'
