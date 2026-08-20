# Release notes — static-analysis-runner 0.9.35

This release makes the HTTP portfolio-topology workflow practical for very large Bitbucket projects.

## Highlights

- Dedicated Core `portfolio-topology` task with no deep-analysis foundation.
- Sequential one-repository-at-a-time clone, analysis, persistent compact publication, and cleanup.
- `--repository-limit N` (`--max-repositories` alias) for controlled 50–100 repository pilots.
- Deterministic prefix selection is recorded in run manifests and summaries.
- Persistent topology shards retain only inbound REST request and outbound HTTP client boundaries required by HTTP Islands v1.
- KLC 0.53.7 batch ingestion handles 1,600 AT900-shaped compact results in tens of seconds.

## Compatibility

- Code Analyzer Core 0.43.19 is required for `repository-portfolio-topology.yaml`.
- Knowledge Layer Core 0.53.7 is required for the canonical `portfolio-topology` task.
- Existing non-topology suites continue to use their shared foundation unchanged.
