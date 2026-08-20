# Handover — Concept Discovery / Preflight Planning through Block F

Date: 2026-08-16  
Status: **INITIATIVE COMPLETE**

## Completed sequence

- Block A — Preflight Evidence Audit: COMPLETE.
- Block B — Preflight Execution Contract: COMPLETE.
- Block C — Repository Inventory v3: COMPLETE.
- Block D — KLC Concept Detector Registry: COMPLETE.
- Block E — Core applicability → Runner selective execution: COMPLETE.
- Block F — broader multi-case selective-execution acceptance: COMPLETE.

## Canonical architecture at handover

```text
Repository
  ↓
Runner observed source snapshot
  ↓
Core-owned preflight_planning.applicability
  ↓
existing Runner knowledge-execution planner
  ↓
selected Core evidence analyzers
  ↓
KLC Repository Inventory v3 + Concept Detector Registry
  ↓
Prepared Knowledge / Knowledge API
```

Hard-skip authorization comes only from a formalized owner predicate plus observed source landscape. Unresolved applicability preserves execution and remains diagnostic-visible.

## Block F Gold / Acceptance

No Manual Gold is used as a runtime source. Block F acceptance is structural/semantic comparison between the released pre-selection Block D baseline and released selective Block E behavior over four real repository classes.

Acceptance: PASS for all four cases and all machine global assertions.

## Authoritative runtime regression

Package bytes are unchanged from Block E, whose authoritative regression is:

- Core 610/610 PASS
- Runner 113/113 PASS
- KLC 256 PASS / 8 SKIPPED
- Prepared Runtime 10/10 PASS
- Knowledge API 118/118 PASS
- KCP 95/95 PASS

Block F additionally provides eight fresh real publication jobs and a machine structural/semantic diff.

## Known gap

`data-model-candidate-evidence` applicability is intentionally `not_formalized`. Core implementation proves that this scanner is not Java-only: it also observes declarative schema, SQL DDL/migrations, and model-oriented paths. Runner must continue executing it until an owner-level generic predicate can safely express all relevant sources.

This gap does not block the completed initiative.

## Parked scope

Do not automatically resume FI-002, Islands/portfolio topology, Benchmark Miner changes, or other parked work. `PARKED_SCOPE.md` remains authoritative.

## Continuation point

There is no mandatory Block G. Return to user/product value and choose the next workstream explicitly. If selective execution is revisited, expand applicability only where observed generic evidence and owner-level tests prove a hard skip safe and where the optimization has demonstrated value.
