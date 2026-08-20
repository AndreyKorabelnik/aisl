from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

from knowledge_control_plane.api.generic_v1.models import (
    GitTrackedRef,
    GitTrackedRefKind,
    PageMeta,
    RepositoryDiscoverRequest,
    RepositoryDiscoverResponse,
    RepositoryListResponse,
    RepositorySourceKind,
    RepositoryStatus,
    RepositorySummary,
    SourceSnapshot,
    SourceSnapshotAvailability,
    SourceSnapshotKind,
)

from .errors import ResourceNotFound, RuntimeApiError
from .settings import RuntimeSettings
from .store import RuntimeStore


_CHECKOUT_MARKER = ".knowledge-control-plane-checkout.json"

# Strong, language-agnostic project-root markers. Repository discovery must also
# work for exported source trees where VCS metadata such as .git was removed.
_PROJECT_MARKER_FILES = (
    ".git",
    ".hg",
    ".svn",
    "pom.xml",
    "settings.gradle",
    "settings.gradle.kts",
    "build.gradle",
    "build.gradle.kts",
    "gradlew",
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "package.json",
    "Cargo.toml",
    "go.mod",
    "composer.json",
    "Gemfile",
    "mix.exs",
    "CMakeLists.txt",
)
_PROJECT_MARKER_SUFFIXES = (".sln", ".csproj", ".fsproj", ".vbproj")
_SOURCE_LAYOUT_MARKERS = (
    "src/main/java",
    "src/main/kotlin",
    "src/main/scala",
    "src/main/python",
    "src",
)


def _slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-._").lower() or "repository"
    return slug[:120]


def _repository_id(name: str, location: str) -> str:
    digest = hashlib.sha256(location.encode("utf-8")).hexdigest()[:10]
    return f"{_slug(name)}-{digest}"


def _analysis_repository_id(name: str) -> str:
    """Stable logical repository id used inside analysis artifacts.

    Runtime registration ids keep a location hash to avoid collisions. Analysis
    contracts should not inherit that checkout-specific suffix.
    """
    value = re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_").lower()
    return (value or "repository")[:120]


def _git_revision(path: Path) -> tuple[str | None, str | None]:
    try:
        revision = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        branch = subprocess.run(
            ["git", "-C", str(path), "branch", "--show-current"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        return (
            revision.stdout.strip() or None if revision.returncode == 0 else None,
            branch.stdout.strip() or None if branch.returncode == 0 else None,
        )
    except (OSError, subprocess.SubprocessError):
        return None, None


def _git_worktree_dirty(path: Path) -> bool | None:
    try:
        completed = subprocess.run(
            ["git", "-C", str(path), "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    return bool(completed.stdout.strip())


def _snapshot_fingerprint(payload: dict) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _tracked_ref_payload(value: object) -> GitTrackedRef:
    if isinstance(value, dict):
        try:
            return GitTrackedRef.model_validate(value)
        except Exception:
            pass
    return GitTrackedRef()


def _tracked_refspec(tracked_ref: GitTrackedRef) -> str:
    if tracked_ref.kind is GitTrackedRefKind.HEAD:
        return "HEAD"
    if tracked_ref.kind is GitTrackedRefKind.BRANCH:
        return f"refs/heads/{tracked_ref.name}"
    assert tracked_ref.name is not None
    return tracked_ref.name


def _validate_remote_location(location: str) -> None:
    if location.startswith("-"):
        raise RuntimeApiError(400, "invalid_repository_url", "repository URL cannot start with '-'")
    parsed = urlsplit(location)
    if parsed.username or parsed.password:
        raise RuntimeApiError(
            400,
            "embedded_credentials_forbidden",
            "repository URL must not contain embedded credentials; configure Bitbucket authentication in the Knowledge Control Plane backend environment",
        )
    if parsed.scheme and parsed.scheme not in {"http", "https", "ssh", "file"}:
        raise RuntimeApiError(
            400,
            "unsupported_repository_scheme",
            f"unsupported repository URL scheme: {parsed.scheme}",
        )


@dataclass(frozen=True)
class CheckoutCommand:
    argv: list[str]
    cwd: Path
    environment: dict[str, str]
    target: Path
    action: str


class RepositoryService:
    def __init__(self, store: RuntimeStore, settings: RuntimeSettings) -> None:
        self.store = store
        self.settings = settings
        self.checkout_root = (settings.runtime_root / "repositories").resolve()
        self.checkout_root.mkdir(parents=True, exist_ok=True)
        self.credentials_root = (settings.runtime_root / "credentials").resolve()
        self.credentials_root.mkdir(parents=True, exist_ok=True)

    def discover(self, request: RepositoryDiscoverRequest) -> RepositoryDiscoverResponse:
        discovered: list[RepositorySummary] = []
        warnings: list[str] = []
        for root_value in request.roots or []:
            root = Path(root_value).expanduser().resolve()
            if not root.is_dir():
                warnings.append(f"repository root does not exist: {root}")
                continue
            try:
                candidates = self._local_candidates(root)
            except PermissionError:
                warnings.append(f"repository root is not readable: {root}")
                continue
            except OSError as exc:
                warnings.append(f"cannot inspect repository root {root}: {exc}")
                continue
            for path in candidates:
                revision, branch = _git_revision(path)
                markers = self._project_markers(path)
                repository = RepositorySummary(
                    repository_id=_repository_id(path.name, str(path)),
                    name=path.name,
                    source_kind=RepositorySourceKind.LOCAL,
                    location=str(path),
                    status=RepositoryStatus.AVAILABLE,
                    default_branch=branch,
                    revision=revision,
                    metadata={
                        "discovered_from": str(root),
                        "analysis_repository_id": _analysis_repository_id(path.name),
                        "materialized_path": str(path),
                        "project_markers": markers,
                        "vcs_metadata_present": any(marker in {".git", ".hg", ".svn"} for marker in markers),
                        "discovery_basis": "project_markers" if markers else "explicit_directory",
                        "discovered_as": "explicit_root" if path == root else "direct_child",
                    },
                )
                self.store.upsert_repository(repository)
                discovered.append(repository)
        for remote in request.remotes or []:
            _validate_remote_location(remote.location)
            name = remote.name or Path(remote.location.rstrip("/")).stem.removesuffix(".git") or "repository"
            repository_id = _repository_id(name, remote.location)
            existing = self.store.get_repository(repository_id)
            materialized = self._materialized_path(existing) if existing else None
            repository = RepositorySummary(
                repository_id=repository_id,
                name=name,
                source_kind=RepositorySourceKind.BITBUCKET,
                location=remote.location,
                status=RepositoryStatus.AVAILABLE if materialized else RepositoryStatus.UNAVAILABLE,
                default_branch=existing.default_branch if existing else None,
                revision=existing.revision if existing else None,
                metadata={
                    "registered": True,
                    "analysis_repository_id": _analysis_repository_id(name),
                    "checkout_status": "materialized" if materialized else "not_materialized",
                    "tracked_ref": (
                        remote.tracked_ref.model_dump(mode="json")
                        if remote.tracked_ref is not None
                        else (existing.metadata.get("tracked_ref") if existing else GitTrackedRef().model_dump(mode="json"))
                    ),
                    **({"materialized_path": str(materialized)} if materialized else {}),
                },
            )
            self.store.upsert_repository(repository)
            if request.refresh:
                try:
                    repository = self.materialize_now(repository_id, refresh=True)
                except RuntimeApiError as exc:
                    warnings.append(f"{repository.name}: {exc.message}")
            discovered.append(repository)
        unique = {item.repository_id: item for item in discovered}
        return RepositoryDiscoverResponse(
            repositories=list(unique.values()),
            discovered_count=len(unique),
            warnings=warnings,
        )

    @staticmethod
    def _project_markers(path: Path) -> list[str]:
        markers: list[str] = []
        for marker in _PROJECT_MARKER_FILES:
            if (path / marker).exists():
                markers.append(marker)
        try:
            for child in path.iterdir():
                if child.is_file() and child.suffix.lower() in _PROJECT_MARKER_SUFFIXES:
                    markers.append(child.name)
        except OSError:
            return markers
        for relative in _SOURCE_LAYOUT_MARKERS:
            if (path / relative).is_dir():
                markers.append(relative + "/")
        return sorted(set(markers))

    def _local_candidates(self, root: Path) -> list[Path]:
        """Resolve a user-selected directory into repository candidates.

        An explicitly selected directory is always valid source input. Project markers
        are used only to recognize a container whose direct children are independently
        identifiable projects; they are never required to accept local code.
        """
        if self._project_markers(root):
            return [root]
        marked_children: list[Path] = []
        for child in sorted(root.iterdir()):
            if child.is_dir() and self._project_markers(child):
                marked_children.append(child.resolve())
        return marked_children or [root]

    def list(
        self,
        *,
        offset: int,
        limit: int,
        source_kind: RepositorySourceKind | None,
        search: str | None,
    ) -> RepositoryListResponse:
        items = self.store.list_repositories()
        if source_kind is not None:
            items = [item for item in items if item.source_kind is source_kind]
        if search:
            needle = search.casefold()
            items = [
                item
                for item in items
                if needle in item.name.casefold() or needle in item.location.casefold()
            ]
        total = len(items)
        return RepositoryListResponse(
            items=items[offset : offset + limit],
            page=PageMeta(offset=offset, limit=limit, total=total),
        )

    def get(self, repository_id: str) -> RepositorySummary:
        repository = self.store.get_repository(repository_id)
        if repository is None:
            raise ResourceNotFound("repository", repository_id)
        return repository

    @staticmethod
    def analysis_repository_id(repository: RepositorySummary) -> str:
        configured = repository.metadata.get("analysis_repository_id")
        if isinstance(configured, str) and configured.strip():
            return configured.strip()
        return _analysis_repository_id(repository.name)

    def execution_path(self, repository_id: str) -> Path:
        repository = self.get(repository_id)
        if repository.source_kind is RepositorySourceKind.LOCAL:
            path = Path(repository.location).expanduser().resolve()
        else:
            path = self._materialized_path(repository)
            if path is None:
                raise RuntimeApiError(
                    409,
                    "repository_not_materialized",
                    f"remote repository is not checked out: {repository_id}",
                )
        if not path.is_dir():
            raise RuntimeApiError(409, "repository_unavailable", f"repository path is unavailable: {path}")
        return path

    def resolve_snapshot(self, repository_id: str) -> SourceSnapshot:
        repository = self.get(repository_id)
        checked_at = datetime.now(UTC)
        if repository.source_kind is RepositorySourceKind.LOCAL:
            path = Path(repository.location).expanduser().resolve()
            revision, branch = _git_revision(path)
            dirty = _git_worktree_dirty(path)
            if revision is None:
                payload = {
                    "source_id": repository_id,
                    "source_kind": SourceSnapshotKind.GIT.value,
                    "location": str(path),
                    "availability": SourceSnapshotAvailability.UNAVAILABLE.value,
                    "diagnostic": "local source has no resolvable Git commit; automated refresh requires immutable Git revision",
                }
                return SourceSnapshot(
                    source_id=repository_id,
                    source_kind=SourceSnapshotKind.GIT,
                    location=str(path),
                    resolved_version={},
                    checked_at=checked_at,
                    snapshot_fingerprint=_snapshot_fingerprint(payload),
                    availability=SourceSnapshotAvailability.UNAVAILABLE,
                    diagnostic=payload["diagnostic"],
                )
            if dirty:
                payload = {
                    "source_id": repository_id,
                    "source_kind": SourceSnapshotKind.GIT.value,
                    "location": str(path),
                    "revision": revision,
                    "dirty": True,
                }
                return SourceSnapshot(
                    source_id=repository_id,
                    source_kind=SourceSnapshotKind.GIT,
                    location=str(path),
                    requested_ref=GitTrackedRef(kind=GitTrackedRefKind.BRANCH, name=branch) if branch else GitTrackedRef(),
                    resolved_version={"kind": "git_commit", "commit_sha": revision},
                    checked_at=checked_at,
                    snapshot_fingerprint=_snapshot_fingerprint(payload),
                    availability=SourceSnapshotAvailability.UNAVAILABLE,
                    diagnostic="local Git working tree is dirty; automated refresh will not guess a reproducible source snapshot",
                )
            requested = GitTrackedRef(kind=GitTrackedRefKind.BRANCH, name=branch) if branch else GitTrackedRef()
            resolved = {"kind": "git_commit", "commit_sha": revision}
            payload = {
                "source_id": repository_id,
                "source_kind": SourceSnapshotKind.GIT.value,
                "location": str(path),
                "requested_ref": requested.model_dump(mode="json"),
                "resolved_version": resolved,
            }
            return SourceSnapshot(
                source_id=repository_id,
                source_kind=SourceSnapshotKind.GIT,
                location=str(path),
                requested_ref=requested,
                resolved_version=resolved,
                checked_at=checked_at,
                snapshot_fingerprint=_snapshot_fingerprint(payload),
            )

        _validate_remote_location(repository.location)
        tracked_ref = _tracked_ref_payload(repository.metadata.get("tracked_ref"))
        refspec = _tracked_refspec(tracked_ref)
        environment = os.environ.copy()
        environment.update(self._git_environment())
        try:
            completed = subprocess.run(
                ["git", "-c", "credential.helper=", "ls-remote", "--exit-code", "--", repository.location, refspec],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
                env=environment,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            completed = None
            detail = f"{type(exc).__name__}: {exc}"
        else:
            detail = (completed.stderr or completed.stdout or "").strip().splitlines()[-1:] or [""]
            detail = detail[0]
        commit_sha: str | None = None
        if completed is not None and completed.returncode == 0:
            for line in completed.stdout.splitlines():
                parts = line.split()
                if len(parts) >= 2 and parts[1] == refspec and re.fullmatch(r"[0-9a-fA-F]{40,64}", parts[0]):
                    commit_sha = parts[0].lower()
                    break
        if commit_sha is None:
            payload = {
                "source_id": repository_id,
                "source_kind": SourceSnapshotKind.GIT.value,
                "location": repository.location,
                "requested_ref": tracked_ref.model_dump(mode="json"),
                "availability": SourceSnapshotAvailability.UNAVAILABLE.value,
            }
            return SourceSnapshot(
                source_id=repository_id,
                source_kind=SourceSnapshotKind.GIT,
                location=repository.location,
                requested_ref=tracked_ref,
                resolved_version={},
                checked_at=checked_at,
                snapshot_fingerprint=_snapshot_fingerprint(payload),
                availability=SourceSnapshotAvailability.UNAVAILABLE,
                diagnostic=f"cannot resolve tracked Git ref {refspec}: {detail or 'ref not found'}",
            )
        resolved = {"kind": "git_commit", "commit_sha": commit_sha}
        payload = {
            "source_id": repository_id,
            "source_kind": SourceSnapshotKind.GIT.value,
            "location": repository.location,
            "requested_ref": tracked_ref.model_dump(mode="json"),
            "resolved_version": resolved,
        }
        return SourceSnapshot(
            source_id=repository_id,
            source_kind=SourceSnapshotKind.GIT,
            location=repository.location,
            requested_ref=tracked_ref,
            resolved_version=resolved,
            checked_at=checked_at,
            snapshot_fingerprint=_snapshot_fingerprint(payload),
        )

    def pinned_execution_path(self, repository_id: str, *, job_id: str) -> Path:
        root = (self.settings.jobs_root / job_id / "sources").resolve()
        target = (root / repository_id).resolve()
        if target.parent != root:
            raise RuntimeApiError(400, "unsafe_checkout_path", "pinned checkout path escaped job root")
        return target

    def pinned_checkout_commands(
        self,
        repository_id: str,
        *,
        job_id: str,
        commit_sha: str,
        preview: bool = False,
    ) -> list[CheckoutCommand]:
        """Build job-local commands for an exact immutable Git commit.

        Both local and remote Git sources are cloned into the job source area. Reading a
        local working tree directly after freshness resolution would not be immutable: its
        HEAD could move before Runner starts. Preview mode is side-effect free.
        """
        repository = self.get(repository_id)
        if not re.fullmatch(r"[0-9a-fA-F]{40,64}", commit_sha):
            raise RuntimeApiError(422, "source_snapshot_invalid", "pinned Git commit SHA is invalid")
        target = self.pinned_execution_path(repository_id, job_id=job_id)
        if not preview:
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                shutil.rmtree(target)
        if repository.source_kind is RepositorySourceKind.LOCAL:
            source = str(Path(repository.location).expanduser().resolve())
            environment: dict[str, str] = {}
        else:
            _validate_remote_location(repository.location)
            source = repository.location
            environment = self._git_preview_environment() if preview else self._git_environment()
        return [
            CheckoutCommand(
                argv=["git", "-c", "credential.helper=", "clone", "--no-checkout", "--", source, str(target)],
                cwd=target.parent,
                environment=environment,
                target=target,
                action="pinned_clone",
            ),
            CheckoutCommand(
                argv=["git", "-c", "credential.helper=", "-C", str(target), "checkout", "--detach", commit_sha],
                cwd=target.parent,
                environment=environment,
                target=target,
                action="pinned_checkout",
            ),
        ]

    def cleanup_failed_pinned_checkout(self, repository_id: str, *, job_id: str) -> None:
        target = self.pinned_execution_path(repository_id, job_id=job_id)
        sources_root = (self.settings.jobs_root / job_id / "sources").resolve()
        if target.parent == sources_root and target.exists():
            shutil.rmtree(target, ignore_errors=True)

    def finalize_pinned_checkout(self, repository_id: str, *, job_id: str, expected_commit_sha: str) -> Path:
        target = self.pinned_execution_path(repository_id, job_id=job_id)
        revision, _branch = _git_revision(target)
        if revision is None or revision.lower() != expected_commit_sha.lower():
            raise RuntimeApiError(
                409,
                "source_snapshot_mismatch",
                "pinned repository checkout does not match resolved source snapshot",
                details={"repository_id": repository_id, "expected": expected_commit_sha, "actual": revision},
            )
        return target

    def planned_execution_path(self, repository_id: str) -> Path:
        """Return the path that execution will use, without materializing a remote repository."""
        repository = self.get(repository_id)
        if repository.source_kind is RepositorySourceKind.LOCAL:
            return Path(repository.location).expanduser().resolve()
        existing = self._materialized_path(repository)
        return existing or (self.checkout_root / repository.repository_id).resolve()

    def preview_checkout_command(
        self, repository_id: str, *, refresh: bool = False
    ) -> CheckoutCommand | None:
        """Plan the checkout command without creating credentials or mutating checkout paths."""
        repository = self.get(repository_id)
        if repository.source_kind is RepositorySourceKind.LOCAL:
            return None
        _validate_remote_location(repository.location)
        existing = self._materialized_path(repository)
        environment = self._git_preview_environment()
        if existing and not refresh:
            return None
        if existing:
            return CheckoutCommand(
                argv=["git", "-c", "credential.helper=", "-C", str(existing), "pull", "--ff-only"],
                cwd=self.checkout_root,
                environment=environment,
                target=existing,
                action="refresh",
            )
        target = (self.checkout_root / repository.repository_id).resolve()
        if target.parent != self.checkout_root:
            raise RuntimeApiError(400, "unsafe_checkout_path", "checkout path escaped runtime root")
        if target.exists():
            marker = target / ".git" / _CHECKOUT_MARKER
            if not marker.is_file():
                raise RuntimeApiError(
                    409,
                    "checkout_path_not_owned",
                    f"refusing to replace non-owned checkout path: {target}",
                )
        return CheckoutCommand(
            argv=["git", "-c", "credential.helper=", "clone", "--", repository.location, str(target)],
            cwd=self.checkout_root,
            environment=environment,
            target=target,
            action="clone",
        )

    def checkout_command(self, repository_id: str, *, refresh: bool = False) -> CheckoutCommand | None:
        repository = self.get(repository_id)
        if repository.source_kind is RepositorySourceKind.LOCAL:
            return None
        _validate_remote_location(repository.location)
        existing = self._materialized_path(repository)
        environment = self._git_environment()
        if existing and not refresh:
            return None
        if existing:
            return CheckoutCommand(
                argv=["git", "-c", "credential.helper=", "-C", str(existing), "pull", "--ff-only"],
                cwd=self.checkout_root,
                environment=environment,
                target=existing,
                action="refresh",
            )
        target = (self.checkout_root / repository.repository_id).resolve()
        if target.parent != self.checkout_root:
            raise RuntimeApiError(400, "unsafe_checkout_path", "checkout path escaped runtime root")
        if target.exists():
            marker = target / ".git" / _CHECKOUT_MARKER
            if not marker.is_file():
                raise RuntimeApiError(
                    409,
                    "checkout_path_not_owned",
                    f"refusing to replace non-owned checkout path: {target}",
                )
            shutil.rmtree(target)
        return CheckoutCommand(
            argv=["git", "-c", "credential.helper=", "clone", "--", repository.location, str(target)],
            cwd=self.checkout_root,
            environment=environment,
            target=target,
            action="clone",
        )


    def cleanup_failed_checkout(self, repository_id: str, target: Path) -> None:
        expected = (self.checkout_root / repository_id).resolve()
        resolved = target.resolve()
        if resolved != expected or resolved.parent != self.checkout_root:
            return
        if resolved.exists():
            shutil.rmtree(resolved, ignore_errors=True)

    def finalize_checkout(self, repository_id: str, target: Path) -> RepositorySummary:
        repository = self.get(repository_id)
        if not (target / ".git").exists():
            raise RuntimeApiError(500, "checkout_invalid", "git checkout completed without a .git directory")
        (target / ".git" / _CHECKOUT_MARKER).write_text(
            '{"schema_version":"knowledge_control_plane_checkout/v1"}\n', encoding="utf-8"
        )
        revision, branch = _git_revision(target)
        metadata = dict(repository.metadata)
        metadata.update(
            {
                "checkout_status": "materialized",
                "materialized_path": str(target.resolve()),
            }
        )
        updated = repository.model_copy(
            update={
                "status": RepositoryStatus.AVAILABLE,
                "default_branch": branch,
                "revision": revision,
                "metadata": metadata,
            }
        )
        self.store.upsert_repository(updated)
        return updated

    def materialize_now(
        self,
        repository_id: str,
        *,
        refresh: bool = False,
    ) -> RepositorySummary:
        command = self.checkout_command(repository_id, refresh=refresh)
        if command is None:
            return self.get(repository_id)
        environment = os.environ.copy()
        environment.update(self._git_environment())
        try:
            completed = subprocess.run(
                command.argv,
                cwd=command.cwd,
                env=environment,
                capture_output=True,
                text=True,
                timeout=600,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            if command.action == "clone":
                self.cleanup_failed_checkout(repository_id, command.target)
            raise RuntimeApiError(
                502,
                "git_checkout_failed",
                f"git checkout failed: {type(exc).__name__}",
            ) from exc
        if completed.returncode != 0:
            if command.action == "clone":
                self.cleanup_failed_checkout(repository_id, command.target)
            detail = (completed.stderr or completed.stdout or "").strip().splitlines()
            suffix = f": {detail[-1]}" if detail else ""
            raise RuntimeApiError(
                502,
                "git_checkout_failed",
                f"git checkout failed with exit code {completed.returncode}{suffix}",
            )
        return self.finalize_checkout(repository_id, command.target)

    def _materialized_path(self, repository: RepositorySummary | None) -> Path | None:
        if repository is None:
            return None
        raw = repository.metadata.get("materialized_path")
        if not isinstance(raw, str):
            return None
        path = Path(raw).expanduser().resolve()
        if path.is_dir() and (path / ".git").exists():
            return path
        return None

    def _git_preview_environment(self) -> dict[str, str]:
        """Return only the environment shape used by checkout, without exposing secrets."""
        token_present = bool(os.getenv("BITBUCKET_TOKEN") or os.getenv("BITBUCKET_ACCESS_TOKEN"))
        base = {
            "GIT_TERMINAL_PROMPT": "0",
            "GCM_INTERACTIVE": "Never",
            "SSH_ASKPASS_REQUIRE": "never",
        }
        if not token_present:
            return {**base, "GIT_ASKPASS": "/bin/false", "SSH_ASKPASS": "/bin/false"}
        return {
            **base,
            "GIT_ASKPASS": str(self.credentials_root / "git-askpass.py"),
            "SSH_ASKPASS": "/bin/false",
            "KNOWLEDGE_CONTROL_PLANE_GIT_USERNAME": "<redacted>",
            "KNOWLEDGE_CONTROL_PLANE_GIT_TOKEN": "<redacted>",
        }

    def _git_environment(self) -> dict[str, str]:
        username = os.getenv("BITBUCKET_USERNAME")
        token = os.getenv("BITBUCKET_TOKEN") or os.getenv("BITBUCKET_ACCESS_TOKEN")
        base = {
            "GIT_TERMINAL_PROMPT": "0",
            "GCM_INTERACTIVE": "Never",
            "SSH_ASKPASS_REQUIRE": "never",
            "SSH_ASKPASS": "/bin/false",
        }
        if not token:
            return {**base, "GIT_ASKPASS": "/bin/false"}
        askpass = self.credentials_root / "git-askpass.py"
        if not askpass.exists():
            askpass.write_text(
                "#!/usr/bin/env python3\n"
                "import os, sys\n"
                "prompt = ' '.join(sys.argv[1:]).lower()\n"
                "print(os.environ.get('KNOWLEDGE_CONTROL_PLANE_GIT_USERNAME', 'x-token-auth') "
                "if 'username' in prompt else os.environ['KNOWLEDGE_CONTROL_PLANE_GIT_TOKEN'])\n",
                encoding="utf-8",
            )
            askpass.chmod(0o700)
        return {
            **base,
            "GIT_ASKPASS": str(askpass),
            "KNOWLEDGE_CONTROL_PLANE_GIT_USERNAME": username or "x-token-auth",
            "KNOWLEDGE_CONTROL_PLANE_GIT_TOKEN": token,
        }
