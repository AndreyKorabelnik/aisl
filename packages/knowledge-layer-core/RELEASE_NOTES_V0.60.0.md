# knowledge-layer-core 0.60.0

Prepared Knowledge read-boundary extraction.

- moved canonical read/query contracts and shared read primitives to `prepared-knowledge-runtime 0.1.0`;
- removed the corresponding Python modules from `knowledge_layer_core` (no re-export adapters or dual implementation);
- KLC materialization/builders now depend on the single owner for shared primitives;
- materialization semantics and Prepared Knowledge schemas are unchanged.
