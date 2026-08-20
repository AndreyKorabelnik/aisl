# code-analyzer-core 0.44.16

Focused FDP evidence improvement for real AT900 paths without adding system-specific rules.

## What changed

- Known ingress DTO schemas now bound the set of fields that may be attributed to that external payload. Downstream wrapper-only fields are no longer silently relabelled as external input fields.
- JOOQ batch extraction now understands ordinary `DSL.param(...)` placeholders and enhanced-for iterator binding.
- Thin source-declared same-class DAO wrappers can be followed to concrete JOOQ writes using exact positional parameter binding.
- Existing observed facts can be composed across `source object → factory field → DAO physical field` when payload type, saved object and field identities all agree.

## Real AT900 result

- `SyncPushDeviceRequest → DEVICE_LINK`: five observed payload fields remain; false `phoneNumber/loginId/reason` source attributions are removed.
- `SpreadProfileRq.id → UCP_PHONE_2.UCP_ID`: confirmed.
- `SpreadProfileRq.version → UCP_PHONE_2.LAST_EVENT_ID`: confirmed.
- `phoneNumber` and `lastEventTime` remain partial because their factory source fields are not directly observed; no inference was added to force them complete.
- Existing confirmed MNP lineage remains intact.

No business FDP verdicts, AT900 names, table names or method-name heuristics are embedded in the implementation.
