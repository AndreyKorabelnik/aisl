# knowledge-layer-core 0.59.14

Adds generic schema-aware composition for ambiguous unqualified SQL columns. KLC resolves a column only when one observed relation contract can supply it; if other joined relations are opaque, the candidate is deliberately not traversed into end-to-end lineage. Only a unique owner across complete observed contracts is materialized as derived lineage. No SQL parser heuristics, fuzzy name matching, or UCP-specific rules were added.
