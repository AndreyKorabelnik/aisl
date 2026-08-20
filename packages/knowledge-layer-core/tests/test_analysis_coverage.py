from pathlib import Path

import duckdb

from prepared_knowledge_runtime import KnowledgeLayerQuery, ReportingQueryService


def test_analysis_coverage_aggregates_known_facts_and_limitations(tmp_path: Path) -> None:
    database = tmp_path / "coverage.duckdb"
    con = duckdb.connect(str(database))
    try:
        con.execute("CREATE TABLE workspace_repository(repo_id VARCHAR)")
        con.execute("CREATE TABLE source_observation(source_observation_occurrence_id VARCHAR)")
        con.execute("CREATE TABLE model_relationship_observation(relationship_id VARCHAR)")
        con.execute("CREATE TABLE model_relationship_candidate(candidate_id VARCHAR)")
        con.execute("CREATE TABLE model_relationship_storage_reference(relationship_id VARCHAR)")
        con.execute("CREATE TABLE model_relationship_storage_key_derivation(relationship_id VARCHAR)")
        con.execute("CREATE TABLE table_relationship_observation(relationship_id VARCHAR)")
        con.execute(
            "CREATE TABLE workspace_missing_fact(repo_id VARCHAR, category VARCHAR, missing_fact_kind VARCHAR, required_for_operation VARCHAR)"
        )
        con.execute("INSERT INTO workspace_repository VALUES ('repo-a'), ('repo-b')")
        con.execute("INSERT INTO source_observation VALUES ('o1'), ('o2'), ('o3')")
        con.execute("INSERT INTO model_relationship_observation VALUES ('r1'), ('r2')")
        con.execute("INSERT INTO model_relationship_candidate VALUES ('c1')")
        con.execute("INSERT INTO model_relationship_storage_reference VALUES ('r1')")
        con.execute("INSERT INTO model_relationship_storage_key_derivation VALUES ('r1'), ('r2')")
        con.execute("INSERT INTO table_relationship_observation VALUES ('sql-r1')")
        con.execute(
            "INSERT INTO workspace_missing_fact VALUES "
            "('repo-a','resolution','source_expression_not_resolved','field_flow'),"
            "('repo-a','resolution','source_expression_not_resolved','field_flow'),"
            "('repo-b','language','unsupported_construct','data_model'),"
            "('repo-b','mapping','ambiguous_target','relationship')"
        )
        con.execute("CHECKPOINT")
    finally:
        con.close()

    coverage = KnowledgeLayerQuery(database).analysis_coverage()
    assert coverage["schema_version"] == "analysis_coverage/v1"
    assert coverage["status"] == "partial"
    assert coverage["summary"] == {
        "repository_count": 2,
        "observed_fact_count": 3,
        "known_gap_count": 4,
        "unresolved_count": 3,
        "conflicting_count": 1,
        "unsupported_count": 1,
        "not_observed_count": 0,
        "requires_interpretation_count": 2,
        "physical_join_observation_count": 1,
    }
    assert coverage["domains"]["data_model"]["unresolved_relationship_candidate_count"] == 1
    assert coverage["domains"]["physical_storage"]["requires_interpretation_count"] == 2
    assert coverage["count_basis"] == "diagnostic_occurrences_not_unique_business_elements"
    assert "absence of evidence" in coverage["statement"]

    result = ReportingQueryService(database).get_analysis_coverage(max_results=2).to_dict()
    assert result["items"][0]["limitations_truncated"] is True
    assert result["pagination"]["total_count"] == 1
