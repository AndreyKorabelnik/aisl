from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path


def remove_path(path: Path) -> None:
    target = Path(path)
    if not target.exists() and not target.is_symlink():
        return
    if target.is_dir() and not target.is_symlink():
        shutil.rmtree(target)
    else:
        target.unlink()


def publish_directory_atomic(
    staging_path: Path,
    output_path: Path,
    *,
    replace: bool,
    existing_label: str = "knowledge-layer output",
) -> None:
    staging = Path(staging_path)
    output = Path(output_path)
    if output.exists() or output.is_symlink():
        if not replace:
            raise FileExistsError(f"{existing_label} already exists: {output}")
        backup = output.with_name(f".{output.name}.previous-{os.getpid()}-{uuid.uuid4().hex[:12]}")
        os.replace(output, backup)
        try:
            os.replace(staging, output)
        except Exception:
            os.replace(backup, output)
            raise
        else:
            remove_path(backup)
        return
    os.replace(staging, output)
