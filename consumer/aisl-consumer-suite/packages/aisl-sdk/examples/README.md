# Python examples

All examples use only the public `aisl-sdk` + Knowledge API boundary.

```bash
python list_systems.py --api-url http://127.0.0.1:8080
python inspect_revision.py --api-url http://127.0.0.1:8080 --system-id ucp-data-model
python data_model_lookup.py --api-url http://127.0.0.1:8080 --system-id ucp-data-model --search "Страна рождения"
python object_context.py --api-url http://127.0.0.1:8080 --system-id ucp-data-model --object-id <object-id>
```

Omitting `--revision-id` resolves the active revision once and then uses the concrete immutable id for the operation.
