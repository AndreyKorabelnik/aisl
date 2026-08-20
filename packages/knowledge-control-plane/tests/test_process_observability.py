from __future__ import annotations

from knowledge_control_plane.api.generic_v1.models import LogLevel, LogStream
from knowledge_control_plane.runtime.process import classify_process_line


def test_stderr_progress_is_not_reported_as_error() -> None:
    assert classify_process_line(LogStream.STDERR, "Checking code-analyzer-core version") is LogLevel.INFO
    assert classify_process_line(LogStream.STDERR, "Repository analysis completed: ucp_api") is LogLevel.INFO
    assert classify_process_line(LogStream.STDERR, "Updating files: 57% (286/501)") is LogLevel.INFO


def test_stderr_warning_and_error_are_classified_by_content() -> None:
    assert classify_process_line(LogStream.STDERR, "WARNING: partial coverage") is LogLevel.WARNING
    assert classify_process_line(LogStream.STDERR, "ERROR: profile mismatch") is LogLevel.ERROR
    assert classify_process_line(LogStream.STDERR, "Out of Memory Error: failed to allocate") is LogLevel.ERROR


def test_executor_returns_after_direct_process_exit_when_descendant_keeps_pipes_open(tmp_path) -> None:
    import asyncio
    import sys
    import time

    from knowledge_control_plane.runtime.commands import CommandSpec
    from knowledge_control_plane.runtime.process import ProcessExecutor

    async def run_probe():
        messages = []

        async def on_log(level, stream, message, stage):
            messages.append((level, stream, message, stage))

        command = CommandSpec(
            stage="runner_execution",
            argv=(
                sys.executable,
                "-c",
                (
                    "import subprocess; "
                    "subprocess.Popen([%r, '-c', 'import time; time.sleep(2)']); "
                    "print('direct process completed', flush=True)"
                ) % sys.executable,
            ),
            cwd=tmp_path,
            environment={},
            output_path=tmp_path,
        )
        executor = ProcessExecutor(pipe_drain_grace_seconds=0.05)
        started = time.monotonic()
        result = await executor.execute(
            job_id="job-descendant-pipe-probe",
            command=command,
            timeout_seconds=10,
            on_log=on_log,
        )
        return result, messages, time.monotonic() - started

    result, messages, elapsed = asyncio.run(run_probe())
    assert result.exit_code == 0
    assert elapsed < 1.5
    assert any(message == "direct process completed" for _level, _stream, message, _stage in messages)
    assert any("inherited output pipes remained open" in message for _level, _stream, message, _stage in messages)


def test_executor_timeout_still_terminates_owned_process_group(tmp_path) -> None:
    import asyncio
    import sys
    import time

    from knowledge_control_plane.runtime.commands import CommandSpec
    from knowledge_control_plane.runtime.process import ProcessExecutor

    async def run_probe():
        async def on_log(_level, _stream, _message, _stage):
            return None

        command = CommandSpec(
            stage="runner_execution",
            argv=(sys.executable, "-c", "import time; time.sleep(5)"),
            cwd=tmp_path,
            environment={},
            output_path=tmp_path,
        )
        executor = ProcessExecutor(pipe_drain_grace_seconds=0.05)
        started = time.monotonic()
        result = await executor.execute(
            job_id="job-timeout-probe",
            command=command,
            timeout_seconds=0.1,
            on_log=on_log,
        )
        return result, time.monotonic() - started

    result, elapsed = asyncio.run(run_probe())
    assert result.timed_out is True
    assert result.exit_code != 0
    assert elapsed < 1.5
