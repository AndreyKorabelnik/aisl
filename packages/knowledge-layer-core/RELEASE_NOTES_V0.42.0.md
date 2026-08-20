# knowledge-layer-core 0.42.0

Introduces the first independent `portfolio-topology/v1` build path. It produces a compact `portfolio-topology.duckdb` from repository `system_interface_catalog.json` artifacts and materializes boundaries, HTTP matching, repository interactions, coverage and strict/extended islands without executing deep field/object lineage, value-origin, persistence or data-model materializers.

The build supports partial snapshots: repositories missing the required interface catalog remain visible with failed analysis coverage and do not block publication of successfully analyzed repositories.

No compatibility view, dual-write path or legacy topology representation was added.
