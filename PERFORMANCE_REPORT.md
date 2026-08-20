# Performance Report — FI-001

No broad performance campaign was run for this targeted contract block.

The architectural cost control is explicit: `structured-file-shape-evidence/v1` is `existing_only` in the default Repository Inventory materialization contract. Therefore default inventory does not start structured-content parsing solely for this enrichment.

The generic sanitized acceptance used 8 JSON members and is a correctness/architecture smoke, not a scale benchmark. Scale/per-format performance should be measured only when Miner requests wider structured-format coverage.
