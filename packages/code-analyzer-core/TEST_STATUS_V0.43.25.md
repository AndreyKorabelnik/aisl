# Test status — code-analyzer-core 0.43.25

## Scope

Read-only contract release. Adds the generic `core_evidence_contract_catalog/v1` and the first typed payload contract `java-type-structure-evidence/v1`. No analyzer runtime or artifact publication changed.

## Source-tree and clean-ZIP tests

```text
21 passed
```

Covered:

- generic evidence contract catalog;
- complete Java declaration sections;
- semantic exclusions;
- deterministic fingerprints;
- input fingerprint validation;
- generic CLI behavior;
- Core analysis catalog and target contracts;
- lightweight CLI and package version.

## Exact archive verification

```text
source manifest: 448 entries, passed
compileall: passed
analysis-catalog CLI and byte parity: passed
target-contracts CLI and JSON/Markdown byte parity: passed
evidence-contracts CLI and JSON/Markdown byte parity: passed
version smoke: 0.43.25
ZIP integrity: passed
```

## Current result

`java-type-structure-evidence/v1` is defined but not published. Current source observations exist in `java_structural_scan` and `java_source_observation_build`.

## Full regression

Not run because runtime is unchanged.

## Known limitations

- No runtime evidence artifact is written yet.
- Runner does not register this artifact yet.
- KLC `code-declared-data-model` materialization remains contract-only.
- Current Java observations remain spread across `AnalysisResult.schemas`, facts and the uncapped source-observation store.

## Next step

Implement runtime publication of `java-type-structure-evidence/v1` from the existing Java syntax parse, without adding new semantic interpretation and without changing legacy outputs yet.
