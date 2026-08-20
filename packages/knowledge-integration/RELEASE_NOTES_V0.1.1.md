# knowledge-integration 0.1.1

- Added deterministic `tool + pinned scope + arguments -> Knowledge API HTTP request` materialization from the canonical public `api_binding`.
- Added response-schema metadata to HTTP bindings.
- Made the integration prompt consumer-neutral so the same renderer is usable by external consumers and Knowledge Assistant.
- No agent loop, LLM provider, source analysis, or knowledge production was added.
