from __future__ import annotations

import hashlib
import os
import re
import subprocess
from pathlib import Path
from typing import Callable

from .execution import command_parts, run_process

MIN_CODE_ANALYZER_CORE_VERSION = (0, 36, 27)


_FINGERPRINT_IGNORED_DIRECTORIES = {
    ".git", ".gradle", ".idea", "__pycache__", "build", "dist", "node_modules", "out", "target"
}


def _content_fingerprint(repository: Path) -> str:
    digest = hashlib.sha256()
    files: list[Path] = []
    for current, directories, names in os.walk(repository, topdown=True, followlinks=False):
        directories[:] = sorted(
            item for item in directories if item not in _FINGERPRINT_IGNORED_DIRECTORIES
        )
        base = Path(current)
        for name in sorted(names):
            files.append(base / name)
    for path in sorted(files, key=lambda item: item.relative_to(repository).as_posix()):
        relative = path.relative_to(repository).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        if path.is_symlink():
            digest.update(b"symlink:")
            digest.update(os.readlink(path).encode("utf-8", errors="surrogateescape"))
        else:
            try:
                with path.open("rb") as handle:
                    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                        digest.update(chunk)
            except OSError as exc:
                digest.update(f"unreadable:{exc.__class__.__name__}".encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def repository_revision(repository: Path) -> dict:
    git_dir = repository / ".git"
    if git_dir.exists():
        try:
            head = subprocess.run(
                ["git", "-C", str(repository), "rev-parse", "HEAD"],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
            ).stdout.strip()
            dirty = bool(
                subprocess.run(
                    ["git", "-C", str(repository), "status", "--porcelain"],
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True,
                    encoding="utf-8",
                ).stdout.strip()
            )
            payload = {"kind": "git", "revision": head, "working_tree_dirty": dirty}
            if dirty:
                payload["working_tree_content_sha256"] = _content_fingerprint(repository)
            return payload
        except Exception:
            pass
    fingerprint = _content_fingerprint(repository)
    return {"kind": "content", "revision": f"sha256:{fingerprint}", "content_sha256": fingerprint}


def _parse_version_identity(value: str) -> tuple[str, tuple[int, int, int]]:
    match = re.search(
        r"(?<![A-Za-z0-9])((\d+)\.(\d+)\.(\d+)[A-Za-z0-9.+-]*)(?![A-Za-z0-9])",
        value,
    )
    if not match:
        raise ValueError(f"cannot parse code-analyzer-core version from output: {value!r}")
    return match.group(1), tuple(int(part) for part in match.groups()[1:])


def _parse_version_tuple(value: str) -> tuple[int, int, int]:
    return _parse_version_identity(value)[1]


def validate_core_version(
    *,
    core_command: str,
    log_path: Path,
    progress: Callable[[str], None] | None = None,
    minimum_version: tuple[int, int, int] = MIN_CODE_ANALYZER_CORE_VERSION,
) -> str:
    command = command_parts(core_command) + ["version"]
    if progress:
        progress("Checking code-analyzer-core version")
    result = run_process(command, log_path=log_path, echo=progress)
    if result.returncode != 0:
        raise RuntimeError(f"code-analyzer-core version check exited with code {result.returncode}")
    raw = result.log_path.read_text(encoding="utf-8", errors="replace")
    exact_version, actual = _parse_version_identity(raw)
    if actual < minimum_version:
        required = ".".join(str(part) for part in minimum_version)
        found = ".".join(str(part) for part in actual)
        raise RuntimeError(
            f"code-analyzer-core is too old: found {found}, required >= {required}"
        )
    return exact_version
