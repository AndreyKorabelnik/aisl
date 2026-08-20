# knowledge-api 0.5.0

Iteration 24.3 removes the registry-based read-only runtime and its `/api/v1/**` routes.

- `/api/knowledge/v1/**` is the only supported public API.
- `create_app()` creates the canonical contract application directly.
- CLI options `--registry` and `--no-legacy` were removed.
- the KLC query adapter was renamed and isolated as internal implementation (`data_model_query.py`, `query_source.py`, `data_model_models.py`);
- legacy registry, report service, response models, validation assets and duplicate OpenAPI exporter were removed;
- the canonical relationship and publication contracts are unchanged.
