# KCP one-shot lifecycle — change report

Date: 2026-08-15
Status: COMPLETE

## Problem

A real one-shot invocation previously remained in the Runner lifecycle after Runner had already produced an immutable `knowledge_execution_result/v2`. The same result could be published/read correctly through the official Knowledge API, so the issue had to be diagnosed independently from KLC performance and AISL semantic correctness.

## Observed root cause

`ProcessExecutor` coupled direct subprocess completion to EOF on asyncio stdout/stderr pumps. A direct command may exit while a descendant retains inherited output descriptors. In that state the direct process is complete, but the pipe readers do not receive EOF, so KCP can remain inside process execution and never advance the job stage.

A bounded synthetic reproduction demonstrated this independently of Runner semantics.

## Generic fix

1. Observe direct-child exit through the subprocess return code rather than waiting on output-pipe EOF.
2. Drain stdout/stderr for a bounded grace period.
3. If inherited handles remain open, emit an explicit warning and terminate only descendants in the POSIX process group owned by the KCP command.
4. Preserve existing timeout/cancel process-group termination behavior.
5. Keep the Runner stage active through result validation and artifact registration.
6. Perform Runner artifact scanning once and off the event loop.

This does not introduce another executor, Runner path, publication path, or fallback success state.

## Version

- knowledge-control-plane: `1.2.0a21` → `1.2.0a22`.
- all other framework runtime package versions unchanged.

## Separate baseline hygiene correction

The incoming canonical had inconsistent KCP version markers: package metadata/runtime reported `1.2.0a21`, while `VERSION` and `tests/test_module_baseline.py` still contained `1.2.0a20`. The release synchronizes all KCP version markers to `1.2.0a22`.
