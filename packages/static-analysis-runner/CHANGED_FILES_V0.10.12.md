# static-analysis-runner 0.10.12

Legacy Cleanup Block 5.

- Knowledge planning now consumes KLC materialization catalog v3 and the current installed materialization set only.
- Removed responsibility-map input and migration architecture-audit runtime/CLI surfaces.
- Removed migration statuses and old/planned materialization lookup.
- Unregistered current KLC materializations are explicitly `unavailable_unregistered`; no compatibility route is attempted.
- Execution planning, materialization executor and execution-result contracts consume catalog v3.
