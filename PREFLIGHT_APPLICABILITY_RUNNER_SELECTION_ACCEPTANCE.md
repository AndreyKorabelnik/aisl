# Preflight applicability → Runner selection — Block E Acceptance

Date: 2026-08-16
Verdict: PASS

## Acceptance conditions

- Runner consumes the official Core evidence contract applicability metadata.
- Hard skip is limited to proven observed non-applicability for optional automatic production.
- Unresolved applicability preserves execution and remains visible in diagnostics.
- Required/explicit evidence cannot be silently optimized away.
- A false/incomplete owner predicate must be corrected at the owner, not patched in Runner for a particular repository.
- Real publication must preserve useful Repository Inventory knowledge.

## Generic safety correction found by real acceptance

The initial Core declaration for `data-model-candidate-evidence` said Java-only applicability. Real SQL-heavy acceptance showed that this would discard useful observed SQL physical-schema candidate evidence. Inspection of the existing generic scanner confirmed the issue: the scanner also observes declarative schemas, SQL DDL/migrations, and model-oriented paths.

Core 0.44.23a7 therefore marks this applicability `not_formalized`. Runner treats that as unresolved and preserves execution. A dedicated SQL-only Core regression proves candidate evidence without Java. No application-specific fallback was introduced.

## Real acceptance

Fresh `--force-rebuild` publication through KCP → Runner → Core → KLC → Knowledge API:

- gateway: PASS; 4 Core analyzers selected; Repository Inventory concept projection and composition are semantically equal to Block D;
- SQL-heavy datamart: PASS; 3 Core analyzers selected instead of 4; only `interaction-boundary-analyzer` is skipped;
- datamart positive concept semantics are preserved, including `data_model = probable`, confidence `probable_inference`, score `27.0`, 156 structural members, 10 structural-novelty candidates, 6 unknown primitives, and 0 automatic unclassified candidates;
- previous skipped interaction evidence contained 0 inbound and 0 outbound boundaries;
- datamart `system_interaction` changes from evaluated `not_detected` to `not_evaluated` plus a visible coverage gap. This is an intentional conservative semantic improvement caused by not executing the analyzer, not a positive-evidence loss;
- both Repository Inventory products remain `evaluation.phase = preflight`.

Exact provenance is stored in `validation/preflight-applicability-runner-selection-2026-08-16/REAL_ACCEPTANCE.json` and the two final execution plans.

## Verdict

PASS. Selective execution is connected to the existing Runner planner with Core-owned applicability, visible uncertainty, no silent fallback, and real proof that useful knowledge is retained.
