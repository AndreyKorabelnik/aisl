from __future__ import annotations

import importlib.util

from pathlib import Path

from typer.testing import CliRunner

from static_analysis_runner.cli import app

runner = CliRunner()


def test_cli_exposes_only_installed_typed_runtime_commands():
    result = runner.invoke(app, ["--help"], env={"COLUMNS": "220"})
    assert result.exit_code == 0, result.output
    for command in (
        "data-model-discovery",
        "repository-batch-discover",
        "repository-batch-run",
        "execution-result-contract",
        "knowledge-catalog",
        "knowledge-profile-resolve",
        "knowledge-input-inventory",
        "knowledge-input-prepare",
        "knowledge-execution-plan",
        "knowledge-execute",
    ):
        assert command in result.stdout
    for removed in ("repository", "workspace", "portfolio-topology", "materialize-knowledge-layer", "physical-model", "mechanism-catalog", "responsibility-map", "knowledge-architecture-audit"):
        missing = runner.invoke(app, [removed, "--help"])
        assert missing.exit_code != 0
        assert "No such command" in missing.output


def test_version():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert result.stdout.strip() == "0.10.28"


def test_data_model_discovery_remains_an_independent_typed_workflow():
    result = runner.invoke(app, ["data-model-discovery", "--help"], env={"COLUMNS": "240"})
    assert result.exit_code == 0, result.output
    assert "--bitbucket-project-url" in result.stdout
    assert "--repository-sources" in result.stdout
    assert "--repository-limit" in result.stdout
    assert "--max-repositories" in result.stdout
    assert "--suite" not in result.stdout
    assert "--task-registry" not in result.stdout
    assert "--profiles-root" not in result.stdout


def test_removed_runtime_modules_are_not_importable():
    for module_name in (
        "static_analysis_runner.repository",
        "static_analysis_runner.workspace",
        "static_analysis_runner.suite",
        "static_analysis_runner.suite_catalog",
        "static_analysis_runner.portfolio_topology",
        "static_analysis_runner.portfolio_topology_contracts",
    ):
        assert importlib.util.find_spec(module_name) is None
    assert importlib.util.find_spec("workspace_knowledge_layer") is None


def test_topology_snapshot_is_not_part_of_product_source_or_package():
    root = Path(__file__).resolve().parents[1]
    assert not (root / "parked_topology").exists()
    assert importlib.util.find_spec("static_analysis_runner.portfolio_topology") is None
    assert importlib.util.find_spec("static_analysis_runner.portfolio_topology_contracts") is None
