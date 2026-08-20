# FI-001a — Core generic structured member evidence

## Version
- code-analyzer-core: 0.44.23a4 -> 0.44.23a5

## Added
- `structured-file-shape-evidence/v1` registered in the generic Core Evidence Runtime.
- Bounded JSON/YAML structural observation over all repository files with supported syntax.
- Exact source member/path/content SHA provenance.
- Structure and variant signatures.
- Bounded path/type observations, boolean/null/empty state sketch and array cardinality sketch.
- Explicit parse/size-limit diagnostics.

## Evidence boundary
Core does NOT publish family membership, dominant/rare classification, concepts, business meaning or arbitrary scalar values.

## Tests
- targeted FI-001a + repository frontier + Core evidence catalog: 13/13 PASS
- compileall/import: PASS
- full regression: NOT RUN

## Next
FI-001b in KLC: deterministic structural families, family -> exact members, variant descriptors and provenance.
