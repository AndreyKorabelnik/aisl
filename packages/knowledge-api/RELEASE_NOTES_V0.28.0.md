# knowledge-api 0.28.0

Knowledge API no longer owns DuckDB schema knowledge for effective data model, cross-artifact lineage, or observed-storage usage. These read semantics now live in `knowledge-layer-core`; the API remains the HTTP/publication projection boundary. Existing HTTP contracts are preserved.
