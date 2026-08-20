# Iteration 28.2B — constructor target resolution and source-scope separation

## Production change

`code-analyzer-core 0.40.3` replaces simple-name overwrite behavior for constructor lineage with deterministic Java-context resolution:

1. exact FQCN;
2. declaring package;
3. explicit import;
4. wildcard import;
5. unique simple name;
6. explicit ambiguity gap when several observed declarations remain possible.

Unresolved constructor arguments from test and generated source are no longer counted as production coverage gaps. Confirmed mappings from those scopes remain observable.

## Tests

- full core suite: 386 passed;
- compileall: passed;
- focused collision/scope/compact tests: passed.

## AT900 result

| Metric | Core 0.40.2 | Core 0.40.3 | Delta |
|---|---:|---:|---:|
| data-model facts | 32997 | 32421 | -576 |
| data_model_lineage_gaps | 7062 | 6486 | -576 |
| constructor_mapping_not_resolved | 760 | 184 | -576 |
| generated unresolved constructor args | 303 | 0 published | -303 |
| test unresolved constructor args | 273 | 0 published | -273 |
| production constructor gaps | 184 | 184 | 0 |
| workspace_missing_fact | 7967 | 7391 | -576 |

The remaining 184 production gaps are classified in compact JSON as:

- unknown/local identifier: 120;
- constant_or_default: 38;
- method_call: 20;
- dictionary_lookup: 6.

Observed collision regression:

- domain `Card` now resolves to `cardId`, `isCreditCard`, `number`, `reissued`;
- domain `Phone` now resolves to `number`;
- generated jOOQ fields such as `CARDID`, `BLOCKCODEID`, `PHONEID`, `OPERATORID` are no longer assigned to production domain constructor gaps.

## Downstream finding

`knowledge-layer-core 0.29.0` successfully materializes the corrected gap counts, but its `workspace_missing_fact.payload_json` currently retains only the generic missing-fact contract. Constructor-specific fields from compact JSON are not preserved:

- `source_scope`;
- `target_container_fqcn`;
- `target_resolution_kind`;
- `constructor_argument_index`;
- `constructor_argument_expression_kind`.

This becomes the next isolated contract stage before resolving constants or pass-through mappings.
