# analysis-ui 2.0.0a23

## Iteration 25.3

- identifies one post-summary shutdown stall as the auto-loaded external `ddtrace` pytest plugin;
- disables that unrelated plugin for this module's test suite;
- fixes the real runtime resource leak: SQLite context management previously committed transactions but did not close connections;
- removes the `os._exit()` pytest wrapper and per-test interpreter workaround;
- restores ordinary grouped runtime regression in `scripts/check.sh`.
