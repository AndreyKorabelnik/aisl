# Test results — static-analysis-runner 0.10.7

Scope: declarative Knowledge Product Catalog only. No Core/KLC/API implementation changes.

## Focused regression

- Knowledge planning + execution planning + architecture audit: PASS.
- Generic knowledge execution + physical-model typed-route smoke with KLC 0.59.26 on PYTHONPATH: PASS.
- `compileall static_analysis_runner tests`: PASS.
- Product catalog JSON parse: PASS.
- Product catalog JSON Schema parse: PASS.
- Wheel build with `--no-build-isolation`: PASS.
- Packaged resource present in wheel: PASS.
- Installed-wheel `load_knowledge_product_catalog()`: PASS (`0.10.7`, 16 products).
- `_KNOWLEDGE_POLICY` absent from Runner package code: PASS.

## Semantic equivalence

Baseline: Runner 0.10.6 compiled `knowledge_catalog/v2`.
Current: Runner 0.10.7 compiled `knowledge_catalog/v2` from `knowledge_product_catalog/v1`.

Result: semantic equality PASS after excluding only:

- `runner_version`;
- compiled `catalog_fingerprint`;
- new product-catalog provenance fields (`schema`, `fingerprint`, `catalog_id`, `source`).

Machine-readable report:
`validation/knowledge_product_catalog_v0.10.7/semantic_diff.json`.

## Acceptance

A new selectable knowledge product referencing the existing `sql-analysis` materialization
is added only to a temporary declarative catalog. No Runner Python branch is added.
The compiled catalog exposes 17 selectable products and the resolution plan resolves the
new product to `sql-analysis`: PASS.

No long repository-analysis E2E was run because this change does not alter Core evidence,
KLC materialization execution, or repository scanning.
