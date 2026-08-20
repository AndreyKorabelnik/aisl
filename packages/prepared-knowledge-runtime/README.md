# Prepared Knowledge Runtime 0.1.0

`prepared-knowledge-runtime` is the canonical lightweight runtime for reading already materialized Prepared Knowledge artifacts.

It owns the typed consumer/query contracts, read-only DuckDB query services, portable artifact/manifest helpers used by the read boundary, and shared deterministic primitives required by those contracts.

It does **not** own or execute repository analysis, Core analyzers, Runner planning, KLC materialization, knowledge production catalogs, or orchestration.

Runtime dependency: `duckdb>=1.1.0`.

Primary consumer: `knowledge-api`.

The read path is intentionally:

`Prepared Knowledge -> prepared-knowledge-runtime -> Knowledge API -> consumers`.
