# Test Results — static-analysis-runner 0.9.51

## Targeted checks

- 49 passed: execution planning, canonical knowledge execution, generic evidence execution, generic KLC execution, knowledge planning and CLI.
- `compileall`: passed.
- Architecture source check: the changed scheduler contains no Java persistence, logical/physical mapping or physical-model identifiers.

## Expanded regression

The monolithic pytest invocation exceeded the environment limit without a test failure. All Runner test files were then executed in isolated groups, with the historically order-sensitive workspace file in its own process.

Result across every collected Runner test:

- **158 passed**;
- **0 skipped**;
- **0 failed**.

## Real second-family smoke

One `knowledge-execute` call completed the graph:

```text
java-persistence-mapping-analyzer
java-type-structure-analyzer
→ code-declared-data-model
→ physical-model
→ logical-physical-mapping
```

The executor produced three knowledge artifacts and published 15 capabilities. The only Runner production change is generic node-kind phase ordering; no evidence-family, knowledge or materialization dispatch was added.
