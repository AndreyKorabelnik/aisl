from __future__ import annotations

import threading
from datetime import datetime
from pathlib import Path
from typing import Callable

from rich.console import Console

ProgressCallback = Callable[[str, str], None]


class ConsoleFileProgress:
    """Write concise progress events to both the terminal and a durable run log."""

    _STYLES = {
        "DEBUG": "dim",
        "INFO": "cyan",
        "WARNING": "yellow",
        "ERROR": "bold red",
        "SUCCESS": "green",
    }

    def __init__(self, log_path: Path, *, console: Console | None = None, quiet: bool = False) -> None:
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.console = console or Console()
        self.quiet = quiet
        self._lock = threading.Lock()
        self.log_path.write_text("", encoding="utf-8")

    def __call__(self, level: str, message: str) -> None:
        normalized = str(level or "INFO").upper()
        timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
        plain = f"{timestamp} {normalized:<7} {message}"
        with self._lock:
            with self.log_path.open("a", encoding="utf-8") as handle:
                handle.write(plain + "\n")
            if not self.quiet:
                style = self._STYLES.get(normalized, "")
                self.console.print(f"[{style}]{normalized:<7}[/{style}] {message}" if style else plain)
