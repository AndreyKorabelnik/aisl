from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
import time
from typing import Callable, Iterator

ProgressSink = Callable[[str], None]
_PROGRESS_SINK: ContextVar[ProgressSink | None] = ContextVar("knowledge_layer_progress_sink", default=None)


def emit_progress(message: str) -> None:
    sink = _PROGRESS_SINK.get()
    if sink is not None:
        sink(str(message))


@contextmanager
def bind_progress(sink: ProgressSink | None) -> Iterator[None]:
    token = _PROGRESS_SINK.set(sink)
    try:
        yield
    finally:
        _PROGRESS_SINK.reset(token)


@contextmanager
def timed_phase(label: str) -> Iterator[None]:
    started = time.monotonic()
    emit_progress(f"{label} started")
    try:
        yield
    except Exception:
        emit_progress(f"{label} failed; duration={time.monotonic() - started:.1f}s")
        raise
    else:
        emit_progress(f"{label} completed; duration={time.monotonic() - started:.1f}s")
