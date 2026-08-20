# FI-001 — Official structural family membership and source-level variant descriptors

Date: 2026-08-13
Status: COMPLETE; FI-002 remains parked.

## Problem
Benchmark Miner 0.8.0 consumes official `repository-inventory/v2`, but source-level Unknown Parser case production could not select exact structural-family members or preserve rare/minority variants without re-reading repository source.

## Architecture

```text
Source repository
    ↓
Core `structured-file-shape-evidence/v1`   (observed, bounded)
    ↓
KLC Repository Inventory                   (derived family membership/variant roles)
    ↓
Prepared `repository-inventory/v2`
    ↓
Benchmark Miner                            (select/reduce only; no source parser)
```

### FI-001a — Core 0.44.23a5
Added optional typed evidence `structured-file-shape-evidence/v1`.

Observed per member:
- exact repository-relative source occurrence and content SHA-256;
- syntax and parse/coverage status;
- structure and variant signatures;
- bounded key-path/type observations;
- boolean/null/empty/non-empty and zero/non-zero state observations;
- bounded array cardinality observations;
- structural-size sketch and provenance.

Core does **not** publish family IDs, dominant/rare roles, concepts or business meaning. Arbitrary scalar values are not exported.

Current syntax coverage is bounded JSON/YAML (`.json`, `.yaml`, `.yml`). Other formats remain explicit future coverage, not guessed.

### FI-001b — KLC 0.61.0a26
Repository Inventory consumes `structured-file-shape-evidence/v1` as `existing_only` enrichment and derives:
- deterministic structural families;
- `family_id -> exact member occurrences`;
- dominant/rare structural roles;
- minority structural-state observations;
- cardinality extrema;
- exact paths/content identity/provenance;
- typed DuckDB relation `repository_inventory_structural_member`.

No KLC source scan or parser was added.

### Default inventory cost policy
`structured-file-shape-evidence` is `existing_only` for the normal Repository Inventory product. Therefore ordinary inventory does not start this source-content analysis by default. A source-level/enriched workflow requests official Core shape evidence explicitly and then reuses the same Repository Inventory materializer.

## Generic acceptance
A sanitized family reproducing the historical parser-fidelity dimensions was used:
- ordinary structural shape;
- missing ordinary container;
- empty container;
- minority `deleted=true`;
- cardinality minimum/maximum.

Core produced official evidence, then the source repository was physically deleted **before KLC materialization**. KLC still produced one family with 8 exact members. A Miner-like consumer selected dominant/rare/minority/cardinality representatives using only Prepared Repository Inventory.

This is **not** a claim of a real industrial PLP application run. It is a generic acceptance based on documented historical PLP failure modes.

## Not changed
- Benchmark Miner source code;
- Runner runtime code;
- Repository Inventory schema identifier (`repository-inventory/v2` remains additive-compatible);
- default heavy/deep inventory policy;
- FI-002 generic cross-artifact correspondence.
