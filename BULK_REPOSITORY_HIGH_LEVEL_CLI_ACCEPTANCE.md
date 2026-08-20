# Acceptance — Bulk Repository High-Level CLI

Date: 2026-08-14

## Local Bitbucket-compatible end-to-end smoke

A local HTTP fixture exposed a Bitbucket Data Center compatible `/rest/api/latest/projects/ABC/repos` response for two real git repositories. The user-facing command path was executed with the real framework components:

```text
knowledge-control-plane run
  → official build-repository-inventory-v1 scenario
  → official repository-inventory-v1 profile
  → Runner repository-batch-run
  → Bitbucket-compatible repository discovery
  → temporary git clone
  → Core evidence production
  → KLC repository-inventory materialization
  → per-repository persisted result
  → checkout cleanup
```

Result:
- repository_count: 2
- repositories_completed: 2
- repositories_failed: 0
- execution_mode: sequential
- max_concurrent_checkouts: 1
- persistent_repository_checkout_count: 0
- every repository result: `temporary_checkout_removed=true`
- no `.git` directory or `repository-slot` remained under the runtime root after completion

The first attempt in the session reached Core but could not import `tree_sitter` from the ambient Python environment. The framework code was not changed for this. The supplied dependency wheels (`tree_sitter`, `tree_sitter_java`, `sqlglot`, `duckdb`) were installed into a temporary test-only target, after which the same end-to-end smoke passed.

## Remaining acceptance

The only unverified operational boundary is the user's actual corporate Bitbucket Data Center endpoint, authentication/TLS configuration and large-project behavior. Start with `--repository-limit 3`, then remove the limit after inspecting cleanup and per-repository results.
