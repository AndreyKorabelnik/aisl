# knowledge-layer-core 0.53.2

Iteration 110 adds an explicit deterministic hand-off from ranked logical target candidates to the SQL insertion-context resolver.

Each target candidate now contains:

- `recommended_target_relation`;
- `target_relation_recommendation_status`;
- `target_relation_recommendation_reasons`;
- the complete unchanged `target_relation_candidates` list.

A unique observed relation is `confirmed_unique`. Multiple relations are ranked only by observed writes, logical-name identity, concrete relation identity and observed reads. Remaining ties are visible as `probable_tie_break`; alternatives are never discarded.
