from __future__ import annotations

import sys
from types import ModuleType

import pytest

from static_analysis_runner.knowledge_compat import require_knowledge_layer_core


def _module(version: str, **symbols):
    module = ModuleType("knowledge_layer_core")
    module.__version__ = version
    for name, value in symbols.items():
        setattr(module, name, value)
    return module


def test_compatible_knowledge_layer_version_is_accepted(monkeypatch: pytest.MonkeyPatch):
    fake = _module("0.59.0", materialize=lambda *a, **k: None)
    monkeypatch.setitem(sys.modules, "knowledge_layer_core", fake)
    module, version = require_knowledge_layer_core(context="typed runtime", required_symbols=("materialize",))
    assert module is fake
    assert version == "0.59.0"


def test_old_knowledge_layer_version_is_rejected(monkeypatch: pytest.MonkeyPatch):
    fake = _module("0.48.9", materialize=lambda *a, **k: None)
    monkeypatch.setitem(sys.modules, "knowledge_layer_core", fake)
    with pytest.raises(RuntimeError, match="required >= 0.50.0"):
        require_knowledge_layer_core(context="typed runtime", required_symbols=("materialize",))


def test_missing_current_runtime_api_is_rejected(monkeypatch: pytest.MonkeyPatch):
    fake = _module("0.59.0")
    monkeypatch.setitem(sys.modules, "knowledge_layer_core", fake)
    with pytest.raises(RuntimeError, match="missing required symbols: materialize"):
        require_knowledge_layer_core(context="typed runtime", required_symbols=("materialize",))


def test_next_major_knowledge_layer_version_is_rejected(monkeypatch: pytest.MonkeyPatch):
    fake = _module("1.0.0", materialize=lambda *a, **k: None)
    monkeypatch.setitem(sys.modules, "knowledge_layer_core", fake)
    with pytest.raises(RuntimeError, match="required < 1.0.0"):
        require_knowledge_layer_core(context="typed runtime", required_symbols=("materialize",))
