# Knowledge API 0.30.3

- Adds read-only Portfolio Inventory aggregation over published Repository Inventory revisions.
- Aggregates the latest published passport per `repo_id` inside each system with provenance to repository/revision.
- Adds system filtering/facets and portfolio interaction observations without persistent dual-write index or new analysis.
- Unresolved peers remain unresolved; exact system-id membership is reported without alias guessing.
