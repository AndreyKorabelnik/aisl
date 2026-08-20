# static-analysis-runner 0.9.35

## Portfolio topology scale pilot

- Added the dedicated `portfolio-topology` analysis task and Core profile routing.
- Portfolio topology repository suites now skip the reusable deep-analysis foundation. Other repository suites keep the existing shared-foundation behaviour.
- Added `--repository-limit N` with `--max-repositories` as an alias.
- The limit is applied to the deterministic prefix returned by Bitbucket pagination or the offline source manifest.
- Run manifest and summary publish selection mode, requested limit, source count, selected count, whether the limit was reached, and whether the source was truncated.
- Persistent repository shards retain only HTTP topology boundaries used by Islands v1; AT900 shrank from 131 source interfaces / 2.63 MB to 41 selected boundaries / 82.7 KB. Deferred REST responses and Kafka boundaries are counted in catalog selection metadata and will be enabled in the Kafka block.
- Added tests for Bitbucket pagination stopping at the requested limit, offline manifest prefix selection, CLI aliases, no-foundation topology suite execution, and compact boundary filtering.

## Validation

- Real AT900 `client-profile`: 1,038 files, 131 interface boundaries, complete end-to-end topology run in 11.90 seconds, peak process RSS 494,052 KiB.
- Three-entry AT900-derived manifest with `--repository-limit 2`: exactly two repositories processed in 22.31 seconds; the third repository was not cloned or analyzed.
- Requires Code Analyzer Core 0.43.19 for the dedicated topology profile and Knowledge Layer Core 0.53.7 for canonical `portfolio-topology` task materialization.

- KLC assembly benchmark: 1,600 Runner-pruned AT900-shaped catalogs, 65,600 HTTP boundaries, complete islands materialization and JSON export in 26.613 seconds; peak process RSS 1,269,504 KiB.
