# Test status — code-analyzer-core 0.44.14

## Automated
- targeted SQL scoped/evidence/catalog regression: **22 passed**
- `compileall`: **OK**

## Real validation status
- full real datamart evidence regeneration is the next step; no claim is made yet for the 0.44.14 real artifact.

## Known limits
- `projection_expression_path` is structural evidence only; Core does not infer storage-key or business semantics.
- downstream KLC must combine it with independent typed key-lineage evidence before claiming a parent-key/value-origin equivalence.
