# knowledge-layer-core 0.53.4

## Exact FDP field/path cases

The previous table-level FDP mechanical case has been removed.

A mechanical case is now created at the exact granularity:

`repository + storage object + storage field + source path + access path`.

A case is confirmed only when:

- the storage object identity matches;
- the physical storage field identity matches;
- the source-to-storage path is confirmed;
- the storage-to-access path is confirmed.

Different fields and different business paths of the same table are no longer
combined into one evidence case. Table-level information remains available only
as a summary and is explicitly marked `summary_only_not_end_to_end_proof`.

No business FDP classification or risk verdict is assigned.
