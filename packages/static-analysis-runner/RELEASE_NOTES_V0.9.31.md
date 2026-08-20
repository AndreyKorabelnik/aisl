# static-analysis-runner 0.9.31

## Sequential Bitbucket portfolio topology

Added the independent `portfolio-topology` workflow:

- discovers every repository in a Bitbucket Data Center project with pagination;
- supports an offline `portfolio_repository_sources/v1` manifest for deterministic tests;
- clones one repository at a time with shallow, single-branch, no-tags semantics;
- skips Git LFS object download and does not initialize submodules;
- runs the topology-only `system-description` suite;
- persists a compact self-contained repository result;
- rewrites evidence file paths to repository-relative paths before the clone is removed;
- removes the clone and temporary analysis output in `finally` after every repository;
- continues after clone or analysis failure and publishes a placeholder topology suite so KLC coverage records the repository as failed rather than isolated;
- assembles the final `portfolio-topology/v1` artifact with the existing KLC builder;
- keeps tokens/passwords out of process arguments, logs and persisted repository URLs.

The default clone concurrency and analysis concurrency are both one. Kafka matching is intentionally not part of this release.
