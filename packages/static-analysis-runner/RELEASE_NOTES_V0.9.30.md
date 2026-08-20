# static-analysis-runner 0.9.30

## Portfolio topology contracts

Added protocol-neutral contracts for the HTTP Islands MVP:

- `portfolio_repository_sources/v1` — deterministic repository inventory after project discovery;
- `repository_topology_result/v1` — persistent per-repository topology result after the clone is removed;
- `portfolio_interaction_islands/v1` — user-facing strict/extended islands payload validation.

The contracts deliberately do not encode HTTP-only graph semantics. Kafka can extend the same boundary model later without replacing the orchestration contracts.

Within one island mode a repository may occur in exactly one island. Overlapping/custom island criteria remain outside Islands v1.
