# Iteration 28.2D validation — code-analyzer-core 0.40.5

## Result

- production `constructor_mapping_not_resolved`: **184 → 30** (**-154**);
- all data-model lineage gaps: **6,486 → 6,332**;
- workspace missing facts: **7,391 → 7,237**;
- attribute mappings: **1,591 → 1,723** (**+132**);
- attribute derivations: **1,529 → 1,940** (**+411**);
- remaining constructor gaps retaining raw expression in DuckDB: **30/30**.

## Implemented generic patterns

- local variable declaration recursion;
- direct method-parameter pass-through;
- implicit `this.field` pass-through;
- literal/null/boolean/numeric and conventional named constants as observed origins;
- nested object creation with explicit parameter inputs;
- raw expression and resolution-attempt metadata for remaining gaps.

## Deliberately unresolved

The remaining 30 cases are not guessed. They include helper/DAO return values, lambda-local symbols, jOOQ `Record.getValue(field)` semantics, standard empty factories and compound field expressions that need separate API/lexical evidence.

## Tests

- full module regression: **393 passed**;
- AT900 foundation: complete;
- system-description: complete;
- data-model: complete;
- conceptual-model quality gate: passed;
- DuckDB materialization: complete.
