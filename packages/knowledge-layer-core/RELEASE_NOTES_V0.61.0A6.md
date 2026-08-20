# Knowledge Layer Core 0.61.0a6

S2T final-target partial-contract increment on top of 0.61.0a4.

- Final workflow-target anchoring can preserve a useful column contract when a direct observed workflow/config copy has at least one complete source-producer contract and all complete contracts agree, while sibling producer branches remain contract-incomplete.
- The fallback is local to final target anchoring; global producer traversal remains strict and unchanged.
- Lineage emitted through this fallback is explicitly `partial`, with the partial-contract basis and incomplete sibling producer diagnostics retained.
- Conflicting complete contracts and targets without any complete source contract remain gaps.
- No application/table/Gold-specific rules, new analyzer, new materializer, or API route are introduced.
