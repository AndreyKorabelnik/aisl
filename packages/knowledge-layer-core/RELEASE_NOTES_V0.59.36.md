# knowledge-layer-core 0.59.36

Adds a read-only query surface for the already materialized `code-declared-data-model/v1`: lexical object/field/documentation search and exact object detail with effective fields, inheritance and declared relationships. The read layer does not infer business meaning, storage JOINs or physical mappings.

The generic query capability catalog also derives the existing `common.code-declared-*` capabilities from canonical materialized tables when a legacy/minimal artifact has no declared manifest capabilities. This is read-time discoverability only; no producer contract or materialization is changed.
