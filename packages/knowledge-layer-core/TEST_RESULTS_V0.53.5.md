# Test results — knowledge-layer-core 0.53.5

Environment:

- Python 3.13;
- DuckDB 1.5.5 supplied wheel;
- sqlglot 30.13.0 supplied wheel.

Results:

- `compileall` — passed;
- topology and interaction focused regression — 13 passed;
- JSON re-export fingerprint smoke — passed;
- partial snapshot regression — passed; failed repository is `connectivity_status=unknown` and component kind `unknown`;
- broad suite progressed beyond 64% without a new failure after stale baseline expectations were corrected, but the heavy run did not finish within the 240-second execution window.

The incomplete broad run is not claimed as passed. No failure was observed in the modified topology contour.
