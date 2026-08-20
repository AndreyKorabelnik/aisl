# Knowledge API 0.32.0 — changed files

- `knowledge_api/contract_v1/models.py` — canonical `physical_artifacts[]` published-product model.
- `knowledge_api/publication.py` — multi-file Core SQL package validation/discovery and partial observed publication semantics.
- `knowledge_api/contract_v1/service.py` — role-based CAS import, publication and universal read routing.
- `knowledge_api/contract_v1/runtime.py` — physical role is addressing metadata, excluded from byte-artifact validation payload.
- `schemas/knowledge-v1.openapi.json` — regenerated public schema.
- `tests/test_aisl_multifile_observed_persistence.py` — multi-file, tamper and partial/failed publication guards.
- `tests/test_aisl_observed_persistence.py` — first single-file pilot updated to the unified physical representation.
