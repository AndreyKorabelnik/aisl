# aisl-reporting 0.10.0

Iteration 22 migrates all data-model and workspace-interaction builders to the canonical nested relationship contract from KLC 0.27.0.

- Reads logical identity and physical storage keys separately.
- Uses `reference.encoding_inputs` and structured `join` instead of legacy `join_guidance`/`target_key_fields`.
- Exposes alias and storage-key components to the renderer while requiring an explicit profile or user instruction for physical formatting.
- The generic prompt does not invent separators, alias normalization, collection representation or SQL functions and keeps `physical_join_confirmed=false`.
