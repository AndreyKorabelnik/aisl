# Iteration 28.2A — validation report

## Scope

This stage implements two independent baseline corrections discovered by the AT900 gap drill-down:

1. prevent `java_data_model_lineage_build` from republishing persistence facts already emitted by `java_persistence_lineage_build` in the same pipeline;
2. synchronize `static-analysis-runner` materialization contracts with the current `knowledge-layer-core 0.29.0` baseline.

No AT900-, UCP-, class-, package- or field-specific condition was introduced.

## Module results

- code-analyzer-core 0.40.2: 382 tests passed.
- static-analysis-runner 0.9.10: 51 tests passed.
- compileall: passed for both modules.

## Real AT900 replay

Command: repository suite `default-system-analysis.yaml`, shared foundation, tasks `system-description` and `data-model`, with suite-level knowledge materialization.

Result:

- foundation: complete;
- system-description: complete;
- data-model: complete;
- knowledge-layer materialization: complete;
- knowledge-layer-core producer version: 0.29.0;
- DuckDB size: 472395776 bytes;
- main tables: 78.

## Deterministic delta

| Metric | Baseline | 28.2A | Delta |
|---|---:|---:|---:|
| data-model facts | 38835 | 32997 | -5838 |
| storage_lineage_gaps | 1810 | 905 | -905 |
| field_mapping_not_resolved occurrences | 980 | 490 | -490 |
| unique field_mapping gap IDs | 490 | 490 | 0 |
| data_model_lineage_gaps | 7062 | 7062 | 0 |
| constructor_mapping_not_resolved | 760 | 760 | 0 |

All storage-lineage gap kinds were exactly duplicated in the baseline profile because the entire persistence fact set was republished. The correction removes duplicate publication without suppressing a unique gap ID or changing constructor/source-expression analysis.

## Remaining Iteration 28 targets

The next stage remains diagnostic-driven:

1. constructor target type resolution under simple-name collisions;
2. production/test/generated scope separation for constructor gaps;
3. explicit constant/default constructor arguments;
4. typed identity/pass-through provenance at DAO boundaries.
