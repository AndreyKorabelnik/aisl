# UCP 91 external blind one-shot acceptance

Date: 2026-08-15  
Status: **UCP_91_EXTERNAL_BLIND_ONE_SHOT_READY**

## Goal

Reduce the independent 91-attribute acceptance run to one Gold-isolated command without moving agent reasoning into AISL.

The consumer-side wrapper owns only operational composition:

```text
prepared published knowledge
→ read-only Knowledge API
→ external OpenAI-compatible agent
→ 91-item structural validation
→ pre-Gold SHA-256 freeze
→ portable frozen-result bundle
```

AISL still owns deterministic published knowledge and exact/read projections only. The wrapper remains a validation/consumer artifact, not an AISL runtime component.

## Observed acceptance

- `scripts/run_blind_once.py` compiles and exposes explicit endpoint/model/runtime options.
- It accepts both `LLM_BASE_URL`/`LLM_MODEL` and the existing project/KCP-style `LLM_ENDPOINT`/`LLM_DEFAULT_MODEL` environment names.
- Authentication remains environment-owned: bearer API key or mTLS certificate/key with optional CA. Secret values are not copied into run metadata.
- Missing endpoint/model fails before publication/run-directory creation.
- Full orchestration was executed against a local OpenAI-compatible mock endpoint.
- Official prepared revision publication returned the expected deterministic revision `rev-828b3d5897d6bf2f09d6b0c4`.
- Knowledge API started and became reachable.
- Ten batches covered all 91 inputs exactly once.
- The mock deliberately returned 91 `unresolved` rows; this was accepted structurally and is **not** an agent-quality result.
- `freeze_result.py` produced a pre-Gold receipt with `gold_accessed_by_validator=false`.
- Frozen mock result SHA-256: `7ac0dfeb466596d836fd23e656678dd5486946ddc6e55f31dfaec41ef62d6cc6`.
- A portable frozen-result ZIP was created.
- Knowledge API shutdown completed and the test port was closed after the run.

## External-model status

The current execution environment contains no configured external LLM endpoint/model/certificates and no independent LLM connector. Therefore the real DeepSeek 91-item quality run is still **unresolved**. The same chat/model is not substituted because Manual Gold was already inspected in this conversation.

Historical project configuration establishes that the workplace route is an OpenAI-compatible proxy with certificate/key and has used model `DeepSeek-v4-pro`; the concrete endpoint/credential files are not present in this execution environment.

## Acceptance boundary

This block proves **operational readiness**, not recall/precision. The next valid quality artifact is one frozen result produced by an independent external model with no Gold access.
