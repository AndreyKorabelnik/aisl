# Release notes — code-analyzer-core 0.42.1

Iteration 58 replaces the legacy regex-level JOIN evidence with a canonical scoped AST JOIN graph.

## Changes

- Added canonical `sql_join_edge` facts, one fact per JOIN clause in a SELECT scope.
- Added deterministic JOIN type extraction for inner, left, right, full, cross, semi, anti, and natural variants supported by SQLGlot.
- Added condition classification for `ON`, `USING`, `CROSS`, and `NATURAL` joins.
- JOIN sides are bound to scoped `sql_relation` facts rather than file-global aliases.
- Simple column comparisons are emitted as typed `column_pairs` with:
  - left and right relation/column identities;
  - operator;
  - predicate role (`equality_key` or `range_or_temporal`);
  - per-pair resolution status.
- Expression-based relationships such as `substring(coalesce(a.x, a.y), ...) = b.key` are emitted as `expression_links` without inventing a single-column key pair.
- Predicate operand order is canonicalized to JOIN rowsets, so `b.id = a.id` still records the existing left rowset on the left and the newly joined relation on the right.
- Additional predicates are separated from cross-relation links.
- Range and temporal predicates are retained independently.
- `USING` after a multi-relation left rowset remains partial instead of producing false base-table pairs.
- Added `resolution_status`, localized `resolution_reasons`, and `physical_join_confirmed`.
- Added JOIN artifacts to full, compact, fact-type, navigation, package-manifest, run-count, and evidence-capability outputs.
- Removed the parallel legacy `source_join_evidence` fact and capability.
- Migrated `source_key_candidate` and mart load-pattern join keys to canonical `sql_join_edge.column_pairs`.
- SQL profile schema version advanced from `1.1` to `1.2`.
- Package and runtime versions are synchronized at `0.42.1`.

## Compatibility

No compatibility adapter is provided. `sql_join_edge` is the only canonical SQL JOIN contract. The former `source_join_evidence` JSON/fact type is no longer published.
