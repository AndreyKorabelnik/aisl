# AISL Reachability-Based Artifact Store GC — Acceptance

Date: 2026-08-16
Status: **AISL_REACHABILITY_GC_COMPLETE**

## Architecture accepted

- AISL Catalog revision membership is the only reachability source of truth.
- Every retained committed revision is a root regardless of `active`, `superseded` or `inactive` state.
- Typed reachability fields are revision execution result, optional report and KnowledgeProduct `physical_artifacts[]`.
- No arbitrary metadata scan, refcount table, second artifact registry, dual-write or SQLite normalization was introduced.
- GC is operational maintenance after publication and is not required for publication correctness.
- Retention policy is external; GC enforces durability for whatever revisions remain in the Catalog.
- Publication finalize/catalog commit and destructive GC share the same Artifact Store lifecycle lock.

## Safety semantics

- `plan` is non-destructive.
- `sweep` requires explicit `confirm_delete_unreferenced=true`.
- `grace_period_seconds` is supplied by the operator.
- only official CAS layout blobs can be deleted; unknown/unmanaged entries remain visible diagnostics and untouched.
- crash `.staging` files are separate candidates under the same grace.
- missing referenced blobs are explicit diagnostics and are never guessed/repaired.

## Deterministic E2E acceptance

Validation artifact: `validation/aisl-reachability-gc-2026-08-16/GC_REALISTIC_E2E_ACCEPTANCE.json`.

Two mixed observed+derived revisions were published, making one superseded and one active. Producer workspaces were removed. An old unreferenced CAS blob and old crash staging file were added.

Before sweep:
- retained revisions: 2;
- reachable digests: 6;
- store blobs: 7;
- exactly 1 unreferenced old blob eligible;
- exactly 1 old staging file eligible;
- 0 missing referenced blobs.

After sweep:
- only the orphan blob/staging file were removed;
- observed + derived exact reads on both active and superseded revisions: PASS.

After deleting the system from the Catalog:
- retained revisions: 0;
- reachable digests: 0;
- all 6 formerly referenced blobs became eligible;
- final sweep removed them;
- final canonical CAS blob count: 0.

## Regression

- Knowledge API: 118/118 PASS.
- Prepared Runtime: 10/10 PASS.
- Knowledge Integration: 19/19 PASS.
- Knowledge Reporting: 100 PASS / 2 SKIPPED.
- AISL Contract 0.3.0b8: 47/47 PASS.
- KLC: 252 PASS / 8 SKIPPED.
- KCP: 95/95 PASS.

A monolithic KLC run hit the external wrapper timeout and was not counted; all KLC tests were rerun in completed groups producing the authoritative 252/8 result.
