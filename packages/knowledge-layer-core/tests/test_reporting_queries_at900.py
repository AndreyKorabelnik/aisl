import os
from pathlib import Path

import pytest

from prepared_knowledge_runtime.reporting_queries import ReportingQueryService


DB_ENV = "AT900_KNOWLEDGE_LAYER"


def _service():
    raw = os.environ.get(DB_ENV)
    if not raw or not Path(raw).is_file():
        pytest.skip(f"set {DB_ENV} to run the AT900 contract test")
    return ReportingQueryService(raw)


def test_at900_reporting_queries_are_deterministic_and_grounded():
    service = _service()
    overview = service.get_scope_overview().to_dict()
    assert overview["items"][0]["scope"]["id"] == "client_profile"
    interfaces = service.list_interfaces(direction="inbound", boundary_kinds=("rest_request", "kafka_consume"), max_results=1000).to_dict()
    assert interfaces["summary"]["boundary_kind_counts"]["rest_request"] == 35
    assert interfaces["summary"]["boundary_kind_counts"]["kafka_consume"] == 24
    assert interfaces["evidence"]
    assert all(item["evidence_ids"] for item in interfaces["items"])
    tables = service.list_data_objects(max_results=20).to_dict()
    assert tables["summary"]["table_count"] == 80
    assert tables["items"][0]["selection_score"] >= tables["items"][-1]["selection_score"]
    gaps = service.get_gap_summary().to_dict()
    assert gaps["summary"]["gap_count"] == 8872
