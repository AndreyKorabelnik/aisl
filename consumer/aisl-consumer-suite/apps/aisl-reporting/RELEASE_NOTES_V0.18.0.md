# aisl-reporting 0.18.0

Reporting has one canonical knowledge-consumption path: Knowledge API. It no longer opens Prepared Knowledge DuckDB files or imports KLC query services.

`workspace-interaction/v1` retains interaction, field-contract, execution-context, coverage and diagnostics reporting. Direct value-flow graph / attribute-path resolver enrichment remains parked and is not reintroduced through a compatibility route.
