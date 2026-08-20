# knowledge-layer-core 0.59.34

Fix a contract/manifest mismatch discovered by the final `data-model-attribute-extension` product E2E.

`cross-artifact-data-model-mapping/v6` already materialized `cross_artifact_target_source_mapping` rows and its materialization contract already declared capability `common.sql-target-source-mapping`, but the produced Knowledge Layer manifest omitted both the mart name and capability.

0.59.34 makes the runtime manifest match the knowledge actually present in the artifact. No new inference, analyzer or matching rule is introduced.
