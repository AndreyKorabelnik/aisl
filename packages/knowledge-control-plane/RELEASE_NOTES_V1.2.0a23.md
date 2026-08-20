# knowledge-control-plane 1.2.0a23

- Stops recursively indexing/hash-scanning producer-internal Core evidence payload packages after Runner completion.
- KCP still indexes the immediate typed Core evidence descriptor and orchestration/materialization artifacts.
- The payload remains on disk and referenced through canonical Core/Runner provenance; KCP does not become a second evidence catalog.
- Fixes fresh one-shot publication stalls on large evidence packages while preserving consumer/publication semantics.
