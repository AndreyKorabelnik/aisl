# AT900 FDP report validation — 0.13.1

The earlier FDP dataset for AT900 exceeded the profile limit:

- previous dataset: approximately `2.1 MB`;
- profile limit: `500000` bytes.

The cause was duplication and unbounded inclusion of all low-level lineage rows in the report payload, not missing Core or Knowledge Layer facts.

## Implemented selection policy

The report payload now selects paths in this order:

1. paths participating in confirmed end-to-end same-data cases;
2. other confirmed paths;
3. source-interpreted confirmed paths;
4. paths from connected source-and-access cases;
5. remaining paths in deterministic order.

The canonical catalog is not modified. Aggregate counts and completeness summaries use all paths.

## Real result

The prepared AT900 dataset is `311324` bytes and validates against the profile schema and budget.

The connected case for `DEVICE_LINK` is present:

```text
Kafka SyncPushDeviceRequest
→ DEVICE_LINK
→ POST /deviceIdList
```

Exact field overlap:

```text
CLIENT_ID
DEVICE_ID
UCP_ID
```

Status:

- source-to-storage observed: `true`;
- storage-to-access observed: `true`;
- end-to-end same-data: `confirmed`;
- business FDP decision: `not_assigned`;
- risk decision: `not_assigned`;
- missing links: none;
- case path selection truncated: `false`.

The result proves a mechanical same-data path for the listed physical fields. It does not by itself assign a business conclusion that the data are “foreign” or that their storage is a risk.
