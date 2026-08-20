# aisl-sdk

Public Python SDK for reading immutable AISL revisions through Knowledge API.

`aisl-sdk` is transport/integration convenience, not a Knowledge Layer. It never reads AISL storage directly and has no dependency on Core, Runner, KLC or KCP.

```python
from aisl_sdk import AislClient

with AislClient("http://127.0.0.1:8080") as client:
    revision = client.revision("ucp-data-model", "rev-...")
    integration = revision.integration("data-model/v1")
    result = integration.execute_tool("get_data_model_object_context", {"object_id": "..."})
```

The caller/LLM chooses tools according to the revision-specific Integration Profile. The SDK only executes canonical revision-pinned bindings and never upgrades ambiguity or missing evidence.
