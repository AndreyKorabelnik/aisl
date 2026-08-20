# knowledge-layer-core 0.59.20

## Ultimate SQL target-to-source mapping mart

The cross-artifact data-model materialization now publishes `cross_artifact_target_source_mapping`.
It records target physical columns against terminal SQL source relation columns after recursively
crossing observed repository-local physical relation producers.

Key properties:
- source mappings do not require a Java/logical-model binding;
- intermediate physical relations remain present in projection/materialization provenance but are not terminal sources when an observed producer exists;
- traversal is based on observed relation materializations and workflow dependencies, never on `stg_*` naming or semantic-role guessing;
- original SQL relation/column spelling and the full projection/materialization paths are retained;
- composed transformation descriptors are materialized from the observed projection path.

The cross-artifact model schema is now `cross-artifact-data-model-mapping/v6` and publishes capability `common.sql-target-source-mapping`.
Knowledge API projection is intentionally deferred until real `epk_client` validation confirms the KLC semantics.
