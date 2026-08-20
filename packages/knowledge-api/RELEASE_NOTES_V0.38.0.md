# knowledge-api 0.38.0

Date: 2026-08-17

## Object-centric data-model context

Adds `GET /api/knowledge/v1/systems/{system_id}/data-model/object-context/{object_id}`.

The endpoint is a deterministic read projection over already-published knowledge. It returns the declared object, fields and relationships and, when the selected revision contains the existing logical/model-storage products, exact storage mapping semantics, derivations, provenance and gaps.

The endpoint never invokes an LLM and never promotes logical/model-storage relations to a confirmed physical SQL/PDM join. Missing optional storage products are surfaced as `not_available`; physical mapping remains `not_observed` unless a future read model explicitly consumes such evidence.

No new analyzer, concept detector, materializer, or knowledge source is introduced.
