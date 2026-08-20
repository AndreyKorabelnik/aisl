# Knowledge Layer Core 0.61.0a1

S2T / target-column-lineage hardening checkpoint.

- Canonical workflow target-column lineage now reuses the existing `SqlProducerColumnTraversal` and observed materialization index instead of maintaining a weaker local CTE/wildcard tracer.
- Unqualified `SELECT *` over a unique observed relation now propagates the requested column without name guessing.
- Observed physical relation producers are traversed across SQL units on the canonical `common.sql-target-column-lineage` surface.
- Window/control-only usages remain excluded from value origins.
- Materialization/workflow-dependency IDs are retained in branch provenance.
- No new analyzer, materializer, API route, compatibility adapter, or Gold-specific rule was added.
