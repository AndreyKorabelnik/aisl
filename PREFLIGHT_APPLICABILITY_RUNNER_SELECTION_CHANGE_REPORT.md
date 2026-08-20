# Preflight applicability → Runner selection — Block E Change Report

Date: 2026-08-16
Status: PREFLIGHT_APPLICABILITY_RUNNER_SELECTION_BLOCK_E_COMPLETE

## Purpose

Connect the existing Core-owned `preflight_planning.applicability` contract to the existing Runner knowledge-execution planner without creating a second planner, detector registry, or Runner-owned source of applicability semantics.

## Runtime changes

### Core 0.44.23a7

Observed during real acceptance that the previous Java-only applicability declaration for `data-model-candidate-evidence` was incomplete. The existing candidate scanner generically observes Java, declarative schemas, SQL DDL/migrations, and model-oriented repository paths. An SQL-only regression proves that useful `physical_schema` candidate evidence can be produced without any Java files.

Generic correction:
- `data-model-candidate-evidence.preflight_planning.applicability.status = not_formalized`;
- no Java-only hard-skip predicate is published;
- the missing safe predicate is an explicit `current_state_gap`;
- scanner/runtime semantics are unchanged;
- no datamart/application-specific exception was added.

### Runner 0.10.27

The existing source snapshot now records observed lowercase file extensions in addition to languages and file count. Runner mechanically evaluates only the Core-owned applicability predicate.

Safety behavior:
- optional automatic `produce_if_missing` evidence may be omitted only when all observed source snapshots are `not_applicable` under a formalized Core predicate;
- `unresolved` / `not_formalized` applicability preserves execution and emits `evidence_applicability_unresolved_execution_preserved`;
- explicit/required evidence is never silently skipped; observed incompatibility becomes `required_evidence_observed_not_applicable` and blocks the plan;
- no concept inference or analyzer-code inspection is used to decide applicability.

### Knowledge Control Plane 1.2.0a27

Pinned runtime catalogs were regenerated from canonical owners after the Core and Runner version changes. KCP adds no independent applicability logic.

## Real observed effect

Gateway (`gateway-sberid-userinfo-by-ucpid`): all four bounded P0/P1 Core analyzers remain selected because the observed source landscape satisfies the relevant formalized predicates; `data-model-candidate` remains deliberately unresolved and therefore executes.

SQL-heavy datamart (`datamart_profile_fl`): P0/P1 Core analyzer count changes from 4 to 3. Only Java-only `interaction-boundary-evidence` is omitted. `data-model-candidate-evidence` remains selected because its safe non-applicability is not formalized and real SQL candidate evidence exists.

The skipped Block D interaction analyzer had observed 0 inbound / 0 outbound boundaries. Positive Repository Inventory knowledge is preserved. `system_interaction` becomes conservatively `not_evaluated` with an explicit coverage gap instead of the previous evaluated `not_detected` result.

## Architectural result

Block E is an execution optimization over owner-provided observed applicability. It is not concept inference and it is not a second analysis subsystem.
