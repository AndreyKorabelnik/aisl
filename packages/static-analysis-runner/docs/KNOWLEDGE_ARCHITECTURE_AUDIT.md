# Knowledge Architecture Audit

`knowledge_architecture_audit/v1` is a read-only Runner-owned audit over the official knowledge, KLC, Core and execution catalogs.

The audit answers one cross-module question:

> Can a selected user-facing knowledge type be produced through the target typed-evidence and KLC materialization boundary?

It does not execute analysis and does not inspect repository source code.

## Ownership

- Knowledge Catalog defines the user-facing knowledge type and its source lineage.
- KLC Materialization Catalog defines required evidence, required knowledge models and target outputs.
- Core Analysis Catalog shows current source-observation stages.
- Core Target Contracts define the common Foundation, analyzer and evidence-artifact envelope boundary.
- Core Evidence Contract Catalog declares concrete typed evidence schemas and current runtime publication.
- Runner Execution Result Contract defines typed artifact registration requirements.
- Core/KLC Responsibility Map exposes current ownership and legacy Task routes.
- Runner composes these official declarations into one readiness audit.

## One command for every knowledge type

```bash
static-analysis-runner knowledge-architecture-audit \
  --knowledge-catalog knowledge-catalog.json \
  --klc-materialization-contracts knowledge-materialization-contracts.json \
  --core-catalog core-analysis-catalog.json \
  --core-target-contracts core-target-analysis-contracts.json \
  --core-evidence-contracts core-evidence-contract-catalog.json \
  --execution-result-contracts analysis-execution-result-contract.json \
  --responsibility-map core-klc-responsibility-map.json \
  --knowledge code-declared-data-model \
  --output knowledge-architecture-audit.json \
  --markdown knowledge-architecture-audit.md
```

`--knowledge` may be repeated. When omitted, all knowledge types selectable by `knowledge_profile/v2` are audited.

Adding a new knowledge type must not add another CLI command or another knowledge-specific audit implementation.

## Readiness gates

For every knowledge type the audit evaluates:

1. knowledge and materialization contracts;
2. current source-observation producer mappings;
3. typed evidence contract availability;
4. current typed artifact publication;
5. Runner typed artifact registration;
6. KLC materialization runtime;
7. removal of legacy Task-based semantic routing.

Different source families remain separate. The audit never treats physical schema, source-code declarations, persistence mappings or SQL observations as interchangeable evidence.

## Scope and limitation

The audit evaluates declared official contracts. A historical forensic report may still be needed once to prove how a legacy implementation works internally. Once its useful conclusions are transferred into official Core/KLC contracts, that specialized diagnostic command should be removed rather than copied for every knowledge type.

## Target-ready result

When every readiness gate passes and the canonical generic execution path is available, the audited knowledge no longer needs a knowledge-specific Runner route. The next architectural proof is another independent evidence family and materializer:

```text
next_independent_evidence_and_materializer
```

Runner production dispatch must remain unchanged during that proof.
