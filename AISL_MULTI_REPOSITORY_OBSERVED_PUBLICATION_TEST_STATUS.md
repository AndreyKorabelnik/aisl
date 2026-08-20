# AISL multi-repository observed publication — test status

Date: 2026-08-17

- Canonical baseline SHA-256 before change: `364207d1e1926476bbf2d57729f6d043ceaf30e569c667b26a5637d1faaee1ec` — verified before modification.
- Targeted observed/AISL persistence regression: 10/10 PASS.
- Contract/OpenAPI focused tests: 2/2 PASS.
- Python compile for changed runtime/tests: PASS.
- Real UCP `build-data-model-v1` with two repositories: PASS through publication.
- Published revision: `rev-cf1820d42ff0cf021ccb358a`.
- Full framework regression: not run; change is isolated to Knowledge API publication identity and package metadata. Core/Runner/KLC source trees are unchanged.
