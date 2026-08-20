# Knowledge Layer Core 0.61.0a29

This release makes AISL KnowledgeProduct coverage explicit for the three representative data-model products validated on real UCP/PDM inputs.

## Semantics

- Analysis completion and semantic mapping coverage are separate dimensions.
- A logical/physical mapping run with zero observed mapping records publishes `mapping_coverage_status=no_mapping_evidence`.
- Code-declared product publication preserves source repository partial/complete coverage and model gaps.
- Physical-model publication reports parser-contract coverage and explicitly does not claim business semantic completeness.

No parser, Core evidence producer, or Knowledge API inference was added.

## Validation

- full KLC suite: 247 passed, 8 skipped;
- real UCP + PDM production: 5 KnowledgeProducts;
- official Knowledge API publication: PASS;
- consumer-only exact evidence reads: PASS.
