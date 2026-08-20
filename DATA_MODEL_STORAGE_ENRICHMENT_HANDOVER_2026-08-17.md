# Data Model Storage Enrichment — Handover

Date: 2026-08-17
Status: DATA_MODEL_STORAGE_ENRICHMENT_E2E_COMPLETE

## Architecture result

The earlier read-tool block is now complete end-to-end.

Producer path:

`Sources -> Core observed evidence -> Runner canonical planning -> KLC declared/storage products -> AISL publication`

Consumer path remains:

`Published Prepared Knowledge -> Knowledge API -> Consumer Kit tools -> external LLM/agent`

Knowledge API remains deterministic and LLM-free. External LLMs select/call tools; `knowledge-external-llm` remains only a demo/debug harness.

## What changed

- Runner 0.10.28 adds one generic optional-internal-materialization mechanism to the existing knowledge planner.
- `code-declared-data-model` optionally composes existing storage products through the existing KLC dependency graph.
- KCP 1.2.0a31 only repins the canonical generated runtime bundle.
- Core and KLC semantics were not changed because existing evidence/materializers already contain the required facts.

## Real acceptance point

The isolated UCP rebuild publishes revision `rev-88415df4d14df2ff3827b01c`. `Individual` now returns rich deterministic storage context through `get_data_model_object_context`; `birthPlace` ambiguity and missing physical join remain explicit rather than guessed.

## Operational consequence

Existing data-model revisions created before this block are immutable and do not gain storage products retroactively. A deployment/user must run `build-data-model-v1` once with Runner 0.10.28 / KCP 1.2.0a31 to create a new enriched revision, then regenerate the `data-model/v1` Consumer Kit for that revision.

## Parked scope

No previously parked portfolio/islands/other product scope is resumed by this block.

## Continuation point

This block has no unfinished storage-composition task. Continue only from a new product-value requirement or a separately chosen validation/benchmark task; do not reopen Core/KLC cleanup merely because optional composition now exists.
