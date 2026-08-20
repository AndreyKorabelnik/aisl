from __future__ import annotations

import httpx

from aisl_reporting.contracts import ReportRequest
from aisl_reporting.pipeline import prepare_report
from aisl_reporting.profile import load_profile


def _transport(request: httpx.Request) -> httpx.Response:
    path=request.url.path; params=dict(request.url.params)
    if path == "/api/knowledge/v1/systems/model-a/revisions/rev-1":
        return httpx.Response(200,json={
            "system_id":"model-a","revision_id":"rev-1","capabilities":["common.code-declared-data-model","common.model-storage-semantics","common.logical-storage-mapping"],
            "knowledge_artifacts":[{"artifact_id":"declared","model_kind":"code-declared-data-model","schema_version":"code-declared-data-model/v1","capabilities":["common.code-declared-data-model"],"physical_artifacts":[],"content_fingerprint":"a"*64}],
            "execution":{"scope_kind":"repositories"}
        })
    if path == "/api/knowledge/v1/systems/model-a/data-model/declared-summary":
        return httpx.Response(200,json={"build":{"build_status":"complete"},"counts":{"type_count":1,"effective_field_count":2,"relationship_count":1,"gap_count":0},"type_annotation_counts":[],"field_annotation_counts":[],"gap_counts":[]})
    if path == "/api/knowledge/v1/systems/model-a/data-model/declared-objects":
        if params.get("search"):
            return httpx.Response(200,json={"items":[],"page":{"offset":0,"limit":100,"total":0}})
        return httpx.Response(200,json={"items":[{"object_id":"o1","repo_id":"repo","fqcn":"com.acme.Individual","name":"Individual","package_name":"com.acme","type_kind":"class","source_set":"main","documentation":{"display_name":"Физическое лицо"},"annotations":[{"annotation_name":"MetaRootEntity"}],"field_count":2,"relationship_count":1,"binding_summary":{"incoming_relationship_count":0},"source_ref":{"repository_relative_path":"Individual.java","line_start":1,"line_end":20,"extractor":"java"}}],"page":{"offset":0,"limit":100,"total":1}})
    if path == "/api/knowledge/v1/systems/model-a/data-model/object-context/o1":
        return httpx.Response(200,json={
            "object":{"object_id":"o1","repo_id":"repo","fqcn":"com.acme.Individual","name":"Individual","package_name":"com.acme","type_kind":"class","source_set":"main","documentation":{"display_name":"Физическое лицо"},"annotations":[],"source_ref":{"repository_relative_path":"Individual.java","line_start":1,"line_end":20},"inheritance":[]},
            "fields":[{"name":"birthCountry","declared_type_expression":"Country","is_inherited":False,"inherited_depth":0,"documentation":{"summary":"Страна рождения"},"annotations":[],"source_ref":{"repository_relative_path":"Individual.java","line_start":5,"line_end":5}}],
            "relationships":[{"source_field":"birthCountry","declared_relationship":{"declared_type_expression":"Country"},"target":{"fqcn":"com.acme.Country","resolution_status":"resolved"},"cardinality":"one","storage_semantics":{"status":"ambiguous","basis":"conflicting_confirmed_observations","candidate_mappings":[{"knowledge_class":"confirmed","mapping_status":"matched","storage_key_expression":"Country_ + code"},{"knowledge_class":"confirmed","mapping_status":"matched","storage_key_expression":"CountryById_ + id"}],"reference_value_derivations":[]},"physical_mapping":{"status":"not_observed","physical_join_confirmed":False}}],
            "storage_identities":[],"storage_context":{"status":"available","published_optional_capabilities":["common.model-storage-semantics","common.logical-storage-mapping"]},"gaps":[]
        })
    return httpx.Response(404,json={"path":path})


def test_profile_has_explicit_declared_model_requirement() -> None:
    profile=load_profile("declared-data-model-report/v1")
    req=profile.knowledge_requirement
    assert req is not None
    assert req.model_kind == "code-declared-data-model"
    assert req.required_capabilities == ("common.code-declared-data-model",)
    assert req.optional_capabilities == ("common.model-storage-semantics","common.logical-storage-mapping")


def test_dataset_preserves_storage_ambiguity_and_no_physical_join() -> None:
    request=ReportRequest(report_type="declared-data-model-report",report_version="v1",api_url="http://knowledge.test",system_id="model-a",revision_id="rev-1",api_transport=httpx.MockTransport(_transport))
    prepared=prepare_report(request, heartbeat_sec=0)
    data=prepared.dataset
    assert data["coverage"]["catalog_complete_against_summary"] is True
    rel=data["sections"]["detailed_objects"][0]["relationships"][0]
    assert rel["storage_status"] == "ambiguous"
    assert len(rel["storage_candidates"]) == 2
    assert rel["physical_status"] == "not_observed"
    assert rel["physical_join_confirmed"] is False
    assert data["interpretation_policy"]["physical_mapping"].startswith("No physical SQL/PDM join")
