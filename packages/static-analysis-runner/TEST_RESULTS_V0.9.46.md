# Test results — static-analysis-runner 0.9.46

## Scope

Runtime registration of the first Core typed evidence artifact, `java-type-structure-evidence/v1`, plus official-catalog assessment updates. KLC materialization and Analysis UI were not changed.

## Completed regression groups

The complete test file set was executed in three non-overlapping groups because one monolithic process exceeded the command timeout.

```text
Runtime/repository/suite/workspace/SQL/physical-model: 77 passed in 28.20s
Architecture/knowledge/execution contracts:          42 passed in 1.17s
Portfolio topology contracts/runtime:                 11 passed in 3.85s
Total completed:                                     130 passed
```

The earlier monolithic `pytest -q` run reached about 55% without a reported failure and was terminated by the execution timeout. It is not counted as a successful test run.

## Real Core integration smoke

Runner 0.9.46 invoked actual Core 0.43.26 on a three-file Java repository.

```text
repository status: completed
registered evidence artifacts: 1
registered analyzer executions: 1
artifact: java-type-structure-evidence/v1
Java files discovered/parsed: 3 / 3
field declarations: 5
inheritance declarations: 1
coverage: complete
diagnostics: 0
task_id/suite_id semantic keys: absent
```

## Official contract exports

Generated and validated:

- `analysis_execution_result_catalog/v1`;
- `knowledge_catalog/v2`;
- `knowledge_architecture_audit/v1` using `core_evidence_contract_catalog/v1`.

For `code-declared-data-model`, the following gates pass:

- knowledge contract;
- source observations;
- typed evidence contract;
- Core runtime publication;
- Runner artifact registration.

Remaining blocked gates:

- KLC materialization runtime;
- legacy semantic routing removal.

## Additional checks before packaging

- package version: `0.9.46`;
- full source `compileall`: required for clean ZIP verification;
- source manifest: regenerated after final source cleanup;
- wheel: intentionally not built.

## Known limitations

- Only `java-type-structure-evidence/v1` is registered through the new Core typed-artifact path.
- Suite preservation is task-local; there is no general suite-level deduplicated artifact registry yet.
- Workspace visibility is inherited through repository/suite manifests rather than a direct workspace artifact registry.
- One Core process attempt is reused as the transitional analyzer-execution attempt because Core still publishes the artifact inside `java_source_observation_build`.
- Core artifact source revision may be null; Runner separately records the repository revision.
- KLC does not yet import or materialize `code-declared-data-model` from the artifact.
- Legacy Task-based data-model selection and capability publication remain.
- Analysis UI is unchanged.

## Clean candidate ZIP verification

```text
focused runtime/contract tests: 40 passed in 9.00s
source manifest: passed
compileall: passed
execution-result JSON/Markdown byte parity: passed
knowledge-catalog JSON/Markdown byte parity: passed
knowledge-audit JSON/Markdown byte parity: passed
version smoke: 0.9.46
```
