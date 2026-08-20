from __future__ import annotations

from pathlib import Path
from typing import Iterable


INTERESTING_SUFFIXES = {
    ".java", ".py", ".sql", ".xml", ".yml", ".yaml", ".properties", ".json", ".csv", ".tsv", ".toml", ".conf", ".avsc", ".proto", ".gradle"
}
INTERESTING_NAMES = {
    "pom.xml", "Dockerfile", "pyproject.toml", "requirements.txt", "setup.py", "setup.cfg",
    "build.gradle.kts", "settings.gradle.kts", "libs.versions.toml",
}
SKIP_PARTS = {".git", "target", "build", ".gradle", ".idea", ".venv", "node_modules"}


def scan_all_files(repo_path: Path) -> list[Path]:
    """Enumerate the complete in-scope repository file frontier once.

    This is intentionally concept-agnostic.  Analyzer eligibility is a separate view so
    adding repository inventory coverage cannot silently broaden existing analyzer inputs.
    """
    files: list[Path] = []
    for path in repo_path.rglob("*"):
        if not path.is_file():
            continue
        try:
            relative_parts = path.relative_to(repo_path).parts
        except ValueError:
            relative_parts = path.parts
        if any(part in SKIP_PARTS for part in relative_parts):
            continue
        files.append(path)
    return sorted(files)


def is_analyzer_eligible_file(path: Path) -> bool:
    return path.suffix.lower() in INTERESTING_SUFFIXES or path.name in INTERESTING_NAMES


def filter_analyzer_files(files: Iterable[Path]) -> list[Path]:
    return sorted(path for path in files if is_analyzer_eligible_file(path))


def scan_files(repo_path: Path) -> list[Path]:
    """Backward-compatible analyzer-eligible repository view.

    Existing analyzers keep exactly the historical suffix/name filter.  Universal file
    inventory is available through :func:`scan_all_files` instead of widening this API.
    """
    return filter_analyzer_files(scan_all_files(repo_path))


def detect_stack(files: list[Path]) -> list[str]:
    names = {p.name.lower() for p in files}
    text_paths = " ".join(str(p).lower() for p in files)
    stack = []
    if any(p.suffix == ".java" for p in files):
        stack.append("java")
    if any(p.suffix == ".py" for p in files):
        stack.append("python")
    if "pyproject.toml" in names or "requirements.txt" in names or "setup.py" in names:
        stack.append("python_packaging")
    if any("fastapi" in str(p).lower() or "flask" in str(p).lower() for p in files):
        stack.append("python_web_candidate")
    if "pom.xml" in names:
        stack.append("maven")
    if any(p.name.endswith(".gradle") or p.name == "build.gradle" for p in files):
        stack.append("gradle")
    if "liquibase" in text_paths or "changelog" in text_paths:
        stack.append("liquibase")
    if "flyway" in text_paths:
        stack.append("flyway")
    if any("application" in p.name.lower() and p.suffix.lower() in {".yml", ".yaml", ".properties"} for p in files):
        stack.append("spring_config")
    return sorted(set(stack))
