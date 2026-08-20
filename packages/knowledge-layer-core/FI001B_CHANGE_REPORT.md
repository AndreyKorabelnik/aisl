# FI-001b — Repository Inventory structural family membership

## Version
- knowledge-layer-core: 0.61.0a25 -> 0.61.0a26

## Change
- Repository Inventory consumes optional official `structured-file-shape-evidence/v1` with `production_policy=existing_only`.
- KLC derives deterministic structural families from official member observations.
- Publishes exact family -> source member membership, structure/variant signatures, dominant/rare structural roles, minority state observations, cardinality extremes and provenance.
- Adds typed DuckDB relation `repository_inventory_structural_member`.
- Adds actual revision capability `common.repository-structural-members` only when structured member evidence was evaluated.
- No source repository scan is performed by KLC; no PLP-specific rule or business semantic inference was added.

## Targeted verification
- repository inventory/member tests + materialization contract tests: 13/13 PASS
- compile/import: PASS
- full regression: NOT RUN

## Next
Generic Structural Member Selection acceptance: Core structured evidence -> Repository Inventory -> hide/remove source repo -> select dominant/rare/minority/cardinality representatives from Prepared Knowledge only.
