# Test results — static-analysis-runner 0.9.42

## Scope

This iteration adds a read-only Runner-owned architecture contract. Repository, workspace, Suite, Task, portfolio, Core and KLC runtime behavior was not changed, so the full regression was intentionally not run.

## Targeted tests

Groups:

- analysis execution result contracts;
- CLI and version;
- official mechanism catalog and Core/KLC responsibility map;
- built-in Suite catalog.

Result:

```text
32 passed
```

Covered:

- official Core and KLC contract fingerprint validation;
- Runner/Core/KLC responsibility boundary;
- typed evidence semantic identity;
- current repository/Suite/workspace/portfolio manifest assessment;
- deterministic JSON and Markdown output;
- revised vertical-slice implementation sequence;
- CLI export and version;
- existing mechanism-catalog and Suite contracts.

## Real integration

Generated from:

- `core_target_analysis_contracts/v1`, Core 0.43.22;
- `knowledge_materialization_catalog/v1`, KLC 0.53.8.

Observed:

- 4 current Runner manifest variants assessed;
- 0 fully compliant variants;
- 1 variant with partial typed evidence registration (SQL);
- 2 variants with direct or indirect Foundation identity;
- 3 task-semantic-coupled variants;
- 8 current KLC task-semantic routes.

## Additional checks

- `compileall`: passed;
- real CLI export: passed;
- canonical upstream fingerprint validation: passed;
- execution effect: `none`;
- wheel: not built by agreement.

## Clean ZIP verification

From the unpacked provisional source archive:

```text
14 passed
```

Additional clean checks:

- source manifest verification: passed;
- `compileall`: passed;
- CLI export: passed;
- generated JSON byte parity: passed;
- generated Markdown byte parity: passed.
