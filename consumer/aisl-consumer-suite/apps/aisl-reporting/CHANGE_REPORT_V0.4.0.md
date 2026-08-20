# aisl-reporting 0.4.0 — Change Report

Date: 2026-08-18

## Change

Added an explicit `declared-data-model-report/v1` consumer profile for revisions published by `build-data-model-v1`.

The existing `data-model-report/v1` contract remains strict and continues to require `effective-data-model`; no fallback or weaker dual-read path was added.

## Knowledge boundary

Required:
- model kind `code-declared-data-model`
- capability `common.code-declared-data-model`

Optional, consumed only when published:
- `common.model-storage-semantics`
- `common.logical-storage-mapping`

The profile preserves ambiguity, reference-value derivations, gaps, and `physical_join_confirmed=false`. It does not infer a physical SQL/PDM join from a declared type relation.

## Dataset

- complete compact declared-object catalog (bounded only by explicit 20k safety cap; completeness checked against published summary count)
- deterministic bounded detailed object contexts (20), with optional focus-first selection
- declared fields / inheritance / relationships
- optional storage identities and relationship mappings
- explicit coverage and interpretation policy

## Compatibility

No backward-compatibility adapter was introduced. This is a new public report profile.
