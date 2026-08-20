# prepared-knowledge-runtime 0.1.0

Initial extraction of the canonical Prepared Knowledge read boundary from `knowledge-layer-core`.

- owns read-only DuckDB query services and typed consumer contracts;
- contains no Core/Runner/KLC materialization execution path;
- `KnowledgeLayerQuery` opens Prepared Knowledge databases read-only;
- is the runtime dependency of Knowledge API 0.30.0;
- is also used by KLC 0.60.0 for shared deterministic contracts/primitives, avoiding duplicate implementations.
