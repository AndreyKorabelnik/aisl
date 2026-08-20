# AISL Publication Bundle Boundary — Change Report

Date: 2026-08-18

## Decision

AISL Producer owns knowledge production and creation of a self-contained publication bundle.
AISL Server owns validation, artifact ingestion, immutable revision creation, activation, and publication lifecycle.
Producer no longer publishes Knowledge API revisions and no longer sends Producer-local `file://` artifact locations to Server.

## Producer changes

- `knowledge-control-plane` version: `1.2.0a33`.
- Final KCP pipeline stage changed from `publication` to `bundle`.
- Added canonical bundle format `aisl_publication_bundle/v1`.
- Bundle contains the unchanged execution result tree, a manifest, per-member SHA-256/size, producer provenance, system identity, publication defaults, and a stable bundle fingerprint.
- Removed Producer publication service/path and publication timeout setting.
- Successful Producer job records publication bundle path/SHA, not a Server revision ID.
- Knowledge API client retained only for optional read access to already published revisions used by composition scenarios.

## Server changes

- `knowledge-api` version: `0.40.0`.
- Added `knowledge-api import --bundle ...`.
- Server validates bundle schema/fingerprint/member set/path safety/member SHA and execution-result SHA.
- Server relocates Producer-local provenance paths only for validation/read resolution; knowledge bytes are not rewritten.
- Existing `KnowledgeDomainService.publish_revision()` remains the single canonical publisher.
- Published artifacts are ingested into Server-owned SHA CAS and catalog references become `aisl+sha256://...`.
- Import does not require Producer output paths to be included in Server `allowed_roots` and does not require a shared filesystem.

## Removed contract

The replaced Producer -> Server contract based on Producer-local `file://` artifact paths was removed. No dual publication path or compatibility adapter was added.

## Unchanged

Core evidence semantics, Runner analysis/materialization semantics, KLC knowledge semantics, Client, UI, and Integration Profile semantics were not changed by this block.
