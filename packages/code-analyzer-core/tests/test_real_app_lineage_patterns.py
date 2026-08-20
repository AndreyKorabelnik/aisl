from __future__ import annotations

import json
from pathlib import Path

from code_analyzer_core.scanners.java_trace_common import _kafka_payload_type_from_method_info
from code_analyzer_core.scanners.java_persistence_lineage import _jooq_batch_bind_mappings
from code_evidence import commands as evidence_commands


def test_kafka_payload_resolver_uses_deserialize_class_literal() -> None:
    method_info = {
        "method_calls": [
            {
                "method": "deserialize",
                "receiver": "this",
                "args": ["r", "SpreadProfileRq.class", "x -> x.getId().toString()"],
                "text": "deserialize(r, SpreadProfileRq.class, x -> x.getId().toString())",
                "line_start": 12,
            }
        ]
    }

    result = _kafka_payload_type_from_method_info(method_info)

    assert result["payload_type"] == "SpreadProfileRq"
    assert result["status"] == "resolved_from_deserialize_class_literal"


def test_jooq_batch_bind_mapping_maps_bind_args_to_set_and_where_slots(tmp_path: Path) -> None:
    body = """
        UpdateConditionStep<PhoneRecord> updateStep = dsl.update(PHONE)
            .set(PHONE.OPERATORID, (String) null)
            .set(PHONE.PHONEBLOCKCODE, (Long) null)
            .set(PHONE.QUICKSERVICES, (Short) null)
            .where(PHONE.PHONEID.eq((Long) null));
        BatchBindStep batch = dsl.batch(updateStep);
        phones.forEach(p -> batch.bind(
            p.getOperatorId(),
            p.getPhoneBlockCode(),
            p.getQuickServices(),
            p.getPhoneId()));
    """
    methods = {
        "PhoneDao.updatePhones": {
            "operation": "PhoneDao.updatePhones",
            "class_name": "PhoneDao",
            "method_name": "updatePhones",
            "body": body,
            "file": tmp_path / "PhoneDao.java",
            "line_start": 1,
            "method_calls": [
                {
                    "receiver": "batch",
                    "method": "bind",
                    "args": ["p.getOperatorId()", "p.getPhoneBlockCode()", "p.getQuickServices()", "p.getPhoneId()"],
                    "text": "batch.bind(p.getOperatorId(), p.getPhoneBlockCode(), p.getQuickServices(), p.getPhoneId())",
                    "line_start": 9,
                }
            ],
        }
    }

    facts = _jooq_batch_bind_mappings(methods)

    assert len(facts) == 1
    props = facts[0].properties
    assert props["storage_table"] == "PHONE"
    mappings = props["mappings"]
    assert mappings[0]["storage_field"] == "OPERATORID"
    assert mappings[0]["source_object"] == "p"
    assert mappings[0]["source_field"] == "operatorId"
    assert mappings[2]["storage_field"] == "QUICKSERVICES"
    assert mappings[2]["field_role"] == "write_target_field"
    assert mappings[3]["storage_field"] == "PHONEID"
    assert mappings[3]["field_role"] == "where_key_field"


def _write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def test_new_lineage_pattern_evidence_tools_return_fact_artifacts(tmp_path: Path) -> None:
    out = tmp_path / "analysis-out"
    _write(out / "manifest.json", {"repo_path": str(tmp_path / "repo")})
    _write(out / "facts" / "facts_by_type" / "java_lineage_pattern.json", [
        {"properties": {"java_lineage_pattern_id": "java_lineage_pattern_000001", "pattern_kind": "kafka_request_get_parsed_object", "operation": "Consumer.consume"}}
    ])
    _write(out / "facts" / "facts_by_type" / "jooq_batch_bind_mapping.json", [
        {"properties": {"jooq_batch_bind_mapping_id": "jooq_batch_bind_mapping_000001", "storage_table": "PHONE", "mapping_kind": "jooq_batch_bind_order"}}
    ])

    res1 = evidence_commands.java_lineage_patterns(out)
    assert res1["kind"] == "java-lineage-patterns"

    res2 = evidence_commands.jooq_batch_bind_mappings(out)
    assert res2["kind"] == "jooq-batch-bind-mappings"

from code_analyzer_core.scanners.java_persistence_lineage import (
    _spring_component_dependency_facts,
    _template_method_dispatch_facts,
    _factory_method_mapping_facts,
    _builder_field_mapping_facts,
    _stream_collection_lineage_facts,
)


def test_spring_component_dependency_detects_lombok_required_args_candidate(tmp_path: Path) -> None:
    facts = _spring_component_dependency_facts(
        class_fields={"Controller": {"service": "ProfileService"}},
        class_infos={
            "Controller": {"class_name": "Controller", "is_spring_component": True, "spring_component_kind": "RestController", "lombok_required_args": True, "file": str(tmp_path / "Controller.java")},
            "ProfileServiceImpl": {"class_name": "ProfileServiceImpl", "interfaces": ["ProfileService"], "kind": "class", "file": str(tmp_path / "ProfileServiceImpl.java")},
        },
    )

    assert len(facts) == 1
    props = facts[0].properties
    assert props["declared_type"] == "ProfileService"
    assert props["candidate_implementations"] == ["ProfileServiceImpl"]
    assert props["dependency_resolution_status"] == "candidate"


def test_template_method_dispatch_detects_abstract_handler_override(tmp_path: Path) -> None:
    methods = {
        "AbstractDalResultHandler.handle": {"operation": "AbstractDalResultHandler.handle", "class_name": "AbstractDalResultHandler", "method_name": "handle", "file": tmp_path / "AbstractDalResultHandler.java", "line_start": 1},
        "QuickServiceUpdateHandler.handleByDal": {"operation": "QuickServiceUpdateHandler.handleByDal", "class_name": "QuickServiceUpdateHandler", "method_name": "handleByDal", "file": tmp_path / "QuickServiceUpdateHandler.java", "line_start": 10},
    }
    class_infos = {"QuickServiceUpdateHandler": {"superclass": "AbstractDalResultHandler", "file": str(tmp_path / "QuickServiceUpdateHandler.java")}}

    facts = _template_method_dispatch_facts(methods, class_infos)

    assert len(facts) == 1
    assert facts[0].properties["candidate_template_operations"] == ["AbstractDalResultHandler.handle"]
    assert facts[0].properties["dispatch_status"] == "candidate_template_override"


def test_factory_method_mapping_extracts_setter_source_fields(tmp_path: Path) -> None:
    methods = {
        "Mapper.createRecord": {
            "operation": "Mapper.createRecord",
            "class_name": "Mapper",
            "method_name": "createRecord",
            "file": tmp_path / "Mapper.java",
            "line_start": 1,
            "syntax_assignments": [
                {"assignment_kind": "variable_declaration", "target": "record", "declared_type": "UcpPhone_2Record", "expression": "new UcpPhone_2Record()", "start_byte": 1, "end_byte": 50},
            ],
            "object_creations": [{"type": "UcpPhone_2Record", "start_byte": 20, "end_byte": 45}],
            "returns": [{"expression": "record"}],
            "method_calls": [
                {"receiver": "record", "method": "setUcpId", "args": ["request.getId()"], "text": "record.setUcpId(request.getId())", "line_start": 3},
                {"receiver": "request", "method": "getId", "args": [], "text": "request.getId()", "line_start": 3},
            ],
        }
    }

    facts = _factory_method_mapping_facts(methods)

    assert len(facts) == 1
    mapping = facts[0].properties["field_mappings"][0]
    assert mapping["target_container"] == "UcpPhone_2Record"
    assert mapping["target_field"] == "ucpId"
    assert mapping["source_object"] == "request"
    assert mapping["source_field"] == "id"


def test_builder_field_mapping_detects_to_builder_override(tmp_path: Path) -> None:
    methods = {
        "Handler.update": {
            "operation": "Handler.update",
            "class_name": "Handler",
            "method_name": "update",
            "file": tmp_path / "Handler.java",
            "line_start": 1,
            "method_calls": [
                {"receiver": "phone", "method": "toBuilder", "args": [], "text": "phone.toBuilder()", "line_start": 2},
                {"receiver": "phone.toBuilder()", "method": "quickServices", "args": ["request.getQuickServicesNewStatus()"], "text": "phone.toBuilder().quickServices(request.getQuickServicesNewStatus())", "line_start": 2},
                {"receiver": "request", "method": "getQuickServicesNewStatus", "args": [], "text": "request.getQuickServicesNewStatus()", "line_start": 2},
            ],
        }
    }

    facts = _builder_field_mapping_facts(methods)

    assert len(facts) == 1
    assert facts[0].properties["builder_origin_kind"] == "to_builder_clone"
    mapping = facts[0].properties["field_mappings"][0]
    assert mapping["target_field"] == "quickServices"
    assert mapping["source_object"] == "request"
    assert mapping["source_field"] == "quickServicesNewStatus"



def test_builder_field_mapping_preserves_overloaded_method_variants(tmp_path: Path) -> None:
    methods = {
        "DeviceLinkWrapper.updateBy": {
            "operation": "DeviceLinkWrapper.updateBy",
            "operation_signature": "com.acme.DeviceLinkWrapper#updateBy(String)",
            "class_name": "DeviceLinkWrapper",
            "method_name": "updateBy",
            "file": tmp_path / "DeviceLinkWrapper.java",
            "line_start": 20,
            "params": [{"name": "newPhone", "type": "String"}],
            "method_calls": [
                {"receiver": "this", "method": "toBuilder", "args": [], "text": "toBuilder()", "line_start": 21},
                {"receiver": "toBuilder()", "method": "phoneNumber", "args": ["newPhone"], "text": "toBuilder().phoneNumber(newPhone)", "line_start": 21},
            ],
        }
    }
    variants = [
        {
            "operation": "DeviceLinkWrapper.updateBy",
            "operation_signature": "com.acme.DeviceLinkWrapper#updateBy(SyncPushDeviceRequest)",
            "class_name": "DeviceLinkWrapper",
            "method_name": "updateBy",
            "file": tmp_path / "DeviceLinkWrapper.java",
            "line_start": 1,
            "params": [{"name": "syncDevice", "type": "SyncPushDeviceRequest"}],
            "method_calls": [
                {"receiver": "this", "method": "toBuilder", "args": [], "text": "toBuilder()", "line_start": 2},
                {"receiver": "toBuilder()", "method": "clientId", "args": ["syncDevice.getClientId()"], "text": "toBuilder().clientId(syncDevice.getClientId())", "line_start": 2},
                {"receiver": "syncDevice", "method": "getClientId", "args": [], "text": "syncDevice.getClientId()", "line_start": 2},
            ],
            "var_types": {"syncDevice": "SyncPushDeviceRequest"},
            "raw_var_types": {"syncDevice": "SyncPushDeviceRequest"},
        },
        methods["DeviceLinkWrapper.updateBy"],
    ]

    facts = _builder_field_mapping_facts(methods, method_variants=variants)

    assert len(facts) == 2
    by_signature = {f.properties["operation_signature"]: f.properties for f in facts}
    request_mapping = by_signature["com.acme.DeviceLinkWrapper#updateBy(SyncPushDeviceRequest)"]["field_mappings"][0]
    assert request_mapping["target_field"] == "clientId"
    assert request_mapping["source_object"] == "syncDevice"
    assert request_mapping["source_field"] == "clientId"
    phone_mapping = by_signature["com.acme.DeviceLinkWrapper#updateBy(String)"]["field_mappings"][0]
    assert phone_mapping["target_field"] == "phoneNumber"
    assert phone_mapping["source_expression"] == "newPhone"

def test_stream_collection_lineage_emits_source_collection_hint(tmp_path: Path) -> None:
    methods = {
        "Service.process": {
            "operation": "Service.process",
            "class_name": "Service",
            "method_name": "process",
            "file": tmp_path / "Service.java",
            "line_start": 1,
            "raw_var_types": {"requests": "List<SpreadProfileRq>"},
            "method_calls": [
                {"receiver": "requests", "method": "stream", "args": [], "text": "requests.stream()", "line_start": 2},
                {"receiver": "requests.stream().map(this::createUcpPhone)", "method": "collect", "args": ["toList()"], "text": "requests.stream().map(this::createUcpPhone).collect(toList())", "line_start": 2},
            ],
            "method_references": [{"qualifier": "this", "method": "createUcpPhone", "text": "this::createUcpPhone"}],
            "lambdas": [],
        }
    }

    facts = _stream_collection_lineage_facts(methods)

    assert len(facts) == 1
    props = facts[0].properties
    assert props["source_collection"] == "requests"
    assert props["source_collection_type"] == "List"
    assert "collect" in props["terminal_operations"]


def test_deep_lineage_pattern_evidence_tools_return_fact_artifacts(tmp_path: Path) -> None:
    out = tmp_path / "analysis-out"
    _write(out / "manifest.json", {"repo_path": str(tmp_path / "repo")})
    fact_files = {
        "spring_component_dependency": ("spring-component-dependencies", "spring_component_dependency_000001"),
        "template_method_dispatch": ("template-method-dispatches", "template_method_dispatch_000001"),
        "factory_method_mapping": ("factory-method-mappings", "factory_method_mapping_000001"),
        "builder_field_mapping": ("builder-field-mappings", "builder_field_mapping_000001"),
        "stream_collection_lineage": ("stream-collection-lineages", "stream_collection_lineage_000001"),
    }
    for fact_type, (_, evidence_id) in fact_files.items():
        _write(out / "facts" / "facts_by_type" / f"{fact_type}.json", [{"properties": {f"{fact_type}_id": evidence_id, "operation": "Sample.op"}}])

    command_funcs = {
        "spring-component-dependencies": evidence_commands.spring_component_dependencies,
        "template-method-dispatches": evidence_commands.template_method_dispatches,
        "factory-method-mappings": evidence_commands.factory_method_mappings,
        "builder-field-mappings": evidence_commands.builder_field_mappings,
        "stream-collection-lineages": evidence_commands.stream_collection_lineages,
    }
    for _, (cmd, _) in fact_files.items():
        res = command_funcs[cmd](out)
        assert res["kind"] == cmd

    show_res = evidence_commands.show(out, "factory_method_mapping_000001")
    assert show_res["kind"] == "factory-method-mappings"


def test_jooq_parameterized_sql_mapping_maps_execute_args_to_write_and_where_slots(tmp_path: Path) -> None:
    from code_analyzer_core.scanners.java_persistence_lineage import _jooq_parameterized_sql_mappings

    methods = {
        "PhoneDao.updatePhone": {
            "operation": "PhoneDao.updatePhone",
            "class_name": "PhoneDao",
            "method_name": "updatePhone",
            "body": 'dsl.execute("update PHONE set OPERATORID = ? where PHONEID = ?", p.getOperatorId(), p.getPhoneId());',
            "file": tmp_path / "PhoneDao.java",
            "line_start": 1,
            "method_calls": [
                {
                    "receiver": "dsl",
                    "method": "execute",
                    "args": ['"update PHONE set OPERATORID = ? where PHONEID = ?"', "p.getOperatorId()", "p.getPhoneId()"],
                    "text": 'dsl.execute("update PHONE set OPERATORID = ? where PHONEID = ?", p.getOperatorId(), p.getPhoneId())',
                    "line_start": 1,
                }
            ],
        }
    }

    facts = _jooq_parameterized_sql_mappings(methods)

    assert len(facts) == 1
    props = facts[0].properties
    assert props["storage_table"] == "PHONE"
    assert props["write_target_fields"][0]["storage_field"] == "OPERATORID"
    assert props["write_target_fields"][0]["source_field"] == "operatorId"
    assert props["where_key_fields"][0]["storage_field"] == "PHONEID"
    assert props["where_key_fields"][0]["source_field"] == "phoneId"


def test_mapstruct_mapper_signature_fact_is_object_level_only() -> None:
    from code_analyzer_core.scanners.java_persistence_lineage import _mapstruct_mapper_signature_facts

    facts = _mapstruct_mapper_signature_facts({
        "toRecord": [
            {
                "mapper_class": "ProfileMapper",
                "method": "toRecord",
                "source_container": "ProfileRequest",
                "source_variable_hint": "request",
                "target_container": "ProfileRecord",
                "source_path": "src/main/java/ProfileMapper.java",
                "line_start": 7,
            }
        ]
    })

    assert len(facts) == 1
    props = facts[0].properties
    assert props["source_container"] == "ProfileRequest"
    assert props["target_container"] == "ProfileRecord"
    assert props["mapping_status"] == "candidate_object_bridge"
    assert "field" not in props.get("mapping_status", "")


def test_named_parameter_sql_mapping_maps_update_set_slots_only(tmp_path: Path) -> None:
    from code_analyzer_core.scanners.java_persistence_lineage import _jooq_parameterized_sql_mappings

    methods = {
        "PhoneDao.updatePhoneNamed": {
            "operation": "PhoneDao.updatePhoneNamed",
            "class_name": "PhoneDao",
            "method_name": "updatePhoneNamed",
            "body": 'namedJdbc.update("update PHONE set OPERATORID = :operatorId where PHONEID = :phoneId", params);',
            "file": tmp_path / "PhoneDao.java",
            "line_start": 1,
            "method_calls": [
                {"receiver": "params", "method": "addValue", "args": ['"operatorId"', "p.getOperatorId()"], "text": 'params.addValue("operatorId", p.getOperatorId())'},
                {"receiver": "params", "method": "addValue", "args": ['"phoneId"', "p.getPhoneId()"], "text": 'params.addValue("phoneId", p.getPhoneId())'},
                {
                    "receiver": "namedJdbc",
                    "method": "update",
                    "args": ['"update PHONE set OPERATORID = :operatorId where PHONEID = :phoneId"', "params"],
                    "text": 'namedJdbc.update("update PHONE set OPERATORID = :operatorId where PHONEID = :phoneId", params)',
                    "line_start": 3,
                },
            ],
        }
    }

    facts = _jooq_parameterized_sql_mappings(methods)

    assert len(facts) == 1
    props = facts[0].properties
    assert props["mapping_kind"] == "named_parameter_sql_mapping"
    assert props["storage_table"] == "PHONE"
    assert props["write_target_fields"][0]["storage_field"] == "OPERATORID"
    assert props["write_target_fields"][0]["bind_parameter"] == "operatorId"
    assert props["write_target_fields"][0]["source_field"] == "operatorId"
    assert props["where_key_fields"][0]["storage_field"] == "PHONEID"
    assert props["where_key_fields"][0]["source_field"] == "phoneId"


def test_named_parameter_sql_mapping_maps_insert_values_from_map_of(tmp_path: Path) -> None:
    from code_analyzer_core.scanners.java_persistence_lineage import _jooq_parameterized_sql_mappings

    methods = {
        "PhoneDao.insertPhoneNamed": {
            "operation": "PhoneDao.insertPhoneNamed",
            "class_name": "PhoneDao",
            "method_name": "insertPhoneNamed",
            "body": 'namedJdbc.update("insert into PHONE (PHONEID, OPERATORID) values (:phoneId, :operatorId)", Map.of("phoneId", p.getPhoneId(), "operatorId", p.getOperatorId()));',
            "file": tmp_path / "PhoneDao.java",
            "line_start": 1,
            "method_calls": [
                {
                    "receiver": "namedJdbc",
                    "method": "update",
                    "args": [
                        '"insert into PHONE (PHONEID, OPERATORID) values (:phoneId, :operatorId)"',
                        'Map.of("phoneId", p.getPhoneId(), "operatorId", p.getOperatorId())',
                    ],
                    "text": 'namedJdbc.update("insert into PHONE (PHONEID, OPERATORID) values (:phoneId, :operatorId)", Map.of("phoneId", p.getPhoneId(), "operatorId", p.getOperatorId()))',
                    "line_start": 1,
                }
            ],
        }
    }

    facts = _jooq_parameterized_sql_mappings(methods)

    assert len(facts) == 1
    props = facts[0].properties
    fields = {x["storage_field"]: x for x in props["write_target_fields"]}
    assert fields["PHONEID"]["source_field"] == "phoneId"
    assert fields["OPERATORID"]["source_field"] == "operatorId"
    assert props.get("where_key_fields") is None or props.get("where_key_fields") == []


def test_mapstruct_mapper_signature_fact_carries_annotation_field_mappings() -> None:
    from code_analyzer_core.scanners.java_persistence_lineage import _mapstruct_mapper_signature_facts

    facts = _mapstruct_mapper_signature_facts({
        "toRecord": [
            {
                "mapper_class": "ProfileMapper",
                "method": "toRecord",
                "source_container": "ProfileRequest",
                "source_variable_hint": "request",
                "target_container": "ProfileRecord",
                "field_mappings": [
                    {"source_field": "clientId", "source_path": "client.id", "target_field": "clientId", "target_path": "clientId", "mapping_kind": "mapstruct_annotation_field_mapping"},
                ],
                "source_path": "src/main/java/ProfileMapper.java",
                "line_start": 7,
            }
        ]
    })

    assert len(facts) == 1
    props = facts[0].properties
    assert props["mapping_status"] == "candidate_object_bridge_with_field_annotations"
    assert props["lineage_status"] == "candidate_field_mapping_annotation"
    assert props["field_mappings"][0]["source_field"] == "clientId"
    assert props["field_mappings"][0]["target_field"] == "clientId"


def test_mapper_result_save_emits_candidate_field_lineage_without_gap(tmp_path: Path) -> None:
    from code_analyzer_core.scanners.repo_scanner import scan_files
    from code_analyzer_core.scanners.java_trace_builder import build_java_persistence_lineage_facts

    def write_java(path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    src = tmp_path / "src" / "main" / "java" / "com" / "acme"
    write_java(src / "ProfileRequest.java", """
        package com.acme;
        public class ProfileRequest { private String stateCode; public String getStateCode(){ return stateCode; } }
    """)
    write_java(src / "ProfileEntity.java", """
        package com.acme;
        import javax.persistence.*;
        @Entity @Table(name="profile_state")
        public class ProfileEntity { @Column(name="state_code") private String stateCode; public void setStateCode(String stateCode){ this.stateCode = stateCode; } }
    """)
    write_java(src / "ProfileMapper.java", """
        package com.acme;
        @org.mapstruct.Mapper
        public interface ProfileMapper { ProfileEntity toEntity(ProfileRequest request); }
    """)
    write_java(src / "ProfileRepository.java", """
        package com.acme;
        import org.springframework.data.jpa.repository.JpaRepository;
        public interface ProfileRepository extends JpaRepository<ProfileEntity, String> {}
    """)
    write_java(src / "ProfileService.java", """
        package com.acme;
        public class ProfileService {
          private ProfileRepository repository;
          private ProfileMapper mapper;
          public void process(ProfileRequest request) { repository.save(mapper.toEntity(request)); }
        }
    """)

    facts, status = build_java_persistence_lineage_facts(scan_files(tmp_path), deep=True)
    lineages = [f.properties for f in facts if f.fact_type == "source_to_storage_lineage"]
    gaps = [f.properties.get("gap_kind") for f in facts if f.fact_type == "storage_lineage_gap"]

    assert any(
        l.get("assignment_kind") == "mapper_signature_same_name_field_candidate"
        and l.get("source_payload") == "ProfileRequest"
        and l.get("source_field") == "stateCode"
        and l.get("saved_object") == "ProfileEntity"
        and l.get("saved_object_field") == "stateCode"
        and "mapper_result_field_mapping_candidate" in l.get("missing_links", [])
        for l in lineages
    )
    assert "save_payload_from_mapper_result" not in gaps
    assert status["source_to_storage_lineages_extracted"] >= 1


def test_dao_jooq_mapping_resolves_local_alias_and_record_accessor() -> None:
    from code_analyzer_core.scanners.java_persistence_lineage import _dao_jooq_field_mappings

    dao_mi = {
        "operation": "PhoneDao.updatePhone",
        "class_name": "PhoneDao",
        "method_name": "updatePhone",
        "params": [{"name": "wrapper", "type": "PhoneWrapper"}],
        "body": """
            String phoneId = wrapper.phoneId();
            dsl.update(PHONE)
               .set(PHONE.PHONEID, phoneId)
               .set(PHONE.OPERATORID, wrapper.getOperatorId())
               .execute();
        """,
        "method_calls": [
            {"receiver": "wrapper", "method": "phoneId", "args": [], "text": "wrapper.phoneId()"},
            {"receiver": "wrapper", "method": "getOperatorId", "args": [], "text": "wrapper.getOperatorId()"},
        ],
        "syntax_assignments": [
            {"assignment_kind": "variable_declaration", "target": "phoneId", "expression": "wrapper.phoneId()"},
        ],
    }

    mappings = _dao_jooq_field_mappings(dao_mi, {})
    by_field = {m["storage_field"]: m for m in mappings}

    assert by_field["PHONEID"]["source_object"] == "wrapper"
    assert by_field["PHONEID"]["source_field"] == "phoneId"
    assert by_field["OPERATORID"]["source_object"] == "wrapper"
    assert by_field["OPERATORID"]["source_field"] == "operatorId"


def test_dao_jooq_mapping_resolves_stream_record_setters_feeding_batch_insert() -> None:
    from code_analyzer_core.scanners.java_persistence_lineage import _dao_jooq_field_mappings

    dao_mi = {
        "operation": "PhoneDao.addPhones",
        "class_name": "PhoneDao",
        "method_name": "addPhones",
        "params": [{"name": "phones", "type": "java.util.List<PhoneWrapper>"}],
        "body": """
            List<PhoneRecord> phones2Insert = phones.stream()
                .map(p -> {
                    PhoneRecord phoneRecord = new PhoneRecord();
                    phoneRecord.setPhoneid(p.getPhoneId());
                    phoneRecord.setOperatorid(p.getOperatorId());
                    return phoneRecord;
                })
                .collect(Collectors.toList());
            dsl.batchInsert(phones2Insert).execute();
        """,
        "method_calls": [
            {"receiver": "phones", "method": "stream", "args": [], "text": "phones.stream()"},
            {"receiver": "p", "method": "getPhoneId", "args": [], "text": "p.getPhoneId()"},
            {"receiver": "p", "method": "getOperatorId", "args": [], "text": "p.getOperatorId()"},
            {"receiver": "phoneRecord", "method": "setPhoneid", "args": ["p.getPhoneId()"], "text": "phoneRecord.setPhoneid(p.getPhoneId())"},
            {"receiver": "phoneRecord", "method": "setOperatorid", "args": ["p.getOperatorId()"], "text": "phoneRecord.setOperatorid(p.getOperatorId())"},
            {"receiver": "dsl", "method": "batchInsert", "args": ["phones2Insert"], "text": "dsl.batchInsert(phones2Insert)"},
        ],
    }

    mappings = _dao_jooq_field_mappings(dao_mi, {})
    by_field = {m["storage_field"]: m for m in mappings}

    assert by_field["phoneid"]["mapping_kind"] == "jooq_record_batch_insert_call_argument_mapping"
    assert by_field["phoneid"]["storage_table"] == "PHONE"
    assert by_field["phoneid"]["source_object"] == "phones"
    assert by_field["phoneid"]["source_field"] == "phoneId"
    assert by_field["operatorid"]["source_object"] == "phones"
    assert by_field["operatorid"]["source_field"] == "operatorId"


def test_jooq_batch_bind_insert_for_link_exposes_persistent_write_and_lineage(tmp_path: Path) -> None:
    from code_analyzer_core.scanners.java_persistence_lineage import _jooq_batch_bind_write_facts

    body = """
        for (LinkWrapper link : links) {
            link.setLinkId(dsl.nextval(LINK_SEQ));
        }
        InsertSetMoreStep<LinkRecord> insertStep = dsl.insertInto(LINK)
                .set(LINK.LINKID, (Long) null)
                .set(LINK.PAYMENTCARDID, (Long) null)
                .set(LINK.PHONEID, (Long) null)
                .set(LINK.PAYMENTBLOCKID, (Long) null)
                .set(LINK.CHANNEL, (Long) null)
                .set(LINK.CHANGELINKTIME, DbUtil.getSysTimestamp().coerce(LocalDateTime.class))
                .set(LINK.LINKNOTIFICATIONSTATE, (Long) null)
                .set(LINK.LINKPHASETYPE, DSL.inline(2L))
                .set(LINK.LINKPRODTYPE, DSL.inline(1L));
        BatchBindStep batch = dsl.batch(insertStep);
        links.forEach(l -> batch.bind(
                l.getLinkId(),
                Optional.ofNullable(l.getCardId()).orElse(l.getCardWrapper().getCardId()),
                Optional.ofNullable(l.getPhoneId()).orElse(l.getPhoneWrapper().getPhoneId()),
                l.getPaymentBlockId(),
                l.getChannel(),
                Optional.ofNullable(l.getTariff()).map(BigDecimal::new).orElse(BigDecimal.ONE)
        ));
    """
    methods = {
        "LinkDao.addWay4Links": {
            "operation": "LinkDao.addWay4Links",
            "class_name": "LinkDao",
            "method_name": "addWay4Links",
            "body": body,
            "file": tmp_path / "LinkDao.java",
            "line_start": 1,
            "method_calls": [],
        }
    }

    mapping_facts = _jooq_batch_bind_mappings(methods)
    assert len(mapping_facts) == 1
    props = mapping_facts[0].properties
    assert props["storage_table"] == "LINK"
    by_field = {m["storage_field"]: m for m in props["write_target_fields"]}
    assert by_field["LINKID"]["source_field"] == "linkId"
    assert by_field["LINKID"]["source_generation"]["sequence_name"] == "LINK_SEQ"
    assert by_field["PAYMENTCARDID"]["source_field"] == "cardId"
    assert by_field["PHONEID"]["source_field"] == "phoneId"

    promoted = _jooq_batch_bind_write_facts(mapping_facts)
    assert any(f.fact_type == "persistent_write" and f.properties["storage_target"] == "LINK" for f in promoted)
    lineages = [f for f in promoted if f.fact_type == "source_to_storage_lineage"]
    assert any(f.properties["storage_field"] == "PAYMENTCARDID" and f.properties["source_field"] == "cardId" for f in lineages)
    assert any(f.properties["storage_field"] == "LINKID" and f.properties["assignment_kind"] == "jooq_batch_bind_sequence_generated_field" for f in lineages)




def test_jooq_batch_bind_promotion_handles_unresolved_source_field() -> None:
    from code_analyzer_core.models import EvidenceRef, Fact
    from code_analyzer_core.scanners.java_persistence_lineage import _jooq_batch_bind_write_facts

    mapping = Fact(
        fact_type="jooq_batch_bind_mapping",
        name="batch",
        properties={
            "jooq_batch_bind_mapping_id": "jooq_batch_bind_mapping_000001",
            "operation": "LinkDao.addWay4Links",
            "class_name": "LinkDao",
            "storage_table": "LINK",
            "statement_kind": "batch_insert",
            "batch_variable": "batch",
            "write_target_fields": [
                {
                    "storage_field": "CHANGELINKTIME",
                    "source_expression": "DbUtil.getSysTimestamp()",
                    "source_field": None,
                }
            ],
        },
        evidence=[EvidenceRef(file_path="LinkDao.java", line_start=1, line_end=1, extractor="test")],
    )

    promoted = _jooq_batch_bind_write_facts([mapping])
    lineages = [f for f in promoted if f.fact_type == "source_to_storage_lineage"]
    assert len(lineages) == 1
    assert lineages[0].properties["storage_field"] == "CHANGELINKTIME"
    assert lineages[0].properties["source_field_role"] == "field"
    assert "source_field_not_resolved" in lineages[0].properties["missing_links"]


def test_table_filter_finds_jooq_promoted_persistent_write(tmp_path: Path) -> None:
    import json
    out = tmp_path / "analysis-out"
    facts_dir = out / "facts" / "facts_by_type"
    facts_dir.mkdir(parents=True, exist_ok=True)
    (out / "manifest.json").write_text(json.dumps({"repo_path": str(tmp_path)}), encoding="utf-8")
    (facts_dir / "persistent_write.json").write_text(json.dumps([
        {"properties": {"persistent_write_id": "persistent_write_1", "storage_target": "OTHER"}},
        {"properties": {"persistent_write_id": "persistent_write_2", "storage_target": "LINK"}},
    ]), encoding="utf-8")

    data = evidence_commands.persistent_write(out, table="link")
    assert data["hit_count"] == 1
    assert data["hits"][0]["item"]["properties"]["storage_target"] == "LINK"


def test_source_to_storage_table_filter_preserves_multiple_fields_same_storage_access(tmp_path: Path) -> None:
    import json
    out = tmp_path / "analysis-out"
    facts_dir = out / "facts" / "facts_by_type"
    facts_dir.mkdir(parents=True, exist_ok=True)
    (out / "manifest.json").write_text(json.dumps({"repo_path": str(tmp_path)}), encoding="utf-8")
    (facts_dir / "source_to_storage_lineage.json").write_text(json.dumps([
        {"properties": {"source_to_storage_lineage_id": "l1", "storage_access_id": "same", "storage_target": "LINK", "storage_field": "A"}},
        {"properties": {"source_to_storage_lineage_id": "l2", "storage_access_id": "same", "storage_target": "LINK", "storage_field": "B"}},
    ]), encoding="utf-8")

    data = evidence_commands.source_to_storage_lineage(out, table="link")
    assert data["hit_count"] == 2


def test_interprocedural_container_provenance_reaches_kafka_payload_through_batch(tmp_path: Path) -> None:
    from collections import defaultdict

    from code_analyzer_core.scanners.java_call_observations import (
        _build_call_facts,
        _build_method_index,
        _detect_origins,
    )
    from code_analyzer_core.scanners.java_persistence_lineage import (
        _actual_origin_for_cross_dao,
        _interprocedural_container_parameter_origin,
        _interprocedural_index,
    )
    from code_analyzer_core.scanners.java_persistence_mapping_resolvers import _builder_field_mapping_facts

    src = tmp_path / "src" / "main" / "java" / "com" / "acme"
    src.mkdir(parents=True)
    (src / "InputEvent.java").write_text(
        "package com.acme; public class InputEvent { public String getClientId(){ return null; } }",
        encoding="utf-8",
    )
    (src / "Wrapper.java").write_text(
        """
        package com.acme;
        public class Wrapper {
          public Builder toBuilder(){ return new Builder(); }
          public Wrapper updateBy(InputEvent event){ return toBuilder().clientId(event.getClientId()).build(); }
          public static class Builder {
            public Builder clientId(String value){ return this; }
            public Wrapper build(){ return new Wrapper(); }
          }
        }
        """,
        encoding="utf-8",
    )
    (src / "Batch.java").write_text(
        """
        package com.acme;
        import java.util.*;
        public class Batch {
          private final List<Wrapper> records = new ArrayList<>();
          public void addRecord(Wrapper record){ records.add(record); }
          public List<Wrapper> records(){ return records; }
        }
        """,
        encoding="utf-8",
    )
    (src / "Flow.java").write_text(
        """
        package com.acme;
        import java.util.*;
        class Consumer {
          private Handler handler;
          @org.springframework.kafka.annotation.KafkaListener(topics="events")
          public void onReceive(InputEvent request){ handler.handle(request); }
        }
        class Handler {
          private Gateway gateway;
          public void handle(InputEvent event){ doHandle(event); }
          private void doHandle(InputEvent event){
            Batch batch = new Batch();
            Wrapper wrapper = new Wrapper();
            batch.addRecord(wrapper.updateBy(event));
            gateway.send(batch);
          }
        }
        class Gateway {
          private Service service;
          public void send(Batch batch){ service.save(batch); }
        }
        class Service {
          private Dao dao;
          public void save(Batch batch){ dao.update(batch.records()); }
        }
        class Dao { public void update(List<Wrapper> records){} }
        """,
        encoding="utf-8",
    )

    files = sorted(src.glob("*.java"))
    methods, class_fields, class_infos, _warnings = _build_method_index(files)
    calls = _build_call_facts(methods, class_fields, class_infos)
    origins_by_operation: dict[str, list[dict]] = defaultdict(list)
    for origin in _detect_origins(methods):
        origins_by_operation[str(origin.get("operation") or "")].append(origin)
    variants = [
        variant
        for info in class_infos.values()
        for variant in info.get("method_variants", [])
        if isinstance(variant, dict)
    ]
    index = _interprocedural_index(
        methods=methods,
        class_infos=class_infos,
        calls=calls,
        origins_by_operation=origins_by_operation,
        builder_field_mapping_facts=_builder_field_mapping_facts(methods, method_variants=variants),
    )

    origin = _interprocedural_container_parameter_origin(
        operation="Service.save",
        parameter="batch",
        accessor="records",
        target_field="clientId",
        index=index,
    )

    assert origin is not None
    assert origin["source_kind"] == "kafka_consumed"
    assert origin["source_operation"] == "Consumer.onReceive"
    assert origin["source_payload"] == "InputEvent"
    assert origin["source_field"] == "clientId"
    assert "source_kind_not_confirmed" not in origin["missing_links"]

    canonical_origin = _actual_origin_for_cross_dao(
        "batch",
        dao_source_object="records",
        dao_source_field="records.clientId",
        caller_mi=methods["Service.save"],
        variable_origins={},
        ingress_by_param={},
        interprocedural_index=index,
    )
    assert canonical_origin["source_kind"] == "kafka_consumed"
    assert canonical_origin["source_operation"] == "Consumer.onReceive"
    assert canonical_origin["source_payload"] == "InputEvent"
    assert canonical_origin["source_field"] == "clientId"


def test_jooq_select_from_chain_emits_physical_read_fields_and_record_type(tmp_path: Path) -> None:
    from code_analyzer_core.scanners.java_call_observations import _build_method_index, _build_storage_facts

    src = tmp_path / "src" / "main" / "java" / "com" / "acme"
    src.mkdir(parents=True)
    java_file = src / "DeviceDao.java"
    java_file.write_text(
        """
        package com.acme;
        class DeviceDao {
          private org.jooq.DSLContext dsl;
          Object load(java.util.List<String> ids) {
            return dsl.select(DEVICE_LINK.DEVICE_ID, DEVICE_LINK.CLIENT_ID, DEVICE_LINK.UCP_ID)
                .from(DEVICE_LINK)
                .where(DEVICE_LINK.DEVICE_ID.in(ids))
                .fetchInto(DeviceLinkRecord.class);
          }
        }
        """,
        encoding="utf-8",
    )

    methods, _fields, _infos, _warnings = _build_method_index([java_file])
    reads = [
        access
        for access in _build_storage_facts(methods)
        if access.get("access_kind") == "read" and access.get("storage_kind") == "jooq_select"
    ]

    assert len(reads) == 1
    assert reads[0]["table_or_repository"] == "DEVICE_LINK"
    assert reads[0]["selected_fields"] == ["DEVICE_ID", "CLIENT_ID", "UCP_ID"]
    assert reads[0]["result_type"] == "DeviceLinkRecord"
    assert reads[0]["storage_resolution_level"] == "confirmed_sql_read"


def test_jooq_record_constructor_projection_reaches_rest_response(tmp_path: Path) -> None:
    from code_analyzer_core.scanners.java_call_observations import (
        _build_call_facts,
        _build_method_index,
        _build_storage_facts,
    )
    from code_analyzer_core.scanners.java_persistence_lineage import (
        _build_stored_data_access_facts,
        _extract_all_schema_fields,
    )

    src = tmp_path / "src" / "main" / "java" / "com" / "acme"
    src.mkdir(parents=True)
    sources = {
        "DeviceLinkRecord.java": """
            package com.acme;
            public class DeviceLinkRecord {
              private String clientId; private String deviceId; private String ucpId;
              public String getClientId(){ return clientId; }
              public String getDeviceId(){ return deviceId; }
              public String getUcpId(){ return ucpId; }
            }
        """,
        "ClientDevicePair.java": """
            package com.acme;
            public class ClientDevicePair {
              private final String clientId; private final String deviceId; private final String ucpId;
              public ClientDevicePair(String clientId, String deviceId, String ucpId){
                this.clientId=clientId; this.deviceId=deviceId; this.ucpId=ucpId;
              }
            }
        """,
        "DevicesResponse.java": """
            package com.acme;
            import java.util.Map;
            public class DevicesResponse {
              private final Map<String, ClientDevicePair> phoneToDevice;
              public DevicesResponse(Map<String, ClientDevicePair> phoneToDevice){ this.phoneToDevice=phoneToDevice; }
            }
        """,
        "DeviceDao.java": """
            package com.acme;
            import java.util.*;
            class DeviceDao {
              private org.jooq.DSLContext dsl;
              Map<String, ClientDevicePair> load(Set<String> phones) {
                return dsl.select(DEVICE_LINK.CLIENT_ID, DEVICE_LINK.DEVICE_ID, DEVICE_LINK.UCP_ID)
                    .from(DEVICE_LINK)
                    .fetchInto(DeviceLinkRecord.class).stream()
                    .collect(java.util.stream.Collectors.toMap(x -> "key",
                        x -> new ClientDevicePair(x.getClientId(), x.getDeviceId(), x.getUcpId())));
              }
            }
        """,
        "DeviceService.java": """
            package com.acme;
            import java.util.*;
            class DeviceService {
              private DeviceDao dao;
              DevicesResponse find(Set<String> phones) {
                Map<String, ClientDevicePair> pairs = dao.load(phones);
                return new DevicesResponse(pairs);
              }
            }
        """,
        "DeviceController.java": """
            package com.acme;
            import java.util.*;
            @org.springframework.web.bind.annotation.RestController
            class DeviceController {
              private DeviceService service;
              @org.springframework.web.bind.annotation.PostMapping("/devices")
              DevicesResponse find(Set<String> phones) { return service.find(phones); }
            }
        """,
    }
    files: list[Path] = []
    for name, text in sources.items():
        path = src / name
        path.write_text(text, encoding="utf-8")
        files.append(path)

    methods, class_fields, class_infos, _warnings = _build_method_index(files)
    storage_accesses = _build_storage_facts(methods)
    calls = _build_call_facts(methods, class_fields, class_infos)
    schema_fields = _extract_all_schema_fields(files)
    facts, _counts = _build_stored_data_access_facts(
        methods,
        class_fields,
        storage_accesses,
        schema_fields,
        calls=calls,
    )

    lineages = [
        fact.properties
        for fact in facts
        if fact.fact_type == "storage_to_access_lineage"
        and fact.properties.get("source_storage_object") == "DEVICE_LINK"
        and fact.properties.get("access_boundary") == "DeviceController.find"
    ]
    assert len(lineages) == 1
    lineage = lineages[0]
    assert lineage["lineage_status"] == "confirmed"
    assert lineage["path"][-1]["endpoint_or_topic"] == "/devices"
    mappings = {item["storage_field"]: item["response_field"] for item in lineage["field_mappings"]}
    assert mappings == {
        "CLIENT_ID": "phoneToDevice.clientId",
        "DEVICE_ID": "phoneToDevice.deviceId",
        "UCP_ID": "phoneToDevice.ucpId",
    }
    assert not any(
        fact.fact_type == "storage_to_access_lineage"
        and fact.properties.get("source_storage_object") == "DEVICE_LINK"
        and fact.properties.get("access_boundary") == "DeviceDao.load"
        and fact.properties.get("lineage_status") == "confirmed"
        for fact in facts
    )


def test_deep_profile_promotes_resolved_custom_dao_update_and_keeps_kafka_provenance(tmp_path: Path) -> None:
    from code_analyzer_core.scanners.java_persistence_lineage import build_java_persistence_lineage_facts
    from code_analyzer_core.scanners.repo_scanner import scan_files

    src = tmp_path / "src" / "main" / "java" / "com" / "acme"
    src.mkdir(parents=True)
    sources = {
        "InputEvent.java": """
            package com.acme;
            public class InputEvent {
              public String getClientId(){ return null; }
              public String getDeviceId(){ return null; }
              public String getUcpId(){ return null; }
            }
        """,
        "Wrapper.java": """
            package com.acme;
            public class Wrapper {
              public String getClientId(){ return null; }
              public String getDeviceId(){ return null; }
              public String getUcpId(){ return null; }
              public String getReason(){ return null; }
              public Wrapper updateBy(InputEvent event){
                return toBuilder()
                    .clientId(event.getClientId())
                    .deviceId(event.getDeviceId())
                    .ucpId(event.getUcpId())
                    .build();
              }
              public Builder toBuilder(){ return new Builder(); }
              public Wrapper(){}
              public static class Builder {
                public Builder clientId(String value){ return this; }
                public Builder deviceId(String value){ return this; }
                public Builder ucpId(String value){ return this; }
                public Builder reason(String value){ return this; }
                public Wrapper build(){ return new Wrapper(); }
              }
            }
        """,
        "Batch.java": """
            package com.acme;
            import java.util.*;
            public class Batch {
              private final List<Wrapper> records = new ArrayList<>();
              public void updateActual(Wrapper record){ records.add(record); }
              public List<Wrapper> forUpdateActual(){ return records; }
            }
        """,
        "Flow.java": """
            package com.acme;
            import java.util.*;
            class Consumer {
              private Handler handler;
              @org.springframework.kafka.annotation.KafkaListener(topics="events")
              public void onReceive(InputEvent request){ handler.handle(request); }
            }
            class Handler {
              private Service service;
              public void handle(InputEvent event){
                Batch batch = new Batch();
                Wrapper current = new Wrapper();
                batch.updateActual(current.updateBy(event));
                service.changeData(batch);
              }
            }
            class Service {
              private DeviceDao dao;
              public void changeData(Batch batch){ dao.updateDeviceLink(batch.forUpdateActual()); }
            }
            class DeviceDao {
              private org.jooq.DSLContext dsl;
              public void updateDeviceLink(List<Wrapper> records){
                records.forEach(link -> dsl.update(DEVICE_LINK)
                    .set(DEVICE_LINK.CLIENT_ID, link.getClientId())
                    .set(DEVICE_LINK.DEVICE_ID, link.getDeviceId())
                    .set(DEVICE_LINK.UCP_ID, link.getUcpId())
                    .set(DEVICE_LINK.REASON, link.getReason())
                    .where(DEVICE_LINK.DEVICE_ID.eq(link.getDeviceId()))
                    .execute());
              }
            }
        """,
    }
    for name, text in sources.items():
        (src / name).write_text(text, encoding="utf-8")

    facts, status = build_java_persistence_lineage_facts(scan_files(tmp_path), deep=True)
    lineages = [
        fact.properties
        for fact in facts
        if fact.fact_type == "source_to_storage_lineage"
        and fact.properties.get("storage_target") == "DEVICE_LINK"
        and fact.properties.get("source_operation") == "Consumer.onReceive"
    ]
    mappings = {(item.get("source_field"), item.get("storage_field")) for item in lineages}
    assert ("clientId", "CLIENT_ID") in mappings
    assert ("deviceId", "DEVICE_ID") in mappings
    assert ("ucpId", "UCP_ID") in mappings
    # ``reason`` is a field of the downstream wrapper, not of InputEvent.
    # It must not be relabelled as an external ingress field merely because
    # the same wrapper is persisted together with fields that came from input.
    assert ("reason", "REASON") not in mappings
    assert all(item.get("source_kind") == "kafka_consumed" for item in lineages)
    assert all(item.get("lineage_status") == "confirmed" for item in lineages)
    from code_analyzer_core.navigation import _source_to_storage_lineage_brief_from_fact
    compact_items = [
        _source_to_storage_lineage_brief_from_fact(fact)
        for fact in facts
        if fact.fact_type == "source_to_storage_lineage"
        and fact.properties.get("storage_target") == "DEVICE_LINK"
        and fact.properties.get("source_operation") == "Consumer.onReceive"
    ]
    assert all(item and item.get("lineage_status") == "confirmed" for item in compact_items)
    assert all(item.get("missing_links") == [] for item in lineages)
    assert all(item.get("source_to_storage_segment", {}).get("status") == "confirmed" for item in lineages)
    assert all(
        mapping.get("mapping_status") == "confirmed"
        for item in lineages
        for mapping in item.get("source_to_saved_field_mappings") or []
    )
    assert status["promoted_custom_dao_mutation_count"] >= 1

    unresolved_requests = [
        fact.properties
        for fact in facts
        if fact.fact_type == "source_inspection_request"
        and fact.properties.get("reason") == "dao_implementation_not_resolved"
        and fact.properties.get("target_operation") == "Service.changeData"
    ]
    assert unresolved_requests == []


def test_interprocedural_index_recovers_inherited_and_template_method_dispatch(tmp_path: Path) -> None:
    from collections import defaultdict

    from code_analyzer_core.scanners.java_call_observations import _build_call_facts, _build_method_index
    from code_analyzer_core.scanners.java_persistence_lineage import (
        _builder_field_mapping_facts,
        _detect_origins,
        _interprocedural_index,
    )

    src = tmp_path / "src" / "main" / "java" / "com" / "acme"
    src.mkdir(parents=True)
    sources = {
        "BaseHandler.java": """
            package com.acme;
            abstract class BaseHandler<T> {
              public void handle(T request) { dispatch(request); }
              private void dispatch(T request) { handleConcrete(request); }
              protected abstract void handleConcrete(T request);
            }
        """,
        "ConcreteHandler.java": """
            package com.acme;
            class ConcreteHandler extends BaseHandler<Input> {
              protected void handleConcrete(Input request) { new Service().save(request); }
            }
        """,
        "Caller.java": """
            package com.acme;
            class Caller {
              private ConcreteHandler handler;
              void run(Input request) { handler.handle(request); }
            }
            class Input {}
            class Service { void save(Input input) {} }
        """,
    }
    files: list[Path] = []
    for name, text in sources.items():
        path = src / name
        path.write_text(text, encoding="utf-8")
        files.append(path)

    methods, class_fields, class_infos, _warnings = _build_method_index(files)
    calls = _build_call_facts(methods, class_fields, class_infos)
    origins_by_operation: dict[str, list[dict]] = defaultdict(list)
    for origin in _detect_origins(methods):
        origins_by_operation[str(origin.get("operation") or "")].append(origin)
    variants = [
        variant
        for info in class_infos.values()
        for variant in info.get("method_variants", [])
        if isinstance(variant, dict)
    ]
    index = _interprocedural_index(
        methods=methods,
        class_infos=class_infos,
        calls=calls,
        origins_by_operation=origins_by_operation,
        builder_field_mapping_facts=_builder_field_mapping_facts(methods, method_variants=variants),
    )

    inherited_callers = index["reverse_calls"]["BaseHandler.handle"]
    assert any(
        call.get("caller_operation_id") == "Caller.run"
        and call.get("resolution_kind") == "inherited_method_dispatch"
        for call in inherited_callers
    )

    override_callers = index["reverse_calls"]["ConcreteHandler.handleConcrete"]
    assert any(
        call.get("caller_operation_id") == "BaseHandler.dispatch"
        and call.get("resolution_kind") == "virtual_override_dispatch"
        for call in override_callers
    )


def test_template_dispatch_context_preserves_kafka_map_projection_for_persistence(tmp_path: Path) -> None:
    """Do not borrow ingress provenance from a sibling template-method handler."""
    from collections import defaultdict

    from code_analyzer_core.scanners.java_call_observations import _build_call_facts, _build_method_index
    from code_analyzer_core.scanners.java_persistence_lineage import (
        _actual_origin_for_cross_dao,
        _builder_field_mapping_facts,
        _detect_origins,
        _interprocedural_index,
    )

    src = tmp_path / "src" / "main" / "java" / "com" / "acme"
    src.mkdir(parents=True)
    sources = {
        "Model.java": """
            package com.acme;
            import java.util.*;
            class InputEvent { String getPhone(){return null;} Phone getPhoneData(){return null;} }
            class Phone { Operator getOperator(){return null;} }
            class Operator { String getOperatorId(){return null;} }
            class PhoneWithoutOper {
              String getPhone(){return null;} String getOperator(){return null;}
              void setOperator(String value){}
            }
            class PhoneRecord {
              String getPhonenumber(){return null;} String getOperatorId(){return null;}
              void setOperatorid(String value){}
            }
            class OtherRequest { String getOperator(){return null;} }
            enum Kind { MNP, OTHER }
        """,
        "BaseHandler.java": """
            package com.acme;
            abstract class BaseHandler<T> {
              public void handle(T request, Kind kind){ doHandleByDal(request, kind); }
              private void doHandleByDal(T request, Kind kind){ handleByDal(request); }
              protected abstract void handleByDal(T request);
            }
        """,
        "MnpFlow.java": """
            package com.acme;
            import java.util.*;
            import java.util.stream.*;
            class MnpConsumer {
              private PhoneHandler handler;
              @org.springframework.kafka.annotation.KafkaListener(topics="mnp")
              void onReceive(List<InputEvent> events){
                Map<String,String> values = events.stream().collect(Collectors.toMap(
                    e -> e.getPhone(), e -> e.getPhoneData().getOperator().getOperatorId()));
                update(values);
              }
              void update(Map<String,String> values){
                List<PhoneWithoutOper> rows = new ArrayList<>();
                String newOperatorId = values.get("phone");
                PhoneWithoutOper row = new PhoneWithoutOper();
                row.setOperator(newOperatorId);
                rows.add(row);
                handler.handle(rows, Kind.MNP);
              }
            }
            class PhoneHandler extends BaseHandler<List<PhoneWithoutOper>> {
              private OperatorService service;
              protected void handleByDal(List<PhoneWithoutOper> rows){ service.update(rows); }
            }
            class OperatorService {
              private PhoneDao dao;
              void update(List<PhoneWithoutOper> rows){
                Map<String,String> operatorMap = rows.stream().collect(Collectors.toMap(
                    PhoneWithoutOper::getPhone, PhoneWithoutOper::getOperator));
                List<PhoneRecord> records = dao.load();
                records.forEach(p -> p.setOperatorid(operatorMap.get(p.getPhonenumber())));
                dao.updatePhones(records);
              }
            }
            class PhoneDao { List<PhoneRecord> load(){return null;} void updatePhones(List<PhoneRecord> rows){} }
        """,
        "OtherFlow.java": """
            package com.acme;
            @org.springframework.web.bind.annotation.RestController
            class AOtherController {
              private OtherHandler handler;
              @org.springframework.web.bind.annotation.PostMapping("/other")
              void change(OtherRequest request){ handler.handle(request, Kind.OTHER); }
            }
            class OtherHandler extends BaseHandler<OtherRequest> {
              protected void handleByDal(OtherRequest request){}
            }
        """,
    }
    files: list[Path] = []
    for name, text in sources.items():
        path = src / name
        path.write_text(text, encoding="utf-8")
        files.append(path)

    methods, class_fields, class_infos, _warnings = _build_method_index(files)
    calls = _build_call_facts(methods, class_fields, class_infos)
    origins_by_operation: dict[str, list[dict]] = defaultdict(list)
    for origin in _detect_origins(methods):
        origins_by_operation[str(origin.get("operation") or "")].append(origin)
    variants = [
        variant
        for info in class_infos.values()
        for variant in info.get("method_variants", [])
        if isinstance(variant, dict)
    ]
    index = _interprocedural_index(
        methods=methods,
        class_infos=class_infos,
        calls=calls,
        origins_by_operation=origins_by_operation,
        builder_field_mapping_facts=_builder_field_mapping_facts(methods, method_variants=variants),
    )

    origin = _actual_origin_for_cross_dao(
        "records",
        dao_source_object="p",
        dao_source_field="operatorId",
        caller_mi=methods["OperatorService.update"],
        variable_origins={},
        ingress_by_param={},
        interprocedural_index=index,
    )

    assert origin["source_kind"] == "kafka_consumed"
    assert origin["source_operation"] == "MnpConsumer.onReceive"
    assert origin["source_payload"] in {"InputEvent", "List"}
    assert origin["source_field"] == "phoneData.operator.operatorId"
    assert origin["source_operation"] != "AOtherController.change"


def test_multitable_jooq_builder_projection_reaches_rest_with_physical_field_owner(tmp_path: Path) -> None:
    from code_analyzer_core.scanners.java_call_observations import (
        _build_call_facts,
        _build_method_index,
        _build_storage_facts,
    )
    from code_analyzer_core.scanners.java_persistence_lineage import (
        _build_stored_data_access_facts,
        _extract_all_schema_fields,
    )

    src = tmp_path / "src" / "main" / "java" / "com" / "acme"
    src.mkdir(parents=True)
    sources = {
        "Model.java": """
            package com.acme;
            import java.util.*;
            class Profile {
              String operatorId;
              static Builder builder(){return new Builder();}
              static class Builder { Builder operatorId(String value){return this;} Profile build(){return new Profile();} }
            }
            class ProfilesResponse { Set<Profile> profiles; ProfilesResponse(Set<Profile> value){profiles=value;} }
        """,
        "Dao.java": """
            package com.acme;
            import java.util.*;
            class Dao {
              private org.jooq.DSLContext dsl;
              Map<Long, Profile> load(){
                return dsl.select(LINK.ID, PHONE.OPERATORID)
                    .from(LINK).join(PHONE).on(PHONE.ID.eq(LINK.PHONE_ID))
                    .fetchMap(LINK.ID, r -> Profile.builder()
                        .operatorId(r.getValue(PHONE.OPERATORID)).build());
              }
            }
        """,
        "Controller.java": """
            package com.acme;
            import java.util.*;
            @org.springframework.web.bind.annotation.RestController
            class Controller {
              private Dao dao;
              @org.springframework.web.bind.annotation.GetMapping("/profiles")
              ProfilesResponse profiles(){ return new ProfilesResponse(new HashSet<>(dao.load().values())); }
            }
        """,
    }
    files: list[Path] = []
    for name, text in sources.items():
        path = src / name
        path.write_text(text, encoding="utf-8")
        files.append(path)

    methods, class_fields, class_infos, _warnings = _build_method_index(files)
    accesses = _build_storage_facts(methods)
    calls = _build_call_facts(methods, class_fields, class_infos)
    schema_fields = _extract_all_schema_fields(files)
    facts, _counts = _build_stored_data_access_facts(
        methods,
        class_fields,
        accesses,
        schema_fields,
        calls=calls,
    )

    lineages = [
        fact.properties
        for fact in facts
        if fact.fact_type == "storage_to_access_lineage"
        and fact.properties.get("source_storage_object") == "PHONE"
        and fact.properties.get("access_boundary") == "Controller.profiles"
        and fact.properties.get("lineage_status") == "confirmed"
    ]
    assert len(lineages) == 1
    assert lineages[0]["field_mappings"] == [{
        "storage_field": "OPERATORID",
        "storage_field_ref": "PHONE.OPERATORID",
        "record_type": "Record",
        "record_field": "oPERATORID",
        "response_container": "Profile",
        "response_field": "profiles.operatorId",
        "mapping_type": "jooq_record_getter_to_builder_field",
        "evidence_level": "confirmed_by_static_analysis",
        "response_or_payload_type": "ProfilesResponse",
    }]


def test_factory_method_reference_preserves_nested_request_fields_through_to_map(tmp_path: Path) -> None:
    from collections import defaultdict

    from code_analyzer_core.scanners.java_call_observations import (
        _build_call_facts,
        _build_method_index,
        _detect_origins,
    )
    from code_analyzer_core.scanners.java_persistence_lineage import (
        _builder_field_mapping_facts,
        _factory_method_mapping_facts,
        _interprocedural_index,
        _stream_to_map_projection,
    )

    src = tmp_path / "src" / "main" / "java" / "com" / "acme"
    src.mkdir(parents=True)
    sources = {
        "Request.java": """
            package com.acme;
            class Request { Card getData(){ return null; } }
            class Card {
              String getFinancialProductId(){ return null; }
              String getEpkId(){ return null; }
              String getProductCode(){ return null; }
              String getPan(){ return null; }
            }
            class CardUpdate {
              void setAccount(String value){}
              void setUcpId(java.math.BigInteger value){}
              void setProductId(String value){}
            }
        """,
        "Processor.java": """
            package com.acme;
            import java.math.BigInteger;
            import java.util.*;
            import java.util.stream.*;
            class Processor {
              void process(List<Request> requests) {
                Map<String, CardUpdate> updates = requests.stream()
                  .collect(Collectors.toMap(r -> r.getData().getPan(), this::createCardUpdate, (a, b) -> b));
                save(updates);
              }
              private CardUpdate createCardUpdate(Request req) {
                Card card = req.getData();
                CardUpdate update = new CardUpdate();
                update.setAccount(card.getFinancialProductId());
                update.setUcpId(Optional.ofNullable(card.getEpkId()).map(BigInteger::new).orElse(null));
                update.setProductId(req.getData().getProductCode());
                return update;
              }
              void save(Map<String, CardUpdate> updates) {}
            }
        """,
    }
    files = []
    for name, text in sources.items():
        path = src / name
        path.write_text(text, encoding="utf-8")
        files.append(path)

    methods, class_fields, class_infos, _warnings = _build_method_index(files)
    calls = _build_call_facts(methods, class_fields, class_infos)
    origins_by_operation: dict[str, list[dict]] = defaultdict(list)
    for origin in _detect_origins(methods):
        origins_by_operation[str(origin.get("operation") or "")].append(origin)
    factory_facts = _factory_method_mapping_facts(methods)
    factory = next(
        fact.properties
        for fact in factory_facts
        if fact.properties.get("operation") == "Processor.createCardUpdate"
    )
    mapped = {
        item["target_field"]: (item.get("source_object"), item.get("source_field"))
        for item in factory["field_mappings"]
    }
    assert mapped == {
        "account": ("req", "data.financialProductId"),
        "ucpId": ("req", "data.epkId"),
        "productId": ("req", "data.productCode"),
    }

    variants = [
        variant
        for info in class_infos.values()
        for variant in info.get("method_variants", [])
        if isinstance(variant, dict)
    ]
    index = _interprocedural_index(
        methods=methods,
        class_infos=class_infos,
        calls=calls,
        origins_by_operation=origins_by_operation,
        builder_field_mapping_facts=_builder_field_mapping_facts(methods, method_variants=variants),
        factory_method_mapping_facts=factory_facts,
    )
    process = methods["Processor.process"]
    assert _stream_to_map_projection(
        mi=process, map_symbol="updates", target_field="account", index=index
    ) == {
        "parameter_or_symbol": "requests",
        "source_field": "data.financialProductId",
        "projection_kind": "stream_to_map_factory_method_reference",
        "factory_parameter": "req",
    }
    assert _stream_to_map_projection(
        mi=process, map_symbol="updates", target_field="ucpId", index=index
    )["source_field"] == "data.epkId"


def test_dao_jooq_mappings_follow_unique_same_class_parameter_delegation(tmp_path: Path) -> None:
    from code_analyzer_core.scanners.java_call_observations import _build_method_index
    from code_analyzer_core.scanners.java_persistence_lineage import _dao_jooq_field_mappings

    src = tmp_path / "src" / "main" / "java" / "com" / "acme"
    src.mkdir(parents=True)
    path = src / "Dao.java"
    path.write_text(
        """
        package com.acme;
        import java.util.*;
        class Record { String getId(){return null;} long getVersion(){return 0;} }
        class Dao {
          private org.jooq.DSLContext dsl;
          void merge(Set<Record> add, Set<Record> update) {
            insertRecords(add);
            updateRecords(update);
          }
          private void insertRecords(Set<Record> add) {
            org.jooq.InsertSetMoreStep<Record> stmt = dsl.insertInto(DEMO)
              .set(DEMO.ID, org.jooq.impl.DSL.param(String.class))
              .set(DEMO.VERSION, org.jooq.impl.DSL.param(Long.class));
            org.jooq.BatchBindStep batch = dsl.batch(stmt);
            for (Record row : add) { batch.bind(row.getId(), row.getVersion()); }
            batch.execute();
          }
          private void updateRecords(Set<Record> update) {
            org.jooq.UpdateConditionStep<Record> stmt = dsl.update(DEMO)
              .set(DEMO.VERSION, org.jooq.impl.DSL.param(Long.class))
              .where(DEMO.ID.eq(org.jooq.impl.DSL.param(String.class)));
            org.jooq.BatchBindStep batch = dsl.batch(stmt);
            for (Record row : update) { batch.bind(row.getVersion(), row.getId()); }
            batch.execute();
          }
        }
        """,
        encoding="utf-8",
    )
    methods, _class_fields, _class_infos, _warnings = _build_method_index([path])
    mappings = _dao_jooq_field_mappings(methods["Dao.merge"], methods)
    pairs = {
        (item.get("source_object"), item.get("source_field"), item.get("storage_field"))
        for item in mappings
    }
    assert ("add", "id", "ID") in pairs
    assert ("add", "version", "VERSION") in pairs
    assert ("update", "version", "VERSION") in pairs
    assert all(str(item.get("mapping_kind") or "").startswith("same_class_delegate:") for item in mappings)


def test_observed_factory_and_dao_physical_facts_compose_without_name_heuristics(tmp_path: Path) -> None:
    from code_analyzer_core.models import Fact
    from code_analyzer_core.scanners.java_persistence_lineage import (
        _build_java_persistence_lineage_context,
        _compose_observed_factory_to_physical_lineage_facts,
    )
    from code_analyzer_core.scanners.repo_scanner import scan_files

    src = tmp_path / "src" / "main" / "java" / "com" / "acme"
    src.mkdir(parents=True)
    (src / "InputEvent.java").write_text(
        """
        package com.acme;
        public class InputEvent {
          public String getId(){ return null; }
          public long getVersion(){ return 0; }
        }
        """,
        encoding="utf-8",
    )
    (src / "Record.java").write_text(
        """
        package com.acme;
        public class Record {
          void setId(String value){}
          void setVersion(long value){}
          String getId(){ return null; }
          long getVersion(){ return 0; }
        }
        """,
        encoding="utf-8",
    )
    (src / "Flow.java").write_text(
        """
        package com.acme;
        import java.util.*;
        class Consumer {
          private Service service;
          @org.springframework.kafka.annotation.KafkaListener(topics="events")
          public void onReceive(List<InputEvent> requests){ service.process(requests); }
        }
        class Service {
          private Dao dao;
          public void process(List<InputEvent> requests){
            Set<Record> add = new HashSet<>();
            for (InputEvent request : requests) { add.add(createRecord(request)); }
            dao.merge(add);
          }
          private Record createRecord(InputEvent request){
            Record record = new Record();
            record.setId(request.getId());
            record.setVersion(request.getVersion());
            return record;
          }
        }
        class Dao {
          private org.jooq.DSLContext dsl;
          void merge(Set<Record> add){ insertRecords(add); }
          private void insertRecords(Set<Record> add){
            org.jooq.InsertSetMoreStep<Record> stmt = dsl.insertInto(DEMO)
              .set(DEMO.ID, org.jooq.impl.DSL.param(String.class))
              .set(DEMO.VERSION, org.jooq.impl.DSL.param(Long.class));
            org.jooq.BatchBindStep batch = dsl.batch(stmt);
            for (Record row : add) { batch.bind(row.getId(), row.getVersion()); }
            batch.execute();
          }
        }
        """,
        encoding="utf-8",
    )

    ctx = _build_java_persistence_lineage_context(scan_files(tmp_path), deep=True)
    access = next(
        item
        for item in ctx.storage_accesses
        if item.get("operation") == "Service.process" and item.get("storage_method") == "merge"
    )
    object_fact = Fact(
        fact_type="source_to_storage_lineage",
        name="InputEvent.object -> Record",
        properties={
            "source_to_storage_lineage_id": "source_to_storage_lineage_000001",
            "source_kind": "method_input",
            "source_operation": "Service.process",
            "source_payload": "InputEvent",
            "source_field": None,
            "source_payload_parameter": "requests",
            "storage_operation": "Service.process",
            "storage_access_id": access["storage_access_id"],
            "persistent_write_id": "persistent_write_000001",
            "storage_call": "dao.merge(add)",
            "storage_method": "merge",
            "saved_object": "Record",
        },
        evidence=[],
    )

    composed = _compose_observed_factory_to_physical_lineage_facts(ctx, [object_fact])
    mappings = {
        (fact.properties.get("source_operation"), fact.properties.get("source_field"),
         fact.properties.get("storage_target"), fact.properties.get("storage_field"),
         fact.properties.get("lineage_status"))
        for fact in composed
    }
    assert mappings == {
        ("Consumer.onReceive", "id", "DEMO", "ID", "confirmed"),
        ("Consumer.onReceive", "version", "DEMO", "VERSION", "confirmed"),
    }
    assert all(
        fact.properties.get("assignment_kind") == "factory_to_dao_physical_composition"
        for fact in composed
    )
