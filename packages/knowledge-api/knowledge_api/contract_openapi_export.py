from __future__ import annotations

import argparse
import json
from pathlib import Path

from .contract_v1 import create_contract_app


def export_contract_openapi(output: str | Path) -> Path:
    path = Path(output).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(create_contract_app().openapi(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Export the Knowledge API OpenAPI document")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    print(export_contract_openapi(args.output))


if __name__ == "__main__":
    main()
