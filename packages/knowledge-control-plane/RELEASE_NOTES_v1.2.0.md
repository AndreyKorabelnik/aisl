# UI2 v1.2.0 — pipeline-provided agent consumer views

## Main change

The agent runtime now prefers the official compact files produced by `evidence-llm-pipeline v0.23.37`:

- `agent_bootstrap.json` is the only dynamic bundle projection inserted into the model system prompt;
- `agent_runtime_manifest.json` is used only by backend code for repository routing, tool selection and validation.

The UI no longer needs to semantically compact nine internal bundle artifacts for newly generated analysis bundles.

## Prompt cache behavior

For current bundles, prompt invalidation depends only on:

- `agent_system_prompt.md`;
- `agent_bootstrap.json`;
- `agent_runtime_manifest.json`.

Changes in internal report or manifest files do not invalidate the agent prompt unless the pipeline regenerates a consumer view.

## Security and runtime controls

All v1.1.0 controls remain in place:

- no shell execution;
- structured `agent_requests` only;
- Evidence Access API execution;
- bounded history, iterations and tool outputs;
- exact tool-contract validation;
- diagnostics endpoint.

## Compatibility

- code-analyzer-core >= 0.23.68;
- evidence-llm-pipeline >= 0.23.37;
- llm-prompts >= 0.25.8.

## Validation

- pipeline tests: 160 passed;
- UI backend tests: 12 passed;
- consumer-view prompt fixture reduction: 76.5%.
