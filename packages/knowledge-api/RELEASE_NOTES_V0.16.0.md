# knowledge-api 0.16.0

## Breaking publication contract

Knowledge API now publishes `knowledge_execution_result/v1` instead of a single caller-selected DuckDB.

A revision stores:

- execution summary and immutable execution-result artifact;
- all typed knowledge artifacts produced by completed KLC materializations;
- published capabilities;
- optional report.

Removed without adapters:

- `PublicationSource` and repository revision fields from the publication request;
- `knowledge_layer` request field;
- CLI `--knowledge-layer` and `--source-manifest`;
- old single-database revision columns;
- the old combined data-model query adapter.

A pre-0.16 SQLite catalog is rejected. No schema migration or dual read is provided.

## Typed query routing

- data-model routes read `effective-data-model/v1`;
- physical-model routes read `model_kind=physical-data-model`;
- SQL routes read an artifact publishing `common.sql*` capabilities;
- missing or ambiguous artifacts produce explicit diagnostics.

## New endpoints

- `GET /systems/{system_id}/knowledge-artifacts`;
- `GET /systems/{system_id}/knowledge-artifacts/{artifact_id}`;
- `GET /systems/{system_id}/capabilities`.

## Validation

Publication validates execution-result fingerprint and policy, completed DAG nodes, materialization outputs, capabilities, manifests, database digests, allowed roots and typed queryability.
