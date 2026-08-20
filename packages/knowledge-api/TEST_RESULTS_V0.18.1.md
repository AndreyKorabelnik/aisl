# Test results — knowledge-api 0.18.1

## Automated tests

- Full knowledge-api suite: 55 passed in 14.11s.
- Focused SQL/publication/runtime suite: 27 passed in 9.55s.
- `compileall knowledge_api`: OK.
- OpenAPI export: version 0.18.1, 36 paths.
- Source manifest: 148 files verified.

## Real E2E

Published the completed `ucp-datamart-pdm` execution result as active revision `rev-1d36f6678966a51259336123`.

Validated over HTTP:

- systems and revisions;
- seven typed knowledge artifacts and 29 capabilities;
- effective data model: 1,326 entities;
- physical model: 522 tables, 498 keys, 370 relationships;
- SQL relations and source inventory;
- workspace SQL catalog.

The pre-fix SQL query returned `409 knowledge_artifact_ambiguous` because both repository SQL knowledge and the workspace SQL catalog published `common.sql*` capabilities. Version 0.18.1 deterministically selects the workspace catalog when present and the repository SQL artifact only when no workspace catalog exists.
