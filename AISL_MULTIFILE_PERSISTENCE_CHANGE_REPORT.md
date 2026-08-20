# AISL Multi-file Published Persistence — Change Report

Date: 2026-08-16

## Knowledge API 0.32.0

- Generalized published physical representation to `physical_artifacts[]` with unique explicit roles.
- Removed the old internal alternatives `database`, `manifest`, `observed_artifact`; no dual-read/compatibility path was added.
- Existing derived products use `database` + `manifest` as physical **roles**, not product model fields.
- Existing Java observed single-file product uses role `descriptor`.
- Added real multi-file observed publication for Core `sql-analysis/v1`.
- Validates SQL descriptor, canonical manifest, coverage and every manifest-declared fact shard before import/publication.
- Imports/finalizes every physical member into the existing AISL content-addressed Artifact Store before revision visibility.
- Observed `partial` products are publishable with unchanged coverage/diagnostics; failed/incomplete products are not.
- `knowledge_execution_result/v2` validation no longer assumes a completed execution must contain a KLC knowledge artifact; observed-only, derived-only and mixed publication are valid when at least one publishable product is actually projected.
- Universal observed SQL read resolves exact CAS members by roles and does not rediscover producer-local sibling paths.

## Prepared Knowledge Runtime 0.1.0.post9

- Added native exact reader for published `sql-analysis/v1` packages.
- Reader receives explicit published manifest, coverage and `fact:<type>` members.
- Exact reads do not depend on producer workspace adjacency/layout.

## Knowledge Reporting 0.18.1

- Derived database selection now resolves the `database` member from `physical_artifacts[]`.
- Duplicate role is an explicit error.

## AISL Contract 0.3.0b6

- `ArtifactDescriptor.role` is required.
- Physical artifact roles must be unique within one `KnowledgeProduct`.
- Canon/docs now explicitly permit one or many physical members per semantic product.
- Physical location is not semantic product identity.
- Partial observed publication semantics are documented without status promotion.

## Unchanged semantic producers/orchestration

- evidence-common 0.23.2
- code-analyzer-core 0.44.23a5
- static-analysis-runner 0.10.25
- knowledge-layer-core 0.61.0a32
- knowledge-integration 0.1.15
- knowledge-control-plane 1.2.0a23

No Core SQL analyzer, Runner orchestration or KLC materializer semantics were changed.
