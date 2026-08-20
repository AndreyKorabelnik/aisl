from __future__ import annotations

import hashlib
import json
import re
from datetime import timedelta
from pathlib import Path
from typing import Iterable

from knowledge_control_plane.api.generic_v1.models import (
    JobStatus,
    ProductionFreshnessResponse,
    ProductionFreshnessStatus,
    ProductionRefreshMode,
    ProductionRegistration,
    SourceSnapshot,
    SourceSnapshotAvailability,
    SourceSnapshotKind,
)

from .errors import ResourceNotFound, RuntimeApiError
from .jobs import JobManager, TERMINAL_STATUSES
from .productions import ProductionService
from .repositories import RepositoryService
from .store import RuntimeStore, utc_now


def _stable_fingerprint(payload: object) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_iso8601_interval(value: str) -> timedelta:
    match = re.fullmatch(
        r"P(?:(?P<days>\d+)D)?(?:T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?)?",
        value.strip().upper(),
    )
    if not match:
        raise RuntimeApiError(422, "refresh_interval_invalid", f"unsupported refresh interval: {value}")
    values = {name: int(raw or 0) for name, raw in match.groupdict().items()}
    interval = timedelta(**values)
    if interval.total_seconds() <= 0:
        raise RuntimeApiError(422, "refresh_interval_invalid", "refresh interval must be greater than zero")
    return interval


def source_snapshot_fingerprint(snapshots: Iterable[SourceSnapshot]) -> str:
    return _stable_fingerprint(
        [
            {"source_id": item.source_id, "snapshot_fingerprint": item.snapshot_fingerprint}
            for item in sorted(snapshots, key=lambda value: value.source_id)
        ]
    )


class FreshnessService:
    """Control-plane freshness decision service.

    It resolves immutable source versions and delegates actual production to the
    existing JobManager/Runner path. It is deliberately not a scheduler or producer.
    """

    def __init__(
        self,
        *,
        store: RuntimeStore,
        productions: ProductionService,
        repositories: RepositoryService,
        jobs: JobManager,
    ) -> None:
        self.store = store
        self.productions = productions
        self.repositories = repositories
        self.jobs = jobs

    def due(self, production: ProductionRegistration) -> bool:
        if not production.enabled or production.refresh_policy.mode is not ProductionRefreshMode.POLL:
            return False
        assert production.refresh_policy.interval is not None
        interval = _parse_iso8601_interval(production.refresh_policy.interval)
        if production.last_checked_at is None:
            return True
        return utc_now() >= production.last_checked_at + interval

    async def check_due(self, *, enqueue: bool = True) -> list[ProductionFreshnessResponse]:
        results: list[ProductionFreshnessResponse] = []
        for production in self.store.list_productions():
            if self.due(production):
                results.append(await self.check(production.production_id, enqueue=enqueue))
        return results

    async def check(
        self,
        production_id: str,
        *,
        enqueue: bool = True,
        force: bool = False,
    ) -> ProductionFreshnessResponse:
        production = self._reconcile(self.productions.get(production_id))
        observed = self._resolve_sources(production)
        checked_at = utc_now()
        unavailable = [item for item in observed if item.availability is SourceSnapshotAvailability.UNAVAILABLE]
        if unavailable:
            diagnostics = [item.diagnostic or f"source unavailable: {item.source_id}" for item in unavailable]
            updated = production.model_copy(
                update={
                    "freshness_status": ProductionFreshnessStatus.SOURCE_UNAVAILABLE,
                    "last_checked_at": checked_at,
                    "last_observed_source_snapshots": observed,
                    "diagnostics": diagnostics,
                }
            )
            updated = self.productions.update_runtime_state(updated)
            return ProductionFreshnessResponse(
                production=updated,
                observed_source_snapshots=observed,
            )

        desired_fingerprint = source_snapshot_fingerprint(observed)
        changed = self._changed_source_ids(production.last_successful_source_snapshots, observed)
        configuration_changed = production.last_successful_production_revision != production.revision
        active_job = self._active_refresh_job(production.production_id)
        if active_job is not None:
            status = (
                ProductionFreshnessStatus.UPDATE_QUEUED
                if active_job.status is JobStatus.QUEUED
                else ProductionFreshnessStatus.UPDATE_RUNNING
            )
            updated = production.model_copy(
                update={
                    "freshness_status": status,
                    "last_checked_at": checked_at,
                    "last_observed_source_snapshots": observed,
                    "desired_source_snapshot_fingerprint": desired_fingerprint,
                    "last_refresh_job_id": active_job.job_id,
                    "diagnostics": (
                        [
                            "newer source snapshot observed while an earlier refresh is still active; "
                            "the active pinned job is allowed to finish before another refresh is queued"
                        ]
                        if (
                            active_job.source_snapshot_fingerprint != desired_fingerprint
                            or active_job.production_revision != production.revision
                        )
                        else []
                    ),
                }
            )
            updated = self.productions.update_runtime_state(updated)
            return ProductionFreshnessResponse(
                production=updated,
                observed_source_snapshots=observed,
                changed_source_ids=changed,
            )

        if production.last_successful_source_snapshots and not changed and not configuration_changed and not force:
            updated = production.model_copy(
                update={
                    "freshness_status": ProductionFreshnessStatus.UP_TO_DATE,
                    "last_checked_at": checked_at,
                    "last_observed_source_snapshots": observed,
                    "desired_source_snapshot_fingerprint": desired_fingerprint,
                    "diagnostics": [],
                }
            )
            updated = self.productions.update_runtime_state(updated)
            return ProductionFreshnessResponse(
                production=updated,
                observed_source_snapshots=observed,
                changed_source_ids=[],
            )

        detection_status = (
            ProductionFreshnessStatus.CHANGE_DETECTED
            if production.desired_source_snapshot_fingerprint != desired_fingerprint or configuration_changed
            else ProductionFreshnessStatus.STALE
        )
        diagnostics = []
        if force:
            diagnostics.append("manual refresh was explicitly requested")
        if not production.last_successful_source_snapshots:
            diagnostics.append(
                "no successful source-snapshot baseline exists for this production; a full refresh is required"
            )
        elif configuration_changed:
            diagnostics.append(
                "production configuration revision differs from the last successfully built publication bundle"
            )
        updated = production.model_copy(
            update={
                "freshness_status": detection_status,
                "last_checked_at": checked_at,
                "last_observed_source_snapshots": observed,
                "desired_source_snapshot_fingerprint": desired_fingerprint,
                "diagnostics": diagnostics,
            }
        )
        updated = self.productions.update_runtime_state(updated)
        if not enqueue or not updated.enabled:
            return ProductionFreshnessResponse(
                production=updated,
                observed_source_snapshots=observed,
                changed_source_ids=changed,
            )

        request = self.productions.build_job_request(
            updated,
            source_snapshots=observed,
            source_snapshot_fingerprint=desired_fingerprint,
            force_rebuild=force,
        )
        job = await self.jobs.create(request)
        queued = updated.model_copy(
            update={
                "freshness_status": ProductionFreshnessStatus.UPDATE_QUEUED,
                "last_refresh_job_id": job.job_id,
                "diagnostics": [],
            }
        )
        queued = self.productions.update_runtime_state(queued)
        return ProductionFreshnessResponse(
            production=queued,
            observed_source_snapshots=observed,
            changed_source_ids=changed,
            enqueued_job_id=job.job_id,
        )

    def _resolve_sources(self, production: ProductionRegistration) -> list[SourceSnapshot]:
        snapshots = [self.repositories.resolve_snapshot(repository_id) for repository_id in production.repository_ids]
        if production.physical_model_path:
            path = Path(production.physical_model_path).expanduser().resolve()
            checked_at = utc_now()
            if not path.is_file():
                payload = {"source_id": "physical-model", "path": str(path), "availability": "unavailable"}
                snapshots.append(
                    SourceSnapshot(
                        source_id="physical-model",
                        source_kind=SourceSnapshotKind.FILE,
                        location=str(path),
                        resolved_version={},
                        checked_at=checked_at,
                        snapshot_fingerprint=_stable_fingerprint(payload),
                        availability=SourceSnapshotAvailability.UNAVAILABLE,
                        diagnostic=f"physical model source is not available: {path}",
                    )
                )
            else:
                sha256 = _sha256_file(path)
                resolved = {"kind": "sha256", "sha256": sha256, "byte_size": path.stat().st_size}
                snapshots.append(
                    SourceSnapshot(
                        source_id="physical-model",
                        source_kind=SourceSnapshotKind.FILE,
                        location=str(path),
                        resolved_version=resolved,
                        checked_at=checked_at,
                        snapshot_fingerprint=_stable_fingerprint(
                            {"source_id": "physical-model", "path": str(path), "resolved_version": resolved}
                        ),
                    )
                )
        return sorted(snapshots, key=lambda item: item.source_id)

    @staticmethod
    def _changed_source_ids(baseline: list[SourceSnapshot], observed: list[SourceSnapshot]) -> list[str]:
        base = {item.source_id: item.snapshot_fingerprint for item in baseline}
        current = {item.source_id: item.snapshot_fingerprint for item in observed}
        return sorted(
            source_id
            for source_id in set(base) | set(current)
            if base.get(source_id) != current.get(source_id)
        )

    def _active_refresh_job(self, production_id: str):
        candidates = [
            job for job in self.store.list_jobs()
            if job.production_id == production_id and job.status not in TERMINAL_STATUSES
        ]
        return candidates[0] if candidates else None

    def _reconcile(self, production: ProductionRegistration) -> ProductionRegistration:
        job_id = production.last_refresh_job_id
        if not job_id:
            return production
        try:
            job = self.jobs.get(job_id)
        except ResourceNotFound:
            return self.productions.update_runtime_state(
                production.model_copy(
                    update={
                        "diagnostics": [f"last refresh job is no longer available: {job_id}"],
                    }
                )
            )
        if job.status is JobStatus.SUCCEEDED and job.publication_bundle is not None:
            if production.last_successful_bundle_sha256 != job.publication_bundle.sha256:
                return self.productions.update_runtime_state(
                    production.model_copy(
                        update={
                            "last_successful_bundle_sha256": job.publication_bundle.sha256,
                            "last_successful_production_revision": job.production_revision,
                            "last_successful_source_snapshots": list(job.source_snapshots),
                            "desired_source_snapshot_fingerprint": job.source_snapshot_fingerprint,
                            "diagnostics": [],
                        }
                    )
                )
            return production
        if job.status is JobStatus.FAILED:
            message = job.failure.message if job.failure is not None else "refresh job failed"
            return self.productions.update_runtime_state(
                production.model_copy(
                    update={
                        "freshness_status": ProductionFreshnessStatus.UPDATE_FAILED,
                        "diagnostics": [message],
                    }
                )
            )
        if job.status is JobStatus.CANCELLED:
            return self.productions.update_runtime_state(
                production.model_copy(
                    update={
                        "freshness_status": ProductionFreshnessStatus.UPDATE_FAILED,
                        "diagnostics": ["refresh job was cancelled"],
                    }
                )
            )
        return production
