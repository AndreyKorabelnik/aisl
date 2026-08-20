# Real validation — knowledge-api 0.19.2

## Input

Clean real product run:
`/mnt/data/data_model_real_run/final-product-0109-05934`

Versions:
- code-analyzer-core 0.44.16
- static-analysis-runner 0.10.9
- knowledge-layer-core 0.59.34
- knowledge-api 0.19.2

The API published the completed `knowledge_execution_result/v1` and selected the typed artifact `data-model-attribute-extension-context/v1` by model kind/capability.

## C2 HTTP gate

Query filters:
- source type: `com.sbt.bm.ucp.retail.model.individual.BirthPlace`
- source field: `country`
- target type: `com.sbt.bm.ucp.common.model.dictionary.Country`

Result:
- HTTP 200
- total: 1
- join method: `resolve_reference_value_to_target_key`
- confidence: `confirmed`
- SQL generation status: `transformation_required`
- exact structural correspondence count: 1
- BirthPlace SQL source anchors: present
- Country SQL target/join anchors: present
- target field usages include `name`: yes
- diagnostics: none for this relationship

## Boundary

This validates read-only publication/query only. SQL generation remains a downstream agent responsibility.
