# static-analysis-runner 0.9.10

Iteration 28.2A synchronizes all repository, suite and workspace materialization boundaries with `knowledge-layer-core 0.29.0`.

The required KLC version is now declared once in `static_analysis_runner.version` and reused by all runtime checks, preventing divergent hard-coded contracts.
