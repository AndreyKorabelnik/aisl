# AISL Storage Mobility — Change Report

Date: 2026-08-16

## Knowledge API 0.33.0

- Published Artifact Store members now use backend-root-independent `aisl+sha256://<digest>` locators.
- Added deterministic content-locator parsing and filesystem blob resolution through current `artifact_store_path`.
- Artifact import/finalize remains content-addressed and immutable.
- Producer publication inputs continue to use explicit validated `file://` paths before import.
- Published reads resolve logical content identity against the currently configured Artifact Store root.
- Locator SHA/content SHA mismatch is an explicit error.
- Moving the filesystem Artifact Store does not require a new KnowledgeRevision, new KnowledgeProduct or catalog row rewrite.

## AISL Contract 0.3.0b7

- Formalizes backend/root location independence for AISL-managed content-addressed storage.
- Moving immutable bytes between storage roots/backends must not create a new semantic product/revision when content identity and membership are unchanged.

## Unchanged runtime modules

- evidence-common 0.23.2
- code-analyzer-core 0.44.23a5
- static-analysis-runner 0.10.25
- prepared-knowledge-runtime 0.1.0.post9
- knowledge-layer-core 0.61.0a32
- knowledge-integration 0.1.15
- knowledge-reporting 0.18.1
- knowledge-control-plane 1.2.0a23

No Core/KLC semantic, Runner/KCP orchestration, consumer query schema or SQLite normalization changes were required.
