from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from code_analyzer_core.cli import app


ROOT = Path(__file__).resolve().parents[1]


def test_specialized_sufficiency_command_is_removed() -> None:
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "conceptual-model-evidence-sufficiency" not in result.stdout


def test_specialized_sufficiency_implementation_is_removed() -> None:
    assert not (ROOT / "code_analyzer_core" / "conceptual_model_sufficiency.py").exists()
    assert not (
        ROOT
        / "code_analyzer_core"
        / "resources"
        / "conceptual_model_evidence_sufficiency_definitions_v1.json"
    ).exists()


def test_historical_assessment_is_not_a_current_core_contract() -> None:
    validation_root = ROOT / "validation"
    assert not (validation_root / "conceptual-model-evidence-sufficiency-v1.json").exists()
    assert not (validation_root / "conceptual-model-evidence-sufficiency-v1.md").exists()


def test_general_core_contract_commands_remain_available() -> None:
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "analysis-catalog" in result.stdout
    assert "target-contracts" in result.stdout
