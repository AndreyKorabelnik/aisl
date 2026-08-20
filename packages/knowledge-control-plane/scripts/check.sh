#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export TERM="${TERM:-dumb}"

python scripts/verify_source_manifest.py
PYTHONPATH="src${PYTHONPATH:+:$PYTHONPATH}" python -m compileall -q src/knowledge_control_plane
PYTHONPATH="src${PYTHONPATH:+:$PYTHONPATH}" python -m pytest -q \
  tests/test_module_baseline.py \
  tests/test_generator_headless_boundary.py \
  tests/test_generic_api_contract.py \
  tests/test_knowledge_api_proxy.py \
  tests/test_runtime_store_lifecycle.py
