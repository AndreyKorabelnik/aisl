# Handover — Preflight applicability → Runner selection / Block E

Date: 2026-08-16
Status: PREFLIGHT_APPLICABILITY_RUNNER_SELECTION_BLOCK_E_COMPLETE

## Completed

- Block A — Preflight Evidence Audit: complete.
- Block B — Preflight Execution Contract: complete.
- Block C — Repository Inventory v3: complete.
- Block D — Concept Detector Registry: complete.
- Block E — Core-owned applicability wired into existing Runner selection: complete.

Final changed versions in Block E:
- code-analyzer-core `0.44.23a7`;
- static-analysis-runner `0.10.27`;
- knowledge-control-plane `1.2.0a27`.

Unchanged but revalidated:
- knowledge-layer-core `0.61.0a35`;
- prepared-knowledge-runtime `0.1.0.post10`;
- knowledge-api `0.35.0`.

Authoritative regression: Core 610/610; Runner 113/113; KLC 256 PASS / 8 SKIP; Prepared 10/10; API 118/118; KCP 95/95. Fresh gateway and SQL-heavy datamart publication PASS.

## Important discovered gap

`data-model-candidate-evidence` safe non-applicability is deliberately `not_formalized`. The existing scanner consumes Java, declarative schema, SQL DDL/migration, and model-oriented path signals. Runner therefore preserves execution until Core can publish a complete predicate. This is a visible gap, not a fallback.

## Real selective-execution result

- gateway: 4/4 current P0/P1 analyzers retained;
- SQL-heavy datamart: 3/4 retained; only Java-only interaction-boundary analysis is proven non-applicable and omitted;
- no positive Repository Inventory semantic loss; skipped interaction evidence was previously empty;
- absence of execution is represented as `not_evaluated` + coverage gap rather than an invented negative conclusion.

## Continuation point

Block F — broader end-to-end selective-execution acceptance across structurally different repository classes.

Block F should prove that the mechanism behaves safely beyond the two Block E repositories and compare selective execution against a full/baseline execution on semantic/structural dimensions. It should not invent new predicates merely to increase skip counts.

Only after evidence supports a generic richer applicability predicate should Core formalize additional hard-skip conditions.

## Parked scope

FI-002, portfolio topology/Islands, Benchmark Miner changes, vector/embedding retrieval, universal graph/EAV, agent memory/planning, new concept expansion, and cleanup without a proven architectural duplicate remain parked.
