# Test status — code-analyzer-core 0.43.23

## Scope

Targeted validation only. This iteration adds a read-only source-grounded sufficiency assessment and CLI export. Repository scanning, Foundation construction, analyzer execution and `code_conceptual_model/v2` runtime are unchanged.

## Completed checks

- Targeted source tests: 39 passed.
  - Conceptual Model Evidence Sufficiency: 9 passed.
  - Core Analysis Catalog: 5 passed.
  - Core Target Analysis Contracts: 6 passed.
  - Existing conceptual-model prepared artifact: passed.
  - Effective entity fields/associations and inheritance detail: passed.
  - Package version and lightweight CLI: passed.
- Local Tree-sitter wheels were used for Java parser tests because the base Python environment did not provide those optional native packages.
- Real contract generation from all 14 built-in profiles and the current materializer source: passed.
- Source definition probes: passed.
- Observed materializer inventory:
  - 36 fact types;
  - 6 DB schema sections;
  - 10 conceptual-model migration sections;
  - 17 legacy bundle sections excluded from the first migration.
- Python `compileall`: passed.
- Source-tree manifest verification: passed (437 entries before final status refresh).
- Clean self-contained provisional ZIP: 23 passed.
- Clean ZIP CLI export and JSON/Markdown byte parity: passed.
- ZIP integrity: passed.

## Full regression

Not run. No analysis runtime path changed.

## Known limitations

- The assessment is read-only and does not publish typed evidence at runtime.
- KLC `conceptual-data-model` contract still carries the previous fixed required-input assumption until the next KLC iteration.
- Generic normalized fact files remain capped and cannot serve as complete typed cross-module evidence.
- Current dependent `effective_entity_field` and `effective_entity_association` facts still exist in Core runtime.
- The old `code_conceptual_model/v2` umbrella artifact and task-based KLC route remain unchanged.
