# knowledge-api 0.14.0

Adds two read-only SQL planning endpoints over already materialized Knowledge Layer facts.

`target-candidates` returns explainably ranked write targets. `attribute-insertion-context`
returns observed SQL scopes where a requested source relation/column can be introduced,
together with target workflow context, existing JOIN/projection facts and diagnostics.

The API preserves all candidates and evidence. Selection and SQL generation remain the
responsibility of Knowledge Assistant or another consumer.
