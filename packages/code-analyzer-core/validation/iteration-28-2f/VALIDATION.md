# Iteration 28.2F validation — code-analyzer-core 0.40.7

## Purpose

Validate the final safe constructor-resolution additions across AT900 and UCP and confirm that UCP relationship/storage evidence is unchanged by the constructor work.

## Safe forms added

1. Generic JDK empty-collection factory: `Collections.<T>emptyList/emptyMap/emptySet()`.
2. Java class literal: `Type.class`.
3. Enhanced-for lexical variable inside its exact Tree-sitter loop span.

## Explicitly not inferred

- direct DAO result fields;
- arbitrary helper-method result fields;
- framework getter return semantics;
- `Supplier.get()` result semantics without an observed contract.

## Results

| System/repository | Baseline constructor gaps | 0.40.6 | 0.40.7 |
|---|---:|---:|---:|
| AT900 | 760 | 3 | 3 |
| UCP API | 4 | 1 | 0 |
| UCP TSA v4 | 454 | 9 | 2 |

Full core regression: **404 passed**.

The canonical UCP `repository-data-model-static` workspace completed for both repositories with zero failures. It contains **504 relationships**, **312 key observations**, **224 storage references**, **202 storage-key derivations**, **241 reference-value/key correspondences**, and **19 excluded candidates**. All 224 storage-reference observations continue to require downstream physical-encoding interpretation.
