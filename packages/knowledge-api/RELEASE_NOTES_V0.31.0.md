# Knowledge API 0.31.0 release notes

- Makes AISL durable artifact lifecycle real for published products through a filesystem content-addressed immutable Artifact Store.
- Imports execution results and published observed/derived artifact bytes into AISL-managed storage before revision visibility.
- Adds first observed Core KnowledgeProduct publication for `java-type-structure-evidence/v1`.
- Generalizes product origin, producer, COW slot and exact dependency metadata across Core and KLC products.
- Rejects copy-on-write snapshots retaining products whose exact dependencies are no longer present.
- Removes read dependence on producer-local DuckDB filename/manifest adjacency by using exact published database + manifest artifacts.
- Does not add a second catalog, publisher, Knowledge Layer or compatibility path.
