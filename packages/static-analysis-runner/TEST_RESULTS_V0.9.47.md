# Test results — static-analysis-runner 0.9.47

## Scope

Universal execution of KLC materialization plans. Repository/Suite legacy orchestration and Analysis UI were not changed.

## Targeted source tests

- generic materialization executor;
- knowledge architecture audit;
- execution-result contracts;
- knowledge planning;
- existing KLC invocation compatibility.

Result: `38 passed` before packaging.

## Real generic smoke

Runner consumed an actual 0.9.46 repository run containing registered `java-type-structure-evidence/v1` and invoked KLC 0.54.1 only through `knowledge_materialization_runtime/v1`.

```text
status: completed
materializations: 1
knowledge artifacts: 1
source units: 3
types: 3
fields: 5
inheritance: 1
effective fields: 6
relationships: 1
gaps: 0
legacy code_conceptual_model consumed: false
```

Semantic policy:

```text
runner dispatch: generic_contract_driven
KLC dispatch: materialization_id_to_klc_owned_handler
capability publication: completed_materialization_results_only
Task/Suite/Profile semantics: not_used
legacy fallback: not_supported
```

## Packaging policy

Per the accelerated no-legacy process, broad legacy regression is intentionally omitted. Final verification is limited to changed contracts/runtime, one real smoke, compileall, source manifest, deterministic official exports and exact ZIP integrity.

## Clean candidate ZIP verification

```text
focused tests: 38 passed
source manifest: 373 files, passed
compileall: passed
execution-result contract byte parity: passed
knowledge catalog byte parity: passed
knowledge resolution plan byte parity: passed
knowledge architecture audit byte parity: passed
generic materialization CLI smoke: passed
version smoke: 0.9.47
ZIP integrity: passed
```

The final archive is rebuilt after recording this status and receives a shorter exact-archive verification.

## Exact final ZIP verification

```text
executor + architecture audit tests: 12 passed
source manifest: passed
compileall: passed
generic materialization CLI smoke: passed
source-level no-special-case assertions: passed
version smoke: 0.9.47
ZIP integrity: passed
```
