# ADR-011: Content-addressed stage reuse

## Decision

`knowledge-control-plane` reuses pipeline results by independent stage fingerprints rather than by output
path, repository URL, workspace name or most-recent-job heuristics.

The default policy is `reuse_if_unchanged`. Callers can select `force_rebuild` to bypass reuse.

## Stage boundaries

1. `static_analysis`: source identity, workspace membership, profile digest, runner identity and
   analysis parameters.
2. `knowledge_materialization`: static-analysis fingerprint, runner identity and DuckDB tuning
   parameters.
3. `report_build`: Knowledge Layer fingerprint, report-profile digest, reporting tool identity
   and rendering parameters.

A successful later stage can be reused even when the original job later failed, because cache
records are written immediately after each stage succeeds.

## Repository identity

For Git repositories the fingerprint includes HEAD, a binary diff against HEAD and hashes of
untracked files. For non-Git directories a deterministic tree digest is used while transient
build/cache directories are excluded.

Remote repositories are fingerprinted from the materialized checkout. `force_rebuild` refreshes
that checkout first; a normal reuse run does not perform an implicit network fetch.

## Safety

Missing artifacts turn a cache hit into a cache miss. No output directory is trusted merely
because its name matches a previous run. Reused artifacts are registered against the new job and
retain a source-job provenance record.
