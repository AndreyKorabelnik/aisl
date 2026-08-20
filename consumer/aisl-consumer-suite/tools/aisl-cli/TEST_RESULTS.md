# aisl-cli 0.2.0 — Test Results

- Python SDK + CLI targeted suite: 21/21 PASS.
- `aisl --version`: PASS (`0.2.0`).
- `aisl --help`: PASS.
- real UCP `revision`: PASS.
- real UCP `tools --profile data-model/v1`: PASS.
- real UCP `project data-model-object --object Individual`: PASS; 41 relationships, 5 executable storage joins.
- CLI has no direct httpx/requests/urllib transport implementation: PASS.
