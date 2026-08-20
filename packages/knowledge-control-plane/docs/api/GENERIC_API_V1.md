# Knowledge Control Plane orchestration API v1

The API owns orchestration resources only. Its executable contract is `generic-v1.openapi.json`.

Main resources:

```text
/version
/capabilities
/diagnostics
/configuration
/repositories
/workspaces
/knowledge-profiles
/jobs
/artifacts
```

Only `knowledge_execution` jobs are accepted. Knowledge semantics and immutable revisions are owned by Knowledge API under `/api/knowledge/v1/**`; that path is proxied by Knowledge Control Plane when configured and is deliberately absent from this OpenAPI document.

Public request models are strict (`extra=forbid`). Removed Task, Suite, Core Profile and single-Knowledge-DB payloads are rejected rather than adapted.
