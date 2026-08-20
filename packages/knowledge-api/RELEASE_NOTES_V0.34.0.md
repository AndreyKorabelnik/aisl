# Knowledge API 0.34.0

Date: 2026-08-16

## AISL reachability-based Artifact Store GC

- Added `POST /api/knowledge/v1/artifact-store/gc` with explicit `plan | sweep` modes.
- Reachability is derived from every retained Catalog revision, including active, superseded and inactive revisions.
- Reachable physical identities come only from typed revision-owned fields: execution result, optional report and KnowledgeProduct `physical_artifacts[]`.
- No refcount table, second registry, dual-write or SQLite normalization was introduced.
- Sweep requires explicit destructive confirmation and an operator-provided grace period.
- Canonical unreferenced CAS blobs and old crash-staging files are eligible; unknown Artifact Store entries remain untouched diagnostics.
- Missing referenced blobs are surfaced explicitly and are never guessed/repaired by GC.
- Publication finalization/catalog commit and destructive GC share one Artifact Store lifecycle lock, preventing collection before publication membership commits.
- System deletion remains logical Catalog deletion; later GC reclaims bytes that are no longer reachable from any retained revision.
