# WKL 0.35.29 compatibility mapping

| Existing WKL concept | Core contract concept |
|---|---|
| `workspace_id` | `scope_id` |
| selected repository entry | `RepositoryEvidence` |
| `workspace.duckdb` | compatibility filename for future `knowledge-layer.duckdb` |
| `workspace_data_model_manifest.json` | WKL adapter manifest plus future core manifest |
| `analysis_mode=data-model` | `modes=[data-model]` |
| selection fingerprint | adapter metadata / build fingerprint |
| `workspace_repository` rows | scope repository registry |

No existing WKL output changes in contract v0.1.0.
