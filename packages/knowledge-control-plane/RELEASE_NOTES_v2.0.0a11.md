# analysis-ui 2.0.0a11 — canonical Knowledge API publication

Iteration 14 moves the `publication` pipeline stage from the transitional local
system catalog to the external canonical `knowledge-api` HTTP contract.

## Pipeline behavior

The completed pipeline now calls:

```text
POST /api/knowledge/v1/systems
POST /api/knowledge/v1/systems/{system_id}/revisions
```

The revision payload contains producer-neutral provenance, repository revisions,
file URIs, SHA-256 values, media types and byte sizes. `analysis-ui` imports no
`knowledge-api` implementation modules.

If the upstream is unavailable, only `publication` fails. Static analysis,
Knowledge Layer and report artifacts remain registered, and retry with
`from_stage=publication` reuses them.

## Configuration

```bash
KNOWLEDGE_API_BASE_URL=http://127.0.0.1:8080/api/knowledge/v1
KNOWLEDGE_API_TIMEOUT_SECONDS=30
```

Successful jobs expose `JobDetails.publication` with `system_id`, `revision_id`
and the canonical Knowledge API URL.

The old local system/data-model/report routes remain transitional until the
frontend migration and duplicate-code removal iterations.
