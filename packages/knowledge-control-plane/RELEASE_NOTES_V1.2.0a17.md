# Knowledge Control Plane 1.2.0a17

Adds one-command Bitbucket Project repository-batch execution to the existing `knowledge-control-plane run` CLI. The Control Plane resolves the selected Analysis Scenario and built-in repository-scoped Knowledge Profile, uses its packaged Core/Runner/KLC catalogs, and delegates acquisition/execution to Runner `repository-batch-run`.

Normal usage no longer requires users to create `knowledge_profile/v2` JSON or pass catalog paths. The batch remains independent single-repository production: no Core/Runner multi-repository scope and no KLC portfolio assembly are introduced. Runner temporary-checkout cleanup semantics are unchanged.
