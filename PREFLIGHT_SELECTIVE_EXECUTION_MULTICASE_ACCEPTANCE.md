# Preflight Selective Execution — Block F Multi-case Acceptance

Date: 2026-08-16  
Status: **PASS / BLOCK F COMPLETE**

## Purpose

Validate the released Block E selective-execution mechanism across structurally different real repositories, using the released Block D behavior as the pre-selection baseline. Block F is validation-only: it introduces no runtime code or contract change.

## Compared baselines

- Baseline: Block D — Core `0.44.23a6`, Runner `0.10.26`, KLC `0.61.0a35`; all current bounded P0/P1 Repository Inventory analyzers execute.
- Selective: Block E — Core `0.44.23a7`, Runner `0.10.27`, KLC `0.61.0a35`; optional automatic production may be omitted only from Core-owned formalized applicability plus observed source landscape.

Both paths were run through the official KCP → Runner → Core → KLC → Knowledge API publication path with force rebuild.

## Real repository matrix

| Case | Observed landscape | Baseline | Selective | Proven omission |
|---|---|---:|---:|---|
| gateway | Java + JSON/YAML/XML | 4 | 4 | none |
| datamart | Scala + SQL + JSON/YAML, no Java | 4 | 3 | `interaction-boundary-analyzer` |
| insurance | SQL + JSON/YAML, no Java | 4 | 3 | `interaction-boundary-analyzer` |
| UCP data model | Java + XML, no JSON/YAML | 4 | 3 | `structured-file-shape-analyzer` |

All eight baseline/selective publication jobs succeeded.

## Semantic / structural acceptance

Across all four cases:

- positive concept set is preserved;
- composition is preserved;
- detected concepts are preserved;
- root file count and extension-family count are preserved;
- structural member count is preserved;
- structured-shape-family count is preserved;
- structural novelty count is preserved;
- unknown primitive count is preserved;
- unclassified concept candidate count is preserved;
- evaluation remains `preflight`;
- selective execution never adds an analyzer absent from the baseline.

The machine-readable acceptance reports all required booleans `true` and verdict `PASS`.

## Evidence discipline for omitted analyzers

The baseline evidence produced by every omitted analyzer was empty for the bounded signal that justified omission:

- datamart interaction evidence: `0` boundaries, `0` inbound, `0` outbound;
- insurance interaction evidence: `0` boundaries, `0` inbound, `0` outbound;
- UCP structured-file evidence: `0` candidate files, `0` parsed files, `0` members.

The selective path does not convert an omitted evaluation into a false negative. Where the omitted analyzer previously produced an evaluated-empty result, the resulting knowledge is conservative (`not_evaluated` and/or an explicit coverage gap) unless another executed analyzer still evaluates that concept.

## Important calibration

`data-model-candidate-evidence` remains `not_formalized` for applicability because the Core scanner observes mixed Java, declarative-schema, SQL DDL/migration, and model-oriented path evidence. Runner therefore preserves execution rather than hard-skipping it. This is an explicit current gap, not a silent fallback.

## Performance note

Single-run durations are retained as provenance only. They are not a benchmark and are not used as an acceptance criterion.

## Result

**PASS.** The Concept Discovery / Preflight Planning selective-execution initiative is complete through Blocks A–F. Further applicability expansion is optional future calibration and requires generic owner-level evidence; it is not required to close this initiative.

Machine evidence: `validation/preflight-selective-execution-multicase-2026-08-16/REAL_MULTICASE_ACCEPTANCE.json`.
