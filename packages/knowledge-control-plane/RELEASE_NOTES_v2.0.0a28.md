# Analysis UI 2.0.0a28

Adds the prepared-context wizard to the existing browser UI. Users can register or select
already analyzed source-model, SQL-datamart and optional PDM DuckDB artifacts, create a
context with pinned Knowledge API revisions, and continue in the standard Markdown/SQL
chat. The wizard does not request a target table; automatic target and insertion-point
resolution remain backend responsibilities. Direct browser routes are served by the existing
FastAPI frontend fallback.
