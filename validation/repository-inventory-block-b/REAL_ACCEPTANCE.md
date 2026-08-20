# Repository Inventory — Block B real acceptance

Status: **BLOCK_B_CHECKPOINT_COMPLETE_WITH_KNOWN_GAPS**. Block C has not started.

## Observed facts

- SQL datamart: official Core `repository-structure-evidence/v1` completed; `sql-analysis/v1` completed with `partial` coverage because the official SQL analyzer reported unsupported/partially parsed syntax. Runtime completion: ~18.25 s.
- SQL repository-structure refresh after terminology finalization: 491 files, 12 extension families, ~0.052 s.
- SQL KLC `repository-inventory`: 31 structural families, 29 novelty candidates, concepts `data_model`, `data_flow`, `workflow`, 19 unclassified candidates, ~1.304 s.
- UCP TSA repository structure: 490 files, 8 extension families, ~0.066 s.
- UCP TSA structure-only KLC inventory: no concepts asserted, 5 unclassified candidates, ~1.011 s.
- Attempting official UCP `reference-data` evidence was stopped at the 300 s acceptance bound after it entered a broader Java pipeline. This run is **not PASS** and no reference-data parity is claimed.

## Structural comparison with standalone 0.1.0

### SQL datamart

- Root file count: **491 = 491**.
- Extension distribution: **exact match** after normalizing standalone `<noext>` to Core `<none>`.
- Standalone concepts: `data_model`, `data_flow`.
- Official-evidence Inventory: `data_model`, `data_flow`, `workflow`.
- `workflow` is an expanded-coverage inference, not a guess: basis is official `sql_workflow_binding` with 3142 records; confidence remains `probable_inference` and claim boundary explicitly denies exact runtime/business-process semantics.
- Structural-family counts are intentionally not count-parity (`168` standalone vs `31` official): standalone families are created by its own JSON/Java/SQL/config/tabular parsers; the integrated product creates families only from official Core evidence sections/fact shards plus file-extension frontier.

### UCP TSA

- Root file count: **490 = 490**.
- Extension distribution: **exact match** after `<noext>` normalization.
- Standalone detects `reference_data`; the integrated structure-only run does **not** repeat that claim because official `reference-data-evidence` was not available. It emits `repository_inventory_concept_unresolved`.
- Therefore reference-data concept parity is **unresolved/gap**, not failure and not PASS.

## Important semantic correction made during acceptance

The new Core contract does not call files/extensions generally “unsupported”. It publishes `analyzer_eligible` / `outside_analyzer_frontier`. This is narrower and observed: it states only whether the file belongs to the current Core analyzer input frontier.

## Evaluation before Block C

Block A/B architecture is validated strongly enough to stop and assess: universal file composition is exact on two real repositories; SQL concept discovery works from official evidence without source re-parsing; missing evidence remains visible as unresolved. The main remaining quality question is whether generic JSON/config/tabular structural primitives should later be added to Core. That is parked until a concrete consumer/acceptance requires them.
