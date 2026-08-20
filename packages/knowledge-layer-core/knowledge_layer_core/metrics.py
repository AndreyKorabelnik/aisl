from __future__ import annotations

import json
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))


class BuildStats:
    def __init__(self, build_id: str) -> None:
        self.build_id = build_id
        self.rows: list[tuple[Any, ...]] = []
        self.order = 0

    @contextmanager
    def phase(
        self,
        name: str,
        repo_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> Iterator[dict[str, Any]]:
        self.order += 1
        started_at = utc_now()
        started = time.perf_counter()
        state: dict[str, Any] = {"row_count": 0}
        yield state
        self.rows.append(
            (
                self.build_id,
                self.order,
                name,
                repo_id,
                started_at,
                time.perf_counter() - started,
                int(state.get("row_count") or 0),
                canonical_json(details or {}),
            )
        )
