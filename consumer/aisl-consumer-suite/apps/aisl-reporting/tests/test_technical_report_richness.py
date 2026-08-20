from importlib.resources import files

import pytest

from aisl_reporting.profile import load_profile
from aisl_reporting.profiles.sql_source_inventory_report.v1 import builder as sql_builder


def _source(identity: str, *, repo_id: str = "repo", kind: str = "physical", fields: int = 1) -> dict:
    return {
        "repo_id": repo_id,
        "relation_identity": identity,
        "relation_kind": kind,
        "fields": [{"name": f"field_{index}"} for index in range(fields)],
    }


def test_sql_source_catalog_groups_keep_every_source_and_field():
    items = [
        _source("crm.customer", repo_id="mart-a", fields=3),
        _source("crm.account", repo_id="mart-a", fields=2),
        _source("billing.payment", repo_id="mart-b", kind="physical-template", fields=4),
    ]

    groups = sql_builder._source_catalog_groups(items)

    assert [item["group"] for item in groups["by_repository"]] == ["mart-a", "mart-b"]
    assert groups["by_repository"][0]["sources"] == ["crm.account", "crm.customer"]
    assert groups["by_repository"][0]["used_field_count"] == 5
    assert groups["by_schema_or_prefix"][0]["group"] == "billing"
    assert all(item["complete_group_catalog"] is True for values in groups.values() for item in values)
    assert sql_builder._DETAIL_LIMITS == {
        "executive": {"top_sources": 15, "profile_items": 15},
        "standard": {"top_sources": 40, "profile_items": 50},
        "detailed": {"top_sources": 80, "profile_items": 100},
    }
