# knowledge-api release notes

## 0.37.1

Multi-repository observed Core products now use source-aware copy-on-write product slots, and the stale exact Prepared Runtime dependency pin is replaced by the supported 0.1.x contract range. See `RELEASE_NOTES_V0.37.1.md`.

## 0.23.0

Prepared System Description knowledge is exposed through one thin revision-bound query surface backed by the KLC reporting facade. See `RELEASE_NOTES_V0.23.0.md`.

## 0.21.0

`sql/target-column-lineage` now reads canonical recursive SQL lineage from the prepared SQL knowledge artifact; the obsolete dedicated S2T artifact dependency is removed. See `RELEASE_NOTES_V0.21.0.md`.

## 0.16.0

Publication is driven by `knowledge_execution_result/v1`; revisions contain typed knowledge artifacts and completed capabilities. The old single-DuckDB request and query adapter were removed. See `RELEASE_NOTES_V0.16.0.md`.

## 0.9.0

SQL-only Knowledge Layer publication and the first SQL relation/used-field endpoint with coverage and evidence. See `RELEASE_NOTES_V0.9.0.md`.

## 0.8.0

Compact relationship JOIN contracts in table details and a separate full relationship-detail endpoint. See `RELEASE_NOTES_V0.8.0.md`.

## 0.7.0

Operational `validate` and `publish` CLI, deterministic content/provenance revision identity, initial system creation, PATCH system metadata, revision activation and confirmed permanent system deletion. See `RELEASE_NOTES_V0.7.0.md`.

## 0.5.1

Request-validation serialization is compatible with FastAPI `RequestValidationError`; invalid publication payloads now return canonical 422 JSON instead of failing inside the exception handler.

## 0.5.0

The canonical `/api/knowledge/v1/**` contract is now the only public runtime. Registry-based compatibility routes and duplicate API surfaces were removed. The KLC query adapter remains internal and preserves `data_model_api/v3` behavior.
