# static-analysis-runner 0.10.24

`static-analysis-runner` compiles and executes typed Core evidence and deterministic KLC materialization graphs.

```text
knowledge_profile/v2
→ knowledge_input_inventory/v1
→ knowledge_execution_plan/v1
→ Core evidence analyzers
→ KLC materializations
→ knowledge_execution_result/v1
```

Task/Suite orchestration, repository/workspace wrapper commands and portfolio-topology are absent from the installed product runtime. There is no compatibility adapter, hidden fallback or dual-write.

## Product commands

- `knowledge-catalog` — publish selectable knowledge from Core and KLC contracts.
- `knowledge-profile-resolve` — validate and resolve `knowledge_profile/v2`.
- `knowledge-input-inventory` — bind repositories, typed evidence and existing knowledge artifacts.
- `knowledge-execution-plan` — compile one deterministic execution DAG.
- `knowledge-execute` — canonical product execution route.
- `data-model-discovery` — lightweight portfolio candidate scan through typed Core evidence.
- `repository-batch-discover` — list repositories in a Bitbucket Data Center project without cloning them.
- `repository-batch-run` — execute one repository-scoped Knowledge Profile independently for every selected repository.

Low-level `evidence-execute` and `knowledge-materialize` commands are diagnostics, not alternate product routes.

## Canonical execution

```bash
static-analysis-runner knowledge-input-inventory \
  --scope-kind repository \
  --scope-id client-profile \
  --repository ./client-profile \
  --core-evidence-catalog core-evidence-contract-catalog.json \
  --materialization-catalog knowledge-materialization-contracts.json \
  --output knowledge-input-inventory.json

static-analysis-runner knowledge-execution-plan \
  --knowledge-catalog knowledge-catalog.json \
  --profile knowledge-profile.json \
  --input-inventory knowledge-input-inventory.json \
  --core-evidence-catalog core-evidence-contract-catalog.json \
  --materialization-catalog knowledge-materialization-contracts.json \
  --output knowledge-execution-plan.json

static-analysis-runner knowledge-execute \
  --execution-plan knowledge-execution-plan.json \
  --core-evidence-catalog core-evidence-contract-catalog.json \
  --materialization-catalog knowledge-materialization-contracts.json \
  --output outputs/knowledge-execution
```

Runner selects Core outputs by typed artifact identity and invokes KLC only through its generic materialization runtime. The validated topological order in `knowledge_execution_plan/v1` is preserved; independent graph branches are not reordered by a second semantic scheduler.

## Evidence reuse

Completed and partial Core artifacts can be registered as existing typed inputs. Reuse preserves:

- artifact kind and schema version;
- fingerprint;
- actual status (`completed` or `partial`);
- coverage;
- diagnostic summary;
- repository and scope provenance.

A reuse plan can therefore contain zero Core analyzers and only the missing materializations.

## Materialization workers

Each KLC graph node executes in a clean worker process while still using the same generic KLC registry. This isolates DuckDB state and file handles between sequential materializations. Worker stdout and stderr are retained beside the typed execution result.

## Data-model discovery

`data-model-discovery` clones repositories sequentially, runs `data-model-candidate-analyzer`, stores compact candidate evidence outside each clone and deletes the temporary working copy. It does not build a full model.

## Repository batch processing

`repository-batch-run` is orchestration, not multi-repository analysis. It discovers or reads an operational repository list and executes the existing repository-scoped Knowledge pipeline independently for each member. Each Git checkout lives under a Runner-owned temporary run directory, is deleted immediately after that repository finishes (success or failure), and is never persisted in the batch output. The current execution mode is deliberately sequential (`max_concurrent_checkouts=1`). Failures are retained per repository and do not silently remove that repository from the batch report.

`repository-batch-discover` can persist the Bitbucket project membership manifest without downloading repository contents.

## Portfolio topology

Portfolio topology is maintained only as a separately distributed parked snapshot. It is not present in this source tree, imported by the CLI or installed with Runner. Kafka topology, Bitbucket streaming for islands and island selection remain in that independent track.

## Checks

```bash
python -m compileall static_analysis_runner
pytest -q
```
