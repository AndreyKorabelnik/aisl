# Legacy Cleanup Block 6 — KLC consumer retirement audit

## Observed facts before the cut

1. Core still produces `code_conceptual_model/v2` in two legacy repository data-model profiles.
2. Current KLC typed materializations (`code-declared-data-model`, `logical-physical-mapping`, `effective-data-model`, and related products) do not accept or require that umbrella artifact.
3. A separate older KLC repository/workspace build path still resolved `compact/code_conceptual_model.json`, its manifest, and detail JSONL files.
4. Current Runner, Knowledge API, Assistant, Reporting, and UI do not invoke `build_workspace_data_model`, `build_knowledge_layer`, `RepositoryEvidence`, or `KnowledgeLayerBuildRequest`.
5. The old KLC build path was therefore an active source-level consumer implementation without a current product-runtime caller.
6. The KLC read/query layer is still reused by `DataModelQueryService` and Reference Data enrichment and was not removed in this block.

## Conclusion

The old repository/workspace production bridge is confirmed legacy and can be removed before retiring its Core umbrella producer. This ordering avoids creating a compatibility adapter and leaves the current typed materialization path untouched.

## Removed

- `api.py` legacy materializer protocol;
- `scope_builder.py`;
- `scope_materialization.py`;
- `repository.py`;
- `repository_materialization.py`;
- `workspace_data_model.py`;
- `workspace_validation.py`;
- `workspace_selection.py`;
- old build-request/repository-evidence contracts and IO;
- conceptual-model-specific loaders that existed only for the removed bridge;
- obsolete tests whose subject was the retired producer path.

## Preserved deliberately

- current materialization registry and all typed materializers;
- `KnowledgeLayerManifest`, used by current materializers;
- generic JSON/manifest IO;
- read/query services;
- uncertainty, gaps, diagnostics, and normal technical fallback behavior;
- historical validation/release artifacts as provenance.

## Next proof

After this cut, current KLC source has zero `code_conceptual_model` references. The remaining live producer is Core itself. Block 7 should prove no current consumer remains, then remove `code_conceptual_model_build`, its two profile bindings, artifact publication, Runner stage taxonomy entry, and current docs/tests.
