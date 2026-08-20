# aisl-reporting 0.9.1

## Structured relationship-key fix

`system-description/v1` no longer assumes that `matched_declared_keys` contains only scalar key IDs.
Real Knowledge Layer relationship rows may contain structured dictionaries with key metadata. The
previous `set(...)` based merge therefore failed with `TypeError: unhashable type: 'dict'` while the
deterministic report dataset was being built.

The relationship merge now:

- deduplicates arbitrary JSON-like values by canonical JSON content;
- treats dictionaries with different source key order as the same value;
- preserves structured declared-key metadata in the report dataset;
- keeps deterministic ordering and scalar-ID compatibility.

The `--debug` CLI option remains a boolean flag and must be passed without a value.
