# Test results — static-analysis-runner 0.9.44

## Scope

Read-only knowledge-planning contract update. Analysis runtime, repository/workspace execution, KLC runtime and UI are unchanged.

## Targeted regression

Command group:

- `tests/test_knowledge_planning.py`
- `tests/test_execution_result_contracts.py`
- `tests/test_cli.py`
- `tests/test_mechanism_catalog.py`
- `tests/test_builtin_suite_catalog.py`

Result: **42 passed**.

## Real contract generation

Generated and validated against:

- Core target contracts 0.43.23;
- KLC materialization catalog v2 / KLC 0.53.9;
- Runner execution-result contract 0.9.42 and regenerated 0.9.44 assessment;
- Core/KLC responsibility map 0.9.41.

Observed result:

- 15 catalogued knowledge types;
- 14 selectable knowledge types;
- 4 explicitly requested knowledge types in the example profile;
- 3 implicit required knowledge dependencies;
- 7 resolved knowledge types;
- no user-facing `conceptual-data-model`;
- `effective-data-model` is composition over code-declared, physical and logical/physical mapping knowledge;
- SQL and storage usage remain separate optional knowledge enrichments.

## Packaging checks

To be repeated on the exact final ZIP:

- source manifest;
- `compileall`;
- focused knowledge-planning tests;
- CLI export;
- JSON/Markdown byte parity;
- version smoke;
- ZIP integrity.

## Intentionally not run

Full Runner regression was not run because runtime execution and UI did not change.

Wheel was not built.
