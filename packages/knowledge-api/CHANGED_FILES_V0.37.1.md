# Changed files — 0.37.1

- `knowledge_api/publication.py` — one canonical source-aware observed product slot builder and duplicate-slot validation.
- `knowledge_api/contract_v1/service.py` — publication uses the same canonical observed slot builder.
- `tests/test_aisl_observed_persistence.py` — multi-repository publication, source-scoped incremental replacement and real duplicate rejection coverage.
- `tests/test_aisl_multifile_observed_persistence.py` — source-aware expected SQL observed slot.
- `knowledge_api/version.py`, `pyproject.toml` — version 0.37.1 and compatible Prepared Runtime dependency range.
- `schemas/knowledge-v1.openapi.json` — regenerated canonical OpenAPI for 0.37.1.
