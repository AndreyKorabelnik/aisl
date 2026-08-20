# knowledge-layer-core 0.52.7

Version 0.52.7 adds explainable read-only ranking of likely SQL destination tables for assistant workflows.

## Added

- `KnowledgeLayerQuery.find_sql_target_candidates(...)`;
- capability `common.sql-target-resolution`;
- deterministic candidate aggregation from already materialized facts:
  - workflow target bindings such as `main_table_name`;
  - resolved placeholders used as target relations;
  - observed write targets and physical target definitions;
  - exact read observations outside the target's own workflow;
  - existing semantic output roles;
  - source relation and column hints inside workflow-reachable SQL;
  - business entity hints;
  - explicit technical/intermediate name diagnostics.

## Contract boundary

- no LLM runs inside KLC;
- no new DuckDB table or rematerialization is required;
- scores order observed candidates but do not turn weak signals into canonical facts;
- each evidence category contributes once, regardless of how many workflows repeat the same target;
- all reasons, alternatives, source matches and diagnostics remain visible.

## Real repository result

On the unchanged `datamart_profile_fl` DuckDB, with source hints `Individual`, `BirthPlace`, `Region`, columns `birthPlace`, `regionCode`, `name`, and business entity `client`:

1. `epk_client` — rank 1, `published_or_terminal`;
2. specialised client outputs follow as alternatives;
3. `epk_client_v2` remains a workflow target with direct source-context matches, but is not selected as the final published destination.

The result is produced directly from the 0.52.6 artifact; no rebuild is needed.
