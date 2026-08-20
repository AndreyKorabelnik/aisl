import os
from pathlib import Path

import pytest

from prepared_knowledge_runtime import ForeignDataPersistenceQueryService

DB_ENV = "UCP_FULL_KNOWLEDGE_LAYER"


def test_real_ucp_fdp_query_contract_is_partial_and_facts_only():
    value = os.environ.get(DB_ENV)
    if not value or not Path(value).is_file():
        pytest.skip(f"set {DB_ENV} to run real UCP FDP query contract")
    service = ForeignDataPersistenceQueryService(value)
    paths = service.list_paths()
    cases = service.list_mechanical_cases()
    assert paths.summary["path_count"] == 4
    assert paths.summary["direction_counts"] == {"storage-to-access": 4}
    assert paths.summary["business_fdp_decision_assigned"] is False
    assert cases.summary["case_count"] == 3
    assert cases.summary["source_and_access_case_count"] == 0
    assert cases.summary["same_data_confirmed_case_count"] == 0
    assert all(item["business_fdp_decision"] == "not_assigned" for item in cases.items)
    assert all(not ref.path.startswith("/") for ref in paths.evidence)
