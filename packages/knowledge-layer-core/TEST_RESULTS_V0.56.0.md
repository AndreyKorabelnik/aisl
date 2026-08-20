# Test Results — knowledge-layer-core 0.56.0

## Targeted checks

The changed composition path and its direct dependencies were tested:

- code-declared data model;
- physical model and physical-model queries;
- logical/physical mapping;
- effective data model;
- generic materialization runtime;
- materialization contracts;
- offline package/version import.

Result:

- **32 passed**;
- `compileall`: passed;
- public effective-model exports: passed.

A full KLC regression was intentionally not run. The generic runtime mechanism was not changed; this iteration adds one KLC-owned handler and its typed composition tables.

## Real unchanged-Runner smoke

Executed with Core 0.43.28, unchanged Runner 0.9.51 and KLC 0.56.0:

- Knowledge Profile requested `effective-data-model`;
- Core analyzers: 2;
- execution nodes: 6;
- KLC materializations: 4;
- knowledge artifacts: 5;
- published capabilities: 17;
- status: `completed`.

Execution order:

1. `java-persistence-mapping-analyzer`;
2. `java-type-structure-analyzer`;
3. `code-declared-data-model`;
4. `physical-model`;
5. `logical-physical-mapping`;
6. `effective-data-model`.

Effective model result:

- logical entities: 2;
- logical/effective fields: 5;
- keys: 2;
- relationships: 1;
- unmapped physical objects: 0;
- gaps: 0;
- technical domains: 1;
- technical entity clusters: 1.

The smoke confirms that no Core or Runner production-code change is required for the KLC-only composition.
