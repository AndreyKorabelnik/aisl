# AISL multi-repository observed publication — change report

Date: 2026-08-17
Status: COMPLETE

## Problem

A workspace containing two repositories legitimately produced two `java-type-structure-evidence` artifacts. Knowledge API 0.37.0 assigned both to `core:java-type-structure-evidence`, so revision publication failed with `observed_product_slot_ambiguous`.

## Root cause

Observed `product_slot_id` represented only `artifact_kind`, while copy-on-write identity must distinguish stable source repository identity as well.

## Generic fix

Knowledge API 0.37.1 owns one canonical observed slot builder:

```text
core:<stable source identity>:<artifact kind>
```

The source snapshot fingerprint/revision is deliberately excluded because it changes when repository content changes. A later revision of one repository therefore replaces only that repository's observed product and retains other repository products.

The one-product-per-slot invariant remains strict; a true duplicate for the same source + artifact kind is still rejected.

No Core, Runner or KLC semantic producer was changed. No adapter, dual-read, dual-write or legacy slot compatibility path was added.

## Packaging correction

The stale `knowledge-api` exact dependency `prepared-knowledge-runtime==0.1.0.post8` was replaced with `prepared-knowledge-runtime>=0.1.0,<0.2.0`. Exact canonical versions remain recorded in the release/recovery manifest.
