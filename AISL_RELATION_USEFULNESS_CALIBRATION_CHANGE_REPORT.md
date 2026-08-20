# Change report — relation usefulness calibration

## Changed packages

- knowledge-layer-core: `0.61.0a31 -> 0.61.0a32`
- knowledge-integration: `0.1.9 -> 0.1.10`

## KLC

`data-model-attribute-extension-context/v1` now publishes a consumer-oriented `basis.usefulness` classification without changing observed evidence or the original technical `confidence`.

This classification is derived from existing typed evidence and keeps its basis, residual checks, cardinality, and ambiguity explicit. Analog JOIN examples stay useful but are not promoted to exact observed JOINs.

Materialization runtime also removes execution-local metadata from the persisted canonical KnowledgeProduct manifest before product identity hashing. This fixes nondeterministic product identity caused by timestamps/local paths while preserving execution-level provenance in the execution result.

## Knowledge Integration

`attribute-addition-plan/v1` profile version 12 instructs external agents to consume `basis.usefulness`, preserve many-valued relations, and expose polymorphic ambiguity rather than making silent choices.

## Architecture

No second producer, materializer, graph store, dual-read path, compatibility adapter, Core parser, or API execution path was added.
