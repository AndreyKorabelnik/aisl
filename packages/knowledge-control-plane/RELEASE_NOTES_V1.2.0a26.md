# Knowledge Control Plane 1.2.0a26

## Block D — Concept Detector Registry contract repin

- Regenerates the pinned `knowledge_materialization_catalog/v3` from canonical KLC `0.61.0a35`.
- Regenerates the dependent Runner `knowledge_catalog/v2` from canonical builders.
- Keeps the Core evidence catalog byte-identical because Core contracts did not change.
- Regenerates `knowledge_control_plane_runtime_contract_bundle/v2` checksums, fingerprints, and framework baseline.
- No execution-planning semantics change is introduced by this KCP release; this is a required contract-bundle repin for the KLC ownership refactor.
