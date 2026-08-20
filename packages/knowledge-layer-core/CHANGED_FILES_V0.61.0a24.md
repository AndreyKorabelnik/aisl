# knowledge-layer-core 0.61.0a24 — repository inventory materialization

- Added generic `repository-inventory` materialization over official typed Core evidence only.
- Produces repository composition, Core analyzer coverage frontier, structural families, generic novelty candidates, `UNCLASSIFIED`, concept classifications, diagnostics, and provenance.
- Concept inference keeps confidence/basis/claim-boundary and never re-reads repository source.
- Java/SQL/config/reference parsers from the standalone experimental Inventory were not copied into runtime.
- Added `repository-inventory/v1` DuckDB/JSON prepared knowledge schema and capabilities.
