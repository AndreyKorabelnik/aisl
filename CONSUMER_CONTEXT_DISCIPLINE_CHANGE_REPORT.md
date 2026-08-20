# Consumer context discipline — change report

Date: 2026-08-14
Status: A_H_COMPLETE

## Problem observed in supplied traces

Knowledge API latency was small, but raw Knowledge API payloads were copied into every subsequent LLM request. Broad declared-model searches and exact-object reads produced hundreds of KB of repeated context. Some batches also exhausted the interaction budget or made unsupported completeness claims.

## Architecture

No Core/Runner/KLC producer changes were required.

- `knowledge-integration 0.1.3` owns reusable model-facing result projections.
- `knowledge-assistant 0.25.1.post11` owns session/runtime coverage, stopping guidance, protocol recovery and LLM context assembly.
- raw Knowledge API ToolResponse remains the provenance/source-of-truth payload in tool trace.
- compact LLM projection never silently means absence; truncation/continuation metadata is explicit.

## Changes

1. `search_declared_data_objects` -> bounded discovery cards. Raw fields returned by a broad search are not copied into LLM context; field presence is explicit and exact object read is required.
2. `get_declared_data_object` -> complete compact structural representation retaining every effective field and relationship while removing repeated AST/annotation detail.
3. Runtime-owned retrieval coverage: scan visibility, projection truncations, exact reads, novelty, search history and budget exhaustion.
4. Budget exhaustion is an explicit diagnostic; uninvestigated parts must be `gap/insufficient_search_coverage`, not semantic absence.
5. CLI traces record raw-vs-LLM result sizes and max LLM request chars.
6. Invalid model response reinjection during protocol recovery is bounded to 8K chars.
7. Attribute-search utility retries `gap` rows, does not retry semantic `unresolved`, and keeps `basis` compact.

## Not changed

- Core evidence extraction.
- Runner execution.
- KLC materialization.
- Knowledge API data semantics/endpoints.
- physical/storage mapping semantics.

## Optional next optimization

Generic batch tool execution was intentionally not implemented. Per plan, decide on it only after a real rerun with the bounded-context implementation.
