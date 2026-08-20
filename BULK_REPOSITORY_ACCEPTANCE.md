# Acceptance — Bulk Repository Processing

Date: 2026-08-14

## Synthetic lifecycle acceptance — PASS

Three local git repositories were processed through the batch lifecycle with a controlled test pipeline.

Observed:
- only the current repository checkout existed during processing;
- maximum concurrent checkout count = 1;
- each checkout was removed after processing;
- a failure in repository 1 did not block repository 2;
- workspace-scoped profile was rejected before source selection/download;
- no checkout remained after batch completion.

## Real Core → KLC smoke — PASS

Two local git repositories were processed through the real Core `0.44.23a5` → Runner → KLC Repository Inventory pipeline using the final pinned catalogs.

Observed result: 2/2 completed, 0 failed, `persistent_repository_checkout_count=0`, `temporary_checkout_removed=true` for both repositories.

## Representative uploaded-application acceptance — PASS

Two user-provided application archives were copied to acceptance fixtures, initialized as local git repositories, and processed by the same real Repository Inventory batch route:

- `gw-sberid-update-phone-flags(1).zip`: 182 extracted source/content files in the fixture; completed.
- `gateway-sberid-userinfo-by-ucpid(1).zip`: 302 extracted source/content files in the fixture; completed.

Observed result: 2/2 completed, one knowledge artifact per repository, no residual `.git` checkout or `repository-slot` below batch work/output after completion.

The original uploaded archives were not modified.

## Bitbucket Data Center live acceptance — NOT RUN

No live Bitbucket project URL/credentials were supplied in this block. Existing Bitbucket discovery/auth/pagination code is reused and its generic selection path is covered by targeted tests, but a live server/project execution is not claimed.

## Provenance note

Persistent generic execution manifests retain the historical temporary source path as execution provenance. That path is no longer present after cleanup. Durable batch identity is separately recorded as repository URL + requested ref + resolved commit. No source checkout is persisted.
