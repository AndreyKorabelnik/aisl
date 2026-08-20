# code-analyzer-core 0.44.19 — Legacy Cleanup Block 7

- Removed the obsolete `code_conceptual_model_build` stage and `code_conceptual_model/v2` prepared-artifact producer.
- Removed the umbrella artifact implementation and producer-specific tests.
- Removed the stage from repository data-model profiles; their primary interface is now `evidence_access_api`.
- Removed runtime dispatch/status/coverage/manifest publication for the umbrella stage.
- Updated the Core analysis catalog and target assessment; `knowledge_materialization_inside_core_count` is now 0.
- Added negative contracts preventing the removed umbrella stage/artifact from returning.
- No umbrella-to-typed compatibility adapter was introduced.
