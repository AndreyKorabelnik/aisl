# Benchmark Miner handoff — FI-001 completed

Date: 2026-08-13
Framework status: FI-001 complete; FI-002 parked.
Target Miner baseline: `benchmark-miner 0.8.0` official-inventory Level-1.

## Decision
Miner must remain a consumer of official Prepared Knowledge. Do **not** restore standalone repository scanning/parsing, JSON/YAML shape discovery, family grouping, or fallback adapters in Miner.

## New official input
Repository Inventory `repository-inventory/v2` now optionally contains:

```text
structural_report.structural_members
  evaluation_status
  families[]
    family_id
    family_kind = structured_file_shape
    syntax
    occurrence_count
    shape_count
    dominant_structure_signature
    dominant_structure_count
    dominant_structure_rate
    consensus_path_types[]
    member_ids[]
    claim_boundary
  members[]
    family_id
    member_id
    repository_relative_path
    content_identity.sha256
    syntax
    parse_status
    structure_signature
    variant_signature
    structure_family_occurrence_count
    structural_size
    variant_roles[]
    minority_states[]
    cardinality_extremes[]
    observation_truncated
    provenance
```

`variant_roles` currently includes generic derived roles such as:
- `dominant_structure`
- `rare_structure`
- `minority_state`
- `cardinality_extreme`
- `partial_observation`

No role asserts business semantics.

## Production boundary
Default Repository Inventory remains cheap. Its materialization contract declares:

```text
structured-file-shape-evidence/v1 -> optional, production_policy=existing_only
```

For source-level Unknown Parser package production, orchestration must request the **official Core** `structured-file-shape-evidence/v1` first, then build the ordinary Repository Inventory from that evidence. Miner itself must not parse source.

Core generic request identity:

```text
artifact_kind = structured-file-shape-evidence
schema_version = structured-file-shape-evidence/v1
```

The existing generic Core/Runner evidence execution boundary must be used; do not add a Miner-specific parser or Core adapter.

## Acceptance result available in handoff package
The sample enriched `repository_inventory.json` was materialized only after its source repository had been deleted. It demonstrates exact selection of:
- dominant member;
- rare missing/empty-container structural variants;
- minority `deleted=true` member;
- min/max cardinality members.

Use this sample for Miner contract development without opening any repository.

## Requested Miner changes
1. Keep existing Level-1 `Fingerprint -> Clustering -> Repository/Family Representative Selection` behavior unchanged unless FI-001 data is explicitly used.
2. Re-enable/develop source-level representative selection **from `structural_members` only**.
3. Select exact source member refs needed by case production using `repository_relative_path + content_identity + member_id`.
4. Preserve provenance and role/basis in the produced candidate package.
5. If `evaluation_status=not_evaluated`, keep source-level package production parked/blocked; do not fall back to source scanning.
6. If member observations are truncated/partial, preserve that diagnostic and do not claim complete variant coverage.
7. Do not require historical standalone field-name/count parity.

## Still blocked / FI-002
Generic unknown-family cross-artifact correspondence is **not** implemented yet. Do not rebuild it in Miner. Fields such as old `cross_artifact_links` / identifier-overlap rates remain parked until framework FI-002.

## Framework versions for this handoff
- code-analyzer-core `0.44.23a5`
- knowledge-layer-core `0.61.0a26`
- static-analysis-runner `0.10.23` unchanged
- knowledge-control-plane `1.2.0a15` pinned catalog refresh
