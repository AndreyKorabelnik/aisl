# knowledge-control-plane 1.2.0a22

Date: 2026-08-15

## One-shot lifecycle reliability

- Fixed a subprocess lifecycle stall where the direct Runner process had exited but an inherited stdout/stderr descriptor held by a descendant kept asyncio pipe readers open indefinitely.
- `ProcessExecutor` now observes the direct child exit independently from pipe EOF, allows a bounded drain grace period, and terminates remaining owned POSIX process-group descendants if inherited pipes stay open.
- The condition is explicitly logged as a warning; it is not silently treated as normal completion.
- Timeout and cancellation semantics remain process-group based and are regression-tested.

## Runner-stage observability

- Runner output artifact scanning is now performed once, explicitly after the immutable execution result is validated.
- The scan runs via `asyncio.to_thread`, so hashing/registering artifacts does not block the control-plane event loop and heartbeat.
- `runner_execution` remains active until post-process artifact handling completes; publication starts only afterwards.

No Core, Runner, KLC, Prepared Runtime, Knowledge API, Knowledge Integration, or AISL contract semantics changed in this release.
