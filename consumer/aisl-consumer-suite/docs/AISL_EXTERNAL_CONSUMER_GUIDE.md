# AISL External Consumer Guide

## Supported public boundaries

1. Raw Knowledge API HTTP — language-neutral source-of-truth.
2. `aisl-sdk` for Python — typed/convenient revision-pinned access.
3. `aisl-sdk-typescript` for JavaScript/TypeScript — OpenAPI-anchored revision-pinned access.
4. Revision-specific Integration Profile — machine-readable capabilities, tools, retrieval/grounding rules and API bindings for an external LLM/agent runtime.

External consumers do not need Core, Runner, KLC, KCP, source repositories, DuckDB internals or AISL filesystem access.

## Revision discipline

Resolve active only when explicitly desired, then pin the concrete immutable `revision_id`. Do not silently follow `latest` during one workflow.

## Python

```python
from aisl_sdk import AislClient
with AislClient("http://knowledge-api:8080") as client:
    rev = client.active_revision("ucp-data-model")
    results = rev.search_declared_data_objects(search="гражданство", include_fields=True)
```

## TypeScript

```ts
import { AislClient } from "aisl-sdk-typescript";
const client = new AislClient("http://knowledge-api:8080");
const rev = await client.activeRevision("ucp-data-model");
const products = await rev.listProducts();
```

## Authentication and TLS

Python supports custom headers, CA verification and client certificates via `AislClient` options. TypeScript supports headers and a custom `fetch` implementation; enterprise TLS/mTLS can be supplied by the host runtime or gateway. SDKs do not own identity policy.

## LLM / Agent

Load the revision-pinned Integration Profile from Knowledge API through the SDK and expose only tools allowed by that profile. The external agent runtime owns dialogue and tool selection; AISL SDK is the transport/integration executor. Preserve `ambiguous`, `not_observed`, `not_available`, provenance and diagnostics. Never manufacture physical JOINs or business meaning absent from published knowledge.

## Failure interpretation

- HTTP/transport failure: consumer connectivity/configuration issue.
- API 4xx/5xx: explicit Knowledge API error; do not silently fall back.
- missing capability/product: selected revision does not publish required knowledge.
- ambiguous/unresolved/gap: semantic status from published knowledge, not an SDK error.
