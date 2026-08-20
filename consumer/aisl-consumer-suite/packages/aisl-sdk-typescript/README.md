# aisl-sdk-typescript

Public revision-pinned TypeScript/JavaScript SDK for AISL Knowledge API.

The Knowledge API OpenAPI document is the transport source of truth. The SDK owns transport convenience and immutable revision pinning only; it does not infer knowledge, resolve ambiguity, or access AISL storage directly.

```ts
import { AislClient } from "aisl-sdk-typescript";
const client = new AislClient("http://knowledge-api:8080");
const revision = await client.revision("ucp-data-model", "rev-...");
const integration = await revision.integration("data-model/v1");
```
