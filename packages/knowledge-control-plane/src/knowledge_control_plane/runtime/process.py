from __future__ import annotations

import asyncio
import os
import re
import signal
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from knowledge_control_plane.api.generic_v1.models import LogLevel, LogStream

from .commands import CommandSpec
from .security import environment_secret_values, redact_text

LogCallback = Callable[[LogLevel, LogStream, str, str | None], Awaitable[None]]


_ERROR_PATTERN = re.compile(
    r"(?:^|\b)(?:error|fatal|exception|traceback|out of memory error|permission denied|operation not permitted)(?:\b|:)",
    re.IGNORECASE,
)
_WARNING_PATTERN = re.compile(r"(?:^|\b)(?:warning|warn)(?:\b|:)", re.IGNORECASE)


def classify_process_line(stream: LogStream, text: str) -> LogLevel:
    """Classify subprocess output by content, not by the selected pipe."""
    if stream is LogStream.STDOUT:
        return LogLevel.INFO
    normalized = text.strip()
    if _ERROR_PATTERN.search(normalized):
        return LogLevel.ERROR
    if _WARNING_PATTERN.search(normalized):
        return LogLevel.WARNING
    return LogLevel.INFO


@dataclass(frozen=True)
class ProcessResult:
    exit_code: int
    cancelled: bool = False
    timed_out: bool = False


class ProcessExecutor:
    """Execute a configured command without a shell and stream both output pipes."""

    def __init__(self, *, pipe_drain_grace_seconds: float = 1.0) -> None:
        self._processes: dict[str, asyncio.subprocess.Process] = {}
        self._lock = asyncio.Lock()
        self._pipe_drain_grace_seconds = max(0.01, float(pipe_drain_grace_seconds))

    async def execute(
        self,
        *,
        job_id: str,
        command: CommandSpec,
        timeout_seconds: int,
        on_log: LogCallback,
    ) -> ProcessResult:
        environment = os.environ.copy()
        environment.update(command.environment)
        secrets = environment_secret_values(command.environment)
        process = await asyncio.create_subprocess_exec(
            *command.argv,
            cwd=str(command.cwd),
            env=environment,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=(os.name == "posix"),
        )
        async with self._lock:
            self._processes[job_id] = process

        async def pump(
            stream: asyncio.StreamReader | None,
            stream_kind: LogStream,
        ) -> None:
            if stream is None:
                return
            while True:
                line = await stream.readline()
                if not line:
                    break
                decoded = line.decode("utf-8", errors="replace")
                # Git progress uses carriage returns. splitlines() turns each progress
                # update into a separate UI log entry instead of one large block.
                messages = decoded.splitlines() or [decoded.rstrip("\r\n")]
                for text in messages:
                    sanitized = redact_text(text, secrets=secrets)
                    await on_log(
                        classify_process_line(stream_kind, sanitized),
                        stream_kind,
                        sanitized,
                        command.stage,
                    )

        stdout_task = asyncio.create_task(pump(process.stdout, LogStream.STDOUT))
        stderr_task = asyncio.create_task(pump(process.stderr, LogStream.STDERR))
        timed_out = False
        cancelled = False
        try:
            await self._wait_for_direct_process_exit(process, timeout_seconds=timeout_seconds)
        except asyncio.TimeoutError:
            timed_out = True
            await self._terminate(process)
        except asyncio.CancelledError:
            cancelled = True
            await self._terminate(process)
            raise
        finally:
            try:
                await self._finish_stream_pumps(
                    process,
                    (stdout_task, stderr_task),
                    on_log=on_log,
                    stage=command.stage,
                )
            finally:
                async with self._lock:
                    self._processes.pop(job_id, None)
        return ProcessResult(
            exit_code=int(process.returncode if process.returncode is not None else -1),
            cancelled=cancelled,
            timed_out=timed_out,
        )


    @staticmethod
    async def _wait_for_direct_process_exit(
        process: asyncio.subprocess.Process,
        *,
        timeout_seconds: float,
    ) -> None:
        """Wait for the direct child status without coupling exit to pipe EOF.

        ``asyncio.subprocess.Process.wait()`` may stay pending after the direct child
        exits when a descendant inherited stdout/stderr. ``returncode`` is updated
        by the child watcher independently, so bounded polling preserves the real
        process lifecycle and leaves pipe draining to ``_finish_stream_pumps``.
        """
        loop = asyncio.get_running_loop()
        deadline = loop.time() + max(0.0, float(timeout_seconds))
        while process.returncode is None:
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise asyncio.TimeoutError()
            await asyncio.sleep(min(0.05, remaining))

    async def _finish_stream_pumps(
        self,
        process: asyncio.subprocess.Process,
        tasks: tuple[asyncio.Task[None], asyncio.Task[None]],
        *,
        on_log: LogCallback,
        stage: str,
    ) -> None:
        """Drain direct-process output without waiting forever on inherited pipe handles.

        A command can exit while a descendant still owns a copy of stdout/stderr. In
        that case ``StreamReader.readline()`` never receives EOF and the orchestrator
        would otherwise remain stuck after the direct process has already completed.
        The command owns its POSIX process group, so remaining descendants are
        terminated only after a bounded drain grace period.
        """
        pending = {task for task in tasks if not task.done()}
        if pending:
            _done, pending = await asyncio.wait(
                pending, timeout=self._pipe_drain_grace_seconds
            )
        if not pending:
            await asyncio.gather(*tasks, return_exceptions=True)
            return

        await on_log(
            LogLevel.WARNING,
            LogStream.SYSTEM,
            "Direct process exited but inherited output pipes remained open; "
            "terminating remaining process-group descendants",
            stage,
        )
        if os.name == "posix" and process.pid:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            _done, pending = await asyncio.wait(
                pending, timeout=self._pipe_drain_grace_seconds
            )
            if pending:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass

        for task in pending:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    async def cancel(self, job_id: str) -> bool:
        async with self._lock:
            process = self._processes.get(job_id)
        if process is None or process.returncode is not None:
            return False
        await self._terminate(process)
        return True

    async def _terminate(self, process: asyncio.subprocess.Process) -> None:
        if process.returncode is not None:
            return
        try:
            if os.name == "posix" and process.pid:
                os.killpg(process.pid, signal.SIGTERM)
            else:
                process.terminate()
        except ProcessLookupError:
            return
        try:
            await asyncio.wait_for(process.wait(), timeout=3)
            return
        except asyncio.TimeoutError:
            pass
        try:
            if os.name == "posix" and process.pid:
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
        except ProcessLookupError:
            return
        await process.wait()
