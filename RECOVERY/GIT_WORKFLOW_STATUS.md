# Git workflow status

Date: 2026-08-20
Status: `GIT_CANONICAL_ACTIVE`

## Repository

GitHub repository:

`https://github.com/AndreyKorabelnik/aisl`

Default branch:

`main`

## Canonical-state rule

The Git repository is the authoritative source-history and source-state store.

- Source canonical = exact Git commit SHA on `main` selected as the current canonical state.
- Release canonical = Git tag + GitHub Release containing the four clean deliveries and `SHA256SUMS`.
- Recovery ZIP is emergency export only and is not the normal continuation mechanism.
- Change-transfer files or ZIPs are transport artifacts only. They do not become canonical state.

## Bootstrap provenance

The repository was bootstrapped from the verified pre-Git source archive:

`auto-code-analysis-current-reporting-http-parity-2026-08-19.zip`

SHA-256:

`f6b39783676cea949e76d47d7982436deafded3ab644266d92c6b53b2603465f`

First published Git bootstrap commit observed externally:

`c0a0599395c76d224165d11a810403cf86d6922f`

This SHA is historical bootstrap provenance. The current Source canonical must always be taken from Git after subsequent commits; do not try to write a commit's own SHA into that same commit.

## Fixed delivery boundaries

- `aisl-producer`
- `aisl-server`
- `aisl-client`
- `aisl-ui`

No fifth top-level delivery is introduced by the GitHub migration.

## Development discipline

GitHub migration must not create new framework analysis/runtime mechanisms.

Functional development continues to follow the canonical architecture:

`Sources → Core → Runner → KLC → Prepared Knowledge/AISL → Knowledge API → Consumers`

The operational observability task remains parked until explicitly resumed.
