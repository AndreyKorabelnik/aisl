# AISL SDK Rename — Change Report

Date: 2026-08-19

## Scope

Clean-break consumer-side naming refactor only. Top-level delivery boundaries remain:

- aisl-producer
- aisl-server
- aisl-client
- aisl-ui

Internal libraries are now named:

- `aisl-sdk` — Python SDK, import `aisl_sdk`
- `aisl-sdk-typescript` — TypeScript SDK
- `aisl-cli` — CLI over `aisl-sdk`
- `aisl-reporting` — reporting consumer over `aisl-sdk`

`AislClient` remains the public client class.

## Removed

No compatibility package, alias, re-export, dual dependency, or legacy import is retained. The old Python distribution/package `aisl-client` / `aisl_client` and TypeScript package `aisl-client-typescript` are absent from active code and package directories.

## Changed modules

- AISL Consumer Suite 0.7.0
- aisl-sdk 0.3.0
- aisl-sdk-typescript 0.3.0
- aisl-cli 0.2.0
- aisl-reporting 0.4.1
- aisl-agent-runtime 0.2.1
- aisl-workbench 0.4.1

Producer, Server, Knowledge API contracts, Integration Profile, publication bundle v2, KLC knowledge semantics and revision semantics are unchanged.
