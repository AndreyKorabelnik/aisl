# AISL Publication Bundle Boundary — Acceptance

Date: 2026-08-18

## Acceptance result

PASS for the changed Producer -> Server boundary.

A cross-module test used the real KCP bundle builder and the real Knowledge API bundle importer. Producer output root was deliberately not present in Server `allowed_roots`.

Observed result:

- bundle schema: `aisl_publication_bundle/v1`
- bundle SHA-256: `5e8f6a737365d3928925a693e17458a39a378ae9674ac2aae976ce046479a921`
- bundle members: 3
- import status: `published`
- system: `ucp-data-model` (synthetic acceptance fixture identity)
- created revision: `rev-600e39144c1bed3a008d9a85`
- revision active: true
- CAS blobs ingested: 3
- Producer root allowed by Server: false

The acceptance proves the new contract does not require shared filesystem access to Producer outputs.

## User UCP run evidence

The user's real UCP run on 2026-08-18 completed all three requested materializations before the old publication boundary failed:

- `code-declared-data-model`
- `model-storage-semantics`
- `logical-storage-mapping`

The old run failed only when publishing Producer-local artifacts outside configured Server roots. Those exact UCP artifacts exist on the user's machine and were not available in this build environment, so the real UCP production was not rerun here.
