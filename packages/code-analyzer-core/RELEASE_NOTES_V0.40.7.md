# code-analyzer-core 0.40.7

Iteration 28.2F completes the deterministic constructor-resolution contour for exact Java lexical and JDK language/API forms found during cross-system validation.

## Changes

- recognizes generic static JDK empty-collection factories such as `Collections.<T>emptyList()` while retaining import/API proof requirements;
- recognizes Java class literals such as `Type.class` as observed constructor origins;
- resolves enhanced-for variables only inside the exact Tree-sitter loop byte span and preserves the iterable expression as provenance;
- keeps unknown helper, framework and DAO return values unresolved when no return-field contract is observed;
- preserves repository-neutral behavior: no AT900, UCP, package, class or field-name conditions were added.

## Cross-system result

- AT900 remains at **3** intentional direct-DAO constructor gaps;
- UCP API constructor gaps: **1 → 0** from 0.40.6 and **4 → 0** from the Iteration 28 baseline;
- UCP TSA constructor gaps: **9 → 2** from 0.40.6 and **454 → 2** from the Iteration 28 baseline;
- the two remaining UCP cases are `this.getLog()` and `supplier.get()`, intentionally unresolved because the source does not prove their result contract.
