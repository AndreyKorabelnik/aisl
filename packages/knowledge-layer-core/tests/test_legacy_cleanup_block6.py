from __future__ import annotations

from pathlib import Path

import knowledge_layer_core as klc


def test_retired_workspace_build_api_is_not_public() -> None:
    for name in (
        "KnowledgeLayerBuildRequest",
        "RepositoryEvidence",
        "KnowledgeLayerMaterializer",
        "build_knowledge_layer",
        "build_workspace_data_model",
        "validate_data_model_inputs",
        "resolve_repository_evidence",
    ):
        assert not hasattr(klc, name), name


def test_retired_workspace_build_modules_are_physically_absent() -> None:
    package_root = Path(klc.__file__).resolve().parent
    for name in (
        "api.py",
        "scope_builder.py",
        "scope_materialization.py",
        "repository.py",
        "repository_materialization.py",
        "workspace_data_model.py",
        "workspace_validation.py",
        "workspace_selection.py",
    ):
        assert not (package_root / name).exists(), name


def test_current_klc_source_does_not_consume_core_conceptual_model() -> None:
    package_root = Path(klc.__file__).resolve().parent
    offenders = []
    for path in package_root.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "code_conceptual_model" in text or "legacy_code_conceptual_model_consumed" in text:
            offenders.append(path.name)
    assert offenders == []
