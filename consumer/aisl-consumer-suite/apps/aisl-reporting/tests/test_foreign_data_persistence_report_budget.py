from aisl_reporting.profiles.foreign_data_persistence.v1.builder import (
    _MAX_REPORT_PATHS,
    _selected_report_cases,
    _selected_report_paths,
)


def _path(path_id: str, *, maturity: str = "unresolved", storage: str = "T") -> dict:
    return {
        "path_id": path_id,
        "direction": "source-to-storage",
        "storage_object": storage,
        "evidence_maturity_level": maturity,
        "source_interpretation": {},
        "evidence_ids": [f"evidence-{path_id}"],
    }


def test_confirmed_same_data_case_paths_are_selected_before_large_background_catalog():
    background = [_path(f"background-{index:03d}") for index in range(_MAX_REPORT_PATHS + 40)]
    source = _path("confirmed-source", maturity="confirmed", storage="DEVICE_LINK")
    access = {
        **_path("confirmed-access", maturity="confirmed", storage="DEVICE_LINK"),
        "direction": "storage-to-access",
    }
    case = {
        "source_to_storage_observed": True,
        "storage_to_access_observed": True,
        "same_data_end_to_end_status": "confirmed",
        "source_path_id": "confirmed-source",
        "access_path_id": "confirmed-access",
    }

    selected, metadata = _selected_report_paths([*background, source, access], [case])
    selected_ids = {item["path_id"] for item in selected}

    assert "confirmed-source" in selected_ids
    assert "confirmed-access" in selected_ids
    assert len(selected) == _MAX_REPORT_PATHS
    assert metadata["complete_path_catalog"] is False
    assert metadata["omitted_path_count"] == 42


def test_report_path_selection_is_deterministic():
    paths = [
        _path("z-unresolved", storage="B"),
        _path("a-confirmed", maturity="confirmed", storage="Z"),
        _path("b-confirmed", maturity="confirmed", storage="A"),
    ]

    first, first_metadata = _selected_report_paths(paths, [])
    second, second_metadata = _selected_report_paths(list(reversed(paths)), [])

    assert [item["path_id"] for item in first] == [item["path_id"] for item in second]
    assert first_metadata == second_metadata


def test_exact_case_selection_keeps_all_confirmed_cases_and_limits_background():
    selected_paths = [
        _path("source-1", maturity="confirmed"),
        {**_path("access-1", maturity="confirmed"), "direction": "storage-to-access"},
    ]
    confirmed_case = {
        "case_id": "case-confirmed",
        "storage_object": "PHONE",
        "storage_field": "OPERATORID",
        "source_path_id": "source-1",
        "access_path_id": "access-1",
        "source_to_storage_observed": True,
        "storage_to_access_observed": True,
        "same_data_end_to_end_status": "confirmed",
    }
    background = [
        {
            "case_id": f"case-{index:03d}",
            "storage_object": "T",
            "storage_field": f"F{index}",
            "source_path_id": None,
            "access_path_id": None,
            "source_to_storage_observed": True,
            "storage_to_access_observed": False,
            "same_data_end_to_end_status": "unresolved",
        }
        for index in range(200)
    ]

    selected, metadata = _selected_report_cases([*background, confirmed_case], selected_paths)

    assert selected[0]["case_id"] == "case-confirmed"
    assert metadata["all_confirmed_cases_selected"] is True
    assert metadata["selected_case_count"] == 160
    assert metadata["omitted_case_count"] == 41
    assert metadata["complete_case_catalog"] is False


def test_exact_case_selection_is_deterministic():
    paths = [_path("source-1"), {**_path("access-1"), "direction": "storage-to-access"}]
    cases = [
        {
            "case_id": "z-case",
            "storage_object": "PHONE",
            "storage_field": "TOKENID",
            "source_path_id": "source-1",
            "access_path_id": "access-1",
            "source_to_storage_observed": True,
            "storage_to_access_observed": True,
            "same_data_end_to_end_status": "unresolved",
        },
        {
            "case_id": "a-case",
            "storage_object": "PHONE",
            "storage_field": "OPERATORID",
            "source_path_id": "source-1",
            "access_path_id": "access-1",
            "source_to_storage_observed": True,
            "storage_to_access_observed": True,
            "same_data_end_to_end_status": "confirmed",
        },
    ]
    first, first_meta = _selected_report_cases(cases, paths)
    second, second_meta = _selected_report_cases(list(reversed(cases)), list(reversed(paths)))
    assert [item["case_id"] for item in first] == [item["case_id"] for item in second]
    assert first_meta == second_meta

