from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
import json
import re
import shutil
import uuid
from typing import Any, Callable, Mapping

from .io_utils import now_utc, stable_fingerprint, write_json

PRODUCER_REUSE_ENTRY_SCHEMA_VERSION = "producer_artifact_reuse_entry/v1"
PRODUCER_REUSE_KEY_SCHEMA_VERSION = "producer_reuse_key/v1"
_SAFE_KIND = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass(frozen=True)
class ProducerReuseLookup:
    status: str
    entry: dict[str, Any] | None = None
    payload_root: Path | None = None
    diagnostic: str | None = None


class ProducerArtifactStore:
    """Filesystem-backed immutable content-addressed registry for producer outputs.

    The registry is intentionally execution-engine agnostic. It stores completed immutable
    producer directories keyed by a caller-supplied compatibility material. Callers remain
    responsible for validating their own typed contracts before accepting a hit.
    """

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def reuse_key(material: Mapping[str, Any]) -> str:
        return stable_fingerprint({
            "schema_version": PRODUCER_REUSE_KEY_SCHEMA_VERSION,
            "material": deepcopy(dict(material)),
        })

    def _kind_root(self, producer_kind: str) -> Path:
        value = _SAFE_KIND.sub("-", str(producer_kind)).strip("-._")
        if not value:
            raise ValueError("producer_kind has no safe filesystem identity")
        path = (self.root / value).resolve()
        path.relative_to(self.root)
        return path

    def entry_root(self, producer_kind: str, reuse_key: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{64}", str(reuse_key)):
            raise ValueError("reuse_key must be a SHA-256 fingerprint")
        return self._kind_root(producer_kind) / reuse_key

    def lookup(
        self,
        *,
        producer_kind: str,
        reuse_key: str,
        validator: Callable[[Path, Mapping[str, Any]], None] | None = None,
    ) -> ProducerReuseLookup:
        entry_root = self.entry_root(producer_kind, reuse_key)
        entry_path = entry_root / "entry.json"
        payload_root = entry_root / "payload"
        if not entry_path.is_file():
            return ProducerReuseLookup(status="miss")
        try:
            entry = json.loads(entry_path.read_text(encoding="utf-8"))
            if str(entry.get("schema_version") or "") != PRODUCER_REUSE_ENTRY_SCHEMA_VERSION:
                raise ValueError(f"unsupported reuse entry schema: {entry.get('schema_version')!r}")
            if str(entry.get("reuse_key") or "") != reuse_key:
                raise ValueError("reuse entry key mismatch")
            if str(entry.get("producer_kind") or "") != producer_kind:
                raise ValueError("reuse entry producer_kind mismatch")
            if str(entry.get("status") or "") != "completed":
                raise ValueError(f"reuse entry is not completed: {entry.get('status')!r}")
            if not payload_root.is_dir():
                raise FileNotFoundError(f"reuse payload directory is missing: {payload_root}")
            if validator is not None:
                validator(payload_root, entry)
        except Exception as exc:
            return ProducerReuseLookup(
                status="invalid",
                diagnostic=f"{type(exc).__name__}: {exc}",
            )
        return ProducerReuseLookup(
            status="hit",
            entry=deepcopy(dict(entry)),
            payload_root=payload_root,
        )

    def quarantine(
        self,
        *,
        producer_kind: str,
        reuse_key: str,
        diagnostic: str | None = None,
    ) -> Path | None:
        entry_root = self.entry_root(producer_kind, reuse_key)
        if not entry_root.exists():
            return None
        if diagnostic:
            write_json(
                entry_root / "invalid.json",
                {
                    "schema_version": "producer_artifact_reuse_invalid/v1",
                    "reuse_key": reuse_key,
                    "producer_kind": producer_kind,
                    "invalidated_at": now_utc(),
                    "diagnostic": diagnostic,
                },
            )
        invalid_root = self.root / "invalid" / self._kind_root(producer_kind).name
        invalid_root.mkdir(parents=True, exist_ok=True)
        target = invalid_root / f"{reuse_key}-{uuid.uuid4().hex[:12]}"
        entry_root.rename(target)
        return target

    def publish_directory(
        self,
        *,
        producer_kind: str,
        reuse_key: str,
        source_root: str | Path,
        metadata: Mapping[str, Any],
    ) -> tuple[Path, dict[str, Any]]:
        source = Path(source_root).expanduser().resolve()
        if not source.is_dir():
            raise ValueError(f"producer output directory does not exist: {source}")
        kind_root = self._kind_root(producer_kind)
        kind_root.mkdir(parents=True, exist_ok=True)
        final_root = self.entry_root(producer_kind, reuse_key)
        if final_root.exists():
            entry = json.loads((final_root / "entry.json").read_text(encoding="utf-8"))
            return final_root / "payload", entry

        temp_root = kind_root / f".{reuse_key}.tmp-{uuid.uuid4().hex}"
        try:
            payload_root = temp_root / "payload"
            shutil.copytree(source, payload_root)
            entry: dict[str, Any] = {
                "schema_version": PRODUCER_REUSE_ENTRY_SCHEMA_VERSION,
                "reuse_key": reuse_key,
                "producer_kind": producer_kind,
                "status": "completed",
                "created_at": now_utc(),
                "metadata": deepcopy(dict(metadata)),
            }
            write_json(temp_root / "entry.json", entry)
            try:
                temp_root.rename(final_root)
            except FileExistsError:
                shutil.rmtree(temp_root, ignore_errors=True)
            entry = json.loads((final_root / "entry.json").read_text(encoding="utf-8"))
            return final_root / "payload", entry
        finally:
            if temp_root.exists():
                shutil.rmtree(temp_root, ignore_errors=True)


def build_reuse_decision(
    *,
    node_id: str,
    producer_kind: str,
    producer_id: str,
    producer_version: str,
    action: str,
    reuse_key: str,
    basis: str,
    source_id: str | None = None,
    invalidation_reason: str | None = None,
    artifact_reference: str | None = None,
    elapsed_seconds: float | None = None,
    saved_seconds: float | None = None,
    diagnostics: list[str] | None = None,
) -> dict[str, Any]:
    if action not in {"built", "reused"}:
        raise ValueError(f"unsupported producer reuse action: {action!r}")
    return {
        "node_id": node_id,
        "producer_kind": producer_kind,
        "producer_id": producer_id,
        "producer_version": producer_version,
        "source_id": source_id,
        "action": action,
        "reuse_key": reuse_key,
        "basis": basis,
        "invalidation_reason": invalidation_reason,
        "artifact_reference": artifact_reference,
        "elapsed_seconds": elapsed_seconds,
        "saved_seconds": saved_seconds,
        "diagnostics": list(diagnostics or []),
    }
