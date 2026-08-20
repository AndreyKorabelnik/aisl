from pathlib import Path

from code_analyzer_core.models import AnalysisResult
from code_analyzer_core.navigation import build_navigation
from code_analyzer_core.scanners.java_scanner import scan_java_files
from code_analyzer_core.scanners.repo_scanner import scan_files
from code_analyzer_core.scanners.sql_scanner import scan_sql_files
from code_analyzer_core.scanners.system_description_enrichment import build_system_description_enrichment_facts


def test_java_schema_annotations_feed_data_dictionary_and_interface_descriptions(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    src = repo / "src/main/java/com/acme"
    src.mkdir(parents=True)
    (src / "ReviewController.java").write_text(
        '''
package com.acme;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.*;
import org.springframework.web.bind.annotation.*;

@Schema(description = "Отзыв пользователя")
class ReviewRequest {
  @Schema(description = "Рейтинг от 1 до 5", example = "5")
  @Min(1) @Max(5)
  Integer rating;
}

@RestController
@RequestMapping("/v1/review")
class ReviewController {
  @Operation(summary = "Создание отзыва")
  @PostMapping("/create")
  ReviewRequest create(@RequestBody ReviewRequest request) { return request; }
}
''',
        encoding="utf-8",
    )
    facts, schemas, interfaces, relations, mapper_facts, warnings = scan_java_files(scan_files(repo))
    result = AnalysisResult(system_name="S", project_code="P", repo_path=str(repo), facts=facts, schemas=schemas, interfaces=interfaces)
    enrich, status = build_system_description_enrichment_facts(result)
    all_facts = facts + enrich
    dictionary = [f for f in all_facts if f.fact_type == "data_dictionary_entry"]
    assert any(f.name == "ReviewRequest.rating" and f.properties.get("description") == "Рейтинг от 1 до 5" for f in dictionary)
    assert any(f.properties.get("entry_kind") == "interface_operation" and f.properties.get("description") == "Создание отзыва" for f in dictionary)


def test_feign_and_external_client_calls_are_visible(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    src = repo / "src/main/java/com/acme"
    src.mkdir(parents=True)
    (src / "EmployeeClient.java").write_text(
        '''
package com.acme;
import org.springframework.cloud.openfeign.FeignClient;
@FeignClient(name = "hrdata", url = "${hr.url}")
interface EmployeeClient { String getEmployee(String id); }
''',
        encoding="utf-8",
    )
    (src / "EmployeeService.java").write_text(
        '''
package com.acme;
class EmployeeService {
  private EmployeeClient employeeClient;
  String load(String id) { return employeeClient.getEmployee(id); }
}
''',
        encoding="utf-8",
    )
    facts, schemas, interfaces, relations, mapper_facts, warnings = scan_java_files(scan_files(repo))
    deps = [f for f in facts if f.fact_type in {"external_dependency", "external_dependency_call"}]
    assert any(f.fact_type == "external_dependency" and f.properties.get("dependency_kind") == "feign_client" for f in deps)
    assert any(f.fact_type == "external_dependency_call" and f.properties.get("client_receiver") == "employeeClient" for f in deps)


def test_sql_query_model_extracts_projection_and_calculation(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    sql = repo / "src/main/resources/report.sql"
    sql.parent.mkdir(parents=True)
    sql.write_text(
        """
select b.id as booking_id,
       coalesce(z.name, 'n/a') as zone_name,
       case when b.status = 'CANCELLED' then true else false end as cancelled
from reservation.booking b
join reservation.zone z on z.id = b.zone_id
where b.deleted = false;
""",
        encoding="utf-8",
    )
    facts, summary, warnings = scan_sql_files(scan_files(repo))
    models = [f for f in facts if f.fact_type == "sql_query_model"]
    assert models
    assert "reservation.booking" in models[0].properties["source_tables"]
    assert any(x.get("alias") == "cancelled" for x in models[0].properties["calculated_fields"])


def test_system_description_compact_artifact_contains_enriched_sections(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    src = repo / "src/main/java/com/acme"
    src.mkdir(parents=True)
    (src / "CityController.java").write_text(
        '''
package com.acme;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Schema;
import org.springframework.web.bind.annotation.*;
class CityRequest { @Schema(description="Название города") String city; }
@RestController
@RequestMapping("/v1/cities")
class CityController {
  @Operation(summary = "Поиск городов")
  @PostMapping("/search")
  CityRequest search(@RequestBody CityRequest request) { return request; }
}
''',
        encoding="utf-8",
    )
    facts, schemas, interfaces, relations, mapper_facts, warnings = scan_java_files(scan_files(repo))
    result = AnalysisResult(system_name="S", project_code="P", repo_path=str(repo), facts=facts, schemas=schemas, interfaces=interfaces)
    enrich, status = build_system_description_enrichment_facts(result)
    result.facts.extend(enrich)
    build_navigation(result, tmp_path / "out")
    compact = (tmp_path / "out" / "compact" / "system_description_compact.json").read_text(encoding="utf-8")
    assert "data_dictionary_entries" in compact
    assert "system_scenarios" in compact
    assert "Поиск городов" in compact


def test_system_scenario_composes_inbound_call_chain_to_storage() -> None:
    from code_analyzer_core.models import Direction, EvidenceRef, Fact, InterfaceInfo, InterfaceKind

    ev = [EvidenceRef(file_path="src/main/java/com/acme/ProfileController.java", line_start=10, line_end=10, extractor="java_tree_sitter")]
    result = AnalysisResult(
        system_name="S",
        project_code="P",
        repo_path="/repo",
        interfaces=[InterfaceInfo(
            name="ProfileController.load",
            operation="ProfileController.load",
            direction=Direction.INBOUND,
            kind=InterfaceKind.REST,
            path="/profile",
            method="POST",
            properties={"boundary_role": "rest_request"},
            evidence=ev,
        )],
        facts=[
            Fact(
                fact_type="type_reference_observation",
                name="ProfileController -> ProfileService",
                properties={
                    "reference_role": "field_type",
                    "owner_fqcn": "com.acme.ProfileController",
                    "member_name": "profileService",
                    "resolved_fqcn": "com.acme.ProfileService",
                },
                evidence=ev,
            ),
            Fact(
                fact_type="java_method_call_observation",
                name="ProfileController.load:profileService.load",
                properties={
                    "owner_operation": "ProfileController.load",
                    "owner_fqcn": "com.acme.ProfileController",
                    "receiver_expression": "profileService",
                    "method": "load",
                    "call_depth": 0,
                    "is_unqualified": False,
                },
                evidence=ev,
            ),
            Fact(
                fact_type="java_method_call_observation",
                name="ProfileService.load:dao.find",
                properties={
                    "owner_operation": "ProfileService.load",
                    "owner_fqcn": "com.acme.ProfileService",
                    "receiver_expression": "dao",
                    "method": "find",
                    "call_depth": 0,
                    "is_unqualified": False,
                },
                evidence=ev,
            ),
            Fact(
                fact_type="type_reference_observation",
                name="ProfileService -> ProfileDao",
                properties={
                    "reference_role": "field_type",
                    "owner_fqcn": "com.acme.ProfileService",
                    "member_name": "dao",
                    "resolved_fqcn": "com.acme.ProfileDao",
                },
                evidence=ev,
            ),
            Fact(
                fact_type="storage_access",
                name="ProfileDao.find",
                properties={
                    "operation": "ProfileDao.find",
                    "storage_target": "PROFILE",
                    "access_kind": "read",
                    "storage_method": "select",
                },
                evidence=ev,
            ),
        ],
    )

    enrich, _ = build_system_description_enrichment_facts(result)
    scenarios = [fact for fact in enrich if fact.fact_type == "system_scenario_candidate"]
    assert len(scenarios) == 1
    payload = scenarios[0].properties
    assert payload["composition_status"] == "observed_source_call_chain"
    assert payload["storage_touches"][0]["storage_target"] == "PROFILE"
    assert [edge["to_operation"] for edge in payload["call_chain"]] == [
        "ProfileService.load",
        "ProfileDao.find",
    ]
