from pathlib import Path

from code_analyzer_core.scanners.java_trace_builder import build_java_data_model_lineage_facts
from code_analyzer_core.models import Fact, EvidenceRef


META_CONTRACTS = {
    "MetaRootEntity": "meta_entity",
    "MetaVersionedEntity": "meta_entity",
    "MetaEntity": "meta_entity",
    "MetaDictionary": "meta_dictionary",
    "MetaVersionedDictionary": "meta_dictionary",
}

def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _props(facts, fact_type):
    return [f.properties for f in facts if f.fact_type == fact_type]


def test_data_model_lineage_extracts_jpa_structure_mapping_derivation_and_mapper_gap(tmp_path: Path):
    src = _write(tmp_path / "src" / "main" / "java" / "Profile.java", """
        import jakarta.persistence.*;
        @Entity
        @Table(name = "profile_state")
        class ProfileEntity {
          @Id
          @Column(name = "profile_id")
          private Long id;
          @Column(name = "state_code", nullable = false, unique = true)
          private String stateCode;
          @JoinColumn(name = "client_id", referencedColumnName = "id")
          @ManyToOne
          private ClientEntity client;
          private String ageGroup;
          public void setStateCode(String stateCode) {}
          public void setAgeGroup(String ageGroup) {}
        }
        @Entity
        @Table(name = "client")
        class ClientEntity { @Id private Long id; }
        class ProfileResponse {
          private String stateCode;
          private java.time.LocalDate birthDate;
          public String getStateCode() { return stateCode; }
          public java.time.LocalDate getBirthDate() { return birthDate; }
        }
        @org.mapstruct.Mapper
        interface ProfileMapper {
          @org.mapstruct.Mapping(source = "stateCode", target = "stateCode")
          ProfileEntity toEntity(ProfileResponse response);
        }
        interface ProfileRepository extends org.springframework.data.jpa.repository.JpaRepository<ProfileEntity, Long> {}
        class ProfileService {
          private final ProfileRepository repository;
          private final ProfileMapper mapper;
          void save(ProfileResponse response) {
            ProfileEntity entity = new ProfileEntity();
            entity.setStateCode(response.getStateCode());
            entity.setAgeGroup(calcAgeGroup(response.getBirthDate()));
            repository.save(mapper.toEntity(response));
          }
          String calcAgeGroup(java.time.LocalDate birthDate) { return "adult"; }
        }
    """)

    facts, status = build_java_data_model_lineage_facts([src], project_code="AS001", system_name="as", repo_id="fp-a", repo_path=str(tmp_path), model_annotation_contracts=META_CONTRACTS)

    structures = _props(facts, "persistent_structure")
    assert status["persistent_structures_extracted"] >= 1
    profile = next(x for x in structures if x.get("storage_target") == "profile_state")
    fields = {f["java_field"]: f for f in profile["fields"]}
    assert fields["id"]["storage_field"] == "profile_id"
    assert fields["id"]["key_role"] == "primary_key"
    assert fields["stateCode"]["storage_field"] == "state_code"
    assert fields["stateCode"]["nullable"] is False
    assert fields["stateCode"]["unique"] is True
    assert fields["client"]["key_role"] == "foreign_key"
    assert profile.get("source_repositories") == ["ProfileRepository"]

    mappings = _props(facts, "attribute_mapping")
    assert any(m.get("source_container") == "ProfileResponse" and m.get("source_field") == "stateCode" and m.get("target_container") == "ProfileEntity" and m.get("target_field") == "stateCode" for m in mappings)
    assert any(m.get("mapping_kind") == "mapper_annotation" and m.get("source_container") == "ProfileResponse" and m.get("target_container") == "ProfileEntity" for m in mappings)

    derivations = _props(facts, "attribute_derivation")
    assert any(d.get("target_field") == "ageGroup" and d.get("expression_kind") in {"expression_with_one_source_field", "method_call", "dictionary_lookup"} for d in derivations)

    lineages = _props(facts, "source_to_storage_lineage")
    assert any(l.get("assignment_kind") == "mapper_call" and l.get("gap_kind") == "save_payload_from_mapper_result" for l in lineages)
    gaps = _props(facts, "data_model_lineage_gap")
    assert any(g.get("gap_kind") == "save_payload_from_mapper_result" for g in gaps)




def test_meta_model_entities_with_same_simple_name_in_different_packages_remain_distinct(tmp_path: Path):
    meta = """
        package ru.sbrf.ucp.meta.annotations;
        public @interface MetaVersionedEntity { String id(); String version(); }
    """
    _write(tmp_path / "src/main/java/ru/sbrf/ucp/meta/annotations/MetaVersionedEntity.java", meta)
    first = _write(tmp_path / "src/main/java/com/acme/common/Consent.java", """
        package com.acme.common;
        import ru.sbrf.ucp.meta.annotations.MetaVersionedEntity;
        @MetaVersionedEntity(id = "id", version = "version")
        public class Consent { private Long id; private int version; }
    """)
    second = _write(tmp_path / "src/main/java/com/acme/retail/Consent.java", """
        package com.acme.retail;
        import ru.sbrf.ucp.meta.annotations.MetaVersionedEntity;
        @MetaVersionedEntity(id = "id", version = "version")
        public class Consent { private Long id; private int version; private String channel; }
    """)

    facts, status = build_java_data_model_lineage_facts(
        [first, second], project_code="UCP", system_name="ucp", repo_id="ucp-model", repo_path=str(tmp_path), model_annotation_contracts=META_CONTRACTS
    )

    structures = [
        p for p in _props(facts, "persistent_structure")
        if p.get("storage_kind") == "conceptual_model"
    ]
    assert status["persistent_structures_extracted"] == 2
    assert {p.get("container_fqcn") for p in structures} == {
        "com.acme.common.Consent",
        "com.acme.retail.Consent",
    }
    assert {p.get("storage_target") for p in structures} == {
        "com.acme.common.Consent",
        "com.acme.retail.Consent",
    }


def test_meta_model_entity_is_kept_as_conceptual_not_physical_structure(tmp_path: Path):
    src = _write(tmp_path / "src/main/java/com/acme/Party.java", """
        package com.acme;
        import ru.sbrf.ucp.meta.annotations.MetaRootEntity;
        @MetaRootEntity(id = "id")
        public class Party { private Long id; private String name; }
    """)

    facts, _status = build_java_data_model_lineage_facts(
        [src], project_code="UCP", system_name="ucp", repo_id="ucp-model", repo_path=str(tmp_path), model_annotation_contracts=META_CONTRACTS
    )

    structures = _props(facts, "persistent_structure")
    party = next(p for p in structures if p.get("container_fqcn") == "com.acme.Party")
    assert party["storage_kind"] == "conceptual_model"
    assert party["container_kind"] == "meta_entity"
    assert party["model_annotation"] == "MetaRootEntity"
    assert party["storage_target"] == "com.acme.Party"
    assert party["source_scope"] == "production_code"
    assert party["source_set"] == "production_code"
    assert party["is_test_source"] is False


def test_test_scoped_meta_model_type_is_not_materialized_as_workspace_structure(tmp_path: Path):
    production = _write(tmp_path / "src/main/java/com/acme/ProductionParty.java", """
        package com.acme;
        import ru.sbrf.ucp.meta.annotations.MetaEntity;
        @MetaEntity
        public class ProductionParty { private Long id; }
    """)
    test_fixture = _write(tmp_path / "src/test/java/com/acme/TestParty.java", """
        package com.acme;
        import ru.sbrf.ucp.meta.annotations.MetaEntity;
        @MetaEntity
        public class TestParty { private Long id; }
    """)

    facts, _status = build_java_data_model_lineage_facts(
        [production, test_fixture], project_code="UCP", system_name="ucp", repo_id="ucp-model", repo_path=str(tmp_path), model_annotation_contracts=META_CONTRACTS
    )

    structures = [p for p in _props(facts, "persistent_structure") if p.get("storage_kind") == "conceptual_model"]
    assert {p.get("container_fqcn") for p in structures} == {"com.acme.ProductionParty"}


def test_unresolved_write_expression_does_not_create_persistent_structure(tmp_path: Path):
    src = _write(tmp_path / "src/main/java/com/acme/Writer.java", """
        package com.acme;
        public class Writer { void write() {} }
    """)
    unresolved_write = Fact(
        fact_type="persistent_write",
        name="verify_write",
        properties={
            "saved_object": "getStorage",
            "storage_kind": "ignite",
            "storage_target": "verify_getStorage()",
        },
        evidence=[EvidenceRef(file_path=str(src), line_start=2)],
    )

    facts, _status = build_java_data_model_lineage_facts(
        [src], project_code="UCP", system_name="ucp", repo_id="writer", repo_path=str(tmp_path), model_annotation_contracts=META_CONTRACTS,
        persistence_facts=[unresolved_write], persistence_status={},
    )

    structures = _props(facts, "persistent_structure")
    assert not any(p.get("container_name") == "getStorage" for p in structures)
    assert not any(p.get("storage_target") == "verify_getStorage()" for p in structures)
    assert any(f.fact_type == "persistent_write" and f.name == "verify_write" for f in facts)


def test_test_only_write_does_not_materialize_production_saved_object(tmp_path: Path):
    production = _write(tmp_path / "src/main/java/com/acme/SchemaParams.java", """
        package com.acme;
        public class SchemaParams { private String typeName; }
    """)
    test_file = _write(tmp_path / "src/test/java/com/acme/SchemaLoaderTest.java", """
        package com.acme;
        public class SchemaLoaderTest { void save() {} }
    """)
    test_write = Fact(
        fact_type="persistent_write",
        name="test repository write",
        properties={
            "saved_object": "SchemaParams",
            "storage_kind": "storage",
            "storage_target": "repository",
            "source_scope": "test_code",
            "observation_source_scope": "test_code",
        },
        evidence=[EvidenceRef(file_path=str(test_file), line_start=2)],
    )

    facts, _status = build_java_data_model_lineage_facts(
        [production, test_file], project_code="UCP", system_name="ucp", repo_id="ucp", repo_path=str(tmp_path), model_annotation_contracts=META_CONTRACTS,
        persistence_facts=[test_write], persistence_status={},
    )

    structures = _props(facts, "persistent_structure")
    assert not any(p.get("container_fqcn") == "com.acme.SchemaParams" for p in structures)
    copied_write = next(f for f in facts if f.fact_type == "persistent_write")
    assert copied_write.properties.get("source_scope") == "test_code"
    assert copied_write.properties.get("observation_source_scope") == "test_code"


def test_plain_java_class_attribute_filter_uses_declared_type_role_not_business_field_name(tmp_path: Path):
    src = _write(tmp_path / "src" / "main" / "java" / "Sample.java", """
        class Sample {
          private MergeClientInfo mergeClientInfo;
          private String clientReference;
          private RemoteClient remoteClient;
          private CustomerRepository repository;
        }
        class MergeClientInfo {}
        class RemoteClient {}
        class CustomerRepository {}
    """)

    facts, _status = build_java_data_model_lineage_facts(
        [src],
        project_code="AS001",
        system_name="as",
        repo_id="fp-a",
        repo_path=str(tmp_path),
    )

    sample_fields = {
        p["attribute_name"]
        for p in _props(facts, "attribute_occurrence")
        if p.get("container_name") == "Sample"
    }
    assert "mergeClientInfo" in sample_fields
    assert "clientReference" in sample_fields
    assert "remoteClient" not in sample_fields
    assert "repository" not in sample_fields
