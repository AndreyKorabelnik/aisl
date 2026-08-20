# Knowledge Control Plane 1.0.0a1

Breaking product rename from `analysis-ui` 2.0.0a94 to `knowledge-control-plane` 1.0.0a1.

This step changes naming only; production semantics, Runner/Core/KLC ownership, Knowledge API publication semantics and job execution behavior are intentionally unchanged.

## Active runtime rename

- distribution: `knowledge-control-plane`
- Python package: `knowledge_control_plane`
- CLI: `knowledge-control-plane`
- environment prefix: `KNOWLEDGE_CONTROL_PLANE_*`
- runtime database/log/marker names use `knowledge-control-plane`
- OpenAPI product extension uses `x-knowledge-control-plane-schema-version`
- runtime contract bundle schema owner name is `knowledge_control_plane_runtime_contract_bundle/v2`
- publication metadata producer/managed-by uses `knowledge-control-plane`

No compatibility alias, re-export, dual CLI or old environment-variable fallback is retained.
Historical release/test documents are preserved as provenance and may still mention Analysis UI.
