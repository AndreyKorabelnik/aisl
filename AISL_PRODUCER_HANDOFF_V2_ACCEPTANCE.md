# AISL producer handoff v2 — acceptance

Date: 2026-08-15

## PASS

- Active Runner/API/KCP path contains no `knowledge_execution_result/v1` reader or writer.
- Runner unit/contract tests not requiring DuckDB: 13 PASS.
- Dedicated prior-revision dependency projection and unresolved/unused registry tests: PASS (included above).
- Knowledge API publication + runtime contract + OpenAPI + Runner/API schema parity: 28 PASS.
- Dedicated Knowledge API prior-revision dependency acceptance/rejection: PASS (included above).
- Knowledge Control Plane execution/publication tests: 31 PASS.
- `knowledge_execution_result_v2.schema.json` is identical at Runner/API contract boundaries: PASS.

## Environment-limited / not claimed PASS

Six Runner materialization-path tests require DuckDB. In the available Python environment they fail before exercising the changed handoff because `duckdb` is not installed (`DuckDB runtime is unavailable`). These tests are not reported as PASS or functional failures of v2.

Canonical Core catalog regeneration also cannot run here because `tree_sitter` is unavailable. The unchanged KCP planning bundle was therefore not regenerated or hand-edited.

## Required deployment pairing

Runner 0.10.25, Knowledge API 0.30.8 and Knowledge Control Plane 1.2.0a21 must be updated together for new publication runs. The active path intentionally has no v1 compatibility reader.

Existing published AISL/Prepared Knowledge revisions remain readable; no KnowledgeProduct/Prepared Knowledge rebuild is required by this handoff change.
