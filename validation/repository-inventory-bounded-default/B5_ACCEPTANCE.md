# Repository Inventory bounded-default acceptance — 2026-08-13

Status: **PASS for B.1–B.5 checkpoint**, with explicit deep-analysis gaps left `not_evaluated`.

## Default cost policy

- Required/FREE: `repository-structure-evidence/v1`.
- CHEAP and allowed `produce_if_missing`: `data-model-candidate-evidence/v1`, `interaction-boundary-evidence/v1`.
- DEEP/accumulative and `existing_only`: Java type/persistence, persistence-lineage, reference-data, SQL analysis, storage usage, system-description, value-flow, model-storage.
- Missing DEEP evidence does not trigger production and is exposed as `not_evaluated`.

## Producer timings

Representative fresh Core producer timings:

- gateway, 91 files: repository structure 0.013 s; data-model candidate 0.391 s; interaction boundary 0.621 s.
- UCP TSA v4, 487 analyzer-eligible files: data-model candidate 6.938 s; interaction boundary 6.935 s.
- AT900 client-profile, 1038 analyzer-eligible files: data-model candidate 7.130 s; interaction boundary 7.771 s.

All bounded runs completed inside the 45 s per-producer guard. No reference-data/value-flow/deep persistence pipeline was run.

## Passport results

- `gw-update-phone-flags`: 91 files; Maven/Docker/Helm/OpenAPI markers; data model `not_detected`; system interaction `strongly_supported`; 2 inbound / 0 outbound; Bitbucket URL carried from authoritative KCP repository metadata in the acceptance fixture.
- `ucp-tsa-v4`: 490 files; Java/Maven; data model `strongly_supported` score 80; system interaction `not_detected` with complete interaction evidence and zero boundaries.
- `at900-client-profile`: 1048 files; Java + 136 SQL files; Gradle/Docker; data model `probable` score 39; system interaction `strongly_supported`; 35 inbound / 6 outbound.
- SQL datamart: 355 files, 306 SQL files; deep concepts remain `not_evaluated` because SQL analysis is `existing_only` in default inventory.

## Evidence discipline

`not_detected` means no supported candidate was detected in **completed supplied evidence**. It is not an assertion that the concept is absent from the system.

`not_evaluated` means the relevant official evidence was not supplied/produced under the bounded default policy.

Peer system identity is not guessed from URLs/service aliases; unresolved peers remain null with `peer_resolution_status=unresolved`.

## Bitbucket URL

Repository URL is owned by the KCP repository registry (`RepositorySummary.location` for `source_kind=bitbucket`). It is forwarded as source metadata and consumed by Repository Inventory. `.git/config` is not parsed as a second source of truth.
