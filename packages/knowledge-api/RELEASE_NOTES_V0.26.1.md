# Knowledge API 0.26.1

## Legacy Cleanup Block 1

- Removed `task_suite_profile_semantics` and `legacy_fallback` from the current `knowledge_execution_result/v1` publication schema/policy checks.
- Publication still requires completed execution, valid fingerprints, deterministic execution order, completed nodes, supported capability publication, and `dual_write="not_supported"`.
- No compatibility reader/default for old execution results was added.
- Historical validation snapshots remain unchanged.
