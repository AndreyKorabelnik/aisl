# Knowledge Control Plane 1.2.0a29

Repins the official runtime contract bundle for Repository Inventory source localization (`KLC 0.61.0a37`).

- Core evidence catalog remains byte-identical at Core `0.44.23a7`.
- KLC materialization catalog is regenerated from the canonical builder and now publishes `repository-inventory/v4` with `common.repository-source-occurrences`.
- Runner execution-result and knowledge catalogs are regenerated from canonical builders; Runner code remains `0.10.27`.
- Bundle manifest hashes/fingerprints are regenerated from packaged catalog bytes.
