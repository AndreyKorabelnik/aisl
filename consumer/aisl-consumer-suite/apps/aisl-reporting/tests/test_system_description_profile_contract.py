from __future__ import annotations

from pathlib import Path

from aisl_reporting.contracts import ReportRequest
from aisl_reporting.profiles.system_description.v1 import builder


def _result(kind: str, *, items=(), summary=None, evidence=()):
    return {"query": {"kind": kind}, "items": list(items), "summary": dict(summary or {}), "evidence": list(evidence), "gaps": []}


class _Source:
    revision_id = "revision-1"

    def __init__(self):
        self._evidence = {
            "rest": {"evidence_id": "evidence_aaaaaaaaaaaaaaaaaaaa", "repo_id": "client_profile", "path": "client-profile-app/src/main/java/ClientProfileController.java", "line_start": 52, "line_end": 65, "maturity": "observed"},
            "out": {"evidence_id": "evidence_bbbbbbbbbbbbbbbbbbbb", "repo_id": "client_profile", "path": "client-profile-app/src/main/java/CardLifeCycleServiceImpl.java", "line_start": 28, "line_end": 33, "maturity": "observed"},
            "table": {"evidence_id": "evidence_cccccccccccccccccccc", "repo_id": "client_profile", "path": "client-profile-db/src/main/resources/db/changelog.xml", "line_start": 10, "line_end": 30, "maturity": "observed"},
            "relation": {"evidence_id": "evidence_dddddddddddddddddddd", "repo_id": "client_profile", "path": "client-profile-db/src/main/resources/db/link.sql", "line_start": 4, "line_end": 8, "maturity": "observed"},
        }

    def get_scope_overview(self):
        return _result(
            "get_scope_overview",
            items=[{
                "scope_id": "client_profile",
                "scope_type": "repository",
                "repository_ids": ["client_profile"],
                "counts": {
                    "db_schema_table": 2,
                    "db_schema_column": 12,
                    "db_schema_key": 3,
                    "db_schema_foreign_key": 1,
                    "db_schema_index": 2,
                },
            }],
        )

    def get_repository_composition(self, **_kwargs):
        return _result(
            "get_repository_composition",
            items=[{
                "repositories": [{"repo_id": "client_profile"}],
                "modules": [
                    {"repo_id": "client_profile", "module_path": "", "module_name": "client-profile"},
                    {"repo_id": "client_profile", "module_path": "client-profile-api", "module_name": "client-profile-api"},
                    {"repo_id": "client_profile", "module_path": "client-profile-app", "module_name": "client-profile-app"},
                    {"repo_id": "client_profile", "module_path": "client-profile-db", "module_name": "client-profile-db"},
                ],
            }],
        )

    def get_technologies(self, **_kwargs):
        return _result(
            "get_technologies",
            items=[
                {"kind": "build_plugin", "plugin_id": "org.springframework.boot", "version": "3.5.14"},
                {
                    "kind": "declared_dependency",
                    "coordinate": "org.springframework.kafka:spring-kafka",
                    "group_id": "org.springframework.kafka",
                    "artifact_id": "spring-kafka",
                    "configuration": "implementation",
                    "module_path": "client-profile-app",
                    "evidence_ids": ["evidence_aaaaaaaaaaaaaaaaaaaa"],
                },
            ],
            evidence=[self._evidence["rest"]],
        )

    def list_interfaces(self, **_kwargs):
        return _result(
            "list_interfaces",
            items=[{
                "interface_id": "interface_000005",
                "direction": "inbound",
                "boundary_kind": "rest_request",
                "operation": "profileByCard",
                "http_method": "POST",
                "endpoint_or_topic": "/profilesByCard",
                "request_payload_type": "ProfilesByCardRequest",
                "response_payload_type": "ProfilesByCardResponse",
                "evidence_ids": ["evidence_aaaaaaaaaaaaaaaaaaaa"],
            }],
            evidence=[self._evidence["rest"]],
        )

    def list_integrations(self, **_kwargs):
        return _result(
            "list_integrations",
            items=[{
                "interface_id": "flow_000005",
                "direction": "outbound",
                "boundary_kind": "http_outbound",
                "operation": "getPprbCardInfoByPan",
                "endpoint_or_topic": "CARD_LIFE_CYCLE_URL",
                "request_payload_type": "CardInfoByPanRq",
                "evidence_ids": ["evidence_bbbbbbbbbbbbbbbbbbbb"],
            }],
            evidence=[self._evidence["out"]],
        )

    def list_events(self, **_kwargs):
        return _result("list_events", items=[])

    def list_data_objects(self, **_kwargs):
        return _result(
            "list_data_objects",
            items=[
                {
                    "object_id": "table:mbk_cache.card",
                    "name": "card",
                    "schema": "mbk_cache",
                    "qualified_name": "mbk_cache.card",
                    "column_count": 7,
                    "key_count": 1,
                    "relationship_count": 1,
                    "selection_score": 20,
                    "evidence_ids": ["evidence_cccccccccccccccccccc"],
                },
                {
                    "object_id": "table:mbk_cache.link",
                    "name": "link",
                    "schema": "mbk_cache",
                    "qualified_name": "mbk_cache.link",
                    "column_count": 5,
                    "key_count": 2,
                    "relationship_count": 1,
                    "selection_score": 18,
                    "evidence_ids": ["evidence_cccccccccccccccccccc"],
                },
            ],
            summary={"table_count": 2},
            evidence=[self._evidence["table"]],
        )

    def list_relationships(self, **_kwargs):
        return _result(
            "list_relationships",
            items=[{
                "relationship_id": "relationship_000001",
                "left_table": "card",
                "right_table": "link",
                "join_type": "foreign_key",
                "relation_kind": "foreign_key",
                "column_pair_count": 1,
                "column_pairs": [{"left_column": "cardid", "operator": "=", "right_column": "paymentcardid"}],
                "matched_declared_keys": [
                    {"key_id": "fk_link_card", "fields": ["paymentcardid"]},
                ],
                "evidence_ids": ["evidence_dddddddddddddddddddd"],
            }],
            summary={"relationship_count": 1},
            evidence=[self._evidence["relation"]],
        )

    def get_analysis_coverage(self, **_kwargs):
        return _result(
            "get_analysis_coverage",
            items=[{
                "schema_version": "analysis_coverage/v1",
                "status": "partial",
                "statement": "Coverage describes observed facts and known limitations; absence of evidence does not prove absence in source systems.",
                "count_basis": "diagnostic_occurrences_not_unique_business_elements",
                "summary": {
                    "repository_count": 1,
                    "observed_fact_count": 120,
                    "known_gap_count": 4,
                    "unresolved_count": 4,
                    "conflicting_count": 0,
                    "unsupported_count": 0,
                    "not_observed_count": 0,
                    "requires_interpretation_count": 1,
                    "physical_join_observation_count": 1,
                },
                "domains": {
                    "source_facts": {"status": "observed", "observed_fact_count": 120},
                    "data_model": {"status": "partial", "relationship_count": 1, "unresolved_relationship_candidate_count": 1},
                    "physical_storage": {"status": "requires_interpretation", "storage_evidence_relationship_count": 1, "requires_interpretation_count": 1, "physical_join_observation_count": 1},
                    "analysis_gaps": {"status": "observed", "known_gap_count": 4, "status_counts": {"unresolved": 4}},
                },
                "limitations": [],
                "limitations_total_groups": 0,
                "limitations_truncated": False,
            }],
        )

    def get_gap_summary(self, **_kwargs):
        return _result(
            "get_gap_summary",
            items=[{"missing_fact_kind": "field_mapping_not_resolved", "count": 4}],
            summary={"gap_count": 4},
        )

    def get_representative_journeys(self, **_kwargs):
        return _result(
            "get_representative_journeys",
            items=[{
                "journey_id": "scenario_000001",
                "operation": "profileByCard",
                "entrypoints": ["ClientProfileController.profileByCard"],
                "external_calls": [],
                "storage_touches": [{"table": "mbk_cache.card"}],
                "is_complete": False,
            }],
            summary={"scenario_count": 1},
        )


    def query_system_description(self, query_kind: str, *, filters=None, max_results: int = 100):
        dispatch = {
            "get_scope_overview": self.get_scope_overview,
            "get_repository_composition": self.get_repository_composition,
            "get_technologies": self.get_technologies,
            "list_interfaces": self.list_interfaces,
            "list_integrations": self.list_integrations,
            "list_events": self.list_events,
            "list_data_objects": self.list_data_objects,
            "list_relationships": self.list_relationships,
            "get_analysis_coverage": self.get_analysis_coverage,
            "get_gap_summary": self.get_gap_summary,
            "get_representative_journeys": self.get_representative_journeys,
        }
        kwargs = dict(filters or {})
        if query_kind != "get_scope_overview":
            kwargs["max_results"] = max_results
        return dispatch[query_kind](**kwargs)


def test_system_description_dataset_contains_rich_structured_material(tmp_path):
    request = ReportRequest(
        report_type="system-description",
        report_version="v1",
        api_url="http://knowledge-api.test",
        system_id="fixture",
        knowledge_source=_Source(),
        audience="business",
    )

    dataset = builder.build_dataset(request)

    assert "quality_expectations" not in dataset
    assert dataset["audience_policy"]["preferred_opening"].startswith("Сначала самостоятельное бизнес-описание")
    assert dataset["audience_policy"]["opening_contract"]["heading"] == "О системе"
    assert dataset["report_blueprint"]["required_sections"][0] == "О системе"
    assert dataset["sections"]["functional_capabilities"]["clusters"]
    assert dataset["sections"]["system_boundaries"]["inbound_items"][0]["interface_id"] == "interface_000005"
    assert dataset["sections"]["interface_map"]["items"][0]["provenance"][0]["display"].endswith(":52–65")
    assert dataset["sections"]["journeys"]["items"][0]["journey_id"] == "scenario_000001"
    assert dataset["sections"]["diagrams"]["system_boundary"]["edges"]
    assert dataset["sections"]["diagrams"]["data_relationships"]["edges"][0]["kind"] == "explicit_foreign_key"
    assert dataset["sections"]["data_and_storage"]["explicit_relationships"][0]["matched_declared_keys"] == [
        {"key_id": "fk_link_card", "fields": ["paymentcardid"]},
    ]
    roles = {item["module_path"]: item["role_hint"] for item in dataset["sections"]["project_structure"]["modules"]}
    assert "API-контракты" in roles["client-profile-api"]
    assert "runtime-приложение" in roles["client-profile-app"]
    assert "схема данных" in roles["client-profile-db"]
    assert dataset["coverage"]["analysis_coverage"]["status"] == "partial"
    assert dataset["coverage"]["analysis_coverage"]["summary"]["unresolved_count"] == 4
    assert dataset["evidence_index"]


def test_renderer_contract_has_no_subjective_legacy_score():
    profile_dir = Path(builder.__file__).parent
    prompt = (profile_dir / "renderer-prompt.md").read_text(encoding="utf-8")
    rules = (profile_dir / "quality-rules.yaml").read_text(encoding="utf-8")

    assert "legacy baseline" not in prompt
    assert "quality_expectations" not in prompt
    assert "warn_on_underfilled_report" not in rules
    assert "final_response.json" not in prompt
    assert "### Основные сценарии" in prompt
    assert "# О системе" in prompt
    assert "В бизнес-вступлении evidence-ссылки запрещены" in prompt
    assert "детали находятся в приложении A" in prompt
    assert "Mermaid" in prompt
    assert "coverage.analysis_coverage" in prompt
    assert "not_observed" in prompt


def test_relationship_deduplication_supports_structured_declared_keys():
    relationship = {
        "left_table": "card",
        "right_table": "link",
        "join_type": "foreign_key",
        "relation_kind": "foreign_key",
        "column_pair_count": 1,
        "column_pairs": [{"left_column": "cardid", "operator": "=", "right_column": "paymentcardid"}],
        "evidence_ids": ["evidence_1"],
        "matched_declared_keys": [
            {"key_id": "fk_link_card", "fields": ["paymentcardid"]},
        ],
    }
    duplicate = {
        **relationship,
        "evidence_ids": ["evidence_2"],
        "matched_declared_keys": [
            {"fields": ["paymentcardid"], "key_id": "fk_link_card"},
            {"key_id": "fk_link_account", "fields": ["accountid"]},
        ],
    }

    result = builder._deduplicate_relationships([relationship, duplicate])

    assert len(result) == 1
    assert result[0]["evidence_ids"] == ["evidence_1", "evidence_2"]
    assert result[0]["matched_declared_keys"] == [
        {"key_id": "fk_link_account", "fields": ["accountid"]},
        {"key_id": "fk_link_card", "fields": ["paymentcardid"]},
    ]


def test_relationship_deduplication_keeps_scalar_declared_key_compatibility():
    item = {
        "left_table": "card",
        "right_table": "link",
        "join_type": "foreign_key",
        "column_pair_count": 1,
        "column_pairs": [{"left_column": "cardid", "operator": "=", "right_column": "paymentcardid"}],
        "matched_declared_keys": ["fk_link_card", "fk_link_card"],
    }

    result = builder._deduplicate_relationships([item])

    assert result[0]["matched_declared_keys"] == ["fk_link_card"]


def test_semantic_grouping_excludes_transport_and_schema_tokens():
    interfaces = [
        {
            "interface_id": "in-card",
            "operation": "receiveCardMessage",
            "endpoint_or_topic": "${kafka.card.topic.name}",
            "request_payload_type": "CardUpdateMessage",
            "evidence_ids": ["evidence_in"],
        },
        {
            "interface_id": "in-profile",
            "operation": "getProfileByCard",
            "endpoint_or_topic": "/profiles/by-card",
            "request_payload_type": "ProfileByCardRequest",
            "evidence_ids": ["evidence_profile"],
        },
    ]
    integrations = [
        {
            "interface_id": "out-card",
            "operation": "sendCardNotification",
            "endpoint_or_topic": "${kafka.card.notification.topic.name}",
            "request_payload_type": "CardNotificationMessage",
            "evidence_ids": ["evidence_out"],
        },
    ]
    data_objects = [
        {"object_id": "card", "name": "card", "qualified_name": "mbk_cache.card"},
        {"object_id": "card_history", "name": "card_history", "qualified_name": "mbk_cache.card_history"},
        {"object_id": "profile", "name": "profile", "qualified_name": "mbk_cache.profile"},
    ]

    clusters = builder._semantic_clusters(interfaces, integrations, data_objects, limit=8)
    labels = {item["label_hint"] for item in clusters}
    groups = builder._data_groups(data_objects)
    group_labels = {item["group_hint"] for item in groups}

    assert "card" in labels
    assert "profile" in labels
    assert not labels.intersection({"topic", "name", "message", "receive", "send", "mbk", "cache"})
    assert "card" in group_labels
    assert not group_labels.intersection({"mbk", "cache", "table", "таблица"})
    assert next(item for item in groups if item["group_hint"] == "card")["overlap_policy"] == "allowed"
