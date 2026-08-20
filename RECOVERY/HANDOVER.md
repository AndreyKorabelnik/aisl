# Handover — GitHub/Codex migration

Date: 2026-08-19

## Goal

Move AISL development from chat/ZIP-centric recovery to a normal Git workflow:

`GitHub repository → Git commit SHA → Codex edit/test/build/git → push/PR`

ChatGPT remains the architecture, review, coordination, and task-definition layer.

## Architectural guardrails

Canonical pipeline:

`Sources → Core → Runner → KLC → Prepared Knowledge/AISL → Knowledge API → Consumers`

Ownership:

- Core owns observed evidence.
- KLC owns derived/useful knowledge semantics.
- AISL/Server owns durable lifecycle of published immutable products and revisions.
- Knowledge API is a thin read boundary.
- Integration Profile for the pinned revision is the source of truth for AI consumers.

Top-level deliveries remain exactly `aisl-producer`, `aisl-server`, `aisl-client`, `aisl-ui`.

Do not introduce new framework mechanisms as part of Git migration.

## Pre-Git source provenance

Bootstrap input:

- archive: `auto-code-analysis-current-reporting-http-parity-2026-08-19.zip`
- SHA-256: `f6b39783676cea949e76d47d7982436deafded3ab644266d92c6b53b2603465f`

The archive SHA was independently rechecked during migration and matched exactly.

Migration-only hygiene changes in this bootstrap tree:

- removed generated `__pycache__` directories and `*.pyc` files;
- added repository-level `.gitignore` and `.gitattributes`;
- added `README.md` and canonical `RECOVERY/*` documents;
- moved legacy pre-Git top-level checksum manifests under `RECOVERY/PRE_GIT_CHECKSUMS/` so they are not mistaken for hashes of the Git canonical tree;
- updated top-level continuation pointers to the Git migration state.

No framework/runtime semantics were intentionally changed.

## Last confirmed functional state

Real UCP E2E passed over `ucp-api + ucp-tsa-v4` through producer → publication bundle v2 → AISL Server CAS/revision → SDK/CLI.

Pinned revision: `rev-8bed9d612efcdac7198640ad`.

For `Individual`:

- fields: 52
- relationships: 41
- strongly-supported joins: 5
- executable storage joins: 5
- ambiguous: 33
- unresolved/not-ready: 3

`birthCountry → Country` is strongly supported and `executable_storage_join` with `match_basis=exact_structural_expression_signature`.

`birthPlace → BirthPlace` remains ambiguous with two candidates; the framework does not silently select one.

Storage joins can be strongly supported/executable without PDM. This does not assert a physical SQL/PDM join.

## Latest development block before migration

`aisl-reporting 0.4.3` added curl-parity transport behavior and diagnostics for the corporate LLM endpoint:

- explicit `Accept: application/json` and `Content-Type: application/json`;
- redirects;
- final URL, HTTP version, request size, `x-request-id`, bounded response body on HTTP failures;
- existing mTLS/TLS/HTTP2 options: `--cert`, `--key`, `--ca`, `--insecure`, `--http2` and corresponding environment variables.

Observed external state: TLS/mTLS progressed successfully enough to receive HTTP 404; exact endpoint/path compatibility remains pending external acceptance.

## Continuation rule

Finish GitHub canonicalization first. Do not resume functional AISL work or operational observability automatically.
