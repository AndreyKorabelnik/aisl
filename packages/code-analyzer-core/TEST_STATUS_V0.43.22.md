# Test status — code-analyzer-core 0.43.22

## Scope

Targeted validation only. The iteration adds read-only target contract definitions, current-state assessment and CLI export. Repository analysis, Foundation construction, analyzer execution and output materialization are unchanged.

## Completed checks

- Targeted source tests: 21 passed.
  - Core Target Analysis Contracts: 6 passed.
  - Core Analysis Catalog: 5 passed.
  - External profile loading and profile composition: 7 passed.
  - Lightweight CLI without native analyzer imports: 2 passed.
  - Package version consistency: 1 passed.
- Real contract generation from all 14 built-in profiles and 48 stage definitions: passed.
- Expected current-state diagnosis:
  - 1 Foundation violation;
  - 6 observed public stage dependencies;
  - 3 shared `AnalysisResult` readers;
  - 4 knowledge materializations still inside Core;
  - 5 technical packaging stages.
- Python `compileall`: pending final packaging check.
- Source-tree manifest verification: pending final packaging check.
- Clean self-contained ZIP tests: pending final packaging check.

## Full regression

Not run. No analysis runtime path changed.

## Known limitations

- Contracts are descriptive and not yet enforced by runtime execution.
- Current Foundation still contains `java_system_interaction_enrichment`.
- Current public stages can still read shared `AnalysisResult` or depend on prior stage output.
- Core still produces four knowledge materializations.
- KLC materialization and Runner execution-result contracts are only declared as required external contracts; they are not implemented in this Core release.
