from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest


@pytest.fixture
def discovery_profile(tmp_path: Path) -> Path:
    path = tmp_path / "discovery.yaml"
    path.write_text(
        """schema_version: candidate_discovery_profile/v1
profile_id: data-model-discovery/v1
analysis_mode: data-model
selection_rules:
  - DM_CONCEPTUAL_MODEL_DECLARATION
""",
        encoding="utf-8",
    )
    return path


def make_executable(path: Path, body: str) -> Path:
    # Test doubles use the active interpreter without site initialization.
    # This avoids unrelated global site/plugin startup hooks in subprocess fixtures.
    path.write_text(f"#!{sys.executable} -S\n" + body, encoding="utf-8")
    path.chmod(path.stat().st_mode | 0o111)
    return path

