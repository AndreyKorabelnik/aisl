# Preflight Contract Block B — Test Status

Date: 2026-08-16
Status: PASS

Completed authoritative results:
- code-analyzer-core: 609/609 PASS (4 completed chunks: 140 + 148 + 158 + 163)
- static-analysis-runner: 108/108 PASS (completed groups only)
- knowledge-layer-core: 252 PASS / 8 SKIPPED (70+71+111; 7+1 skipped)
- knowledge-control-plane: 95/95 PASS
- real gateway KCP one-shot + AISL publication: PASS
- real datamart KCP one-shot + AISL publication: PASS

Discarded/non-authoritative attempts:
- combined cross-package pytest import collision: not counted
- monolithic Runner runs interrupted by wrapper timeout: not counted
- first gateway local wrapper run that produced no Runner CLI output: environment setup failure, not counted
- pre-fix gateway run that exposed the 12-analyzer policy propagation bug: diagnostic evidence, not PASS

Baseline hygiene fixed during the block:
- Runner selectable knowledge type assertions: current catalog is 18, synthetic extension 19.
- Core registered typed evidence analyzer assertion: current catalog is 13, not 11.
- KCP pinned version assertions aligned to Core 0.44.23a6 / Runner 0.10.26 / KLC 0.61.0a33 / KCP 1.2.0a24.
