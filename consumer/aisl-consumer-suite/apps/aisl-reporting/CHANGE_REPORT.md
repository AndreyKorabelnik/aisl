# Change Report — aisl-reporting 0.4.3

## Scope

HTTP request parity and diagnostics for OpenAI-compatible LLM rendering. No AISL knowledge/API/producer/server semantics changed.

## Changes

- Explicit `Accept: application/json` and `Content-Type: application/json` request headers.
- Redirect following enabled to match the supported `curl -L` operational path.
- Non-2xx diagnostics now preserve final request URL, HTTP version, request payload byte size, `x-request-id` when present, and up to 4000 chars of response body.
- mTLS/TLS/HTTP2 behavior from 0.4.2 retained unchanged.
- Version metadata aligned (`VERSION` and `pyproject.toml` both 0.4.3).

## Evidence boundary

The real corporate endpoint is not reachable from this runtime. The prior user run proves TLS/mTLS/HTTP2 reaches the service and receives HTTP 404; 0.4.3 improves parity/diagnostics but real endpoint acceptance remains pending the user's next run.
