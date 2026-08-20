# Consumer retrieval orchestration — framework-side change report

Date: 2026-08-14

Only framework package changed: `knowledge-integration 0.1.3 -> 0.1.6`.

Changes are consumer-contract/model-view only:
- lexical declared-model search guidance;
- explicit `source_has_more` vs `projection_truncated`;
- deterministic batch model-result merge/dedup with query/task provenance.

No Core/Runner/KLC/Knowledge API/KCP/Prepared Knowledge changes. No prepared revision rebuild is required. Assistant/Chat runtime changes remain in the separate standalone Chat handoff.
