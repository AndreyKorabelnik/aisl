# Handover — AISL Reporting Consumer Extraction

Status: `AISL_REPORTING_CONSUMER_EXTRACTION_COMPLETE`

## Completed boundary

Framework:

```text
Sources → Core → Runner → KLC → AISL → Knowledge API / Integration Contract
```

Independent consumers:

```text
Knowledge API → aisl-reporting
Knowledge API + Consumer Kit → external LLM/agent
```

`knowledge-reporting` is no longer a framework package. KCP contains no report execution stage and no LLM/presentation configuration. Knowledge API/AISL revisions contain no report slot; report output cannot affect revision identity or CAS reachability.

## Changed framework modules

- knowledge-api 0.39.0
- knowledge-control-plane 1.2.0a32

Unchanged semantic owners:

- evidence-common 0.23.2
- code-analyzer-core 0.44.23a7
- static-analysis-runner 0.10.28
- prepared-knowledge-runtime 0.1.0.post13
- knowledge-layer-core 0.61.0a38
- knowledge-integration 0.1.16

External module:

- aisl-reporting 0.1.0

## Intentional breaking changes

Backward compatibility was not retained. Old report publication payloads/routes/KCP report options are removed rather than adapted. The old direct local `git-change-impact-report/v1` Reporting input is not carried into `aisl-reporting`; new Reporting consumes published AISL knowledge only.

## Parked / not resumed

- Benchmark workstream remains in the separate Benchmark chat.
- No new Core/KLC analyzers or semantics were introduced.
- No object-store backend work was resumed.

## Recommended continuation

1. validate the external LLM against the current Consumer Kit on a newly rebuilt enriched UCP revision;
2. use Benchmark Gold expansion to drive subsequent framework changes;
3. treat `aisl-reporting` as an independent consumer product with its own release lifecycle.
