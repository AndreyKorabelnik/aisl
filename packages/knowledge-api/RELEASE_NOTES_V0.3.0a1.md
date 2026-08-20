# knowledge-api 0.3.0a1 — canonical v1 contract checkpoint

This design checkpoint adds the executable producer-neutral contract planned in
ADR-0012 without yet replacing the existing `0.2.2` runtime implementation.

Added:

- `/api/knowledge/v1` contract with systems and immutable revisions;
- content-addressed publication request models;
- revision-aware data-model table catalog and detail;
- revision-aware prepared report discovery and Markdown content;
- service health, version and capabilities;
- deterministic OpenAPI in `schemas/knowledge-v1.openapi.json`;
- strict Pydantic validation and contract tests.

Explicitly excluded:

- orchestration jobs and stages;
- UI state;
- LLM execution;
- arbitrary SQL;
- producer-specific `job_id` semantics.

The production implementation is iteration 13.
