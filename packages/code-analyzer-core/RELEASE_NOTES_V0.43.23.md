# code-analyzer-core 0.43.23 — Conceptual Model Evidence Sufficiency v1

## Added

- Read-only `conceptual_model_evidence_sufficiency/v1` assessment.
- `conceptual-model-evidence-sufficiency` CLI command with deterministic JSON and Markdown output.
- Source-grounded inventory of the current `build_code_conceptual_model` inputs, output sections and fact types.
- Nine-element migration matrix for physical assets, entities, attributes, keys, associations, inheritance, logical-to-physical mappings, domains/clusters and coverage/gaps/provenance.
- Explicit split between the conceptual-data-model core and 17 legacy bundle sections owned by other knowledge types.
- Capability-based KLC input policy: Java type structure or physical schema can independently produce a partial model; persistence, SQL relationship and storage usage evidence enrich it.
- Revision of the previous required-input assumption: converter/builder `java-mapping-evidence` is not used by the current conceptual-model core.
- Guardrail preventing current dependent `effective_entity_field` and `effective_entity_association` facts from becoming permanent cross-module contracts.

## Main conclusion

Baseline parity of the conceptual-data-model core is possible without new language-analysis algorithms. Complete uncapped typed source observations are required. Whole-file parity with `code_conceptual_model/v2` is not a valid migration goal because the legacy artifact also bundles system-description, flow, SQL, reference-data and diagnostic sections.

## Execution impact

None. Repository scanning, profiles, Foundation, analyzer execution and conceptual-model materialization runtime are unchanged.

## Compatibility

No compatibility adapter was added. The new assessment is additive and read-only.
