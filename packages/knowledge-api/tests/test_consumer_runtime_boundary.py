from __future__ import annotations

from pathlib import Path

import knowledge_api


def test_knowledge_api_runtime_does_not_import_knowledge_layer_core() -> None:
    root = Path(knowledge_api.__file__).resolve().parent
    sources = "\n".join(path.read_text(encoding="utf-8") for path in root.glob("*.py"))
    assert "knowledge_layer_core" not in sources
