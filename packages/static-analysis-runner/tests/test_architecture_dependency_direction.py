from pathlib import Path


def test_runner_does_not_scan_other_module_source_trees():
    root = Path(__file__).resolve().parents[1]
    runtime = "\n".join(path.read_text(encoding="utf-8") for path in sorted((root / "static_analysis_runner").rglob("*.py")))
    assert "analysis_ui_root" not in runtime
    assert "--analysis-ui-root" not in runtime
    assert "mechanism_catalog" not in runtime
    assert "build_analysis_mechanism_catalog" not in runtime


def test_removed_system_wide_diagnostic_command_stays_removed():
    cli = (Path(__file__).resolve().parents[1] / "static_analysis_runner" / "cli.py").read_text(encoding="utf-8")
    assert '@app.command("mechanism-catalog")' not in cli
