# Handover — Repository Inventory Core-Level Boundary

Date: 2026-08-17
Status: COMPLETE

Repository Inventory v5 is now a Core/evidence-level structural inventory. Runtime KLC concept labels are no longer part of it and the Concept Detector Registry has been deleted.

Canonical semantics:
- observed structure/fingerprints/occurrences/coverage belong in Repository Inventory;
- `unknown_primitive` is framework-owned only when explicit Core analyzer-frontier evidence supports it;
- `structural_salience_score` is local ranking metadata, not novelty;
- novelty requires downstream cross-repository comparison and belongs to Benchmark Miner / consumer logic;
- KLC benchmarks are independently constructed from known-good Core evidence and do not require runtime repository concept detectors.

Do not reintroduce concept labels into Repository Inventory merely for Benchmark organization. Benchmark suite names are not production knowledge objects.

Next product step: adapt Benchmark Miner to consume Core structural phenomena/fingerprints/SourceOccurrence IDs from Repository/Portfolio Inventory, deduplicate/cluster across repositories and select representative occurrence IDs.
