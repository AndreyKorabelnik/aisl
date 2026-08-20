# Test status — code-analyzer-core 0.43.24

## Scope

Read-only cleanup release. Removed the temporary conceptual-model-specific sufficiency CLI, implementation module, resource definitions, tests and current validation copies. No scanner, Foundation, analysis profile, prepared artifact or materialization runtime changed.

## Tests executed in source tree

```text
18 passed
```

Selected tests covered:

- specialized command/module/resource removal;
- Core analysis catalog;
- Core target contracts;
- lightweight CLI;
- package version consistency.

## Clean ZIP verification

The self-contained archive was extracted into a clean directory and checked successfully:

```text
18 passed
source manifest: 440 entries, passed
compileall: passed
analysis-catalog CLI: passed
core analysis catalog byte parity: passed
target-contracts CLI: passed
target contracts JSON/Markdown byte parity: passed
version smoke: 0.43.24
ZIP integrity: passed
```

## Full regression

Not run. The release changes only temporary architecture-audit tooling and documentation; analysis runtime is unchanged.

## Known limitations

- The historical `conceptual_model_evidence_sufficiency/v1` result from Core 0.43.23 remains an external released validation artifact, not a current Core API.
- The generic Runner-owned `knowledge_architecture_audit/v1` is read-only and does not yet publish typed evidence.
- `java-type-structure-evidence/v1` is not defined or emitted yet.

## Next step

Define the narrow, complete and uncapped Core-owned `java-type-structure-evidence/v1` contract for the first `code-declared-data-model` vertical slice. Runtime publication should follow in a separate iteration.
