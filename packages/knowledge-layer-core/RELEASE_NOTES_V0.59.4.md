# knowledge-layer-core 0.59.4

Performance fix for typed repository value-flow materialization.

`value_flow_knowledge_builder` now ingests evidence records and materializes the graph inside one DuckDB transaction. This changes no value-flow semantics or contracts; it removes per-row commit overhead observed on the four real HTTP applications.
