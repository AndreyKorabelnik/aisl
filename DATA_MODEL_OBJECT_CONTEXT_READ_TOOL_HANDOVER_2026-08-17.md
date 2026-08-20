# Data Model Object Context Read Tool — Handover

Date: 2026-08-17
Status: DATA_MODEL_OBJECT_CONTEXT_READ_TOOL_COMPLETE

## Architecture decision

The Knowledge API remains deterministic and LLM-free. External LLM/agent runtimes consume Knowledge API tools from a Consumer Kit. `knowledge-external-llm` is a demo/debug harness, not the production reasoning boundary.

## Completed

- Added one new object-centric read tool: `get_data_model_object_context`.
- Reused existing declared-model, logical-storage-mapping and model-storage-semantics knowledge.
- Added no new framework concept/analyzer/materializer.
- Preserved missing optional storage knowledge as explicit `not_available`.
- Kept physical SQL/PDM join separate and unconfirmed by this projection.

## Versions

- prepared-knowledge-runtime 0.1.0.post13
- knowledge-integration 0.1.16
- knowledge-api 0.38.0
- all other framework versions unchanged; see `VERSIONS.md`.

## Acceptance / tests

See `DATA_MODEL_OBJECT_CONTEXT_READ_TOOL_ACCEPTANCE.md` and `DATA_MODEL_OBJECT_CONTEXT_READ_TOOL_TEST_STATUS.md`.

## Known limitation / next product choice

The existing UCP `build-data-model-v1` revision used for smoke testing contains declared-model products only. Therefore its new object-context response has `storage_context.status = not_available`. If a richer UCP data-model publication is desired, decide separately how existing storage products become optional members of the same revision without making storage evidence mandatory for generic data-model builds.

## Parked scope

No previously parked portfolio/islands scope is resumed.
