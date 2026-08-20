# Test status — iteration 48

## Focused automated tests

- 39 passed, 0 failed.
- Includes Tree-sitter field-flow, evidence navigation, composable profile and external-profile contract tests.

## Real repository performance validation

`gateway-sberid-userinfo-by-ucpid`:

- `java_field_flow_build`: 2.234 s
- full lightweight core analysis: 9.771 s
- field occurrences: 13,993
- field-flow edges: 12,033

The prior implementation did not complete within the user's 900 s runner timeout.

## Semantic parity validation

`gw-sberid-update-phone-flags` old 0.41.0 vs new 0.41.1:

- occurrences: 4,029 in both
- edges: 3,084 in both
- canonical occurrence JSON SHA-256 identical
- canonical edge JSON SHA-256 identical

## Not run

Full platform regression was not run for this bounded core-only performance fix.
