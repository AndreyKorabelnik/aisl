from aisl_reporting.profiles.workspace_interaction.v1 import builder


def test_observed_repository_summary_does_not_require_interaction_coverage_mart():
    summaries = builder._observed_repository_interaction_summaries(
        ["source", "target"],
        [
            {"repo_id": "source", "system_id": "S", "direction": "outbound"},
            {"repo_id": "source", "system_id": "S", "direction": "outbound"},
            {"repo_id": "target", "system_id": "T", "direction": "inbound"},
        ],
        [
            {"source_repo_id": "source", "confidence": "probable"},
        ],
        [
            {"source_repo_id": "source", "match_status": "matched"},
            {"source_repo_id": "source", "match_status": "unresolved"},
        ],
        [],
    )

    by_repo = {item["repo_id"]: item for item in summaries}
    assert by_repo["source"] == {
        "repo_id": "source",
        "system_id": "S",
        "project_id": None,
        "inbound_boundary_count": 0,
        "outbound_boundary_count": 2,
        "matched_outbound_count": 1,
        "confirmed_outbound_count": 0,
        "probable_outbound_count": 1,
        "ambiguous_outbound_count": 0,
        "unresolved_outbound_count": 1,
        "technical_matching_disposition_status": "complete",
        "analysis_status": None,
        "coverage_status": None,
        "matching_coverage_status": None,
        "coverage_basis": "observed_boundary_inventory_without_interaction_coverage_mart",
    }
    assert by_repo["target"]["inbound_boundary_count"] == 1
    assert by_repo["target"]["technical_matching_disposition_status"] == "not_applicable"


def test_role_candidates_use_observed_boundary_inventory_without_claiming_business_ownership():
    roles = builder._role_candidates(
        [
            {
                "repo_id": "source",
                "inbound_boundary_count": 0,
                "outbound_boundary_count": 2,
                "matched_outbound_count": 1,
                "confirmed_outbound_count": 0,
                "probable_outbound_count": 1,
                "unresolved_outbound_count": 1,
                "coverage_status": None,
            }
        ]
    )
    assert roles[0]["role_candidate"] == "interaction_initiator_candidate"
    assert roles[0]["interpretation_status"] == "candidate"
    assert "не доказывает" not in roles[0]["explanation"].casefold() or roles[0]["role_candidate"]


def test_unmatched_inbound_groups_duplicate_evidence_by_operation_signature():
    boundaries = [
        {"repo_id": "target", "direction": "inbound", "interface_id": "route", "protocol": "http", "http_method": "POST", "normalized_paths_json": ["/update"], "operation": "POST /update"},
        {"repo_id": "target", "direction": "inbound", "interface_id": "controller", "protocol": "http", "http_method": "POST", "normalized_paths_json": ["/update"], "operation": "Controller.update"},
        {"repo_id": "target", "direction": "inbound", "interface_id": "v5", "protocol": "http", "http_method": "POST", "normalized_paths_json": ["/v5"], "operation": "POST /v5"},
    ]
    interactions = [
        {"target_repo_id": "target", "target_ingress_endpoint": "/update", "protocol": "http", "http_method": "POST"},
    ]

    result = builder._unmatched_inbound_operations(boundaries, interactions)

    assert len(result) == 1
    assert result[0]["normalized_paths"] == ["/v5"]
    assert result[0]["interface_ids"] == ["v5"]


def test_grounded_owner_questions_are_concrete_and_bounded():
    interactions = [
        {
            "source_repo_id": "source", "target_repo_id": f"target-{index}", "http_method": "POST",
            "target_ingress_endpoint": f"/op-{index}", "confidence": "probable",
            "payload_json": {"outbound_interface": {"response_payload_type": "Response"}, "target_ingress_interface": {}},
        }
        for index in range(3)
    ]
    diagnostics = [
        {"outbound_operation": f"External.call{index}", "outbound_paths_json": [f"/external-{index}"], "match_status": "unresolved"}
        for index in range(3)
    ]
    inbound = [
        {"repo_id": "target-1", "normalized_paths": ["/v5"]},
    ]
    result = builder._grounded_owner_questions(
        interactions, diagnostics, inbound, confidence_counts={"confirmed": 0, "probable": 3}
    )

    assert 8 <= len(result) <= 15
    assert any("`POST /op-0`" in item["question"] for item in result)
    assert any("`/v5`" in item["question"] for item in result)
    assert any("response contract" in item["question"] for item in result)
