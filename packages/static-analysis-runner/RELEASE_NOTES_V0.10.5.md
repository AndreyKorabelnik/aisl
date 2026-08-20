# static-analysis-runner 0.10.5

Restores user-facing planning for cross-repository value flow after the Task/Suite removal.

- `interaction-field-contracts` declares its KLC dependencies as required.
- Adds `cross-repository-attribute-lineage` knowledge selection.
- The selection deterministically expands to local attribute lineage, system interactions, interaction field contracts, and cross-repository value flow.
- Local `attribute-lineage` is described honestly as repository-local.
- Executor remains generic; no topology, Suite/Task, fallback, or materialization-specific dispatch is added.
