# Repository Inventory v3 — real parity acceptance

Date: 2026-08-16

## Inputs

The v3 materializations reuse the exact official Core evidence artifacts produced by Block B for:

- `gateway-sberid-userinfo-by-ucpid`;
- `datamart_profile_fl`.

No repository source re-scan was performed for this acceptance.

## Acceptance

- all six existing concept rows preserve `status`, `confidence`, `concept_score`, and `top_family_id` exactly for both repositories;
- both bounded evidence sets are classified as `evaluation.phase = preflight`;
- discovery is a separate axis (`unknown_primitive`, `structural_novelty`, etc.);
- current generic novelty is **not** promoted to `unclassified_concept_candidate`; count remains zero;
- coverage gaps are first-class Repository Inventory v3 rows;
- a separate targeted KLC test proves that adding official `existing_only` deep evidence produces `evaluation.phase = post_analysis`.

This block does not move concept detectors into a registry and does not make Runner analyzer selection depend on preflight inference.
