# code-analyzer-core 0.44.14

- SQL projection column usages now retain `projection_expression_path`, a structural AST path from the observed source-column occurrence to the projection output.
- The path records operations such as function calls, array/bracket indexes, casts and aliases without assigning business semantics.
- This lets downstream KLC composition distinguish evidence-backed key/value transformations without reparsing SQL text or relying on table/column naming heuristics.
- `sql-analysis/v1` remains the canonical evidence contract; the added field is part of the existing extensible JSONL fact payload.
