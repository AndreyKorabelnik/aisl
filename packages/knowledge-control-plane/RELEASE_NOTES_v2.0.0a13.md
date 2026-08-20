# analysis-ui 2.0.0a13 — production same-origin Knowledge API proxy

- Adds transparent `/api/knowledge/v1/**` reverse proxy to the configured canonical `knowledge-api`.
- Preserves upstream status, body, JSON/Markdown content types, content disposition and end-to-end headers.
- Forwards request methods, query parameters, body and authorization headers.
- Keeps proxy paths out of the orchestration OpenAPI to avoid duplicating the Knowledge API contract.
- Adds explicit 502/504 transport errors for unavailable or timed-out upstreams.
- Adds `KNOWLEDGE_API_PROXY_ENABLED` and an explicit `httpx` runtime dependency.
- Frontend production and development now use the same relative Knowledge API base path.
