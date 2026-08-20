# AISL Persistence Boundary Pilot — Change Report

Date: 2026-08-16

## Changed runtime modules

### Knowledge API 0.31.0

- Added filesystem AISL content-addressed immutable Artifact Store.
- Publication imports/finalizes execution result, observed product bytes and derived product database/manifest before revision visibility.
- Added first observed Core KnowledgeProduct publication for `java-type-structure-evidence/v1`.
- Generalized published product metadata with `origin_kind`, `product_slot_id`, producer contract/reference and exact dependency product ids.
- Copy-on-write replacement is based on generic product slots, not KLC-only materialization identity.
- Publication rejects snapshots containing a retained product whose exact dependency is absent.
- Published derived reads use explicit stored database + manifest artifacts and do not depend on producer-local filenames or adjacency.

### Prepared Knowledge Runtime 0.1.0.post8

- Added exact native reader for published `java-type-structure-evidence/v1`.
- Added explicit `database + manifest` open path for relocated published DuckDB products.
- Declared manifest capabilities and structurally available read capabilities are additive; physical filename/location is not used as semantic identity.

### AISL Contract 0.3.0b5

- `KnowledgeProduct` / candidate contracts distinguish `origin_kind = observed | derived`.
- Product origin is separate from item-level semantic confidence/resolution.
- Product registry is a projection of multiple authoritative owner catalogs, currently Core evidence catalog + KLC materialization catalog.
- Exact product dependency invariants cover observed→derived chains.
- Current-framework producer validation projects both `evidence_artifacts[]` and `knowledge_artifacts[]` from `knowledge_execution_result/v2`.

## Unchanged semantic producers

- evidence-common 0.23.2
- code-analyzer-core 0.44.23a5
- static-analysis-runner 0.10.25
- knowledge-layer-core 0.61.0a32
- knowledge-integration 0.1.15
- knowledge-control-plane 1.2.0a23

No Core analyzer, KLC materializer or Runner execution semantics were changed.

## No new architecture duplicates

The pilot does not add a second catalog, Knowledge Layer, publisher, dual-read, dual-write, graph/EAV representation or Core-copy database.
