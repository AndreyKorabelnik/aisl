#!/usr/bin/env python3
"""Generate the deterministic generic API v1 OpenAPI document."""

from __future__ import annotations

import json
from pathlib import Path

from knowledge_control_plane.api.generic_v1 import create_contract_app

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "api" / "generic-v1.openapi.json"


def main() -> None:
    document = create_contract_app().openapi()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(OUTPUT)


if __name__ == "__main__":
    main()
