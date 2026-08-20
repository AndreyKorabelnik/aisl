# code-analyzer-core 0.44.6

`code-analyzer-core` performs deterministic, repository-local static analysis and publishes typed evidence. It records observed source facts and diagnostics; interpretation, cross-repository composition and knowledge publication belong to downstream layers.

## Runtime boundary

```text
repository or typed external input
→ registered Core analyzer
→ typed artifact envelope
→ evidence files + manifest + coverage + diagnostics
```

The product route is compiled and executed by `static-analysis-runner` through `knowledge_execution_plan/v1`. Core does not orchestrate Task/Suite workflows and does not materialize knowledge models.

## Typed evidence catalog

The release publishes ten registered evidence contracts:

| Artifact kind | Schema |
|---|---|
| `data-model-candidate-evidence` | `data-model-candidate-evidence/v1` |
| `interaction-boundary-evidence` | `interaction-boundary-evidence/v1` |
| `java-persistence-mapping-evidence` | `java-persistence-mapping-evidence/v1` |
| `java-type-structure-evidence` | `java-type-structure-evidence/v1` |
| `persistence-lineage-evidence` | `persistence-lineage-evidence/v1` |
| `reference-data-evidence` | `reference-data-evidence/v1` |
| `sql-analysis` | `sql-analysis/v1` |
| `storage-usage-evidence` | `storage-usage-evidence/v1` |
| `system-description-evidence` | `system-description-evidence/v1` |
| `value-flow-evidence` | `value-flow-evidence/v1` |

Export the machine-readable contract catalog:

```bash
code-analyzer-core evidence-contracts \
  --output core-evidence-contract-catalog.json
```

Execute an already compiled analyzer request:

```bash
code-analyzer-core evidence-execute \
  --request core-evidence-execution-request.json \
  --output-dir outputs/core-evidence
```

`evidence-execute` is the canonical Core runtime invoked by Runner. Analyzer selection is based on `analyzer_id` and typed output identity, never on task names.

## Read-only catalogs

```bash
code-analyzer-core analysis-catalog \
  --profiles-root ./analysis-profiles \
  --fragments-root ./analysis-profile-fragments \
  --output core-analysis-catalog.json

code-analyzer-core target-contracts \
  --output core-target-contracts.json
```

The catalogs describe profiles, fragments, target contracts, runtime bindings and architecture diagnostics without executing repository analysis.

## Facts-only contract

Core may publish:

- source symbols, types, fields, methods and inheritance;
- annotations and their observed parameters;
- SQL statements, scopes, relations, projections, joins and field usage;
- HTTP boundaries and address evidence;
- persistence calls, mappings and unresolved candidates;
- value-flow nodes, edges and traceability paths;
- PDM tables, columns, keys and relationships;
- repository-relative provenance, coverage and diagnostics.

Core does not invent:

- logical or physical keys not observed in source evidence;
- joins based only on naming similarity;
- cross-repository interactions without matching boundary evidence;
- source-to-storage lineage when the physical write is not proven;
- business meaning or confidence hidden behind fallback behavior.

Unsupported, ambiguous and unresolved observations remain explicit diagnostics. Partial evidence remains usable and keeps its actual `partial` status, coverage and diagnostic summary.

## Low-level analysis commands

Commands such as `analyze-java`, `analyze-python`, `analyze-spec`, `analyze-physical-model` and `analyze-git-change` remain available for diagnostics and focused development. They are not alternate product orchestration paths. Production execution should be compiled by Runner and invoked through typed contracts.

## Main analysis families

### Java and Spring

The Java foundation uses Tree-sitter and publishes reusable repository observations. Typed analyzers derive type structure, persistence mapping, system description, reference data, interaction boundaries, persistence lineage, storage usage and value flow from that foundation.

### SQL

The SQL analyzer emits scoped AST-backed evidence for statements, relations, aliases, projections, column usage roles, joins, object dependencies, source-to-target flows and explicit gaps. Temporary and derived relations remain distinguishable from physical objects.

### Physical model

PowerDesigner PDM extraction records physical tables, columns, keys and relationships as deterministic source evidence. Logical-to-physical correspondence is not decided in Core; it is materialized by KLC from typed inputs.

### Discovery

`data-model-candidate-evidence/v1` is intentionally lightweight. It ranks repositories that are likely to contain a data model without building the full model.

## Installation and checks

The runtime is wheels-only; no native build is required during execution when the supplied wheels are available.

```bash
python -m compileall code_analyzer_core
pytest -q
```

Use `code-analyzer-core doctor` to check required runtime dependencies.
