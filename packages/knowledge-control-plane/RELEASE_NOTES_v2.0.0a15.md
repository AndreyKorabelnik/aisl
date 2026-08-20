# analysis-ui 2.0.0a15 — UCP E2E and portable frontend dependencies

Iteration 18 validates the production integration boundary from static analysis through the browser-facing Knowledge API proxy.

## Changed

- replaced 310 private-registry tarball URLs in `frontend/package-lock.json` with canonical public npm registry URLs;
- removed the corporate registry, auth token placeholder and disabled TLS verification from `frontend/.npmrc`;
- added an executable dependency-portability gate and regression tests;
- added a factual UCP compact-source E2E validation record covering runner, DuckDB materialization, reporting, publication, Knowledge API and same-origin proxy.

## Validated

- two UCP-shaped repositories analyzed by `code-analyzer-core 0.38.0` through `static-analysis-runner 0.9.7`;
- workspace Knowledge Layer materialized by `knowledge-layer-core 0.24.0`;
- `data-model-report/v1` completed with all required headings and valid evidence citations;
- immutable revision published through `knowledge-api 0.3.0a2`;
- direct and same-origin proxy responses were byte-identical for health, systems, revisions, tables, `Individual` detail, reports and report content.

## Explicit limitation

The full corporate UCP source archives from the earlier conversation were not mounted in the recovery container, so this checkpoint uses a compact UCP source replay, not the full repository corpus.

The production Vue/Vite command could not complete in the recovery container because its platform-level npm proxy returned `404` for `vue-tsc@2.2.12`. The project lockfile itself is now portable and contains no private registry host or credentials. No prebuilt frontend was substituted and no false build success is claimed.

No Vue template or style section changed.
