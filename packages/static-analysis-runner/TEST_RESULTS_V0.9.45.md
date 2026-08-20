# Test results — static-analysis-runner 0.9.45

## Scope

Read-only `knowledge_architecture_audit/v1`. Repository/workspace runtime, Core runtime, KLC runtime and Analysis UI were not changed.

## Targeted tests

```text
44 passed in 0.50s
```

Included:

- generic knowledge architecture audit;
- code-declared-data-model readiness gates;
- current typed physical-model case;
- all-selectable default audit;
- unknown/duplicate knowledge validation;
- cross-catalog fingerprint validation;
- deterministic CLI JSON/Markdown;
- knowledge planning v2;
- execution-result contracts;
- mechanism/responsibility catalogs;
- CLI exposure and version.

## Additional checks

- `compileall`: passed.
- version smoke: `0.9.45`.
- JSON Schema draft 2020-12 validation: passed.
- real audit from Core 0.43.23 + KLC 0.53.9 + Runner contracts: passed.

## Real audit result for `code-declared-data-model`

Passed gates:

- knowledge contract;
- required source observations.

Blocked gates:

- typed evidence contracts;
- Core typed artifact publication;
- Runner artifact registration;
- KLC materialization runtime;
- legacy semantic routing removal.

## Not run

Full Runner regression was intentionally not run because execution runtime was not changed.

Wheel was not built.

## Clean provisional ZIP

- manifest validation: 326 entries, passed;
- focused tests: 14 passed;
- `compileall`: passed;
- real official-catalog CLI audit: passed;
- JSON/Markdown byte parity: passed;
- version smoke: `0.9.45`.
