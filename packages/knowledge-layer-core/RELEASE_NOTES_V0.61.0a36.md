# knowledge-layer-core 0.61.0a36

Repository Inventory concept classification storage is now sparse at structural-family level.

- `concept_status` remains dense for every registered concept and retains the existing inference/coverage semantics.
- `concept_report.classifications` and `repository_inventory_concept_classification` retain only detector/family evaluations whose `source_artifact_kind` is covered by the detector's official `relevant_evidence_kinds` contract.
- Absence of a family-level row means the detector is not applicable to that family evidence kind; it is not a negative concept result.
- Relevant evaluated-but-not-classified rows are preserved.
- No new source scan, parser, analyzer, detector semantic, concept id, or fallback is introduced.
