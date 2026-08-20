# AISL Consumer Suite Architecture

## One public contract, multiple consumers

Knowledge API is the data/read contract. `llm_integration_profile/v1` is the LLM/tool/grounding contract. SDKs are transport convenience only.

### Python SDK
Used by `aisl-reporting` and `aisl-agent-runtime`.

### TypeScript SDK
Used by `aisl-workbench`.

### Agent runtime
Owns dialogue state, provider calls and tool-loop orchestration. It delegates pinned Integration Profile retrieval and selected-tool `api_binding` execution to the public Python SDK.

### Reporting
Owns ReportRun / rendering lifecycle and never republishes reports into AISL revisions.

### Workbench
Owns browser UX. Its Knowledge API proxy is read-only. Reports and Chat call separate consumer services.
