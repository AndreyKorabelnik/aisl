# knowledge-layer-core 0.50.0

## SQL analysis materialization

Version 0.50.0 adds a dedicated facts-only SQL knowledge-layer path for the canonical
`sql-analysis/v1` artifact produced by `code-analyzer-core >= 0.42.2`.

The new `build_sql_knowledge_layer(...)` builder:

- validates the exact 17-shard contract, shard order, identifiers, sizes, SHA-256 values,
  coverage file and content fingerprint;
- rejects non-portable source/evidence paths;
- ingests JSONL incrementally in bounded batches;
- materializes one typed DuckDB table per canonical fact type;
- preserves complete source records in `payload_json` without using generic `analysis_record`;
- publishes standard `knowledge-layer.duckdb` and `knowledge-layer-manifest.json` artifacts;
- exposes capabilities `common.sql-analysis` and `common.sql-relation-fields`;
- keeps source `analysis_status=partial` as coverage metadata rather than failing a valid build.

## First SQL query contract

`KnowledgeLayerQuery.list_sql_relations(...)` returns logical relation identities aggregated
across scoped occurrences, with only the fields actually linked to those relation occurrences.
The result includes field usage roles, resolution statuses, statement/occurrence counts,
repository-relative evidence and SQL coverage.

Template relations keep their template identity and return no fabricated resolved physical names.

## Real repository validation

On `datamart_profile_fl`:

- 27,600 canonical SQL facts imported;
- 17 typed fact tables populated;
- 1,426 scoped relations and 10,636 column usages preserved;
- 292 typed JOIN edges and 731 recursive lineage paths preserved;
- 0 duplicate fact IDs;
- 0 orphan non-null column-to-relation references;
- 89 aggregated physical relations;
- 195 aggregated physical-template relations;
- materialization completed in approximately 4 seconds with approximately 296 MB peak RSS;
- resulting DuckDB size: approximately 81 MB.

## Compatibility

The existing data-model, suite and portfolio-topology builders are unchanged. The shared
manifest contract now permits the explicit `sql` mode. No compatibility adapter or dual-write
contract was introduced.

`static-analysis-runner 0.9.25` still intentionally blocks SQL materialization until it is updated
to invoke this new builder.
