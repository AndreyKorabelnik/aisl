# Knowledge Control Plane 1.2.0a1

## Scope

Completes the automatic Prepared Knowledge freshness/refresh block with the Control Plane UI on top of the 1.1.0a1 backend checkpoint. No second scheduler, source registry, planner, job engine, producer, materializer, or publication path is introduced.

## Backend carried forward and finalized

- Durable Production Registration: system + compatible Knowledge Profile + selected repositories + optional physical model + refresh policy.
- Immutable Git commit SHA and file SHA-256 source snapshots.
- Freshness is measured against the last successfully published production baseline.
- Production configuration revision participates in freshness, so profile/parameters/source-set/PDM/report changes rebuild even with unchanged Git.
- Refresh jobs acquire job-local pinned Git checkouts and verified file copies before Runner execution.
- Failed/cancelled jobs do not advance the baseline; unavailable or dirty sources remain explicit diagnostics.
- Explicit `force` refresh uses the ordinary job path with `FORCE_REBUILD` rather than a special refresh execution pipeline.
- Production may use any platform or user Knowledge Profile compatible with the selected Scenario source mode. Scenario-specific report projection remains available only for the Scenario default profile.

## UI

- New `Производство Knowledge` / `/productions` surface for Production Registrations.
- Create/edit/delete registration with System, Scenario, platform/user Knowledge Profile, repositories, optional PDM, parameters, enable flag and refresh policy.
- Register local or remote Git sources with explicit tracked ref (`HEAD`, branch or ref).
- Show current observed snapshots versus the last successful snapshots, configuration revision, freshness state, diagnostics, last refresh job and published Prepared Knowledge revision.
- `Проверить` observes freshness without enqueueing a job.
- `Обновить сейчас` explicitly queues a forced rebuild through the same backend FreshnessService/JobManager path.
- `Проверить по расписанию` invokes the same due-production backend operation intended for an external scheduler.
- The UI contains no Git subprocess calls, snapshot fingerprint implementation, source resolver, Runner planner or publication logic.

## Small correctness fix

The existing repository discovery client sent an invalid request body for `discoverRepository(location)`. It now selects the backend-supported local-root or remote-repository request shape without changing backend semantics.

## Scheduler boundary

No scheduler runtime is shipped inside Knowledge Control Plane. Cron, systemd timer, Kubernetes CronJob or a corporate scheduler can call `knowledge-control-plane refresh-check --due` against the already running Control Plane service. This preserves a single RuntimeStore and JobManager owner.

## Known unverified acceptance

- Real Bitbucket network/credential smoke is not executed in this environment.
- Frontend production build is not executed because the local `vue-tsc` and `vite` binaries are unavailable offline. Static frontend contracts and dependency-portability tests are executed separately.
