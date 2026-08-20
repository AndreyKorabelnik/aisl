# AISL producer handoff v2 — change report

Date: 2026-08-15

## Purpose

Make `knowledge_execution_result` self-contained for AISL publication provenance when a materialization consumes a KnowledgeProduct from an already published revision.

## Contract replacement

`knowledge_execution_result/v1` is replaced by `knowledge_execution_result/v2` in the active Runner → Knowledge API → Knowledge Control Plane path. No v1 adapter, dual-read or compatibility alias is retained.

## New field

`external_knowledge_artifacts[]` contains only prior-revision KnowledgeProducts actually referenced by `materialization_executions[].input_knowledge_artifact_ids` and not produced by the current execution.

Each descriptor contains immutable dependency identity:
- artifact/product id;
- model kind and schema version;
- source materialization id;
- content fingerprint;
- source system/scope id;
- source revision id;
- published capabilities.

Machine-local artifact locations are intentionally not copied into this dependency registry.

## Invariants

Every materialization knowledge input id resolves to exactly one of:
1. current execution `knowledge_artifacts[]`, or
2. prior-revision `external_knowledge_artifacts[]`.

Unused external descriptors, unresolved input ids, duplicate ids, overlap between produced/external registries, and incomplete prior-revision identity are rejected explicitly.

## Ownership

- Runner owns the self-contained producer handoff.
- Knowledge API validates v2 and publishes only current execution outputs; external descriptors are provenance/dependency inputs, not republished artifacts.
- KCP transfers and labels the v2 execution result.
- Core, KLC and Prepared Knowledge schemas are unchanged.

## Runtime contract bundle

KCP's pinned knowledge-planning bundle was intentionally not modified. Knowledge planning/catalog semantics did not change. Regeneration from the official Core builder could not be executed in this environment because the Core builder import requires unavailable `tree_sitter`; fingerprints were not edited manually.
