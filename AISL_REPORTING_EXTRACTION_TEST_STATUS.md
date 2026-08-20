# AISL Reporting Extraction Test Status

Date: 2026-08-17

## PASS

- knowledge-control-plane full package suite: 95/95 PASS.
- knowledge-api extraction/publication/lifecycle targeted subset: 38/38 PASS.
- aisl-reporting isolated suite: 93/93 PASS.
- actual Knowledge API → isolated aisl-reporting integration smoke: PASS.
- compileall for modified framework modules and isolated consumer: PASS.
- generated KCP and Knowledge API OpenAPI documents refreshed and contract-current tests pass.

## Broad suite note

A broad Knowledge API suite attempt before the final generated OpenAPI refresh did not complete within the 120 second command limit and therefore is not reported as PASS. The extraction-specific and publication/lifecycle subset was rerun after all fixes and passed 38/38. No full framework regression was run.
