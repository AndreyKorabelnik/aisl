# static-analysis-runner 0.10.9 — agent-ready data-model product wiring

Wire the existing user-facing `data-model-attribute-extension` product to KLC 0.59.33 `data-model-attribute-extension-context`.

The generic internal-materialization closure introduced in Runner 0.10.8 is reused unchanged. The user still selects one knowledge product; Runner automatically adds the technical dependency chain required by the KLC contract.

For the current data-model extension product the resulting KLC chain is:

`model-storage-semantics -> logical-storage-mapping -> cross-artifact-data-model-mapping -> data-model-attribute-extension-context`

Public dependencies remain code-declared data model, physical data model and SQL source inventory. Internal materializations are not directly user-selectable.

No UCP/datamart/PDM-specific dispatch or naming heuristic is added.
