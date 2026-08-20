# UI2 v1.1.0 — optimized agent runtime

## Scope

The visual interface and analysis/report workflow are unchanged. The `/ask` backend was rewritten to align with the current analysis bundle and Evidence Access API architecture.

## Main changes

- compact canonical agent prompt instead of concatenating nine full artifacts;
- in-process prompt cache invalidated by artifact fingerprint;
- bounded real conversation history;
- structured `agent_requests` contract;
- Evidence Access API execution through `code_evidence.access`;
- strict allowlist and argument validation from `enabled_evidence_tools.json`;
- no shell command execution from LLM output;
- limits for iterations, total requests, output size, history and wall time;
- lower reasoning effort for simple first questions;
- bounded tool results and duplicate request detection;
- diagnostics endpoint and per-step timing metrics;
- old Git pin for code-analyzer-core removed from UI requirements;
- npm token removed from `.npmrc` and replaced with `${NPM_TOKEN}`.

## Compatibility

Required project packages:

- code-analyzer-core 0.23.68 or newer;
- evidence-llm-pipeline 0.23.36 or newer;
- llm-prompts 0.25.8 or newer.

## Validation

- Python compile check: passed;
- backend unit/integration tests: 10 passed;
- real `code_evidence.access` field-flow smoke test: passed;
- FastAPI `/ask` integration test: passed;
- frontend source was not changed; dependency installation/build could not be repeated in the isolated environment because the configured internal npm registry was unavailable.
