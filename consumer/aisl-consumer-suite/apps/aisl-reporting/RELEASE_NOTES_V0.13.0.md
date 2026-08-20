# aisl-reporting 0.13.0

## Iteration 85 — SQL Source Inventory business report

- Added profile `sql-source-inventory-report/v1`.
- Consumes the canonical `sql-source-inventory/v1` through `ReportingQueryService`; no direct DuckDB SQL and no repeated source-code analysis.
- Produces a complete catalog of external physical/physical-template sources and all deterministically bound fields.
- Adds role analysis for projection, join, filter and window usage, top/reused sources, join/filter-only sources and explicit coverage limitations.
- Keeps ambiguous/unmapped usages outside per-source fields and forbids LLM classification or assignment.
- Extended report validation to accept canonical SQL relation and column-usage evidence IDs.
