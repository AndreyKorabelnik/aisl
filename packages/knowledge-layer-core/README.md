# knowledge-layer-core 0.59.6

`knowledge-layer-core` (KLC) deterministically materializes typed knowledge artifacts from Core evidence and previously materialized knowledge. DuckDB is the storage format; the materialization registry and contracts are owned by KLC.

## Runtime boundary

```text
typed evidence artifacts + typed knowledge dependencies
→ knowledge_materialization_request/v1
→ KLC-owned materialization registry
→ knowledge_materialization_execution_result/v1
→ immutable typed knowledge artifact
```

Runner schedules the graph but does not contain knowledge-specific handlers. KLC validates typed identities, input fingerprints, coverage and provenance before invoking a registered materializer.

## Registered materializations

The release contains twelve runtime-registered materializations:

| Materialization ID | Purpose |
|---|---|
| `code-declared-data-model` | Logical objects, fields and relationships declared in code |
| `physical-model` | Tables, columns, keys and relationships from PDM evidence |
| `logical-physical-mapping` | Evidence-backed correspondence between logical and physical objects |
| `effective-data-model` | Combined declared, physical, mapping and observed-use model |
| `sql-analysis` | Repository SQL knowledge from `sql-analysis/v1` |
| `workspace-sql-catalog` | Workspace-wide SQL relations, usage and lineage |
| `system-description` | System structure and external dependencies |
| `reference-data` | Observed reference-data facts |
| `persistence-lineage` | Source, storage and access lineage with explicit gaps |
| `system-interactions` | Matched repository interaction boundaries |
| `repository-value-flow` | Repository value-flow graph and attribute paths |
| `observed-storage-usage` | Code-observed storage access kept distinct from declared constraints |

Task/Suite routing is absent. Materialization selection uses `materialization_id` plus typed evidence and knowledge identities. There is no compatibility adapter, hidden fallback or dual-write.

## Contract catalog

```bash
knowledge-layer-materialization-contracts \
  --core-target-contracts core-target-contracts.json \
  --output knowledge-materialization-contracts.json
```

The catalog exposes required and optional evidence, required knowledge dependencies, output model identity, runtime registration and catalog fingerprint.

## Direct diagnostic execution

```bash
knowledge-layer-materialize \
  --request knowledge-materialization-request.json \
  --output knowledge-materialization-execution-result.json
```

This CLI executes one typed request. Product graph planning and sequencing are performed by `static-analysis-runner knowledge-execute`.

## Deterministic knowledge rules

KLC preserves the evidence boundary:

- observed facts and declared constraints remain distinguishable;
- `partial` input status, coverage and diagnostics remain visible;
- ambiguous candidates are retained instead of silently discarded;
- unsupported or unresolved joins, writes and mappings become explicit gaps;
- payload fingerprints may support compatibility checks but do not create addresses or relationships by themselves;
- physical, logical, SQL-observed, interaction, persistence and value-flow models remain separate typed models even when combined in an effective view.

## Prepared Knowledge read boundary

Canonical typed read/query contracts are owned by the separate `prepared-knowledge-runtime` package. `knowledge-layer-core` owns materialization and production semantics and depends on that runtime only for the shared deterministic contracts/primitives that have a single owner.

Published consumers should use Knowledge API. Direct local diagnostic reads, when required by framework development, use `prepared_knowledge_runtime` rather than KLC.

## Performance and atomicity

Large materializations use explicit transactions so thousands of rows are committed atomically rather than one row at a time. Each materialization can be executed in a clean worker process by Runner to isolate DuckDB state between graph nodes.

## Portfolio topology

Portfolio topology and repository interaction islands are not part of the installed KLC package or this source tree. Their historical implementation is distributed only as a separate parked snapshot. The product materializations for SQL, data models, system knowledge, interactions, persistence lineage and value flow do not depend on topology.

## Checks

```bash
python -m compileall knowledge_layer_core
pytest -q
```
