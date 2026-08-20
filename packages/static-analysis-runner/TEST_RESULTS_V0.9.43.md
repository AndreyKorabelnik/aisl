# Test results — static-analysis-runner 0.9.43

## Scope

This iteration adds read-only user knowledge planning contracts. Repository, workspace, Suite, Task, Core, KLC and Analysis UI runtime behavior was not changed, so the full regression was intentionally not run.

## Targeted tests

Groups:

- knowledge catalog/profile/resolver;
- analysis execution result contracts;
- official mechanism catalog;
- built-in Suite catalog;
- CLI and version.

Result:

```text
42 passed
```

Covered:

- compilation of `knowledge_catalog/v1` from four official upstream contracts;
- user/internal materialization separation;
- current-runtime versus target-contract availability;
- repository/workspace scope validation;
- rejection of Task/Suite/Core technical fields in `knowledge_profile/v1`;
- deterministic evidence/materialization/Foundation resolution;
- recommended knowledge dependencies;
- JSON and Markdown determinism;
- CLI export and YAML profile resolution;
- upstream fingerprint validation.

## Real contract integration

Generated from:

- Core target contracts 0.43.22;
- KLC materialization contracts 0.53.8;
- Runner execution-result contract 0.9.42;
- Core/KLC responsibility map 0.9.41.

Observed:

- 12 user-facing knowledge descriptions;
- 11 selectable in `knowledge_profile/v1`;
- 2 internal materializations hidden;
- 11 knowledge types available through the current runtime;
- only 2 already ready through the target typed-input boundary;
- runtime states: 5 `current_legacy`, 4 `current_partial`, 2 `current_typed`;
- example workspace profile resolves 4 selected knowledge types;
- actual repository/workspace source availability remains explicitly `not_assessed`.

## Additional checks

- `compileall`: passed;
- `knowledge_profile_v1.schema.json`: valid JSON;
- real `knowledge-catalog` CLI export: passed;
- real `knowledge-profile-resolve` CLI export: passed;
- upstream canonical fingerprints: passed;
- execution effect: `none`;
- Analysis UI: unchanged;
- wheel: not built by agreement.

## Full regression decision

Not run. No runtime execution path, materializer, query contract or UI component changed.

## Clean provisional ZIP verification

From a newly unpacked provisional source archive:

```text
42 passed
```

Additional checks:

- source manifest: passed;
- `compileall`: passed;
- real catalog/profile CLI export: passed;
- generated JSON byte parity: passed;
- generated Markdown byte parity: passed.
