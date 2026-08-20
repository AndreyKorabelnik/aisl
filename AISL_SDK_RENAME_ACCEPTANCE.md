# AISL SDK Rename — Acceptance

Date: 2026-08-19
Status: PASS for targeted rename scope

## Acceptance evidence

- Python SDK + CLI tests: 21/21 PASS.
- aisl-agent-runtime tests: 4/4 PASS.
- aisl-reporting tests: 98/98 PASS.
- TypeScript SDK contract generation/build/test: PASS.
- Workbench SDK vendor/build/test: PASS.
- Python compile/import: PASS.
- `aisl_sdk` clean-wheel import: PASS.
- `aisl_client` import absent: PASS.
- old Python distribution `aisl-client` absent from clean install: PASS.
- TypeScript `.tgz` install/import/basic call: PASS.
- CLI direct duplicate HTTP transport search: none observed.
- representative real UCP read through built SDK/CLI against pinned revision `rev-8bed9d612efcdac7198640ad`: PASS.
- `Individual`: 52 fields, 41 relationships, 5 `executable_storage_join`, 33 ambiguous, 3 unresolved/not-ready.

Initial JavaScript test attempts without their required fixture services failed due to missing harness/server state; both were rerun with their intended mock services and passed. These are not classified as runtime failures.

Full framework regression was not run and is not claimed PASS.
