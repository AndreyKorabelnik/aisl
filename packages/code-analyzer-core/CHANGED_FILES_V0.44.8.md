# code-analyzer-core 0.44.8

## Purpose
Publish generic structured script-call evidence needed to compose SQL materialization paths without assigning datamart-specific semantics in Core.

## Changes
- Added canonical `sql_script_call` facts.
- Captures call symbol, named arguments, positional arguments, referenced placeholders and provenance.
- No hardcoded knowledge of `runAndSaveSqlHdfs` or UCP/datamart table names.

## Validation
- Targeted Core tests: 16/16 passed.
- Real datamart analysis: 412 structured script calls observed.
- `compileall`: passed.

## Known limitation
Semantic interpretation of script calls belongs to KLC; Core intentionally publishes syntax/evidence only.
