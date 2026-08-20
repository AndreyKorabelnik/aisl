# Real validation — system interactions richness — Reporting 0.17.7

Input: real four-repository workspace materialized with KLC 0.59.32.

Observed result:
- 3 business interaction records;
- 5 selected representative journeys;
- 14 unresolved/ambiguous outbound operations in the dedicated outbound section;
- both `/giveSberProfileId` outbound observations remain unresolved and visible;
- 22 unmatched inbound technical operations in the dedicated inbound section;
- among the three target-provider repositories, the only unmatched inbound operation is `gateway-sberid-userinfo-by-ucpid POST /v5`;
- duplicate route/controller evidence for matched `/updatePhoneFlags` and `/updateOrCreate` is not falsely listed as unmatched;
- 15 concrete owner questions;
- dataset schema validation PASS, dangling evidence IDs 0.

Response-contract diagnostic:
- no current interaction has sufficiently rich bilateral response-field evidence for deterministic response field correspondence;
- userinfo: source response payload type is observed but its local contract signature is unavailable; target has response candidates;
- update/create: source response signature is rich, target response signature is unavailable;
- phone flags: response evidence is incomplete on both sides.

Therefore response-field matching remains an explicit P1 evidence gap rather than an inferred mapping.
