from pathlib import Path


def test_reporting_runtime_depends_on_knowledge_api_not_klc_or_duckdb():
    root = Path(__file__).resolve().parents[1]
    package_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((root / "aisl_reporting").rglob("*.py"))
    )
    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
    assert "knowledge_layer_core" not in package_text
    assert "import duckdb" not in package_text
    assert "local_database_path" not in package_text
    assert "knowledge-layer-core" not in pyproject
