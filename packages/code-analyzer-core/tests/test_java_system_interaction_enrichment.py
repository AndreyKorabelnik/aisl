from __future__ import annotations

import json
from pathlib import Path

import yaml

from code_analyzer_core.analysis_profiles import load_analysis_profile, profile_stage_ids

from code_analyzer_core.scanners.config_scanner import scan_config_files
from code_analyzer_core.scanners.java_interaction_enrichment import scan_java_system_interaction_evidence
from code_analyzer_core.scanners.java_scanner import scan_java_files


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_json_config_is_flattened_as_source_observed_properties(tmp_path: Path) -> None:
    cfg = _write(
        tmp_path / "base-config.json",
        json.dumps({"client": {"url": "http://service", "path": "/do"}}),
    )
    facts = scan_config_files([cfg])
    values = {fact.name: fact.properties["value"] for fact in facts if fact.fact_type == "config_property"}
    assert values["client.url"] == "http://service"
    assert values["client.path"] == "/do"


def test_parameter_catalog_json_emits_canonical_property_key(tmp_path: Path) -> None:
    cfg = _write(
        tmp_path / "base-config.json",
        json.dumps({
            "parameters": [
                {"client.path": {"stringValue": {"default": "/from-catalog"}}}
            ]
        }),
    )
    facts = scan_config_files([cfg])
    matches = [fact for fact in facts if fact.fact_type == "config_property" and fact.name == "client.path"]
    assert len(matches) == 1
    assert matches[0].properties["value"] == "/from-catalog"
    assert matches[0].properties["configuration_structure"] == "parameter_catalog_default"


def test_deep_interaction_stage_composes_direct_helper_and_armeria_evidence(tmp_path: Path) -> None:
    app = _write(
        tmp_path / "src/main/resources/application.yml",
        """
client:
  url: http://service
  direct-path: /direct
  helper-path: /helper
""",
    )
    java = _write(
        tmp_path / "src/main/java/example/App.java",
        r'''
package example;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.web.client.RestTemplate;

class Constants {
    static final String BASE = "/base";
    static final String NAME = "search";
    static final String METHOD = "/" + NAME;
}

interface SearchService {}
class SearchServiceImpl implements SearchService {
    @Post(Constants.METHOD)
    public ResponseDto run(AggregatedHttpRequest request) {
        RequestDto dto = jsonConverter.deserialize(request, RequestDto.class);
        return new ResponseDto();
    }
}

class ServerConfig {
    private SearchService service;
    void configure() {
        builder.annotatedService(Constants.BASE, service, decorator);
    }
}

class ClientConfig {
    @Value("${client.url}") private String clientUrl;
    @Bean RestTemplate clientRestTemplate() {
        return clientRestTemplate(clientUrl);
    }
}

class Helper {
    static ResponseDto send(RequestDto request, RestTemplate restTemplate, String path) {
        HttpEntity<RequestDto> entity = new HttpEntity<>(request);
        return restTemplate.exchange(path, HttpMethod.POST, entity, ResponseDto.class).getBody();
    }
}

class Caller {
    @Value("${client.direct-path}") private String directPath;
    @Value("${client.helper-path}") private String helperPath;
    private RestTemplate client;

    Caller(@Qualifier("clientRestTemplate") RestTemplate client) {
        this.client = client;
    }

    ResponseDto direct(RequestDto request) {
        HttpEntity<RequestDto> entity = new HttpEntity<>(request);
        return client.exchange(directPath, HttpMethod.POST, entity, ResponseDto.class).getBody();
    }

    ResponseDto composed(RequestDto request) {
        return Helper.send(request, client, helperPath);
    }
}

class Facade {
    private Caller caller;
    ResponseDto scenario(RequestDto request) { return caller.direct(request); }
    RequestDto prepare() { RequestDto dto = RequestDto.builder().id("x").build(); return dto; }
}
class RequestDto { String id; static Builder builder() { return null; } }
class Builder { Builder id(String value) { return this; } RequestDto build() { return null; } }
class ResponseDto { String status; }
''',
    )
    files = [app, java]
    config_facts = scan_config_files(files)
    java_facts, schemas, interfaces, _, _, _ = scan_java_files(files)

    facts, _, warnings, coverage = scan_java_system_interaction_evidence(
        files,
        config_facts=config_facts,
        schemas=schemas,
        interfaces=interfaces,
    )

    assert not warnings
    assert coverage["http_outbound_composed_calls"] == 1
    assert coverage["http_service_registrations"] == 1

    production = [item for item in interfaces if not (item.properties or {}).get("is_test_source")]
    direct = next(item for item in production if item.operation == "Caller.direct" and item.direction.value == "outbound")
    assert direct.path == "/direct"
    assert direct.method == "POST"
    assert direct.properties["base_url_observed_values"] == ["http://service"]
    assert direct.properties["endpoint_url_variants"] == ["http://service/direct"]
    assert direct.properties["request_payload_type"] == "RequestDto"
    assert direct.properties["response_payload_type"] == "ResponseDto"
    assert direct.properties["local_caller_operations"] == ["Facade.scenario"]
    assert direct.properties["request_observed_builder_setters"] == ["id"]

    helper = next(item for item in production if item.operation == "Caller.composed" and item.direction.value == "outbound")
    assert helper.path == "/helper"
    assert helper.properties["composition_basis"] == "helper_method_template_and_concrete_call_site"
    assert helper.properties["helper_operation"] == "Helper.send"
    assert helper.properties["endpoint_url_variants"] == ["http://service/helper"]

    # The helper implementation itself is a template, not a concrete boundary.
    assert not any(item.operation == "Helper.send" and item.direction.value == "outbound" for item in production)

    inbound = next(item for item in production if item.operation == "SearchServiceImpl.run" and item.direction.value == "inbound")
    assert inbound.path == "/base/search"
    assert inbound.properties["method_path_variants"] == ["/search"]
    assert inbound.properties["registration_base_path_variants"] == ["/base"]
    assert inbound.properties["request_payload_type"] == "RequestDto"

    fact_types = {fact.fact_type for fact in facts}
    assert "configuration_value_binding" in fact_types
    assert "http_outbound_binding" in fact_types
    assert "http_outbound_helper_template" in fact_types
    assert "http_outbound_call_composed" in fact_types
    assert "http_service_registration" in fact_types
    assert "http_inbound_endpoint_registration" in fact_types


def test_topology_profile_runs_interaction_enrichment_after_structural_scan() -> None:
    root = Path(__file__).resolve().parents[1] / "analysis-profiles"
    profile = load_analysis_profile(root / "repository-portfolio-topology.yaml")
    stages = profile_stage_ids(profile)
    assert "java_system_interaction_enrichment" in stages
    assert stages.index("java_system_interaction_enrichment") > stages.index("java_structural_scan")


def test_contract_signature_filters_generated_constants_and_supports_builder_fallback() -> None:
    from code_analyzer_core.models import FieldInfo, SchemaInfo
    from code_analyzer_core.navigation import _observed_builder_signature, _schema_contract_signature

    schemas = {
        "RequestDto": SchemaInfo(
            name="RequestDto",
            fields=[
                FieldInfo(name="SERIALIZED_NAME_ID", type="String"),
                FieldInfo(name="id", type="String"),
            ],
        )
    }
    signature = _schema_contract_signature(schemas, "RequestDto")
    assert [item["attribute_path"] for item in signature] == ["id"]
    assert [item["attribute_path"] for item in _observed_builder_signature(["phone", "sberProfileId"])] == ["phone", "sberProfileId"]


def test_interface_catalog_recovers_path_variants_from_all_observed_config_values() -> None:
    from code_analyzer_core.navigation import _system_interface_catalog_item

    item = {
        "id": "if-1",
        "direction": "outbound",
        "kind": "rest",
        "name": "updateOrCreateLightClientPath",
        "operation": "CreateLightClientServiceImpl.createProfileByNewLogic",
        "path": "updateOrCreateLightClientPath",
        "method": "POST",
        "schema_ref": "UpdateProfileInfoResponse",
        "properties": {
            "boundary_role": "http_outbound",
            "endpoint_path_property_key": "sbpr.ucp-integration.ucp.update-or-create-light-client.path",
            "request_payload_type": "UpdateProfileInfoRequest",
            "response_payload_type": "UpdateProfileInfoResponse",
        },
        "evidence": [],
    }
    row = _system_interface_catalog_item(
        item,
        schema_by_name={},
        config_values={
            "sbpr.ucp-integration.ucp.update-or-create-light-client.path": [
                "/UpdateOrCreate",
                "/ucp/updateOrCreate",
            ]
        },
    )
    assert row["endpoint_path_observed_values"] == ["/UpdateOrCreate", "/ucp/updateOrCreate"]
    assert row["endpoint_path_variants"] == ["/UpdateOrCreate", "/ucp/updateOrCreate"]


def test_normalized_fact_store_keeps_interaction_enrichment_properties() -> None:
    from code_analyzer_core.normalizer import _slim_properties

    props = _slim_properties({
        "scenario_operation": "CreateLightClientServiceImpl.createProfileByNewLogic",
        "helper_operation": "RestTemplateUcpUpdateOrCreateSender.send",
        "endpoint_path_property_key": "sbpr.ucp-integration.ucp.update-or-create-light-client.path",
        "endpoint_path_observed_values": ["/UpdateOrCreate", "/ucp/updateOrCreate"],
        "request_observed_builder_setters": ["sberProfileId", "ucpId"],
        "property_key": "sbpr.ucp-integration.ucp.update-or-create-light-client.path",
        "observed_values": ["/UpdateOrCreate", "/ucp/updateOrCreate"],
    })
    assert props["scenario_operation"].endswith("createProfileByNewLogic")
    assert props["endpoint_path_observed_values"] == ["/UpdateOrCreate", "/ucp/updateOrCreate"]
    assert props["request_observed_builder_setters"] == ["sberProfileId", "ucpId"]
    assert props["property_key"].endswith("update-or-create-light-client.path")
