# code-analyzer-core 0.41.1

Emergency performance fix for `java_field_flow_build`.

- Memoizes Tree-sitter expression processing by method, AST byte range and semantic role.
- Prevents re-entry of the same recovered AST expression.
- Replaces linear duplicate lookup for object-field occurrences with an indexed set while preserving deterministic list order.
- Publishes expression memoization and duplicate-registration diagnostics.
- Does not change the canonical field occurrence or field-flow edge contracts.

Real validation on `gateway-sberid-userinfo-by-ucpid`:

- before: did not finish within the runner 900 second task timeout;
- after: `java_field_flow_build` 2.234 seconds; full lightweight core profile 9.771 seconds;
- output: 13,993 field occurrences and 12,033 field-flow edges.

Semantic parity validation on `gw-sberid-update-phone-flags`:

- old and new occurrence catalogs: identical SHA-256;
- old and new edge catalogs: identical SHA-256;
- 4,029 occurrences and 3,084 edges in both versions.
