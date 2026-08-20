# knowledge-layer-core 0.53.5

## User-facing portfolio islands JSON

`build_portfolio_topology` now publishes `portfolio-interaction-islands.json` alongside the compact DuckDB artifact.

The export contains:

- strict and extended island sets with deterministic island IDs and sorted repository membership;
- repository-level connectivity classification (`connected`, `isolated`, `no_observed_edges`, `unknown`);
- directed repository interactions and operation counts;
- per-island members, degrees, protocols, confidence counts and coverage;
- repository and diagnostic summaries;
- a deterministic topology fingerprint independent of generation time.

A repository whose analysis failed is explicitly classified as `unknown`; it is not presented as a proven isolated repository. The export can also be regenerated from an existing topology artifact with `export_portfolio_interaction_islands`.
