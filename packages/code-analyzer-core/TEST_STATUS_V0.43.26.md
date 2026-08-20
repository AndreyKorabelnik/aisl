# Test status — code-analyzer-core 0.43.26

## Scope

Runtime publication release for the first complete typed Core evidence artifact:
`java-type-structure-evidence/v1`.

The existing Java analysis behavior remains available. The new artifact is published in parallel and is not yet registered by Runner or consumed by KLC.

## Targeted source-tree tests

```text
45 passed
```

Covered:

- complete raw Java type declarations;
- fields including static fields and record components;
- inheritance, raw annotations, type references and enum constants;
- forbidden semantic exclusions (`effective_*`, JPA interpretation, logical/physical mappings);
- deterministic artifact identity and repository-relative provenance;
- direct analysis publication;
- Foundation-reuse byte parity;
- manifest and evidence-coverage registration;
- Foundation, composable and data-model profiles;
- generic evidence contract catalog;
- Core analysis catalog and target contracts;
- package version and public contract tests.

## Real repository smoke

Input: `At900. client-profile.zip`.

```text
Java files in scope:       868
Java files parsed:         868
Coverage status:           complete
Type declarations:         909
Field declarations:        4010
Inheritance declarations:  459
Annotation declarations:   2208
Type references:           4171
Unresolved references:     57
Ambiguous references:      5
Diagnostics:               62
Artifact size:              12,447,959 bytes
Manifest registration:     passed
Absolute path check:        passed
```

The unresolved and ambiguous references are explicit diagnostics; they do not suppress successfully observed declarations.

## Clean candidate archive verification

```text
45 passed
source manifest: 450 entries, passed
compileall: passed
analysis-catalog CLI byte parity: passed
target-contracts CLI JSON/Markdown byte parity: passed
evidence-contracts CLI JSON/Markdown byte parity: passed
version smoke: 0.43.26
ZIP integrity: passed
```

## Full regression

Not run. The change is localized to Java typed-evidence publication and targeted profile/Foundation regression is green.

## Known limitations

- Publication is transitionally executed inside `java_source_observation_build`.
- Foundation-reused task runs rebuild the artifact from the same repository snapshot instead of loading a persisted typed artifact.
- Runner does not yet register the typed artifact.
- KLC `code-declared-data-model` materialization is not implemented yet.
- Java annotation type declarations are diagnosed but not materialized as type records.
- Source revision is not resolved by Core and remains `null`; the source-file fingerprint is deterministic.
- The artifact is intentionally uncapped and can be large on real repositories.

## Next step

Add Runner typed-artifact registration for `java-type-structure-evidence/v1` without using `task_id` as semantic identity.
