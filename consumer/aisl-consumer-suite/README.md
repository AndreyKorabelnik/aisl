# AISL Consumer Suite 0.7.2

Workspace aggregation only; not a new runtime layer. Modules remain independently releasable.

- `packages/aisl-sdk` 0.3.0 — public Python SDK
- `packages/aisl-sdk-typescript` 0.3.0 — public TypeScript SDK
- `apps/aisl-reporting` 0.4.3
- `apps/aisl-agent-runtime` 0.2.1 — internal runtime of the `aisl-ui` delivery
- `apps/aisl-workbench` 0.4.1
- `tools/aisl-cli` 0.2.0 — human/operator CLI over `aisl-sdk`

Top-level delivery boundaries remain `aisl-producer`, `aisl-server`, `aisl-client`, and `aisl-ui`. The name `aisl-client` denotes the delivery, not a Python/TypeScript SDK distribution.
