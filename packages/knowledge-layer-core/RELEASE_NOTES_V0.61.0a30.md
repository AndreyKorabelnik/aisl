# knowledge-layer-core 0.61.0a30

- Fixes persistence-lineage ProductItem identity at the typed product owner boundary.
- Each of the six `persistence-lineage/v1` artifact families now uses its own canonical record ID field rather than the generic subject-record ID heuristic.
- Missing required product-owned IDs fail materialization explicitly; no fallback to a related nested ID is performed.
- This enables stable exact AISL reads such as `source_to_storage_lineage_000108` without changing Core evidence semantics.
