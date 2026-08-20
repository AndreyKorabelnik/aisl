# Knowledge Control Plane 1.2.0a33

`knowledge-control-plane` is the **headless orchestration backend** for the canonical knowledge-execution route of the automatic code-analysis platform. The browser frontend is a separate product: `knowledge-base-generator-ui`.

The product route is:

```text
repository revision + Knowledge Profile + optional typed external inputs
→ knowledge_input_inventory/v1
→ knowledge_execution_plan/v1
→ Core typed evidence
→ KLC materializations
→ knowledge_execution_result/v2
→ self-contained AISL publication bundle
```

Knowledge Control Plane does not define the semantics of knowledge, does not read knowledge DuckDB files directly and does not publish capabilities itself. Core owns evidence analyzers, KLC owns materializers, and Knowledge API/AISL owns immutable published revisions. Reporting, chat/LLM, visualization and other presentation consumers are outside the framework production runtime.

## Supported user flow

The current built-in profile is `data-model-v1`. The user selects the desired knowledge outcomes:

- model declared in code;
- physical data model;
- logical-to-physical mapping;
- effective data model.

A PowerDesigner `.pdm` file is required when the selected result depends on the physical model. Knowledge Control Plane compiles the requested scenario/profile context into an executable plan; clients never select Core analyzers or KLC materializers directly.

The visible execution stages are:

```text
checkout
prepare_inputs
runner_plan
runner_execution
bundle
```

After completion a self-contained AISL publication bundle is available. `aisl-server` imports that bundle and owns validation, Artifact Store ingestion, immutable revision creation and activation. Reporting and Chat/LLM consumption remain separate product boundaries.

## Start

```bash
pip install -e . --no-deps
knowledge-control-plane doctor
knowledge-control-plane serve --host 0.0.0.0 --port 8000
```

The standalone Generator UI is installed and run from the separate `knowledge-base-generator-ui` project. KCP does not serve frontend files and has no Node/npm runtime dependency.

## Required external commands

```bash
export STATIC_ANALYSIS_RUNNER_COMMAND="static-analysis-runner"
```

Knowledge Control Plane calls Runner only through generic runtime commands. Single/workspace runs use `physical-model` when required, `knowledge-input-inventory`, `knowledge-execution-plan` and `knowledge-execute`. Repository-batch runs use Runner-owned `repository-batch-run`; Control Plane supplies the selected repository-scoped Knowledge Profile and its pinned catalogs but does not clone repositories itself.


## Knowledge API

```bash
export KNOWLEDGE_API_BASE_URL="http://127.0.0.1:8080/api/knowledge/v1"
export KNOWLEDGE_API_TIMEOUT_SECONDS=30
export KNOWLEDGE_API_PROXY_ENABLED=1
```

Knowledge consumers may call Knowledge API directly. KCP also exposes `/api/knowledge/v1/**` as a transparent optional reverse proxy to the configured upstream without changing JSON, Markdown, status codes or end-to-end headers.

Knowledge Control Plane stores orchestration state and Producer bundle metadata. It never creates AISL revisions. It may read pinned published revisions for composition scenarios and may proxy Knowledge API reads, but publication is owned by `aisl-server`.

## Bitbucket authentication

```bash
export BITBUCKET_USERNAME="<username>"
export BITBUCKET_TOKEN="<token-or-app-password>"
# or BITBUCKET_ACCESS_TOKEN
```

Credentials are passed through a runtime `GIT_ASKPASS` helper, not through repository URLs or command arguments. SSH host verification is not disabled.

## Main orchestration API

Knowledge Control Plane owns:

```text
/api/v1/repositories
/api/v1/workspaces
/api/v1/knowledge-profiles
/api/v1/jobs
/api/v1/artifacts
/api/v1/diagnostics
/api/v1/productions
```

## Registered production and automatic freshness

A Production Registration binds a system, a compatible Knowledge Profile, selected source repositories, optional typed external inputs and a refresh policy. It is control-plane state only; Runner remains the owner of Knowledge Product dependency resolution and execution planning.

For Git sources, freshness is compared using immutable commit SHA snapshots. For file inputs such as PDM, SHA-256 is used. The Producer baseline is the last successfully built publication bundle for that production; failed or cancelled jobs never advance it. Server revision lifecycle is tracked by `aisl-server`, not by Producer. Source acquisition for refresh jobs is pinned to the exact observed snapshot.

The Control Plane does not contain an internal periodic scheduler. An external scheduler calls the running service through:

```bash
knowledge-control-plane refresh-check --due
```

or the equivalent `/api/v1/productions/.../refresh-check` HTTP endpoints. Any UI or automation client uses this same public backend path.

Knowledge API owns `/api/knowledge/v1/**`.

The executable OpenAPI document is stored in `docs/api/generic-v1.openapi.json`.

## Runtime compatibility

Runtime storage schema v3 is the only supported schema. A runtime SQLite database created before the breaking product rename is rejected explicitly. There is no automatic migration or legacy fallback; start with a new runtime database.

## Validation

```bash
PYTHONPATH=src pytest -q
python -m compileall -q src/knowledge_control_plane
python scripts/generate_openapi.py
python scripts/verify_source_manifest.py
```

The release archive includes current test results and architecture audit. Consumer/chat acceptance is owned by the separate Chat product after the split.

## One-shot terminal execution

An Analysis Scenario can be executed directly from a terminal without starting the Knowledge Control Plane HTTP server. The command uses the built-in scenario/profile registry and the packaged runtime contracts; users do not pass Knowledge Profile JSON or catalog paths.

Single repository example:

```bash
knowledge-control-plane run \
  --scenario build-repository-inventory-v1 \
  --repository /path/to/repository \
  --system-id my-repository
```

Repository-batch example for a Bitbucket Data Center project:

```bash
export BITBUCKET_TOKEN='...'
knowledge-control-plane run \
  --scenario build-repository-inventory-v1 \
  --bitbucket-project-url 'https://bitbucket.example/projects/ABC'
```

The batch path is operational orchestration, not multi-repository analysis. Runner discovers the project repositories and executes the same repository-scoped Knowledge Profile independently for each repository. Each checkout is created under Runner-owned temporary work, deleted after that repository completes or fails, and never persisted in the batch output. The current mode is sequential (`max_concurrent_checkouts=1`).

Use `--repository-limit 3` for a small live acceptance run before processing the full project. `--output` is optional; without it Control Plane creates a timestamped output under its configured analysis output root. Authentication is read from the normal Bitbucket environment variables.

`knowledge-control-plane serve` is not required for either terminal path. The existing single/workspace path produces a self-contained AISL publication bundle. The repository-batch path currently persists independent Runner/KLC repository results plus the batch manifest; it does not create multi-repository KLC knowledge or silently publish a combined portfolio revision.

## Packaged runtime contracts

Knowledge Control Plane ships the compact runtime contract bundle required by the current framework baseline under `knowledge_control_plane/resources/runtime_contracts/`. Runtime execution does **not** depend on any project `validation/` directory. The bundle is validated by schema and by the Core/KLC catalog fingerprints referenced from the Knowledge catalog. Explicit `KNOWLEDGE_CONTROL_PLANE_*_CATALOG` overrides remain available for advanced diagnostics only.

## Reusable System Description context (2.0.0a78)

The built-in `system-description-v1` Knowledge Profile uses the same generic source-backed workspace pipeline as other multi-repository products. The wizard selects only stable repository context and Runner produces `system-description` knowledge once. Consumer guidance such as `system-description/v1` belongs to the public integration contract and is consumed outside Knowledge Base Generator; there is no scenario-specific System Description runtime.
