# AT900 FDP exact-case report validation — 0.13.2

knowledge-layer-core 0.53.4 replaced table-level FDP mechanical cases with exact cases having the following proof granularity:

```text
repository
+ storage object
+ storage field
+ source path
+ access path
```

The reporting profile was updated without a compatibility adapter.

## Selection policy

The report keeps exact cases in this order:

1. every confirmed exact case;
2. exact cases whose source and access paths are both in the selected path excerpt;
3. cases with either selected path;
4. other connected cases;
5. unmatched source-only or access-only cases.

The canonical KLC case catalog is not modified. Full counts and table summaries remain available, while the renderer receives a bounded deterministic excerpt.

## Real AT900 result

- exact cases in KLC: `945`;
- exact cases selected for reporting: `160`;
- confirmed exact cases in KLC: `11`;
- confirmed exact cases selected: `11`;
- selected lineage paths: `120` of `757`;
- compact dataset size: `423130` bytes;
- configured maximum: `500000` bytes.

### MNP operator case

A confirmed exact case is retained for:

```text
PhoneMNPEvent.phone.operator.operatorId
→ PHONE.OPERATORID
→ MbClientProfileExtendedResponse.profiles.operatorId
→ POST /mbClientProfileExtended
```

The case contains only:

```text
storage_object: PHONE
storage_field: OPERATORID
same_data_field_overlap: [OPERATORID]
```

`TOKENID` and `PHONEBLOCKCODE` are not merged into this proof.

### Push-device cases

The report retains separate confirmed exact cases for:

```text
DEVICE_LINK.CLIENT_ID
DEVICE_LINK.DEVICE_ID
DEVICE_LINK.UCP_ID
```

Each case references one source path and one access path. They are not collapsed into one table-level claim.

## Interpretation boundary

The result proves mechanical reuse of the same physical field across a confirmed source-to-storage path and a confirmed storage-to-access path. It does not assign:

- a business conclusion that the data are foreign;
- a compliance violation;
- a risk severity;
- an owner decision.
