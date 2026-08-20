from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "src" / "knowledge_control_plane" / "runtime"


def _runtime_text() -> str:
    return "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(RUNTIME.glob("*.py"))
    )


def test_control_plane_does_not_invoke_core_or_build_runner_input_envelopes() -> None:
    text = _runtime_text()
    forbidden = (
        'command_parts("code_analyzer_core")',
        '"analyze-physical-model"',
        "materialize_physical_model_descriptor",
        "materialize_knowledge_artifact_descriptor",
        "external_typed_input",
        "requires_physical_model(",
    )
    for token in forbidden:
        assert token not in text, token


def test_control_plane_delegates_raw_input_normalization_to_runner() -> None:
    commands = (RUNTIME / "commands.py").read_text(encoding="utf-8")
    assert '"knowledge-input-prepare"' in commands
    assert '"--physical-model"' in commands
    assert '"--published-revision"' in commands


def test_knowledge_product_metadata_is_projected_from_runner_catalog() -> None:
    from knowledge_control_plane.runtime.knowledge_products import KnowledgeProductCatalogService

    response = KnowledgeProductCatalogService().list(offset=0, limit=500)
    by_id = {item.knowledge_id: item for item in response.items}
    assert by_id["code-declared-data-model"].title == "Модель данных, объявленная в коде"
    assert by_id["data-model-attribute-extension"].supported_scopes == ["workspace"]
    assert by_id["data-model-attribute-extension"].profile_v2_selectable is True
    assert response.catalog_fingerprint


def test_frontend_does_not_reconstruct_knowledge_product_semantics() -> None:
    frontend = ROOT / "frontend" / "src"
    text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(frontend.rglob("*.vue"))
    )
    assert "const requiresPdm" not in text
    assert "'physical-data-model': 'Физическая модель'" not in text
    assert "'code-declared-data-model': 'Объявленная модель'" not in text
