# code-analyzer-core 0.43.22 — Core Target Analysis Contracts v1

## Added

- Read-only `core_target_analysis_contracts/v1` export.
- Core-owned target contracts:
  - `core_foundation_contract/v1`;
  - `core_evidence_analyzer_contract/v1`;
  - `core_evidence_artifact_contract/v1`.
- `target-contracts` CLI command with deterministic JSON and optional Markdown output.
- Current-state assessment of Foundation violations, public stage dependencies, shared `AnalysisResult` reads and knowledge materializations still located in Core.
- Explicit future boundary: evidence semantics are selected by `artifact_kind + schema_version`, not by `task_id`.

## Execution impact

None. Profile resolution, Foundation runtime, analyzers and output materialization are unchanged.

## Compatibility

No backward-compatibility adapter was added. The new contract is additive and read-only.
