# AISL Reachability-Based GC — Change Report

Date: 2026-08-16

## Changed modules

### Knowledge API 0.34.0

- added Artifact Store plan/sweep API;
- added deterministic reachability derivation from all retained revisions;
- added canonical CAS inventory and safe blob deletion;
- added crash-staging cleanup and unmanaged-entry diagnostics;
- added missing-referenced diagnostics;
- added cross-process POSIX lifecycle lock shared by publication finalization and destructive GC;
- system deletion remains logical only; physical reclamation is deferred to GC.

### AISL Contract 0.3.0b8

- added ADR-012 reachability-based Artifact Store GC;
- formalized retained revision roots, external retention policy, grace/staging safety and no-refcount invariant.

## Explicitly unchanged

Core, Runner, KLC, KCP, Prepared Runtime, Knowledge Integration and Knowledge Reporting runtime semantics are unchanged.

## Not added

- refcount table;
- second artifact registry;
- per-revision delete/retention policy;
- synchronous CAS deletion on system delete;
- SQLite normalization;
- GC-driven semantic inference.
