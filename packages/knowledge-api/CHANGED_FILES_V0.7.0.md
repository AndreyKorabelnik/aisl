# Changed files — knowledge-api 0.7.0

- `knowledge_api/cli.py` — operational subcommands and readable JSON/text output.
- `knowledge_api/publication.py` — artifact descriptors, manifest provenance and metadata parsing.
- `knowledge_api/contract_v1/models.py` — system update/delete contract models.
- `knowledge_api/contract_v1/contract.py` — PATCH, DELETE and revision activation endpoints.
- `knowledge_api/contract_v1/service.py` — validation workflow, stable revision identity and administration services.
- `knowledge_api/contract_v1/store.py` — update/delete persistence operations.
- `knowledge_api/version.py`, `pyproject.toml` — 0.7.0 and KLC 0.29.1 dependency.
- `schemas/knowledge-v1.openapi.json` — regenerated canonical OpenAPI.
- focused tests for CLI, publication builder and system administration.
