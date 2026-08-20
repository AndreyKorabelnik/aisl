# knowledge-layer-core 0.61.0a37

Adds generic Repository Inventory source provenance localization without changing Core evidence or concept semantics.

- Repository Inventory schema advances to `repository-inventory/v4`.
- Adds normalized `repository_inventory_source_occurrence` and `repository_inventory_object_occurrence` relations.
- SourceOccurrence preserves repository-relative path, observed line range when available, localization kind, file SHA from official repository structure, and provenance basis.
- Adds links for structural families/members, discovery candidates, concept classifications, and source-localizable coverage gaps.
- Uses explicit official evidence shapes only; no recursive provenance guessing and no source parser/scanner in KLC.
- SQL localization reads official Core JSONL fact shards; Java uses published source_ref/source_refs; structured file shapes remain honest file-level provenance.
- Coverage gaps now carry explicit `localization_scope_kind` / `localization_status`; source links are created only from related family provenance or explicit diagnostic `source_ref/source_refs`.
- Analysis-level/evidence-artifact gaps remain non-source-localized rather than being assigned guessed files/spans.
