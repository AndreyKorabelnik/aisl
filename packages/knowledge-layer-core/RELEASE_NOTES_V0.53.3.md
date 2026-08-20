# knowledge-layer-core 0.53.3

## FDP scalar field mapping normalization

The FDP query service now supports both canonical source-to-storage representations:

1. aggregated path records containing `field_mappings`;
2. scalar Core records containing top-level `source_field` and `storage_field`.

The second representation is normalized only in the query projection. Raw imported evidence is not modified.

Mechanical FDP cases can therefore calculate exact physical-field overlap between source-to-storage and storage-to-access segments produced by current Core versions.

For the AT900 `DEVICE_LINK` vertical case, the bridge is now confirmed for:

- `CLIENT_ID`;
- `DEVICE_ID`;
- `UCP_ID`.

The service still assigns no business FDP or risk verdict. `same_data_end_to_end_status=confirmed` means only that both observed path segments share exact physical fields in the same storage object.
