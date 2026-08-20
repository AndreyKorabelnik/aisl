# knowledge-api 0.18.1

Fixes SQL query ambiguity when one revision contains both repository SQL knowledge (`knowledge_layer_sql/v2`) and the composed workspace SQL catalog (`workspace-sql-catalog/v1`).

The API now uses an explicit typed-model priority:

1. workspace SQL catalog for workspace-wide queries;
2. repository SQL knowledge only when no workspace catalog is published.

This is deterministic semantic routing. It does not use legacy bundles, dual-write, or hidden fallback. Multiple artifacts of the selected model kind remain a 409 ambiguity error.
