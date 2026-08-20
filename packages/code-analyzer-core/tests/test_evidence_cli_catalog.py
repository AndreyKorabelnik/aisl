from __future__ import annotations

import json
from code_analyzer_core import __version__
from code_evidence.catalog import filter_evidence_tool_catalog, load_evidence_tool_catalog
from evidence_access_test_utils import evidence_tool_ids


REQUIRED_FIELDS = {
    "command_id",
    "view_name",
    "required_args",
    "optional_args",
    "when_to_use",
    "do_not_use_when",
    "output_kind",
}

EXPECTED_STABLE_VIEWS = {
    "operation",
    "interface",
    "schema",
    "symbol",
    "source-inspect",
    "source-open",
    "callable",
    "find-implementations",
    "confirmed-evidence",
    "candidate-signal",
    "unresolved-gap",
    "source-inspection-request",
    "persistent-structure",
    "attribute-occurrence",
    "attribute-mapping",
    "attribute-derivation",
    "source-to-storage-lineage",
    "data-model-lineage-gap",
    "stored-data-access",
    "read-from-storage",
    "access-boundary",
    "storage-to-access-lineage",
    "stored-field-to-response-field-mapping",
    "system-data-model-overview",
    "system-table-catalog",
    "evidence-coverage",
    "transformation-catalog",
    "conceptual-implementation-profile",
    "foreign-data-persistence-cases",
    "openspec-data-evidence-full",
    "git-change-coverage-delta",
}

def test_catalog_resource_is_valid_and_contains_required_static_contract():
    catalog = load_evidence_tool_catalog()

    assert catalog["format"] == "evidence_tool_catalog"
    assert catalog["format_version"] == "1.0"
    assert catalog["producer"] == "code_analyzer_core.evidence_access"
    assert catalog["analyzer_version"] == __version__
    assert isinstance(catalog["commands"], list)
    assert catalog["commands"]

    text = json.dumps(catalog, ensure_ascii=False)
    assert "/home/" not in text
    assert "C:\\" not in text
    assert "/actual/path" not in text

    view_names = {item["view_name"] for item in catalog["commands"]}
    assert EXPECTED_STABLE_VIEWS.issubset(view_names)

    command_ids = [item["command_id"] for item in catalog["commands"]]
    assert len(command_ids) == len(set(command_ids))

    for command in catalog["commands"]:
        assert REQUIRED_FIELDS.issubset(command)
        assert command["command_id"]
        assert command["view_name"]
        assert command.get("access_mode") == "evidence_access_api"
        assert isinstance(command["required_args"], list)
        assert isinstance(command["optional_args"], list)
        assert command["when_to_use"]
        assert command["do_not_use_when"]
        assert command["output_kind"]


def test_agent_visible_catalog_commands_are_registered_for_access_api():
    catalog = load_evidence_tool_catalog()
    registered = evidence_tool_ids()

    for command in catalog["commands"]:
        if not command.get("agent_visible"):
            continue
        assert command["command_id"] in registered
        assert command.get("access_mode") == "evidence_access_api"


def test_tool_catalog_loader_returns_json_catalog():
    payload = load_evidence_tool_catalog()
    assert payload["format"] == "evidence_tool_catalog"
    assert payload["analyzer_version"] == __version__
    assert any(item["view_name"] == "source-inspect" for item in payload["commands"])

def test_catalog_filter_supports_llm_pipeline_enabled_subset():
    catalog = load_evidence_tool_catalog()
    subset = filter_evidence_tool_catalog(
        catalog,
        workspace_type="java",
        analysis_profile="system-data-model-description",
        capabilities={"system_data_model_overview", "stored_data_access"},
        agent_visible_only=True,
    )

    view_names = {item["view_name"] for item in subset["commands"]}
    assert "system-data-model-overview" in view_names
    assert "stored-data-access" in view_names
    assert "sql-object" not in view_names
    assert "cli-catalog" not in view_names
    assert subset["filtered"] is True


def test_optional_token_rules_are_explicit_without_cli_placeholders():
    catalog = load_evidence_tool_catalog()
    for command in catalog["commands"]:
        if "token" in command.get("optional_args", []) and "token" not in command.get("required_args", []):
            assert command.get("optional_positional_args"), command["command_id"]
            text = json.dumps(command, ensure_ascii=False)
            assert "Never leave <token>" in text or "никогда" in text.lower()

def test_retired_sql_workspace_views_are_absent():
    catalog = load_evidence_tool_catalog()
    command_ids = {item["command_id"] for item in catalog["commands"]}
    assert {
        "sql_portfolio",
        "sql_object",
        "sql_attribute",
        "sql_lineage",
        "sql_query",
        "sql_comment",
        "sql_optimization",
        "mart_inventory",
        "mart_column_lineage",
        "source_table_usage",
        "source_join_evidence",
        "source_key_candidate",
        "grain_candidate",
        "mart_load_pattern",
        "temporal_logic_evidence",
        "mart_dependency",
        "sql_mart_lineage_gap",
        "workspace_mart_catalog",
        "workspace_source_table_catalog",
        "workspace_mart_dependency_graph",
        "workspace_source_join_graph",
        "workspace_key_candidate_catalog",
    }.isdisjoint(command_ids)

