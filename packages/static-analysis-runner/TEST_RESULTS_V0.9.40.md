# Test results — static-analysis-runner 0.9.40

## Targeted result

The change affects only the read-only mechanism catalog and its CLI. Repository/workspace analysis execution was not changed, so a full Runner regression was intentionally not run.

Targeted groups:

- mechanism catalog and official Core contract validation;
- CLI version and command parsing;
- built-in Suite catalog;
- repository Suite orchestration contracts.

Result:

```text
30 passed
```

Additional checks:

- `compileall`: passed;
- official Core catalog schema validation: passed;
- official Core catalog fingerprint validation: passed;
- missing Task-linked Core profile failure: passed;
- legacy `--profiles-root` catalog option rejection: passed.

## Real integration

The catalog was generated successfully from:

- code-analyzer-core 0.43.21 official catalog;
- static-analysis-runner 0.9.40;
- knowledge-layer-core 0.53.7;
- analysis-ui 2.0.0a61.

Observed composition:

- 5 Analysis UI pipeline profiles;
- 7 Runner Suites;
- 8 Runner Tasks;
- 8 Task-linked Core profiles;
- 14 total Core profiles;
- 48 Core stage definitions;
- 9 Java derived-stage contracts;
- 4 knowledge-materialization candidates.

## Runtime behavior

No repository, workspace, Suite, Task, Core execution or Knowledge Layer materialization path changed.

## Packaging checks

- wheel build with `--no-build-isolation`: passed;
- wheel installation into a clean target: passed;
- wheel `version` smoke: `0.9.40`;
- wheel `mechanism-catalog` smoke against Core 0.43.21: passed.
