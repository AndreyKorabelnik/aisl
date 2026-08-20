from pathlib import Path

from code_analyzer_core.scanners.repo_scanner import scan_files
from code_analyzer_core.scanners.java_trace_builder import build_java_persistence_lineage_facts


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_deep_persistence_lineage_classifies_read_delete_and_mapper_save(tmp_path: Path) -> None:
    src = tmp_path / "src/main/java/com/acme"
    _write(src / "Profile.java", """
        package com.acme;
        public class Profile { private String stateCode; public String getStateCode(){ return stateCode; } }
    """)
    _write(src / "ProfileEntity.java", """
        package com.acme;
        import javax.persistence.*;
        @Entity @Table(name="profile_state")
        public class ProfileEntity {
          @Id @Column(name="id") private String id;
          @Column(name="state_code") private String stateCode;
          public void setStateCode(String stateCode){ this.stateCode = stateCode; }
        }
    """)
    _write(src / "ProfileMapper.java", """
        package com.acme;
        public interface ProfileMapper { ProfileEntity toEntity(Profile response); }
    """)
    _write(src / "ProfileRepository.java", """
        package com.acme;
        import org.springframework.data.jpa.repository.JpaRepository;
        public interface ProfileRepository extends JpaRepository<ProfileEntity, String> {}
    """)
    _write(src / "ProfileService.java", """
        package com.acme;
        import java.util.*;
        public class ProfileService {
          private ProfileRepository profileRepository;
          private ProfileMapper mapper;
          public void process(Profile response) { profileRepository.save(mapper.toEntity(response)); }
          public java.util.List<ProfileEntity> getUnprocessed(){ return profileRepository.findAll(); }
          public void removeLinks(java.util.List<String> phonesToRemove){ profileRepository.deleteAll(); }
        }
    """)

    facts, status = build_java_persistence_lineage_facts(scan_files(tmp_path), deep=True)
    by_type = {}
    for f in facts:
        by_type.setdefault(f.fact_type, []).append(f)

    writes = [f.properties for f in by_type.get("persistent_write", [])]
    assert any(w.get("saved_object") == "ProfileEntity" and w.get("dao_entity_type") == "ProfileEntity" for w in writes)

    lineages = [f.properties for f in by_type.get("source_to_storage_lineage", [])]
    assert any(
        l.get("assignment_kind") == "mapper_signature_same_name_field_candidate"
        and l.get("source_field") == "stateCode"
        and l.get("saved_object_field") == "stateCode"
        and "mapper_result_field_mapping_candidate" in l.get("missing_links", [])
        for l in lineages
    )

    gaps = [f.properties.get("gap_kind") for f in by_type.get("storage_lineage_gap", [])]
    assert "save_payload_from_mapper_result" not in gaps
    assert "storage_operation_is_read" in gaps
    assert "storage_operation_is_delete" in gaps
    assert status["deep"] is True


def test_deep_persistence_lineage_resolves_collection_constructor_fields_from_kafka_payload(tmp_path: Path) -> None:
    src = tmp_path / "src/main/java/com/acme"
    _write(src / "SpreadProfileRq.java", """
        package com.acme;
        public class SpreadProfileRq {
          private String phone;
          private String stateCode;
          public String getPhone(){ return phone; }
          public String getStateCode(){ return stateCode; }
        }
    """)
    _write(src / "UcpPhone_2Record.java", """
        package com.acme;
        public record UcpPhone_2Record(String phone, String stateCode) {}
    """)
    _write(src / "UcpPhoneDao.java", """
        package com.acme;
        import java.util.*;
        public class UcpPhoneDao { public void saveAll(Set<UcpPhone_2Record> records){} }
    """)
    _write(src / "SpreadProfileServiceImpl.java", """
        package com.acme;
        import java.util.*;
        import org.springframework.kafka.annotation.KafkaListener;
        public class SpreadProfileServiceImpl {
          private UcpPhoneDao ucpPhoneDao;
          @KafkaListener(topics="spread-profile")
          public void process(SpreadProfileRq rq) {
            Set<UcpPhone_2Record> toAdd = new HashSet<>();
            toAdd.add(new UcpPhone_2Record(rq.getPhone(), rq.getStateCode()));
            ucpPhoneDao.saveAll(toAdd);
          }
        }
    """)

    facts, status = build_java_persistence_lineage_facts(scan_files(tmp_path), deep=True)
    by_type = {}
    for f in facts:
        by_type.setdefault(f.fact_type, []).append(f)

    writes = [f.properties for f in by_type.get("persistent_write", [])]
    assert any(
        w.get("storage_target") == "ucpPhoneDao"
        and w.get("saved_object") == "UcpPhone_2Record"
        and w.get("saved_container_type") == "Set"
        and w.get("saved_element_type") == "UcpPhone_2Record"
        and w.get("dao_entity_type") == "UcpPhone_2Record"
        for w in writes
    )

    lineages = [f.properties for f in by_type.get("source_to_storage_lineage", [])]
    assert any(
        l.get("source_kind") == "kafka_consumed"
        and l.get("source_payload") == "SpreadProfileRq"
        and l.get("source_field") == "phone"
        and l.get("saved_object") == "UcpPhone_2Record"
        and l.get("saved_object_field") == "phone"
        and l.get("lineage_level") == "field"
        and l.get("assignment_kind") == "constructor"
        and l.get("evidence_maturity_dimensions", {}).get("field_mapping") == "confirmed"
        for l in lineages
    )
    assert any(
        l.get("source_field") == "stateCode"
        and l.get("saved_object_field") == "stateCode"
        and l.get("lineage_level") == "field"
        for l in lineages
    )
    assert status["source_to_storage_lineages_extracted"] >= 2


def test_deep_persistence_lineage_emits_object_level_when_collection_field_mapping_unresolved(tmp_path: Path) -> None:
    src = tmp_path / "src/main/java/com/acme"
    _write(src / "SpreadProfileRq.java", """
        package com.acme;
        public class SpreadProfileRq { private String raw; public String getRaw(){ return raw; } }
    """)
    _write(src / "UcpPhone_2Record.java", """
        package com.acme;
        public class UcpPhone_2Record { private String phone; private String stateCode; }
    """)
    _write(src / "UcpPhoneDao.java", """
        package com.acme;
        import java.util.*;
        public class UcpPhoneDao { public void saveAll(Set<UcpPhone_2Record> records){} }
    """)
    _write(src / "SpreadProfileServiceImpl.java", """
        package com.acme;
        import java.util.*;
        import org.springframework.kafka.annotation.KafkaListener;
        public class SpreadProfileServiceImpl {
          private UcpPhoneDao ucpPhoneDao;
          @KafkaListener(topics="spread-profile")
          public void process(SpreadProfileRq rq) {
            Set<UcpPhone_2Record> toAdd = new HashSet<>();
            UcpPhone_2Record record = convert(rq);
            toAdd.add(record);
            ucpPhoneDao.saveAll(toAdd);
          }
          private UcpPhone_2Record convert(SpreadProfileRq rq){ return new UcpPhone_2Record(); }
        }
    """)

    facts, status = build_java_persistence_lineage_facts(scan_files(tmp_path), deep=True)
    lineages = [f.properties for f in facts if f.fact_type == "source_to_storage_lineage"]
    assert any(
        l.get("lineage_level") == "collection_element"
        and l.get("source_payload") == "SpreadProfileRq"
        and l.get("source_kind") == "kafka_consumed"
        and l.get("saved_object") == "UcpPhone_2Record"
        and "field_mapping_not_resolved" in (l.get("missing_links") or [])
        for l in lineages
    )
    gaps = [f.properties for f in facts if f.fact_type == "storage_lineage_gap"]
    assert any(g.get("source_inspection_required") is True for g in gaps)
    assert status["source_to_storage_lineages_extracted"] >= 1


def test_deep_persistence_lineage_resolves_list_payload_loop_element_setter_mapping(tmp_path: Path) -> None:
    src = tmp_path / "src/main/java/com/acme"
    _write(src / "SpreadProfileRq.java", """
        package com.acme;
        public class SpreadProfileRq {
          private String phone;
          private String stateCode;
          public String getPhone(){ return phone; }
          public String getStateCode(){ return stateCode; }
        }
    """)
    _write(src / "UcpPhone_2Record.java", """
        package com.acme;
        public class UcpPhone_2Record {
          public void setPhone(String value) {}
          public void setStateCode(String value) {}
        }
    """)
    _write(src / "UcpPhoneDao.java", """
        package com.acme;
        import java.util.*;
        public class UcpPhoneDao { public void merge(Set<UcpPhone_2Record> records){} }
    """)
    _write(src / "SpreadProfileServiceImpl.java", """
        package com.acme;
        import java.util.*;
        import org.springframework.kafka.annotation.KafkaListener;
        public class SpreadProfileServiceImpl {
          private UcpPhoneDao ucpPhoneDao;
          @KafkaListener(topics="spread-profile")
          public void process(List<SpreadProfileRq> requests) {
            Set<UcpPhone_2Record> toAdd = new HashSet<>();
            for (SpreadProfileRq rq : requests) {
              UcpPhone_2Record record = new UcpPhone_2Record();
              record.setPhone(rq.getPhone());
              record.setStateCode(rq.getStateCode());
              toAdd.add(record);
            }
            ucpPhoneDao.merge(toAdd);
          }
        }
    """)

    facts, status = build_java_persistence_lineage_facts(scan_files(tmp_path), deep=True)
    lineages = [f.properties for f in facts if f.fact_type == "source_to_storage_lineage"]
    assert any(
        l.get("source_kind") == "kafka_consumed"
        and l.get("source_payload") == "SpreadProfileRq"
        and l.get("source_container") == "requests"
        and l.get("source_container_type") == "List"
        and l.get("source_element_type") == "SpreadProfileRq"
        and l.get("source_field") == "phone"
        and l.get("saved_object") == "UcpPhone_2Record"
        and l.get("saved_object_field") == "phone"
        and l.get("persistent_write_id")
        and l.get("storage_call") == "ucpPhoneDao.merge(toAdd)"
        for l in lineages
    )
    assert any(
        l.get("source_field") == "stateCode"
        and l.get("saved_object_field") == "stateCode"
        and l.get("lineage_level") == "field"
        for l in lineages
    )
    assert status["source_to_storage_lineages_extracted"] >= 2


def test_deep_persistence_lineage_resolves_collection_helper_method_return_setters(tmp_path: Path) -> None:
    src = tmp_path / "src/main/java/com/acme"
    _write(src / "SpreadProfileRq.java", """
        package com.acme;
        public class SpreadProfileRq {
          private String phoneNumber;
          private String ucpId;
          public String getPhoneNumber(){ return phoneNumber; }
          public String getUcpId(){ return ucpId; }
        }
    """)
    _write(src / "UcpPhone_2Record.java", """
        package com.acme;
        public class UcpPhone_2Record {
          public void setPhoneNumber(String value) {}
          public void setUcpId(String value) {}
        }
    """)
    _write(src / "UcpPhoneDao.java", """
        package com.acme;
        import java.util.*;
        public class UcpPhoneDao { public void merge(List<UcpPhone_2Record> records){} }
    """)
    _write(src / "SpreadProfileServiceImpl.java", """
        package com.acme;
        import java.util.*;
        public class SpreadProfileServiceImpl {
          private UcpPhoneDao ucpPhoneDao;
          public void process(List<SpreadProfileRq> requests) {
            List<UcpPhone_2Record> toAdd = new ArrayList<>();
            for (SpreadProfileRq rq : requests) {
              UcpPhone_2Record record = toRecord(rq);
              toAdd.add(record);
            }
            ucpPhoneDao.merge(toAdd);
          }
          private UcpPhone_2Record toRecord(SpreadProfileRq rq) {
            UcpPhone_2Record record = new UcpPhone_2Record();
            record.setPhoneNumber(rq.getPhoneNumber());
            record.setUcpId(rq.getUcpId());
            return record;
          }
        }
    """)

    facts, status = build_java_persistence_lineage_facts(scan_files(tmp_path), deep=True)
    lineages = [f.properties for f in facts if f.fact_type == "source_to_storage_lineage"]
    assert any(
        l.get("source_kind") == "method_input"
        and l.get("source_payload") == "SpreadProfileRq"
        and l.get("source_container") == "requests"
        and l.get("source_field") == "phoneNumber"
        and l.get("saved_object") == "UcpPhone_2Record"
        and l.get("saved_object_field") == "phoneNumber"
        and l.get("assignment_kind") == "setter"
        and l.get("lineage_level") == "field"
        for l in lineages
    )
    assert any(
        l.get("source_field") == "ucpId"
        and l.get("saved_object_field") == "ucpId"
        and l.get("persistent_write_id")
        for l in lineages
    )
    assert not any(
        g.properties.get("saved_object_field") in {"phoneNumber", "ucpId"}
        and g.properties.get("gap_kind") == "field_mapping_not_resolved"
        for g in facts if g.fact_type == "storage_lineage_gap"
    )
    assert status["source_to_storage_lineages_extracted"] >= 2


def test_deep_persistence_lineage_resolves_jooq_record_setvalue_fields(tmp_path: Path) -> None:
    src = tmp_path / "src/main/java/com/acme"
    _write(src / "SpreadProfileRq.java", """
        package com.acme;
        public class SpreadProfileRq {
          private String phoneNumber;
          private String ucpId;
          public String getPhoneNumber(){ return phoneNumber; }
          public String getUcpId(){ return ucpId; }
        }
    """)
    _write(src / "UcpPhone_2.java", """
        package com.acme;
        public class UcpPhone_2 {
          public static final Object PHONE_NUMBER = null;
          public static final Object UCP_ID = null;
        }
    """)
    _write(src / "UcpPhone_2Record.java", """
        package com.acme;
        public class UcpPhone_2Record {
          public void setPhoneNumber(String value) {}
          public void setUcpId(String value) {}
          public void set(Object field, Object value) {}
          public void setValue(Object field, Object value) {}
        }
    """)
    _write(src / "UcpPhoneDao.java", """
        package com.acme;
        import java.util.*;
        public class UcpPhoneDao { public void merge(List<UcpPhone_2Record> records){} }
    """)
    _write(src / "SpreadProfileServiceImpl.java", """
        package com.acme;
        import java.util.*;
        public class SpreadProfileServiceImpl {
          private UcpPhoneDao ucpPhoneDao;
          public void process(List<SpreadProfileRq> requests) {
            List<UcpPhone_2Record> toAdd = new ArrayList<>();
            for (SpreadProfileRq rq : requests) {
              UcpPhone_2Record record = new UcpPhone_2Record();
              record.set(UcpPhone_2.PHONE_NUMBER, rq.getPhoneNumber());
              record.setValue(UcpPhone_2.UCP_ID, rq.getUcpId());
              toAdd.add(record);
            }
            ucpPhoneDao.merge(toAdd);
          }
        }
    """)

    facts, status = build_java_persistence_lineage_facts(scan_files(tmp_path), deep=True)
    lineages = [f.properties for f in facts if f.fact_type == "source_to_storage_lineage"]
    assert any(
        l.get("source_field") == "phoneNumber"
        and l.get("saved_object_field") == "phoneNumber"
        and l.get("assignment_kind") == "jooq_setter"
        and l.get("lineage_level") == "field"
        for l in lineages
    )
    assert any(
        l.get("source_field") == "ucpId"
        and l.get("saved_object_field") == "ucpId"
        and l.get("assignment_kind") == "jooq_setter"
        for l in lineages
    )
    assert status["source_to_storage_lineages_extracted"] >= 2


def test_deep_persistence_lineage_detects_domain_named_dao_writes_and_mutations(tmp_path: Path) -> None:
    src = tmp_path / "src/main/java/com/acme"
    _write(src / "SaveOrUpdateUfsDocumentRequest.java", """
        package com.acme;
        public class SaveOrUpdateUfsDocumentRequest {
          private String loginId;
          private String externalId;
          public String getLoginId(){ return loginId; }
          public String getExternalId(){ return externalId; }
        }
    """)
    _write(src / "PushOperationDaoDto.java", """
        package com.acme;
        public class PushOperationDaoDto {
          public void setClientId(String value) {}
          public void setExternalId(String value) {}
        }
    """)
    _write(src / "SaveOrUpdateToPushDaoDtoConverter.java", """
        package com.acme;
        public class SaveOrUpdateToPushDaoDtoConverter {
          public PushOperationDaoDto convert(SaveOrUpdateUfsDocumentRequest source) {
            PushOperationDaoDto result = new PushOperationDaoDto();
            result.setClientId(source.getLoginId());
            result.setExternalId(source.getExternalId());
            return result;
          }
        }
    """)
    _write(src / "UohSaveDao.java", """
        package com.acme;
        public class UohSaveDao { public void mergeInternalLead(PushOperationDaoDto dto, Object markers){} }
    """)
    _write(src / "UohUpdateOperationDao.java", """
        package com.acme;
        public class UohUpdateOperationDao { public Long updateIsHidden(String clientId, String uohId, Boolean hidden, Object markers){ return 1L; } }
    """)
    _write(src / "UohPrepareDao.java", """
        package com.acme;
        public class UohPrepareDao { public Object prepareMarker(String clientId){ return new Object(); } public void actualize(Object markers){} }
    """)
    _write(src / "SaveOrUpdateUfsDocumentService.java", """
        package com.acme;
        public class SaveOrUpdateUfsDocumentService {
          private SaveOrUpdateToPushDaoDtoConverter requestConverter;
          private UohSaveDao uohSaveDao;
          private UohPrepareDao uohPrepareDao;
          public void saveOrUpdateUfsDocument(SaveOrUpdateUfsDocumentRequest request) {
            Object markers = uohPrepareDao.prepareMarker(request.getLoginId());
            uohPrepareDao.actualize(markers);
            uohSaveDao.mergeInternalLead(requestConverter.convert(request), markers);
          }
        }
    """)
    _write(src / "UpdateOperationsHidingService.java", """
        package com.acme;
        public class UpdateOperationsHidingService {
          private UohUpdateOperationDao updateOperationDao;
          public void updateHiding(String clientId, String uohId, Boolean hidden, Object markers) {
            updateOperationDao.updateIsHidden(clientId, uohId, hidden, markers);
          }
        }
    """)

    facts, status = build_java_persistence_lineage_facts(scan_files(tmp_path), deep=True)
    writes = [f.properties for f in facts if f.fact_type == "persistent_write"]
    gaps = [f.properties for f in facts if f.fact_type == "storage_lineage_gap"]

    domain_write = next(w for w in writes if w.get("storage_target") == "uohSaveDao" and w.get("write_kind") == "merge")
    assert domain_write.get("evidence_maturity_dimensions", {}).get("persistence_write") == "unresolved"
    signals = domain_write.get("candidate_signals") or []
    assert any(s.get("signal_type") == "custom_dao_persistence_boundary" and s.get("is_evidence") is False for s in signals)
    assert domain_write.get("source_inspection_required") is True
    assert any(g.get("storage_method") == "actualize" and g.get("access_kind") == "mutation" and g.get("not_saved_payload") is True for g in gaps)
    assert any(g.get("storage_method") == "updateIsHidden" and g.get("access_kind") == "mutation" and g.get("not_saved_payload") is True for g in gaps)
    assert status["persistent_writes_extracted"] >= 1
    assert status["storage_access_kind_counts"].get("write") >= 1
    assert status["storage_access_kind_counts"].get("mutation") >= 2
    assert status["candidate_signal_type_counts"].get("custom_dao_persistence_boundary") >= 1


def test_deep_persistence_lineage_marks_sql_writes_as_confirmed(tmp_path: Path) -> None:
    src = tmp_path / "src/main/java/com/acme"
    _write(src / "JdbcWriter.java", """
        package com.acme;
        public class JdbcWriter {
          private JdbcTemplate jdbcTemplate;
          public void save(String clientId) {
            jdbcTemplate.update("INSERT INTO UOH_OPERATIONS_HISTORY", clientId);
          }
        }
    """)

    facts, status = build_java_persistence_lineage_facts(scan_files(tmp_path), deep=True)
    writes = [f.properties for f in facts if f.fact_type == "persistent_write"]

    sql_write = next(w for w in writes if w.get("storage_target") == "UOH_OPERATIONS_HISTORY")
    assert sql_write.get("evidence_maturity_dimensions", {}).get("persistence_write") == "confirmed"
    assert sql_write.get("evidence_maturity_dimensions", {}).get("physical_storage") == "confirmed"
    assert not sql_write.get("source_inspection_required")
    assert status["evidence_maturity_level_counts"].get("confirmed") >= 1


def test_persistence_lineage_emits_evidence_maturity_matrix_for_unresolved_source_and_mapping(tmp_path: Path) -> None:
    src = tmp_path / "src/main/java/com/acme"
    _write(src / "SpreadProfileRq.java", """
        package com.acme;
        public class SpreadProfileRq { private String phoneNumber; public String getPhoneNumber(){ return phoneNumber; } }
    """)
    _write(src / "UcpPhone_2Record.java", """
        package com.acme;
        public class UcpPhone_2Record { private String phoneNumber; }
    """)
    _write(src / "UcpPhoneDao.java", """
        package com.acme;
        import java.util.*;
        public class UcpPhoneDao { public void merge(java.util.List<UcpPhone_2Record> records){} }
    """)
    _write(src / "SpreadProfileServiceImpl.java", """
        package com.acme;
        import java.util.*;
        public class SpreadProfileServiceImpl {
          private UcpPhoneDao ucpPhoneDao;
          public void process(java.util.List<SpreadProfileRq> requests) {
            java.util.List<UcpPhone_2Record> toAdd = new java.util.ArrayList<>();
            for (SpreadProfileRq rq : requests) {
              UcpPhone_2Record record = convert(rq);
              toAdd.add(record);
            }
            ucpPhoneDao.merge(toAdd);
          }
          private UcpPhone_2Record convert(SpreadProfileRq rq) { return new UcpPhone_2Record(); }
        }
    """)

    facts, status = build_java_persistence_lineage_facts(scan_files(tmp_path), deep=True)
    lineages = [f.properties for f in facts if f.fact_type == "source_to_storage_lineage"]
    gaps = [f.properties for f in facts if f.fact_type == "storage_lineage_gap"]

    object_lineage = next(l for l in lineages if l.get("lineage_level") == "collection_element")
    dims = object_lineage.get("evidence_maturity_dimensions") or {}
    assert object_lineage.get("evidence_maturity_level") == "unresolved"
    assert dims.get("source_boundary") == "unresolved"
    assert dims.get("field_mapping") == "unresolved"
    assert "field_mapping_not_resolved" in object_lineage.get("missing_links", [])

    field_gap = next(g for g in gaps if g.get("gap_kind") == "field_mapping_not_resolved")
    assert field_gap.get("evidence_maturity_level") == "unresolved"
    assert field_gap.get("lineage_blocker") in {
        "saved_payload_variable_assignment_not_resolved",
        "unsupported_or_dynamic_mapping_pattern",
        "known_storage_api_payload_mapping_not_resolved",
    }
    assert "evidence_maturity_model" in status
    assert status["evidence_maturity_level_counts"].get("unresolved", 0) >= 1
    inspections = [f.properties for f in facts if f.fact_type == "source_inspection_request"]
    assert inspections
    field_mapping_request = next(r for r in inspections if r.get("reason") == "field_mapping_not_resolved")
    assert field_mapping_request.get("request_type") == "targeted_source_inspection"
    assert field_mapping_request.get("target_operation") == "SpreadProfileServiceImpl.process"
    assert "read_only_targeted_code_check" in field_mapping_request.get("inspection_policy")
    assert any(cmd.get("purpose") == "open_target_method" for cmd in field_mapping_request.get("suggested_evidence_tools", []))
    assert status["source_inspection_requests_extracted"] >= 1


def test_strict_evidence_contract_marks_dao_boundary_as_candidate_signal_not_evidence(tmp_path: Path) -> None:
    src = tmp_path / "src/main/java/com/acme"
    _write(src / "SaveRq.java", """
        package com.acme;
        public class SaveRq {
          public String getValue(){ return "x"; }
        }
    """)
    _write(src / "DomainDao.java", """
        package com.acme;
        public interface DomainDao {
          void mergeInternalLead(Object dto);
        }
    """)
    _write(src / "Svc.java", """
        package com.acme;
        public class Svc {
          private DomainDao domainDao;
          public void process(SaveRq rq) {
            domainDao.mergeInternalLead(rq);
          }
        }
    """)

    facts, status = build_java_persistence_lineage_facts(scan_files(tmp_path), deep=True)
    write = next(f.properties for f in facts if f.fact_type == "persistent_write" and f.properties.get("storage_method") == "mergeInternalLead")

    assert write.get("evidence_maturity_dimensions", {}).get("persistence_write") == "unresolved"
    assert write.get("evidence_maturity_level") == "unresolved"
    signals = write.get("candidate_signals") or []
    assert signals
    assert signals[0]["signal_type"] == "custom_dao_persistence_boundary"
    assert signals[0]["is_evidence"] is False
    assert signals[0]["allowed_use"] == "navigation_only"
    lifecycle = write.get("unresolved_gap_lifecycle") or []
    assert any(item.get("dimension") == "persistence_write" and item.get("source_inspection_required") is True for item in lifecycle)
    assert status["evidence_maturity_model"]["levels"] == ["confirmed", "unresolved", "not_applicable"]
    assert "candidate_signal_policy" in status["evidence_maturity_model"]


def test_unresolved_gap_lifecycle_links_to_source_inspection_request(tmp_path: Path) -> None:
    src = tmp_path / "src/main/java/com/acme"
    _write(src / "SpreadProfileRq.java", """
        package com.acme;
        public class SpreadProfileRq { private String phoneNumber; public String getPhoneNumber(){ return phoneNumber; } }
    """)
    _write(src / "UcpPhone_2Record.java", """
        package com.acme;
        public class UcpPhone_2Record { private String phoneNumber; }
    """)
    _write(src / "UcpPhoneDao.java", """
        package com.acme;
        import java.util.*;
        public class UcpPhoneDao { public void merge(java.util.List<UcpPhone_2Record> records){} }
    """)
    _write(src / "SpreadProfileServiceImpl.java", """
        package com.acme;
        import java.util.*;
        public class SpreadProfileServiceImpl {
          private UcpPhoneDao ucpPhoneDao;
          public void process(java.util.List<SpreadProfileRq> requests) {
            java.util.List<UcpPhone_2Record> toAdd = new java.util.ArrayList<>();
            for (SpreadProfileRq rq : requests) {
              UcpPhone_2Record record = convert(rq);
              toAdd.add(record);
            }
            ucpPhoneDao.merge(toAdd);
          }
          private UcpPhone_2Record convert(SpreadProfileRq rq) { return new UcpPhone_2Record(); }
        }
    """)

    facts, _ = build_java_persistence_lineage_facts(scan_files(tmp_path), deep=True)
    lineage = next(f.properties for f in facts if f.fact_type == "source_to_storage_lineage" and f.properties.get("lineage_level") == "collection_element")
    lifecycle = lineage.get("unresolved_gap_lifecycle") or []
    field_items = [x for x in lifecycle if x.get("dimension") == "field_mapping"]
    assert field_items
    assert field_items[0]["actionability"] == "actionable"
    assert field_items[0]["source_inspection_required"] is True
    assert field_items[0]["source_inspection_request_status"] == "emitted"
    assert field_items[0]["source_inspection_request_ids"]
