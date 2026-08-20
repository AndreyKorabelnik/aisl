# AISL Platform

Canonical source repository for the **Automatic Code Analysis / AISL** project.

## Architecture

`Sources → Core → Runner → KLC → Prepared Knowledge/AISL → Knowledge API → Consumers`

Ownership:

- **Core** owns observed evidence.
- **KLC** combines evidence and builds useful/derived knowledge.
- **AISL / Server** owns the durable lifecycle of published immutable products and revisions.
- **Knowledge API** is a thin read boundary, not a second Knowledge Layer.
- A revision's **Integration Profile** is the source of truth for AI consumers.

## Delivery boundaries

Exactly four top-level deliveries are supported:

- `aisl-producer`
- `aisl-server`
- `aisl-client`
- `aisl-ui`

Current consumer boundary:

- `aisl-client` delivery → `aisl-sdk`, `aisl-sdk-typescript`, `aisl-cli`, `aisl-reporting`
- `aisl-ui` → `aisl-agent-runtime`, `aisl-workbench`

Python public SDK entry point:

```python
from aisl_sdk import AislClient
```

No compatibility aliases for the former `aisl-client` / `aisl_client` Python distribution/import are retained.

## Canonical state after Git migration

- **Source canonical:** the exact Git commit (`git rev-parse HEAD`).
- **Release canonical:** an immutable Git tag + GitHub Release containing the four clean deliveries and `SHA256SUMS`.
- ZIP/recovery archives are transfer/emergency exports only; they are not the canonical source state.

See `RECOVERY/` for current handover, acceptance status, parked scope, and the Git workflow.
