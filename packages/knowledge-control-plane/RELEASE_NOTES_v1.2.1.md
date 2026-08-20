# UI2 v1.2.1 — mandatory agent consumer views

## Changed

- Removed the legacy fallback that reconstructed an agent prompt from nine internal bundle artifacts.
- `agent_system_prompt.md`, `agent_bootstrap.json` and `agent_runtime_manifest.json` are now mandatory.
- Missing, empty, invalid or unsupported consumer views fail explicitly with `AgentBundleContractError`.
- `/ask` returns HTTP 409 for an incompatible analysis bundle and instructs the operator to regenerate it with `evidence-llm-pipeline v0.23.37+`.
- Prompt cache signatures depend only on the three mandatory consumer-view files.

## Why

The UI is no longer a second implementation of bundle compaction. The pipeline is the only component responsible for preparing the semantic agent bootstrap and runtime manifest. This removes silent behavior differences between old and new bundles.

## Required bundle contract

```text
agent_system_prompt.md
agent_bootstrap.json          format = agent_bootstrap
agent_runtime_manifest.json   format = agent_runtime_manifest
```

There is no backward-compatible fallback. Existing bundles must be regenerated before using the agent chat.
