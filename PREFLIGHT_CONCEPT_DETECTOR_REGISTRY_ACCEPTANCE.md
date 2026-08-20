# Preflight Concept Detector Registry — Block D Acceptance

Date: 2026-08-16
Verdict: PASS

The six existing Repository Inventory concept detectors now have one KLC-owned registry. The registry owns ordered detector definitions, concept ids, claim boundaries, relevant official evidence kinds and detector dispatch.

Semantic parity is proven at two levels:
1. an old-canonical vs new-registry probe covers all six concepts and the SQL/workflow/persistence branch cases and produces byte-identical classification + concept-status JSON;
2. fresh real gateway and SQL-heavy datamart source runs publish successfully and preserve all 12 concept status rows plus all Block C Repository Inventory v3 acceptance counts exactly.

Block D therefore changes ownership/structure only. It does not change observed evidence production, concept inference semantics, discovery semantics or Runner execution selection.

The KCP pinned runtime contract bundle is regenerated from canonical owners for KLC `0.61.0a35`; Knowledge Control Plane is `1.2.0a26`. The bundled Core evidence catalog remains byte-identical because Core contracts are unchanged.
