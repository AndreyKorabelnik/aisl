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
    p=root/rel; p.parent.mkdir(parents=True,exist_ok=True); p.write_text(text,encoding='utf-8'); return p


def _assocs(facts, owner):
    return [f.properties for f in facts if f.fact_type=='effective_entity_association' and f.properties.get('effective_owner_fqcn')==owner]


def test_effective_associations_cover_all_inheriting_entities_and_supporting_abstract_targets(tmp_path: Path):
    files=[
        _write(tmp_path,'src/main/java/d/AbstractDocument.java','package d; public abstract class AbstractDocument { String number; }'),
        _write(tmp_path,'src/main/java/d/Passport.java','package d; @MetaEntity public class Passport extends AbstractDocument { String series; }'),
        _write(tmp_path,'src/main/java/d/AbstractParty.java','package d; public abstract class AbstractParty { java.util.List<Phone> phones; java.util.List<AbstractDocument> documents; }'),
        _write(tmp_path,'src/main/java/d/Phone.java','package d; @MetaVersionedEntity public class Phone { String value; }'),
        _write(tmp_path,'src/main/java/d/Customer.java','package d; @MetaRootEntity public class Customer extends AbstractParty { String id; }'),
        _write(tmp_path,'src/main/java/d/Company.java','package d; @MetaRootEntity public class Company extends AbstractParty { String reg; }'),
    ]
    facts,status=build_java_data_model_lineage_facts(files,repo_id='r',repo_path=str(tmp_path), model_annotation_contracts=META_CONTRACTS)
    customer=_assocs(facts,'d.Customer')
    company=_assocs(facts,'d.Company')
    assert {(x['source_field'],x['target_observed_fqcn']) for x in customer}=={('phones','d.Phone'),('documents','d.AbstractDocument')}
    assert {(x['source_field'],x['target_observed_fqcn']) for x in company}=={('phones','d.Phone'),('documents','d.AbstractDocument')}
    docs=next(x for x in customer if x['source_field']=='documents')
    assert docs['target_model_kind']=='observed_java_type'
    assert docs['conceptual_descendant_fqcns']==['d.Passport']
    assert docs['association_origin']=='inherited_field'
    assert status['effective_entity_associations_inherited']==4


def test_standard_scalar_types_do_not_become_associations_and_custom_external_is_retained(tmp_path: Path):
    src=_write(tmp_path,'src/main/java/d/Entity.java','package d; @MetaEntity public class Entity { String name; java.time.LocalDate date; vendor.ExternalValue external; }')
    facts,_=build_java_data_model_lineage_facts([src],repo_id='r',repo_path=str(tmp_path), model_annotation_contracts=META_CONTRACTS)
    rows=_assocs(facts,'d.Entity')
    assert len(rows)==1
    assert rows[0]['source_field']=='external'
    assert rows[0]['target_model_kind']=='unresolved_type'


def test_project_specific_metaignore_is_observed_but_not_interpreted_as_exclusion(tmp_path: Path):
    filler = " ".join(f"String field{i};" for i in range(20))
    files = [
        _write(tmp_path, 'src/main/java/d/Phone.java', 'package d; @MetaEntity public class Phone { String value; }'),
        _write(tmp_path, 'src/main/java/d/Address.java', 'package d; @MetaEntity public class Address { String value; }'),
        _write(
            tmp_path,
            'src/main/java/d/Customer.java',
            'package d; @MetaRootEntity public class Customer { '
            + filler
            + ' @MetaIgnore java.util.List<Phone> phones; @jakarta.persistence.Transient Address address; }',
        ),
    ]
    facts, status = build_java_data_model_lineage_facts(files, repo_id='r', repo_path=str(tmp_path), model_annotation_contracts=META_CONTRACTS)
    fields = {
        f.properties['field_name']: f.properties
        for f in facts
        if f.fact_type == 'effective_entity_field' and f.properties.get('effective_owner_fqcn') == 'd.Customer'
    }
    associations = {x['source_field']: x for x in _assocs(facts, 'd.Customer')}
    assert len(fields) == 22
    assert fields['phones']['model_exclusion_annotations'] == []
    assert fields['address']['model_exclusion_annotations'] == ['Transient']
    assert set(associations) == {'phones', 'address'}
    assert associations['phones']['target_observed_fqcn'] == 'd.Phone'
    assert associations['phones']['model_exclusion_observed'] is False
    assert associations['phones']['model_exclusion_annotations'] == []
    assert associations['phones']['syntax_provider'] == 'tree_sitter'
    assert associations['address']['target_observed_fqcn'] == 'd.Address'
    assert status['effective_entity_fields_with_model_exclusion_annotation'] == 1
