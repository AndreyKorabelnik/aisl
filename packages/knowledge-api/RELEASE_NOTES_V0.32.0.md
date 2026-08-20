# Knowledge API 0.32.0

- Replaces producer-specific published physical fields (`database`, `manifest`, `observed_artifact`) with one canonical `physical_artifacts[]` representation using unique product-local roles.
- Publishes real Core `sql-analysis/v1` as one observed KnowledgeProduct whose descriptor, manifest, coverage and typed JSONL shards are imported/finalized into AISL CAS before catalog visibility.
- Validates SQL descriptor/manifest/shard SHA-256, byte sizes and canonical content fingerprint before publication.
- Accepts producer-valid `partial` observed evidence without semantic promotion; `failed` observed artifacts remain non-publishable.
- Universal exact read resolves SQL observed facts from published CAS members by role, independent of producer-local directory layout.
- Existing derived products use the same physical-artifact contract (`database`, `manifest` roles); no dual read/write representation remains.
