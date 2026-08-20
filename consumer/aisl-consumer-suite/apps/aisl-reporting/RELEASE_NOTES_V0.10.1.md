# aisl-reporting 0.10.1

## Iteration 23

- supports repeatable explicit `--instruction-file` inputs for downstream interpretation rules;
- labels explicit rules as instructions, never as Knowledge Layer evidence;
- keeps the generic prompt free of UCP/ChangeVector formatting assumptions;
- compacts high-volume relationship provenance while preserving all aliases and storage-key fields;
- reports truncation counts explicitly and remains within the configured prompt budget.
