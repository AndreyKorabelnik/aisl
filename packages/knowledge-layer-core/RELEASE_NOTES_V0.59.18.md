# knowledge-layer-core 0.59.18

## Standalone System Description reporting facade

`ReportingQueryService` now consumes a standalone `system-description/v1` materialization without requiring unrelated general-workspace tables.

When only `common.system-description/*` capabilities are present, the facade projects already materialized subject records into:
- repository/module composition from observed build-dependency locations;
- declared technologies from Gradle artifact observations;
- observed storage targets from storage-usage summaries;
- explicit scenario-composition gap summary;
- materialization coverage from the knowledge manifest.

No new source analysis or business inference is performed. General workspace behavior is unchanged when its relations are available.
