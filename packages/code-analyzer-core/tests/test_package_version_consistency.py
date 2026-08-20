from pathlib import Path
import tomllib

import code_analyzer_core


def test_package_version_matches_pyproject():
    root = Path(__file__).resolve().parents[1]
    metadata = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    assert code_analyzer_core.__version__ == metadata["project"]["version"]
