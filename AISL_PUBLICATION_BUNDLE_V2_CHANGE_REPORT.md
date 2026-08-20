# AISL Publication Bundle v2 — Change Report

Date: 2026-08-18

## Problem
`aisl_publication_bundle/v1` copied only the Knowledge Execution tree. Real executions may reference publishable Core evidence packages stored under Producer runtime `producer-artifacts`, outside that tree. Server import then required access to Producer-local paths, contradicting the independent Producer/Server boundary.

## Change
- Publication bundle schema advanced to `aisl_publication_bundle/v2`.
- Producer bundles the execution tree plus bounded external physical artifact packages referenced by `evidence_artifacts` / `knowledge_artifacts`.
- Bundle manifest carries explicit `source_mappings` from Producer provenance roots to verified bundle payload prefixes.
- Server import relocates physical artifact reads through those mappings into Server-owned staging.
- Server `allowed_roots` during import are staging-only; Producer filesystem access is not required.
- Existing Server publication engine remains the single owner of validation, CAS ingestion and immutable revision publication.
- `v1` is not supported by the new importer; rebuild the bundle with the updated Producer. No compatibility adapter or dual path was added.

## Versions
- knowledge-control-plane: 1.2.0a34
- knowledge-api: 0.40.2

Core, Runner and KLC semantics are unchanged.
