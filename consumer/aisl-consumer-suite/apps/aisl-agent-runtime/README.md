# aisl-agent-runtime

External consumer-owned agent runtime for AISL.

Boundary:

```
External LLM / provider
        ↓
aisl-agent-runtime
        ↓
llm_integration_profile/v1 + Knowledge API
```

The runtime owns dialogue state, provider calls and the tool loop. It does **not** own Knowledge semantics, retrieval policy or grounding rules. Those arrive from the revision-pinned Integration Profile produced by `knowledge-integration` and served by Knowledge API.

It never imports Core, Runner, KLC or KCP and never reads AISL storage directly.

## Service

```bash
export AISL_API_URL=http://127.0.0.1:8080
export LLM_BASE_URL=https://your-openai-compatible-endpoint
export LLM_MODEL=your-model
# optional: LLM_API_KEY / LLM_CERT_FILE / LLM_KEY_FILE / LLM_CA_FILE

aisl-agent-runtime serve --port 18220
```

HTTP flow:

1. `POST /api/agent/v1/sessions` with pinned `system_id`, `revision_id`, `profile_id`.
2. `POST /api/agent/v1/sessions/{session_id}/messages` with `question`.
3. The response includes the final answer and full per-round tool trace.

`AISL_AGENT_PROVIDER=fixture` exists only for deterministic acceptance and is not an LLM-quality test.
