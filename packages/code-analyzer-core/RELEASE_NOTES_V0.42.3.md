# Release notes — code-analyzer-core 0.42.3

Version 0.42.3 fixes SQL comment normalization so comment markers inside string literals and quoted identifiers are preserved.

## Changes

- Added lexer-aware SQL comment stripping.
- Real `-- ...` and `/* ... */` comments are replaced with spaces while line offsets remain stable.
- Comment markers inside single-quoted strings, double-quoted identifiers, backtick identifiers, and dollar-quoted text are retained.
- Replaced the previous regex-based stripping in `_normalize_sql_for_profile`.
- Bumped the SQL profile implementation version to `1.4`.

## Real repository effect

`epk_persdata_mapping.sql` previously became invalid because the literal comparison `trim(doc_full) <> '--'` was truncated as a line comment. It now produces both expected business relations:

- `custom_b2c_profile_fl.epk_client_doc`;
- `custom_b2c_profile_fl.epk_client`.

On the unchanged 30-file SQL Source Inventory quality fixture:

- relation precision: 1.0000;
- relation recall: 0.9080, up from 0.8957;
- classification accuracy: 1.0000;
- field precision/recall/role accuracy: 1.0000;
- passed files: 29 of 30.

The only remaining failed case is the separately diagnosed silent AST truncation in `epk_client.sql`.
