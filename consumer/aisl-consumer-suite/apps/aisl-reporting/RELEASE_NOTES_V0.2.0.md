# aisl-reporting 0.2.0

`aisl-reporting` now dogfoods the same public `aisl-client` SDK intended for external teams.

The reporting package no longer owns a duplicate HTTP/revision client. It retains only reporting-specific knowledge requirements, artifact selection rules, report datasets and renderers. Active revision resolution is explicit and becomes pinned before report dataset construction.

Backward compatibility with the removed `KnowledgeApiClient` Python export is intentionally not provided.
