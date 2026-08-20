# code-analyzer-core 0.44.9

## Purpose
Preserve repeated DSL variable-binding occurrences even when an assignment is preceded by a SQL-style comment.

## Change
- Leading comments are removed only for assignment recognition; literal/inline content is preserved.
- Repeated `let` assignments remain separate occurrence-based facts with their own source position and ID.

## Real validation
For `prep_stg_epk_client_birthplace.sql`, `prep_src_table` now publishes all three observed values:
- `stg_epk_client_birthplace_snp`
- `stg_epk_client_birthplace_hist`
- `stg_epk_client_birthplace_bv`

Targeted tests: 17/17 passed. `compileall`: passed.
