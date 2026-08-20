# knowledge-layer-core 0.39.0

## Indexed authority-aware HTTP topology matching

- Added canonical `repository_interaction_boundary` inventory for normalized HTTP boundaries.
- Preserved normalized paths, authorities/hostnames, service identities, base-URL property identities and request contract fingerprints.
- Replaced per-outbound full inbound-route scanning with indexed lookup buckets.
- Added authority/service-identity-first matching and explicit match diagnostics.
- Same HTTP method/path across multiple services is now ambiguous unless stronger address or contract evidence selects one target.
- Unique route-only matches remain `probable`; address-backed matches are `confirmed`.
- Added query and evidence-tool access to normalized repository boundaries.
- Existing strict/extended island materialization now consumes the improved interaction edges unchanged.

No compatibility adapters or legacy matcher are retained.
