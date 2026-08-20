# knowledge-layer-core 0.59.5

Completes the cross-repository value-flow restoration on real applications and removes the remaining evidence-ingestion bottleneck.

- `value_flow_knowledge_builder` now batch-inserts typed evidence records with the existing `bulk_insert` helper inside the transaction introduced in 0.59.4.
- No value-flow semantics or matching rules changed.
- Real four-application E2E restored 231 HTTP transport edges and end-to-end attribute-path traversal across repository boundaries.
