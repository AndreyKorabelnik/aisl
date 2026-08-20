# ADR-002: separate generic orchestration API from data-model API

Status: accepted  
Date: 2026-07-28

## Decision

Keep `/api/v1/systems/**` as the stable data-model surface and introduce generic orchestration resources for UI operations.

## Consequences

- Existing data-model consumers remain unaffected.
- Jobs, logs, artifacts, repositories, workspaces, profiles, configuration, and conversations receive explicit resource contracts.
- The legacy route set is not preserved verbatim; its capabilities are migrated to the new canonical contract.
