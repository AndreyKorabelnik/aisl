# knowledge-layer-core 0.59.22

## Change

Completes generic value-flow handling for aliased/windowed workflow target lineage and strict intermediate frontiers in `sql-target-source-mapping/v1`.

- workflow target traversal follows the observed source-column name across CTE aliases/renames;
- value lineage follows only SQL usages classified as `projection`; window partition/order and other control dependencies remain available in typed SQL evidence but are not promoted to value origins;
- the same rule is enforced recursively inside `SqlProducerColumnTraversal`, preventing control dependencies from reappearing through producer queries;
- physical relations classified as `internal_intermediate` or `external_or_shared_intermediate` are not silently promoted to ultimate sources when no producer is observed: the raw frontier is preserved and `intermediate_producer_unresolved` is published instead. Semantic role never selects or guesses a producer.

## Real `epk_client` validation

Using full real `datamart_profile_fl` SQL knowledge and real TSA model-storage semantics:

- generic `sql-target-source-mapping` runtime completed in ~16 s;
- `epk_id`: 2 resolved value origins (`Individual.id`, current/history), no target gaps;
- `last_name`: 2 resolved `IndividualName.surname` origins;
- `active_flag`: 2 resolved `Individual.endDate` origins;
- `row_actual_from` / `row_actual_to`: local alias/window gaps eliminated; control `epk_id` no longer appears as a value origin; each has 52 evidence-backed external value origins, 0 staging value sources, plus explicit `intermediate_producer_unresolved` frontiers where producer evidence is missing.

The manual Gold lists only `Individual.startDate/versionStartDate` for these technical validity fields. Runtime does not force that interpretation: the real SQL constructs final validity ranges from boundaries of multiple staging families. This remains an explicit Gold-semantic/evidence investigation, not a hardcoded normalization.
