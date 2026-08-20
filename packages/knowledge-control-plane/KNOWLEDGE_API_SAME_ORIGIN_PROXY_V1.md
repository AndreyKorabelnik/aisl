# Knowledge API same-origin proxy v1

`analysis-ui` exposes a transparent browser transport at:

```text
/api/knowledge/v1/**
```

The upstream is configured with:

```bash
export KNOWLEDGE_API_BASE_URL=http://127.0.0.1:8080/api/knowledge/v1
export KNOWLEDGE_API_TIMEOUT_SECONDS=30
export KNOWLEDGE_API_PROXY_ENABLED=1
```

The proxy forwards HTTP method, query string, request body and end-to-end headers. It streams the upstream response and preserves status, body, content type, content disposition and other end-to-end response headers.

It does not:

- define knowledge-domain Pydantic models;
- read Knowledge Layer DuckDB;
- reinterpret JSON or Markdown;
- add proxied Knowledge API paths to the orchestration OpenAPI;
- follow upstream redirects.

Connection failure is reported as `502 knowledge_api_proxy_unavailable`. Timeout is reported as `504 knowledge_api_proxy_timeout`. Responses received from `knowledge-api`, including 4xx and 5xx payloads, pass through unchanged.

For direct browser-to-service deployment, disable the backend proxy and configure CORS on `knowledge-api`:

```bash
export KNOWLEDGE_API_PROXY_ENABLED=0
export VITE_KNOWLEDGE_API_BASE_URL=http://127.0.0.1:8080/api/knowledge/v1
```
