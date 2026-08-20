# AISL Coverage Semantics — Acceptance

Date: 2026-08-15

## Automated

- KLC targeted representative tests: 14/14 PASS.
- KLC full regression: 247 PASS, 8 SKIPPED.
- AISL contract: 43/43 PASS.

## Real UCP/PDM

Canonical Runner 0.10.25 + KLC 0.61.0a29 produced five KnowledgeProducts from two real UCP Java repositories plus the real B2C PDM.

Published revision: `rev-97726fa47b2de005da068bd1`.

Observed coverage:

- code-declared: `analysis_status=partial`, 1061/1061 Java files parsed, 31 model gaps, 14 unresolved type refs, 17 unsupported declarations;
- physical: `analysis_status=complete`, 522 tables, 11940 columns, 498 keys, 370 relationships, 0 gaps, plus `does_not_claim_business_semantic_completeness=true`;
- logical/physical mapping: `analysis_status=complete`, `mapping_coverage_status=no_mapping_evidence`, observed/matched mappings 0/0.

Consumer-only universal exact read returned `AbstractParty.serviceStartDate` with source evidence at Java lines 160–162; physical-table exact read returned PDM evidence; Agent SDK request binding PASS.

## Not claimed PASS

The KCP one-shot job lifecycle stalled in this container after the Runner subprocess had already completed. Direct canonical Runner execution and official Knowledge API publication/read passed. KCP one-shot lifecycle is a separate operational investigation.
