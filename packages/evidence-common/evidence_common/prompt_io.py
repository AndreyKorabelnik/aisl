from __future__ import annotations

from pathlib import Path

from .files import sha256_text


def load_prompt(prompt_file: Path) -> tuple[str, str]:
    if not prompt_file.exists() or not prompt_file.is_file():
        raise FileNotFoundError(f"Prompt file not found: {prompt_file}")
    return prompt_file.read_text(encoding="utf-8", errors="ignore"), str(prompt_file)


def prompt_sha256(text: str) -> str:
    return sha256_text(text)
