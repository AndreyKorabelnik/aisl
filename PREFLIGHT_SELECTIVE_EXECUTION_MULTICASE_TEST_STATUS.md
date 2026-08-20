# Test Status — Preflight Selective Execution Block F

Date: 2026-08-16  
Status: **PASS**

## New Block F acceptance

Fresh official KCP → Runner → Core → KLC → Knowledge API publication was executed for baseline and selective paths on four real repository classes.

- gateway baseline: PASS
- gateway selective: PASS
- datamart baseline: PASS
- datamart selective: PASS
- insurance baseline: PASS
- insurance selective: PASS
- UCP data model baseline: PASS
- UCP data model selective: PASS

Machine multi-case acceptance: **PASS**; all global acceptance assertions are true.

## Semantic / structural comparison

All four cases pass the checked invariants for positive concepts, composition, detected concepts, root/extension structure, structural members, structured shapes, novelty, unknown primitives, unclassified candidates, and preflight evaluation phase.

## Runtime regression provenance

Block F changes no runtime package bytes. Package byte identity against the released Block E canonical is independently recorded for all 9 runtime packages. Therefore the authoritative Block E regression remains applicable to the exact same package trees:

- Core: 610/610 PASS
- Runner: 113/113 PASS
- KLC: 256 PASS / 8 SKIPPED
- Prepared Runtime: 10/10 PASS
- Knowledge API: 118/118 PASS
- KCP: 95/95 PASS

Block F does not claim an additional redundant full regression over unchanged package bytes; its new release gate is the four-case real publication and semantic/structural comparison.

## Non-results

- Single-run timing observations are not a performance benchmark.
- No timeout or partial suite is counted as PASS.

## Release packaging gate

- runtime package byte identity vs Block E: 9/9 PASS;
- package source-tree manifests: 9/9 PASS;
- compileall over staged package trees: PASS;
- root content manifest coverage after Block F documentation/validation: verified;
- final ZIP is required to pass independent unpacked content-manifest, package-manifest, source-manifest, import/version, pinned-bundle, and machine-acceptance checks before its SHA-256 is declared final.
