# Release notes — code-analyzer-core 0.42.4

Version 0.42.4 prevents semantic placeholders immediately after `SELECT` from silently truncating the SQLGlot AST.

## Changes

- Added context-aware parser rendering for placeholders placed directly after `SELECT`.
- Dynamic optimizer hints or comma-terminated projection fragments are omitted only from the parser view when a static projection follows without an explicit comma.
- The original placeholder remains published as a semantic fact with role `select_modifier_or_projection_fragment`.
- Whole projection-list placeholders before `FROM`, and explicit comma-separated placeholder expressions, remain parser-safe synthetic projections.
- Added a lexical-versus-scoped source coverage check for strong qualified/template relation names.
- A syntactically accepted but incomplete AST now produces a localized `scoped_ast_source_coverage_incomplete` gap instead of being silently treated as complete.
- SQL profile implementation version is now `1.5`.

## Real repository effect

`epk_client.sql` now exposes all 24 expected direct relations instead of only the first 9. The unchanged 30-file SQL Source Inventory fixture now passes all quality gates:

- relation precision: 1.0000;
- relation recall: 1.0000;
- classification accuracy: 1.0000;
- field precision/recall/role accuracy: 1.0000;
- 30 of 30 files passed.
